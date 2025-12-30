# Feature: Lab Harness Tier 2: “Proxmox-like” Coverage Increase

**Feature ID**: 019b
**Status**: Draft
**Feature Branch**: `019b-proxmox-lab-harness-tier2`

## 1. Introduction

### 1.1. Context
The `019a` feature established a robust Lab Harness (`pve-lab`) capable of spinning up isolated VMs on `vmbr99` (`10.99.0.0/24`), running basic bootstrap tests (Tier 1), and safely destroying them. This provides a foundation for testing.

The next step (`019b`) is to increase the depth of testing ("Tier 2") to validate the actual Proxmox host configuration automation. By simulating a Proxmox host environment within the lab, we can test the Ansible roles responsible for configuring the hypervisor itself (e.g., storage, networking, packages) without risking the production host.

### 1.2. Goals
1.  **Increase Coverage**: Validate "Proxmox-adjacent" bootstrap behaviors (OS config, packages, users) in a safe environment.
2.  **Maintain Safety**: Ensure zero risk to the production host or tailnet.
3.  **Repeatability**: Enable single-command end-to-end testing (`pve-lab run --tier 2`).
4.  **Future-Proofing**: Target **Proxmox VE 9 (Debian 13 / Trixie)** to align with upcoming infrastructure upgrades.

### 1.3. Scope
*   **In Scope**:
    *   Extending `pve-lab` to support `--tier 2`.
    *   Creating a Tier 2 playbook that applies host-level configurations.
    *   Validating nested virtualization (if applicable) or OS-level invariants.
    *   Updating documentation and artifacts.
*   **Out of Scope**:
    *   Full cluster simulation (corosync).
    *   Testing hardware passthrough.
    *   Modifying production inventory structure.
    *   Full host configuration automation (storage/network) - Tier 2 focuses on "PVE control-plane install + sanity verification".

## 2. Functional Requirements

### 2.1. Harness Interface (`pve-lab`)
*   **FR-001**: The `run` and `test` commands MUST accept a `--tier <level>` argument (defaulting to 1).
*   **FR-002**: When `--tier 2` is specified, the harness MUST execute the Tier 2 playbook after Tier 1 success.
*   **FR-003**: Tier 2 execution logs MUST be captured in `artifacts/019-lab/<runid>/tier2.log`.
*   **FR-004**: Failure in Tier 2 MUST trigger the standard cleanup (destroy) unless a debug flag is provided.
*   **FR-013 (Tier2 Template)**: When `--tier 2` is specified, the harness MUST use `LAB_TEMPLATE_VMID_TIER2` (defaulting to a Debian 13 template ID) instead of the Tier 1 default.

### 2.2. Tier 2 Logic ("PVE-in-Lab")
*   **FR-005**: The Tier 2 playbook (`ansible/playbooks/lab_tier2_pve.yml`) MUST install **Proxmox VE 9** packages on the Lab VM.
    *   *Constraint*: All package installs MUST be **noninteractive** (`DEBIAN_FRONTEND=noninteractive`) with appropriate preseeding to avoid blocking prompts.
*   **FR-012 (OS Gate)**: The Tier 2 playbook MUST assert that the target OS is **Debian 13 (Trixie)** (e.g., check `/etc/os-release`). If not, it MUST fail fast with a clear error message.
*   **FR-006**: The playbook MUST validate that PVE services (`pveproxy`, `pvedaemon`) are active and running.
*   **FR-007**: The playbook MUST validate that the PVE API is accessible (e.g., `curl -k https://localhost:8006`).
*   **FR-008**: The playbook MUST NOT attempt to join a cluster or mount production storage.
*   **FR-014 (Tier2 Modes)**:
    *   **Tier2-min** (Default): Install PVE packages + validate services/API. No nested VM required.
    *   **Tier2-plus** (Optional/Future): Create/start a tiny VM inside lab PVE. Requires nested KVM enabled on the host.
    *   *Check*: If Tier2-plus is requested, the harness MUST verify host nested virt support (`/sys/module/kvm_intel/parameters/nested` or AMD equivalent) and fail fast if missing.

### 2.3. Inventory & Safety
*   **FR-009**: The Lab Inventory (`ansible/inventories/lab/hosts.yml`) MUST remain the Single Source of Truth (SSOT) for the lab target.
*   **FR-010**: Tier 2 tests MUST use existing Ansible variables and roles where possible, rather than defining a parallel configuration.
*   **FR-011**: The harness MUST enforce that Tier 2 tests run ONLY against the `lab` inventory.
    *   *Guard*: The Tier 2 playbook MUST assert that the target hostname matches the lab naming convention (e.g., `lab-pve-*`).

## 3. User Scenarios

### 3.1. US1: Full Cycle Tier 2 Run
**Actor**: Developer
**Action**: Runs `scripts/lab/pve-lab run --tier 2`
**Outcome**:
1.  Harness provisions Lab VM using **Tier 2 Template** (Debian 13).
2.  Harness runs Tier 1 Bootstrap (Success).
3.  Harness runs Tier 2 PVE Install/Config (Noninteractive).
4.  Tier 2 validates PVE services are up.
5.  Harness destroys Lab VM.
6.  Summary JSON reports `tier: 2` and `status: SUCCESS`.

### 3.2. US2: Debugging Tier 2
**Actor**: Developer
**Action**: Runs `scripts/lab/pve-lab up --tier 2` then `scripts/lab/pve-lab test --tier 2`
**Outcome**:
1.  Harness uses existing VM (or creates one from Tier 2 template).
2.  Harness runs Tier 2 tests directly.
3.  VM remains running for manual inspection (SSH).

### 3.3. US3: Idempotency Check
**Actor**: Developer
**Action**: Runs `scripts/lab/pve-lab test --tier 2` twice on the same VM.
**Outcome**:
1.  First run installs/configures PVE.
2.  Second run reports `changed=0` (or minimal changes) and passes.

## 4. Technical Design

### 4.1. Architecture Updates
*   **Nested Virtualization**: The Proxmox Host (`192.168.1.112`) SHOULD have nested virtualization enabled (KVM) to allow future expansion to Tier2-plus.
    *   *Constraint*: Tier 2 (min) does not strictly require nested KVM for package installation and API checks, but it is recommended.
*   **Template**: The Lab VM MUST be based on **Debian 13 (Trixie)** to support Proxmox VE 9 installation.
    *   *Action*: Verify `tpl-pve-lab-tier2` (or configured ID) is Debian 13.

### 4.2. Tier 2 Playbook (`lab_tier2_pve.yml`)
*   **Target**: `lab_hosts`
*   **Guards**:
    *   `hosts: lab_hosts`
    *   `assert: inventory_hostname matches 'lab-pve-.*'`
    *   `assert: ansible_distribution == 'Debian' and ansible_distribution_major_version == '13'`
*   **Roles/Tasks**:
    1.  Add Proxmox VE Repository (No-Subscription).
    2.  Install `proxmox-ve`, `postfix`, `open-iscsi` (Noninteractive).
    3.  Check `pveversion`.
    4.  Check `systemctl is-active pveproxy`.
    5.  Check `curl -k https://localhost:8006/api2/json/version`.

### 4.3. Artifacts
*   `artifacts/019-lab/<runid>/tier2.log`: Ansible output for Tier 2.
*   `artifacts/019-lab/<runid>/summary.json`: Updated to include `tier_level`, `tier2_status`, and `tier2_mode`.

## 5. Success Criteria

1.  **Automation**: `pve-lab run --tier 2` completes successfully without user intervention.
2.  **Verification**: The Lab VM is confirmed to be running Proxmox VE 9 services (API accessible).
3.  **Safety**: No changes are made to the production host (verified by inventory restriction and hostname guards).
4.  **Performance**: Tier 2 execution completes within a reasonable timeframe (e.g., < 15 minutes).

## 6. Risks & Mitigations

| Risk | Impact | Mitigation |
| :--- | :--- | :--- |
| **Nested Virt Missing** | Tier2-plus features (nested VMs) will fail. | Tier2-min is the default and does not require nested virt. Explicit check added for Tier2-plus. |
| **Template Mismatch** | PVE install fails on non-Debian OS. | Enforce Debian 13 template requirement via `LAB_TEMPLATE_VMID_TIER2` and OS Gate (FR-012). |
| **Prod Accidental Target** | Tier 2 playbook runs against prod host. | Harness strictly limits inventory to `ansible/inventories/lab`. Playbook has `hosts: lab_hosts` and hostname regex guard. |
| **Interactive Prompts** | Automation hangs on package install. | Enforce `DEBIAN_FRONTEND=noninteractive` and preseed answers. |

## 7. Assumptions
*   The Proxmox Host (`192.168.1.112`) has sufficient resources to run a nested PVE instance (4GB+ RAM).
*   A Debian 13 (Trixie) Cloud-Init template is available or will be created as `LAB_TEMPLATE_VMID_TIER2`.
*   Internet access (NAT) on `vmbr99` is functional (verified in 019a).
