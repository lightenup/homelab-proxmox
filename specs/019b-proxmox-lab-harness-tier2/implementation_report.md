# Implementation Report: Lab Harness Tier 2

**Feature**: `019b-proxmox-lab-harness-tier2`
**Date**: December 30, 2025
**Status**: Complete

## 1. Executive Summary

The Lab Harness has been successfully extended to support "Tier 2" testing, enabling the simulation of a Proxmox VE host environment within the lab. This capability allows for safe, isolated testing of Proxmox host configuration roles (storage, networking, packages) without impacting the production hypervisor.

The implementation includes:
*   **Harness Logic**: Updated `pve-lab` script with Tier 2 lifecycle management, resource enforcement, and preflight checks.
*   **Template Automation**: A new `create_tier2_template.sh` script to generate Debian 13 (Trixie) templates with Cloud-Init and resized storage (32GB).
*   **Verification Playbook**: A new `lab_tier2_pve.yml` playbook that installs Proxmox VE 9, configures dependencies, and validates the installation via API checks.

## 2. Implementation Details

### 2.1 Harness Script (`scripts/lab/pve-lab`)

The harness script was refactored to support multi-tier execution flows.

*   **Flags**: Added `--tier <1|2>`, `--tier2-mode <min|plus>`, and `--keep`.
*   **Resource Floors**: Enforces minimum 4GB RAM and 2 vCPUs for Tier 2 VMs to ensure Proxmox VE stability.
*   **Template Selection**: Automatically selects `LAB_TEMPLATE_VMID_TIER2` (9002) when running in Tier 2 mode.
*   **Preflight Checks**:
    *   **Host**: Checks `/sys/module/kvm_intel/parameters/nested` for "Y" or "1" (Tier 2 Plus).
    *   **Guest**: Checks for `/dev/kvm` presence inside the Lab VM (Tier 2 Plus).

### 2.2 Template Creation (`scripts/lab/create_tier2_template.sh`)

A dedicated script was created to build the base image for Tier 2 testing.

*   **Source**: Debian 13 (Trixie) Generic Cloud Image.
*   **Customization**:
    *   Injects local SSH keys via Cloud-Init.
    *   Resizes the root disk to **32GB** to accommodate the Proxmox VE installation (resolving early "No space left on device" failures).
    *   Converts the VM to a template (VMID 9002).

### 2.3 Verification Playbook (`ansible/playbooks/lab_tier2_pve.yml`)

This playbook serves as the integration test for the Tier 2 environment. It performs the following actions:

1.  **Guards**: Validates the environment before making changes.
2.  **Repo Setup**: Configures Proxmox VE Trixie repositories and installs the release key.
3.  **Installation**: Installs `proxmox-ve`, `postfix`, and `open-iscsi` non-interactively.
4.  **Verification**: Checks service status and API availability.

## 3. Test Coverage & Assertions

The implementation relies on a series of strict assertions (Guards) and verification steps to ensure correctness.

### 3.1 Playbook Guards (Assertions)

| Guard Name | Assertion Logic | Purpose |
| :--- | :--- | :--- |
| **Check Inventory** | `lab_inventory is defined` AND `lab_inventory == true` | Prevents accidental execution against production hosts. |
| **Check Hostname Pattern** | `inventory_hostname` matches `^lab-pve-.*` | Ensures target matches the naming convention for ephemeral lab VMs. |
| **Check OS** | `distribution == 'Debian'` AND `major_version == '13'` | Verifies the base OS is Debian 13 (Trixie) as required for PVE 9. |
| **Hostname Resolution** | `hostname -f` returns FQDN | Confirms DNS/Hosts configuration is valid for PVE cluster communication. |
| **Ping Self** | `ping -c 1 {{ inventory_hostname }}` succeeds | Verifies local network stack and hostname resolution. |

### 3.2 Verification Steps

| Verification Task | Method | Success Criteria |
| :--- | :--- | :--- |
| **Verify Services** | Ansible `service` module | `pveproxy`, `pvedaemon`, `pve-cluster` are `started` and `enabled`. |
| **Verify Mountpoint** | `mountpoint -q /etc/pve` | Exit code 0 (Confirming pmxcfs is mounted). |
| **Verify API** | `pvesh get /version --output-format json` | Command succeeds (Exit code 0) and returns JSON. |
| **Capture Version** | `pveversion` | Command succeeds and outputs version string. |

## 4. Execution Results

The final validation run (`lab-20251230-135952`) completed successfully.

*   **Command**: `./scripts/lab/pve-lab run --tier 2`
*   **Duration**: ~7 minutes
*   **Outcome**:
    *   Template 9002 cloned to VM 9003.
    *   VM 9003 booted and accessible via SSH.
    *   Tier 1 (Bootstrap) passed.
    *   Tier 2 (PVE Install) passed all guards and verifications.
    *   VM 9003 destroyed (Cleanup).

```text
[INFO] Tier 2 passed.
[INFO] Run completed with status: SUCCESS
```

## 5. Artifacts

*   **Playbook**: `ansible/playbooks/lab_tier2_pve.yml`
*   **Harness**: `scripts/lab/pve-lab`
*   **Template Script**: `scripts/lab/create_tier2_template.sh`
*   **GPG Key**: `ansible/playbooks/files/proxmox-release-trixie.gpg`
