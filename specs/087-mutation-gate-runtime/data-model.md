# Data Model: Mutation Gate Runtime

**Feature**: `087-mutation-gate-runtime` | **Date**: 2026-10-24

There is no database. The entities are files: on the NAS, in the repo, and in a working
`mutants/` directory.

## Published main results

One directory per nightly run, on the NAS. Layout and file formats are in
[contracts/published-results.md](contracts/published-results.md).

| Field | Source | Rule |
|---|---|---|
| per-function verdicts | `mutants/**/*.py.meta` | written by mutmut, copied unchanged |
| test map, hashes, config fingerprint | `mutants/mutmut-stats.json` | written by mutmut, copied unchanged |
| counts | `mutants/mutmut-cicd-stats.json` | from `mutmut export-cicd-stats` |
| score, floor, margin, gate line, pass/fail | `report.json` | from the gate script (FR-010) |
| survivors per module | `report.json`, `survivors.txt` | sorted by survivor count, then by module name |
| commit SHA, UTC time | `report.json` | the commit the run tested, and when it finished |

**Lifecycle**:

```text
nightly run starts ─► full run in /home/ci/homelab-proxmox/mutants (empty at start)
        │
        ├─ run crashes or is cancelled ─► nothing published; current set unchanged
        │
        └─ run completes (any score) ─► write mutmut/main-<UTC>/ ─► swap mutmut/main symlink
                                         ─► keep newest two main-* dirs, delete the rest
```

**Invariants**: there is exactly one current set (`mutmut/main`). It always holds every file listed
above. A reader never sees a partial set.

## Floor

`python/mutmut-threshold.txt`: comment lines that give the formula and how no-tests are counted,
then one number, the floor in percent. The gate script reads the first non-comment line, as today.

| Field | Value | Rule |
|---|---|---|
| floor | 61.0 (proposed, R6) | changed only by hand in a PR; ratchets up |
| margin | 1.0 | `MUTMUT_SCORE_MARGIN` env, default 1.0, as today |
| gate line | floor − margin | the run fails when `score < gate line` |

## Survivor report

Derived from the `.meta` files after a run. There is one per source file:
`mutants/src/homelab_proxmox_orchestrator/<module path>.py.meta`, JSON with the keys
`exit_code_by_key`, `hash_by_function_name`, `type_check_error_by_key` and `durations_by_key`. The
module is the meta file's path below `homelab_proxmox_orchestrator/`, without `.py.meta`, with `/`
replaced by `.`. Each value in `exit_code_by_key` maps to a status through mutmut 3.8's
`status_by_exit_code`:

| exit code | status |
|---|---|
| 1, 3 | killed |
| 0 | survived |
| 5, 33 | no tests |
| 34 | skipped |
| 36, 24, -24, 152, 255 | timeout |
| 37 | caught by type check |
| -11, -9 | segfault |
| `null` | not checked |
| anything else (incl. 35) | suspicious |

| Field | Rule |
|---|---|
| module | dotted module name, without the `homelab_proxmox_orchestrator.` prefix |
| survived | count of survived mutants in that module |
| killed, no_tests | counts in that module, for context |

Order: `survived` descending, then `module` ascending. The alert shows the top 5.

## Score

```text
score = 100 * killed / (killed + survived)        # 100.0 if the denominator is 0
excluded: no_tests, timeout, suspicious, skipped, segfault, caught by type check
```

## Retired

| Item | Removed by |
|---|---|
| `python/mutmut.ini` | PR 2 (config moves to `setup.cfg`) |
| `.mutmut-cache` symlink logic in both workflows | PR 2 |
| `/mnt/nas/homelab_ci/mutmut-cache/` (mutmut 2 caches, 14 files) | after PR 2 merges (FR-011) |
| `run_on_pve`, `run_mutmut` nightly inputs | PR 1 |
