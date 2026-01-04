# Feature Specification: Gated LXC Deploy (Least Privilege)

**Feature Branch**: `022-lxc-gated-deploy`  
**Created**: 2026-01-04  
**Status**: Draft  
**Input**: Create a gated, least-privilege CI/CD flow to deploy new Proxmox LXC services (baseline example: Jellyfin).

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

### User Story 1 - Plan LXC Deployment Without Changes (Priority: P1)

As an operator, I want a non-destructive “plan/preflight” stage that describes exactly what would happen (create vs update vs no-op) when deploying a new LXC service, so I can review intent safely in pull requests and before applying in any environment.

**Why this priority**: Safe, reviewable intent is the foundation for least-privilege CI/CD and prevents accidental or unsafe changes.

**Independent Test**: Can be fully tested by running the plan/preflight stage and confirming it produces a deterministic, human-readable summary and a machine-readable artifact without changing Proxmox state.

**Acceptance Scenarios**:

1. **Given** the target LXC does not exist, **When** plan/preflight runs, **Then** it reports “create” intent with the requested parameters and produces a plan artifact.
2. **Given** the target LXC exists but differs from desired state, **When** plan/preflight runs, **Then** it reports “update” intent and highlights the exact differences.
3. **Given** the target LXC exists and matches desired state, **When** plan/preflight runs, **Then** it reports “no changes” and exits successfully.
4. **Given** the requested change would require modifying shared infrastructure or could cause downtime, **When** plan/preflight runs, **Then** it fails fast with a clear reason.

---

### User Story 2 - Apply to Lab With Evidence (Priority: P2)

As an operator, I want an apply stage for LAB that can create a new unprivileged LXC service (example: Jellyfin) and converge configuration on reruns, while producing an evidence bundle that can be verified offline.

**Why this priority**: LAB is the safe proving ground. Automatic apply in LAB accelerates iteration and validates idempotency, evidence, and health checks before production.

**Independent Test**: Can be fully tested by applying to LAB twice: first run creates and configures the container; second run converges without recreating. Evidence verification must pass offline.

**Acceptance Scenarios**:

1. **Given** the LAB target has no existing LXC with the requested name/ID, **When** apply runs, **Then** a new unprivileged LXC is created and the service becomes healthy (baseline example: Jellyfin).
2. **Given** the LAB LXC already exists, **When** apply runs again, **Then** it does not recreate the LXC and converges configuration to the desired state.
3. **Given** apply completes, **When** validation runs, **Then** an evidence bundle is produced and offline verification passes.
4. **Given** apply is running, **When** it detects a required shared-infra change, **Then** it fails fast without making partial changes.

---

### User Story 3 - Apply to Production With Explicit Approval (Priority: P3)

As an operator, I want production apply to be explicitly gated so it cannot run accidentally, and when it does run it must create the new LXC service without root access and produce verifiable evidence.

**Why this priority**: Production safety requires human review and explicit intent confirmation.

**Independent Test**: Can be tested by attempting to run production apply without approvals/confirmation (must be blocked), then running with approvals/confirmation (must succeed and produce evidence).

**Acceptance Scenarios**:

1. **Given** production apply is triggered without the required manual approval, **When** the pipeline evaluates gating, **Then** it does not proceed.
2. **Given** production apply is triggered without the explicit confirmation input, **When** the pipeline evaluates gating, **Then** it does not proceed.
3. **Given** production apply is approved and explicitly confirmed, **When** it runs, **Then** it creates or converges the target LXC service and produces an evidence bundle that passes offline verification.

---

[Add more user stories as needed, each with an assigned priority]

### Edge Cases

**Definition (shared infrastructure change)**: Any change outside the single target service LXC, including Proxmox bridges, storage pools, templates, host firewall/networking, NAS/NFS mounts, and any other LXC/VM. If plan/preflight detects a shared-infra change, it MUST fail fast.

- Requested container ID is already in use by a different workload.
- Requested container name conflicts with an existing container.
- The desired template/storage/bridge is unavailable on the target host.
- The container starts but the service does not become healthy within a reasonable time.
- Network mode is misconfigured (no DHCP lease, static IP conflict).
- GPU passthrough is requested but host devices are unavailable or permissions cannot be safely configured.
- Evidence capture fails (missing permissions or missing tools); pipeline must still provide actionable failure output.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a non-destructive plan/preflight stage that reports create/update/no-op intent for a new LXC deployment.
- **FR-002**: System MUST provide an apply stage that creates the LXC if missing and converges configuration if it exists.
- **FR-003**: System MUST keep LAB and PROD deployments separated, with LAB permitted to auto-apply and PROD requiring explicit approval.
- **FR-004**: System MUST prevent production apply from running without both manual approval and an explicit confirmation input.
- **FR-005**: System MUST operate without requiring Proxmox root login; all operations must be performed using a non-root automation account with narrowly scoped elevation.
  The deploy flow MUST capture the remote effective identity and allowed elevation surface (e.g., permitted elevated operations) into the evidence bundle and MUST NOT require interactive elevation.
- **FR-006**: System MUST manage secrets via the CI secret store and must not require secrets to be committed to the repository.
- **FR-007**: System MUST be idempotent: rerunning apply MUST NOT recreate an existing container and MUST converge configuration.
- **FR-008**: System MUST capture durable evidence for each deployment attempt (success or failure) and store it in a persistent artifact location on the Proxmox host.
- **FR-009**: System MUST support offline verification of evidence bundles and fail the pipeline when verification fails.
- **FR-010**: System MUST validate service health (baseline example: Jellyfin) and include the results in the evidence bundle.
- **FR-011**: System MUST avoid downtime for existing workloads; if a requested change would require modifying shared infrastructure, it MUST fail fast.
- **FR-012**: System MUST support safe parameterization for container identity, compute/storage/network resources, optional mounts, and optional GPU passthrough (disabled by default).

### Key Entities *(include if feature involves data)*

- **Deployment Target**: The environment selected for the deploy (LAB or PROD) and its gating rules.
- **LXC Deployment Request**: Desired container name/identity and desired runtime policy (resources, network mode, optional mounts, optional GPU toggle).
- **Plan Artifact**: A versioned description of intended changes produced by plan/preflight.
- **Evidence Bundle**: The collected outputs proving what was changed and whether the service is healthy.
- **Verification Result**: The offline validation outcome for the evidence bundle.

## Success Criteria *(mandatory)*

<!--
  ACTION REQUIRED: Define measurable success criteria.
  These must be technology-agnostic and measurable.
-->

### Measurable Outcomes

- **SC-001**: Plan/preflight completes successfully on pull requests from this repository (non-fork) and on `workflow_dispatch`, and produces a plan artifact in under 2 minutes.
- **SC-002**: LAB apply completes with a verified evidence bundle (verification PASS) in under 15 minutes.
- **SC-003**: Re-running LAB apply results in “no recreate” behavior (no new container identity created) and still produces a verified evidence bundle.
- **SC-004**: Production apply cannot start without both a manual approval and explicit confirmation input (0 accidental prod applies).
- **SC-005**: 100% of deployment attempts (success or failure) produce a durable evidence bundle.

## Assumptions

- LAB is allowed to auto-apply; PROD requires manual approval.
- A non-root automation account exists on the Proxmox host and can perform required operations via narrowly-scoped elevation.
- Jellyfin is acceptable as the initial service validation target (baseline example).

## Out of Scope

- Migrating or reconfiguring existing workloads.
- Bulk provisioning of multiple services in one run.
- Changing shared networking/storage infrastructure as part of this feature.
