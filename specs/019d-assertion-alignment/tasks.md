---
description: "Task list for feature 019d-assertion-alignment"
---

# Tasks: Assertion Alignment

**Input**: Design documents from `specs/019d-assertion-alignment/`
**Prerequisites**: plan.md, spec.md, data-model.md, quickstart.md

**Tests**: Tests are included as part of the harness integration (US3) and manual verification steps.

**Organization**: Tasks are grouped by user story, with foundational setup first.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create reusable Ansible components for reporting.

- [x] T001 Create `ansible/roles/assertion_utils/tasks/generate_report.yml` to write JSON reports
- [x] T002 [P] Create `ansible/roles/assertion_utils/defaults/main.yml` with default empty assertion list

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Ensure Harness passes necessary context to Ansible.

- [x] T003 Update `scripts/lab/test-harness.sh` to pass `evidence_dir`, `run_id`, `profile_id`, `phase` as extra vars to Ansible

## Phase 3: User Story 1 & 2 - Bootstrap Assertions (Priority: P1)

**Goal**: Refactor bootstrap validations to new assertion style and enable reporting.

**Independent Test**: Run `lab_bootstrap.yml`. Verify `reports/assertions.bootstrap.json` is created and contains NET-001/NET-002 results.

- [x] T004 [US1] Refactor NET-001 (DNS resolution) in `ansible/playbooks/lab_bootstrap.yml` to use `block/assert/always` pattern
- [x] T005 [US1] Refactor NET-002 (Internet connectivity) in `ansible/playbooks/lab_bootstrap.yml` to use `block/assert/always` pattern
- [x] T006 [US2] Add `include_role: assertion_utils` task to `ansible/playbooks/lab_bootstrap.yml` to generate `assertions.bootstrap.json`

## Phase 4: User Story 1 & 2 - Tier 2 Assertions (Priority: P1)

**Goal**: Refactor Tier 2 PVE validations to new assertion style and enable reporting.

**Independent Test**: Run `lab_tier2_pve.yml`. Verify `reports/assertions.tier2.json` is created and contains PVE/GUARD results.

- [x] T007 [P] [US1] Refactor PVE-001 (Packages installed) in `ansible/playbooks/lab_tier2_pve.yml`
- [x] T008 [P] [US1] Refactor PVE-002 (Services running) in `ansible/playbooks/lab_tier2_pve.yml`
- [x] T009 [P] [US1] Refactor PVE-003 (pmxcfs mounted) in `ansible/playbooks/lab_tier2_pve.yml`
- [x] T010 [P] [US1] Refactor PVE-004 (API reachable) in `ansible/playbooks/lab_tier2_pve.yml`
- [x] T011 [P] [US1] Refactor PVE-005 (Version check) in `ansible/playbooks/lab_tier2_pve.yml`
- [x] T012 [P] [US1] Implement GUARD-001 (Inventory safety) in `ansible/playbooks/lab_tier2_pve.yml`
- [x] T013 [P] [US1] Implement GUARD-002 (Hostname safety) in `ansible/playbooks/lab_tier2_pve.yml`
- [x] T014 [US2] Add `include_role: assertion_utils` task to `ansible/playbooks/lab_tier2_pve.yml` to generate `assertions.tier2.json`

## Phase 5: User Story 3 - Integrated Evidence Pack (Priority: P2)

**Goal**: Harness ingests assertion reports into the main `checks.json`.

**Independent Test**: Run full suite. Verify `checks.json` contains Ansible checks with correct `source` and `evidence_refs`.

- [x] T015 [US3] Update `scripts/lab/test-harness.sh` to ingest `reports/assertions.*.json` files
- [x] T016 [US3] Update `scripts/lab/test-harness.sh` to merge assertion results into `checks.json` with `source: ansible`
- [x] T017 [US3] Add validation in harness to flag ERROR if assertion reports are missing or malformed

## Phase 6: Polish & Verification

- [x] T018 Verify all assertion messages follow the style guide (Check ID, Remediation)
- [x] T019 Run full regression suite `pve-lab suite hypervisor-nested-workload` and validate Evidence Pack structure
- [x] T020 Create implementation report with failure analysis

