---
description: "Task list for 019a-proxmox-lab-harness"
---

# Tasks: Proxmox Lab Test Harness

**Input**: Design documents from `specs/019a-proxmox-lab-harness/`
**Prerequisites**: plan.md, spec.md

## Phase 1: Design & Prerequisites

- [x] T001 Update design document `docs/architecture/019-proxmox-lab-harness.md` with new topology, VMID allocation, and strict safety rules (FR-015)
- [x] T002 Document manual setup steps (bridge `vmbr99`, template `tpl-pve-lab-base`, SSH) in the design doc
- [x] T021 Automate manual setup steps (Bridge + Template) via Ansible playbook `ansible/playbooks/lab_setup.yml`

## Phase 2: Harness Foundation (Up/Destroy)

- [x] T003 Update `scripts/lab/pve-lab` to implement locking mechanism (`flock`) and wrap `run`/`up` commands (FR-017)
- [x] T004 Implement "First Free" VMID allocation logic (9000-9099) in `pve-lab` (FR-016)

- [x] T005a Validate prod vmbr99 exists and has 10.99.0.1/24 (or otherwise L3 reachability) via SSH to prod host.(FR-011, FR-013)

- [x] T005b Ensure lab guest gets 10.99.0.10/24 using the chosen method(FR-011, FR-013):
If cloud-init: qm set <vmid> --ipconfig0 ip=10.99.0.10/24,gw=10.99.0.1 (+ verify template is cloud-init capable)
If baked-in: validate template config states the static IP (documented in design doc) and only verify reachability in up.

- [x] T006 Update `destroy` command: Enforce strict guardrails (Range + Name + ManagedBy + RunId) (FR-012)
- [x] T007 Update `status` command: Report Static IP and SSH reachability (FR-009)

## Phase 3: Inventory & Connectivity

- [x] T008 Create `ansible/inventories/lab/hosts.yml` with lab host definition
- [x] T009 Configure `ansible_ssh_common_args` for ProxyJump in lab inventory (FR-007)
- [x] T010 “Verify SSH reachability to 10.99.0.10 via ProxyJump (e.g., ssh -J root@<prod-pve> root@10.99.0.10 true) and use that as the up success condition.”

## Phase 4: Testing Logic (Tier 0 & 1)

- [x] T011 Update Tier 0 checks in `test` command: Limit to `terraform fmt` in `./terraform` and `ansible-playbook --syntax-check` on bootstrap playbook (FR-002)
- [x] T012 Create a minimal bootstrap playbook `ansible/playbooks/lab_bootstrap.yml` for Tier 1 (FR-014)
- [x] T013 Implement Tier 1 execution in `test` command (run bootstrap playbook against lab inventory)

## Phase 5: Orchestration & Artifacts

- [x] T014 Implement `run` command logic (sequence: up -> test -> destroy) (FR-004)
- [x] T015 Implement logging to `artifacts/019-lab/<runid>/` (FR-005)
- [x] T016 Generate `summary.json` at the end of the run
- [x] T017 Ensure `destroy` runs even if `test` fails (trap/finally block) (FR-006)
- [x] T018 Implement pre-run cleanup: detect any existing lab VM(s) with markers and VMID in range, destroy them with the strict guardrails before allocating a new VMID.
- [x] T019 Template validation: on up, verify qm status $LAB_TEMPLATE_VMID exists and (optionally) name matches tpl-pve-lab-base as a warning-only sanity check (VMID remains canonical).
- [x] T020 Implement full command transcript logging (stdout/stderr + exit codes + durations) to artifacts/019-lab/<runid>/run.log (and commands.jsonl) from scripts/lab/pve-lab, preserving logs on failure and redacting secrets (FR-005, FR-006)
