# Plan: Tier 2 Hardening

**Feature**: `019b1-proxmox-lab-harness-tier2-hardening`
**Status**: Planned

## Phase 1: Harness Hardening (Preflights & Artifacts)

**Objective**: Enhance the `pve-lab` harness script to fail fast on missing prerequisites and reliably collect diagnostic data.

- [ ] **Enhanced Preflights**:
    - Update `check_host_requirements` to support `kvm_amd` detection (FR-010).
    - Add `check_network_requirements` to validate FQDN resolution and internet connectivity (FR-009).
- [ ] **Artifact Collection & Rotation**:
    - Implement `collect_artifacts` to fetch logs and status from the Lab VM to the controller (FR-011).
    - Ensure collection runs on both success and failure.
    - Implement `rotate_artifacts` to keep only the last 5 run directories (FR-012).

## Phase 2: Playbook Hardening (Repo, Keyring, Non-interactive)

**Objective**: Update the Ansible playbook to ensure secure, deterministic, and non-interactive execution.

- [ ] **Non-interactive Configuration**:
    - Configure `needrestart` to automatic mode (`NEEDRESTART_MODE=a`) (FR-006).
    - Preseed `postfix` for "Local only" installation (FR-005).
    - Set `DEBIAN_FRONTEND=noninteractive` for all apt tasks (FR-004).
- [ ] **Repository & Keyring**:
    - Download official Proxmox release key to `/usr/share/keyrings/` (FR-001).
    - Configure `apt_repository` with `signed-by` (FR-001a).
    - Remove Enterprise repo (FR-002).
    - Validate repo availability via `apt-cache policy` (FR-003).
- [ ] **Robustness**:
    - Add retries and timeouts to all `apt` module calls (FR-007).

## Phase 3: Verification

**Objective**: Validate that the hardening measures work as expected and meet success criteria.

- [ ] **Manual Verification**:
    - Verify artifact generation and rotation.
    - Verify no interactive prompts during run.
- [ ] **Idempotency Test**:
    - Run Tier 2, keep VM, run again. Verify `changed=0` (SC-003).
- [ ] **Stability Test**:
    - Execute 5 consecutive runs for standard and plus modes (SC-001, SC-002).
