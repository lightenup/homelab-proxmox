---
description: "Task list for feature implementation"
---

# Tasks: Automated Testing Refactor

**Input**: Design documents from `/specs/027-automated-testing-refactor/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/, quickstart.md

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Every task includes exact file paths

---

## Delivery Slices (4–7 independently shippable increments)

These slices are the intended shipping order while keeping workflow UX stable.

- **Slice 1 (Foundation)**: T001–T011
- **Slice 2 (Runner MVP on PVE)**: T012–T018 + T040–T044
- **Slice 3 (Evidence-first summaries + golden)**: T019–T024 + T045
- **Slice 4 (PR validation suite)**: T025–T028 + T048–T049
- **Slice 5 (Nightly deeper verification)**: T029–T032
- **Slice 6 (Workflow UX contract + optional toggle + docs)**: T033–T038

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the Python testable surface + minimal tooling without changing workflow UX.

- [X] T001 Create Python package skeleton in src/homelab_proxmox_orchestrator/ (__init__.py, cli.py, orchestrator.py, exec.py, models.py)
- [X] T002 Add Python test deps in python/requirements-test.txt (pytest) and python/requirements-nightly.txt (mutmut, molecule, molecule-plugins[docker])
- [X] T003 Add pytest configuration in python/pytest.ini (set PYTHONPATH=python/src, testpaths=python/tests)
- [X] T004 [P] Add Python artifact ignores in .gitignore (.pytest_cache/, __pycache__/, .mutmut-cache/, .molecule/)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared building blocks for runner + summaries + tests.

**⚠️ CRITICAL**: No user story work should start until these foundations exist.

- [X] T005 [P] Implement core data classes in src/homelab_proxmox_orchestrator/models.py (AutomationRun, EvidencePointer, RunSummary, RunResponse)
- [X] T006 [P] Implement bounded output helpers in src/homelab_proxmox_orchestrator/bounds.py (truncate lines/bytes, redact obvious secrets patterns)
- [X] T007 [P] Add unit tests for bounds in tests/orchestrator/test_bounds.py
- [X] T008 Implement evidence pack helpers in src/homelab_proxmox_orchestrator/evidence.py (resolve pack paths, load JSON safely, validate required files)
- [X] T009 [P] Add evidence helper tests in tests/orchestrator/test_evidence.py using scripts/lab/fixtures/evidence-packs/valid
- [X] T010 Implement subprocess execution wrapper in src/homelab_proxmox_orchestrator/exec.py (run command, capture rc/stdout/stderr bounded)
- [X] T011 [P] Add exec wrapper tests in tests/orchestrator/test_exec.py using tiny fixture scripts under tests/orchestrator/fixtures/

**Checkpoint**: `pytest` passes and foundational modules are importable via `PYTHONPATH=python/src`.

---

## Phase 3: User Story 1 - Deterministic Automation Entry Point (Priority: P1) 🎯 MVP

**Goal**: Provide a single Python entry point that can run plan/apply for a service/environment while preserving existing bash entrypoints (initially wrapping them).

**Independent Test**: Run the Python runner against a fake underlying deploy script and confirm (a) expected exit codes, (b) bounded JSON output matching the conceptual contract, (c) evidence pointers are present.

### Tests for User Story 1

- [X] T012 [P] [US1] Add CLI parsing tests in tests/orchestrator/test_cli.py
- [X] T013 [P] [US1] Add fake deploy script fixture tests/orchestrator/fixtures/fake_pve_service_deploy.sh that writes a minimal evidence pack to a temp evidence root
- [X] T014 [P] [US1] Add runner integration tests in tests/orchestrator/test_runner_plan_apply.py (calls CLI with --runner-script-path to fixture)

### Implementation for User Story 1

- [X] T015 [US1] Implement CLI in src/homelab_proxmox_orchestrator/cli.py (args: action plan|apply, --environment, --service, --source-ref, --evidence-root, --runner-script-path)
- [X] T016 [US1] Implement orchestration logic in src/homelab_proxmox_orchestrator/orchestrator.py (runner executes on PVE) to invoke scripts/lab/pve-service-deploy (default) or injected script path (for tests)
- [X] T017 [US1] Implement fail-fast prerequisite checks in src/homelab_proxmox_orchestrator/orchestrator.py (missing script, invalid env/service, non-writable evidence root)
- [X] T018 [US1] Emit RunResponse JSON to stdout from src/homelab_proxmox_orchestrator/cli.py (bounded fields + evidence pointers)

### Plan/apply provenance & mismatch handling (FR-009)

- [X] T040 [US1] Define and persist provenance fields in evidence for each run (src/homelab_proxmox_orchestrator/provenance.py; write into <evidence_pack>/provenance.json): environment, service, action, source_ref, started_at/finished_at
- [X] T041 [US1] For plan runs, write a plan identity record (src/homelab_proxmox_orchestrator/plan_identity.py; write into <evidence_pack>/reports/plan/plan-identity.json) including: plan_run_id, plan_created_at, optional planfile hash (if available)
- [X] T042 [US1] Add CLI flags in src/homelab_proxmox_orchestrator/cli.py: --from-plan-run-id and --require-source-ref-match (default true for prod)
- [X] T043 [US1] Enforce apply provenance association in src/homelab_proxmox_orchestrator/orchestrator.py: if --from-plan-run-id set, verify referenced plan identity exists and matches (service/environment/source_ref) or fail with bounded remediation guidance
- [X] T044 [P] [US1] Add mismatch tests in tests/orchestrator/test_provenance_mismatch.py (unknown plan id, wrong service/env/source_ref, missing identity file)

**Checkpoint**: `python3 -m homelab_proxmox_orchestrator.cli plan --environment lab --service ntfy --runner-script-path python/tests/orchestrator/fixtures/fake_pve_service_deploy.sh` works locally and tests pass.

---

## Phase 4: User Story 2 - Evidence-First Summaries With Golden Coverage (Priority: P1)

**Goal**: Deterministic, bounded operator-facing summaries derived from evidence packs, with golden tests.

**Independent Test**: Generate markdown summary from fixture evidence packs and compare to golden expected outputs.

### Tests for User Story 2

- [X] T019 [P] [US2] Create golden expected markdown in tests/orchestrator/golden/ for at least one pack under scripts/lab/fixtures/evidence-packs/valid
- [X] T020 [P] [US2] Add golden tests in tests/orchestrator/test_summary_golden.py (markdown output matches golden files)

### Implementation for User Story 2

- [X] T021 [US2] Implement markdown renderer in src/homelab_proxmox_orchestrator/summary_markdown.py (input: plan-ui-summary.json object; output: bounded markdown)
- [X] T022 [US2] Implement evidence-derived summary loader in src/homelab_proxmox_orchestrator/summary_from_evidence.py (find plan-ui-summary.json, validate with existing schema expectations)
- [X] T023 [US2] Add CLI command in src/homelab_proxmox_orchestrator/cli.py: `summary --evidence-pack <path>` (prints markdown)
- [X] T024 [US2] Update scripts/lab/render_github_summary.sh to delegate rendering to `python3 -m homelab_proxmox_orchestrator.cli summary --evidence-pack ...` (keep existing CLI contract stable)

**Checkpoint**: Golden tests fail on unintended changes and the rendered summary remains bounded.

---

## Phase 5: User Story 3 - PR Validation Suite That Catches Regressions Early (Priority: P2)

**Goal**: Fast PR CI checks (<10 minutes typical) covering Python unit+golden tests and baseline IaC checks.

**Independent Test**: Open a PR with a known failing change (e.g., break a golden output) and confirm CI fails with actionable output.

- [X] T025 [P] [US3] Add Terraform validation script scripts/ci/terraform-validate.sh (terraform fmt -check -recursive terraform/; terraform -chdir=terraform init -backend=false; terraform -chdir=terraform validate)
- [X] T026 [P] [US3] Add Python test runner script scripts/ci/python-tests.sh (PYTHONPATH=python/src python3 -m pytest -c python/pytest.ini)
- [X] T027 [US3] Add PR workflow .github/workflows/ci.yml to run: scripts/lab/ci-validate-iac.sh, scripts/lab/ci-verify.sh fixtures/evidence-packs/valid, scripts/ci/terraform-validate.sh, scripts/ci/python-tests.sh
- [X] T028 [US3] Add pip caching + pinned Python version in .github/workflows/ci.yml to keep runtime predictable

### Coverage metric (SC-003)

- [X] T048 [P] [US3] Add coverage tooling to python/requirements-test.txt (pytest-cov) and configure python/pytest.ini to report coverage for python/src/homelab_proxmox_orchestrator/
- [X] T049 [US3] Enforce SC-003 in .github/workflows/ci.yml by failing if coverage for orchestrator decision logic is <80% (scope limited to src/homelab_proxmox_orchestrator/orchestrator.py and summary/evidence parsing modules)

**Checkpoint**: PR workflow is green on main; fails on deliberate regressions.

---

## Phase 6: User Story 4 - Nightly Deeper Verification (Priority: P2)

**Goal**: Nightly deeper checks (mutation testing + Molecule) to catch subtler logic/role regressions.

**Independent Test**: Manually dispatch the nightly workflow and confirm it uploads artifacts and reports a clear overall status.

- [X] T029 [P] [US4] Add mutmut configuration in python/mutmut.ini (paths-to-mutate=python/src/homelab_proxmox_orchestrator; test-command=python3 -m pytest -c python/pytest.ini)
- [X] T030 [P] [US4] Add Molecule scenario files for a service role in ansible/roles/<role>/molecule/default/{molecule.yml,converge.yml,verify.yml}
- [X] T031 [US4] Add nightly workflow .github/workflows/nightly-deeper-verification.yml (schedule + workflow_dispatch) running: mutmut + molecule test
- [X] T032 [US4] Upload nightly artifacts (mutmut results, molecule logs) in .github/workflows/nightly-deeper-verification.yml

**Checkpoint**: Nightly runs succeed on main and provide actionable artifacts on failure.

---

## Phase 7: User Story 5 - Incremental Migration Without Workflow UX Changes (Priority: P3)

**Goal**: Keep workflow inputs/outputs stable while swapping internals incrementally.

**Independent Test**: Validate workflow dispatch inputs remain unchanged and that a LAB workflow run still produces the same evidence pack semantics.

- [X] T033 [P] [US5] Add workflow input contract test in tests/workflows/test_workflow_inputs.py asserting workflow_dispatch input keys/types for .github/workflows/lxc-deploy-lab.yml and .github/workflows/lxc-apply-prod.yml
- [X] T034 [US5] Add optional internal runner toggle in .github/workflows/lxc-deploy-lab.yml (behind env var) to call python runner on PVE while keeping workflow_dispatch inputs identical
- [X] T035 [US5] Document real-LAB validation steps in docs/operations/lxc-deploy-ci.md (how to confirm evidence packs + bounded summary with no secrets)

**Checkpoint**: Workflow UX is unchanged; internal invocation can migrate safely behind a toggle.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Hardening, documentation, and completeness checks.

- [X] T036 [P] Update quickstart with exact commands and CI pointers in specs/027-automated-testing-refactor/quickstart.md
- [X] T037 [P] Add repository-wide documentation note about new runner entrypoint in README.md
- [X] T038 Run act validation for edited workflows and document the commands used in specs/027-automated-testing-refactor/tasks.md
  - `act -l`
  - `act workflow_dispatch -W .github/workflows/lxc-deploy-lab.yml -j plan --dryrun -e /tmp/act-lxc-deploy-lab.json`
  - `act workflow_dispatch -W .github/workflows/lxc-apply-prod.yml -j apply_prod --dryrun -e /tmp/act-lxc-apply-prod.json`
- [X] T039 Review all tasks against FR-001 through FR-013 to ensure requirement coverage remains accurate after implementation

### Dependency hardening (uv)

- [X] T050 Add reproducible, hashed Python lockfiles under python/ (python/requirements-test.lock.txt, python/requirements-nightly.lock.txt) generated via uv
- [X] T051 Update CI workflows to install Python deps via uv + lockfiles (.github/workflows/ci.yml, .github/workflows/nightly-deeper-verification.yml)
- [X] T052 Add helper to regenerate lockfiles (scripts/ci/uv-lock.sh) and document in quickstart

## Dependencies & Execution Order

### User Story Completion Order

- **Setup + Foundational** → blocks all stories
- **US1 (P1)** and **US2 (P1)** can proceed after Foundational
- **US3 (P2)** depends on US1/US2 existing (to run their tests in CI)
- **US4 (P2)** depends on US3 baseline tests (mutmut uses pytest runner; Molecule uses repo state)
- **US5 (P3)** can be last (wiring/toggle + contract tests)

### Parallel Opportunities (examples)

- Setup: T004 can run in parallel with T001–T003
- Foundational: T005–T007 can run in parallel
- US1: T012–T014 can run in parallel
- US2: T019–T020 can run in parallel
- US3: T025–T026 can run in parallel
- US4: T029–T030 can run in parallel

---

## Parallel Example: User Story 1

- Task: T012 [US1] Add CLI parsing tests in tests/orchestrator/test_cli.py
- Task: T013 [US1] Add fake deploy script fixture tests/orchestrator/fixtures/fake_pve_service_deploy.sh
- Task: T014 [US1] Add runner integration tests in tests/orchestrator/test_runner_plan_apply.py

---

## Parallel Example: User Story 2

- Task: T019 [US2] Create golden expected markdown in tests/orchestrator/golden/
- Task: T020 [US2] Add golden tests in tests/orchestrator/test_summary_golden.py

---

## Functional Requirements Mapping

| FR | Description | Tasks |
|----|-------------|-------|
| FR-001 | Single automation entry point (plan/apply) | T015–T018 |
| FR-002 | Stable inputs (service, env, optional source ref) | T015, T040 |
| FR-003 | Bounded summary + evidence pointers | T006–T007, T018, T021–T024 |
| FR-004 | Preserve evidence pack model | T008–T009, T022, T040–T041 |
| FR-005 | Plan semantics remain planning-only | T016, T041 (plan identity), T043 (apply must reference plan when required) |
| FR-006 | Workflow UX unchanged | T033–T035, T038 |
| FR-007 | Separate evidence phases (plan/apply/verify distinguishable) | T005, T040–T041 (phase fields), T022 |
| FR-008 | Fail fast on missing prerequisites with remediation | T017, T043 |
| FR-009 | Apply associated with intended plan/source ref; detect mismatches | T041–T044 |
| FR-010 | PR validation suite | T025–T028 |
| FR-011 | Scheduled deeper verification suite | T029–T032 |
| FR-012 | Incremental, independently shippable slices | Delivery slices section + Phase checkpoints |
| FR-013 | No secrets in summaries/logs | T006–T007, T035 |
