# Tasks: Lab Harness Tier 2

**Feature**: `019b-proxmox-lab-harness-tier2`
**Status**: In Progress

## Phase 1: Setup & Prerequisites
*Goal: Ensure environment is ready for Tier 2 development.*

- [x] T001 Define `LAB_TEMPLATE_VMID_TIER2` default in `scripts/lab/pve-lab` and document requirement.

## Phase 2: Foundational (Harness CLI & Logic)
*Goal: Update the harness to support new flags and lifecycle logic.*

- [x] T002 Update `scripts/lab/pve-lab` argument parsing for `--tier`, `--tier2-mode`, `--keep`.
- [x] T003 Implement resource floor enforcement (4GB RAM, 2 vCPU) in `scripts/lab/pve-lab`.
- [x] T004 Implement template selection logic (Tier 1 vs Tier 2) in `scripts/lab/pve-lab`.
- [x] T005 Update `destroy` function in `scripts/lab/pve-lab` to respect `--keep` flag.

## Phase 3: User Story 1 (Tier 2 Min - Playbook)
*Goal: Implement the Ansible playbook for Proxmox VE installation and verification.*

- [x] T006 [US1] Create `ansible/playbooks/lab_tier2_pve.yml` with inventory and hostname guards.
- [x] T007 [US1] Add OS (Debian 13) and Hostname Resolution checks to `ansible/playbooks/lab_tier2_pve.yml`.
- [x] T008 [US1] Implement Proxmox Repo setup (Keyring, No-Sub) in `ansible/playbooks/lab_tier2_pve.yml`.
- [x] T009 [US1] Implement Non-interactive Install (PVE, Postfix preseed) in `ansible/playbooks/lab_tier2_pve.yml`.
- [x] T010 [US1] Implement Service (proxy, daemon, cluster) & API Validation in `ansible/playbooks/lab_tier2_pve.yml`.
- [x] T011 [US1] Update `scripts/lab/pve-lab` to execute `lab_tier2_pve.yml` when tier >= 2.
- [x] T012 [US1] Update `scripts/lab/pve-lab` to capture `tier2.log` and update `summary.json`.

## Phase 4: User Story 3 (Tier 2 Plus - Nested Virt)
*Goal: Add support for nested virtualization testing.*

- [x] T013 [US3] Implement Host Nested KVM preflight check in `scripts/lab/pve-lab`.
- [x] T014 [US3] Implement Guest `/dev/kvm` preflight check in `scripts/lab/pve-lab`.
- [x] T015 [US3] Add nested VM smoke test to `ansible/playbooks/lab_tier2_pve.yml` (conditional on `tier2_mode=plus`).

## Dependencies
- US1 (Tier 2 Min) must be completed before US3 (Tier 2 Plus).
- Phase 2 (Harness) is a prerequisite for executing Phase 3 (Playbook).

## Implementation Strategy
1.  **Harness First**: Update `pve-lab` to handle the new flags and flow control.
2.  **Playbook Iteration**: Build the playbook step-by-step (Repo -> Install -> Verify), testing with `pve-lab run --tier 2 --keep`.
3.  **Nested Virt**: Add the "Plus" mode features last.
