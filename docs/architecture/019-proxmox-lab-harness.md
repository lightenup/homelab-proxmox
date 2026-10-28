# Architecture: Proxmox Lab Test Harness

**Feature**: 019c1-semantic-safety-closure
**Status**: Active
**Last Updated**: 2025-12-31

> **Scope note (2026-10-28):** this harness (`pve-lab`, the nested VM rig on `vmbr99`) is **not**
> what the service pipeline's "LAB" stage uses. `pve-service-deploy --environment lab` deploys
> per-service LXCs to the **production** host, bridge, IPs and Terraform state. The isolated
> topology below applies to the harness only. See
> [`docs/backlog/067`](../backlog/067-lab-prod-same-address-space.md).

## Overview

The Proxmox Lab Test Harness is a local CLI tool (`pve-lab`) that orchestrates the creation, testing, and destruction of ephemeral Proxmox environments. It enables safe, repeatable infrastructure testing without risking the production environment.

The system uses a **Profile-Driven** approach to validation, producing **Evidence Packs** that contain machine-readable proof of results, safety guardrails, and cleanup.

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

3.  **Test (Profile Execution)**:
    - Loads the selected **Profile** (e.g., `hypervisor-nested-workload`).
    - Executes defined phases (Bootstrap, Tier 2, Validation).
    - Records **Checks** (PASS/FAIL) for every validation step.
    - Emits real-time JSONL events for monitoring.

4.  **Destroy**:
    - Identifies the Lab VM (by VMID or RunID).
    - **Safety Check**: Verifies VMID is in range AND has ALL Identity Markers (Name + ManagedBy + RunId).
    - Stops VM.
    - Destroys VM.

5.  **Evidence**:
    - Generates an **Evidence Pack** containing all artifacts, logs, and provenance data.

## Validation Profiles

Profiles are the primary way to define what to test. They replace the legacy "Tier" concept.

| Profile ID | Display Name | Description | Legacy Equivalent |
| :--- | :--- | :--- | :--- |
| **hypervisor-control-plane** | Hypervisor Control Plane | Installs and verifies the PVE control plane on Debian 13. Includes hardening and API checks. | Tier 2 (Min) |
| **hypervisor-nested-workload** | Hypervisor Nested Workload | Control plane + Nested VM + Nested LXC. Verifies KVM module and network bridging for workloads. | Tier 2 (Plus) |

### Profile Definition Example
```bash
profile_id="hypervisor-nested-workload"
display_name="Hypervisor Nested Workload"
tier=2
mode="plus"
safety_level="standard"
expected_duration_minutes=10
prerequisites=("pve_host" "nested_kvm")
```

### Console Output Example
```text
[PASS] PVE-001: Proxmox VE packages installed
[PASS] PVE-002: PVE services running
[PASS] NET-001: DNS resolution working
[PASS] NEST-001: Host KVM module supports nesting
...
[PASS] CLEANUP-001: No lab VMs remain in range
```

## Check Catalog

Checks are stable validation units with consistent IDs.

| Namespace | Description | Examples |
| :--- | :--- | :--- |
| **PVE-###** | Proxmox VE Installation | `PVE-001` (Packages), `PVE-005` (Version) |
| **NET-###** | Network Configuration | `NET-001` (DNS), `NET-003` (Bridge) |
| **NEST-###** | Nested Virtualization | `NEST-001` (KVM Module), `NEST-003` (Nested VM) |
| **WORK-###** | Workload Deployment | `WORK-001` (LXC Template), `WORK-004` (Service Reachability) |
| **GUARD-###** | Safety Guardrails | `GUARD-001` (Inventory Lock), `GUARD-003` (Destroy Safety) |
| **CLEANUP-###** | Cleanup Verification | `CLEANUP-001` (No Lab VMs), `CLEANUP-002` (No Locks) |

## Evidence Packs

Every run produces a structured directory at `artifacts/019-lab/<runid>/`.

### Core Artifacts

1.  **`checks.json`**: The canonical checklist results.
    ```json
    {
      "schema_version": "1.0.0",
      "checks": [
        {
          "check_id": "PVE-001",
          "title": "Proxmox VE packages installed",
          "result": "PASS",
          "timestamp": "2025-12-31T12:00:00Z"
        }
      ]
    }
    ```

2.  **`provenance.json`**: The exact context of the run.
    ```json
    {
      "controller": { "os": "Darwin", "git_commit": "a1b2c3d" },
      "target": { "pveversion": "8.1.3", "kernel": "6.5.11" },
      "parameters": { "profile": "hypervisor-nested-workload" }
    }
    ```

3.  **`summary.json`**: High-level results for quick parsing.
    ```json
    {
      "runid": "lab-20251231-120000",
      "profile": "hypervisor-nested-workload",
      "status": "success",
      "duration_seconds": 450
    }
    ```

4.  **`evidence_manifest.json`**: Inventory of all files in the pack.

## Migration Guide

Legacy flags are deprecated but supported via transparent mapping.

| Legacy Command | New Command |
| :--- | :--- |
| `pve-lab run --tier 2` | `pve-lab suite hypervisor-control-plane` |
| `pve-lab run --tier 2 --tier2-mode plus` | `pve-lab suite hypervisor-nested-workload` |

## Safety Guardrails

The `destroy` command is the most critical operation. It must implement the following logic:

1.  **Range Check**: VMID must be 9000-9099.
2.  **Name Check**: Name must start with `lab-pve-`.
3.  **Tag Check**: Description must contain `ManagedBy=019a` AND `RunId=...`.

If ANY check fails, the operation aborts.

## Host Setup Prerequisites

Before the harness can be used, the production Proxmox host must be prepared one time.

### 1. SSH Access

Ensure the local machine can SSH to the Proxmox host (`root@proxmox`) without password (SSH Key). This is required for both the Ansible setup playbook and the harness itself.

### 2. Automated Setup (Bridge + Template)

Run the provided Ansible playbook to configure the `vmbr99` bridge and create the `tpl-pve-lab-base` template.

```bash
ansible-playbook ansible/playbooks/lab_setup.yml -i ansible/inventories/static/hosts.yml
```
