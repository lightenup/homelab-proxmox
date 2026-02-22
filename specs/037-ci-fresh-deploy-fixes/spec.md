# Feature Specification: CI Fresh-Deploy Pipeline Fixes

**Feature Branch**: `037-ci-fresh-deploy-fixes`
**Created**: 2026-02-22
**Status**: Draft
**Input**: User description: "CI fresh deploy fixed"

## Overview

The CI pipeline (LXC Promote) cannot deploy a brand-new service end-to-end. The first service created purely through CI (Nextcloud — all prior services were bootstrapped via `rebuild.sh`) exposes two systemic defects:

1. **SSH key mismatch**: The orchestrator sets the deploy key via `TF_VAR_ssh_public_keys` (environment variable), but the operator's personal key is also declared in the `.tfvars` file under the same variable name. Terraform's variable precedence order gives `.tfvars` files higher priority than `TF_VAR_*` environment variables, so the personal key from tfvars wins and the deploy key is never written into the container. The SSH wait loop then fails because the orchestrator cannot authenticate with the key it holds.
2. **Network unreachability with no diagnostics**: Freshly created containers can be network-unreachable (e.g., due to stale CTID, interface misconfiguration, or routing gaps). The current pipeline has no pre-SSH reachability check — it proceeds directly to a 300-second SSH wait loop that produces zero diagnostic output before timing out.

Both defects share a root cause: the CI deploy path was never exercised for fresh container creation — only for updates to containers originally created by `rebuild.sh`.

## User Scenarios & Testing

### User Story 1 — CI Deploys a Fresh Container with Working SSH Access (Priority: P1)

As a homelab operator running the CI pipeline, I want the automated deployment to create a new LXC container from scratch and establish SSH connectivity on the first deploy, so that new services can be onboarded entirely through CI without manual intervention.

**Why this priority**: This is the core defect. Without SSH access, the pipeline cannot proceed to Ansible bootstrap, bind-mount verification, or any post-create step. Every downstream operation depends on this.

**Independent Test**: Trigger the "Lab 1 — LXC Promote" workflow for a service that has never been deployed (no existing container). The pipeline must complete through the SSH wait step without manual key injection.

**Acceptance Scenarios**:

1. **Given** a service definition for a container that does not yet exist on the Proxmox host, **When** the CI pipeline runs Terraform apply and the container is created, **Then** the orchestrator's deploy key is present in the container's `/root/.ssh/authorized_keys` before the SSH wait loop begins.
2. **Given** the orchestrator's deploy key has been injected into the container, **When** the SSH wait loop executes, **Then** the orchestrator connects successfully using its deploy key within 120 seconds.
3. **Given** the operator's personal SSH key is defined in the tfvars file, **When** the deploy key is injected post-create, **Then** the operator's personal key remains in the container (both keys are present, not replaced).
4. **Given** the CI pipeline has previously deployed the same service (container already exists with the deploy key), **When** the pipeline runs again, **Then** the deploy key injection is idempotent — no duplicate keys are added, and SSH connectivity still works.

---

### User Story 2 — Network Failures Produce Actionable Diagnostics (Priority: P1)

As a homelab operator, I want the CI pipeline to detect network unreachability early and provide actionable diagnostic output, so that I can identify and resolve connectivity issues in minutes rather than waiting 300 seconds for a blind timeout.

**Why this priority**: Equal to P1 because without network reachability, the SSH wait loop is futile. The current 300-second silent timeout wastes operator time and provides zero debugging information. Fast failure with diagnostics is essential for operational efficiency.

**Independent Test**: Deploy a container whose IP is not reachable from the Proxmox host (e.g., due to a misconfigured interface). The pipeline must fail within 30 seconds with output showing the container's network interface state and routing table.

**Acceptance Scenarios**:

1. **Given** a freshly created container, **When** the orchestrator reaches the post-create phase (before the SSH wait loop), **Then** it performs a network reachability check against the container's assigned IP address.
2. **Given** the container's IP is not pingable from the Proxmox host, **When** the network reachability check fails, **Then** the orchestrator captures the container's network interface state and routing table (from inside the container) and writes them to the evidence artifact and terminal/CI output.
3. **Given** the container's IP is not pingable, **When** the diagnostic output is produced, **Then** the pipeline fails immediately with a clear error message naming the unreachable IP and referencing the diagnostic output — not after a 300-second timeout.
4. **Given** the container's IP is pingable from the Proxmox host, **When** the network reachability check passes, **Then** the pipeline proceeds to the SSH wait loop without delay.

---

### User Story 3 — Existing Services Are Not Disrupted (Priority: P1)

As a homelab operator, I want the fresh-deploy fixes to leave all existing deployed services completely unaffected, so that fixing the new-container path carries zero risk of breaking running workloads.

**Why this priority**: Equal to P1 because regression on live services (Immich, Jellyfin, AdGuard, etc.) is unacceptable. The changes must be additive — they apply only to the deploy flow, not to existing container configurations.

**Independent Test**: Run the CI pipeline for an existing service (e.g., Jellyfin). The pipeline must complete identically to its behaviour before this change — same SSH connectivity, same result.

**Acceptance Scenarios**:

1. **Given** an existing container that was previously deployed and has a working SSH connection, **When** the CI pipeline runs for that service after this change, **Then** SSH connectivity continues to work exactly as before.
2. **Given** the deploy key injection step runs against an existing container where the deploy key is already present, **When** the step completes, **Then** no duplicate key is added and no existing keys are removed.
3. **Given** the network reachability check runs against an existing container with a known-working IP, **When** the check completes, **Then** it passes and the pipeline proceeds without delay or changed behaviour.

---

### User Story 4 — Laptop Deploy Has Parity with CI (Priority: P2)

As a homelab operator running deployments from my laptop, I want the deploy key injection and network health check to work identically from my laptop and from CI, so that neither path has capabilities the other lacks.

**Why this priority**: The constitution mandates dual-provisioning parity (Principle IV). Both paths must produce the same deploy key injection and the same network diagnostics.

**Independent Test**: Run `pve-service-deploy` for a new service from a developer laptop. The deploy key must be injected and the network check must run with the same output as CI.

**Acceptance Scenarios**:

1. **Given** an operator runs `pve-service-deploy` from their laptop for a new service, **When** the script completes the post-create phase, **Then** the deploy key is injected into the container and the network health check passes — identical to a CI run.
2. **Given** the network health check fails during a laptop deploy, **When** the diagnostic output is produced, **Then** it shows the same container interface state and routing information that CI would show.

---

### User Story 5 — Reduced SSH Wait Timeout (Priority: P3)

As a homelab operator, I want the SSH wait timeout reduced from 300 seconds to a more appropriate value, so that genuine SSH failures are surfaced faster now that the network reachability pre-check catches connectivity issues early.

**Why this priority**: Nice-to-have optimisation. The network reachability check (US-2) catches the most common failure mode (unreachable IP). With that in place, the SSH wait loop only needs to cover sshd startup time, not network-layer issues, and a shorter timeout is appropriate.

**Independent Test**: Create a container where sshd takes longer than the new timeout to start (e.g., by pausing the sshd service). The pipeline should fail at the reduced timeout, not 300 seconds.

**Acceptance Scenarios**:

1. **Given** a container with a reachable IP where sshd is running, **When** the SSH wait loop executes, **Then** it succeeds well within the reduced timeout.
2. **Given** a container with a reachable IP where sshd fails to start, **When** the SSH wait loop executes, **Then** it fails at the reduced timeout (120 seconds or less) rather than the previous 300-second timeout.
3. **Given** the timeout is configurable via an environment variable, **When** an operator overrides it, **Then** the override value is respected.

---

### Edge Cases

- **Stale CTID from failed first run**: If a previous pipeline run partially created a container (allocated CTID, created rootfs) before failing, the next run may encounter a container with an inconsistent network interface. The network health check must detect this and provide diagnostics rather than hanging.
- **Container not yet running when checks execute**: After `terraform apply` creates the container, it may not be in "running" state immediately. The deploy key injection and network check must account for the container needing to be started first.
- **Deploy key file missing on PVE host**: If `~/.ssh/id_lxc_deploy` does not exist, the orchestrator currently generates it. The deploy key injection step must handle the case where the public key file is not present (error with clear message, not silent failure).
- **`pct exec` unavailable or fails**: If `sudo pct exec` fails (e.g., container is in a stopped state that doesn't support exec), the error must be surfaced with remediation guidance rather than proceeding to a doomed SSH wait.
- **Multiple rapid deploys for the same service**: If two pipeline runs execute simultaneously for the same CTID, the deploy key injection must not corrupt `authorized_keys` (append operation is atomic enough for single-line keys, but concurrent `pct exec` calls may conflict).
- **Container on a different subnet than expected**: The network health check uses ping from PVE. If the PVE host and container are on different subnets (e.g., `192.168.1.x` vs `192.168.20.x`), the check must still work as long as routing exists (verified by the fact that other containers on that subnet are reachable).

## Requirements

### Functional Requirements

- **FR-001**: The orchestrator MUST inject the deploy public key (`id_lxc_deploy.pub`) into the container's `/root/.ssh/authorized_keys` after Terraform creates the container and before the SSH wait loop begins. *(Traces to US-1)*
- **FR-002**: The deploy key injection MUST use `pct exec` to write the key inside the container, bypassing Terraform variable precedence entirely. *(Traces to US-1)*
- **FR-003**: The deploy key injection MUST be idempotent — if the key is already present in `authorized_keys`, it MUST NOT be added again. *(Traces to US-1 AC-1.4, US-3 AC-3.2)*
- **FR-004**: The deploy key injection MUST NOT remove or overwrite any existing keys in `authorized_keys` (including the operator's personal key from tfvars). *(Traces to US-1 AC-1.3)*
- **FR-005**: The deploy key injection MUST ensure the `/root/.ssh/` directory and `authorized_keys` file exist with correct permissions (directory: 700, file: 600) before writing. *(Traces to US-1)*
- **FR-006**: The orchestrator MUST perform a network reachability check (ping) against the container's assigned IP address after Terraform apply and deploy key injection, before the SSH wait loop. *(Traces to US-2)*
- **FR-007**: When the network reachability check fails, the orchestrator MUST capture the container's network interface state (`ip addr show eth0`) and routing table (`ip route`) from inside the container via `pct exec` and write them to the evidence artifact and terminal/CI output. *(Traces to US-2 AC-2.2)*
- **FR-008**: When the network reachability check fails, the orchestrator MUST fail immediately with an actionable error message naming the unreachable IP and referencing the captured diagnostics. It MUST NOT proceed to the SSH wait loop. *(Traces to US-2 AC-2.3)*
- **FR-009**: When the network reachability check passes, the orchestrator MUST proceed to the SSH wait loop without additional delay. *(Traces to US-2 AC-2.4)*
- **FR-010**: The deploy key injection and network health check MUST produce the same behaviour and output when invoked from CI and from a developer laptop with the same arguments. *(Traces to US-4)*
- **FR-011**: The deploy key injection MUST log its action (key injected, or skipped because already present) to the terminal/CI output. *(Traces to US-1, US-3)*
- **FR-012**: The network diagnostic output MUST include the container ID, the expected IP address, the interface state, and the routing table — sufficient for an operator to diagnose the root cause without SSH access to the container. *(Traces to US-2)*
- **FR-013**: The SSH wait loop timeout MUST be reduced from 300 seconds to 120 seconds (configurable via environment variable). *(Traces to US-5)*
- **FR-014**: Existing containers that already have SSH connectivity MUST NOT be affected by the deploy key injection or network health check — both steps MUST be safe no-ops for already-working containers. *(Traces to US-3)*
- **FR-015**: The orchestrator MUST handle the case where the container is not yet in a running state when deploy key injection or network checks execute — it MUST ensure the container is running before proceeding, or fail with a clear error if the container cannot be started. *(Edge case: container not running)*
- **FR-016**: The deploy key injection step MUST fail with a clear error message if the deploy public key file does not exist on the PVE host, rather than silently proceeding to a doomed SSH wait loop. *(Edge case: key file missing)*
- **FR-017**: The deploy key injection step MUST produce an evidence artifact capturing the action taken (key injected or skipped), the container identifier, and the key fingerprint — following the established evidence-pack pattern used by the orchestrator for other Tier 2 operations (feature flags, bind mounts). *(Traces to US-1, US-3)*

### Key Entities

- **Deploy Key**: An SSH key pair (`id_lxc_deploy` / `id_lxc_deploy.pub`) generated on the PVE host by the orchestrator, used exclusively for CI/orchestrator SSH connectivity to containers. Never leaves the PVE host.
- **Operator Key**: The homelab operator's personal SSH public key, declared in the tfvars file under `ssh_public_keys`. Injected into containers by Terraform at creation time.
- **SSH Wait Loop**: The orchestrator step that repeatedly attempts SSH connection to a container's IP, waiting for sshd to become available. Currently times out at 300 seconds.
- **Network Health Check**: A new pre-SSH-wait step that verifies the container's IP is reachable from the PVE host via ping, capturing diagnostics on failure.
- **Evidence Artifact**: A file capturing diagnostic output (network state, key injection status) to support post-incident review. Follows the existing evidence-pack pattern used by the orchestrator.

## Success Criteria

### Measurable Outcomes

- **SC-001**: A brand-new service (no pre-existing container) can be deployed end-to-end through the CI pipeline — from container creation through SSH connectivity to Ansible bootstrap — on the first attempt, without manual intervention.
- **SC-002**: When a freshly created container has a network connectivity issue, the pipeline fails within 30 seconds (not 300) and the operator receives diagnostic output sufficient to identify the root cause without SSH access to the container.
- **SC-003**: After the changes are applied, running the CI pipeline for all existing services produces identical behaviour to before the change — no regressions in SSH connectivity, no additional keys injected if already present.
- **SC-004**: The same `pve-service-deploy` command and arguments produce identical deploy key injection and network diagnostic behaviour when run from CI and from a developer laptop.
- **SC-005**: The deploy key injection operation is idempotent — running the pipeline twice for the same container results in exactly one copy of the deploy key in `authorized_keys`.
- **SC-006**: When the deploy key file is missing or `pct exec` fails, the operator receives an error message within 10 seconds that names the specific failure and suggests a remediation action.

## Assumptions

- **A-001**: The `ci` user on the PVE host already has passwordless sudo access for `pct` commands (established in Spec 036 for bind-mount operations). No new sudoers entries are needed.
- **A-002**: The `id_lxc_deploy` key pair is generated by the orchestrator at the start of each deploy run if it does not already exist. This existing behaviour is unchanged.
- **A-003**: All LXC containers use Debian stable templates where `/root/.ssh/authorized_keys` is the standard SSH key location.
- **A-004**: The Proxmox host can reach all service IPs (including those on the `192.168.20.0/24` services subnet) via the `vmbr0` bridge. Other services on that subnet already work, confirming routing is functional.
- **A-005**: `pct exec` works on containers in "running" state. The orchestrator already starts containers after Terraform creates them (Proxmox auto-starts LXCs by default with `start = true`).
- **A-006**: The existing `TF_VAR_ssh_public_keys` environment variable setting in the orchestrator continues to work for containers where Terraform variable precedence is not an issue (i.e., where tfvars does not override it). The `pct exec` key injection is a belt-and-suspenders addition, not a replacement.
- **A-007**: The Telmate Proxmox Terraform provider is the active provider and will remain so (per constitution — no migration to bpg provider).

## Non-Functional Requirements

- **NFR-001**: The deploy key injection step MUST complete within 10 seconds per container (single `pct exec` call — negligible overhead).
- **NFR-002**: The network reachability check (ping + diagnostic capture on failure) MUST complete within 15 seconds per container.
- **NFR-003**: The combined overhead of deploy key injection and network health check MUST NOT add more than 30 seconds to a successful deploy compared to the current pipeline duration.
- **NFR-004**: The deploy key injection and network health check MUST be idempotent — running them multiple times on the same container MUST produce the same end state without errors.

## Out of Scope

- **Changing the `rebuild.sh` path** — it works and is the Tier 3 break-glass mechanism. Not modified by this feature.
- **Remote state migration** — Terraform state remains local on PVE.
- **Provider migration (Telmate → bpg)** — per constitution, the Telmate provider remains in use.
- **Modifying Terraform variable files (tfvars)** — the operator's personal key stays in tfvars; the deploy key is injected post-create, outside Terraform's control.
- **Modifying Terraform resource definitions** — no changes to `.tf` files. The key injection moves entirely to the Tier 2 orchestrator layer.
- **Diagnosing the specific root cause of CTID 105 network issue** — the diagnostics added by this feature will capture the information needed, but the actual fix for the Nextcloud container's network issue is a manual operational task, not a code change.
- **Fixing the underlying Terraform variable precedence design** — the `pct exec` key injection sidesteps this issue entirely. No Terraform changes are made to address variable precedence.
- **GitHub Actions workflow YAML changes** — the orchestrator handles everything; no workflow file modifications are needed.

## Decision Log

| # | Ambiguity | Decision | Rationale |
|---|-----------|----------|-----------|
| D-001 | How should the deploy key be injected — via Terraform variable override or post-create? | Post-create via `pct exec` (Option D from reference document). | Most robust approach: zero changes to Terraform, zero tfvars coordination, works regardless of what key is in tfvars, follows the established Tier 2 post-create pattern. The operator's personal key from tfvars remains in the container. |
| D-002 | Should the deploy key replace or supplement the operator's personal key? | Supplement. Both keys are present in the container. | Operators need SSH access for manual debugging. Removing their key would degrade the operational experience. The deploy key is added alongside existing keys. |
| D-003 | Should the network health check be a hard gate (fail pipeline) or a warning? | Hard gate. Pipeline fails immediately on network unreachability. | A warning would allow the SSH wait loop to run for 300 seconds, defeating the purpose. Fast failure with diagnostics is the goal. Operators can re-run after fixing the network issue. |
| D-004 | What diagnostic information should the network health check capture on failure? | Container's `ip addr show eth0` and `ip route` output, plus the Proxmox-side `pct config` network stanza. | These three pieces of information are sufficient to diagnose all hypothesised root causes (H1: stale CTID, H2: routing gap, H3: interface not up) without SSH access to the container. |
| D-005 | What should the reduced SSH wait timeout be? | 120 seconds, configurable via `SSH_WAIT_SECONDS` environment variable. | With the network reachability pre-check catching connectivity issues, the SSH wait only needs to cover sshd startup time. 120 seconds is generous for sshd startup on Debian LXC. The existing environment variable override is preserved for edge cases. |
| D-006 | Should the deploy key injection modify the orchestrator's existing `TF_VAR_ssh_public_keys` setting? | No. The env var setting remains as-is for backward compatibility. `pct exec` injection is an additional step, not a replacement. | Belt-and-suspenders approach. The env var works for containers where tfvars doesn't override it. The `pct exec` injection guarantees the key is present regardless of Terraform variable precedence. Removing the env var would be a larger change with no benefit. |
| D-007 | Where in the orchestrator flow should the new steps be inserted? | After Terraform apply and CTID extraction, before the SSH wait loop. Specifically: (1) inject deploy key, (2) verify network reachability, (3) SSH wait loop. | This ordering ensures the key is present and the network is verified before attempting SSH. The CTID is needed for `pct exec` (available after Terraform apply). |
| D-008 | Should the network health check also run in `cmd_plan()`? | No. `cmd_plan()` does not create containers, so there is no container to check. Deploy key injection and network checks apply only to `cmd_apply()`. Note: `cmd_plan()` also sets `TF_VAR_ssh_public_keys` (lines 795–800), which is equally ineffective due to the same `-var-file` precedence issue. This is cosmetic — plan output will show the personal key from tfvars, not the deploy key — but causes no functional harm since plan does not create containers. No change needed in `cmd_plan()`. | Plan is a read-only operation. Network and key injection are relevant only when a container is created or updated via apply. The cosmetic key mismatch in plan output is acceptable because the `pct exec` injection in `cmd_apply()` guarantees the correct key is present at runtime. |
| D-009 | Should the ping timeout in the network health check be configurable? | No. A fixed 5-second ping timeout is sufficient. The check is a quick pass/fail gate, not a tunable. | Simplicity. The ping check is binary — either the container is reachable or it isn't. A 5-second timeout covers normal network latency on a local LAN with margin. If 5 seconds is insufficient, there's a genuine network problem. |

## Open Questions

None — all ambiguities have been resolved via the reference document analysis and documented in the Decision Log above.

## Self-Critique

### Strengths
- Clearly scoped to two specific defects with well-understood root causes from the reference document.
- User stories cover the full matrix: fresh deploy (P1), diagnostics (P1), regression safety (P1), dual-provisioning parity (P2), and timeout optimisation (P3).
- Acceptance scenarios are concrete and testable — each maps to an observable pipeline outcome.
- Decision log covers the key design choice (Option D for key injection) and all secondary decisions with clear rationale.
- Edge cases are practical and derived from actual failure modes observed in the reference document.
- Out-of-scope section explicitly excludes Terraform changes, tfvars changes, and workflow YAML changes — keeping the blast radius minimal.
- Root cause analysis is precise and codebase-verified: Terraform's `.tfvars` precedence over `TF_VAR_*` environment variables explains the SSH key mismatch exactly.
- Constitution cross-check is thorough: Principles II (secrets — deploy key stays on PVE), III (separation — Tier 2 orchestrator, not Terraform), IV (dual-provisioning parity — US-4), and Token Privilege Tiers (Tier 2 for `pct exec`) are all honoured.

### Issues Found (Resolved)
- **[severity: medium]** Initial draft of US-2 AC-2.2 only required capturing `ip addr show eth0` but the reference document also lists `ip route` and `pct config | grep net` as necessary diagnostics. **Fix applied:** AC-2.2 updated to require both interface state and routing table. FR-012 covers the full diagnostic set.
- **[severity: medium]** Initial edge case list did not address the scenario where the container is not yet running when `pct exec` is called. **Fix applied:** Added edge case "Container not yet running when checks execute" and FR-015 to handle it.
- **[severity: low]** AC-1.2 originally said "within 60 seconds" but D-005 sets the timeout to 120 seconds. **Fix applied:** AC-1.2 aligned to 120 seconds.
- **[severity: low]** FR-011 required logging deploy key injection to terminal/CI output but did not require an evidence artifact — inconsistent with the established Tier 2 evidence pattern (feature flags → `lxc-features.txt`, bind mounts → `lxc-mountpoints.txt`). **Fix applied:** Added FR-017 requiring an evidence artifact for deploy key injection to maintain evidence-pack consistency.
- **[severity: low]** The overview described the Terraform variable precedence issue but did not explicitly name the precedence rule (`.tfvars` overrides `TF_VAR_*` env vars). **Fix applied:** Expanded overview to name the precedence mechanism, making the root cause self-evident for the architect.

### Verdict
ACCEPT — All identified issues resolved. The spec is tightly scoped to the two defects, avoids implementation details, and provides testable acceptance criteria for every functional requirement. The evidence-pack coverage is now complete across all Tier 2 operations introduced by this feature.
