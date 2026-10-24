# Contract: `scripts/ci/mutmut-threshold.sh`

One command scores the orchestrator, on the Mac, on PVE and in CI (Constitution V). The PR gate and
the nightly both call it. Rewritten in PR 2; the existing file keeps its name and env variables.

## Invocation

```bash
bash scripts/ci/mutmut-threshold.sh            # from the repo root, or from anywhere (it cd's)
```

## Environment

| Variable | Default | Meaning |
|---|---|---|
| `PYTHON_BIN` | `.venv/bin/python`, else `python3` | interpreter with mutmut installed (unchanged) |
| `MUTMUT_THRESHOLD_FILE` | `python/mutmut-threshold.txt` | floor file (unchanged) |
| `MUTMUT_MIN_SCORE` | unset | overrides the floor file (unchanged) |
| `MUTMUT_SCORE_MARGIN` | `1.0` | subtracted from the floor (unchanged) |
| `MUTMUT_COMMIT` | `git rev-parse HEAD`, else `unknown` | commit recorded in `report.json`; CI sets it because PVE has no `.git` |

No variable switches to an incremental run. The script always deletes `mutants/` first.

## Behaviour

1. Read the floor. Delete `mutants/`.
2. `mutmut run`. In mutmut 3.8 survivors do not make it exit nonzero (checked 2026-10-24: a run
   of one surviving mutant exits 0). A nonzero exit means mutmut itself failed (for example the
   forced-fail sanity check), so exit 2. Then `mutmut export-cicd-stats`; if it fails, exit 2. If
   that leaves no `mutants/mutmut-cicd-stats.json`, or its `total` is 0, exit 2 (the run itself
   failed, for example a test failed during stats collection). If any mutant has no verdict
   (`null` exit code in its `.meta`; the export omits `not_checked`) or
   `check_was_interrupted_by_user` is above 0, exit 2 before writing any report: a partial run
   must not be scored or published.
3. Compute the score (data-model.md) and write `mutants/report.json` and `mutants/survivors.txt`
   (contracts/published-results.md).
4. Print the counts, the score line and the top 10 survivor modules. If `GITHUB_STEP_SUMMARY` is
   set, append the same lines to it as markdown.
5. Exit 0 if `score >= floor - margin`. Otherwise print
   `::error::Mutation score <s>% is below the gate <g>%` and exit 1.

| Exit | Meaning | Results usable |
|---|---|---|
| 0 | passed | yes |
| 1 | below the gate | yes: the nightly publishes them and alerts (a `min_score` run only alerts) |
| 2 | the run failed or is incomplete | no: nothing is published |

## Configuration it relies on

The root `setup.cfg` `[mutmut]` section and the `src` symlink (research R4). The script passes no
mutmut flags of its own, so `mutmut run` on the Mac uses the same configuration.
