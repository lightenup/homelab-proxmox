---
description: "Task list for LXC lifecycle workflow consolidation"
---

# Tasks: LXC Lifecycle Workflow Consolidation

**Input**: Design documents from `/specs/031-lxc-lifecycle-pipeline/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Not requested for this feature.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [X] T001 Create unified workflow scaffold in .github/workflows/lxc-lifecycle.yml (workflow_dispatch inputs for service, action, and environment)
- [X] T002 [P] Create lifecycle evidence helper script in scripts/lifecycle/terraform_plan_apply.sh

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T003 Update Taskfile.yml to add lifecycle:plan/apply/verify tasks that wrap terraform, inventory:update, and healthcheck:run
- [X] T004 Update scripts/service_lifecycle.py to accept unified actions (add/change/delete) and propagate failures from apply, inventory update, and verification
- [X] T005 [P] Create removal verification utility in scripts/lifecycle/remove_checks.py to validate removal of Terraform, tfvars, Ansible, proxy/DNS, and host_vars references (tolerate missing host_vars)

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Clean LXC Removal (Priority: P1) 🎯 MVP

**Goal**: Remove a service with full cleanup and verification so no orphaned references remain.

**Independent Test**: Remove a service and confirm no inventory, proxy/DNS, healthcheck GAP/zombie entries, or leftover data locations remain.

### Implementation for User Story 1

- [X] T006 [US1] Wire scripts/lifecycle/remove_checks.py into scripts/service_lifecycle.py and Taskfile.yml service:remove to fail on incomplete cleanup
- [X] T007 [US1] Add explicit data deletion confirmation handling in scripts/service_lifecycle.py and scripts/lifecycle/remove_checks.py (only delete mounts/directories after confirmation)
- [X] T008 [US1] Ensure removal deletes ansible/host_vars/<service>.yml when present and removes the service from ansible/playbooks/services.yml
- [X] T020 [US1] Define and document the data deletion confirmation mechanism in .github/workflows/lxc-lifecycle.yml and docs/operations.md
- [X] T021 [US1] Enforce tfvars cleanup validation for service_ips/service_mountpoints in scripts/lifecycle/remove_checks.py and document in docs/runbooks/golden-paths-service-lifecycle.md
- [X] T009 [US1] Document full removal steps and verification commands in docs/runbooks/golden-paths-service-lifecycle.md and docs/reverse-proxy.md

**Checkpoint**: User Story 1 should be fully functional and testable independently

---

## Phase 4: User Story 2 - Unified LXC Pipeline (Priority: P2)

**Goal**: Single lifecycle pipeline that handles add/change/delete with plan + apply and evidence capture.

**Independent Test**: Run the unified pipeline for a change and a removal, confirming plan/apply artifacts and destructive gating behavior.

### Implementation for User Story 2

- [X] T010 [US2] Implement plan/apply flow with artifact reuse in .github/workflows/lxc-lifecycle.yml
- [X] T011 [US2] Add destructive change detection and protected label/tag gate in .github/workflows/lxc-lifecycle.yml (maintainer-controlled)
- [X] T012 [US2] Define maintainer control for destructive labels/tags without paid features in .github/CODEOWNERS and docs/operations.md
- [X] T013 [US2] Document unified pipeline usage and inputs in docs/runbooks/golden-paths-service-lifecycle.md and docs/operations.md

**Checkpoint**: User Story 2 should be fully functional and testable independently

---

## Phase 5: User Story 3 - Resilient Failure Handling (Priority: P3)

**Goal**: Fail fast on apply/inventory/verification failures to prevent partial removals.

**Independent Test**: Induce a failure in apply or inventory update and ensure the workflow ends in failure with a retry required.

### Implementation for User Story 3

- [X] T014 [US3] Ensure .github/workflows/lxc-lifecycle.yml fails the run on apply, inventory update, or verification errors
- [X] T015 [US3] Invoke task healthcheck:run -- --check-drift within .github/workflows/lxc-lifecycle.yml and fail on GAP/zombie output
- [X] T016 [US3] Enforce inventory:update execution and failure propagation in Taskfile.yml and scripts/service_lifecycle.py
- [X] T017 [US3] Add idempotency verification step for delete runs in .github/workflows/lxc-lifecycle.yml (re-run plan after removal and require no changes)

**Checkpoint**: All user stories should now be independently functional

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [X] T018 [P] Validate and refresh specs/031-lxc-lifecycle-pipeline/quickstart.md steps to reflect final workflow
- [X] T019 [P] Add cross-cutting notes on destructive approvals and data deletion confirmation in docs/operations.md

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3+)**: All depend on Foundational phase completion
  - User stories can then proceed in parallel (if staffed)
  - Or sequentially in priority order (P1 → P2 → P3)
- **Polish (Final Phase)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P2)**: Can start after Foundational (Phase 2) - Independent of US1
- **User Story 3 (P3)**: Can start after Foundational (Phase 2) - Independent of US1/US2

### Parallel Opportunities

- T002 and T005 can run in parallel with other tasks in their phases
- Once Foundational completes, US1/US2/US3 can proceed in parallel if staffed
- Polish tasks T016 and T017 can run in parallel

---

## Parallel Example: User Story 1

```bash
Task: "Wire scripts/lifecycle/remove_checks.py into scripts/service_lifecycle.py and Taskfile.yml service:remove to fail on incomplete cleanup"
Task: "Document full removal steps and verification commands in docs/runbooks/golden-paths-service-lifecycle.md and docs/reverse-proxy.md"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Remove a service and verify no orphaned inventory/healthcheck/proxy/DNS entries

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → Deploy/Demo (MVP)
3. Add User Story 2 → Test independently → Deploy/Demo
4. Add User Story 3 → Test independently → Deploy/Demo
5. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1
   - Developer B: User Story 2
   - Developer C: User Story 3
3. Stories complete and integrate independently

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Stop at each checkpoint to validate the story independently
