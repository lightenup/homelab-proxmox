# Implementation Report: 019a Proxmox Lab Harness

**Date**: December 30, 2025
**Status**: Completed & Verified
**Feature Branch**: `019a-proxmox-lab-harness`

## 1. Overview

This feature implements a robust, automated test harness for the Proxmox Homelab environment. It enables safe, isolated testing of Infrastructure-as-Code (IaC) changes by spinning up ephemeral Lab VMs, applying configurations, running verification tests, and tearing down resources.

The harness is designed to run on a macOS controller, interacting with a Proxmox host (`192.168.1.112`) to manage resources in a dedicated `10.99.0.0/24` lab network.

## 2. Components Implemented

### 2.1. Harness Orchestrator (`scripts/lab/pve-lab`)
A Bash script serving as the main entry point.
*   **Commands**: `up`, `down/destroy`, `test`, `status`, `run` (full cycle).
*   **Locking**: Uses `flock` (via Homebrew) on `artifacts/019-lab/.lock` to prevent concurrent runs.
*   **VM Management**:
    *   Allocates "First Free" VMID in range `9000-9099`.
    *   Clones from template `9001` (Ubuntu Cloud-Init).
    *   Configures static IP `10.99.0.10` and Gateway `10.99.0.1`.
    *   Tags VMs with `ManagedBy=019a` and `RunId=<timestamp>`.
*   **Safety**: Strict guardrails in `destroy` command (must match ID range, Name pattern, and Tags).
*   **Logging**: JSONL structured logging and full run logs in `artifacts/019-lab/<runid>/`.

### 2.2. Host Networking (`ansible/playbooks/lab_setup.yml`)
Configures the Proxmox host to support the Lab network.
*   **Bridge**: Ensures `vmbr99` exists with IP `10.99.0.1/24`.
*   **NAT/Masquerade**: Adds `iptables` rules to `vmbr99` interface configuration to allow Lab VMs to access the internet (essential for `apt-get`).

### 2.3. Lab Inventory (`ansible/inventories/lab/hosts.yml`)
Defines the Lab environment for Ansible.
*   **Host**: `lab-pve-01` (IP: `10.99.0.10`).
*   **Connection**: Uses `ProxyJump` via the Proxmox host (`root@192.168.1.112`) to reach the private Lab network from the macOS controller.
*   **Variables**: Sets `ansible_user=root` and strict host key checking options.

### 2.4. Tier 1 Testing (`ansible/playbooks/lab_bootstrap.yml`)
A minimal playbook to verify the Lab VM is functional.
*   **Checks**:
    *   SSH Connectivity (implicit).
    *   Package Installation (`curl`, `git`, `htop`) - verifies Internet/NAT.
    *   Hostname Verification (Regex match `lab-pve-.*`).

## 3. Key Technical Decisions

### 3.1. Locking Mechanism
*   **Decision**: Switched from directory-based locking (`mkdir`) to file locking with `flock`.
*   **Reasoning**: `flock` handles stale locks (process death) automatically by releasing the file descriptor. This prevents "stuck" locks requiring manual intervention.
*   **Implementation**: `exec 200>"$LOCK_FILE"; flock -n 200`.

### 3.2. Networking & Connectivity
*   **NAT**: Lab VMs are on a private subnet (`10.99.0.0/24`). To install packages, they need internet. We implemented Masquerade NAT on the host's `vmbr99` interface.
*   **ProxyJump**: The macOS controller cannot route directly to `10.99.0.0/24`. We configured Ansible to use the Proxmox host as a jump box (`ssh -J`).
*   **DNS**: To avoid local DNS resolution issues with the `.lab` TLD or private IPs, we hardcoded the IP `10.99.0.10` in the inventory and the ProxyJump address.

### 3.3. macOS Compatibility
*   **Timestamp**: macOS `date` does not support `%N` (nanoseconds).
*   **Solution**: Implemented a `get_ms_timestamp` helper that falls back to Python 3 (`time.time()`) or standard seconds if Python is missing.

## 4. Verification Results

### 4.1. Concurrency Test
*   **Test**: Ran a script holding the lock for 5s, attempted to run `pve-lab` simultaneously.
*   **Result**: Second instance correctly failed with `[ERROR] Another instance is running`.

### 4.2. End-to-End Run (`pve-lab run`)
*   **Execution ID**: `lab-20251230-110839`
*   **Steps**:
    1.  **Cleanup**: Checked for existing VMs (None).
    2.  **Up**: Cloned VM 9002, started, waited for SSH (Success).
    3.  **Tier 0**: `terraform fmt` (Passed), Ansible Syntax Check (Passed).
    4.  **Tier 1**: `lab_bootstrap.yml` ran successfully (Installed packages, verified hostname).
    5.  **Destroy**: VM 9002 stopped and removed.
*   **Outcome**: `SUCCESS`.

## 5. Usage Guide

```bash
# Full lifecycle (Up -> Test -> Destroy)
scripts/lab/pve-lab run

# Manual Lifecycle
scripts/lab/pve-lab up      # Create VM
scripts/lab/pve-lab test    # Run tests against current VM
scripts/lab/pve-lab status  # Check VM status
scripts/lab/pve-lab destroy # Tear down
```

## 6. Artifacts

*   **Logs**: `artifacts/019-lab/<runid>/run.log`
*   **Summary**: `artifacts/019-lab/<runid>/summary.json`
*   **Commands**: `artifacts/019-lab/<runid>/commands.jsonl`
