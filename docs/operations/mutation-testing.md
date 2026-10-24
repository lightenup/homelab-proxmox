# Mutation Testing Runbook (spec 087)

Audience: anyone investigating a failed mutation gate, raising the score floor, or inspecting
survivors on the Mac. Covers mutmut 3.8 only; see the spec's research.md for the mutmut 2 history.

## What the Gate Checks

`scripts/ci/mutmut_report.py` computes:

```text
score = 100 * killed / (killed + survived)
```

`no tests`, `timeout`, `suspicious`, `skipped`, `segfault` and `caught by type check` mutants are
excluded from the denominator (FR-010): they are not evidence the tests are weak, only that no test
currently reaches that code, or that the run itself was flaky. The gate passes when
`score >= floor - margin` (floor: `python/mutmut-threshold.txt`; margin: `MUTMUT_SCORE_MARGIN`,
default `1.0`).

A run that fails outright (mutmut itself errors, or any mutant is left unchecked or interrupted)
exits 2 before writing a report: a partial run is never scored or published. See
[contracts/gate-script.md](../../specs/087-mutation-gate-runtime/contracts/gate-script.md).

## The PR Gate

`.github/workflows/mutation.yml` runs `scripts/ci/mutmut-threshold.sh` on `ci@pve` for every PR:
deletes `mutants/`, does a fresh full `mutmut run` (no incremental/cached state carried over, per
spec Clarifications), and scores it. `result` is the required status check; it passes when the
score clears the gate, or when the `gate` job's path check decided the PR could not change the
score.

**Path filtering**: `scripts/ci/mutation-gate-paths.txt` lists the paths that can move the score
(one POSIX ERE per line; a `!`-prefixed line is an exclude, applied first). A PR touching only
excluded paths (for example `python/tests/guardrails/` or docs) skips the `mutation` job entirely,
so it does not hold the single shared PVE runner. To extend it:

1. Add an include (or exclude) line.
2. Run `python/tests/workflows/test_mutation_gate_paths.py`: it asserts every `python/tests/`
   subdirectory (except `guardrails` and `workflows`, which are mutation-irrelevant by design) is
   covered, so a new test directory is covered by default rather than silently skipped.
3. When in doubt, prefer a false run over a false skip (research R9): an uncovered path that could
   matter is worse than an unnecessary ~1-minute PVE run.

Target: under 5 minutes end to end (SC-002). The owner/fork guard on the `mutation` job is never to
be loosened (memory: this is a public repo).

## The Nightly

`.github/workflows/nightly-deeper-verification.yml` runs the same fresh full gate on `main`, then
publishes the result set to the NAS so the Mac can inspect survivors without re-running 15+ minutes
of mutation testing locally.

**Published layout**
([contracts/published-results.md](../../specs/087-mutation-gate-runtime/contracts/published-results.md)):

```text
/mnt/nas/homelab_ci/mutmut/
  main -> main-<UTC timestamp>/     # symlink, atomically repointed
  main-<UTC timestamp>/
    report.json                    # written last: its presence means the set is complete
    survivors.txt
    mutmut-stats.json
    mutmut-cicd-stats.json
    src/homelab_proxmox_orchestrator/**/*.meta
  main-<older UTC timestamp>/       # previous set, kept as a fallback
```

Each publish writes a new `main-<UTC>/` directory, then repoints the `main` symlink with
`ln -sfn` + `mv -T` (atomic on the NFS server: a concurrent pull sees the old set or the new one,
never a half-written one). Only the newest two `main-*` directories are kept.

**Parity limitation** (Constitution V, "same behaviour everywhere"): publishing is CI-only, done by
the nightly on `main`. The Mac has no equivalent publish step. Its two options are:

- Read the published set: `task mutmut:pull` (below).
- Produce the same results locally: `scripts/ci/mutmut-threshold.sh` on the Mac. This publishes
  nothing; it is the same gate script CI runs, for parity checks (FR-001) against a CI score on the
  same commit.

## The Mac Loop

```bash
task mutmut:pull
```

Pulls `main`'s published set from `ci@pve` into the local `mutants/` directory (result files only;
it never touches `mutants/` wholesale on failure, so a bad host or an incomplete remote set leaves
the existing `mutants/report.json` untouched). Prints the commit, age and score.

Then, from the repo root:

```bash
task mutmut:run                                                   # re-test local source changes
```

**mutmut 3 keeps cached verdicts when only a test changes** (research R3): editing
`python/tests/version_currency/test_version_currency.py` and running plain `mutmut run` will not
re-test `version_currency.py`'s mutants. Re-test by module name after editing tests:

```bash
task mutmut:run -- "homelab_proxmox_orchestrator.version_currency*"
```

Then browse survivors:

```bash
task mutmut:browse
```

Or, at any point, print the last result without re-running anything:

```bash
task mutmut:status
```

`mutmut:run`, `mutmut:browse` and `mutmut:status` are thin wrappers in `Taskfile.yml`.
`mutmut:run`/`mutmut:browse` auto-detect which local venv actually has mutmut installed (`.venv`,
falling back to `.venv-mutmut` — see the Python version fallback below), so the right binary runs
without having to remember which venv this Mac ended up using. If you prefer the binary directly,
the same auto-detection logic is one `[ -x .venv/bin/mutmut ] || ...` line you can copy from either
task.

**Warning**: `task mutmut:gate` (wraps `scripts/ci/mutmut-threshold.sh`) deletes `mutants/` before
every run (fresh full run, no exceptions) and takes about 2 minutes. Do not run it after
`task mutmut:pull` if you want to keep the pulled set around for `mutmut browse` — use
`task mutmut:run` instead. Use `mutmut:gate` only to reproduce a CI score locally (FR-001 parity)
or to measure a floor-raising change end to end.

**Python version fallback** (research R11): the Mac's `.venv` may be on a Python version mutmut 3.8
has not been validated against (3.15 at the time of writing; mutmut 3.8 was tried on 3.14). If
`uv pip sync` fails on `python/requirements-nightly.lock.txt` for that reason, use a separate
mutation-only virtualenv instead of changing the lock's `--python-version`:

```bash
uv venv --python 3.14 .venv-mutmut
uv pip sync --python .venv-mutmut/bin/python --require-hashes python/requirements-nightly.lock.txt
PYTHON_BIN=.venv-mutmut/bin/python scripts/ci/mutmut-threshold.sh
```

## Raising the Floor

`python/mutmut-threshold.txt` is a measured baseline, ratcheted up by hand via PR as coverage
improves (never lowered without a justification comment). To raise it:

1. Improve the tests that kill today's survivors (`mutmut browse`, or `survivors.txt` for the
   ranked list of modules with the most survivors).
2. Re-run `scripts/ci/mutmut-threshold.sh` (or pull the next nightly) to get the new score.
3. Set the floor to the new score rounded **down** to a whole point, in a PR, with the measured
   score and commit in the file's comment.

## Regression Alerts

A nightly score below the gate line (`rc == 1`) posts one message to the `mutation` ntfy topic
(`https://ntfy.hus-sky.no/mutation`), in addition to failing the job
([contracts/regression-alert.md](../../specs/087-mutation-gate-runtime/contracts/regression-alert.md)).
A run that fails outright (`rc == 2`) does not post: the red nightly and GitHub's failure email
cover it. PR runs never publish or alert.

To test the alert path without waiting for a real regression, use the `min_score` dispatch input:

```bash
gh workflow run nightly-deeper-verification.yml --ref main -f min_score=99
```

This overrides the floor for that one run only (it does not touch `mutmut-threshold.txt`), so the
gate fails and the alert fires. A `min_score` run never publishes, so `main`'s published results
keep the committed floor. The next scheduled run reads the committed floor again and is green.

## Troubleshooting

**"failed to collect stats"** (mutmut run error) almost always means a test fails under mutmut but
passes outside it. The usual cause (research R4) is a subprocess test that re-executes a package
import without carrying `sys.executable` or the mutated `PYTHONPATH`/environment into the child, so
the child runs the original, unmutated source. Check that the subprocess call:

- uses `sys.executable`, not a hardcoded `python3`/`python`;
- sets `PYTHONPATH` to the mutated package's parent
  (`Path(homelab_proxmox_orchestrator.__file__).resolve().parents[1]`), not a hardcoded
  `python/src`;
- inherits the rest of the parent environment (`{**os.environ, "PYTHONPATH": ...}`), not a
  replacement dict — mutmut 3 selects which mutant runs via `MUTANT_UNDER_TEST` in the environment,
  and a replaced environment silently runs the unmutated code instead of failing loudly.

**Leftover processes on `pve` after a cancelled run.** Cancelling a `mutation` or nightly job stops
the runner, not the `mutmut` process it started over SSH on `pve`. The orphan keeps running and can
hold files open on the NAS (an `rm -rf` there then leaves `.nfsXXXX` files, "Device or resource
busy"). Check and stop them:

```bash
# [m] keeps the pattern from matching the ssh shell's own command line.
ssh ci@pve "pgrep -af '[m]utmut'"          # anything listed with no CI job running is an orphan
ssh ci@pve "pkill -TERM -f '[m]utmut run'"
```
