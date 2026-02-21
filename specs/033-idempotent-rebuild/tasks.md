---
description: "Task list for 033-idempotent-rebuild implementation"
---

# Tasks: Idempotent Rebuild Orchestrator

**Input**: Design documents from specs/033-idempotent-rebuild/
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Not requested for this feature.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: [ID] [P?] [Story] Description

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [X] T001 Add rebuild Taskfile targets for plan/apply entrypoints in Taskfile.yml
- [X] T002 [P] Add rebuild configuration defaults and service scope file in scripts/lab/rebuild-config.json

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

- [X] T003 Create rebuild state machine helpers in scripts/lab/lib/rebuild_state.sh (read/write artifacts/rebuild-runs/<timestamp>/state.json)
- [X] T004 [P] Add rebuild evidence root initialization in scripts/lab/lib/artifacts.sh (artifacts/rebuild-runs/<timestamp>)
- [X] T005 Implement phase flag parsing, preflight summary, and destructive confirmation gate in scripts/lab/lib/rebuild.sh
- [X] T006 Implement lab/prod guardrails with explicit prod confirmation in scripts/lab/lib/rebuild.sh
- [X] T007 Enforce plan-only default with explicit apply flag in scripts/lab/lib/rebuild.sh and Taskfile.yml

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Rebuild to a working system (Priority: P1) 🎯 MVP

**Goal**: Rebuild a fresh PVE 9 host to a working homelab system using existing IaC and service workflows.

**Independent Test**: Run a lab rebuild with plan-only then apply, and verify mounts, LXCs, and services are restored.

### Implementation for User Story 1

- [X] T008 [P] [US1] Implement host mount validation checks in scripts/lab/checks.d/rebuild-mounts.sh for /mnt/nas/homelab_immich and /mnt/nas/photo
- [X] T009 [P] [US1] Implement Immich bind-mount validation in scripts/lab/checks.d/rebuild-mounts.sh for mp0 and mp1 mappings
- [X] T010 [US1] Wire mount validation phase and evidence capture in scripts/lab/lib/rebuild.sh
- [X] T011 [US1] Implement PVE config restore phase aligned to docs/operations/backups-proxmox-config-restore.md in scripts/lab/lib/rebuild.sh
- [X] T012 [US1] Implement IaC restore phase (Terraform state + Ansible inventory) in scripts/lab/lib/rebuild.sh
- [X] T013 [US1] Implement service/LXC rebuild phase using scripts/lab/pve-service-deploy and Taskfile.yml entrypoints in scripts/lab/lib/rebuild.sh
- [X] T014 [US1] Implement verification phase for service status and record evidence in scripts/lab/lib/rebuild.sh

**Checkpoint**: User Story 1 is fully functional and testable independently

---

## Phase 4: User Story 2 - Run rebuild from macOS without GitHub Actions (Priority: P2)

**Goal**: Provide a macOS launcher that drives rebuild locally and incrementally without CI dependencies.

**Independent Test**: Run the launcher on macOS in plan-only mode and confirm it produces local evidence artifacts.

### Implementation for User Story 2

- [X] T015 [P] [US2] Create macOS launcher script in scripts/rebuild/run-rebuild.sh to call Taskfile targets with plan/apply flags
- [X] T016 [US2] Wire Taskfile.yml targets to invoke scripts/rebuild/run-rebuild.sh with environment and confirmation args
- [X] T017 [US2] Add launcher usage documentation in docs/operations/rebuild-orchestrator.md

**Checkpoint**: User Story 2 is independently functional

---

## Phase 5: User Story 3 - Evidence and verification (Priority: P3)

**Goal**: Capture evidence and verification outputs for each rebuild phase.

**Independent Test**: After a rebuild run, validate evidence bundles show pass/fail for mounts, restore, and service verification.

### Implementation for User Story 3

- [X] T018 [P] [US3] Add evidence summary generation for rebuild phases in scripts/lab/lib/evidence.sh
- [X] T019 [US3] Persist phase status updates to state.json via scripts/lab/lib/rebuild_state.sh and scripts/lab/lib/rebuild.sh
- [X] T020 [US3] Add evidence index output for mounts/restore/services in scripts/lab/lib/rebuild.sh

**Checkpoint**: User Story 3 is independently functional

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [X] T021 [P] Update quickstart usage to include launcher and evidence locations in specs/033-idempotent-rebuild/quickstart.md
- [X] T022 [P] Document rebuild guardrails and confirmations in docs/operations/backups-proxmox-config-restore.md
- [X] T023 [P] Manage NAS backup mount via Ansible proxmox_backup role in ansible/roles/proxmox_backup/tasks/prerequisites.yml

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
- **User Story 2 (P2)**: Can start after Foundational (Phase 2) - May integrate with US1 but is independently testable
- **User Story 3 (P3)**: Can start after Foundational (Phase 2) - May integrate with US1/US2 but is independently testable

### Parallel Opportunities

- T002 can run in parallel with T001
- T004 can run in parallel with T003
- T006 and T007 can run in parallel
- T013 can run in parallel with T016
- Documentation tasks (T019, T020) can run in parallel

---

## Parallel Example: User Story 1

Task: "Implement host mount validation checks in scripts/lab/checks.d/rebuild-mounts.sh"
Task: "Implement Immich bind-mount validation in scripts/lab/checks.d/rebuild-mounts.sh"

---

## Parallel Example: User Story 2

Task: "Create macOS launcher script in scripts/rebuild/run-rebuild.sh"
Task: "Add evidence summary generation for rebuild phases in scripts/lab/lib/evidence.sh"

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Run a lab rebuild and verify mounts/services with evidence
5. Deploy/demo if ready

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → Deploy/Demo (MVP)
3. Add User Story 2 → Test independently → Deploy/Demo
4. Add User Story 3 → Test independently → Deploy/Demo
5. Each story adds value without breaking previous stories
