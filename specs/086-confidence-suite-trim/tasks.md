# Tasks: Confidence Suite Trim

**Input**: Design documents from `/specs/086-confidence-suite-trim/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/confidence-suite-paths.md, quickstart.md

**Tests**: Required. Spec FR-003 asks for a drift guard. The tests are written before the workflow edit (Constitution: Test-Driven Changes).

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

None. The repo layout, pytest and CI wiring already exist.

## Phase 2: Foundational

- [X] T001 Create the path list `scripts/ci/confidence-suite-paths.txt` with a header comment pointing to `specs/086-confidence-suite-trim`. Use one anchored ERE per line, as in research.md R2:
  - `^scripts/lab/pve-lab$`
  - `^scripts/lab/guardrails\.sh$`
  - `^scripts/lab/lib/(checks|jsonl|provenance|evidence|artifacts|sudo|cleanup|rebuild|state)\.sh$`
  - `^scripts/lab/(checks\.d|profiles\.d|contracts)/`
  - `^scripts/lab/(ci-verify\.sh|verify_evidence\.py|fetch_evidence_pack\.sh|render_failure_evidence\.sh|render_github_annotations\.sh|create_tier2_template\.sh)$`
  - `^ansible/playbooks/lab_.*\.ya?ml$`
  - `^ansible/inventories/lab/`
  - `^ansible/group_vars/(all|proxmox_hosts|lab)/`
  - `^ansible/roles/assertion_utils/`
  - `^ansible/(ansible\.cfg|requirements\.yml)$`
  - `^\.github/workflows/lxc-promote-prod\.yml$`
  - `^scripts/ci/confidence-suite-paths\.txt$`

  Data-model rule, quoted: "The cleaned list must be non-empty", and the list "must contain patterns matching the list file itself and the promote workflow".

## Phase 3: User Story 1 - A suite run takes one profile, not three (P1) 🎯 MVP

**Goal**: The confidence suite runs the safety step and then only `hypervisor-nested-workload`.

**Independent Test**: Force a promote run with `run_confidence_suite=true`. The suite job should take ≤ 10 minutes, the evidence pack should verify, and the summary should show `suite_ok=true` (quickstart §3).

- [X] T002 [P] [US1] In `scripts/lab/pve-lab` `cmd_confidence_suite`:
  - Replace the three `cmd_run --profile` blocks (bootstrap, hypervisor-control-plane, hypervisor-nested-workload) with one `cmd_run --profile hypervisor-nested-workload` block. Keep the existing log and error lines.
  - Add a short comment: that profile covers the other two; see specs/086.
  - Leave the evidence-pack setup and `cmd_safety_suite` unchanged.
- [X] T003 [US1] In `scripts/lab/pve-lab` `usage()`, change the `confidence` line to `Run Confidence Suite (Safety + nested-workload profile)`.

## Phase 4: User Story 2 - The suite runs only when its own inputs change (P1)

**Goal**: The gate decides with the path list.

**Independent Test**: The replay tests pass, and the quickstart §2 commands give the expected output.

- [X] T004 [P] [US2] Create `python/tests/workflows/test_confidence_gate_paths.py`, reusing the `_load_yaml` approach from `test_workflow_inputs.py`:
  - **Helper**: load the cleaned patterns, skipping `#` and blank lines, and compile them with Python `re`. The patterns use ERE syntax that Python also accepts. Assert the list is non-empty.
  - **Parametrized skip cases**:
    - `ansible/inventories/prod/hosts.yml`
    - `terraform/modules/lxc_service/main.tf`
    - `ansible/roles/lxc_base/tasks/main.yml`
    - `scripts/lab/pve-service-deploy`
    - `ansible/group_vars/services/vars.yml`
    - `docs/backlog/backlog.md`
  - **Parametrized run cases**:
    - `ansible/playbooks/lab_tier2_pve.yml`
    - `scripts/lab/lib/checks.sh`
    - `ansible/group_vars/all/vars.yml`
    - `ansible/roles/assertion_utils/tasks/main.yml`
    - `ansible/ansible.cfg`
    - `ansible/inventories/lab/hosts.yml`
    - `scripts/ci/confidence-suite-paths.txt`
    - `.github/workflows/lxc-promote-prod.yml`
  - **Wiring test**: the `confidence_gate` job's `decide` step `run:` text contains `scripts/ci/confidence-suite-paths.txt` and `grep -qEf`, and no longer contains `^ansible/roles/lxc_base/`.
- [X] T005 [US2] Edit `.github/workflows/lxc-promote-prod.yml` `confidence_gate` → `decide`. Replace the "Provisioning-relevant paths" block (the `grep -qE '^terraform/|…'` if/else) with the block from `contracts/confidence-suite-paths.md`:
  - Strip comments and blanks into a temporary pattern file.
  - If it's empty, `decide true "confidence-suite path list missing or empty"`.
  - Otherwise use `grep -qEf`, with the reasons "confidence-suite paths changed" / "no confidence-suite paths changed".

  Keep the force-run, no-SHA, verified-base and merge-base fallback logic unchanged (FR-004).

## Phase 5: User Story 3 - The path list can't silently drift (P2)

**Goal**: PR CI fails when the suite gains a dependency the list doesn't cover.

**Independent Test**: The closure tests pass on the current tree, and the in-test negative case shows that an uncovered path is reported.

- [X] T006 [US3] In `python/tests/workflows/test_confidence_gate_paths.py`, add closure tests (research.md R4):
  - **Bash**: parse `(?:source|bash)\s+"\$\{(LIB_DIR|SCRIPT_DIR|REPO_ROOT)\}/([^"$]+)"` in `scripts/lab/pve-lab`, `scripts/lab/guardrails.sh` and `scripts/lab/lib/rebuild.sh`. Resolve `LIB_DIR` → `scripts/lab/lib/`, `SCRIPT_DIR` → the file's dir, and `REPO_ROOT` → the repo root. Assert that each resolved path matches the list.
  - **Ansible roles**: in `ansible/playbooks/lab_*.yml`, collect `include_role`/`import_role` names (including the `ansible.builtin.` prefixed forms) that contain no dots. Assert `ansible/roles/<name>/tasks/main.yml` matches.
  - **Group vars**: walk the groups in `ansible/inventories/lab/hosts.yml` plus `all`. For each one with an existing `ansible/group_vars/<group>/` directory, assert `ansible/group_vars/<group>/vars.yml` matches.
  - Failure messages must name the uncovered path.
  - Add one negative test: feed the bash extractor a synthetic `source "${LIB_DIR}/newlib.sh"` and assert the coverage helper reports `scripts/lab/lib/newlib.sh` as uncovered.

## Phase 6: Polish & Cross-Cutting

- [X] T007 [P] In `specs/063-ci-confidence-path-gate/spec.md`, append "*(superseded by 086-confidence-suite-trim)*" to FR-002 and FR-008. Add the same pointer to the path-list section of `specs/063-ci-confidence-path-gate/contracts/confidence-gate.md`.
- [X] T008 Run `bash scripts/ci/python-tests.sh`, `.venv/bin/pre-commit run --all-files` and `bash -n scripts/lab/pve-lab`, and fix any failures.
- [X] T009 Run the quickstart §2 replay and record the result in the PR description.
- [X] T010 Commit, push branch `086-confidence-suite-trim` and open a PR. The PR body must:
  - include the before and after timings
  - note that `act` isn't available, so the workflow wasn't validated locally with `act`
  - list quickstart §3 (forced lab run) as the post-merge or pre-merge operator check

## Dependencies & Execution Order

- T001 blocks T004, T005 and T006.
- US1 (T002–T003) is independent of US2 and US3.
- In US2, T004 (the tests) comes before T005 (the workflow edit).
- US3 (T006) depends on T004's file and helper.
- Polish (T007–T010) comes last. T007 can run in parallel with anything.

## Parallel Example

```text
After T001: run T002 (pve-lab), T004 (test file) and T007 (063 notes) in parallel.
```

## Implementation Strategy

- **MVP**: US1 alone, the single-profile suite. It saves about 10 minutes per suite run with no change to gating.
- **Then**: US2 and US3 together, because the narrower list must ship with its drift guard.
- Ship everything as one PR. The changes are small and reviewed together.

## Phase 7: Convergence

- [X] T011 Trigger `Prod 1 - LXC Promote` with `ref=086-confidence-suite-trim`, `service=ntfy` and `run_confidence_suite=true`, without approving PROD apply. Confirm the `Confidence suite (best-effort)` job takes ≤ 10 min, its log shows only `Profile Selected: hypervisor-nested-workload` after the safety step, the evidence pack verifies, and `suite_ok=true`. Record the run ID and duration in PR #259, per SC-001, SC-005 and US1 Independent Test (partial)
- [X] T012 In `python/tests/workflows/test_confidence_gate_paths.py` `test_ansible_roles_are_covered`, assert that at least one role is found across `ansible/playbooks/lab_*.yml`. Also collect play-level `roles:` entries and the `name:` key anywhere inside an `include_role`/`import_role` block, not only on the next line, by walking the parsed YAML instead of scanning lines. Per FR-003 and US3/AC2 (partial)
- [X] T013 In `python/tests/workflows/test_confidence_gate_paths.py` `test_gate_is_wired_to_path_list`, assert the decide step contains the empty-list fail-safe (`[[ ! -s "${patterns}" ]]` followed by `decide true`), per FR-005 (partial)
- [X] T014 In `python/tests/workflows/test_confidence_gate_paths.py` `_BASH_FILES`, resolve `scripts/lab/lib/rebuild.sh` against base dir `scripts/lab`, because it is sourced by `pve-lab` and inherits that script's `LIB_DIR`/`SCRIPT_DIR`. Add a comment saying so. Per FR-003 and research R4 (partial)
- [X] T015 Re-run `bash scripts/ci/python-tests.sh` and `.venv/bin/pre-commit run --all-files`. Then commit and push `specs/086-confidence-suite-trim/tasks.md` (completed checkboxes plus this phase) together with the T012–T014 test changes to PR #259, per T010 and Constitution I (partial)
