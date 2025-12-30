# Architecture: Proxmox Lab Test Harness

**Feature**: 019a-proxmox-lab-harness
**Status**: Final
**Last Updated**: 2025-12-30

## Overview

The Proxmox Lab Test Harness is a local CLI tool (`pve-lab`) that orchestrates the creation, testing, and destruction of ephemeral Proxmox environments. It enables safe, repeatable infrastructure testing without risking the production environment.

## Topology

### Network Layout

The lab environment uses a dedicated, isolated network bridge on the Proxmox host to prevent interference with the home LAN.

- **Bridge**: `vmbr99` (Isolated, no physical uplink required for internal-only, or NAT if internet needed)
- **Subnet**: `10.99.0.0/24`
- **Gateway**: `10.99.0.1` (Proxmox Host IP on vmbr99)
- **Lab VM IP**: `10.99.0.10` (Static)
- **DHCP**: Disabled (Static IP assignment via Cloud-Init)

### VMID Reservation

To prevent accidental overwrites, a specific VMID range is strictly reserved for lab usage.

- **Range**: `9000` - `9099`
- **Allocation Strategy**: First Free. The harness scans the range 9000-9099 and selects the first unused VMID.
- **Template VMID**: Defined by `LAB_TEMPLATE_VMID` (default `9001`).

### Identity Marker

All lab resources must be identifiable by **ALL** of the following:
1.  **VMID**: Inside the `9000-9099` range.
2.  **Name Prefix**: VM name must start with `lab-pve-`.
3.  **ManagedBy Tag**: VM description must contain `ManagedBy=019a`.
4.  **RunId Tag**: VM description must contain `RunId=<runid>`.

## Workflow

1.  **Locking**:
    - Acquires a local file lock on `artifacts/019-lab/.lock` to prevent concurrent runs.

2.  **Up**:
    - Connects to Proxmox Host via SSH.
    - Allocates next free VMID in `9000-9099`.
    - Clones `LAB_TEMPLATE_VMID` to the allocated VMID.
    - Sets Name: `lab-pve-<vmid>`.
    - Sets Tags: `ManagedBy=019a`, `RunId=<runid>`.
    - Sets IP: `10.99.0.10/24` (Static).
    - Starts VM.
    - Waits for SSH availability on `10.99.0.10` (via ProxyJump).

3.  **Test**:
    - **Tier 0**: Runs local static analysis (`terraform fmt`, `ansible-playbook --syntax-check`).
    - **Tier 1**: Runs Ansible playbook `ansible/playbooks/lab_bootstrap.yml` against `10.99.0.10`.
    - **Tier 2**: Runs Ansible playbook `ansible/playbooks/lab_tier2_pve.yml` (if `--tier 2` specified).
        - Validates PVE installation, hardening, and idempotency.
        - Performs enhanced preflight checks (Nested KVM, Network).
    - Verifies success.

4.  **Destroy**:
    - Identifies the Lab VM (by VMID or RunID).
    - **Safety Check**: Verifies VMID is in range AND has ALL Identity Markers (Name + ManagedBy + RunId).
    - Stops VM.
    - Destroys VM.

## Artifacts

The harness collects diagnostic data after every run (success or failure) to `artifacts/019-lab/<runid>/`.

- **Config**: `pveversion`, `pvesh version`, `apt-cache policy`, `systemctl status`.
- **Logs**: `journalctl` (last 1000 lines).
- **Rotation**: Automatically keeps only the last 5 run directories.

## Host Setup Prerequisites

Before the harness can be used, the production Proxmox host must be prepared one time.

### 1. SSH Access

Ensure the local machine can SSH to the Proxmox host (`root@proxmox`) without password (SSH Key). This is required for both the Ansible setup playbook and the harness itself.

### 2. Automated Setup (Bridge + Template)

Run the provided Ansible playbook to configure the `vmbr99` bridge and create the `tpl-pve-lab-base` template.

```bash
ansible-playbook ansible/playbooks/lab_setup.yml -i ansible/inventories/static/hosts.yml
```

This playbook will:
- Configure `vmbr99` with IP `10.99.0.1/24` in `/etc/network/interfaces`.
- Download the Debian 12 Cloud Image.
- Create the template VM (VMID 9001) with Cloud-Init configured.

## Safety Guardrails

The `destroy` command is the most critical operation. It must implement the following logic:

1.  **Range Check**: VMID must be 9000-9099.
2.  **Name Check**: Name must start with `lab-pve-`.
3.  **Tag Check**: Description must contain `ManagedBy=019a` AND `RunId=...`.

If ANY check fails, the operation aborts.
