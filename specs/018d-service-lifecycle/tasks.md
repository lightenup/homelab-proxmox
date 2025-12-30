---
description: "Task list for 018d-service-lifecycle"
---

# Tasks: Golden Paths: Service Lifecycle

**Input**: Design documents from `specs/018d-service-lifecycle/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Phase 1: Setup (Documentation & Templates)

**Purpose**: Define the standards and templates required for the lifecycle workflows.

- [x] T001 Create golden path runbook skeleton in `docs/operations/golden-paths-service-lifecycle.md`
- [x] T002 Create service host_vars template in `docs/templates/service-host_vars.example.yml`

## Phase 2: Foundational (Runner Core Logic)

**Purpose**: Update the healthcheck runner to support the new data model (Objects, Profiles, GAP detection).

- [x] T003 Modify `scripts/healthcheck/healthcheck.py` to support `healthcheck_url` object structure
- [x] T004 Modify `scripts/healthcheck/healthcheck.py` to implement `profile: none` and `healthcheck_verification_command`
- [x] T005 Modify `scripts/healthcheck/healthcheck.py` to distinguish GAP (Socket Unreachable) from FAIL (HTTP Error)

## Phase 3: User Story 1 - Add a new service (Priority: P1)

**Goal**: Automated process to add a service with minimal duplication.

**Independent Test**: Add a "test-service" using the script and verify it appears in healthchecks.

- [x] T006 [US1] Create `scripts/add-service.sh` to automate inventory addition
- [x] T007 [P] [US1] Migrate `immich` host_vars to new schema in `ansible/host_vars/immich.yml`
- [x] T008 [P] [US1] Migrate `monitoring` host_vars to new schema in `ansible/host_vars/monitoring/vars.yml`
- [x] T009 [P] [US1] Migrate `homeassistant` and `adguard` host_vars to new schema
- [x] T010 [P] [US1] Migrate `proxmox` and `reverse_proxy` host_vars to new schema
- [x] T011 [US1] Verify `add-service.sh` functionality with a dry-run test

## Phase 4: User Story 2 - Change/upgrade a service (Priority: P1)

**Goal**: Standardized process for updates and verification.

**Independent Test**: Run verification script on an existing service.

- [x] T012 [US2] Create `scripts/change-service.sh` wrapper script
- [x] T013 [US2] Document Upgrade and Rollback procedures in `docs/operations/golden-paths-service-lifecycle.md`

## Phase 5: User Story 3 - Remove a service (Priority: P1)

**Goal**: Safe removal process without orphaned artifacts.

**Independent Test**: Remove the "test-service" added in US1.

- [x] T014 [US3] Create `scripts/remove-service.sh` to automate inventory removal
- [x] T015 [US3] Document Removal procedure in `docs/operations/golden-paths-service-lifecycle.md`

## Phase 6: User Story 4 - Standard service metadata schema (Priority: P2)

**Goal**: Enforce SSOT with strict schema validation and drift detection.

**Independent Test**: Run `--check-drift` on a modified inventory with invalid keys.

- [x] T016 [US4] Implement `validate_schema` function in `scripts/healthcheck/healthcheck.py`
- [x] T017 [US4] Implement `--check-drift` argument in `scripts/healthcheck/healthcheck.py`
- [x] T018 [US4] Add "Zombie" detection (Inventory exists, Socket fail) to `--check-drift` logic

## Phase 7: Polish

- [x] T019 Finalize `docs/operations/golden-paths-service-lifecycle.md` with all commands and workflows

## Dependencies

- US1 (Add) depends on Foundational (Runner support for new schema)
- US2 (Change) depends on US1 (Schema migration)
- US3 (Remove) depends on US1 (Schema migration)
- US4 (Drift) depends on Foundational and US1 (Migration complete)

## Parallel Execution

- T007, T008, T009, T010 (Schema Migrations) can be done in parallel.
- T012 (Verify Script) and T014 (Remove Script) can be developed in parallel.
