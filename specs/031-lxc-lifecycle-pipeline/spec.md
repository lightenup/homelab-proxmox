# Feature Specification: LXC Lifecycle Workflow Consolidation

**Feature Branch**: `031-lxc-lifecycle-pipeline`  
**Created**: 2026-01-18  
**Status**: Draft  
**Input**: User description: "Create a spec for improving LXC lifecycle workflows by (a) formalizing full LXC removal cleanup steps and (b) consolidating add/change/delete into a single generic LXC pipeline. Include all required changes: Removal cleanup scope (must be documented and enforced): Terraform: remove LXC module/resource from main.tf or per-service root; remove from outputs.tf ansible_inventory. TF vars: remove service IP and mountpoint entries in service_ips / service_mountpoints in prod.tfvars and lab.tfvars. Inventory: run task inventory:update (uses inventory.py). Host vars: delete ansible/host_vars/<service>.yml (task service:remove currently only strips healthcheck keys in service_lifecycle.py). Ansible: remove service from services.yml and any service-specific playbooks/roles. Proxy/DNS: remove reverse proxy routes and any docs/config references (e.g., reverse-proxy.md). Healthcheck: run task healthcheck:run -- --check-drift and ensure no GAP/zombie entries remain. Data/mounts: remove service-specific NAS mounts, bind mounts, and data directories. Generic LXC pipeline changes (single workflow for add/change/delete): One workflow that always runs plan and apply, regardless of change type. If plan contains replace/destroy, require explicit confirmation gate (reuse existing destructive guard behavior). Ensure apply uses the same plan and captures evidence. Update docs to describe the unified pipeline and removal steps (e.g., golden-paths-service-lifecycle.md). Requirements + Acceptance Criteria: Removal produces no orphaned inventory/healthchecks/proxy routes. Drift detection reports no GAP/zombie entries. Pipeline runs on a single entrypoint for all LXC changes. Destructive actions are blocked without explicit confirmation. Idempotent runs do not re-create removed services. Include edge cases: partial removal, missing host_vars, failed terraform apply, failed inventory update, and destroy confirmation not provided."

## Clarifications

### Session 2026-01-18

- Q: How should data locations be handled during removal? → A: Delete data locations only after explicit confirmation (optionally after backup).
- Q: How should destructive confirmation be enforced without GitHub Environments? → A: Require a protected branch label or tag.
- Q: Should removal succeed if verification steps fail? → A: Treat removal as failed until all verification steps pass; require retry.
- Q: Who is allowed to set the destructive confirmation label/tag? → A: Maintainers can set the destructive label/tag, and the maintainer group must be definable without paid GitHub features.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Clean LXC Removal (Priority: P1)

As an operator, I need to remove an LXC service and know that all related infrastructure, configuration, and healthcheck records are fully cleaned up so the environment has no orphaned references.

**Why this priority**: Unclear or partial removal risks drift, broken automation, and hidden dependencies that complicate future changes.

**Independent Test**: Can be fully tested by removing a single service and verifying that inventory, healthchecks, proxy routes, and data locations show no remnants.

**Acceptance Scenarios**:

1. **Given** a service exists with infrastructure, inventory, host variables, proxy routes, healthchecks, and data mounts, **When** removal is performed, **Then** all related entries are removed and verification reports no orphaned or zombie entries.
2. **Given** a service has already lost its host variable file, **When** removal is performed, **Then** the workflow completes without failure and still removes all remaining references.

---

### User Story 2 - Unified LXC Pipeline (Priority: P2)

As a maintainer, I want a single pipeline entrypoint for add/change/delete so lifecycle updates are predictable and always produce a plan, an apply, and evidence.

**Why this priority**: Multiple pipelines increase errors and make destructive actions harder to guard consistently.

**Independent Test**: Can be fully tested by running the same pipeline for a change and for a removal and verifying that plan/apply are produced with required confirmation for destructive actions.

**Acceptance Scenarios**:

1. **Given** a change that does not destroy resources, **When** the pipeline runs, **Then** it produces a plan and apply without requiring destructive confirmation.
2. **Given** a change that includes replace/destroy, **When** the pipeline runs without confirmation, **Then** apply is blocked until explicit confirmation is provided.

---

### User Story 3 - Resilient Failure Handling (Priority: P3)

As an operator, I need failures (apply, inventory update, or verification) to surface clearly and not silently leave the system in a partial state.

**Why this priority**: Partial execution is the most common source of drift and unreliable automation.

**Independent Test**: Can be fully tested by inducing a failure during apply or inventory update and verifying the run reports failure and does not mark removal complete.

**Acceptance Scenarios**:

1. **Given** a failed apply or failed inventory update, **When** the workflow completes, **Then** the run is marked failed and remediation steps are required before retry.

### Edge Cases

- Partial removal where only some references were deleted before the run.
- Missing host variables file for the service.
- Failed infrastructure apply before completion.
- Failed inventory update or inventory drift after removal.
- Destructive confirmation not provided.
- Data mounts or directories still exist after removal.

### Assumptions

- Services have a single authoritative lifecycle definition used for infrastructure and inventory generation.
- Drift/healthcheck verification is available to run during lifecycle workflows.
- Operators have access to decommission service data locations when required.
- Proxy/DNS configuration and lifecycle documentation are centrally managed and editable.

### Scope Boundaries

- **In scope**: LXC service lifecycle for add/change/delete, full removal cleanup steps, unified pipeline behavior, and documentation updates.
- **Out of scope**: Virtual machine lifecycle management, non-LXC workloads, and broader data retention policies beyond decommissioning locations.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The removal workflow MUST include removing the service’s infrastructure definition and its inventory output mapping.
- **FR-002**: The removal workflow MUST include removing service-specific configuration values for IPs and mountpoints.
- **FR-003**: The removal workflow MUST update the generated inventory and reflect the removal as a required step.
- **FR-004**: The removal workflow MUST delete service-specific host variables when present and MUST tolerate missing host variables without failing.
- **FR-005**: The removal workflow MUST remove the service from automation scope, including service lists, playbooks, and roles.
- **FR-006**: The removal workflow MUST remove reverse proxy and DNS routes plus any referenced documentation/configuration entries.
- **FR-007**: The removal workflow MUST verify drift/healthchecks and pass with no GAP or zombie entries before being considered complete.
- **FR-008**: The removal workflow MUST delete service-specific data locations (NAS mounts, bind mounts, and directories) only after explicit confirmation, optionally after backup.
- **FR-009**: A single, unified LXC lifecycle pipeline MUST handle add, change, and delete with plan and apply produced for every run.
- **FR-010**: Destructive changes (replace/destroy) MUST be blocked unless explicit confirmation is provided via a protected branch label or tag controlled by maintainers defined without paid GitHub features.
- **FR-011**: The apply step MUST use the exact plan produced in the same run and capture evidence for audit.
- **FR-012**: The unified pipeline MUST be documented, including removal steps and required verification checks.
- **FR-013**: Idempotent runs MUST not recreate removed services once deletion is complete.
- **FR-014**: Failures in apply, inventory update, or verification MUST fail the run and prevent removal from being marked complete until a retry succeeds.

### Key Entities *(include if feature involves data)*

- **Service**: A named LXC-backed service with infrastructure, configuration, and automation references.
- **LXC Instance**: The compute instance tied to a service lifecycle.
- **Inventory Entry**: The generated record used by automation to target the service.
- **Host Variables**: Service-specific configuration for automation runs.
- **Proxy/DNS Route**: External routing records tied to the service.
- **Healthcheck Record**: Status or drift tracking entries for the service.
- **Data Location**: Mounts and directories that persist service data.
- **Pipeline Run**: A lifecycle execution containing plan, apply, and evidence.
- **Destructive Confirmation**: Explicit approval required for replace/destroy actions.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of removal runs finish with zero orphaned inventory entries, proxy routes, or healthcheck GAP/zombie entries.
- **SC-002**: 100% of lifecycle runs are executed through the single unified pipeline with both plan and apply evidence captured.
- **SC-003**: 0 destructive applies occur without explicit confirmation.
- **SC-004**: Re-running a completed removal results in 0 re-created services and completes without errors.
