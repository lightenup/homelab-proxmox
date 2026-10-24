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

- [ ] T001 Confirm the branch is `087-mutation-gate-runtime` and up to date with `origin/main` (`git fetch origin main && git log --oneline origin/main -1`). Run `bash scripts/ci/python-tests.sh` and `act -l`. Record any failure that already exists as a note at the end of this file, so it is not blamed on this feature.
- [ ] T002 Read-only check on `pve`: `ssh ci@pve 'ls -la /mnt/nas/homelab_ci /mnt/nas/homelab_ci/mutmut-cache; df -h /mnt/nas/homelab_ci'`. Record the file count and the age of `mutmut-cache/main` in the T001 note. That is the "before" picture for quickstart §1 and §7.

---

## Phase 2: User Story 1, part 1 — the nightly runs on PVE when scheduled (Priority: P1) 🎯 MVP · **PR 1**

**Goal**: A scheduled nightly does the PVE mutation path, still on mutmut 2 (FR-002, research R5).

**Independent Test**: quickstart §1. A manual run with no inputs runs the PVE steps, and
`mutmut-cache/main` on the NAS gets today's date. The next 03:00 `schedule` run is green.

### Tests for User Story 1 (written now, committed in PR 2)

- [ ] T003 [US1] Extend `python/tests/workflows/test_workflow_inputs.py` (reuse its `_load_yaml` and `_Yaml12SafeLoader`). Add `test_nightly_does_not_depend_on_dispatch_inputs`. Load `.github/workflows/nightly-deeper-verification.yml` and assert:
  - (a) `on.workflow_dispatch` exists, and its `inputs` is absent or empty. Write it as `set(inputs) <= ALLOWED_NIGHTLY_INPUTS` with `ALLOWED_NIGHTLY_INPUTS = set()`. PR 2 changes that to `{"min_score"}`.
  - (b) No `if:` value on any job or step contains `inputs.`.
  - (c) The `deeper` job has an integer `timeout-minutes`.
  - (d) No step `run:` contains `run_on_pve`.

  Docstring: "FR-002: a schedule run gets no dispatch inputs (spec 087)". Run `.venv/bin/python -m pytest -c python/pytest.ini -o addopts= python/tests/workflows/test_workflow_inputs.py` and confirm the new test **fails** on today's workflow. **Do not commit it in PR 1**: any `python/` change triggers today's mutmut 2 gate. Keep it as a local change (`git stash` or a scratch commit outside PR 1) and commit it as the first commit of PR 2, where T021 extends it.

### Implementation for User Story 1 (PR 1)

- [ ] T004 [US1] Edit `.github/workflows/nightly-deeper-verification.yml`:
  - (1) Delete the `run_mutmut` and `run_on_pve` inputs. Leave `workflow_dispatch:` with no `inputs` key.
  - (2) Delete the `if: ${{ inputs.run_on_pve }}` line from each of: `Install rsync/ssh (PVE remote)`, `Ensure artifact root on PVE`, `Sync repo to PVE`, `Prepare mutmut shared cache on PVE`, `Prepare Python venv on PVE`, `Mutation testing (mutmut) on PVE`.
  - (3) Delete the two steps guarded by `!inputs.run_on_pve`: `Prepare mutmut shared cache` and `Mutation testing (mutmut)`.
  - (4) Add `timeout-minutes: 120` to the `deeper` job (plan, PR 1 step 4).

  Leave every other step unchanged in PR 1.
- [ ] T005 [US1] In the same file, in the `gate` job's `Decide whether to run` step, make the `no-new-commits` skip apply only to scheduled runs: change the check to `if [ "${GITHUB_EVENT_NAME}" = "schedule" ] && [ "$last_sha" = "$GITHUB_SHA" ]; then`. A `workflow_dispatch` on an unchanged `main` must still run (research R5).
- [ ] T006 [US1] Re-run the T003 test (locally, uncommitted) and the whole `python/tests/workflows/` directory, and confirm green. Confirm the PR 1 diff touches only `.github/workflows/nightly-deeper-verification.yml` (`git diff --name-only origin/main`). Run `act -l` and `act -n -W .github/workflows/nightly-deeper-verification.yml schedule`. In the dry-run output, no step of `deeper` is skipped because of a condition. Record the `act` result in the PR description (Constitution, "Local Workflow Testing").
- [ ] T007 [US1] Open PR 1 (`gh pr create`, base `main`), titled `fix(087): nightly runs the PVE mutation path on schedule`. The body links spec FR-002 and research R5, says mutmut 2 is unchanged, notes the expected ~1 h nightly, and says the guard test follows in PR 2 so that PR 1 skips the mutation gate. Confirm the PR's `mutation` job is skipped and `result` passes. After the owner merges it, run quickstart §1:
  1. `gh workflow run nightly-deeper-verification.yml --ref main`.
  2. Watch it with `gh run watch`.
  3. Confirm the PVE steps run.
  4. Run `ssh ci@pve 'ls -l --time-style=+%F /mnt/nas/homelab_ci/mutmut-cache/main'`.

  Record the run ID, duration and result under "Rollout record" at the end of this file. Then check the next `schedule` run the same way (SC-003, first of 7).

**Checkpoint**: PR 1 merged and the nightly green on `schedule`. Cut the PR 2 branch from the new `main` (keep the name `087-mutation-gate-runtime`, rebased), and commit the T003 test first.

---

## Phase 3: Foundational — mutmut 3 core (blocks US2–US5) · **PR 2**

**Purpose**: Configuration, test fixes, the report script and the gate script. Every later phase
uses them.

### Tests (write first, see them fail)

- [ ] T008 [P] Create `python/tests/workflows/test_mutmut_report.py` for `scripts/ci/mutmut_report.py`. Import it with `importlib.util.spec_from_file_location`, because `scripts/ci` is not a package. In `tmp_path`, build a fake `mutants/` holding:
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
- [ ] T009 [P] Create `python/tests/workflows/test_mutation_gate_paths.py`, modelled on `python/tests/workflows/test_confidence_gate_paths.py` (same YAML loader, same "cleaned patterns" helper). It reads `scripts/ci/mutation-gate-paths.txt`. Lines starting with `!` are exclude EREs, and all other non-comment, non-blank lines are include EREs. Implement `_decide(paths) -> bool` the way the workflow will: drop paths matching any exclude, then run if any remaining path matches an include. Assert:
  - **Runs** (true) for each of: `python/src/homelab_proxmox_orchestrator/cli.py`, `python/tests/orchestrator/test_cli.py`, `python/tests/conftest.py`, `python/pytest.ini`, `python/mutmut-threshold.txt`, `python/requirements-nightly.lock.txt`, `python/requirements-test.txt`, `setup.cfg`, `src`, `scripts/ci/mutmut-threshold.sh`, `scripts/ci/mutmut_report.py`, `scripts/ci/mutation-gate-paths.txt`, `.github/workflows/mutation.yml`.
  - **Skips** (false) for each of: `python/tests/guardrails/test_service_backup.py`, `python/tests/workflows/test_confidence_gate_paths.py`, `.github/workflows/ci.yml`, `docs/operations/mutation-testing.md`, `ansible/roles/ntfy/defaults/main.yml`.
  - **Workflow wiring**: `.github/workflows/mutation.yml` contains `scripts/ci/mutation-gate-paths.txt` and `grep -qEf`, and no longer contains `grep -qE '^python/'`.
  - **Coverage**: every directory directly under `python/tests/`, except `guardrails`, `workflows` and `__pycache__`, has a `test_x.py` path that runs. A new test directory is then covered by default, which prefers a false run (research R9).

  Confirm it fails.

### Implementation

- [ ] T010 Create the layout symlink `src -> python/src` at the repo root (`ln -s python/src src`, committed as a symlink; through the Git-Data API it is a tree entry with mode `120000`). Create `setup.cfg` at the repo root containing only a `[mutmut]` section, with one value per line, exactly as in research R4:
  - `source_paths = src/homelab_proxmox_orchestrator`
  - `also_copy` = `python/tests`, `python/pytest.ini`, `scripts`, `terraform`, `Taskfile.yml`
  - `pytest_add_cli_args` = `-c`, `python/pytest.ini`, `-o`, `addopts=`, `-o`, `pythonpath=src`
  - `pytest_add_cli_args_test_selection` = `python/tests`, `--ignore=python/tests/guardrails`, `--ignore=python/tests/workflows`

  Add a two-line header comment naming spec 087 and research R4. Delete `python/mutmut.ini`.
- [ ] T011 [P] Fix the subprocess callers (research R4 point 3) so they run the mutated code under mutmut and still pass outside it.
  - **Three tests**: `python/tests/orchestrator/test_cli.py`, `python/tests/orchestrator/test_runner_plan_apply.py` and `python/tests/orchestrator/test_provenance_mismatch.py`. In each, replace the `"python3"` argv element with `sys.executable`. Replace `env={"PYTHONPATH": "python/src"}` with `env={"PYTHONPATH": _PKG_ROOT}`, where the module defines `_PKG_ROOT = str(Path(homelab_proxmox_orchestrator.__file__).resolve().parents[1])` after its imports, with `import sys`, `from pathlib import Path` and `import homelab_proxmox_orchestrator` added if missing.
  - **`python/tests/orchestrator/test_exec.py`**: replace both `"python3"` with `sys.executable`.
  - **`python/tests/task_smoke/helpers.py`**: replace `repo_python_src = repo_root / "python" / "src"` with the imported package's parent (`Path(homelab_proxmox_orchestrator.__file__).resolve().parents[1]`), importing the package at module top.

  Match each file's import style. Run `bash scripts/ci/python-tests.sh` and confirm green.
- [ ] T012 [P] Add `mutants/` to `.gitignore` and delete its two `.mutmut-cache` lines. Change `mutmut>=2,<3` to `mutmut>=3.8,<4` in `python/requirements-nightly.txt`. Regenerate both locks with `bash scripts/ci/uv-lock.sh`. It keeps existing pins, so check that `git diff python/requirements-test.lock.txt` is empty. If it is not, revert that file. In `python/requirements-nightly.lock.txt`, confirm `mutmut==3.8.0` is pinned and the header command is unchanged. Re-sync the local venv: `uv pip sync --python .venv/bin/python --require-hashes python/requirements-nightly.lock.txt`. The Mac `.venv` is Python 3.15, and mutmut 3.8 has only been tried on 3.14 (research R11). If the sync fails (for example no 3.15 wheel for `libcst` or `setproctitle`), **stop and report**. Do not change the lock's `--python-version 3.11`. The fallback is a separate `uv venv --python 3.14 .venv-mutmut` for the mutation loop, used by T015, T032 and T039 through `PYTHON_BIN=.venv-mutmut/bin/python`, and documented in T026.
- [ ] T013 Create `scripts/ci/mutmut_report.py`: standard library only, `#!/usr/bin/env python3`, with a docstring naming spec 087, data-model.md and contracts/published-results.md.
  - **Arguments**: `--mutants-dir` (default `mutants`), `--floor` (float), `--margin` (float), `--commit` (str), `--mutmut-version` (str).
  - **Reads** `mutmut-cicd-stats.json` and every `src/homelab_proxmox_orchestrator/**/*.py.meta` under the mutants dir.
  - **Writes** `report.json` (`schema: 1`, the fields and order of contracts/published-results.md, `finished_at` as `datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")`) and `survivors.txt`.
  - **Prints**: the counts, then `>> mutation score: S%  (floor F% - margin M = gate G%)` (keep today's wording), then the top 10 survivor modules. If `GITHUB_STEP_SUMMARY` is set, it appends a markdown table of the same.
  - **Exit**: on failure it prints `::error::Mutation score S% is below the gate G%` and exits 1. With missing stats or `total == 0` it prints `::error::mutmut produced no results (run failed)` and exits 2. Otherwise 0.
  - **Status map**: a module-level dict copied from data-model.md, with a comment naming mutmut 3.8.0's `mutmut/stats.py`.

  Run the T008 tests and confirm green.
- [ ] T014 Rewrite `scripts/ci/mutmut-threshold.sh` per contracts/gate-script.md:
  - **Keep**: the header style, the `REPO_ROOT` cd, `PYTHON_BIN`/`MUTMUT_THRESHOLD_FILE`/`MUTMUT_MIN_SCORE`/`MUTMUT_SCORE_MARGIN` handling and the floor parsing.
  - **Update the header comment**: mutmut 3, a fresh run every time, the score formula, no-tests excluded, and that running it on the Mac discards pulled results.
  - **Body**:
    1. Set `MUTMUT_COMMIT` (default `git rev-parse HEAD 2>/dev/null || echo unknown`).
    2. `rm -rf mutants`.
    3. `"$PYTHON_BIN" -m mutmut run`, then `"$PYTHON_BIN" -m mutmut export-cicd-stats`; exit 2 if either fails (amended after PR #277 review: mutmut 3.8 exits 0 when mutants survive, so a nonzero exit is a real failure; see contracts/gate-script.md).
    4. Read the version: `version="$("$PYTHON_BIN" -m mutmut --version | awk '{print $NF}')"`.
    5. `exec "$PYTHON_BIN" scripts/ci/mutmut_report.py --floor "$FLOOR" --margin "$MARGIN" --commit "$MUTMUT_COMMIT" --mutmut-version "$version"`.
  - **Remove**: the mutmut 2 flags (`--paths-to-mutate`, `--tests-dir`, `--runner`, `result-ids`) and the inline Python.
- [ ] T015 Measure and set the floor (research R6). Run `bash scripts/ci/mutmut-threshold.sh; echo "exit=$?"` on the Mac and record the counts, score and wall time. Expect exit 0 or 1, and a score near 61.81%. Rewrite `python/mutmut-threshold.txt`:
  - Comment lines: "Score = 100 * killed / (killed + survived)", "Excluded: no tests, timeout, suspicious, skipped, segfault, caught by type check (spec 087 FR-010)", "Measured <score>% on <commit> with mutmut 3.8.0", and "Ratchet UP by hand via PR; never lower without justification".
  - Then one line: the score rounded down to a whole point, as `NN.0`.

  Remove the stale "PLACEHOLDER" comment. Re-run the script and confirm exit 0. The floor is re-checked against the PR's own CI score in T020.

**Checkpoint**: the gate runs on the Mac with mutmut 3 and passes, and T008 is green.

---

## Phase 4: User Story 2 — a PR gets a mutation result in minutes (Priority: P1) · PR 2

**Goal**: The PR gate does a fresh full run of the branch on PVE and reports within 5 minutes
(FR-004, SC-002, SC-007).

**Independent Test**: quickstart §3. The PR 2 run itself finishes in under 5 minutes, and a
throwaway PR with a weakened test fails `result`.

- [ ] T016 [US2] Edit `.github/workflows/mutation.yml`, `mutation` job:
  - (1) Add `timeout-minutes: 20`.
  - (2) In `Sync repo to PVE`, change `--exclude '.mutmut-cache'` to `--exclude 'mutants/'`.
  - (3) Delete the step `Prepare mutmut cache on PVE (seed from main baseline)` completely.
  - (4) Change `Run mutation gate on PVE` to `ssh ci@pve "cd /home/ci/homelab-proxmox && PYTHON_BIN=.venv/bin/python MUTMUT_COMMIT='${HEAD_SHA}' bash scripts/ci/mutmut-threshold.sh"`, with `env: HEAD_SHA: ${{ github.event.pull_request.head.sha || github.sha }}`. Record the exit status with `set +e … rc=$?; echo "rc=$rc" >> "$GITHUB_OUTPUT"`, and give the step `id: gate_run`.
  - (5) Add a step `Fetch mutation report`, with `if: always()`: `scp ci@pve:/home/ci/homelab-proxmox/mutants/report.json ci@pve:/home/ci/homelab-proxmox/mutants/survivors.txt . || true`. If `report.json` exists, append to `GITHUB_STEP_SUMMARY` a short table (score, floor, margin, gate, killed, survived, no tests) and the first 10 lines of `survivors.txt`. Parse it with `python3 -c 'import json…'`: the Pi's system Python is enough, stdlib only.
  - (6) Add a final step that runs `exit "${{ steps.gate_run.outputs.rc }}"`, so the job fails on 1 or 2.

  Keep the job's `if:` owner/fork guard **unchanged** (memory: public repo). Keep the `Prepare Python venv on PVE` step as it is: it syncs the nightly lock, which now has mutmut 3.8.
- [ ] T017 [US2] Edit the same file's `concurrency` comment if it mentions the cache. Leave the `result` job unchanged. Confirm no step mentions `.mutmut-cache` or `mutmut-cache` (`grep -n mutmut-cache .github/workflows/mutation.yml` prints nothing).
- [ ] T018 [US2] Run `act -n -W .github/workflows/mutation.yml pull_request` and `act -l`, and confirm both parse. Record the result for the PR description.

**Checkpoint**: the PR gate is wired. It is first exercised live in T020 (PR 2's own run).

---

## Phase 5: User Story 3 — PRs that cannot change the score skip the gate (Priority: P2) · PR 2

**Goal**: The mutation job runs only for paths that can change the outcome (FR-006, research R9,
SC-001).

**Independent Test**: T009 is green, and quickstart §4 (a guard-test-only draft PR skips
`mutation`).

- [ ] T019 [US3] Create `scripts/ci/mutation-gate-paths.txt` in the format of `scripts/ci/confidence-suite-paths.txt`.
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

- [ ] T020 [US1] Open PR 2 as a **draft** now (`gh pr create --draft`), so its own mutation run measures the new gate: it touches `mutation.yml` and `setup.cfg`, so it triggers. Record the `mutation` job's duration (SC-002: under 5 min), counts and score under "Rollout record". If the CI score rounded down differs from the T015 floor, set `python/mutmut-threshold.txt` to the **lower** of the two and note why. Leave it in draft until T037.
- [ ] T021 [US1] Update `python/tests/workflows/test_workflow_inputs.py` (T003, committed at the start of PR 2): set `ALLOWED_NIGHTLY_INPUTS = {"min_score"}`. Add `test_nightly_mutmut3_wiring`, which asserts that `nightly-deeper-verification.yml`:
  - (a) contains no `.mutmut-cache` and no `mutmut-cache`;
  - (b) has a step whose `run` contains `scripts/ci/mutmut-threshold.sh`;
  - (c) has a step whose `run` contains `mv -T` and `/mnt/nas/homelab_ci/mutmut`;
  - (d) has no step named `Upload artifacts`, `Install Ansible Galaxy deps`, `Setup Python (GitHub-hosted only)` or `Debug runner + mounts`;
  - (e) has `deeper.timeout-minutes == 30`.

  Confirm it fails.
- [ ] T022 [US1] Edit `.github/workflows/nightly-deeper-verification.yml` (plan, "Nightly"):
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
- [ ] T023 [US1] In the same file, add a step `Publish main results to NAS` (`id: publish`) with `if: ${{ steps.gate_run.outputs.rc == '0' || steps.gate_run.outputs.rc == '1' }}`. It is a remote `ssh ci@pve bash -s <<'EOF'` heredoc, `set -euo pipefail`, that follows the "Publish procedure" in contracts/published-results.md:
  1. Set `root=/mnt/nas/homelab_ci/mutmut`, `ts="$(date -u +%Y%m%dT%H%M%SZ)"` and `dest="$root/main-$ts"`, then `mkdir -p "$dest"`.
  2. Copy the result files. From `/home/ci/homelab-proxmox/mutants`, run `find . -name '*.meta' -print0 | rsync -a --from0 --files-from=- ./ "$dest/"`, then `cp mutmut-stats.json mutmut-cicd-stats.json survivors.txt "$dest/"`, and copy `report.json` **last**.
  3. `ln -sfn "main-$ts" "$root/main.tmp" && mv -T "$root/main.tmp" "$root/main"`.
  4. `ls -1d "$root"/main-* | sort | head -n -2 | xargs -r rm -rf`, which keeps the newest two.
  5. `readlink "$root/main"`.
- [ ] T024 [US1] In the same file, add the last step, `Fail on gate result`, with `if: always()`. It exits 1 when `steps.gate_run.outputs.rc` is not `0`, with `::error::` naming the rc. A publish failure already fails the job through step `publish` (no `continue-on-error`). Run the T021 and T003 tests and confirm green. Run `act -n -W .github/workflows/nightly-deeper-verification.yml schedule` and `... workflow_dispatch`, and confirm both parse.

**Checkpoint**: the nightly is wired for mutmut 3. It is exercised live after merge (T038).

---

## Phase 7: User Story 4 — the owner inspects survivors on the Mac (Priority: P2) · PR 2

**Goal**: One task pulls `main`'s published results to the Mac through `ci@pve`, safely (FR-008,
research R11).

**Independent Test**: quickstart §5, second half. After `task mutmut:pull`,
`mutmut run "homelab_proxmox_orchestrator.version_currency*"` takes under a minute, and a bad host
leaves `mutants/` unchanged.

- [ ] T025 [P] [US4] Add task `mutmut:pull` to `Taskfile.yml`, after the `ansible:*` tasks, in the file's style:
  - `desc: "[LOCAL] Pull main's published mutation results from the NAS via ci@pve (spec 087)"`, with a `summary:` that describes the loop and the example `task mutmut:pull`.
  - One `cmds:` bash block, `set -euo pipefail`, with `host="${MUTMUT_PULL_HOST:-ci@pve}"`:
    1. `tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT`.
    2. Run `rsync -a "$host:/mnt/nas/homelab_ci/mutmut/main/" "$tmp/"`. On failure, print `error: could not pull from $host:/mnt/nas/homelab_ci/mutmut/main/ (is pve reachable and has a nightly published?)` and exit 1.
    3. Check `"$tmp/report.json"` exists and has `schema == 1`, using `python3 -c`. Otherwise print an error and exit 1.
    4. Only then `mkdir -p mutants`, delete `mutants/mutmut-stats.json` and `mutants/mutmut-cicd-stats.json`, and run `find mutants -name '*.meta' -delete` (results only; never `rm -rf mutants`). Then `rsync -a "$tmp/" mutants/`.
    5. Print `commit`, `finished_at`, the age in hours, `score`/`gate`, and the next commands: `.venv/bin/mutmut run` (re-tests local source changes), `.venv/bin/mutmut run "homelab_proxmox_orchestrator.<module>*"` (after editing tests) and `.venv/bin/mutmut browse`.
- [ ] T026 [P] [US4] Create `docs/operations/mutation-testing.md`, written like `docs/operations/proxmox-ci.md`. Sections:
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

- [ ] T027 [US5] **(owner)** Generate the `mutation` publisher's password hash and token, per `docs/runbooks/ntfy-add-publisher.md` §2. Add them with `ansible-vault edit ansible/group_vars/services/vault.yml` as `ntfy_mutation_password_hash` and `ntfy_mutation_token`. The agent does not see the values. Verification, run by the owner: `ansible-vault view ansible/group_vars/services/vault.yml | grep -c '^ntfy_mutation_'` prints `2`. **This must be done before T028 merges**, or the ntfy role renders undefined variables on its next deploy.
- [ ] T028 [P] [US5] In `ansible/roles/ntfy/defaults/main.yml`, append to `ntfy_users`: `- name: "mutation"`, `topic: "mutation"`, `password_hash: "{{ ntfy_mutation_password_hash }}"`, `token: "{{ ntfy_mutation_token }}"`. In `ansible/roles/ntfy/tasks/preflight.yml`, add `ntfy_mutation_password_hash` and `ntfy_mutation_token` to the required-variables assertion and to its `fail_msg` list, in the same pattern as `ntfy_version_check_*`. From `ansible/`, run `ansible-playbook -i inventories/prod/hosts.yml --syntax-check playbooks/ntfy.yml`.
- [ ] T029 [P] [US5] Extend `scripts/healthcheck/ntfy-acl-check.sh` per `docs/runbooks/ntfy-add-publisher.md` §5:
  - Add `NTFY_MUTATION_TOKEN` to the usage text, the required-vars loop and the token-name lookup.
  - Add a `do_request "$NTFY_MUTATION_TOKEN" …` row for each topic: `GET` deny on all topics including `mutation`, `POST` allow on `mutation`, deny on the rest.
  - Add a `mutation` column to every existing publisher's rows: `POST mutation` deny, `GET mutation` deny.
  - The owner's token gets `GET mutation` allow.

  Follow the existing row order and spacing.
- [ ] T030 [US5] In `.github/workflows/nightly-deeper-verification.yml`, between `Publish main results to NAS` and `Fail on gate result`, add two steps, both with `if: ${{ steps.gate_run.outputs.rc == '1' }}`:
  1. `Read ntfy token`: copy `version-currency.yml`'s step verbatim, except the key is `ntfy_mutation_token`, the error text matches, and the env var is `NTFY_TOKEN`. Keep `::add-mask::`, `umask 077` and the temp-file trap.
  2. `Post regression alert`: build the message from the fetched `report.json` with `python3` (stdlib) exactly per contracts/regression-alert.md:
     - Title: `Mutation score S% is below G%`.
     - Body: the floor/margin/commit line, the counts line, `Most survivors:`, and the top 5 modules.
     - Then `curl -sS -o /dev/null -w '%{http_code}' --max-time 20 -X POST -H "Authorization: Bearer $NTFY_TOKEN" -H "Title: …" -H "Priority: high" -H "Tags: test_tube" -H "Click: $GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID" --data-binary @"$msg" https://ntfy.hus-sky.no/mutation`.
     - If the status is not `200`, or curl fails, print `::warning::Regression alert not delivered (<status or error>)` and **exit 0**: `Fail on gate result` fails the job anyway.

  Add `(e2)` to `test_nightly_mutmut3_wiring` (T021): a step's `run` contains `ntfy_mutation_token`, and the token is never in a URL (`?auth=` absent). Re-run the tests.
- [ ] T031 [US5] Run `act -n -W .github/workflows/nightly-deeper-verification.yml workflow_dispatch --input min_score=99` and confirm the alert steps appear in the plan. Run the full `python/tests/workflows/` suite and `bash scripts/ci/python-tests.sh`, and confirm green.

**Checkpoint**: all of PR 2's code is done.

---

## Phase 9: Rollout and live verification (quickstart order)

**Purpose**: Land PR 2, prove each success criterion live, and record it. Record each result
under "Rollout record" below.

- [ ] T032 Run the Mac gate once more on the final PR 2 head (`bash scripts/ci/mutmut-threshold.sh`). Confirm exit 0 and that the score is within 1 point of the CI score on the same commit (FR-001 parity).
- [ ] T033 **(owner)** **After T037 (merge), before T040.** Confirm T027 is done (the `grep -c` check prints `2`). Then deploy ntfy from `main` through the normal promotion path (`ntfy-add-publisher.md` §3), never from the PR branch: a later prod deploy from `main` would otherwise drop the `mutation` account again. Subscribe to `mutation` on the phone (§4), and run the ACL check with all tokens (§5): every cell PASS.
- [ ] T034 SC-007 (quickstart §3.2): on a throwaway branch off PR 2, delete the assertions in one test in `python/tests/orchestrator/` so the Mac gate (T032) drops below the gate line. Open a draft PR and confirm `result` fails, with the score below the gate line in the summary. Close it without merging and delete the branch.
- [ ] T035 SC-001 (quickstart §4): on a throwaway branch off PR 2, add one comment line to a file under `python/tests/guardrails/`. Open a draft PR and confirm `mutation` is skipped and `result` passes. Close it and delete the branch.
- [ ] T036 Update `docs/backlog/087-mutation-gate-runtime.md`: set the status line to "Specified and implemented in `specs/087-mutation-gate-runtime` (2026-10-…)". Add a short "Outcome" section: the 39 s trial, the fresh full-run decision, the fifth subprocess caller, and the new floor. Update `docs/backlog/backlog.md` if it lists 087's status.
- [ ] T037 Mark PR 2 ready (`gh pr ready`). Its body:
  - links spec, plan and research;
  - lists the measured gate duration (T020), the floor and how it was set, and the `act` results;
  - states that T027 is done, and that ntfy is deployed after the merge (T033).

  After the owner merges it, realign the local branch (`git fetch origin main && git reset --hard origin/main` on a fresh checkout of `main`).
- [ ] T038 US1 + FR-003 (quickstart §5, first half): run `gh workflow run nightly-deeper-verification.yml --ref main` and watch it. Confirm it is green, under 5 minutes in total, and that `ssh ci@pve 'readlink /mnt/nas/homelab_ci/mutmut/main; ls /mnt/nas/homelab_ci/mutmut; cat /mnt/nas/homelab_ci/mutmut/main/report.json'` shows one `main-<UTC>` with the run's `head_sha` as `commit`.
- [ ] T039 US4, SC-004 (quickstart §5, second half):
  1. On the Mac, `task mutmut:pull` prints the commit and age.
  2. Edit a test in `python/tests/version_currency/` locally (then revert it), and time `.venv/bin/mutmut run "homelab_proxmox_orchestrator.version_currency*"` (module by name, because a test edit is not picked up by plain `mutmut run`, research R3): under 60 s. Then change one function in `version_currency.py` (and revert it), and confirm plain `.venv/bin/mutmut run` re-tests only that function's mutants.
  3. Open `.venv/bin/mutmut browse` and confirm survivors are listed.
  4. Run `MUTMUT_PULL_HOST=nope@nowhere task mutmut:pull` and confirm it exits non-zero with the error text, and that `ls -la mutants/report.json` is unchanged.
- [ ] T040 US5, SC-005 (quickstart §6): run `gh workflow run nightly-deeper-verification.yml --ref main -f min_score=99`. Confirm the job fails at `Fail on gate result`, and one message arrives on `mutation` with "floor 99.00". Then confirm that the next scheduled nightly is green and sends nothing.
- [ ] T041 FR-011 prune (quickstart §7), after T038 has published: `ssh ci@pve 'ls -la /mnt/nas/homelab_ci/mutmut-cache'`. Confirm it holds only mutmut 2 `.mutmut-cache` files (about 14, each 0.3–0.4 MB; memory: look before deleting), and **ask the owner before deleting**. Then `ssh ci@pve 'rm -rf /mnt/nas/homelab_ci/mutmut-cache'`, and confirm `ls /mnt/nas/homelab_ci` shows `mutmut` and `infra_state` only.

---

## Phase 10: Polish & Cross-Cutting Concerns

- [ ] T042 SC-003: after 7 nightly runs following T038, run `gh run list --workflow nightly-deeper-verification.yml --limit 10 --json conclusion,headSha,createdAt`. Each one is green, and each `report.json` commit it published matched its `headSha`. A run skipped as `no-new-commits` counts neither way. Record the result.
- [ ] T043 SC-006 (quickstart §8): two weeks after T037, count cancelled `mutation.yml` runs created after the merge. Expected: 0. Record the result. If any are found, open a backlog note with the run IDs.
- [ ] T044 [P] Update `specs/087-mutation-gate-runtime/spec.md` status to "Implemented (<date>)". Tick the checklist in `checklists/requirements.md` if anything changed. Confirm `CLAUDE.md`'s 087 lines still describe what shipped.

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
| T001/T002 baseline | | | |
| T007 PR 1 manual nightly | | | |
| T007 first `schedule` nightly | | | |
| T015 Mac gate (floor) | | | |
| T020 PR 2 gate run | | | |
| T032 parity | | | |
| T034 SC-007 | | | |
| T035 SC-001 | | | |
| T038 nightly publish | | | |
| T039 Mac loop | | | |
| T040 alert | | | |
| T041 prune | | | |
| T042 SC-003 | | | |
| T043 SC-006 | | | |
