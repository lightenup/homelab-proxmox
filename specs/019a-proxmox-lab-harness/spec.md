# Feature Specification: Proxmox Lab Test Harness (Foundation + Design Doc)

**Feature Branch**: `019a-proxmox-lab-harness`
**Created**: 2025-12-30
**Status**: Draft
**Input**: User description: "Proxmox Lab Test Harness (Foundation + Design Doc)"

## Clarifications

### Session 2025-12-30
- Q: How should the harness execute Proxmox commands (clone, start, destroy)? → A: **SSH Tunneling**. The script will run locally and execute `qm` commands on the production host via SSH (e.g., `ssh root@proxmox "qm clone..."`). This avoids managing separate API tokens.
- Q: What is the "Lab VM"? → A: It is a **Lab Host** (Linux VM). While it simulates a Proxmox node in topology, for 019a it is primarily a foundation for testing lifecycle and connectivity. True nested Proxmox capabilities are not fully validated in this iteration.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Full Test Cycle (Priority: P1)

As an operator, I want to run a single command to spin up a lab environment, run basic checks, and tear it down, so that I can verify the infrastructure code without manual intervention.

**Why this priority**: This is the primary use case for the harness—automating the feedback loop.

**Independent Test**: Run `scripts/lab/pve-lab run` and verify it completes successfully with artifacts generated.

**Acceptance Scenarios**:

1. **Given** a clean state (no lab host), **When** I run `pve-lab run`, **Then** a lab host is created, tests pass, host is destroyed, and a summary is written.
2. **Given** a running lab host (from a previous failed run), **When** I run `pve-lab run`, **Then** the old host is cleaned up before the new run starts.
3. **Given** a concurrent run attempt, **When** I run `pve-lab run` while another instance is running, **Then** it fails fast with a lock error.

---

### User Story 2 - Debugging Workflow (Priority: P2)

As an operator, I want to spin up the lab environment and keep it running to inspect failures or run ad-hoc tests.

**Why this priority**: Essential for troubleshooting when the automated run fails.

**Independent Test**: Run `up`, then `test`, then manually SSH into the lab host.

**Acceptance Scenarios**:

1. **Given** no lab host, **When** I run `pve-lab up`, **Then** the host is running and accessible via SSH from the local machine (via ProxyJump).
2. **Given** a running lab host, **When** I run `pve-lab test`, **Then** the tests execute against the existing host.
3. **Given** a running lab host, **When** I run `pve-lab destroy`, **Then** the host is removed.

---

### User Story 3 - Status Check (Priority: P3)

As an operator, I want to know if a lab environment is currently active.

**Why this priority**: Helps avoid confusion about resource usage or accidental concurrent runs.

**Independent Test**: Run `pve-lab status` before and after `up`.

**Acceptance Scenarios**:

1. **Given** no lab host, **When** I run `pve-lab status`, **Then** it reports "Not Running".
2. **Given** a running lab host, **When** I run `pve-lab status`, **Then** it reports "Running" with the VMID and IP.

### Edge Cases

- **VMID Conflict**: If the target VMID (e.g., 9000) is already taken by a non-lab VM (unlikely due to reservation, but possible), the script should abort.
- **Network Unreachable**: If the lab host boots but is unreachable due to vmbr99/NIC misconfiguration or VM not acquiring link, `up` should timeout and fail.
- **Test Failure**: If `test` fails, `destroy` should still be runnable (fail-safe).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Running `scripts/lab/pve-lab up` clones the template defined by `LAB_TEMPLATE_VMID` (numeric) into a new VMID in the lab range (9000-9099) and boots it. This MUST be performed via SSH commands to the production host. Optionally, the harness may verify the template name equals `tpl-pve-lab-base` as a sanity check, but `LAB_TEMPLATE_VMID` is the canonical source.
- **FR-002**: `scripts/lab/pve-lab test` runs Tier 0 checks and then runs Tier 1 convergence against the lab host.
  - Tier 0 Terraform: `terraform fmt -check` in `./terraform`.
  - Tier 0 Ansible: `ansible-playbook --syntax-check` on `ansible/playbooks/lab_bootstrap.yml`.
- **FR-003**: `scripts/lab/pve-lab destroy` removes the lab host and cleans up any temporary runtime files.
- **FR-004**: `scripts/lab/pve-lab run` executes `up` → `test` → `destroy` in sequence.
- **FR-005**: A run must be uniquely identified by `lab-YYYYMMDD-HHMMSS` and produce artifacts (logs) and `summary.json` in `artifacts/019-lab/<runid>/`.
- **FR-006**: The harness must fail-safe: if `test` fails, `destroy` must still be runnable.
- **FR-007**: Lab inventory must use ProxyJump via the prod PVE host and must not require putting the lab host on the LAN. All SSH connections to the lab host originate from the local machine and tunnel through the production PVE host.
- **FR-008**: The harness must verify it is operating on a VMID within the reserved range (9000-9099) before performing destructive actions.
- **FR-009 (Status command)**: `scripts/lab/pve-lab status` MUST report whether the lab host exists/running. If running, include VMID, **configured static IP** `10.99.0.10`, and a reachability indicator ("SSH reachable: yes/no").
- **FR-010 (Template identification)**: The clone source MUST be defined by a variable `LAB_TEMPLATE_VMID` (numeric).
- **FR-011 (Lab Host identity markers)**: Lab Hosts MUST be uniquely identifiable by **TWO** independent markers:
  1.  **Name Prefix**: Must start with `lab-pve-` (or similar deterministic prefix).
  2.  **Description Tags**: Must contain `ManagedBy=019a` AND `RunId=<runid>`.
- **FR-012 (Safe cleanup and destructive guard)**: Any destructive action (`destroy`, pre-run cleanup) MUST require **ALL** of the following:
  1.  VMID in reserved lab range `9000–9099`.
  2.  VM Name matches the lab prefix (e.g., `lab-pve-`).
  3.  VM Description contains the `ManagedBy=019a` tag.
  4.  VM Description contains the `RunId=` tag (must exist).
  If VMID is in range but ANY marker is missing/mismatch, abort with a clear error (protects non-lab VMs).
- **FR-013 (IP discovery & Reachability)**:
  - Lab Host MUST use Static IP `10.99.0.10/24` on `vmbr99`.
  - Production Proxmox Host MUST have L3 reachability to `10.99.0.10` (e.g., assigned IP `10.99.0.1/24` on `vmbr99`).
  - `up` command MUST verify SSH connectivity to `10.99.0.10` via ProxyJump (Local -> Prod PVE -> Lab Host) before declaring success.
- **FR-014 (Tier 1 definition)**: `pve-lab test` Tier 1 convergence MUST run `ansible/playbooks/lab_bootstrap.yml`.
  - This playbook MUST install baseline packages (python3, sudo, sshd).
  - This playbook MUST NOT perform external integrations (Tailscale, NAS mounts, etc.).
- **FR-015 (Design doc)**: Create and maintain `docs/architecture/019-proxmox-lab-harness.md`. It MUST include:
  - Topology diagram (ASCII).
  - `vmbr99` setup steps (including prod PVE IP requirement).
  - VMID range policy (9000-9099) and allocation strategy (First Free).
  - Identity marker scheme and safety model.
  - Command lifecycle inputs/outputs.
  - Artifact layout.
  - Test tiers definition and limitations (explicitly stating 019a does NOT cover full Proxmox rebuilds).
- **FR-016 (VMID Allocation)**: The harness MUST deterministically choose the first available VMID in the 9000-9099 range (ascending order) for new runs.
- **FR-017 (Concurrency Locking)**: The harness MUST acquire a local lock using `flock` on `artifacts/019-lab/.lock` at the start of `run` or `up`. If the lock is held by another process, the harness MUST fail fast with a "run in progress" message.

### Non-Functional Requirements

- **NFR-001 (Isolation)**: Lab network must be isolated (e.g., `vmbr99` + `10.99.0.0/24`) and must not join/bridge into `192.168.1.0/24`.
- **NFR-002 (No external integrations)**: Lab MUST NOT mount NAS shares, MUST NOT join Tailscale, MUST NOT advertise subnet routes, and MUST NOT modify prod tailnet state.
- **NFR-003 (Repeatability)**: Re-running `run` must be repeatable and produce deterministic artifacts structure; no manual steps.
- **NFR-004 (Clean teardown)**: After successful `run`, there must be no residual VMs in the lab range and no lingering runtime files.
- **NFR-005 (No duplicate inventory registration)**: The lab inventory should include only the lab host and connection details; it must not introduce a second copy of service endpoints or host lists.

### Key Entities

- **Lab Host**: The ephemeral Linux VM (simulating a Proxmox node) used for testing.
- **Lab Inventory**: Ansible inventory file specific to the lab environment.
- **Run Artifacts**: Logs and summary files generated by a test run.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `pve-lab up` completes (Host reachable via SSH) in under 5 minutes.
- **SC-002**: `pve-lab destroy` succeeds for **10 consecutive runs** without leftover VMs.
- **SC-003**: Artifacts are generated for every run, including failed ones.
- **SC-004**: No residual resources (VMs, files) remain after a successful `run` command.
- **SC-005**: Destructive actions abort immediately if the target VMID exists but lacks ANY of the required identity markers (Name + Tags).
- **SC-006**: `pve-lab status` correctly reports "Running" with IP `10.99.0.10` when the lab host is active.
- **SC-007**: Concurrent runs are prevented by the locking mechanism.
- **SC-008**: Lab host is reachable by SSH at `10.99.0.10` using ProxyJump via prod PVE (verified by `pve-lab up` reachability check).
