# Quickstart: validating Mutation Gate Runtime

Each scenario maps to a success criterion in [spec.md](spec.md). Formats are in
[contracts/](contracts/).

## Prerequisites

- `ssh ci@pve` works from the Mac, and `/mnt/nas/homelab_ci` is mounted on `pve`.
- A local `.venv` synced from `python/requirements-nightly.lock.txt`.
- `act` for the workflow parse checks (Constitution, "Local Workflow Testing").

## 0. Parse checks (before any PR)

```bash
act -l
act -n -W .github/workflows/nightly-deeper-verification.yml schedule
act -n -W .github/workflows/mutation.yml pull_request
```

Expected: both workflows parse. In the `schedule` dry run no step is skipped because of an input.

## 1. PR 1: the nightly runs on PVE when scheduled (US1, SC-003)

1. Merge PR 1. Trigger it once with the scheduled path's behaviour:
   `gh workflow run nightly-deeper-verification.yml --ref main` (no inputs exist any more).
2. In the run log, `Prepare mutmut shared cache on PVE` and the PVE mutation step run, and no step
   reports `Shared cache mount missing`.
3. On `pve`: `ls -l --time-style=+%F /mnt/nas/homelab_ci/mutmut-cache/main` shows today's date.
4. Wait for the next 03:00 run. It goes green as a `schedule` event.

## 2. PR 2: the gate script on the Mac (FR-001 parity)

```bash
bash scripts/ci/mutmut-threshold.sh; echo "exit=$?"
cat mutants/report.json
```

Expected: exit 0, and a `report.json` per contracts/published-results.md. The score is within a
point of the one the PR's CI run reports for the same commit.

## 3. The PR gate is fast and fresh (US2, SC-002, SC-007)

1. On the migration PR, note the mutation job's duration. Expected: under 5 minutes from job start.
2. On a throwaway branch off it, delete the assertions from one test in
   `python/tests/orchestrator/`, so the score falls below the gate line (check with step 2 on the
   Mac first). Open a draft PR. Expected: `result` fails, and the summary shows the score below the
   gate line.
3. Close the throwaway PR without merging.

## 4. Path guard (US3, SC-001)

Open a draft PR that only touches `python/tests/guardrails/` (a comment line is enough).
Expected: the `mutation` job is skipped, `result` passes. Close it.

## 5. Published results and the Mac loop (US4, SC-003, SC-004)

After the first nightly on mutmut 3:

```bash
ssh ci@pve 'readlink /mnt/nas/homelab_ci/mutmut/main; ls /mnt/nas/homelab_ci/mutmut'
task mutmut:pull
```

Expected: `main` points at the newest `main-<UTC>`, at most two `main-*` directories exist, and the
pull prints the commit (the nightly's `head_sha`) and the age.

Then, after editing one test in a module:

```bash
time .venv/bin/mutmut run "homelab_proxmox_orchestrator.version_currency*"
.venv/bin/mutmut browse
```

Expected: the re-test takes under a minute, and the browser lists survivors.

Failure path: with `ssh` pointed at a bad host (`MUTMUT_PULL_HOST=nope task mutmut:pull`), the task
fails with a clear message and `mutants/` is unchanged.

## 6. Regression alert (US5, SC-005)

The nightly only runs on `main`, so the regression is simulated by raising the floor for one
manual run:

```bash
gh workflow run nightly-deeper-verification.yml --ref main -f min_score=99
```

1. Expected: the job fails, and one message arrives on the `mutation` topic in the format in
   contracts/regression-alert.md, showing floor 99.00. The run does not publish:
   `/mnt/nas/homelab_ci/mutmut/main` still points at the previous set, with the committed floor.
2. A normal nightly afterwards (no `min_score`) sends nothing.

The weakened-test case itself is covered on the PR gate in step 3. It runs the same script.

## 7. Prune (FR-011)

After PR 2 merges and one mutmut 3 nightly has published:

```bash
ssh ci@pve 'ls /mnt/nas/homelab_ci/mutmut-cache'
```

Expected: the directory is gone, or empty, once the prune task has run.

## 8. No cancellations (SC-006)

Two weeks after PR 2 merges:

```bash
gh run list --workflow mutation.yml --limit 100 --json conclusion,createdAt \
  --jq '[.[] | select(.conclusion=="cancelled")] | length'
```

Expected: 0 for runs created after the merge.
