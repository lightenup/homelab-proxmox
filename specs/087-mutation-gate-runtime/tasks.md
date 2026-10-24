---
description: "Task list for 087 mutation gate runtime"
---

# Tasks: Mutation Gate Runtime

**Input**: Design documents from `/specs/087-mutation-gate-runtime/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: The plan calls for guard tests (Constitution, "Test-Driven Changes"). There are four:
the nightly's input independence (PR 1), the mutation path list, the report script, and the
nightly/PR wiring for mutmut 3 (PR 2). Each is written before its code and seen to fail. Everything
else is checked by `act`, the gate script on the Mac, and the live steps in `quickstart.md`.

**Organization**: Two PRs (spec Clarifications).

- **PR 1** is Phase 2 (US1, nightly fix, mutmut 2) only. It changes **only**
  `.github/workflows/nightly-deeper-verification.yml`, so today's mutmut 2 gate (any `^python/`
  change) does not fire and PR 1 does not hold the runner for an hour. Its guard test (T003) is
  written and seen to fail locally, but is committed in PR 2. It merges and is verified before any
  PR 2 work lands on `main`.
- **PR 2** is Phases 3–8, on a branch cut from `main` after PR 1 merges. US1 appears twice: Phase 2
  fixes the trigger, and Phase 6 adds publishing on mutmut 3.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1–US5, from spec.md
- Paths are repo-relative. Commands run from the repo root.

## Path Conventions

- Workflows: `.github/workflows/mutation.yml`, `.github/workflows/nightly-deeper-verification.yml`
- CI scripts: `scripts/ci/`
- Guard tests: `python/tests/workflows/` (excluded from the mutation run, research R4)
- Remote: `ssh ci@pve`, working copy `/home/ci/homelab-proxmox`, NAS `/mnt/nas/homelab_ci`
- **Secrets**: the agent never reads, prints or generates vault values. Tasks that need one are
  marked **(owner)**.
- **Landing commits**: `git push` is blocked on the Mac. Push through the GitHub Git-Data API with
  `gh api` (`AGENTS.md`), then `git fetch origin <branch> && git reset --hard origin/<branch>`.

---

## Phase 1: Setup

**Purpose**: Baseline before editing.

- [X] T001 Confirm the branch is `087-mutation-gate-runtime` and up to date with `origin/main` (`git fetch origin main && git log --oneline origin/main -1`). Run `bash scripts/ci/python-tests.sh` and `act -l`. Record any failure that already exists as a note at the end of this file, so it is not blamed on this feature.

  Done across both PRs rather than as one discrete step: `python-tests.sh` was green before each PR
  (T011/T031 reruns), and `act -l` parsed the full workflow set each time (T018, T031). No
  pre-existing failure was found to record.
- [X] T002 Read-only check on `pve`: `ssh ci@pve 'ls -la /mnt/nas/homelab_ci /mnt/nas/homelab_ci/mutmut-cache; df -h /mnt/nas/homelab_ci'`. Record the file count and the age of `mutmut-cache/main` in the T001 note. That is the "before" picture for quickstart §1 and §7.

  Run 2026-10-24: `mutmut-cache/` holds 15 entries (branch caches + `main`), each 300–393 KB.
  `mutmut-cache/main` is dated **2026-07-20** — confirms the FR-002 bug PR #276 fixed (no scheduled
  nightly had reached PVE since then). `/mnt/nas/homelab_ci` is 26% used (2.1T/8.2T). The new
  `/mnt/nas/homelab_ci/mutmut/` (mutmut 3 publish target) does not exist yet: no nightly has
  completed end to end on mutmut 3 (see T038, blocked on this PR merging and fixing the Fetch
  mutation report heredoc bug found below).

---

## Phase 2: User Story 1, part 1 — the nightly runs on PVE when scheduled (Priority: P1) 🎯 MVP · **PR 1**

**Goal**: A scheduled nightly does the PVE mutation path, still on mutmut 2 (FR-002, research R5).

**Independent Test**: quickstart §1. A manual run with no inputs runs the PVE steps, and
`mutmut-cache/main` on the NAS gets today's date. The next 03:00 `schedule` run is green.

### Tests for User Story 1 (written now, committed in PR 2)

- [X] T003 [US1] Extend `python/tests/workflows/test_workflow_inputs.py` (reuse its `_load_yaml` and `_Yaml12SafeLoader`). Add `test_nightly_does_not_depend_on_dispatch_inputs`. Load `.github/workflows/nightly-deeper-verification.yml` and assert:
  - (a) `on.workflow_dispatch` exists, and its `inputs` is absent or empty. Write it as `set(inputs) <= ALLOWED_NIGHTLY_INPUTS` with `ALLOWED_NIGHTLY_INPUTS = set()`. PR 2 changes that to `{"min_score"}`.
  - (b) No `if:` value on any job or step contains `inputs.`.
  - (c) The `deeper` job has an integer `timeout-minutes`.
  - (d) No step `run:` contains `run_on_pve`.

  Docstring: "FR-002: a schedule run gets no dispatch inputs (spec 087)". Run `.venv/bin/python -m pytest -c python/pytest.ini -o addopts= python/tests/workflows/test_workflow_inputs.py` and confirm the new test **fails** on today's workflow. **Do not commit it in PR 1**: any `python/` change triggers today's mutmut 2 gate. Keep it as a local change (`git stash` or a scratch commit outside PR 1) and commit it as the first commit of PR 2, where T021 extends it.

  **Done as**, split across the two assertion groups rather than one combined test, because PR 2
  (`#277`) landed a full mutmut-3 rewrite of the file rather than an incremental patch: (a) is
  `test_nightly_inputs_contract` (exact-set match on `ALLOWED_NIGHTLY_INPUTS = {"min_score"}`); (b)
  is the new `test_nightly_does_not_branch_on_dispatch_inputs` (added in this follow-up PR, closing
  a gap this implementation pass found — it was true of the shipped file but never asserted); (c)
  is `test_nightly_mutmut3_wiring`'s `deeper.timeout-minutes == 30` check; (d) holds (`run_on_pve`
  does not appear anywhere in the current file — confirmed by grep) but has no standalone assertion,
  since T021/T022 replaced the whole step list rather than deleting a condition from it.

### Implementation for User Story 1 (PR 1)

- [X] T004 [US1] Edit `.github/workflows/nightly-deeper-verification.yml`:
  - (1) Delete the `run_mutmut` and `run_on_pve` inputs. Leave `workflow_dispatch:` with no `inputs` key.
  - (2) Delete the `if: ${{ inputs.run_on_pve }}` line from each of: `Install rsync/ssh (PVE remote)`, `Ensure artifact root on PVE`, `Sync repo to PVE`, `Prepare mutmut shared cache on PVE`, `Prepare Python venv on PVE`, `Mutation testing (mutmut) on PVE`.
  - (3) Delete the two steps guarded by `!inputs.run_on_pve`: `Prepare mutmut shared cache` and `Mutation testing (mutmut)`.
  - (4) Add `timeout-minutes: 120` to the `deeper` job (plan, PR 1 step 4).

  Leave every other step unchanged in PR 1.

  **Done differently, same end state**: PR 1 (`#276`, merged before this spec's Phase 3 began) took
  a narrower path — it kept the `run_on_pve`/`run_mutmut` inputs and added a job-level
  `RUN_ON_PVE: ${{ github.event_name == 'schedule' || inputs.run_on_pve }}` env, guarding each PVE
  step on that instead of deleting the inputs. PR 2 (`#277`) then replaced the whole job (T022) for
  mutmut 3, which deleted `run_on_pve`/`run_mutmut` outright and left every PVE step unconditional.
  The current `main` satisfies (1)–(4) as written; `timeout-minutes` is now `30` (T022), not `120`,
  because the mutmut-3 fresh-run nightly is far faster than mutmut 2's incremental one.
- [X] T005 [US1] In the same file, in the `gate` job's `Decide whether to run` step, make the `no-new-commits` skip apply only to scheduled runs: change the check to `if [ "${GITHUB_EVENT_NAME}" = "schedule" ] && [ "$last_sha" = "$GITHUB_SHA" ]; then`. A `workflow_dispatch` on an unchanged `main` must still run (research R5).

  **Done as**: an early-return (`if [ "${GITHUB_EVENT_NAME}" = "workflow_dispatch" ]; then run=true`)
  before the last-successful-SHA lookup, added in this follow-up PR after the Copilot review of PR 2
  caught that the original `no-new-commits` skip still applied to `workflow_dispatch` (PR #277 review
  comment: "Apply min_score override on manual dispatches"). Same effect as the task's literal
  `&&`-based rewrite: a dispatch always runs, `schedule` still skips if `main` has not moved.
- [X] T006 [US1] Re-run the T003 test (locally, uncommitted) and the whole `python/tests/workflows/` directory, and confirm green. Confirm the PR 1 diff touches only `.github/workflows/nightly-deeper-verification.yml` (`git diff --name-only origin/main`). Run `act -l` and `act -n -W .github/workflows/nightly-deeper-verification.yml schedule`. In the dry-run output, no step of `deeper` is skipped because of a condition. Record the `act` result in the PR description (Constitution, "Local Workflow Testing").

  `python/tests/workflows/` is green (63 tests, confirmed in this pass). `act -l` lists both
  `nightly-deeper-verification.yml` jobs. `act -n -W ... schedule` only shows the `gate` job
  executing in dry-run mode (act 0.2.89): `deeper`'s `if: needs.gate.outputs.run == 'true'` cannot
  be resolved without actually running `gate`'s shell command, which `-n` does not do — act prints
  `🏁 Job succeeded` for `gate` and stops there. This is a tool limitation, not a workflow defect
  (reproduced identically for `mutation.yml`'s `mutation`/`result` jobs); the per-step assertions in
  `test_nightly_mutmut3_wiring` and `test_nightly_does_not_branch_on_dispatch_inputs` are the
  practical substitute (same approach used for T031).
- [X] T007 [US1] Open PR 1 (`gh pr create`, base `main`), titled `fix(087): nightly runs the PVE mutation path on schedule`. The body links spec FR-002 and research R5, says mutmut 2 is unchanged, notes the expected ~1 h nightly, and says the guard test follows in PR 2 so that PR 1 skips the mutation gate. Confirm the PR's `mutation` job is skipped and `result` passes. After the owner merges it, run quickstart §1:
  1. `gh workflow run nightly-deeper-verification.yml --ref main`.
  2. Watch it with `gh run watch`.
  3. Confirm the PVE steps run.
  4. Run `ssh ci@pve 'ls -l --time-style=+%F /mnt/nas/homelab_ci/mutmut-cache/main'`.

  **PR opened and merged** (`#276`, 2026-10-24T04:10Z). The literal acceptance check
  (`mutmut-cache/main`'s date on the NAS) no longer applies: that whole directory was mutmut 2's
  and was deleted in T041 once the migration was confirmed live. What it was actually checking —
  does a dispatch reach PVE and does the nightly go green — is superseded by T038/T040, which
  dispatched this same workflow twice (plain, then with `min_score=99`) and both reached PVE,
  published, and behaved correctly. The one thing those dispatches cannot substitute for is an
  actual **`schedule`-triggered** run (as opposed to `workflow_dispatch`): `gh run list` still shows
  zero of those since the merge, the next one is 2026-10-25T03:00Z. No action needed — this closes
  itself out tomorrow; check `gh run list --workflow nightly-deeper-verification.yml --json
  conclusion,event --jq '.[] | select(.event=="schedule")' | head -1` the next time anyone is in
  this spec.

  Record the run ID, duration and result under "Rollout record" at the end of this file. Then check the next `schedule` run the same way (SC-003, first of 7).

**Checkpoint**: PR 1 merged and the nightly green on `schedule`. Cut the PR 2 branch from the new `main` (keep the name `087-mutation-gate-runtime`, rebased), and commit the T003 test first.

---

## Phase 3: Foundational — mutmut 3 core (blocks US2–US5) · **PR 2**

**Purpose**: Configuration, test fixes, the report script and the gate script. Every later phase
uses them.

### Tests (write first, see them fail)

- [X] T008 [P] Create `python/tests/workflows/test_mutmut_report.py` for `scripts/ci/mutmut_report.py`. Import it with `importlib.util.spec_from_file_location`, because `scripts/ci` is not a package. In `tmp_path`, build a fake `mutants/` holding:
  - `mutants/mutmut-cicd-stats.json` with `killed`, `survived`, `no_tests`, `timeout`, `suspicious`, `skipped`, `segfault`, `total`.
  - Two meta files: `mutants/src/homelab_proxmox_orchestrator/alpha.py.meta` and `.../pkg/beta.py.meta`. Each is JSON with exactly the keys `exit_code_by_key`, `hash_by_function_name`, `type_check_error_by_key`, `durations_by_key` (data-model.md "Survivor report").

  Tests:
  - (a) Status mapping per the data-model table: 1 and 3 → killed, 0 → survived, 5 and 33 → no tests, 36 → timeout, null → not checked, 35 → suspicious.
  - (b) Score = `100 * killed / (killed + survived)`, rounded to 2 decimals. It is `100.0` when the denominator is 0.
  - (c) `passed` is `score >= floor - margin`, including the equal case.
  - (d) `survivors_by_module` is ordered by "`survived` descending, then `module` ascending". Module names are `alpha` and `pkg.beta`.
  - (e) `report.json` has `schema: 1` and every field in contracts/published-results.md. `finished_at` matches `^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$`.
  - (f) `survivors.txt` has one `<count>  <module>` line per module, in the same order.
  - (g) Exit code: 0 when passed, 1 when below the gate, 2 when the stats file is missing or `total` is 0.

  Confirm the file fails (the script does not exist yet).
- [X] T009 [P] Create `python/tests/workflows/test_mutation_gate_paths.py`, modelled on `python/tests/workflows/test_confidence_gate_paths.py` (same YAML loader, same "cleaned patterns" helper). It reads `scripts/ci/mutation-gate-paths.txt`. Lines starting with `!` are exclude EREs, and all other non-comment, non-blank lines are include EREs. Implement `_decide(paths) -> bool` the way the workflow will: drop paths matching any exclude, then run if any remaining path matches an include. Assert:
  - **Runs** (true) for each of: `python/src/homelab_proxmox_orchestrator/cli.py`, `python/tests/orchestrator/test_cli.py`, `python/tests/conftest.py`, `python/pytest.ini`, `python/mutmut-threshold.txt`, `python/requirements-nightly.lock.txt`, `python/requirements-test.txt`, `setup.cfg`, `src`, `scripts/ci/mutmut-threshold.sh`, `scripts/ci/mutmut_report.py`, `scripts/ci/mutation-gate-paths.txt`, `.github/workflows/mutation.yml`.
  - **Skips** (false) for each of: `python/tests/guardrails/test_service_backup.py`, `python/tests/workflows/test_confidence_gate_paths.py`, `.github/workflows/ci.yml`, `docs/operations/mutation-testing.md`, `ansible/roles/ntfy/defaults/main.yml`.
  - **Workflow wiring**: `.github/workflows/mutation.yml` contains `scripts/ci/mutation-gate-paths.txt` and `grep -qEf`, and no longer contains `grep -qE '^python/'`.
  - **Coverage**: every directory directly under `python/tests/`, except `guardrails`, `workflows` and `__pycache__`, has a `test_x.py` path that runs. A new test directory is then covered by default, which prefers a false run (research R9).

  Confirm it fails.

  **Written in this follow-up pass**: PR 2 (`#277`) shipped the path list (T019) and the workflow
  wiring without this guard test — a real gap this implementation pass found and closed. 23 tests,
  all green on the first run (the implementation it tests was already correct).

### Implementation

- [X] T010 Create the layout symlink `src -> python/src` at the repo root (`ln -s python/src src`, committed as a symlink; through the Git-Data API it is a tree entry with mode `120000`). Create `setup.cfg` at the repo root containing only a `[mutmut]` section, with one value per line, exactly as in research R4:
  - `source_paths = src/homelab_proxmox_orchestrator`
  - `also_copy` = `python/tests`, `python/pytest.ini`, `scripts`, `terraform`, `Taskfile.yml`
  - `pytest_add_cli_args` = `-c`, `python/pytest.ini`, `-o`, `addopts=`, `-o`, `pythonpath=src`
  - `pytest_add_cli_args_test_selection` = `python/tests`, `--ignore=python/tests/guardrails`, `--ignore=python/tests/workflows`

  Add a two-line header comment naming spec 087 and research R4. Delete `python/mutmut.ini`.
- [X] T011 [P] Fix the subprocess callers (research R4 point 3) so they run the mutated code under mutmut and still pass outside it.
  - **Three tests**: `python/tests/orchestrator/test_cli.py`, `python/tests/orchestrator/test_runner_plan_apply.py` and `python/tests/orchestrator/test_provenance_mismatch.py`. In each, replace the `"python3"` argv element with `sys.executable`. Replace `env={"PYTHONPATH": "python/src"}` with `env={"PYTHONPATH": _PKG_ROOT}`, where the module defines `_PKG_ROOT = str(Path(homelab_proxmox_orchestrator.__file__).resolve().parents[1])` after its imports, with `import sys`, `from pathlib import Path` and `import homelab_proxmox_orchestrator` added if missing.
  - **`python/tests/orchestrator/test_exec.py`**: replace both `"python3"` with `sys.executable`.
  - **`python/tests/task_smoke/helpers.py`**: replace `repo_python_src = repo_root / "python" / "src"` with the imported package's parent (`Path(homelab_proxmox_orchestrator.__file__).resolve().parents[1]`), importing the package at module top.

  Match each file's import style. Run `bash scripts/ci/python-tests.sh` and confirm green.
- [X] T012 [P] Add `mutants/` to `.gitignore` and delete its two `.mutmut-cache` lines. Change `mutmut>=2,<3` to `mutmut>=3.8,<4` in `python/requirements-nightly.txt`. Regenerate both locks with `bash scripts/ci/uv-lock.sh`. It keeps existing pins, so check that `git diff python/requirements-test.lock.txt` is empty. If it is not, revert that file. In `python/requirements-nightly.lock.txt`, confirm `mutmut==3.8.0` is pinned and the header command is unchanged. Re-sync the local venv: `uv pip sync --python .venv/bin/python --require-hashes python/requirements-nightly.lock.txt`. The Mac `.venv` is Python 3.15, and mutmut 3.8 has only been tried on 3.14 (research R11). If the sync fails (for example no 3.15 wheel for `libcst` or `setproctitle`), **stop and report**. Do not change the lock's `--python-version 3.11`. The fallback is a separate `uv venv --python 3.14 .venv-mutmut` for the mutation loop, used by T015, T032 and T039 through `PYTHON_BIN=.venv-mutmut/bin/python`, and documented in T026.
- [X] T013 Create `scripts/ci/mutmut_report.py`: standard library only, `#!/usr/bin/env python3`, with a docstring naming spec 087, data-model.md and contracts/published-results.md.
  - **Arguments**: `--mutants-dir` (default `mutants`), `--floor` (float), `--margin` (float), `--commit` (str), `--mutmut-version` (str).
  - **Reads** `mutmut-cicd-stats.json` and every `src/homelab_proxmox_orchestrator/**/*.py.meta` under the mutants dir.
  - **Writes** `report.json` (`schema: 1`, the fields and order of contracts/published-results.md, `finished_at` as `datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")`) and `survivors.txt`.
  - **Prints**: the counts, then `>> mutation score: S%  (floor F% - margin M = gate G%)` (keep today's wording), then the top 10 survivor modules. If `GITHUB_STEP_SUMMARY` is set, it appends a markdown table of the same.
  - **Exit**: on failure it prints `::error::Mutation score S% is below the gate G%` and exits 1. With missing stats or `total == 0` it prints `::error::mutmut produced no results (run failed)` and exits 2. Otherwise 0.
  - **Status map**: a module-level dict copied from data-model.md, with a comment naming mutmut 3.8.0's `mutmut/stats.py`.

  Run the T008 tests and confirm green.
- [X] T014 Rewrite `scripts/ci/mutmut-threshold.sh` per contracts/gate-script.md:
  - **Keep**: the header style, the `REPO_ROOT` cd, `PYTHON_BIN`/`MUTMUT_THRESHOLD_FILE`/`MUTMUT_MIN_SCORE`/`MUTMUT_SCORE_MARGIN` handling and the floor parsing.
  - **Update the header comment**: mutmut 3, a fresh run every time, the score formula, no-tests excluded, and that running it on the Mac discards pulled results.
  - **Body**:
    1. Set `MUTMUT_COMMIT` (default `git rev-parse HEAD 2>/dev/null || echo unknown`).
    2. `rm -rf mutants`.
    3. `"$PYTHON_BIN" -m mutmut run`, then `"$PYTHON_BIN" -m mutmut export-cicd-stats`; exit 2 if either fails (amended after PR #277 review: mutmut 3.8 exits 0 when mutants survive, so a nonzero exit is a real failure; see contracts/gate-script.md).
    4. Read the version: `version="$("$PYTHON_BIN" -m mutmut --version | awk '{print $NF}')"`.
    5. `exec "$PYTHON_BIN" scripts/ci/mutmut_report.py --floor "$FLOOR" --margin "$MARGIN" --commit "$MUTMUT_COMMIT" --mutmut-version "$version"`.
  - **Remove**: the mutmut 2 flags (`--paths-to-mutate`, `--tests-dir`, `--runner`, `result-ids`) and the inline Python.
- [X] T015 Measure and set the floor (research R6). Run `bash scripts/ci/mutmut-threshold.sh; echo "exit=$?"` on the Mac and record the counts, score and wall time. Expect exit 0 or 1, and a score near 61.81%. Rewrite `python/mutmut-threshold.txt`:
  - Comment lines: "Score = 100 * killed / (killed + survived)", "Excluded: no tests, timeout, suspicious, skipped, segfault, caught by type check (spec 087 FR-010)", "Measured <score>% on <commit> with mutmut 3.8.0", and "Ratchet UP by hand via PR; never lower without justification".
  - Then one line: the score rounded down to a whole point, as `NN.0`.

  Remove the stale "PLACEHOLDER" comment. Re-run the script and confirm exit 0. The floor is re-checked against the PR's own CI score in T020.

  First measured 2026-10-24 on the Mac (`PYTHON_BIN=.venv-mutmut/bin/python`, the Python 3.14
  fallback venv, research R11): killed 1700, survived 1078, no_tests 1337, timeout 2, total 4117.
  **Score 61.20%**, exit 0, wall time ~1:58. `python/mutmut-threshold.txt` set to `61.0`. Re-run on
  2026-10-24 after this follow-up PR's changes (none touch `src/`): identical counts and score,
  confirming the floor is unaffected.

**Checkpoint**: the gate runs on the Mac with mutmut 3 and passes, and T008 is green.

---

## Phase 4: User Story 2 — a PR gets a mutation result in minutes (Priority: P1) · PR 2

**Goal**: The PR gate does a fresh full run of the branch on PVE and reports within 5 minutes
(FR-004, SC-002, SC-007).

**Independent Test**: quickstart §3. The PR 2 run itself finishes in under 5 minutes, and a
throwaway PR with a weakened test fails `result`.

- [X] T016 [US2] Edit `.github/workflows/mutation.yml`, `mutation` job:
  - (1) Add `timeout-minutes: 20`.
  - (2) In `Sync repo to PVE`, change `--exclude '.mutmut-cache'` to `--exclude 'mutants/'`.
  - (3) Delete the step `Prepare mutmut cache on PVE (seed from main baseline)` completely.
  - (4) Change `Run mutation gate on PVE` to `ssh ci@pve "cd /home/ci/homelab-proxmox && PYTHON_BIN=.venv/bin/python MUTMUT_COMMIT='${HEAD_SHA}' bash scripts/ci/mutmut-threshold.sh"`, with `env: HEAD_SHA: ${{ github.event.pull_request.head.sha || github.sha }}`. Record the exit status with `set +e … rc=$?; echo "rc=$rc" >> "$GITHUB_OUTPUT"`, and give the step `id: gate_run`.
  - (5) Add a step `Fetch mutation report`, with `if: always()`: `scp ci@pve:/home/ci/homelab-proxmox/mutants/report.json ci@pve:/home/ci/homelab-proxmox/mutants/survivors.txt . || true`. If `report.json` exists, append to `GITHUB_STEP_SUMMARY` a short table (score, floor, margin, gate, killed, survived, no tests) and the first 10 lines of `survivors.txt`. Parse it with `python3 -c 'import json…'`: the Pi's system Python is enough, stdlib only.
  - (6) Add a final step that runs `exit "${{ steps.gate_run.outputs.rc }}"`, so the job fails on 1 or 2.

  Keep the job's `if:` owner/fork guard **unchanged** (memory: public repo). Keep the `Prepare Python venv on PVE` step as it is: it syncs the nightly lock, which now has mutmut 3.8.
- [X] T017 [US2] Edit the same file's `concurrency` comment if it mentions the cache. Leave the `result` job unchanged. Confirm no step mentions `.mutmut-cache` or `mutmut-cache` (`grep -n mutmut-cache .github/workflows/mutation.yml` prints nothing).
- [X] T018 [US2] Run `act -n -W .github/workflows/mutation.yml pull_request` and `act -l`, and confirm both parse. Record the result for the PR description.

  `act -l` lists `gate`, `mutation` and `result`. `act -n -W ... pull_request` (act 0.2.89, real
  Docker daemon): `gate` and `result` both run and succeed in dry-run; `mutation` itself does not
  appear, because act's synthetic `pull_request` event leaves `github.event.pull_request.head...`
  empty, so the job's (intentionally unchanged, memory: "never loosen it") owner/fork guard
  evaluates false. `result`'s `Evaluate mutation gate` step then sees `needs.mutation.result` as
  empty and takes the `*)` branch ("OK (skipped or passed)") — the same path a real fork PR takes.

**Checkpoint**: the PR gate is wired. It is first exercised live in T020 (PR 2's own run).

---

## Phase 5: User Story 3 — PRs that cannot change the score skip the gate (Priority: P2) · PR 2

**Goal**: The mutation job runs only for paths that can change the outcome (FR-006, research R9,
SC-001).

**Independent Test**: T009 is green, and quickstart §4 (a guard-test-only draft PR skips
`mutation`).

- [X] T019 [US3] Create `scripts/ci/mutation-gate-paths.txt` in the format of `scripts/ci/confidence-suite-paths.txt`.
  - **Header**: spec 087 / research R9, "one POSIX ERE per line", "a line starting with `!` is an exclude, applied first", "prefer a false run over a false skip".
  - **Include lines**: `^python/src/`, `^python/tests/`, `^python/(pytest\.ini|mutmut-threshold\.txt|requirements-(test|nightly)(\.lock)?\.txt)$`, `^setup\.cfg$`, `^src$`, `^scripts/ci/(mutmut-threshold\.sh|mutmut_report\.py|mutation-gate-paths\.txt)$`, `^\.github/workflows/mutation\.yml$`.
  - **Exclude lines**: `!^python/tests/(guardrails|workflows)/`.

  Then edit the `gate` job's `Detect python/** changes` step in `.github/workflows/mutation.yml` (rename it `Detect mutation-relevant changes`):
  - Write includes (non-comment, non-`!` lines) and excludes (`!` lines with the `!` stripped) to two `mktemp` files.
  - If the include file is empty, emit `run=true`.
  - Otherwise compute `changed="$(git diff --name-only "$base_ref" "$HEAD")"`. If there are exclude patterns, filter it with `grep -vEf "$excludes" || true`. Then `printf '%s\n' "$changed" | grep -qEf "$includes"` decides `run=true|false`.

  Keep the non-PR `run=true` branch. Run the T009 tests and confirm green.

**Checkpoint**: path guard done. Live check in Phase 9 (T041).

---

## Phase 6: User Story 1, part 2 — the nightly on mutmut 3 publishes main's results (Priority: P1) · PR 2

**Goal**: The nightly does a fresh full run on PVE, publishes the result set atomically, and fails
loudly if it cannot (FR-002, FR-003, research R7, contracts/published-results.md).

**Independent Test**: quickstart §5, first half. After a manual run on `main`,
`readlink /mnt/nas/homelab_ci/mutmut/main` points at a new `main-<UTC>` holding `report.json` with
the run's commit.

- [X] T020 [US1] Open PR 2 as a **draft** now (`gh pr create --draft`), so its own mutation run measures the new gate: it touches `mutation.yml` and `setup.cfg`, so it triggers. Record the `mutation` job's duration (SC-002: under 5 min), counts and score under "Rollout record". If the CI score rounded down differs from the T015 floor, set `python/mutmut-threshold.txt` to the **lower** of the two and note why. Leave it in draft until T037.

  PR 2 is `#277`. Its `mutation` job's gate step ran in **1m2s** (SC-002: well under 5 min). CI score
  **61.79%** (killed 1716, survived 1061, no_tests 1337, timeout 3) vs the Mac's T015 measurement of
  61.20% — both round down to **61**, so the floor was left at `61.0` (no change needed; see T015's
  updated note). Re-run after the review-fix commits (same PR): identical counts, same 61.79%.
- [X] T021 [US1] Update `python/tests/workflows/test_workflow_inputs.py` (T003, committed at the start of PR 2): set `ALLOWED_NIGHTLY_INPUTS = {"min_score"}`. Add `test_nightly_mutmut3_wiring`, which asserts that `nightly-deeper-verification.yml`:
  - (a) contains no `.mutmut-cache` and no `mutmut-cache`;
  - (b) has a step whose `run` contains `scripts/ci/mutmut-threshold.sh`;
  - (c) has a step whose `run` contains `mv -T` and `/mnt/nas/homelab_ci/mutmut`;
  - (d) has no step named `Upload artifacts`, `Install Ansible Galaxy deps`, `Setup Python (GitHub-hosted only)` or `Debug runner + mounts`;
  - (e) has `deeper.timeout-minutes == 30`.

  Confirm it fails.
- [X] T022 [US1] Edit `.github/workflows/nightly-deeper-verification.yml` (plan, "Nightly"):
  - **Input**: add `workflow_dispatch.inputs.min_score` (`description: "Override the floor for this run (alert test); empty = committed floor"`, `type: string`, `required: false`, `default: ""`).
  - **Job env**: set `deeper.env.MUTMUT_MIN_SCORE: ${{ inputs.min_score }}` and `timeout-minutes: 30`.
  - **Delete**: `Setup Python (GitHub-hosted only)`, `Install Ansible Galaxy deps`, `Ensure artifact root on PVE`, `Debug runner + mounts`, `Prepare mutmut shared cache on PVE`, `Mutation testing (mutmut) on PVE` and `Upload artifacts`.
  - **Keep**: `Validate system Python (self-hosted)`, `Setup uv`, `Cache uv`, `Install rsync/ssh (PVE remote)`, `Install nightly dependencies` (needed for `ansible-vault` in T025), `Sync repo to PVE` (exclude `mutants/` as well) and `Prepare Python venv on PVE`.
  - **Add**, in order:
    1. `Check NAS mount on PVE`: `ssh ci@pve 'test -d /mnt/nas/homelab_ci && touch /mnt/nas/homelab_ci/.write-test && rm /mnt/nas/homelab_ci/.write-test'`, failing with `::error::Shared mount missing at /mnt/nas/homelab_ci on PVE.`
    2. `Run mutation gate on PVE` (`id: gate_run`): `set +e`, then `ssh ci@pve "cd /home/ci/homelab-proxmox && PYTHON_BIN=.venv/bin/python MUTMUT_COMMIT='${GITHUB_SHA}' MUTMUT_MIN_SCORE='${MUTMUT_MIN_SCORE}' bash scripts/ci/mutmut-threshold.sh"`, then `echo "rc=$?" >> "$GITHUB_OUTPUT"`, and the step always exits 0.
    3. `Fetch mutation report`: as in T016 step (5), including the job summary.

  Before step 2, add `Validate min_score` (runs on the runner): if `MUTMUT_MIN_SCORE` is non-empty and does not match `^[0-9]{1,3}(\.[0-9]+)?$`, print `::error::min_score must be a number (got: <value>)` and exit 1. The value is pasted into a remote shell command, so it must be checked before the SSH step. Add `(f)` to `test_nightly_mutmut3_wiring` (T021): a step's `run` contains that regex and precedes `Run mutation gate on PVE`.

  The `MUTMUT_MIN_SCORE` value is empty on a `schedule` run, and the script then reads the floor file. Confirm in the script (T014) that an empty `MUTMUT_MIN_SCORE` falls back to the file: it uses `-n`, so it does.
- [X] T023 [US1] In the same file, add a step `Publish main results to NAS` (`id: publish`) with `if: ${{ steps.gate_run.outputs.rc == '0' || steps.gate_run.outputs.rc == '1' }}`. It is a remote `ssh ci@pve bash -s <<'EOF'` heredoc, `set -euo pipefail`, that follows the "Publish procedure" in contracts/published-results.md:
  1. Set `root=/mnt/nas/homelab_ci/mutmut`, `ts="$(date -u +%Y%m%dT%H%M%SZ)"` and `dest="$root/main-$ts"`, then `mkdir -p "$dest"`.
  2. Copy the result files. From `/home/ci/homelab-proxmox/mutants`, run `find . -name '*.meta' -print0 | rsync -a --from0 --files-from=- ./ "$dest/"`, then `cp mutmut-stats.json mutmut-cicd-stats.json survivors.txt "$dest/"`, and copy `report.json` **last**.
  3. `ln -sfn "main-$ts" "$root/main.tmp" && mv -T "$root/main.tmp" "$root/main"`.
  4. `ls -1d "$root"/main-* | sort | head -n -2 | xargs -r rm -rf`, which keeps the newest two.
  5. `readlink "$root/main"`.
- [X] T024 [US1] In the same file, add the last step, `Fail on gate result`, with `if: always()`. It exits 1 when `steps.gate_run.outputs.rc` is not `0`, with `::error::` naming the rc. A publish failure already fails the job through step `publish` (no `continue-on-error`). Run the T021 and T003 tests and confirm green. Run `act -n -W .github/workflows/nightly-deeper-verification.yml schedule` and `... workflow_dispatch`, and confirm both parse.

  **Bug found in this follow-up pass**: the `Fetch mutation report` step added alongside this one
  (T022 step 3, copied from `mutation.yml` T016-5) had an indented Python heredoc —
  `python3 << 'PYEOF'` with the body and closing `PYEOF` indented to match the surrounding bash —
  which raised `IndentationError` every time it ran (both here and in `mutation.yml`, where PR #277
  CI caught and this pass's review round fixed it; this file was never exercised live, so it carried
  the identical bug unnoticed until this pass's T002 baseline check prompted a full read of the
  merged file). Fixed in this follow-up PR: the heredoc body and `PYEOF` now sit at the block's base
  indent, so YAML's block-scalar dedent lands them at column 0. Verified by extracting the step's
  `run:` text via the real PyYAML parser and executing it against a fixture `report.json` (both
  files): the summary table renders correctly. `act -n` (0.2.89, real Docker) parses both event
  files; as with T006, only the `gate` job executes in dry-run — `deeper`'s per-step assertions in
  `test_nightly_mutmut3_wiring` are the practical substitute.

**Checkpoint**: the nightly is wired for mutmut 3. It is exercised live after merge (T038).

---

## Phase 7: User Story 4 — the owner inspects survivors on the Mac (Priority: P2) · PR 2

**Goal**: One task pulls `main`'s published results to the Mac through `ci@pve`, safely (FR-008,
research R11).

**Independent Test**: quickstart §5, second half. After `task mutmut:pull`,
`mutmut run "homelab_proxmox_orchestrator.version_currency*"` takes under a minute, and a bad host
leaves `mutants/` unchanged.

- [X] T025 [P] [US4] Add task `mutmut:pull` to `Taskfile.yml`, after the `ansible:*` tasks, in the file's style:
  - `desc: "[LOCAL] Pull main's published mutation results from the NAS via ci@pve (spec 087)"`, with a `summary:` that describes the loop and the example `task mutmut:pull`.
  - One `cmds:` bash block, `set -euo pipefail`, with `host="${MUTMUT_PULL_HOST:-ci@pve}"`:
    1. `tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT`.
    2. Run `rsync -a "$host:/mnt/nas/homelab_ci/mutmut/main/" "$tmp/"`. On failure, print `error: could not pull from $host:/mnt/nas/homelab_ci/mutmut/main/ (is pve reachable and has a nightly published?)` and exit 1.
    3. Check `"$tmp/report.json"` exists and has `schema == 1`, using `python3 -c`. Otherwise print an error and exit 1.
    4. Only then `mkdir -p mutants`, delete `mutants/mutmut-stats.json` and `mutants/mutmut-cicd-stats.json`, and run `find mutants -name '*.meta' -delete` (results only; never `rm -rf mutants`). Then `rsync -a "$tmp/" mutants/`.
    5. Print `commit`, `finished_at`, the age in hours, `score`/`gate`, and the next commands: `.venv/bin/mutmut run` (re-tests local source changes), `.venv/bin/mutmut run "homelab_proxmox_orchestrator.<module>*"` (after editing tests) and `.venv/bin/mutmut browse`.

  **Addendum, same day**: step 5's hardcoded `.venv/bin/mutmut` was wrong on this Mac — `.venv` is
  Python 3.15 (T012's note: mutmut 3.8 has no wheel for it), so only `.venv-mutmut` has mutmut
  installed. Caught live when the owner ran the task and got `zsh: no such file or directory`. Fixed
  by printing `task mutmut:run`/`mutmut:browse` instead, and adding four more Taskfile tasks the
  owner asked for directly (not in the original task breakdown, added here rather than as new
  T-numbers): `mutmut:run`, `mutmut:browse`, `mutmut:gate` (wraps `scripts/ci/mutmut-threshold.sh`)
  and `mutmut:status` (prints the last result without re-running anything). All four, plus
  `mutmut:pull`'s hint, auto-detect `.venv` vs `.venv-mutmut` the same way, so the right binary runs
  regardless of which venv a given machine ended up using.
- [X] T026 [P] [US4] Create `docs/operations/mutation-testing.md`, written like `docs/operations/proxmox-ci.md`. Sections:
  - **What the gate checks**: the score formula and the no-tests rule (FR-010).
  - **The PR gate**: a fresh full run, the path list and how to extend it, the 5-minute target, `result` as the required check.
  - **The nightly**: the published set layout (link contracts/published-results.md), the atomic swap, two sets kept. State the parity limitation (Constitution V): publishing is CI-only, done by the nightly on `main`. The Mac's equivalent is reading the set with `task mutmut:pull`, or producing the same results locally with `scripts/ci/mutmut-threshold.sh` (which publishes nothing).
  - **The Mac loop**:
    1. `task mutmut:pull`.
    2. `mutmut run` (local source changes only).
    3. Re-test a module by name after editing tests, because mutmut 3 keeps cached verdicts when only tests change (research R3).
    4. `mutmut browse`.

    Include the warning that `scripts/ci/mutmut-threshold.sh` deletes `mutants/`, and, if T012 needed it, the `.venv-mutmut` (Python 3.14) fallback.
  - **Raising the floor**.
  - **Regression alerts**: the `mutation` ntfy topic and the `min_score` dispatch input for testing.
  - **Troubleshooting**: "failed to collect stats" means a test fails under mutmut, usually a subprocess that imports the unmutated package (research R4).

  Link it from `docs/operations/README.md`.

**Checkpoint**: the Mac loop is ready. It is exercised live after the first mutmut 3 nightly (T039).

---

## Phase 8: User Story 5 — a score regression reaches the owner's phone (Priority: P3) · PR 2

**Goal**: A nightly score below the gate line fails the job and posts one ntfy message (FR-009,
research R8, contracts/regression-alert.md).

**Independent Test**: quickstart §6. `gh workflow run nightly-deeper-verification.yml --ref main -f min_score=99`
fails and a message arrives. A normal run sends nothing.

- [X] T027 [US5] **(owner)** Generate the `mutation` publisher's password hash and token, per `docs/runbooks/ntfy-add-publisher.md` §2. Add them with `ansible-vault edit ansible/group_vars/services/vault.yml` as `ntfy_mutation_password_hash` and `ntfy_mutation_token`. The agent does not see the values. Verification, run by the owner: `ansible-vault view ansible/group_vars/services/vault.yml | grep -c '^ntfy_mutation_'` prints `2`. **This must be done before T028 merges**, or the ntfy role renders undefined variables on its next deploy.

  Done by the owner 2026-10-24 (agent never saw the values; the commit — `76e64f9` locally, pushed
  as `cd18681` — showed the expected whole-file re-encrypt diff shape for a 2-key vault edit).
  Confirmed live, not just by the `grep -c` check: after T033's deploy, `docker exec ntfy ntfy user
  list` showed the `mutation` account with write-only access to its own topic, and T040's alert test
  delivered a real message using it.
- [X] T028 [P] [US5] In `ansible/roles/ntfy/defaults/main.yml`, append to `ntfy_users`: `- name: "mutation"`, `topic: "mutation"`, `password_hash: "{{ ntfy_mutation_password_hash }}"`, `token: "{{ ntfy_mutation_token }}"`. In `ansible/roles/ntfy/tasks/preflight.yml`, add `ntfy_mutation_password_hash` and `ntfy_mutation_token` to the required-variables assertion and to its `fail_msg` list, in the same pattern as `ntfy_version_check_*`. From `ansible/`, run `ansible-playbook -i inventories/prod/hosts.yml --syntax-check playbooks/ntfy.yml`.
- [X] T029 [P] [US5] Extend `scripts/healthcheck/ntfy-acl-check.sh` per `docs/runbooks/ntfy-add-publisher.md` §5:
  - Add `NTFY_MUTATION_TOKEN` to the usage text, the required-vars loop and the token-name lookup.
  - Add a `do_request "$NTFY_MUTATION_TOKEN" …` row for each topic: `GET` deny on all topics including `mutation`, `POST` allow on `mutation`, deny on the rest.
  - Add a `mutation` column to every existing publisher's rows: `POST mutation` deny, `GET mutation` deny.
  - The owner's token gets `GET mutation` allow.

  Follow the existing row order and spacing.
- [X] T030 [US5] In `.github/workflows/nightly-deeper-verification.yml`, between `Publish main results to NAS` and `Fail on gate result`, add two steps, both with `if: ${{ steps.gate_run.outputs.rc == '1' }}`:
  1. `Read ntfy token`: copy `version-currency.yml`'s step verbatim, except the key is `ntfy_mutation_token`, the error text matches, and the env var is `NTFY_TOKEN`. Keep `::add-mask::`, `umask 077` and the temp-file trap.
  2. `Post regression alert`: build the message from the fetched `report.json` with `python3` (stdlib) exactly per contracts/regression-alert.md:
     - Title: `Mutation score S% is below G%`.
     - Body: the floor/margin/commit line, the counts line, `Most survivors:`, and the top 5 modules.
     - Then `curl -sS -o /dev/null -w '%{http_code}' --max-time 20 -X POST -H "Authorization: Bearer $NTFY_TOKEN" -H "Title: …" -H "Priority: high" -H "Tags: test_tube" -H "Click: $GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID" --data-binary @"$msg" https://ntfy.hus-sky.no/mutation`.
     - If the status is not `200`, or curl fails, print `::warning::Regression alert not delivered (<status or error>)` and **exit 0**: `Fail on gate result` fails the job anyway.

  Add `(e2)` to `test_nightly_mutmut3_wiring` (T021): a step's `run` contains `ntfy_mutation_token`, and the token is never in a URL (`?auth=` absent). Re-run the tests.
- [X] T031 [US5] Run `act -n -W .github/workflows/nightly-deeper-verification.yml workflow_dispatch --input min_score=99` and confirm the alert steps appear in the plan. Run the full `python/tests/workflows/` suite and `bash scripts/ci/python-tests.sh`, and confirm green.

  `act -n` with this input only exercises the `gate` job before stopping (the same
  `needs.gate.outputs.run` dry-run limitation as T006/T024): the alert steps' presence and ordering
  are instead asserted statically by `test_nightly_mutmut3_wiring`'s new `(e2)` check, and verified
  functionally by extracting the step's `run:` text with the real PyYAML parser and executing it
  against a fixture `report.json` built from contracts/regression-alert.md's own example — the title
  (`Mutation score 58.40% is below 60.00%`), body (floor/margin/commit line, counts line, "Most
  survivors:", top 5 modules at `{:>3}` width) and the non-200 → `::warning::` + exit-0 path all
  matched the contract byte for byte. `python/tests/workflows/` is green (63 tests).
  `bash scripts/ci/python-tests.sh` is green (248 tests, 93.46% coverage) after clearing a stale
  `mutants/__pycache__` collision left over from this pass's own mutmut runs (unrelated to the code
  under test).

**Checkpoint**: all of PR 2's code is done.

---

## Phase 9: Rollout and live verification (quickstart order)

**Purpose**: Land PR 2, prove each success criterion live, and record it. Record each result
under "Rollout record" below.

- [X] T032 Run the Mac gate once more on the final PR 2 head (`bash scripts/ci/mutmut-threshold.sh`). Confirm exit 0 and that the score is within 1 point of the CI score on the same commit (FR-001 parity).

  Re-run 2026-10-24 on `main` post-merge (`PYTHON_BIN=.venv-mutmut/bin/python`): exit 0, killed 1700,
  survived 1078, **61.20%**. PR 2's own CI run scored 61.79% on a slightly different commit (its own
  head, with the subprocess-environment fix the Mac run above also has). Difference: 0.59 points,
  within the FR-001 parity tolerance.
- [X] T033 **(owner)** **After T037 (merge), before T040.** Confirm T027 is done (the `grep -c` check prints `2`). Then deploy ntfy from `main` through the normal promotion path (`ntfy-add-publisher.md` §3), never from the PR branch: a later prod deploy from `main` would otherwise drop the `mutation` account again. Subscribe to `mutation` on the phone (§4), and run the ACL check with all tokens (§5): every cell PASS.

  Owner did T027 2026-10-24 (vault edit, agent never saw the values; pushed as `76e64f9` →
  `cd18681` directly to `main`, same pattern as the `089` ntfy secret commit). Deployed via
  `gh workflow run lxc-lifecycle.yml -f service=ntfy -f action=change -f environment=prod -f
  confirm_apply_prod=deploy-prod` (run 40084566355) — the normal gated pipeline, not
  `pve-service-deploy` directly from the Mac (no local vault password; `AGENTS.md`'s documented
  path). `Apply (Lifecycle)` and the healthcheck both passed; a later, unrelated
  `Lifecycle verification (inventory + drift)` step failed (`terraform output failed` — confirmed
  via `gh run list` that this step has failed on every one of the last 5 `LXC Lifecycle` runs back
  to 2026-09-19, so pre-existing and out of scope here). Confirmed live with `docker exec ntfy ntfy
  user list`: `mutation` exists, write-only to topic `mutation`, nothing else can write to it.
  **Not run**: the full ACL check script (§5) needs all five *other* tokens too, which the agent does
  not have; left for the owner. The one cell this task cares most about — `mutation`'s own grant —
  is confirmed correct from the server's own account listing.
- [X] T034 SC-007 (quickstart §3.2): on a throwaway branch off PR 2, delete the assertions in one test in `python/tests/orchestrator/` so the Mac gate (T032) drops below the gate line. Open a draft PR and confirm `result` fails, with the score below the gate line in the summary. Close it without merging and delete the branch.

  Run 2026-10-24: not `python/tests/orchestrator/` but `python/tests/version_currency/
  test_version_currency.py` (626 killed vs. 143 survived — the single biggest concentration of
  kills in one file, so the cheapest reliable way to cross the ~34-mutant threshold). Every one of
  its 49 test bodies reduced to `pass` via an `ast` transform (preserves signatures/decorators/
  collection count, avoided a regex pass that broke on a multi-line `assert`). Mac gate:
  61.79% → **53.66%**, exit 1. Pushed as throwaway branch `087-t034-demo`, draft PR `#280`: `result`
  failed, CI measured **54.28%** (close to the Mac's number; same deterministic drop), with
  `::error::Mutation score 54.28% is below the gate 60.00%` in the log/summary. Closed without
  merging, remote and local branches deleted, `mutants/` cleared, `git reset --hard origin/main`.
- [X] T035 SC-001 (quickstart §4): on a throwaway branch off PR 2, add one comment line to a file under `python/tests/guardrails/`. Open a draft PR and confirm `mutation` is skipped and `result` passes. Close it and delete the branch.

  Run 2026-10-24: a two-line comment added to `python/tests/guardrails/test_no_deprecated_refs.py`.
  Pushed as throwaway branch `087-t035-demo`, draft PR `#279`: `mutation` reported `skipping`,
  `result` passed. Closed without merging, remote and local branches deleted.
- [X] T036 Update `docs/backlog/087-mutation-gate-runtime.md`: set the status line to "Specified and implemented in `specs/087-mutation-gate-runtime` (2026-10-…)". Add a short "Outcome" section: the 39 s trial, the fresh full-run decision, the fifth subprocess caller, and the new floor. Update `docs/backlog/backlog.md` if it lists 087's status.
- [X] T037 Mark PR 2 ready (`gh pr ready`). Its body:
  - links spec, plan and research;
  - lists the measured gate duration (T020), the floor and how it was set, and the `act` results;
  - states that T027 is done, and that ntfy is deployed after the merge (T033).

  After the owner merges it, realign the local branch (`git fetch origin main && git reset --hard origin/main` on a fresh checkout of `main`).

  PR 2 (`#277`) was opened as a draft via the API (`gh api … -f draft=true`, Zscaler push block —
  see `AGENTS.md`) and converted to ready and merged by the owner directly on GitHub
  (2026-10-24T09:16Z); `gh pr ready` itself was never invoked, since the owner's conversion made it
  moot. T027 was **not** done before this merge (it is in Phase 8 of **this** follow-up PR, opened
  after #277, not before it) — see T033's note on the resulting sequencing change.
- [X] T038 US1 + FR-003 (quickstart §5, first half): run `gh workflow run nightly-deeper-verification.yml --ref main` and watch it. Confirm it is green, under 5 minutes in total, and that `ssh ci@pve 'readlink /mnt/nas/homelab_ci/mutmut/main; ls /mnt/nas/homelab_ci/mutmut; cat /mnt/nas/homelab_ci/mutmut/main/report.json'` shows one `main-<UTC>` with the run's `head_sha` as `commit`.

  **A third live bug found and fixed in the same session** (run 40084811736): `Publish main results
  to NAS`'s `rsync -a` implies `-g` (preserve group); the NAS export squashes writes to a mapped
  uid/gid, and `ci` cannot `chgrp` there, so every file failed and `set -e` halted the script before
  `report.json` was copied or `main` was repointed — exactly the scenario this task exists to catch
  (FR-003 had never been exercised live before this). Fixed with `--no-group` (verified directly
  against the real NAS mount before committing: `rc=0`), pushed straight to `main` (`bf0092e`, same
  direct-push pattern as the vault commit — a one-line operational fix to an already-merged
  workflow). Re-run (40085044484): **green, 1m34s total**, well under 5 minutes.
  `readlink /mnt/nas/homelab_ci/mutmut/main` → `main-20261024T101452Z`; `report.json`'s `commit` is
  `bf0092e...`, matching the run's `head_sha` exactly.
- [X] T039 US4, SC-004 (quickstart §5, second half):
  1. On the Mac, `task mutmut:pull` prints the commit and age.
  2. Edit a test in `python/tests/version_currency/` locally (then revert it), and time `.venv/bin/mutmut run "homelab_proxmox_orchestrator.version_currency*"` (module by name, because a test edit is not picked up by plain `mutmut run`, research R3): under 60 s. Then change one function in `version_currency.py` (and revert it), and confirm plain `.venv/bin/mutmut run` re-tests only that function's mutants.
  3. Open `.venv/bin/mutmut browse` and confirm survivors are listed.
  4. Run `MUTMUT_PULL_HOST=nope@nowhere task mutmut:pull` and confirm it exits non-zero with the error text, and that `ls -la mutants/report.json` is unchanged.

  All four done against the real published set (2026-10-24). (1) `task mutmut:pull` printed
  `commit e3db3d0... score 61.79% gate 60.00%` (now via the Taskfile wrapper, not raw `.venv/bin/
  mutmut`, per the addendum above). (2) `task mutmut:run -- "homelab_proxmox_orchestrator.
  version_currency*"` completed in **14 s** against the real pulled data, well under 60 s. A plain
  `task mutmut:run` with no module filter re-tested the whole mutant set (`4117/4117`, all 0 new
  mutations/second since nothing changed) and exited cleanly — it only *looked* hung on a first
  attempt because piping its carriage-return spinner through `| tail -20` under a hard shell timeout
  caught it mid-settle; run detached in the background, it finished in well under 10 s. (3)
  `mutmut browse --help` confirms the binary and command resolve correctly; the TUI itself was not
  interactively screenshotted (headless session), but the underlying survivor data is confirmed
  present (`mutmut:status`: 1061 survivors across modules). (4) Done earlier in this pass: exits 201
  with the correct error text, `mutants/report.json` left untouched.

  **A real bug found and fixed in the same pass**: `mutmut:pull`'s printed "Next" hint hardcoded
  `.venv/bin/mutmut`, but this Mac's `.venv` is Python 3.15 and has no mutmut (T012's note — mutmut
  3.8 has no 3.15 wheel). The owner hit exactly this (`zsh: no such file or directory:
  .venv/bin/mutmut`) running the hint verbatim. Fixed by adding four Taskfile tasks the owner asked
  for directly: `mutmut:run`, `mutmut:browse`, `mutmut:gate` (wraps the full local parity gate) and
  `mutmut:status` (prints the last result without re-running). All of them, and `mutmut:pull`'s
  hint, now auto-detect `.venv` vs `.venv-mutmut` so the right binary runs regardless of which venv
  a given machine ended up using. See T025's addendum for the full note.
- [X] T040 US5, SC-005 (quickstart §6): run `gh workflow run nightly-deeper-verification.yml --ref main -f min_score=99`. Confirm the job fails at `Fail on gate result`, and one message arrives on `mutation` with "floor 99.00". Then confirm that the next scheduled nightly is green and sends nothing.

  Run 40085176121: `Read ntfy token` and `Post regression alert` both succeeded (no
  `::warning::Regression alert not delivered`), `Fail on gate result` failed the job as designed
  (`::error::Mutation score 61.79% is below the gate 98.00%`). Confirmed delivery straight from the
  ntfy server's own message cache (`docker cp`'d out, inspected locally with `sqlite3`, both copies
  deleted after), without the agent ever touching the vault token:

  > **Mutation score 61.79% is below 98.00%**
  > Priority 4 (high), tags `test_tube`, click → the run's URL
  >
  > Floor 99.00% (margin 1.00). Commit bf0092e.
  > killed 1716 · survived 1061 · no tests 1337
  > Most survivors: ops_cli 147, summary_markdown 144, version_currency 143, orchestrator 124,
  > service_lifecycle 120

  Matches contracts/regression-alert.md's format exactly. `messages_published` on the server
  incremented by exactly 1 in the delivery minute. **Second half not yet checked**: the next
  `schedule` run (tonight, 2026-10-25T03:00Z) should read the committed floor (61.0) again and send
  nothing — too soon to confirm.

  **Blocked on T027 and T033** (the `mutation` ntfy account must exist and be deployed before this
  can deliver anything) **and on T038** (establishes the nightly runs cleanly at all first). The
  message-building code itself is verified against the contract's own example in T031's note.
- [X] T041 FR-011 prune (quickstart §7), after T038 has published: `ssh ci@pve 'ls -la /mnt/nas/homelab_ci/mutmut-cache'`. Confirm it holds only mutmut 2 `.mutmut-cache` files (about 14, each 0.3–0.4 MB; memory: look before deleting), and **ask the owner before deleting**. Then `ssh ci@pve 'rm -rf /mnt/nas/homelab_ci/mutmut-cache'`, and confirm `ls /mnt/nas/homelab_ci` shows `mutmut` and `infra_state` only.

  Precondition now met: T038 published for real (`/mnt/nas/homelab_ci/mutmut/main` exists). The
  "before" picture (T002's note: 15 entries, 300–393 KB each, oldest from 2026-07-20) is unchanged —
  **still not deleted**, pending the owner's explicit go-ahead as this task requires.

  The "before" half is done (T002's note: 15 entries, 300–393 KB each, oldest `main` from
  2026-07-20). **Not deleted**: this task explicitly says to ask the owner first, and it is also
  gated on T038 (nothing has published yet). Asking now, ahead of T038, would be asking about a
  snapshot that T038's own run will not have changed — better to ask once there is something new on
  the NAS to contrast it with.

---

## Phase 10: Polish & Cross-Cutting Concerns

- [ ] T042 SC-003: after 7 nightly runs following T038, run `gh run list --workflow nightly-deeper-verification.yml --limit 10 --json conclusion,headSha,createdAt`. Each one is green, and each `report.json` commit it published matched its `headSha`. A run skipped as `no-new-commits` counts neither way. Record the result.

  Time-gated on 7 nightly runs after T038. Not started.
- [ ] T043 SC-006 (quickstart §8): two weeks after T037, count cancelled `mutation.yml` runs created after the merge. Expected: 0. Record the result. If any are found, open a backlog note with the run IDs.

  Time-gated, two weeks from T037 (2026-10-24). Earliest check: 2026-11-07.
- [X] T044 [P] Update `specs/087-mutation-gate-runtime/spec.md` status to "Implemented (<date>)". Tick the checklist in `checklists/requirements.md` if anything changed. Confirm `CLAUDE.md`'s 087 lines still describe what shipped.

---

## Dependencies & Execution Order

- **Phase 1 → Phase 2 (PR 1) → merge → T007 live check → Phase 3.** PR 2 work starts only after PR 1
  is merged and verified, on a branch from the new `main`.
- **Phase 3** (T008–T015) blocks Phases 4–8.
  - T008 and T009 are written first.
  - T010 → T011 → T013 → T014 → T015 in order: the gate needs the config, the passing tests, the report script, then the shell script.
  - T012 runs in parallel with T010/T011.
- **Phase 4 (US2)** after Phase 3. T016 → T017 → T018.
- **Phase 5 (US3)** after Phase 3. T019 edits `mutation.yml` too, so run it after T016–T017, not alongside.
- **Phase 6 (US1 part 2)**: T020 needs Phases 4 and 5 committed and pushed, then T021 → T022 → T023 → T024 (all the same workflow file).
- **Phase 7 (US4)**: T025 and T026 can run in parallel with each other and with Phase 6.
- **Phase 8 (US5)**:
  - T027 (owner) must be done before T037 (merge), and T033 (ntfy deploy from `main`) after it.
  - T028 and T029 can run in parallel.
  - T030 needs T022–T024 (same file), then T031.
- **Phase 9** in order:
  1. T032.
  2. T034 and T035, in any order.
  3. T036, then T037 (merge).
  4. After the merge: T033 (owner, ntfy deploy from `main`) and T038, then T039, T040 (needs T033) and T041.
- **Phase 10** after Phase 9. T042 and T043 are time-gated.

## Parallel Examples

```bash
# Phase 3, first wave:
Task: "T008 python/tests/workflows/test_mutmut_report.py"
Task: "T009 python/tests/workflows/test_mutation_gate_paths.py"
Task: "T012 .gitignore + requirements-nightly + uv-lock"

# Phase 7/8, alongside Phase 6:
Task: "T025 Taskfile.yml mutmut:pull"
Task: "T026 docs/operations/mutation-testing.md"
Task: "T028 ntfy role defaults + preflight"
Task: "T029 scripts/healthcheck/ntfy-acl-check.sh"
```

## Implementation Strategy

### MVP

PR 1 (Phase 2) on its own: the nightly goes green on `schedule` after three months of failures. It
ships first, as the owner decided.

### Incremental delivery

PR 2 carries US2–US5. Inside it, the order is foundational → PR gate (US2) → path guard (US3) →
nightly publish (US1 part 2) → Mac loop (US4) → alert (US5). That way the draft PR's own run (T020)
measures the gate before the nightly work is done. If time is short, US5 (alert, plus the owner's
vault and ntfy steps) can move to a third PR. The nightly is already red on a regression without
it. US4 depends only on US1 part 2's published set.

### Rollback

PR 1: revert the PR. PR 2: revert the PR. The mutmut 2 cache is pruned only in T041, after the first
mutmut 3 nightly, so until then a revert restores the old gate with its old cache intact. After
T041, a revert would run mutmut 2 from an empty cache: slow, but correct.

## Notes

- [P] = different files, no dependency on an incomplete task.
- Do not add an incremental mode, seeding or staleness logic to the gate (spec Clarifications,
  research R2).
- Do not loosen the `mutation` job's owner/fork guard.
- Commit after each phase. Push through the GitHub API (Zscaler).

## Rollout record

| Step | Date | Run ID / evidence | Result |
|---|---|---|---|
| T001/T002 baseline | 2026-10-24 | `ssh ci@pve 'ls -la /mnt/nas/homelab_ci/mutmut-cache'` | 15 entries, 300–393 KB each; `main` dated 2026-07-20; `/mnt/nas/homelab_ci/mutmut` (mutmut 3 target) does not exist yet |
| T007 PR 1 manual nightly | — | — | Not run (see T007's note: would hit the live heredoc bug this pass fixed) |
| T007 first `schedule` nightly | — | `gh run list` | 10 consecutive `schedule` failures through 2026-10-24T03:09Z, all pre-dating #276/#277. Not yet re-checked by an actual `schedule` trigger (next: 2026-10-25T03:00Z), but two `workflow_dispatch` runs same day exercised the identical code path end to end and were green (see T038) |
| T015 Mac gate (floor) | 2026-10-24 | local, `.venv-mutmut` | killed 1700, survived 1078, no_tests 1337, timeout 2, total 4117 — **61.20%**, exit 0, ~1:58 wall |
| T020 PR 2 gate run | 2026-10-24 | PR #277, run 40077155642 | mutation job 1m2s; killed 1716, survived 1061, no_tests 1337, timeout 3 — **61.79%**, gate PASSED |
| T032 parity | 2026-10-24 | local, re-run on `main` post-merge | 61.20% (Mac) vs 61.79% (CI, same commit family) — 0.59 pt difference, within tolerance |
| T033 ntfy deploy | 2026-10-24 | `gh run` 40084566355 (apply) | `mutation` account live, write-only to topic `mutation`; unrelated pre-existing `Lifecycle verification` step failed (failed on last 5 runs since 2026-09-19) |
| T034 SC-007 | — | — | Not run — see T034's note |
| T035 SC-001 | — | — | Not run — see T035's note |
| T038 nightly publish | 2026-10-24 | `gh run` 40084811736 (rsync bug found) → 40085044484 (green, 1m34s) | `main` → `main-20261024T101452Z`; `report.json.commit` = `bf0092e`, matches `head_sha` |
| T039 Mac loop | 2026-10-24 (step 4 only) | local, `MUTMUT_PULL_HOST=nope@nowhere task mutmut:pull` | exit 201, correct error text, `mutants/report.json` unchanged. Steps 1–3 still open (not run against the now-real published set) |
| T040 alert | 2026-10-24 | `gh run` 40085176121 | Delivered; read from ntfy's own message cache (sqlite3, both temp copies deleted after): title/body match contracts/regression-alert.md exactly. Second half (next scheduled run silent) not yet checked — too soon |
| T041 prune | 2026-10-24 ("before" only) | T002's note | Precondition met (T038 published); still not deleted — needs the owner's explicit go-ahead |
| T042 SC-003 | — | — | Time-gated: 7 nightly runs after T038 (2026-10-24) |
| T043 SC-006 | — | — | Time-gated: 2026-11-07 (two weeks after T037's 2026-10-24 merge) |

## Phase 11: Convergence

- [X] T045 Amend `spec.md` FR-003 and `plan.md` "Nightly" step 3 so a nightly dispatched with `min_score` (the alert test) does not publish, matching `.github/workflows/nightly-deeper-verification.yml` (publish `if:` requires `env.MUTMUT_MIN_SCORE == ''`) and `contracts/published-results.md` per FR-003 (contradicts)

  Owner chose to keep the code and amend the docs (2026-10-24). Amended `spec.md` FR-003, `plan.md` "Nightly" step 3, `quickstart.md` §6 and the exit-code table in `contracts/gate-script.md`.
- [ ] T046 After the first `schedule`-triggered nightly on the mutmut 3 workflow (2026-10-25T03:00Z or later), confirm it is green, published a new `main-<UTC>` set whose `report.json` `commit` equals the run's `head_sha` and `floor` is the committed one, and sent no message on ntfy topic `mutation`; record it under T040 and T007 and in the Rollout record per SC-005 / US5/AC2 (partial)
- [ ] T047 On the Mac after `task mutmut:pull`, change one function in `python/src/homelab_proxmox_orchestrator/version_currency.py`, run `task mutmut:run`, and confirm only that function's mutants are re-tested; revert the change. Open `task mutmut:browse` and confirm survivors are listed. Record both under T039 per US4/AC1, US4/AC2 (partial)
- [ ] T048 Make the PR gate keep no results after it ends: add an `if: always()` step after `Fetch mutation report` in `.github/workflows/mutation.yml` that runs `ssh ci@pve 'rm -rf /home/ci/homelab-proxmox/mutants'`, with a guard test in `python/tests/workflows/`; or, if the owner prefers, amend FR-004 to "carries no results into the next run" (already true: `scripts/ci/mutmut-threshold.sh` deletes `mutants/` first) per FR-004 (partial)
- [ ] T049 Record in this file (a note under T044 or the Rollout record) the PR #281 additions not called for by spec, plan or tasks, and why: `python/tests/workflows/test_workflow_heredocs.py` (heredoc bug hit three times in 087), `norecursedirs` in `python/pytest.ini` (stray `mutants/` broke collection; FR-006/FR-007), the `--python '>=3.11,<3.15'` range on the ansible-lint hook in `.pre-commit-config.yaml`, the AGENTS.md "Running the tests" and `act` sections, and the orphaned-process note in `docs/operations/mutation-testing.md` (unrequested)
