# Feature Specification: Sunset Shell Tools

**Feature Branch**: `028-sunset-shell-tools`  
**Created**: 2026-01-14  
**Status**: Draft  
**Input**: User description: "Sunset as much shell code as possible; migrate service lifecycle/CI helpers/healthchecks/operator tooling; keep core harness + host-installed content + spec tooling unchanged; consolidate and simplify; create a Taskfile; deprecate/delete legacy scripts and update docs; write tests as we go for every migration."

## Clarifications

### Session 2026-01-14

- Q: Where should the “top 10 day-to-day workflows” be defined for acceptance testing? → A: Define them explicitly in this spec as a named list and treat that list as the acceptance-test scope.
- Q: What is the policy for keeping legacy script entry points during migration? → A: Use shims only where other methods of call are impractical/cumbersome (typically where CI/IaC/core harness still calls legacy paths); otherwise migrate callers to the Taskfile.
- Q: For legacy scripts being sunset, what’s the required deprecation window before deletion? → A: Deprecate by moving scripts to `scripts/deprecated/`; deprecated scripts must not be referenced by code or documentation.
- Q: What test strategy is required for each migration step? → A: Unit tests plus CLI smoke tests using fakes; nightly mutation tests (mutmut); integration tests can run in GitHub Actions against the lab environment.
- Q: Which Task runner should we standardize on for the “Taskfile” entry point? → A: Use `go-task` with `Taskfile.yml`, and ensure the introduction does not cause downstream incompatibilities.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Single Entry Point for Day-to-Day Ops (Priority: P1)

As an operator, I can run common day-to-day homelab tasks through a single, consistent entry point (tasks/commands), without relying on ad-hoc shell scripts.

**Why this priority**: This reduces operational risk, makes commands discoverable, and avoids shell-specific environment drift.

**Independent Test**: Can be tested by running a small set of representative operator tasks end-to-end in a clean working copy and verifying they produce expected, deterministic outputs and error messages.

**Acceptance Scenarios**:

1. **Given** a clean checkout, **When** an operator runs a documented day-to-day task via the single entry point, **Then** the task completes successfully and produces the same observable result as the legacy approach.
2. **Given** an invalid invocation (missing required inputs), **When** an operator runs the task, **Then** the system prints a clear error message and exits without making changes.

**Top 10 day-to-day workflows (acceptance-test scope)**:

1. Service lifecycle: add a service
2. Service lifecycle: change a service
3. Service lifecycle: remove a service (no orphaned references)
4. Inventory: regenerate/update Ansible inventory
5. Healthchecks: run a service healthcheck suite
6. IaC: terraform validate/format check
7. IaC: terraform plan (no changes applied)
8. IaC: terraform apply (explicit confirmation required)
9. Deployment: deploy/update a service (lab)
10. Reporting: render a human-readable run summary

---

### User Story 2 - Safe IaC Rebuild From Scratch (Priority: P2)

As a maintainer, I can rebuild the environment from scratch using Infrastructure-as-Code, with minimal bootstrapping steps and without needing legacy shell scripts to “fill the gaps.”

**Why this priority**: A reliable rebuild path is the strongest guarantee that day-to-day operations do not hide undeclared state.

**Independent Test**: Can be tested by executing the documented rebuild flow in an isolated lab environment (or equivalent test harness) and verifying that core services come up and health checks pass.

**Acceptance Scenarios**:

1. **Given** no pre-existing environment state, **When** the rebuild workflow is followed, **Then** the system reaches a “healthy” state with the same baseline service set as before.
2. **Given** a rebuild is interrupted mid-way, **When** the rebuild is re-run, **Then** it resumes safely and converges to the same final “healthy” state.

---

### User Story 3 - Incremental Migration With Tests (Priority: P3)

As a contributor, I can migrate one legacy script at a time into the consolidated tooling, with automated tests added for each migration so regressions are caught immediately.

**Why this priority**: The migration is high-touch and risky; test-as-you-go makes it manageable.

**Independent Test**: Can be tested by selecting one legacy script, migrating it, and demonstrating that the new behavior is covered by automated tests and that CI still passes.

**Acceptance Scenarios**:

1. **Given** a legacy script selected for migration, **When** the replacement is added, **Then** automated tests exist that validate success and failure paths.
2. **Given** a legacy script has been deprecated, **When** an operator encounters it (via documentation or by manual invocation), **Then** the operator is guided to the replacement through a clear deprecation message (and if a shim is retained for compatibility, it warns and forwards where safe).

### Edge Cases

- Partial migration where some CI/IaC jobs still invoke legacy script paths.
- Running tasks from non-interactive CI environments vs interactive operator terminals.
- Rebuild/ops tasks that depend on network availability or unreachable hosts.
- Deprecation/removal of scripts that are referenced in documentation or runbooks.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The project MUST provide a single, documented entry point for operational tasks (a Taskfile), so operators do not need to discover or run multiple shell scripts directly.
- **FR-001a**: Introducing the Taskfile MUST NOT break existing CI/IaC workflows; when a downstream caller cannot practically be updated, a shim strategy MUST be used.
- **FR-002**: Core harness workflows, host-installed automation content, and specification tooling MUST remain unchanged and supported.
- **FR-002a**: The project MUST define the protected paths that constitute “core harness / host-installed / spec tooling,” and enforce that this feature does not modify them.
- **FR-003**: Service lifecycle helpers, CI helper scripts, healthcheck wrappers, and operator/maintenance tooling MUST be sunset by migrating their behavior into consolidated tooling or moving the behavior into IaC where appropriate.
- **FR-004**: The migration MUST be incremental: each migrated capability MUST be deliverable independently without requiring the entire migration to finish.
- **FR-005**: Every migrated capability MUST include automated tests (success + failure paths) added at the time of migration.
- **FR-005a**: Automated tests MUST include unit tests and CLI smoke tests (invocation, exit codes, and key outputs) and SHOULD prefer test fakes over live dependencies.
- **FR-005b**: A nightly mutation-testing job MUST run (mutmut) to validate test strength.
- **FR-005c**: Integration tests MAY be executed in GitHub Actions using the lab environment when needed for higher confidence.
- **FR-006**: Legacy scripts selected for sunset MUST be deprecated by moving them under `scripts/deprecated/`.
- **FR-006a**: Deprecated scripts MUST NOT be referenced by repository code, CI, IaC, or documentation.
- **FR-007**: Legacy scripts approved for removal MUST be deleted from the repository once replacements are validated, and any documentation references MUST be removed.
- **FR-007**: Legacy scripts approved for removal MUST be deleted from the repository once replacements are validated, and any documentation references MUST be removed.
- **FR-007b**: “Approved for removal” MUST be explicitly recorded (so deletions are intentional and traceable).
- **FR-007a**: Legacy script shims MAY be kept only when updating the caller is impractical/cumbersome (commonly because CI/IaC/core harness references a path); shims MUST have a clear removal condition.
- **FR-008**: The “January candidate list” markdown document MUST be updated to reflect the new removal implementation and any script deletions/deprecations introduced by this effort.
- **FR-009**: Service lifecycle operations (add/change/remove) MUST remain available via the consolidated entry point and MUST keep repository state consistent (no orphaned service references after removal).
- **FR-010**: Operator-only utilities MAY remain available via the consolidated entry point, but MUST be clearly labeled as “operator-only” and excluded from critical rebuild/IaC paths.
- **FR-011**: The SNMP verification utility MUST be deprecated.
- **FR-012**: Disaster-recovery scripts MUST be treated as maintenance/operator tooling (not required for baseline rebuild correctness).
- **FR-013**: The “Tailscale OAuth test” functionality MUST be re-evaluated and moved into the setup/IaC pathway if it is required for initial provisioning.

### Acceptance Criteria (Requirements)

- **AC-001 (FR-001)**: The Taskfile exposes the “Top 10 day-to-day workflows (acceptance-test scope)” listed in this spec, and each task either succeeds or fails with a clear, actionable message.
- **AC-001a (FR-001a)**: Existing CI/IaC workflows continue to run without requiring changes solely due to Taskfile introduction.
- **AC-002 (FR-003/FR-006/FR-007)**: Each sunset legacy script is either (a) moved to `scripts/deprecated/` with a documented replacement or (b) deleted after replacement behavior and docs are verified.
- **AC-002b (FR-006a)**: No repository code, CI, IaC, or documentation references any script under `scripts/deprecated/`.
- **AC-002a (FR-007a)**: Shims exist only for legacy entry points where replacing the caller is impractical/cumbersome; each shim documents its removal condition (e.g., “remove once CI/IaC caller migrates”).
- **AC-003 (FR-005)**: For each migrated capability, automated tests validate at least one success case and one failure case.
- **AC-003a (FR-005a)**: For each migrated capability, unit tests and CLI smoke tests exist and assert exit codes and at least one key observable output.
- **AC-003b (FR-005b)**: Nightly mutation-testing runs and fails if the test suite does not detect introduced mutations above the configured threshold.
- **AC-003c (FR-005c)**: When an integration test is added, it runs in GitHub Actions and uses the lab environment without requiring manual operator steps.
- **AC-004 (FR-008)**: The January candidate list document is updated in the same change set where removals/deprecations are introduced.
- **AC-005 (FR-009)**: A “remove service” workflow leaves no orphaned references (inventory, variables, documentation links) when completed successfully.
- **AC-006 (FR-010/FR-012)**: Operator-only tasks are clearly labeled and are not required for rebuild correctness.
- **AC-007 (FR-002)**: Core harness/spec tooling continues to function without modification, and any changes in this feature do not require updating those scripts.
- **AC-007a (FR-002a)**: The protected paths are explicitly listed, and automated checks prevent modifications to those paths as part of this feature.
- **AC-008 (FR-004)**: At least one legacy capability can be migrated and delivered independently without requiring other migrations to be completed.
- **AC-009 (FR-011)**: The SNMP verification utility is marked deprecated and is no longer required for baseline rebuild correctness.
- **AC-010 (FR-013)**: The Tailscale OAuth test is either (a) moved into the setup pathway (if required) or (b) clearly documented as operator-only and not required for rebuild.

### Key Entities *(include if feature involves data)*

- **Legacy Script**: A repository script currently used for operations, CI helpers, or runbooks.
- **Task**: A named, documented operation exposed through the single entry point.
- **Migration Item**: A tracked unit of work mapping one legacy script/capability to its replacement and tests.
- **Deprecation Notice**: A user-visible message explaining that a script/task is deprecated and what replaces it.

## Assumptions

- “Sunset” means: migrate behavior into consolidated tooling or IaC, deprecate legacy entry points, update documentation, and delete legacy scripts when safe.
- The Taskfile is the primary human-facing interface; the underlying implementation can evolve as long as task behavior remains stable.
- The repository continues to maintain CI verification while the migration is in progress.
- When “delete them” applies to a legacy script set, deletion happens only after the replacement behavior is tested and documentation is updated.
- Moving a script to `scripts/deprecated/` is the project’s deprecation mechanism.
- Shims are a transitional mechanism, not a permanent compatibility guarantee.

## Protected Paths (Definition)

The following paths are treated as protected for this feature (must remain unchanged):

- `.specify/` (spec tooling)
- `scripts/lab/` (core harness scripts)
- `mkdir/` (host-installed automation content)

If additional protected paths are identified during migration, they must be added to this list and covered by the same protection checks.

## Removal Approval (Definition)

“Approved for removal” means the script is explicitly recorded as safe-to-delete (with its replacement noted) in repository documentation for this feature (so deletion is intentional, reviewable, and not accidental).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Operators can complete the “Top 10 day-to-day workflows (acceptance-test scope)” using only the single entry point, without manually invoking legacy shell scripts.
- **SC-002**: A rebuild-from-scratch run completes with all baseline health checks passing.
- **SC-003**: 100% of migrated legacy capabilities include automated tests and must pass in CI.
- **SC-003a**: Nightly mutation-testing runs succeed (or fail for actionable reasons) and are tracked as part of ongoing quality signals.
- **SC-004**: The number of “operator-invoked shell scripts” required for day-to-day operations is reduced by at least 80% versus the start of this feature.
- **SC-005**: All documentation and runbooks referenced by operators point to the consolidated entry point (no stale references to deleted scripts).
