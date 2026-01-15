# Tasks: Sunset Shell Tools

**Input**: Design documents from `specs/028-sunset-shell-tools/`

**Prerequisites**: [plan.md](plan.md) (required), [spec.md](spec.md) (required), [research.md](research.md), [data-model.md](data-model.md), [contracts/task-interface.md](contracts/task-interface.md), [quickstart.md](quickstart.md)

**Tests**: REQUIRED. Every migrated capability includes unit tests + CLI smoke tests (fakes preferred). Nightly mutation testing uses `mutmut`. Lab-backed integration tests may be added in GitHub Actions for rebuild-critical flows.

## Phase 1: Setup (project initialization)

- [X] T001 Create `Taskfile.yml` defining task namespaces and placeholders for the Top 10 workflows in Taskfile.yml
- [X] T002 [P] Add operator docs for installing/using `task` in README.md and docs/operations/ (e.g., README.md, docs/operations/golden-paths-service-lifecycle.md)
- [X] T003 Add a Taskfile contract test that asserts required task names exist in python/tests/tasks/test_taskfile_contract.py

---

## Phase 2: Foundational (blocking prerequisites)

- [X] T004 Add guardrail test to forbid references to `scripts/deprecated/` across the repo (docs/ansible/terraform/.github/scripts/python) in python/tests/guardrails/test_no_deprecated_refs.py (exclude scripts/deprecated itself)
- [X] T005 Update CI to run guardrail tests (ensure python tests run in .github/workflows/ci.yml)
- [X] T006 Document shim rules + deprecation policy + “approved for removal” definition in docs/operations/tooling-sunsetting.md
- [X] T006a Add CI guardrail to block changes under protected paths (`.specify/`, `scripts/lab/`, `mkdir/`) unless explicitly exempted in the guardrail configuration

**Checkpoint**: Guardrails in CI; safe to deprecate scripts.

---

## Phase 3: User Story 1 - Single Entry Point for Day-to-Day Ops (Priority: P1)

**Goal**: Operators can run the Top 10 day-to-day workflows via `task ...`.

**Independent Test**: Run `task -l` and confirm required tasks exist; run smoke tests in `python/tests/` that validate exit codes and key outputs for each Top 10 task.

### Tests (write first)

- [X] T007 [P] [US1] Add CLI smoke-test harness helpers (fake subprocess runner, temp workspace, env injection) in python/tests/task_smoke/helpers.py
- [X] T008 [P] [US1] Add smoke tests for Top 10 tasks (exit codes + key output assertions) in python/tests/task_smoke/test_top10_tasks.py

### Implementation

- [X] T009 [US1] Implement task `service:add` in Taskfile.yml and route to Python entrypoint in python/src/homelab_proxmox_orchestrator/ops_cli.py
- [X] T010 [US1] Implement task `service:change` in Taskfile.yml and route to python/src/homelab_proxmox_orchestrator/ops_cli.py
- [X] T011 [US1] Implement task `service:remove` in Taskfile.yml and route to python/src/homelab_proxmox_orchestrator/ops_cli.py
- [X] T012 [US1] Implement task `inventory:update` in Taskfile.yml and route to python/src/homelab_proxmox_orchestrator/ops_cli.py
- [X] T013 [US1] Implement task `healthcheck:run` in Taskfile.yml and route to python/src/homelab_proxmox_orchestrator/ops_cli.py
- [X] T014 [US1] Implement task `terraform:validate` in Taskfile.yml and route to python/src/homelab_proxmox_orchestrator/ops_cli.py
- [X] T015 [US1] Implement task `terraform:plan` in Taskfile.yml and route to python/src/homelab_proxmox_orchestrator/ops_cli.py
- [X] T016 [US1] Implement task `terraform:apply` with explicit confirmation in Taskfile.yml and python/src/homelab_proxmox_orchestrator/ops_cli.py
- [X] T017 [US1] Implement task `deploy:lab` in Taskfile.yml and route to python/src/homelab_proxmox_orchestrator/ops_cli.py
- [X] T018 [US1] Implement task `summary:render` in Taskfile.yml and route to existing summary logic via python/src/homelab_proxmox_orchestrator/cli.py

### Docs updates (remove legacy entrypoints)

- [X] T019 [US1] Update service lifecycle docs to use `task` instead of shell scripts in docs/operations/golden-paths-service-lifecycle.md
- [X] T020 [US1] Update healthcheck docs to use `task healthcheck:run` in docs/operations/healthchecks.md

---

## Phase 4: User Story 2 - Safe IaC Rebuild From Scratch (Priority: P2)

**Goal**: Rebuild-critical workflows are explicit and can be validated without depending on operator-only scripts.

**Independent Test**: Identify rebuild-critical tasks in Taskfile and run their smoke tests locally; optionally validate in GitHub Actions lab integration job.

- [X] T021 [US2] Label tasks as rebuild-critical vs operator-only in Taskfile.yml (comments and naming convention)
- [X] T022 [US2] Add documentation describing rebuild-critical path vs operator-only tasks in docs/operations/operations.md
- [X] T023 [US2] Add lab-backed integration workflow skeleton for rebuild-critical flows in .github/workflows/lab-integration-tests.yml

---

## Phase 5: User Story 3 - Incremental Migration With Tests (Priority: P3)

**Goal**: Migrate legacy scripts incrementally into Python, keeping shims only where impractical/cumbersome, and deprecate by moving scripts into `scripts/deprecated/` with zero references.

**Independent Test**: For each migrated script: unit tests + smoke tests pass; callers either use `task` or (if required) a shim remains at the original path.

### Migrate high-caller scripts (keep path-stable shims when required)

- [X] T024 [US3] Add unit tests for inventory generation behavior in python/tests/inventory/test_inventory_update.py
- [X] T025 [US3] Implement inventory generation in python/src/homelab_proxmox_orchestrator/inventory.py and make scripts/update_ansible_inventory.sh a thin shim (if still required by callers)

- [X] T026 [US3] Add unit tests for tfstate backup behavior in python/tests/terraform/test_backup_tfstate.py
- [X] T027 [US3] Implement tfstate backup in python/src/homelab_proxmox_orchestrator/terraform_backup.py and make scripts/backup_tfstate.sh a thin shim (if still required by callers)


- [X] T028 [US3] Add tests covering healthcheck invocation contract in python/tests/healthcheck/test_healthcheck_run.py
- [X] T029 [US3] Rework scripts/healthcheck/run.sh to be a stable shim (Ansible caller) that delegates to Python (scripts/healthcheck/healthcheck.py and/or python/src/homelab_proxmox_orchestrator/healthcheck.py)

### Deprecate legacy operator-only scripts (move + remove references)

 - [X] T030 [US3] Replace docs references to service lifecycle scripts with `task` in docs/operations/golden-paths-service-lifecycle.md then move scripts/add-service.sh to scripts/deprecated/add-service.sh
 - [X] T031 [US3] Replace docs references to service lifecycle scripts with `task` in docs/operations/golden-paths-service-lifecycle.md then move scripts/change-service.sh to scripts/deprecated/change-service.sh
 - [X] T032 [US3] Replace docs references to service lifecycle scripts with `task` in docs/operations/golden-paths-service-lifecycle.md then move scripts/remove-service.sh to scripts/deprecated/remove-service.sh


- [X] T033 [US3] Deprecate SNMP verification utility by removing doc references and moving scripts/monitoring/verify-snmpv3.sh to scripts/deprecated/verify-snmpv3.sh
- [X] T034 [US3] Remove SNMP verify references from docs/operations/monitoring/automation.md and docs/operations/monitoring/quickstart.md

- [X] T035 [US3] Classify DR scripts as maintenance/operator-only and document task entrypoints in docs/runbooks/disaster-recovery-drill.md

- [X] T036 [US3] Re-evaluate tailscale OAuth test: either move logic into IaC/setup docs or mark operator-only; update docs and task entrypoint in Taskfile.yml and scripts/tailscale/test_api_access.sh

### January candidate list update


- [X] T037 [US3] Update the January automation candidate list with “remove service” approach and removals/deprecations in specs/candidate/january.md

### Nightly mutation testing scope


- [X] T038 [US3] Update mutation testing scope to include newly migrated modules in python/mutmut.ini

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T039 [P] Remove stale references to deleted/deprecated scripts across README.md and docs/ (grep + fix)
- [X] T040 Confirm guardrail enforcement catches `scripts/deprecated/` references (python/tests/guardrails/test_no_deprecated_refs.py)
- [X] T041 Remove shims when callers have migrated and document removal conditions in scripts/ (shim headers) and docs/operations/tooling-sunsetting.md
- [X] T042 Record (per deprecated script) whether it is “approved for removal” or “deprecated-only,” and delete any scripts explicitly approved for removal once replacements + docs are verified

---

## Dependencies & Execution Order

- Phase 1 (Setup) → Phase 2 (Foundational) is required before story work.
- US1 depends on Phase 2.
- US2 depends on US1 task surface.
- US3 can start after Phase 2, but deprecations require docs updates + guardrails.

## Parallel Execution Examples

- **US1**: T007 and T008 can run in parallel.
- **US3**: Inventory (T024–T025) and tfstate backup (T026–T027) can run in parallel.

## Implementation Strategy

- MVP scope: Phase 1 + Phase 2 + US1.
- Then: US3 migrations (highest-caller scripts first) with tests written as each migration lands.
- Then: US2 lab-backed integration checks for rebuild-critical tasks.
