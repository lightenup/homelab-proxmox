---
description: "Task list for DR Drill Playbook"
---

# Tasks: DR Drill Playbook

**Input**: Design documents from `/specs/030-dr-drill-playbook/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md

**Tests**: Not requested.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Phase 1: Setup (Shared Infrastructure)

- [x] T001 Create the DR drill runbook skeleton in docs/runbooks/dr-drill-playbook.md (headings for overview, prerequisites, readiness checks, download, validation, reporting)
- [x] T002 [P] Create the drill report template file in docs/runbooks/dr-drill-report-template.md (empty scaffold)

---

## Phase 2: Foundational (Blocking Prerequisites)

- [x] T003 Update scripts/dr/README.md with DR drill prerequisites, secret handling notes, and Taskfile task references

**Checkpoint**: Foundation ready - user story implementation can now begin.

---

## Phase 3: User Story 1 - Complete DR Drill Playbook (Priority: P1) 🎯 MVP

**Goal**: Provide a step-by-step runbook that downloads the full encrypted backup and validates decryption in DSM.

**Independent Test**: Follow the runbook to download the full backup to the DR share and confirm DSM Hyper Backup Explorer can browse it.

### Implementation for User Story 1

- [x] T004 [US1] Document scope, assumptions, and target paths in docs/runbooks/dr-drill-playbook.md
- [x] T005 [US1] Add Hetzner listing + download steps in docs/runbooks/dr-drill-playbook.md referencing scripts/dr/hetzner_list.sh and scripts/dr/hetzner_download.sh
- [x] T006 [US1] Specify Pool directory structure preservation and post-download verification in docs/runbooks/dr-drill-playbook.md
- [x] T007 [US1] Add DSM Hyper Backup Explorer validation steps in docs/runbooks/dr-drill-playbook.md
- [x] T008 [US1] Add verification step using scripts/dr/verify_restore.sh and evidence capture checklist in docs/runbooks/dr-drill-playbook.md

**Checkpoint**: User Story 1 is fully documented and independently executable.

---

## Phase 4: User Story 2 - Space and Readiness Validation (Priority: P2)

**Goal**: Ensure readiness checks prevent failed drills due to missing prerequisites or insufficient space.

**Independent Test**: Run the readiness section only and confirm it blocks execution when prerequisites are missing.

### Implementation for User Story 2

- [x] T009 [US2] Add readiness checklist with mount checks, write test, rclone size estimate, and 2× free-space rule in docs/runbooks/dr-drill-playbook.md
- [x] T010 [US2] Add failure/edge-case guidance (partial downloads, missing credentials, corruption warnings) in docs/runbooks/dr-drill-playbook.md

**Checkpoint**: User Story 2 readiness guidance is clear and independently usable.

---

## Phase 5: User Story 3 - Drill Reporting (Priority: P3)

**Goal**: Capture consistent drill outcomes for auditability and future comparisons.

**Independent Test**: Fill the report template after a dry-run and confirm all required fields are captured.

### Implementation for User Story 3

- [x] T011 [P] [US3] Populate the drill report template fields and outcome definitions in docs/runbooks/dr-drill-report-template.md
- [x] T012 [US3] Add reporting procedure and template usage guidance in docs/runbooks/dr-drill-playbook.md

**Checkpoint**: Reporting workflow is documented and usable independently.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [x] T013 [P] Update docs/runbooks/disaster-recovery-drill.md to reference the new runbook and report template

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3+)**: Depend on Foundational phase completion
- **Polish (Phase 6)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Starts after Foundational phase
- **User Story 2 (P2)**: Starts after Foundational phase
- **User Story 3 (P3)**: Starts after Foundational phase

### Parallel Opportunities

- Phase 1: T001 and T002 can run in parallel (different files)
- Phase 5: T011 can run in parallel with other work (separate template file)
- Phase 6: T013 can run in parallel after user stories complete (separate file)

---

## Parallel Example: User Story 1

- Task: T005 Add Hetzner listing + download steps in docs/runbooks/dr-drill-playbook.md
- Task: T007 Add DSM Hyper Backup Explorer validation steps in docs/runbooks/dr-drill-playbook.md

---

## Parallel Example: User Story 3

- Task: T011 Populate drill report template in docs/runbooks/dr-drill-report-template.md
- Task: T012 Add reporting procedure in docs/runbooks/dr-drill-playbook.md

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: User Story 1
4. Validate User Story 1 independently

### Incremental Delivery

1. Setup + Foundational
2. User Story 1 → Validate
3. User Story 2 → Validate
4. User Story 3 → Validate
5. Polish updates
