# Feature Specification: Proxmox Token Privilege Separation

**Feature Branch**: `036-token-privilege-separation`
**Created**: 2026-02-22
**Status**: Draft
**Input**: User description: "Proxmox token privilege separation"

## Overview

The homelab currently has two Proxmox API tokens (`terraform@pve!terraform-token` and `root@pam!rebuild`) with no formal privilege-separation policy. CI workflows cannot deploy new services that require host-path bind mounts or LXC feature flags because the least-privilege token lacks root@pam authority — which Proxmox enforces at the API level and cannot be overridden by custom roles.

The orchestrator (`pve-service-deploy`) already handles post-create operations (feature flags via `pct set -features` and bind mounts via `pct set -mpN`) using host-level `sudo`, but the bind-mount logic is **hardcoded per service** (Jellyfin, Immich). New services like Nextcloud cannot be deployed through CI without adding more hardcoded blocks.

This feature formalises a three-tier privilege model, generalises the existing per-service bind-mount logic into a data-driven mechanism that reads mount definitions from the service manifest (tfvars), and codifies the policy so every future service follows the same pattern without ad-hoc workarounds.

### Three-Tier Privilege Model

| Tier | Credential / Grant | Scope | Used By |
|------|-------------------|-------|---------|
| **Tier 1** — Least-Privilege API | `terraform@pve!terraform-token` | Container lifecycle (create, resize, start/stop), network, rootfs, SSH keys. Cannot set `features` or host-path `mountpoint` entries — Proxmox API rejects these without `root@pam`. | Terraform (CI and laptop). |
| **Tier 2** — Host-Level Sudo | `ci` user with passwordless `sudo pct` on the PVE host | Post-create configuration: `pct set -features`, `pct set -mpN` for bind mounts, `pct reboot`. Limited to `pct` subcommands only; no shell escalation. | Orchestrator post-create step (CI and laptop). |
| **Tier 3** — Break-Glass | `root@pam!rebuild` API token | Full Proxmox API access. Disaster recovery, manual repairs. | Manual operator action only. Never referenced in CI workflows or automated scripts. |

**Invariants:**
- Tier 1 is the only credential passed to Terraform.
- Tier 2 is exercised only by the orchestrator post-create step, running locally on the PVE host.
- Tier 3 is never used in any automated flow. Its existence is documented for DR procedures only.

## Clarifications

### Session 2026-02-22

- Q: What data format should the orchestrator consume for host-path bind-mount definitions? → A: Reuse existing `service_mountpoints` tfvars structure (`{ mp, volume }` per mount), reinterpreting `volume` as host path when it starts with `/`. Extend the object type with `readonly = optional(bool)`. No new manifest format.
- Q: What should the CI (GitHub Actions) step summary include for bind-mount operations? → A: Structured summary listing each mount applied (host path → container path, permission, result) plus overall success/failure status, written to `$GITHUB_STEP_SUMMARY`.
- Q: Should terminal output display which privilege tier is active at each deployment phase? → A: Yes, emit tier labels at phase boundaries (e.g., `[Tier 1] Terraform apply`, `[Tier 2] Applying bind mounts via pct set`).
- Q: What should actionable error messages contain when the post-create step fails? → A: Error message + cause + suggested remediation action (e.g., "Host path /mnt/nas/nextcloud does not exist — create directory or verify NAS mount status").
- Q: Should there be a user story for an operator adding a new service that needs bind mounts? → A: Yes, P3 user story covering discovery of required mounts, configuration in tfvars, and validation via deploy.
- Q: What per-mount result states should the step summary (FR-017) report? → A: Three states: `applied` (mount newly set), `skipped` (mount already exists — no change), `failed` (operation failed; details per FR-018).
- Q: Should the step summary include all configured mounts or only those with actions? → A: All configured mounts with their result state, giving operators a complete at-a-glance verification view per service.
- Q: When a container reboot is required (FR-011), should the step summary include the container state transition? → A: Yes, include a summary line showing the stop → apply → start lifecycle so operators know when a service was temporarily unavailable.

## User Scenarios & Testing

### User Story 1 — CI Deploys a Service Requiring Host-Path Bind Mounts (Priority: P1)

As a homelab operator running a CI pipeline, I want the automated deployment to create a container and attach host-path bind mounts (e.g., NAS storage) without requiring a root@pam API token, so that the CI path remains least-privilege while still supporting services like Nextcloud that need NAS access.

**Why this priority**: This is the core capability gap. Without it, any service needing NAS bind mounts is blocked in CI or requires escalating the CI token to full root — violating the constitution's "No root@pam tokens in normal path" rule (Spec 023).

**Independent Test**: Deploy the Nextcloud service end-to-end through the CI pipeline. The container must be created with the least-privilege token, and the NAS bind mount must be present and functional after the orchestrator post-create step completes.

**Acceptance Scenarios**:

1. **Given** a service definition that includes a host-path bind mount (e.g., `/mnt/nas/nextcloud`), **When** the CI pipeline runs the Terraform apply step, **Then** the Terraform plan and apply succeed using only the `terraform@pve` token and contain zero `mountpoint` blocks with host-path volumes.
2. **Given** a container has been created by Terraform without bind mounts, **When** the orchestrator post-create step runs, **Then** the bind mount is applied via `pct set` and the container's configuration shows the correct `mp<N>` entry.
3. **Given** the orchestrator has applied a bind mount, **When** the container is started and the service is running, **Then** the mounted path inside the container is accessible by the service with the permissions (read-only or read-write) specified in the manifest.
4. **Given** the orchestrator post-create step runs, **When** it completes, **Then** an evidence artifact is produced containing before-and-after `pct config` output showing the bind mount was added.

---

### User Story 2 — Existing Services Are Not Disrupted (Priority: P1)

As a homelab operator, I want the privilege-separation changes to leave existing deployed services (Immich, Jellyfin, etc.) completely unaffected, so that introducing the new pattern carries zero risk of breaking running workloads.

**Why this priority**: Equal to P1 because regression on live services is unacceptable. The change must be additive only.

**Independent Test**: Run `terraform plan` against the existing estate after the change. No existing container should show planned modifications to `mountpoint` or `features` attributes.

**Acceptance Scenarios**:

1. **Given** existing LXC containers that already have bind mounts set via the rebuild orchestrator, **When** `terraform plan` is run after the module changes, **Then** no changes are proposed for those containers' `mountpoint` or `features` attributes (verified by `lifecycle { ignore_changes }`).
2. **Given** an existing service without bind mounts (e.g., AdGuard), **When** `terraform plan` is run, **Then** no changes are proposed at all for that container.

---

### User Story 3 — Laptop Deploy Has Parity with CI (Priority: P1)

As a homelab operator running deployments from my laptop, I want the same two-phase deploy flow (Terraform + orchestrator post-create) to work identically from my laptop and from CI, so that neither path has capabilities the other lacks.

**Why this priority**: The constitution mandates dual-provisioning parity (Principle IV). This is non-negotiable.

**Independent Test**: Deploy a test service with bind mounts from the laptop using the same `pve-service-deploy` script and arguments that CI uses. The result must be identical.

**Acceptance Scenarios**:

1. **Given** the operator runs `pve-service-deploy` for a service with bind mounts from their laptop, **When** the script completes, **Then** the container has the bind mounts and feature flags applied, with the same evidence artifacts as a CI run.
2. **Given** a CI workflow run and a laptop run targeting the same service, **When** both complete, **Then** the resulting container configuration is identical (same mounts, same features, same network).

---

### User Story 4 — Bind-Mount Path Allowlist Enforcement (Priority: P2)

As a homelab operator, I want the orchestrator to refuse to apply bind mounts whose host paths are outside an explicit allowlist, so that a misconfiguration cannot accidentally expose arbitrary host directories into a container.

**Why this priority**: Security guardrail. Important but secondary to the core deployment flow — the existing `enforce_bind_mount_policy()` already covers Terraform-stage validation, and this extends it to the orchestrator stage.

**Independent Test**: Attempt to deploy a service whose manifest specifies a bind mount with a host path outside `/mnt/nas/`. The orchestrator must reject the operation with a clear error.

**Acceptance Scenarios**:

1. **Given** a service manifest that declares a bind mount with host path `/mnt/nas/nextcloud`, **When** the orchestrator processes it, **Then** the mount is applied (path is on the allowlist).
2. **Given** a service manifest that declares a bind mount with host path `/etc/shadow`, **When** the orchestrator processes it, **Then** the operation is rejected with an error naming the disallowed path, and no `pct set` command is executed.
3. **Given** the allowlist is defined as paths starting with `/mnt/nas/`, **When** a bind mount path is `/mnt/nasty-trick`, **Then** it is rejected (prefix match must be exact directory boundary).

---

### User Story 5 — Documented Token Tier Policy (Priority: P2)

As a homelab operator (or future contributor), I want a clear, documented policy explaining which token tier to use for which operations, so that I never accidentally escalate privileges or use the wrong token for a task.

**Why this priority**: Governance and knowledge management. Without documentation, the pattern will erode over time or be misapplied.

**Independent Test**: Review the constitution and operations documentation. The three-tier model must be described, with clear rules for when each tier is used.

**Acceptance Scenarios**:

1. **Given** a new contributor reads the constitution, **When** they look for guidance on Proxmox API tokens, **Then** they find a section describing Tier 1, Tier 2, and Tier 3 with their scopes and usage rules.
2. **Given** the operations documentation, **When** a reader searches for "token" or "privilege," **Then** they find references to the three-tier model and the rationale for each tier.
3. **Given** the constitution's token tier policy, **When** compared to the actual CI workflow and orchestrator script, **Then** the implementation matches the documented policy (Tier 1 for Terraform, Tier 2 for orchestrator `pct set`, Tier 3 never in automated flows).

---

### User Story 6 — CI Guardrail Rejects root@pam in Terraform (Priority: P2)

As a homelab operator, I want the CI validation step to continue rejecting any reference to `root@pam` in Terraform files, so that the least-privilege boundary cannot be accidentally bypassed by a code change.

**Why this priority**: Existing guardrail (`ci-validate-iac.sh`) already does this. This story ensures it remains intact and is tested as part of this feature.

**Independent Test**: Add a deliberate `root@pam` reference to a Terraform file and run the CI validation script. It must fail.

**Acceptance Scenarios**:

1. **Given** a Terraform file containing `pm_api_token_id = "root@pam!rebuild"`, **When** `ci-validate-iac.sh` runs, **Then** it exits with a non-zero code and outputs a message identifying the violation.
2. **Given** Terraform files that use only `terraform@pve!terraform-token`, **When** `ci-validate-iac.sh` runs, **Then** it exits with code 0 (pass).

---

### User Story 7 — Operator Onboards a New Service Requiring Bind Mounts (Priority: P3)

As a homelab operator adding a new service (e.g., a future media or storage service), I want a clear workflow to discover what bind mounts the service needs, declare them in tfvars, and validate that the deploy pipeline applies them correctly, so that I can onboard new services without reading orchestrator internals or reverse-engineering existing examples.

**Why this priority**: Operational usability. The mechanism (US-1) is P1, but the onboarding experience is a quality-of-life concern — an operator who cannot figure out how to configure mounts will work around the system.

**Independent Test**: Follow only the service lifecycle documentation to add a test service with one NAS bind mount. The operator must not need to read orchestrator source code to determine the required tfvars format.

**Acceptance Scenarios**:

1. **Given** an operator wants to add a new service with NAS bind mounts, **When** they consult the service lifecycle documentation (golden paths), **Then** they find a step-by-step checklist that includes: (a) how to determine what mounts the service needs, (b) how to declare them in `service_mountpoints` in the tfvars file, and (c) how to verify the mounts were applied after deploy.
2. **Given** an operator has added a `service_mountpoints` entry for a new service, **When** they run the deploy pipeline, **Then** the step summary (CI) or terminal output (laptop) confirms which bind mounts were applied, or reports actionable errors if any mount failed.
3. **Given** the existing tfvars examples (`prod.tfvars.example`, `lab.tfvars.example`), **When** an operator reads them, **Then** at least one service entry demonstrates the bind-mount declaration pattern including the `readonly` attribute.

---

### Edge Cases

- **Container reboot timing**: If bind mounts are added while the container is running, a reboot may be required. The orchestrator must handle this gracefully (stop → apply → start) and document the reboot in evidence.
- **Partial failure during post-create**: If one of multiple bind mounts fails to apply (e.g., host path doesn't exist), the orchestrator must report which mount failed, apply the remaining mounts, and exit with a non-zero code.
- **Duplicate mounts**: If a bind mount already exists on the container (e.g., from a previous run), the orchestrator must detect this and skip re-application rather than erroring or creating duplicates.
- **Empty mountpoint list**: If a service has no bind mounts, the orchestrator post-create step should complete with a no-op (log "no bind mounts to apply") rather than failing.
- **Mount index collision**: When applying `mp<N>`, the orchestrator must check which indices are already in use and pick the next available one, not assume `mp0`.

## Requirements

### Functional Requirements

- **FR-001**: The orchestrator (`pve-service-deploy`) MUST apply host-path bind mounts to an LXC container via `pct set` after Terraform creates the container. *(Traces to US-1)*
- **FR-002**: The orchestrator MUST produce an evidence artifact (before/after container configuration) for each bind mount operation. *(Traces to US-1, AC-1.4)*
- **FR-003**: The Terraform LXC module MUST NOT produce `mountpoint {}` blocks containing host-path volumes (volumes whose value starts with `/`). The dynamic `mountpoint {}` block MAY remain in the module for storage-backed volumes (e.g., `local-lvm:`), but no service tfvars may pass host-path values through it. *(Traces to US-1, AC-1.1)*
- **FR-004**: Existing containers' `mountpoint` and `features` attributes MUST NOT be modified by Terraform plan/apply after this change (`lifecycle { ignore_changes }` must remain in effect). *(Traces to US-2)*
- **FR-005**: The orchestrator MUST validate all bind-mount host paths against a configurable allowlist before executing any `pct set` command. *(Traces to US-4)*
- **FR-006**: The orchestrator MUST reject bind-mount host paths outside the allowlist with a clear error message and must not execute the `pct set` command for rejected paths. *(Traces to US-4, AC-4.2)*
- **FR-007**: The bind-mount path allowlist MUST enforce exact directory-boundary prefix matching (e.g., `/mnt/nas/` matches `/mnt/nas/nextcloud` but NOT `/mnt/nasty-trick`). *(Traces to US-4, AC-4.3)*
- **FR-008**: The orchestrator MUST read mountpoint definitions from the existing `service_mountpoints` tfvars variable — not from hardcoded values in the script. Host-path bind mounts are identified as entries whose `volume` value starts with `/` (as opposed to storage-backed volumes like `local-lvm:`). The data shape per mount object is: `{ mp = string, volume = string, readonly = optional(bool) }`, where `mp` is the container-side mount path, `volume` is the host-side path, and `readonly` defaults to `false`. *(Traces to US-1, US-3, US-7)*
- **FR-009**: The `pve-service-deploy` script MUST function identically when invoked from CI and from a developer laptop with the same arguments. *(Traces to US-3)*
- **FR-010**: The CI validation script (`ci-validate-iac.sh`) MUST continue to reject any `root@pam` reference in Terraform files. *(Traces to US-6)*
- **FR-011**: The orchestrator MUST handle container reboot gracefully when bind mounts are applied to a running container (stop → apply → start). *(Edge case: reboot timing)*
- **FR-012**: The orchestrator MUST detect already-existing bind mounts on a container and skip re-application (idempotent operation). *(Edge case: duplicate mounts)*
- **FR-013**: The orchestrator MUST select the next available `mp<N>` index when applying bind mounts, accounting for indices already in use. *(Edge case: mount index collision)*
- **FR-014**: The constitution MUST be updated with the three-tier token privilege model. *(Traces to US-5)*
- **FR-015**: Operations documentation MUST be updated to reference the three-tier model. *(Traces to US-5)*
- **FR-016**: The existing `pct set -features` handling (Tier 2 feature-flag application, e.g., `mount=nfs,nesting=1`) MUST remain functionally unchanged. It is already generic (applied to any container with a CTID) and does not require generalisation. *(Traces to US-2)*
- **FR-017**: The orchestrator MUST produce a human-readable step summary at the end of the post-create phase listing ALL configured bind mounts for the service (host path, container path, permission, result state) plus overall success/failure status. Each mount entry MUST report one of three result states: `applied` (mount newly configured), `skipped` (mount already exists — idempotent no-op), or `failed` (operation failed — cause and remediation per FR-018). The summary MUST include every configured mount regardless of outcome, not only those where an action occurred. When a container reboot was performed (per FR-011), the summary MUST include a line indicating the container state transition (stopped → mounts applied → started). In CI, this summary MUST be written to `$GITHUB_STEP_SUMMARY`. On a developer laptop, the same content MUST be printed to the terminal. *(Traces to US-1, US-3, US-7)*
- **FR-018**: When the orchestrator post-create step fails, the error output MUST include: (a) the specific operation that failed, (b) the root cause, and (c) a suggested remediation action. Examples: "Host path /mnt/nas/nextcloud does not exist — create the directory on PVE or verify NAS mount status"; "Bind mount rejected — path /etc/shadow is outside the allowlist (/mnt/nas/); review service_mountpoints in tfvars." *(Traces to US-1, US-3, US-4)*
- **FR-019**: The orchestrator MUST emit progress output indicating which privilege tier is active at each deployment phase. At minimum: a label before the Terraform plan/apply phase identifying Tier 1 (e.g., `[Tier 1] Creating container via Terraform...`) and a label before the post-create phase identifying Tier 2 (e.g., `[Tier 2] Applying bind mounts via pct set...`). *(Traces to US-1, US-3)*
- **FR-020**: The service lifecycle documentation (golden paths) MUST include a step-by-step checklist for adding bind mounts to a new service, covering: (a) how to determine what host paths the service needs, (b) how to declare mounts in `service_mountpoints` in the tfvars file (with a worked example), and (c) how to verify mounts were applied after deploy. *(Traces to US-7)*
- **FR-021**: The tfvars example files (`prod.tfvars.example`, `lab.tfvars.example`) MUST include at least one service entry that demonstrates the bind-mount declaration pattern, including the `readonly` attribute. *(Traces to US-7)*

### Key Entities

- **Token Tier**: A classification (Tier 1, 2, or 3) defining the privilege scope and permitted operations for a Proxmox access credential or host-level grant. See the Three-Tier Privilege Model table in the Overview for the full definition.
- **Bind Mount**: A host-path volume mount (e.g., `/mnt/nas/nextcloud`) mapped into a container at a specified mount point, with configurable read-only or read-write permission.
- **Service Manifest**: The `service_mountpoints` tfvars variable. Each service key maps to a named set of mount objects (`{ mp = string, volume = string, readonly = optional(bool) }`). Host-path bind mounts are entries whose `volume` starts with `/`; these are consumed exclusively by the orchestrator post-create step and never passed to Terraform's `mountpoint {}` block.
- **Evidence Artifact**: A file capturing before-and-after state (e.g., `pct config` output) to prove a privileged operation was performed correctly.
- **Allowlist**: A set of approved host-path prefixes (currently `/mnt/nas/`) against which all bind-mount paths are validated.

## Success Criteria

### Measurable Outcomes

- **SC-001**: A service requiring host-path bind mounts (e.g., Nextcloud) can be deployed end-to-end through the CI pipeline without any root@pam API token in the workflow, and the bind mount is functional inside the container.
- **SC-002**: After the changes are applied, running a plan against all existing services produces zero proposed changes to `mountpoint` or `features` attributes — confirming no regression.
- **SC-003**: The same deploy command and arguments produce identical container configurations when run from CI and from a developer laptop.
- **SC-004**: An attempt to apply a bind mount outside the allowlist is rejected 100% of the time, with a human-readable error message identifying the disallowed path.
- **SC-005**: Every bind-mount operation produces an evidence artifact containing before-and-after container configuration, verifiable by inspection.
- **SC-006**: The three-tier token policy is documented in the constitution and referenced in operations docs, findable by searching for "token" or "privilege."
- **SC-007**: The CI validation script rejects `root@pam` references in Terraform files with a non-zero exit code, passing when only `terraform@pve` is used.
- **SC-008**: Every bind-mount operation in CI produces a GitHub Actions step summary listing each mount (host path, container path, permission, result). Every bind-mount operation from a laptop produces equivalent terminal output. An operator can determine what happened without reading log files.
- **SC-009**: When a post-create operation fails (e.g., host path missing, allowlist violation), the error output names the failing mount, states the cause, and suggests a remediation — verifiable by inspection of the error text.
- **SC-010**: Running the deploy pipeline twice for the same service and mount configuration produces a step summary where all previously applied mounts show result state `skipped`, confirming idempotent behaviour is visible to the operator without inspecting evidence artifacts.

## Assumptions

- **A-001**: The `ci` user on the PVE host already has passwordless sudo access for `pct` commands. No new sudoers entries are needed.
- **A-002**: The `lifecycle { ignore_changes = [features, mountpoint] }` directive is already present in the `lxc_service` Terraform module and will not be removed.
- **A-003**: The existing `enforce_bind_mount_policy()` function in `pve-service-deploy` can be extended (or a sibling function created) to cover orchestrator-stage validation, not just Terraform-plan-stage validation.
- **A-004**: The Telmate Proxmox Terraform provider is the active provider and will remain so (no migration to bpg provider is in scope).
- **A-005**: Terraform state remains local on the PVE host; no remote state backend is introduced.
- **A-006**: The bind-mount allowlist prefix is `/mnt/nas/`. This is the only approved prefix unless the allowlist is explicitly expanded in a future spec.
- **A-007**: The `root@pam!rebuild` token continues to exist for break-glass disaster recovery but is never referenced in CI workflows or automated scripts.

## Non-Functional Requirements

- **NFR-001**: The orchestrator post-create step (bind mount + feature flags) MUST complete within 60 seconds per container under normal conditions (single PVE host, local network).
- **NFR-002**: The orchestrator MUST be idempotent — running it twice on the same container with the same manifest MUST produce the same end state without errors or duplicated mounts.
- **NFR-003**: Failure in the orchestrator post-create step MUST NOT destroy or corrupt the container. The container must remain in a recoverable state (exists but degraded — missing bind mounts).

## Out of Scope

- **Migration to the bpg Proxmox Terraform provider** — the Telmate provider remains in use per constitution.
- **Storage-backend-only approach (Pattern C)** — Spec 023 advocated this; this feature explicitly extends Pattern B (two-phase split-privilege) instead.
- **Creating new Proxmox API tokens** — no new tokens are introduced; the existing two tokens are retained with formalised usage rules.
- **Remote Terraform state** — state remains local on PVE.
- **Sudoers changes on the PVE host** — the existing `ci` user grant already covers `pct set`.
- **Automating Tier 3 (break-glass) operations** — `root@pam!rebuild` remains manual-only.
- **Rotating existing tokens** — rotation procedure will be documented, but actual rotation is not performed as part of this feature.
- **ACME account management or VM args restrictions** — these are also root@pam-only operations at the Proxmox API level but are not needed by any current service.

## Decision Log

| # | Ambiguity | Decision | Rationale |
|---|-----------|----------|-----------|
| D-001 | Should the feature introduce a new dedicated token or reuse existing ones? | Reuse existing tokens. No new tokens created. | The reference document explicitly states "No new Proxmox tokens are created." The two existing tokens (`terraform@pve` and `root@pam!rebuild`) cover all necessary tiers. Adding a third would increase operational complexity without clear benefit. |
| D-002 | Should mountpoint definitions be read from a new manifest format or from existing tfvars? | Read from existing tfvars / service manifest (same source as today). | Minimises change surface. The orchestrator already reads service configuration; extending it to consume mountpoint data avoids introducing a parallel config format. |
| D-003 | How should the allowlist be configured — hardcoded, config file, or environment variable? | Configurable via the existing bind-mount policy guard mechanism (currently allowlist in the script). | The existing `enforce_bind_mount_policy()` already defines the `/mnt/nas/` prefix. Extending the same mechanism keeps configuration co-located and avoids a new config surface. |
| D-004 | Should the orchestrator remove bind mounts that are no longer in the manifest (convergent behaviour)? | No. The orchestrator only adds mounts; it does not remove existing ones. | Removal is destructive and risks data loss. Removing mounts should be a deliberate manual operation, not an automated side-effect. This aligns with the "no destructive automation without clear barriers" CI/CD expectation in the constitution. |
| D-005 | Which prefix matching strategy for the allowlist — simple string startswith or directory-boundary aware? | Directory-boundary aware (trailing `/` required). `/mnt/nas/` matches `/mnt/nas/foo` but not `/mnt/nasty`. | Prevents path-traversal tricks. The reference document's bind-mount policy guard already uses this approach. |
| D-006 | Should the Terraform `mountpoint {}` block be entirely removed or gated behind a flag? | Keep the dynamic `mountpoint {}` block for storage-backed volumes but ensure host-path entries do not produce Terraform `mountpoint {}` blocks. Host-path entries MAY exist in `service_mountpoints` (single source of truth — see D-010) but Terraform must filter them out or the plan-stage guard (`enforce_bind_mount_policy()`) must reject any plan that includes them. The orchestrator post-create step is the exclusive consumer of host-path entries. | Full removal of the block would also prevent future storage-backed mountpoints. Since the existing plan-stage policy guard prevents abuse, the block can stay. Host-path bind mounts (the security concern) never reach Terraform apply — they travel through the orchestrator only. |
| D-007 | What evidence artifact format should be used for bind mounts? | Same format as existing `lxc-features.txt`: before/after `pct config` output in a text file named `lxc-bind-mounts.txt`. | Follows established evidence patterns in the orchestrator. Consistency reduces cognitive load for reviewers. |
| D-008 | Should bind mounts be read-write or read-only by default? | Read-write by default; individual mounts MAY specify `ro=1` in the manifest. The permission attribute (ro/rw) is per-mount, declared in the same data source as the host path and container mount point. | Matches existing convention: Jellyfin uses `ro=1` (media consumption), Immich uses read-write (photo storage). The manifest must carry this per-mount. |
| D-009 | Are Nextcloud's specific bind mount paths defined yet? | No. The current `prod.tfvars.example` and `lab.tfvars.example` do not include a `nextcloud` entry under `service_mountpoints`. The generic mechanism must be built; the specific Nextcloud mount configuration (e.g., `/mnt/nas/nextcloud` → `/mnt/nextcloud`) will be defined during implementation based on the Nextcloud service requirements from Spec 034. | Separating "build the generic mechanism" (this spec) from "configure the specific mount" (implementation detail) avoids blocking the spec on a single service's config. |
| D-010 | Should the orchestrator consume a new manifest format or reuse existing `service_mountpoints` tfvars? | Reuse existing `service_mountpoints`. Host-path mounts are identified by `volume` starting with `/`. Add `readonly = optional(bool)` to the object type. | Minimises change surface (per D-002). The orchestrator already reads service configuration from tfvars. A parallel format would require operators to maintain two config sources. The existing `{ mp, volume }` structure maps naturally to `pct set -mp<N> <volume>,mp=<mp>`. |
| D-011 | What should the CI step summary contain for bind-mount operations? | Structured list of each mount applied (host path → container path, permission, result) plus overall status, written to `$GITHUB_STEP_SUMMARY`. | Follows established patterns from Spec 025 (`render_github_summary.sh` for plan summaries). Operators need at-a-glance confirmation of what changed without opening evidence packs. |
| D-012 | Should terminal output display privilege tier labels during execution? | Yes, emit `[Tier 1]` and `[Tier 2]` labels at phase boundaries. | Makes the security model visible during execution. Helps operators confirm the privilege boundary is maintained and aids debugging when a step fails (immediately clear which credential context was active). |
| D-013 | What level of guidance should error messages provide when post-create fails? | Error + cause + suggested remediation. No documentation links (fragile in homelab context). | Follows existing patterns in the orchestrator (e.g., `assert_state_lxc_exists_or_empty` already provides "Remediation options:"). Operators running from CI or laptop need self-contained guidance without cross-referencing docs. |
| D-014 | Should the new-service onboarding workflow be a user story or documentation-only? | P3 user story (US-7) with acceptance scenarios, backed by updates to golden-paths-service-lifecycle.md and tfvars examples. | A user story ensures the onboarding workflow is testable and tracked. Documentation-only changes risk being forgotten. The golden paths doc already covers "Add a New Service" but omits mount discovery and configuration steps. |
| D-015 | What per-mount result states should the step summary report? | Three states: `applied`, `skipped`, `failed`. | Distinguishes new mounts from idempotent no-ops and failures. Operators need to know if a re-run changed anything or confirmed existing state. Failure details are specified by FR-018 and need not be duplicated in the state enum. A fourth "rejected" state was considered but is a sub-type of "failed" (the cause distinguishes allowlist rejection from other failures). |
| D-016 | Should the step summary show all configured mounts or only those with actions? | All configured mounts with their result state. | Provides operators a complete verification view. Typical homelab services have 1–3 mounts, so comprehensiveness adds no noise while enabling at-a-glance confirmation of the full mount configuration. Matches the existing plan summary pattern which shows all resources, not just changed ones. |
| D-017 | When a container reboot is required, should the step summary include the state transition? | Yes, include a summary line showing stop → apply → start. | Operators need to know when a service was temporarily unavailable. Transparency about the reboot aligns with the evidence-driven operator UX pattern and the dual-provisioning parity principle (both CI and laptop operators see the same information). |

## Open Questions

None — all ambiguities have been resolved via the reference document, the 2026-02-22 clarification sessions (D-010 through D-017), and documented in the Decision Log above.

## Self-Critique

### Strengths
- Comprehensive user stories with well-formed Given/When/Then acceptance scenarios covering the full deployment lifecycle (CI, laptop, regression).
- Edge cases are thorough and practical (index collision, partial failure, idempotency, empty list).
- Decision Log covers all key ambiguities with clear rationale.
- Constitution cross-check is rigorous — Principles I–IV are all addressed, and Spec 023 alignment is explicit.
- Non-functional requirements (60s timeout, idempotency, non-destructive failure) are measurable and testable.
- Out-of-scope section is well-bounded with 8 explicit exclusions.

### Issues Found (Resolved)
- **[severity: high]** The three-tier privilege model — the central concept of this feature — was referenced in acceptance criteria and key entities but never formally defined. **Fix applied:** Added the Three-Tier Privilege Model table to the Overview section with credentials, scopes, usage rules, and invariants.
- **[severity: high]** FR-003 and D-006 were in tension: D-006 said "remove the dynamic mountpoint block entirely" while FR-003 said "storage-backed mountpoints remain valid." Removing the block removes storage-backed support too. **Fix applied:** Revised D-006 to keep the dynamic block for storage-backed volumes but ensure no host-path values flow through it (enforced by the existing plan-stage policy guard). FR-003 updated to match.
- **[severity: medium]** The Overview mischaracterized the current state by saying the orchestrator manages "feature flags" and needs to be "extended for bind mounts." In reality, the orchestrator already manages both — bind mounts are just hardcoded per-service (Jellyfin, Immich blocks). The real change is generalisation, not addition. **Fix applied:** Revised Overview to accurately describe the current state and frame the change as generalisation.
- **[severity: medium]** AC-1.3 assumed all bind mounts are "writable." Jellyfin's video mount is `ro=1` (read-only). **Fix applied:** Changed to "accessible with the permissions specified in the manifest" and added D-008 for default permission semantics.
- **[severity: medium]** The spec referenced Nextcloud bind mounts as the primary example (e.g., `/mnt/nas/nextcloud`) but the current tfvars do not define Nextcloud mountpoints. **Fix applied:** Added D-009 documenting that the specific Nextcloud mount config is not yet defined; the generic mechanism is the deliverable.
- **[severity: low]** The existing `pct set -features` handling was not called out — could lead an architect to think it also needs generalisation. **Fix applied:** Added FR-016 stating the features handling is already generic and must remain unchanged.

### Verdict
ACCEPT — All identified issues have been resolved in this revision. The spec now has the three-tier model formally defined, the FR-003/D-006 inconsistency resolved, accurate framing of the current state, and complete coverage of all mount permission semantics.
