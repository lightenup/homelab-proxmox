# Feature Specification: Proxmox CI hardening

**Feature Branch**: `021-proxmox-ci-hardening`
**Created**: 2026-01-02
**Status**: Draft
**Input**: "Move proxmox-apply to pi-ci runner using ci@pve with least-privilege sudo, fix rsync/artifacts, harden scripts, and stabilize provisioning with debug evidence."

## Clarifications

### Session 2026-01-02

- Q: Where should runtime artifacts live to avoid rsync deletions/permission issues? → A: Place them under /var/lib/homelab-proxmox/artifacts on PVE; workflows and scripts read/write there and exclude it from repo rsync.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Pipeline runs as ci on pi-ci (Priority: P1)

pi-ci runs proxmox-apply using ci@pve end-to-end without any root SSH or root-owned outputs, and the deploy finishes with rebuild/apply/verify succeeding.

**Why this priority**: This is the primary delivery path; without it green the platform cannot be updated safely.

**Independent Test**: Trigger proxmox-apply on pi-ci and confirm it completes successfully while all remote operations use ci and produce no root-owned files.

**Acceptance Scenarios**:

1. **Given** pi-ci has the repo and SSH config alias pve, **When** proxmox-apply runs, **Then** rsync uses ci@pve and skips runtime artifacts so the job finishes without permission errors.
2. **Given** the workflow completes, **When** pve-lab rebuild --apply --verify is invoked as ci, **Then** all phases pass and the log contains no root SSH usage.

---

### User Story 2 - Least-privilege sudo guardrails (Priority: P2)

ci on PVE has a constrained sudo profile that allows only the orchestrator’s required commands, with smoke checks proving allowed commands work and disallowed commands fail.

**Why this priority**: Reduces blast radius while keeping automation non-interactive; prevents regressions toward root usage.

**Independent Test**: Run sudo smoke checks from the pipeline and verify success for allowed commands and denial for anything outside the allowlist.

**Acceptance Scenarios**:

1. **Given** sudoers policy is installed, **When** the pipeline runs sudo -n true and sudo -n qm --version, **Then** both succeed without password prompts.
2. **Given** the same policy, **When** ci attempts sudo -n bash, **Then** access is denied and logged as blocked.

---

### User Story 3 - Deterministic provisioning with evidence (Priority: P3)

Rebuild provisioning either reaches SSH readiness within the enlarged timeout or automatically captures rich evidence (qm status/config, cloud-init data, network probes, logs) for debugging.

**Why this priority**: Reduces time diagnosing VM bring-up issues and makes failures actionable.

**Independent Test**: Trigger a rebuild; verify either a successful SSH login within the timeout or a collected evidence bundle summarizing failure signals.

**Acceptance Scenarios**:

1. **Given** a new VM build, **When** provisioning starts, **Then** SSH becomes available within the configured wait window and the workflow continues.
2. **Given** SSH does not become available, **When** the timeout expires, **Then** the pipeline emits an evidence bundle containing qm status/config, cloud-init artifacts, and network reachability checks.

---

### Edge Cases

- Artifacts directory on PVE already contains root-owned files; rsync must not delete or overwrite them and must not fail with permission errors.
- jq or other required tools are missing on PVE; checks.json generation must fail fast with a clear missing-tool message.
- Network to the provisioned VM is delayed or flap-prone; SSH wait should retry within the timeout and surface network evidence on failure.
- Sudoers file is malformed or missing; privileged helper should abort with guidance instead of proceeding.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: All workflow SSH/rsync operations MUST target ci@pve via the SSH config alias and MUST NOT use root over SSH.
- **FR-002**: Workflow rsync MUST exclude runtime-generated artifacts and MUST avoid deleting runtime outputs; artifacts MUST reside at /var/lib/homelab-proxmox/artifacts on PVE, outside the repo sync root, with workflows/scripts using that absolute path.
- **FR-003**: proxmox-apply MUST invoke pve-lab rebuild --apply --verify as ci after deploy, using non-interactive sudo only through approved commands.
- **FR-004**: A least-privilege sudoers policy for ci MUST allow only required Proxmox commands (qm, pct, pvesh, pveversion, and documented service controls) with Defaults:ci !requiretty and sudo -n support.
- **FR-005**: Pipeline MUST include smoke checks verifying sudo -n true and sudo -n qm --version succeed, and a representative disallowed command is denied.
- **FR-006**: scripts/lab/pve-lab and supporting libs MUST route privileged operations through a dedicated sudo -n helper that fails fast with actionable messaging when permissions are insufficient.
- **FR-007**: All artifacts, logs, and lock files created by orchestration MUST be owned by ci and written to an artifact path that is not wiped by rsync.
- **FR-008**: Dependency preflight on PVE MUST validate availability of jq, ssh, and rsync; checks.json generation MUST emit valid JSON or fail with a clear error if dependencies or data are invalid.
- **FR-009**: Provisioning MUST use a configurable SSH wait timeout (minimum 5 minutes default) and, on timeout, MUST collect evidence (qm status/config, cloud-init data, network probes, relevant logs) attached to the pipeline artifacts.
- **FR-010**: Any Ansible/Terraform interactions MUST operate as ci with sudo -n or via scoped Proxmox API tokens; required roles/permissions and secret handling MUST be documented.

### Key Entities *(include if feature involves data)*

- **ci user on PVE**: Non-root operator with scoped sudo rights for Proxmox orchestration.
- **pi-ci runner**: Self-hosted GitHub Actions runner (ARM64) that fetches the repo and initiates deployments.
- **Artifact store**: /var/lib/homelab-proxmox/artifacts on PVE for runtime outputs and evidence bundles, writable by ci and excluded from repo rsync.
- **Proxmox orchestrator (pve-lab)**: Script suite that performs rebuild/apply/verify using ci plus privileged helper when needed.

### Assumptions

- Artifacts are stored at /var/lib/homelab-proxmox/artifacts on PVE, outside the repo sync root, remain writable by ci, and are excluded from repo rsync.
- SSH alias pve is configured on pi-ci to reach the PVE host using the ci keypair.
- Proxmox API credentials for non-root automation are available to the pipeline when Terraform is used.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: proxmox-apply completes on pi-ci with zero root@pve SSH calls and succeeds through rebuild/apply/verify.
- **SC-002**: Rsync step finishes without permission errors, leaves runtime artifacts intact, and subsequent pipeline runs succeed repeatedly without manual cleanup.
- **SC-003**: Sudo smoke checks pass for allowed commands and fail for a blocked command in the same run, confirming least-privilege enforcement.
- **SC-004**: VM provisioning reaches SSH availability within the configured timeout in 95% of runs; remaining failures emit an evidence bundle with qm status/config, cloud-init data, and network probes.
- **SC-005**: checks.json is valid JSON in 100% of runs, and missing dependency cases fail with explicit guidance within 1 minute of start.
