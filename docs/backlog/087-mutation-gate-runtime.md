# Backlog: the mutation gate takes ~40 minutes and blocks the only runner

**Status**: Backlog — raised 2026-10-18, while PR #259 (`086`) waited behind it. Spec only. The
fixes below are candidates; measure them at implementation time.
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

## Requirements

- **FR-001 — Run only when the score can change.** The gate runs when the change touches
  `python/src/homelab_proxmox_orchestrator/**`, a test that imports it, the mutmut config or
  runner, or the lock file. Any other Python change skips. The required `result` check still
  reports, as it does today.
- **FR-002 — A test change elsewhere doesn't invalidate survivors.** Changing a test that
  doesn't exercise the orchestrator must not re-run the survivors. Candidates:
  - narrow `--tests-dir` to the orchestrator's tests;
  - move those tests into their own directory.
- **FR-003 — Cheaper per-mutant runs.** Measure about a dozen mutants with `-n auto` and with
  serial pytest, and keep whichever is faster. Record both numbers.
- **FR-004 — A current `main` baseline.** `mutmut-cache/main` is refreshed at least daily, or on
  every merge to `main`. The nightly mutmut path runs on PVE and fails loudly if it can't write
  the cache.
- **FR-005 — Prune stale branch caches.** Branch cache files with no open branch are removed, or
  removed after an age limit.
- **FR-006 — Same gate semantics.** The score formula, floor, margin and skip-as-pass `result`
  job are unchanged. Parity (Constitution V): `scripts/ci/mutmut-threshold.sh` still runs the
  same way locally.

## Success criteria

- **SC-001**: A PR that only changes non-orchestrator tests, workflows or docs skips the mutation
  job.
- **SC-002**: A PR that changes one orchestrator function finishes the gate in under 10 minutes
  with a warm `main` baseline.
- **SC-003**: The nightly run is green and `mutmut-cache/main` is less than 48 hours old.
- **SC-004**: The mutation score and gate decision for a given commit are the same as before
  the change.

## Out of scope / later

- **Migrating to mutmut 3.** It runs only the tests that cover each mutant, which is the biggest
  possible saving. But the cache format and CLI are different, and `mutmut-threshold.sh` would
  need rewriting. Reconsider if FR-001 to FR-004 aren't enough.
- **Adding a second self-hosted runner.** That removes the contention, not the cost.
