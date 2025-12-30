# Implementation Plan - Proxmox Lab Test Harness

**Feature**: 019a-proxmox-lab-harness
**Goal**: Create a repeatable, ephemeral test environment for Proxmox infrastructure.

## Phase 1: Design & Prerequisites
**Goal**: Define the architecture and document manual setup steps.
- [ ] Create design document `docs/architecture/019-proxmox-lab-harness.md` (FR-015).
- [ ] Document manual setup steps (bridge `vmbr99`, template `tpl-pve-lab-base`, SSH keys) in the design doc.
- [ ] (Manual) Perform the one-time setup on the production host.

## Phase 2: Harness Foundation (Up/Destroy)
**Goal**: Script can create and destroy the lab host safely with locking and dynamic VMID.
- [ ] Update `scripts/lab/pve-lab` to support locking (FR-017).
- [ ] Implement "First Free" VMID allocation strategy (9000-9099) (FR-016).
- [ ] Update `up` command: Clone template, set Identity Markers (Name + ManagedBy + RunId) (FR-011).
- [ ] Update `destroy` command: Enforce strict guardrails (Range + Name + ManagedBy + RunId) (FR-012).
- [ ] Update `status` command: Report Static IP and SSH reachability (FR-009).

## Phase 3: Inventory & Connectivity
**Goal**: Ansible can talk to the lab host via ProxyJump.
- [ ] Create `ansible/inventories/lab/hosts.yml`.
- [ ] Configure SSH ProxyJump in Ansible inventory/vars (FR-007).
- [ ] Verify Ansible connectivity (`ansible -i ... -m ping`).

## Phase 4: Testing Logic (Tier 0 & 1)
**Goal**: Harness can run deterministic static checks and basic convergence.
- [ ] Update `test` command in `pve-lab`.
- [ ] Refine Tier 0 checks: `terraform fmt` (limited scope) and `ansible-playbook --syntax-check` (specific playbooks) (FR-002).
- [ ] Add Tier 1 checks (Run `ansible/playbooks/lab_bootstrap.yml` against lab host) (FR-014).

## Phase 5: Orchestration & Artifacts
**Goal**: Full automated run with reporting.
- [ ] Implement `run` command (Up -> Test -> Destroy) (FR-004).
- [ ] Implement artifact generation (logs, `summary.json`) (FR-005).
- [ ] Ensure unique Run IDs (`lab-YYYYMMDD-HHMMSS`).
- [ ] Verify fail-safe behavior (artifacts preserved on failure, destroy runs) (FR-006).
