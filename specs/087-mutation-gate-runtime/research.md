# Research: Mutation Gate Runtime

**Feature**: `087-mutation-gate-runtime` | **Date**: 2026-10-24

Sources: the backlog item (trial on the Mac, 2026-10-22), the workflows on `main` (`9d80372`), the
mutmut 3.8.0 wheel source, and a timed trial on `pve` on 2026-10-24 (below).

## R1. Trial on `pve` (2026-10-24)

A throwaway copy of `main` in `/tmp/mm-trial` on `pve`, deleted afterwards. Python 3.11 venv from
`uv`, `requirements-test.lock.txt` plus `mutmut==3.8.0`. The backlog's migration points 1–4 were
applied, plus the `task_smoke` fix from R4. 8 cores, idle host, everything at `nice -n 19`.

| Run | Time | Result |
|---|---|---|
| Test suite alone (158 tests, guard and workflow tests excluded) | 0.78 s | all pass |
| Fresh full run, 4,117 mutants | **39 s** | 1,717 killed, 1,061 survived, 1,337 no tests, 2 timeouts |
| Rerun after touching every source file (simulates a fresh checkout over a seeded results set) | 6 s | unchanged |
| Rerun after changing one function | 3 s | 2 new mutants, both survived |
| Rerun seeded with only the result files (1.2 MB, 20 files) | 7 s | unchanged |

Score with the FR-010 formula: 1,717 / (1,717 + 1,061) = **61.81%**.

The Mac trial (1 min 44 s for 4,118 mutants) used a narrow test selection, so many functions had no
tests. With the full selection, `pve` is faster still, because each mutant runs only the few tests
that reach it.

## R2. PR gate: fresh full run, not incremental

- **Decision**: Every PR run deletes `mutants/` and does a full run. It reads nothing from the NAS.
- **Rationale**: 39 s for a full run makes the incremental design's savings (about 35 s) smaller
  than its cost. It needs seeding, a staleness check with a fallback, and it has the blind spot in
  R3. A fresh run also means a PR's score depends only on that PR's commit. The owner chose this on
  2026-10-24 (spec Clarifications).
- **Alternatives considered**: Incremental from `main`'s results (the 2026-10-22 decision). Rejected
  for the reasons above. Incremental, with a full run forced whenever tests change: correct, but it
  keeps both code paths for a 35 s saving.

## R3. How mutmut 3.8 decides what to re-test

Read from `mutmut/__main__.py` in the 3.8.0 wheel:

- A cached verdict (`exit_code_by_key` in each `mutants/**/*.py.meta`) is reset only when its
  function's source hash changes (`create_mutants_for_file`), when the pytest arguments or test
  selection change (`config_fingerprint`), or, if `on_dependency_change = "rerun"`, when a watched
  non-Python file changes.
- **New or edited tests do not reset verdicts.** New tests only add to the test map
  (`run_stats_collection(runner, tests=new_tests)`). The main loop keeps any cached result
  ("Rerun mutant if it's explicitly mentioned, but otherwise let the result stand"), and that
  includes `no tests` (exit code 33).
- **Consequence**: an incremental run cannot score a test change. That is why the nightly and the PR
  gate both start from an empty `mutants/`. Only the Mac loop is incremental, which is right for
  "I changed this module, re-test it".
- Source change detection uses file mtimes first, then function hashes. A checkout makes every
  source file newer than the seeded mutants, so all files are re-parsed (6 s), but only changed
  functions lose their verdicts. Seeding by `rsync -a` (mtimes kept) is therefore safe.
- `mutants/mutmut-stats.json` holds the test map, durations, function hashes, config fingerprint and
  the `git_commit` of the last full run. No file under `mutants/` holds an absolute path, so a set
  made in `/home/ci/homelab-proxmox` works in any checkout.

## R4. Migration changes (the backlog's five points, checked)

1. **Layout**: a `src -> python/src` symlink at the repo root, and
   `source_paths = src/homelab_proxmox_orchestrator`. Confirmed on `pve`.
2. **Config**: a `[mutmut]` section in a new root `setup.cfg` replaces `python/mutmut.ini`. Values
   used in the trial:
   - `pytest_add_cli_args = -c python/pytest.ini -o addopts= -o pythonpath=src`, one per line.
   - `pytest_add_cli_args_test_selection = python/tests`, `--ignore=python/tests/guardrails` and
     `--ignore=python/tests/workflows`.
   - `also_copy` = `python/tests`, `python/pytest.ini`, `scripts`, `terraform`, `Taskfile.yml`.
   `setup.cfg` is in mutmut's default `also_copy` and default watched files.
3. **Subprocess tests**: the backlog named four (`test_cli.py`, `test_runner_plan_apply.py`,
   `test_provenance_mismatch.py`, `test_exec.py`). **A fifth was found**:
   `python/tests/task_smoke/helpers.py` (`run_ops_cli`) puts `repo_root/python/src` first on
   `PYTHONPATH`. Under mutmut, stats collection failed on
   `test_top10_tasks.py::test_service_add_smoke_success` with `No module named
   'homelab_proxmox_orchestrator'`. The fix, applied to all five: run `sys.executable`, and point
   `PYTHONPATH` at the imported package's parent,
   `Path(homelab_proxmox_orchestrator.__file__).resolve().parents[1]`. That is `python/src` in a
   normal run and `mutants/src` under mutmut, so the tests still pass outside mutmut.
   `test_exec.py` only needs `sys.executable`.
4. **Guard and workflow tests**: excluded through the test selection above. `python/tests/workflows`
   imports nothing from the package either (0 of 2 files), so it is excluded too. The other test
   directories all import it.
5. **Score**: re-baselined, see R6.

## R5. Nightly fix (FR-002, PR 1)

- **Root cause**: in `nightly-deeper-verification.yml` every PVE step is guarded by
  `if: ${{ inputs.run_on_pve }}` and every runner-local step by `!inputs.run_on_pve`. On a
  `schedule` event `inputs` is empty, so the runner-local steps run on `pi-ci`, which has no NAS
  mount, and `Prepare mutmut shared cache` fails.
- **Decision**: remove the `run_on_pve` and `run_mutmut` inputs and the runner-local mutation steps.
  Every nightly run does the mutation run on PVE.
- **Rationale**: the runner-local path cannot work on the only runner (no NAS mount), and
  `run_mutmut` is read by no step. A guard that ignores the event type (`github.event_name !=
  'workflow_dispatch' || inputs.run_on_pve`) would fix the symptom but keep a path that always
  fails (Constitution IV). Parity is kept by the gate script, which runs on the Mac too.
- **Alternatives considered**: the event-type guard above. It is one line shorter in the diff and
  leaves two dead paths.
- **Alert test input (PR 2)**: one optional `workflow_dispatch` input, `min_score` (string, default
  empty), passed to the gate script as `MUTMUT_MIN_SCORE`. On a scheduled run it is empty, so the
  committed floor applies and nothing depends on input defaults. The `gate` job's
  `no-new-commits` skip must not apply to `workflow_dispatch`, or a manual run on an unchanged
  `main` would be skipped.
- **Note**: under mutmut 2, PR 1's nightly takes about an hour at 03:00, as it did before July. PR 2
  brings it under a minute. PR 1 still has a use: it is the only way the mutmut 2 cache for `main`
  gets refreshed before PR 2 lands.

## R6. Score and floor (FR-010)

- **Decision**: `score = 100 * killed / (killed + survived)`. Excluded: `no tests`, `timeout`,
  `suspicious`, `skipped`, `segfault`, and `caught by type check` (no type-check command is set, so
  that count stays at 0). The input is `mutants/mutmut-cicd-stats.json` from
  `mutmut export-cicd-stats`, which has `killed`, `survived`, `no_tests`, `timeout`, `suspicious`,
  `skipped`, `segfault` and `total`.
- **Proposed floor**: **61.0**, from 61.81% on `main` at `9d80372` (R1), rounded down to a whole
  point as the 41.0 floor was. With the 1.0 margin the gate line is 60.0%. Re-measure on the
  migration PR's own commit before committing the floor: the subprocess fixes in R4 let those tests
  kill mutants they could not reach before, so the number can move.
- **Alternatives considered**: counting no-tests as survived (about 42%), rejected by the owner.

## R7. Published results (FR-003)

- **What is published**: the result files only, not the whole `mutants/` tree. That is every
  `mutants/**/*.meta`, `mutmut-stats.json`, `mutmut-cicd-stats.json`, plus two new files, `report.json`
  and `survivors.txt` (see [contracts/published-results.md](contracts/published-results.md)). That
  is about 1.2 MB; the whole tree is 21 MB.
- **Rationale**: the tree also holds `also_copy` copies of the tests. mutmut refreshes those copies
  but never deletes stale files, so a seeded tree can run a test that has since been deleted.
  Without the copies, mutmut regenerates the mutated sources and copies the tests fresh. Trial: 7 s,
  same verdicts.
- **Atomic swap**: each publish writes a new directory `mutmut/main-<UTC timestamp>/`, then repoints
  the `mutmut/main` symlink with `ln -sfn` to a temporary name and `mv -T` over `main`. A rename is
  atomic on the NFS server, so the Mac pull sees the old set or the new one. Afterwards only the
  newest two `main-*` directories are kept.
- **Alternatives considered**: `rsync --delete` straight into `main/`, which a concurrent pull could
  catch half done.

## R8. Regression alert (FR-009)

- **Decision**: a new ntfy publisher, account `mutation`, topic `mutation`, onboarded with
  `docs/runbooks/ntfy-add-publisher.md`. The nightly reads `ntfy_mutation_token` from
  `ansible/group_vars/services/vault.yml` on the runner, the same way `version-currency.yml` reads
  `ntfy_version_check_token`. The message is built from `report.json` and posted with `curl` from a
  step that runs only when the score check failed.
- **Rationale**: ntfy's preflight asserts one publisher per topic, so the alert cannot reuse
  `versions`. The publish happens on the runner, so the token never travels to PVE. The alert is
  CI-only behaviour. On the Mac the same gate script prints the same summary, and nothing is sent.
- **Alternatives considered**: publishing from inside the gate script when `NTFY_TOKEN` is set.
  The token would then have to be sent to PVE over SSH.

## R9. Trigger paths (FR-006)

The `gate` job in `mutation.yml` runs the mutation job when any changed path matches:

- `^python/src/`
- `^python/tests/`, except `^python/tests/(guardrails|workflows)/`
- `^python/(pytest\.ini|mutmut-threshold\.txt|requirements-(test|nightly)(\.lock)?\.txt)$`
- `^setup\.cfg$`, `^src$` (the layout symlink)
- `^scripts/ci/mutmut-threshold\.sh$`
- `^\.github/workflows/mutation\.yml$`

Fixtures that tests read (`scripts/`, `terraform/`, `Taskfile.yml`) do not trigger it. A change
there that breaks a test is caught by the normal test run, and the next nightly scores it.

## R10. Concurrency on PVE

The nightly and the PR gate both sync into `/home/ci/homelab-proxmox` on PVE with
`rsync --delete`. They cannot overlap, because the only self-hosted runner runs one job at a time.
No change is needed. A second runner (out of scope) would have to give each job its own directory.

## R11. Mac loop (FR-008)

- The local `.venv` is Python 3.15. mutmut 3.8 needs 3.10 or newer, and the Mac trial on 3.14
  worked. 3.15 itself is untried. If `libcst` or `setproctitle` have no 3.15 wheel,
  the fallback is a separate `.venv-mutmut` on Python 3.14, used through `PYTHON_BIN` (tasks T012). `requirements-nightly.lock.txt` is compiled with `--python-version 3.11 --universal`, so
  its pins apply on the Mac too.
- `task mutmut:pull` rsyncs `ci@pve:/mnt/nas/homelab_ci/mutmut/main/` into a temporary directory,
  checks that `report.json` is present, then replaces the result files in `./mutants/` and prints
  `report.json`'s commit and age. On any failure it leaves `./mutants/` as it was.
- Then plain `mutmut run` re-tests only functions changed locally, keeping the pulled verdicts for
  the rest. `mutmut run "homelab_proxmox_orchestrator.<module>*"` names mutants explicitly, so it
  re-tests every mutant in that module (13 s for `version_currency` in the Mac trial).
  `mutmut browse` shows the survivors.
- A test edit is not picked up by plain `mutmut run` (R3). After editing tests, re-test the module
  by name.
- The gate script itself always starts from an empty `mutants/`, so running it on the Mac discards
  pulled results. The doc says so.
