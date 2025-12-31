# Tasks: Lab Harness Confidence Suite

**Feature**: `019c-lab-confidence-suite`

## Phase 1: Foundational (Harness & Ansible Setup)

- [x] T001 Implement `parse_profile` and profile definitions in `scripts/lab/pve-lab`
- [x] T002 Implement `EvidencePack` functions and manifest generation in `scripts/lab/pve-lab`
- [x] T003 Create `roles/validation` for standardized reporting in `ansible/roles/validation/tasks/main.yml`

## Phase 2: User Story 1 - Validation Profiles

- [x] T004 [US1] Update `lab_tier2_pve.yml` to use `validation` role in `ansible/playbooks/lab_tier2_pve.yml`
- [x] T005 [US1] Implement `hypervisor-nested-workload` profile logic (Nested VM + Mini-Service) in `ansible/playbooks/lab_tier2_pve.yml`

## Phase 3: User Story 2 - Evidence Collection

- [x] T006 [US2] Update `collect_artifacts` to write to structured Evidence Pack (`logs/`, `config/`, `validation/`) in `scripts/lab/pve-lab`
- [x] T007 [US2] Implement `enforce_evidence_retention` (keep last 5) in `scripts/lab/pve-lab`

## Phase 4: User Story 3 - Safety & Confidence

- [x] T008 [US3] Implement `run_safety_suite` with negative tests in `scripts/lab/pve-lab`
- [x] T009 [US3] Implement `run_confidence_suite` (Safety + All Profiles + Cleanup Verification) in `scripts/lab/pve-lab`

## Phase 5: Documentation & Polish

- [x] T010 Update architecture docs with Glossary and Evidence Pack details in `docs/architecture/019-proxmox-lab-harness.md`
- [x] T011 Define "Tier 3" concept in `docs/architecture/019-proxmox-lab-harness.md`
