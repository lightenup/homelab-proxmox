# Feature Specification: Golden Paths: Service Lifecycle (Add / Change / Remove)

**Feature Branch**: `018d-service-lifecycle`
**Created**: 2025-12-30
**Status**: Draft
**Input**: User description: "018d — Golden Paths: Service Lifecycle"

## User Scenarios & Testing

### User Story 1 - Golden path: Add a new service (Priority: P1)

As an operator, I want a documented and automated process to add a service so that I provision the LXC with Terraform, Ansible deploys the service, healthchecks start covering it automatically, and optional monitoring hooks are easy to add—with minimal required fields and minimal duplicated configuration.

**Why this priority**: Adding services is a core operational task. Reducing friction and duplication ensures consistency and reduces errors.

**Independent Test**: Can be tested by adding a new "example service" (e.g., a simple web server) following the documented path.

**Acceptance Scenarios**:

1. **Given** a new service definition in Terraform and a single host_vars file, **When** I apply Terraform and run Ansible, **Then** the service is running, and healthchecks automatically detect it and report PASS.
2. **Given** a new service added without healthcheck metadata, **When** the healthcheck runner executes, **Then** it reports a GAP status until the metadata is added.
3. **Given** the process is followed, **Then** the total time to add a representative service is under 30 minutes.

---

### User Story 2 - Golden path: Change/upgrade a service (Priority: P1)

As an operator, I want a safe standard way to change versions/config so that changes are done via variables/templates, upgrade procedure is documented, and rollback is defined.

**Why this priority**: Maintenance is frequent. Standardizing upgrades reduces downtime and risk of regression.

**Independent Test**: Can be tested by bumping the version of an existing service (e.g., Immich or Monitoring) using the standard process.

**Acceptance Scenarios**:

1. **Given** a running service, **When** I update the version variable and deploy, **Then** the service updates successfully.
2. **Given** a failed update, **When** I follow the rollback procedure, **Then** the service is restored to the previous state.
3. **Given** an update is performed, **Then** post-change verification (healthcheck + smoke test) confirms service health.

---

### User Story 3 - Golden path: Remove a service (Priority: P1)

As an operator, I want a safe removal process that ensures the service is stopped, data retention is decided, healthchecks stop failing, DNS/proxy routes are cleaned up, and Terraform destroys infrastructure.

**Why this priority**: Clean removal prevents "zombie" monitoring alerts, security risks from unmaintained services, and resource wastage.

**Independent Test**: Can be tested by removing the "example service" created in US1.

**Acceptance Scenarios**:

1. **Given** a service to be removed, **When** I follow the removal process, **Then** the service is stopped, infrastructure is destroyed, and no healthcheck FAILs occur (service is removed or skipped).
2. **Given** a removal, **When** completed, **Then** there are no orphaned automation timers or proxy routes.
3. **Given** a removal, **When** prompted, **Then** I can explicitly choose between "decommission but keep data" and "full wipe".

---

### User Story 4 - Standard service metadata schema in inventory (Priority: P2)

As an operator, I need a consistent schema for declaring service intent in inventory, so automation can scale without custom per-service logic.

**Why this priority**: Enables automation (healthchecks, monitoring) to scale without code changes for every new service.

**Independent Test**: Can be tested by verifying that the healthcheck runner correctly interprets the schema for various services.

**Acceptance Scenarios**:

1. **Given** a host in the `services` group, **When** it lacks required keys, **Then** drift detection identifies it as a GAP with an actionable message.
2. **Given** a host with `healthcheck_enabled: false`, **When** checked, **Then** it reports SKIP with the provided reason.
3. **Given** the schema is defined, **Then** it is documented in a "service contract".

---

### Edge Cases

- **Zombie Services**: When a service is removed from Terraform (infrastructure destroyed) but remains in Ansible inventory, the healthcheck runner MUST report this as a **GAP** (Configuration Drift: Host Unreachable), distinct from a service FAIL.
- **Non-HTTP Services**: Services without web endpoints (e.g., background workers) MUST use `healthcheck_profile: "none"` and provide a `healthcheck_verification_command` to verify status via shell command.

## Requirements

### Functional Requirements

- **FR-001**: System MUST provide a **golden path runbook** at `docs/operations/golden-paths-service-lifecycle.md`.
- **FR-002**: System MUST provide a **service template** for host_vars at `docs/templates/service-host_vars.example.yml`.
- **FR-003**: Healthcheck drift detection MUST recognize hosts in the `services` group with missing required keys as a **GAP**.
- **FR-004**: Healthcheck drift detection MUST recognize hosts with `healthcheck_enabled: false` as **SKIP** with a reason.
- **FR-005**: System MUST provide helper scripts/commands for lifecycle steps (Add, Remove, Verify).
- **FR-006**: Healthcheck runner MUST distinguish between "Service Down" (FAIL) and "Host Unreachable" (GAP) to identify zombie inventory entries.
- **FR-007**: Drift detection (schema validation, zombie check) MUST be a separate mode/command (`--check-drift`) to avoid slowing down frequent healthchecks.
- **FR-008**: Drift detection MUST enforce **strict schema validation**, reporting warnings or errors for any unknown top-level keys in `host_vars` to prevent configuration drift.

### Non-functional Requirements

- **NFR-001**: No new "service registry" lists. Schema MUST be inventory-native (host_vars).
- **NFR-002**: All docs and templates MUST assume IaC-first (Terraform + Ansible).
- **NFR-003**: Procedures MUST be compatible with the current environment (mDNS `.local`, no new router dependency).

### Key Entities

- **Service Metadata Schema**:
    - `service_name`: String (Required)
    - `service_role`: Enum ["app", "infra", "monitoring", "proxy"] (Required)
    - `healthcheck_enabled`: Boolean (Required)
    - `healthcheck_profile`: Enum ["lan", "tailscale", "both", "none"] (Default: "lan")
    - `healthcheck_url`: Object { scheme, port, path } (Required unless profile is "none") - Strict object format for better automation parsing.
    - `healthcheck_verification_command`: String (Required if profile is "none") - Shell command to verify service status.
    - `healthcheck_expect_status`: Integer (Default: 200)
    - `healthcheck_expect_body_contains`: String (Optional)
    - `healthcheck_reason`: String (Required if disabled)
    - `expose_via_proxy`: Boolean (Optional)
    - `proxy_hostname`: String (Optional)
    - `service_data_paths`: List[String] (Optional)
    - `service_owner`: String (Optional)

## Clarifications

### Session 2025-12-30
- Q: Should `healthcheck_url` allow simple strings or require a strict object? → A: **Strict Object** - Require `{ scheme, port, path }`. Best for future automation but verbose.
- Q: How to handle services removed from Terraform but left in Inventory? → A: **Report GAP** - Detect "Host Unreachable" and report as GAP (Configuration Drift). Clear signal to clean inventory.
- Q: How to handle non-HTTP services (background workers)? → A: **Explicit "None" + Command** - Allow `profile: none` but require a `verification_command` to run via SSH/Ansible.
- Q: Should drift detection run every time or be a separate command? → A: **Separate Command** - `healthcheck.py --check-drift`. (Pros: Fast monitoring, explicit drift auditing. Cons: Drift might go unnoticed until audit).
- Q: Should the schema validation be strict or permissive? → A: **Strict Validation** - Error/Warn on unknown keys in `host_vars`. Enforces SSOT and prevents hidden config.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Adding a new service requires editing **only Terraform + one host_vars file** (no other lists).
- **SC-002**: Healthcheck automation shows **GAP** until metadata is added, then **PASS**.
- **SC-003**: Removing a service yields **no FAIL noise** and no orphaned automation artifacts.
- **SC-004**: Documentation provides copy/paste templates and concrete command sequences.
