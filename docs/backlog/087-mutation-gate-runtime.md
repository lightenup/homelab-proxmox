# Backlog: the mutation gate takes ~40 minutes and blocks the only runner

**Status**: Backlog — raised 2026-10-18, while PR #259 (`086`) waited behind it. Spec only.
**Revised 2026-10-22**: a trial of mutmut 3 (below) made the migration the main fix, and the owner
decided the PR, results and regression behaviour.
**Order**: Independent. Worth doing before the next Python-heavy feature.

## Why this exists

When the `Mutation gate` (`.github/workflows/mutation.yml`) runs, it takes about 40 minutes:
43 minutes on `remove-adguard` and on `deps-hygiene`. It runs on the only self-hosted runner
(`pi-ci`), so for that time nothing else can use the runner, including `Prod 1 - LXC Promote`.

On 2026-10-18 it ran twice for PR #259. That PR only added a workflow test,
`python/tests/workflows/test_confidence_gate_paths.py`, which doesn't touch the code being
mutated. Both runs had to be cancelled so a promote could start, which left the PR with no
mutation result.

## Current state (verified 2026-10-18)

- **The cache is used, but it only remembers killed mutants.**
  - mutmut `2.5.1` keeps its `.mutmut-cache` on the NAS, at
    `/mnt/nas/homelab_ci/mutmut-cache/<branch>`.
  - `cached_mutation_status` (`mutmut/cache.py`) always reuses a mutant marked killed.
  - Every other mutant is re-run whenever `hash_of_tests` changes. That is a SHA-256 over every
    `test*.py` file under `--tests-dir` (`python/tests`).
- **The scale:** the cache holds about 1,490 mutants of
  `python/src/homelab_proxmox_orchestrator`:
  - about 870 `bad_survived`
  - about 620–630 `ok_killed`
  - 1 `bad_timeout`

  That is the 41% floor in `python/mutmut-threshold.txt`. So any PR that changes any test
  re-runs about 870 mutants.
- **Each mutant is a full pytest run with `-n auto`.** mutmut 2 has no per-mutant test
  selection, so every mutant runs all 103 tests, which take about 6 seconds serially. With
  `-n auto`, pytest-xdist also starts new worker processes for every mutant.
- **The gate triggers on any `^python/` change.** That includes tests that never import the
  orchestrator, like the PR #259 example.
- **The `main` baseline cache is three months old.**
  - `mutmut-cache/main` was last written on 2026-07-20, and new branches are seeded from it.
  - PR runs write only their own branch's file.
  - The writer for `main` is `nightly-deeper-verification.yml`, and it has failed every night
    since at least 2026-10-14, after about a minute, with
    `::error::Shared cache mount missing at /mnt/nas/homelab_ci`. The cause: on a `schedule` run,
    `inputs.run_on_pve` is empty, because input defaults only apply to `workflow_dispatch`. So
    every step guarded by `!inputs.run_on_pve` runs on the Pi runner, which has no NAS mount.
- **Stale per-branch cache files** pile up on the NAS: 11 files, some from June.

## Measured 2026-10-22: mutmut 2.5.1 today vs mutmut 3.8.0

- **Today (mutmut 2.5.1, on `pve`)**: the PR #266 (`090`) gate took **57 min 10 s**, over 1,866
  mutants: 785 killed, 1,081 survived, 1 timeout. Score 42.07% against the 41% floor.
- **mutmut 3.8.0** (latest, released 2026-09-12; needs Python 3.10 or newer) works differently:
  - it records which tests reach each function and runs only those tests for each mutant, in a
    forked process;
  - results live per function in `mutants/`, and only changed functions are re-tested;
  - `mutmut run "pkg.module*"` limits a run to one module, and `mutmut browse` is a terminal UI to
    inspect survivors and re-test one function or module.
- **Trial**: on a scratch copy of the `090` branch, on the dev Mac (Python 3.14, 16 workers),
  test selection `python/tests/orchestrator` and `python/tests/version_currency`:

  | Run | Time |
  |---|---|
  | Full run, 4,118 mutants (3.x generates more operators than 2.x) | **1 min 44 s** |
  | Rerun after changing one function | **5 s** |
  | Re-test one module (`version_currency*`) | 13 s |

  Results: 1,348 killed, 626 survived, 2,144 with no test reaching them. That is 68% of the
  reached mutants. Most of the "no tests" mutants come from the trial's narrow test selection
  (`cli`, `ops_cli`, `service_lifecycle`, `inventory`, `healthcheck_runner`, `terraform_backup`
  are exercised from other test directories or through subprocesses).
- **What the migration needs** (each one hit during the trial):
  1. **Layout**: mutmut 3 finds source only under `./`, `src/` or `source/`. With
     `python/src/homelab_proxmox_orchestrator`, test hits are recorded as
     `homelab_proxmox_orchestrator.*` but mutants as `python.src.homelab_proxmox_orchestrator.*`,
     and the run stops. The trial used a `src -> python/src` symlink at the repo root and
     `source_paths = src/homelab_proxmox_orchestrator`.
  2. **Config**: a `[mutmut]` section in a root `setup.cfg` (or `[tool.mutmut]` in
     `pyproject.toml`) replaces `python/mutmut.ini`. List values go one per line. Needed:
     `pytest_add_cli_args = -c python/pytest.ini -o addopts= -o pythonpath=src`, because
     `pytest.ini`'s `pythonpath = python/src` otherwise imports an unmutated copy. Also needed:
     `also_copy` of `python/tests`, `python/pytest.ini`, `scripts`, `terraform` and
     `Taskfile.yml`, which tests read as fixtures.
  3. **Tests**: four tests start `"python3"` with `env={"PYTHONPATH": "python/src"}`
     (`test_cli.py`, `test_runner_plan_apply.py`, `test_provenance_mismatch.py`, `test_exec.py`).
     That bypasses the venv and the mutated copy. Use `sys.executable`, and point `PYTHONPATH`
     at the imported package's location.
  4. **Guard tests** under `python/tests/guardrails` read repo files and don't import the package,
     so they can't kill mutants. Leave them out of the mutation run. `also_copy` turns the
     `ansible/playbooks/group_vars` symlink into a real directory, which breaks
     `test_monitoring_pins_assigned_once`.
  5. **Score**: 3.x has more mutants and a "no tests" category, so the 41% floor doesn't carry
     over. Re-baseline on `main`.
- **NAS**: `/volume1/homelab_ci` is exported over NFS to `192.168.1.0/24` and is mounted on `pve`
  at `/mnt/nas/homelab_ci`.

## Decisions (owner, 2026-10-22)

- **PR**: keep the required `result` check, as a fast incremental mutmut 3 run seeded from
  `main`'s nightly results. The nightly does the full run and sets the baseline.
- **Results on the Mac**: a pull script through `ssh ci@pve`, with no NFS mount on the Mac.
- **Regression**: when the nightly score drops below the floor, the job fails red and posts a short
  summary to ntfy.

## Requirements

- **FR-001 — Migrate to mutmut 3.** Lock `mutmut` 3.x in `python/requirements-nightly.lock.txt`,
  move the config to the root, and fix the layout and the subprocess tests (points 1–4 above).
  Rewrite `scripts/ci/mutmut-threshold.sh` for the 3.x results (`mutmut export-cicd-stats`). Parity
  (Constitution V): it still runs the same way on the Mac, on `pve` and in CI.
- **FR-002 — Nightly full run on PVE.** `nightly-deeper-verification.yml` runs the full mutation
  run on `pve` on every `schedule` run. This fixes the empty-input bug: a scheduled run must not
  depend on `workflow_dispatch` input defaults. It fails loudly if it can't write the results.
- **FR-003 — Published results.** After each nightly run, `pve` writes the `mutants/` directory, the
  score and a survivor report (survivors per module, worst first) to
  `/mnt/nas/homelab_ci/mutmut/main/`, together with the commit SHA and the time.
- **FR-004 — Fast PR gate.** `mutation.yml` seeds `mutants/` from `main`'s published results and
  runs mutmut incrementally, so only functions changed on the branch are re-tested. It keeps the
  path guard and the skip-as-pass `result` job. The gate fails if the branch's score is below the
  floor minus the margin.
- **FR-005 — Pull results to the Mac.** A Taskfile task (e.g. `task mutmut:pull`) rsyncs the
  published results through `ssh ci@pve` into the local `mutants/`. After a pull,
  `mutmut browse` shows current survivors and `mutmut run "<module>*"` re-tests only local changes.
  Document the loop in `docs/`.
- **FR-006 — Regression alert.** When the nightly score is below the floor minus the margin, the
  job fails and posts title, score, floor and the top modules by survivors to an ntfy topic, as a
  publisher under the `082` contract.
- **FR-007 — Re-baseline.** Measure the 3.x score on `main` and set
  `python/mutmut-threshold.txt` from it, recording how "no tests" mutants are counted. Ratchet it
  up by hand afterwards.
- **FR-008 — Prune stale caches.** Remove the per-branch mutmut 2 `.mutmut-cache` files under
  `/mnt/nas/homelab_ci/mutmut-cache/` once the migration lands. Any per-branch 3.x results for
  closed branches are removed, or removed after an age limit.

## Success criteria

- **SC-001**: A PR that only changes non-orchestrator tests, workflows or docs skips the mutation
  job.
- **SC-002**: A PR that changes one orchestrator function finishes the gate in under 10 minutes
  with a fresh `main` baseline.
- **SC-003**: The nightly run is green, and the published `main` results are less than 48 hours
  old.
- **SC-004**: After `task mutmut:pull`, re-testing one changed module on the Mac takes under a
  minute.
- **SC-005**: A deliberately weakened test on a throwaway branch makes the nightly-equivalent run
  fail and an ntfy message arrive.

## Out of scope / later

- **Moving the package** to a root `src/` layout instead of the symlink. Cleaner, but it touches
  every import path, the Taskfile and the workflows.
- **Adding a second self-hosted runner.** That removes the contention, not the cost.
