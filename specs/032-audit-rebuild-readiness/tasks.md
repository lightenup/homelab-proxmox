---

description: "Task list for 032-audit-rebuild-readiness"
---

# Tasks: Audit Rebuild Readiness & Configuration Hygiene

**Input**: Design documents from `/specs/032-audit-rebuild-readiness/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Not requested for this feature.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish audit templates and shared artifacts

- [x] T001 Create audit methodology and classification rubric in specs/032-audit-rebuild-readiness/audit-methodology.md
- [x] T002 Create inventory template and column definitions in specs/032-audit-rebuild-readiness/inventory.md
- [x] T003 [P] Create findings log template in specs/032-audit-rebuild-readiness/findings.md
- [x] T004 [P] Create recommendations log template in specs/032-audit-rebuild-readiness/recommendations.md

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared references required by all user stories

- [x] T005 Create runtime inventory checklist for PVE/LXC/NAS in specs/032-audit-rebuild-readiness/runtime-inventory.md
- [x] T006 Run PVE runtime inventory (mounts, LXCs, mpX) and capture evidence in specs/032-audit-rebuild-readiness/runtime-inventory.md
- [x] T007 Run per-LXC mount validation (immich, jellyfin, etc.) and capture evidence in specs/032-audit-rebuild-readiness/runtime-inventory.md
- [x] T008 [P] Extract rebuild baseline steps into specs/032-audit-rebuild-readiness/rebuild-baseline.md (source: docs/operations/backups-proxmox-config-restore.md)
- [x] T009 [P] Create storage/mount taxonomy reference in specs/032-audit-rebuild-readiness/mount-taxonomy.md
- [x] T010 [P] Draft evidence catalog index in specs/032-audit-rebuild-readiness/evidence-index.md

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Produce an actionable audit report (Priority: P1) 🎯 MVP

**Goal**: Deliver an inventory-backed audit report with evidence-based classification

**Independent Test**: Review inventory and audit report to confirm all items are classified with evidence

### Implementation for User Story 1

- [x] T011 [US1] Populate repository inventory with status and evidence in specs/032-audit-rebuild-readiness/inventory.md
- [x] T012 [US1] Enumerate all environments/nodes and confirm inventory coverage in specs/032-audit-rebuild-readiness/inventory.md
- [x] T013 [US1] Record unused/unneeded/DR-only items with evidence in specs/032-audit-rebuild-readiness/findings.md
- [x] T014 [US1] Produce audit summary report with counts and highlights in specs/032-audit-rebuild-readiness/audit-report.md
- [x] T015 [US1] Prioritize remediation actions (rebuild/DR criticality) in specs/032-audit-rebuild-readiness/recommendations.md

**Checkpoint**: User Story 1 complete - audit report is independently reviewable

---

## Phase 4: User Story 2 - Rebuild readiness assessment (Priority: P2)

**Goal**: Provide a rebuild checklist and identify gaps blocking a full rebuild

**Independent Test**: Another operator can follow the checklist and identify all prerequisites and blockers

### Implementation for User Story 2

- [x] T016 [US2] Build rebuild checklist aligned to PVE+NAS restore in specs/032-audit-rebuild-readiness/rebuild-checklist.md
- [x] T017 [US2] Assess rebuild gaps and blockers and update specs/032-audit-rebuild-readiness/findings.md
- [x] T018 [US2] Document dependencies/prereqs and evidence mapping in specs/032-audit-rebuild-readiness/rebuild-readiness.md

**Checkpoint**: User Story 2 complete - rebuild readiness assessment is independently reviewable

---

## Phase 5: User Story 3 - Storage and shared mount coverage review (Priority: P3)

**Goal**: Map shared mounts and highlight automation gaps or policy conflicts

**Independent Test**: Mount coverage matrix lists all shared mounts with management status and gaps

### Implementation for User Story 3

- [x] T019 [US3] Create mount coverage matrix in specs/032-audit-rebuild-readiness/mount-coverage.md
- [x] T020 [US3] Review NFS role coverage and policy compliance; log gaps in specs/032-audit-rebuild-readiness/findings.md
- [x] T021 [US3] Validate Terraform mountpoint usage vs bind-mount policy exceptions (Immich baseline) and log conflicts in specs/032-audit-rebuild-readiness/findings.md

**Checkpoint**: User Story 3 complete - storage coverage review is independently reviewable

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final validation and consistency

- [x] T022 Cross-check success criteria and update specs/032-audit-rebuild-readiness/audit-report.md
- [x] T023 [P] Update quickstart links to audit artifacts in specs/032-audit-rebuild-readiness/quickstart.md
- [x] T024 Final consistency pass on remediation priorities in specs/032-audit-rebuild-readiness/recommendations.md

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - blocks user stories
- **User Stories (Phase 3+)**: Depend on Foundational completion; proceed in priority order (P1 → P2 → P3)
- **Polish (Phase 6)**: Depends on completion of all desired user stories

### User Story Dependencies

- **User Story 1 (P1)**: No dependencies after Foundational
- **User Story 2 (P2)**: No dependencies after Foundational
- **User Story 3 (P3)**: No dependencies after Foundational

### Parallel Opportunities

- Phase 1: T003 and T004 can run in parallel
- Phase 2: T008, T009, and T010 can run in parallel
- Phase 6: T023 can run in parallel with any non-conflicting tasks

---

## Parallel Example: User Story 1

- Task: Populate repository inventory in specs/032-audit-rebuild-readiness/inventory.md
- Task: Record unused/DR-only items in specs/032-audit-rebuild-readiness/findings.md
- Task: Produce audit summary report in specs/032-audit-rebuild-readiness/audit-report.md

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: User Story 1
4. Validate audit report independently before proceeding

### Incremental Delivery

1. Setup + Foundational
2. User Story 1 → validate
3. User Story 2 → validate
4. User Story 3 → validate
5. Polish and finalize

---

## Notes

- [P] tasks can run in parallel when they touch different files
- User story tasks must remain independently testable
- Runtime inventory requires operator access to PVE/NAS for evidence collection
