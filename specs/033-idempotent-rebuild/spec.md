# Feature Specification: Idempotent Rebuild Orchestrator

**Feature Branch**: `033-idempotent-rebuild`
**Created**: 2026-02-05
**Status**: Draft
**Input**: User description: "Create a dedicated, idempotent rebuild system/script for PVE 9 to full homelab restore with NAS mounts, PVE config restore, LXC/service reinstall, and data repopulation; runnable from macOS without GitHub Actions; reuse existing repo workflows and reference 032-audit-rebuild-readiness."

## Clarifications

### Session 2026-02-05

- Q: What is the target scope for rebuild execution? → A: Lab by default; prod allowed with explicit confirmation flag.
- Q: What should the rebuild driver be? → A: Use Taskfile entrypoints + scripts/lab orchestration with a thin macOS launcher script.
- Q: How should plan/apply be handled? → A: Plan-only by default; apply requires explicit flag.
- Q: Where should evidence be stored? → A: Store evidence locally under artifacts/rebuild-runs/<timestamp> on the laptop.
- Q: How should destructive actions be handled? → A: Require preflight summary + explicit confirmation string before destructive or replace/destroy actions.
- Q: How should incremental execution be organized? → A: Use a single rebuild script with phase flags and a simple state machine to track progress.
- Q: What should the state machine storage be? → A: Store a local JSON state file at artifacts/rebuild-runs/<timestamp>/state.json.

## User Scenarios & Testing *(mandatory)*

<!--
  IMPORTANT: User stories should be PRIORITIZED as user journeys ordered by importance.
  Each user story/journey must be INDEPENDENTLY TESTABLE - meaning if you implement just ONE of them,
  you should still have a viable MVP (Minimum Viable Product) that delivers value.

  Assign priorities (P1, P2, P3, etc.) to each story, where P1 is the most critical.
  Think of each story as a standalone slice of functionality that can be:
  - Developed independently
  - Tested independently
  - Deployed independently
  - Demonstrated to users independently
-->

### User Story 1 - Rebuild to a working system (Priority: P1)

As the operator, I want a rebuild system that takes a fresh PVE 9 install to a working homelab system, so I can recover from host loss with minimal manual steps.

**Why this priority**: Restoring service availability after host failure is the most critical operational capability.

**Independent Test**: Can be tested by running the rebuild on a lab PVE 9 host and verifying services are up with required mounts and data restored.

**Acceptance Scenarios**:

1. **Given** a fresh PVE 9 host and NAS backups, **When** the rebuild is executed, **Then** required mounts exist, LXC configurations are restored, and services start successfully.
2. **Given** a partially rebuilt system, **When** the rebuild is re-run, **Then** no destructive changes occur and the system remains stable.

---

### User Story 2 - Run rebuild from macOS without GitHub Actions (Priority: P2)

As the operator, I want to run the rebuild from a developer laptop (macOS) without GitHub Actions, so I can execute recovery locally and incrementally in lab.

**Why this priority**: Rebuild must not rely on CI/CD availability and must support iterative lab testing.

**Independent Test**: Can be tested by running the rebuild from macOS and producing evidence artifacts without CI dependencies.

**Acceptance Scenarios**:

1. **Given** a macOS laptop with access to PVE and NAS, **When** the rebuild is run, **Then** all steps execute locally and produce evidence.

---

### User Story 3 - Evidence and verification (Priority: P3)

As the operator, I want evidence and verification outputs for each rebuild step, so I can confirm correctness and track gaps without guessing.

**Why this priority**: Rebuild confidence depends on evidence and clear verification signals.

**Independent Test**: Can be tested by verifying that each rebuild phase produces a recorded outcome and validation result.

**Acceptance Scenarios**:

1. **Given** a rebuild run, **When** it completes, **Then** evidence artifacts show mount validation, config restore status, and service verification results.

---

[Add more user stories as needed, each with an assigned priority]

### Edge Cases

- NAS is reachable but required exports are missing or read-only.
- Backup archive exists but is missing IaC artifacts.
- Rebuild is executed against a running system and must be non-destructive.
- Network config restore breaks connectivity mid-run.

## Requirements *(mandatory)*

<!--
  ACTION REQUIRED: The content in this section represents placeholders.
  Fill them out with the right functional requirements.
-->

### Functional Requirements

- **FR-001**: The rebuild system MUST run from a macOS laptop without GitHub Actions dependencies.
- **FR-002**: The rebuild system MUST be idempotent and safe to run multiple times on an existing system.
- **FR-003**: The rebuild system MUST use the PVE restore runbook as the source of truth for configuration restore steps.
- **FR-004**: The rebuild system MUST mount and validate `/mnt/nas/homelab_immich` and `/mnt/nas/photo` on the PVE host.
- **FR-005**: The rebuild system MUST ensure Immich bind mounts are configured (`mp0` to `/mnt/immich`, `mp1` to `/mnt/immich-external/photo`).
- **FR-006**: The rebuild system MUST reinstall/recreate LXCs and services using existing Terraform/Ansible/scripts without inventing new workflows.
- **FR-007**: The rebuild system MUST restore IaC artifacts (Terraform state, Ansible inventory) when available in backups and validate drift.
- **FR-008**: The rebuild system MUST capture evidence for each rebuild phase (mounts, restore, service verification).
- **FR-009**: The rebuild system MUST default to lab execution and require explicit confirmation to target production, with safeguards to avoid unintended production changes.
- **FR-012**: The rebuild system MUST use Taskfile entrypoints and existing scripts/lab orchestration, with a thin macOS launcher (no new parallel workflow).
- **FR-013**: The rebuild system MUST run in plan-only mode by default and require an explicit apply flag to make changes.
- **FR-014**: The rebuild system MUST store evidence locally under artifacts/rebuild-runs/<timestamp> on the operator laptop.
- **FR-015**: The rebuild system MUST require a preflight summary and explicit confirmation string before destructive or replace/destroy actions.
- **FR-016**: The rebuild system MUST provide phase flags and a simple state machine to track execution progress across runs.
- **FR-017**: The rebuild system MUST store state in a local JSON file at artifacts/rebuild-runs/<timestamp>/state.json.
- **FR-010**: The rebuild system MUST allow incremental addition of missing parts without disrupting a running system.

### Key Entities *(include if feature involves data)*

- **Rebuild Run**: A single execution of the rebuild system with inputs, outputs, and evidence.
- **Mount Requirement**: A required host or LXC mount with validation status.
- **Restore Artifact**: Backup contents used for configuration or data restoration.
- **Service Restore Step**: A step that re-creates or verifies an LXC/service.
- **Evidence Bundle**: Collected outputs that prove completion and correctness.

## Success Criteria *(mandatory)*

<!--
  ACTION REQUIRED: Define measurable success criteria.
  These must be technology-agnostic and measurable.
-->

### Measurable Outcomes

- **SC-001**: A full rebuild from fresh PVE 9 reaches a working system in under 1 working day.
- **SC-002**: 100% of required mounts are validated during rebuild (including `/mnt/nas/homelab_immich` and `/mnt/nas/photo`).
- **SC-003**: Rebuild re-run produces zero destructive changes on an already rebuilt lab system.
- **SC-004**: 100% of rebuild phases emit evidence artifacts with pass/fail status.

## Assumptions

- PVE 9 is installed and reachable before rebuild begins.
- NAS exports are available and accessible from PVE.
- Existing Terraform/Ansible workflows remain the source of configuration changes.

## Risks (from 032-audit-rebuild-readiness)

- Host mount for `/mnt/nas/photo` is used by Immich but is not clearly managed by Ansible; rebuild could miss this mount.
- `proxmox_mounts` role exists but may not be wired into host playbooks, risking incomplete host mount automation.
- Terraform examples include host-path bind mounts for shared media outside Immich baseline; requires explicit policy handling.
