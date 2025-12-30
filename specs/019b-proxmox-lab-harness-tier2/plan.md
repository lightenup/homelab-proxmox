# Implementation Plan: Lab Harness Tier 2

**Branch**: `019b-proxmox-lab-harness-tier2` | **Date**: 2025-12-30 | **Spec**: [specs/019b-proxmox-lab-harness-tier2/spec.md](specs/019b-proxmox-lab-harness-tier2/spec.md)
**Input**: Feature specification from `specs/019b-proxmox-lab-harness-tier2/spec.md`

## Summary

Extend the `pve-lab` harness to support "Tier 2" testing, which simulates a Proxmox host environment within the lab. This involves adding CLI flags (`--tier`, `--tier2-mode`, `--keep`), enforcing resource floors, and creating an Ansible playbook to install and verify Proxmox VE 9 (Debian 13) services and API availability in a safe, isolated environment.

## Technical Context

**Language/Version**: Bash (Harness), Ansible 2.14+ (Playbooks)
**Primary Dependencies**: `pve-lab` script, Proxmox VE 9 (Debian 13) repositories
**Storage**: Local VM storage (LVM/ZFS within Lab VM)
**Testing**: `pve-lab run --tier 2` (End-to-end integration test)
**Target Platform**: Debian 13 (Trixie) VM running on Proxmox VE 8 Host
**Project Type**: Infrastructure Automation / Testing Harness
**Performance Goals**: Tier 2 execution < 15 minutes
**Constraints**: Must not affect production host; Must run non-interactively
**Scale/Scope**: Single Lab VM instance

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

*   **Spec-Driven Workflow**: Compliant. Spec is defined in `specs/019b-proxmox-lab-harness-tier2/spec.md`.
*   **Secrets Policy**: Compliant. No secrets required for public Proxmox repos.
*   **Separation of Concerns**: Compliant. Harness manages VM lifecycle; Ansible manages OS/App config.
*   **Provider Strategy**: N/A. Harness uses direct SSH/QM commands for lab management.
*   **Networking**: Compliant. Uses isolated `vmbr99` (10.99.0.0/24).
*   **Access Control**: Compliant. Uses SSH keys.
*   **State Management**: N/A. Lab is ephemeral.

## Project Structure

### Documentation (this feature)

```text
specs/019b-proxmox-lab-harness-tier2/
├── plan.md              # This file
├── spec.md              # Feature specification
└── checklists/
    └── requirements.md  # Quality checklist
```

### Source Code (repository root)

```text
scripts/
└── lab/
    └── pve-lab          # Harness script updates

ansible/
├── playbooks/
│   └── lab_tier2_pve.yml # New Tier 2 playbook
└── inventories/
    └── lab/
        └── hosts.yml    # Existing lab inventory
```

**Structure Decision**: Extend existing `scripts/lab/pve-lab` and add new playbook in `ansible/playbooks/`.

## Phase 0: Outline & Research

*   **Research Task 1**: Confirm Debian 13 (Trixie) cloud image availability or creation process for `LAB_TEMPLATE_VMID_TIER2`.
*   **Research Task 2**: Verify `proxmox-archive-keyring` package availability in Debian 13 or fallback to GPG key download.
*   **Research Task 3**: Validate `kvm_intel` nested parameters on the specific production hardware (Intel NUC/Mini PC).

## Phase 1: Design & Contracts

### Harness CLI Interface
*   `pve-lab run --tier <1|2>`
*   `pve-lab run --tier 2 --tier2-mode <min|plus>`
*   `pve-lab run --keep`

### Ansible Variables (Contracts)
*   `lab_inventory`: boolean (Guard)
*   `pve_repository_url`: string (Proxmox repo URL)
*   `pve_keyring_path`: string (Path to keyring)

## Phase 2: Implementation Tasks

### 1. Harness Updates (`scripts/lab/pve-lab`)
*   [ ] Add argument parsing for `--tier`, `--tier2-mode`, `--keep`.
*   [ ] Implement `LAB_TEMPLATE_VMID_TIER2` selection logic.
*   [ ] Implement resource floor checks (4GB RAM, 2 vCPU).
*   [ ] Update `run` function to execute Tier 2 playbook if tier >= 2.
*   [ ] Implement `destroy` logic updates (respect `--keep`).
*   [ ] Implement Tier 2-plus preflight checks (Host nested KVM, Lab VM `/dev/kvm`).

### 2. Tier 2 Playbook (`ansible/playbooks/lab_tier2_pve.yml`)
*   [ ] Create playbook skeleton with `hosts: lab_hosts`.
*   [ ] Add **Guards**:
    *   Inventory check (`lab_inventory`).
    *   Hostname check (`lab-pve-*`).
    *   OS check (Debian 13).
    *   Hostname resolution check (`hostname -f`, `/etc/hosts`).
*   [ ] Add **Repo Setup**:
    *   Install `proxmox-archive-keyring` or download key.
    *   Configure `sources.list.d/pve-install-repo.list`.
    *   Remove enterprise repo.
*   [ ] Add **Install Tasks**:
    *   Preseed `postfix`.
    *   Install `proxmox-ve`, `postfix`, `open-iscsi` (non-interactive).
*   [ ] Add **Validation Tasks**:
    *   Check services (`pveproxy`, `pvedaemon`, `pve-cluster`).
    *   Check `/etc/pve` mountpoint.
    *   Check API (`curl localhost:8006`).
    *   Capture `pveversion`.

### 3. Integration & Verification
*   [ ] Verify `pve-lab run --tier 2` (Tier 2 Min) succeeds.
*   [ ] Verify `pve-lab run --tier 2 --keep` leaves VM running.
*   [ ] Verify `pve-lab run --tier 2 --tier2-mode plus` (if hardware allows).
*   [ ] Verify resource floor enforcement (try with small template).
*   [ ] Verify OS gate (try with wrong OS template).
