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
*   **FR-005 (Tier2 Mode Selector)**: The harness MUST support a `--tier2-mode <mode>` flag.
    *   Allowed values: `min` (default), `plus`.
    *   `min`: Install PVE packages + validate services/API. No nested VM required.
    *   `plus`: Includes `min` + creates/starts a tiny VM inside lab PVE (requires nested KVM).
*   **FR-006 (Debug/Keep)**: The harness MUST support a `--keep` flag.
    *   If set, the harness MUST NOT destroy the lab VM even if Tier 2 fails.
    *   If not set, Tier 2 failure MUST trigger standard cleanup.
*   **FR-007 (Tier2 Template)**: When `--tier 2` is specified, the harness MUST use `LAB_TEMPLATE_VMID_TIER2` (defaulting to a Debian 13 template ID) and MUST NOT reuse the Tier 1 template.
*   **FR-008 (Tier2 Resource Floor)**: When creating Tier 2 lab VMs, the harness MUST enforce a minimum resource profile:
    *   vCPU ≥ 2
    *   RAM ≥ 4096 MB
    *   Disk ≥ 32 GB
    *   If the template or clone results in less than the minimum, the harness MUST fail fast with a clear error.

### 2.2. Tier 2 Logic ("PVE-in-Lab")
*   **FR-009 (OS Gate)**: The Tier 2 playbook (`ansible/playbooks/lab_tier2_pve.yml`) MUST assert that the target OS is **Debian 13 (Trixie)** (e.g., check `/etc/os-release`). If not, it MUST fail fast with a clear error message.
*   **FR-010 (Repo/Keyring)**: The playbook MUST:
    1.  Install the official Proxmox repository key/keyring (e.g., `/etc/apt/trusted.gpg.d/proxmox-release-trixie.gpg`).
    2.  Add the **Proxmox VE 9 no-subscription** repository for **Debian 13 (Trixie)**.
    3.  Ensure any **enterprise** repository file is disabled/removed.
*   **FR-011 (Noninteractive Install)**: The playbook MUST install `proxmox-ve`, `postfix`, and `open-iscsi` using `DEBIAN_FRONTEND=noninteractive`.
    *   It MUST preseed `postfix` configuration (e.g., "Local only" or "No configuration") to prevent blocking prompts.
*   **FR-012 (Service Verification)**: The playbook MUST verify that the following services are active:
    *   `pveproxy`
    *   `pvedaemon`
    *   `pve-cluster` (or verify `/etc/pve` is mounted/writable).
*   **FR-013 (API Verification)**: The playbook MUST verify API accessibility by querying `https://localhost:8006/api2/json/version` and asserting a 200 OK response.
*   **FR-014 (Version Check)**: The playbook MUST record the output of `pveversion` (or the API version response) into the run artifacts.
*   **FR-015 (Reboot Policy)**: Tier2-min MUST NOT require a reboot to pass; validations are service/API based.

### 2.3. Tier2-plus Logic (Optional/Future)
*   **FR-016 (Tier2-plus Preflight)**: If `--tier2-mode plus` is selected, the harness MUST preflight:
    *   Host nested KVM enabled (`/sys/module/kvm_intel/parameters/nested` == `Y` or AMD equivalent).
    *   Lab VM has `/dev/kvm` present.
    *   Fail fast with a clear message if missing.
*   **FR-017 (Tier2-plus VM Smoke)**: Tier2-plus MUST attempt to create and start a minimal VM inside the lab Proxmox and verify it reaches "running" state.

### 2.4. Inventory & Safety
*   **FR-018 (Inventory SSOT)**: The Lab Inventory (`ansible/inventories/lab/hosts.yml`) MUST remain the Single Source of Truth (SSOT) for the lab target.
*   **FR-019 (Inventory Guard)**: The Tier 2 playbook MUST assert that it is executed against the correct inventory (e.g., by checking a `lab_inventory=true` variable or group membership).
*   **FR-020 (Hostname Guard)**: The Tier 2 playbook MUST assert that the target hostname matches the lab naming convention (e.g., `lab-pve-*`) early in execution.
*   **FR-021 (Isolation)**: The playbook MUST NOT attempt to join a cluster, mount production storage, or modify tailnet configuration.

### 2.5. Artifacts
*   **FR-022 (Summary Fields)**: `summary.json` MUST include:
    *   `tier_level`: `2`
    *   `tier2_mode`: `min` or `plus`
    *   `tier2_status`: `SUCCESS` or `FAILED`
    *   `pve_version`: Captured version string
    *   `checks`: Array/Object summarizing invariants (services, api, /etc/pve).

## 3. User Scenarios

### 3.1. US1: Full Cycle Tier 2 Run
**Actor**: Developer
**Action**: Runs `scripts/lab/pve-lab run --tier 2`
**Outcome**:
1.  Harness provisions Lab VM using **Tier 2 Template** (Debian 13).
2.  Harness enforces resource floor (4GB RAM, 2 vCPU).
3.  Harness runs Tier 1 Bootstrap (Success).
4.  Harness runs Tier 2 PVE Install/Config (Noninteractive, No-Subscription Repo).
5.  Tier 2 validates PVE services (`pveproxy`, `pvedaemon`, `pve-cluster`) and API.
6.  Harness destroys Lab VM.
7.  Summary JSON reports `tier: 2`, `tier2_mode: min`, and `status: SUCCESS`.

### 3.2. US2: Debugging Tier 2
**Actor**: Developer
**Action**: Runs `scripts/lab/pve-lab run --tier 2 --keep`
**Outcome**:
1.  Harness runs full cycle.
2.  If Tier 2 fails (or succeeds), the Lab VM is **NOT** destroyed.
3.  Developer can SSH in to inspect state.
4.  Developer must manually run `scripts/lab/pve-lab destroy` later.

### 3.3. US3: Tier2-plus (Nested Virt)
**Actor**: Developer
**Action**: Runs `scripts/lab/pve-lab run --tier 2 --tier2-mode plus`
**Outcome**:
1.  Harness verifies Host Nested KVM is enabled.
2.  Harness runs standard Tier 2 steps.
3.  Harness creates a nested VM inside the Lab PVE.
4.  Harness verifies nested VM is running.
5.  Harness destroys Lab VM.

## 4. Technical Design

### 4.1. Architecture Updates
*   **Nested Virtualization**:
    *   **BIOS/UEFI**: VT-x/AMD-V enabled (hardware virtualization).
    *   **Host OS**: Nested KVM enabled via kernel module (`kvm_intel nested=1`).
    *   *Requirement*: Tier2-min does **not** require nested KVM. Tier2-plus **does**.
*   **Template**: The Lab VM MUST be based on **Debian 13 (Trixie)** to support Proxmox VE 9 installation.
    *   *Action*: Verify `tpl-pve-lab-tier2` (or configured ID) is Debian 13.

### 4.2. Tier 2 Playbook (`lab_tier2_pve.yml`)
*   **Target**: `lab_hosts`
*   **Guards**:
    *   `hosts: lab_hosts`
    *   `assert: inventory_hostname matches 'lab-pve-.*'`
    *   `assert: ansible_distribution == 'Debian' and ansible_distribution_major_version == '13'`
    *   `assert: lab_inventory is defined and lab_inventory == true`
*   **Roles/Tasks**:
    1.  **Preflight**: Check OS, Hostname, Inventory.
    2.  **Repo Setup**: Install Keyring, Add No-Sub Repo, Remove Enterprise Repo.
    3.  **Install**: `proxmox-ve`, `postfix` (preseeded), `open-iscsi` (Noninteractive).
    4.  **Validation**:
        *   `systemctl is-active pveproxy pvedaemon pve-cluster`
        *   `test -d /etc/pve`
        *   `curl -f -k https://localhost:8006/api2/json/version`
        *   Register `pveversion` output.

### 4.3. Artifacts
*   `artifacts/019-lab/<runid>/tier2.log`: Ansible output for Tier 2.
*   `artifacts/019-lab/<runid>/summary.json`: Updated schema.

## 5. Success Criteria

1.  **Automation**: `pve-lab run --tier 2` completes successfully without user intervention.
2.  **Verification**: The Lab VM is confirmed to be running Proxmox VE 9 services (API accessible, `/etc/pve` present).
3.  **Safety**: No changes are made to the production host (verified by inventory restriction and hostname guards).
4.  **Performance**: Tier 2 execution completes within a reasonable timeframe (e.g., < 15 minutes).
5.  **Determinism**: Package installs use noninteractive mode and explicit repositories to prevent flakes.

## 6. Risks & Mitigations

| Risk | Impact | Mitigation |
| :--- | :--- | :--- |
| **Nested Virt Missing** | Tier2-plus features (nested VMs) will fail. | Tier2-min is the default and does not require nested virt. Explicit check added for Tier2-plus. |
| **Template Mismatch** | PVE install fails on non-Debian OS. | Enforce Debian 13 template requirement via `LAB_TEMPLATE_VMID_TIER2` and OS Gate (FR-009). |
| **Prod Accidental Target** | Tier 2 playbook runs against prod host. | Harness strictly limits inventory to `ansible/inventories/lab`. Playbook has `hosts: lab_hosts`, hostname regex guard, and inventory variable guard. |
| **Interactive Prompts** | Automation hangs on package install. | Enforce `DEBIAN_FRONTEND=noninteractive` and preseed answers (FR-011). |
| **Resource Exhaustion** | Lab VM consumes too much RAM/CPU. | Enforce resource floor (4GB/2vCPU) in `pve-lab` (FR-008). |

## 7. Assumptions
*   The Proxmox Host (`192.168.1.112`) has sufficient resources to run a nested PVE instance (4GB+ RAM).
*   A Debian 13 (Trixie) Cloud-Init template is available or will be created as `LAB_TEMPLATE_VMID_TIER2`.
*   Internet access (NAT) on `vmbr99` is functional (verified in 019a).
