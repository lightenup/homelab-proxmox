---
description: "Task list for feature 019e-evidence-governance"
---

# Tasks: Evidence Governance & CI Gate

**Input**: Design documents from `specs/019e-evidence-governance/`
**Prerequisites**: `019d1` (Confidence Suite Correctness)

**Tests**:
- Offline CI tests via `scripts/lab/ci-verify.sh`
- Manual verification via `pve-lab verify-evidence` on real runs

**Organization**: Tasks are grouped by user story and implementation phase.

## Phase 1: Check Catalog & Contract Definition (P1)

**Goal**: Establish the Single Source of Truth (SSOT) and the formal contract for evidence packs.

- [ ] T001 [US2] Create `scripts/lab/checks.d/catalog.json` with initial schema and populate with existing checks (ENV, CLEANUP, NET, PVE, GUARD, NEST, WORK)
- [ ] T002 [US1] Define `contract_version` (1.0.0) and update `scripts/lab/pve-lab` to inject it into `summary.json` and `evidence_manifest.json`
- [ ] T003 [US2] Update `scripts/lab/pve-lab` to ensure harness-emitted checks include `source: "harness"`
- [ ] T004 [US2] Update `ansible/roles/assertion_utils/tasks/generate_report.yml` to ensure Ansible-emitted checks include `source: "ansible"`

## Phase 2: Evidence Verifier (P1)

**Goal**: Implement the offline verification logic using Python stdlib.

- [ ] T005 [US1] Create `scripts/lab/verify_evidence.py` skeleton with argument parsing and JSON loading
- [ ] T006 [US1] Implement `validate_structure()` in `scripts/lab/verify_evidence.py` (FR-002, FR-002a, FR-002b, FR-002c)
- [ ] T007 [US2] Implement `validate_catalog()` in `scripts/lab/verify_evidence.py` (FR-006, FR-007, FR-008, FR-006a)
- [ ] T008 [US1] Implement `validate_integrity()` in `scripts/lab/verify_evidence.py` (FR-004, FR-004a, FR-004b, FR-003, FR-003a, FR-003b)
- [ ] T009 [US1] Implement reporting in `scripts/lab/verify_evidence.py` to write `reports/verify.json` and output console summary (FR-013)
- [ ] T010 [US1] Integrate `pve-lab verify-evidence <path>` command wrapper in `scripts/lab/pve-lab`

## Phase 3: CI Gate & Fixtures (P2)

**Goal**: Enable offline validation in CI to prevent regressions.

- [ ] T011 [US3] Create fixture directory structure `scripts/lab/fixtures/evidence-packs/`
- [ ] T012 [US3] Create `valid` fixture pack (golden path) in `scripts/lab/fixtures/evidence-packs/valid/`
- [ ] T013 [US3] Create invalid fixture packs in `scripts/lab/fixtures/evidence-packs/` (`invalid-missing-file`, `invalid-bad-evidence-ref`, `invalid-duplicate-id`, `invalid-catalog-mismatch`)
- [ ] T014 [US3] Create `scripts/lab/ci-verify.sh` to lint catalog and run verifier against all fixtures (FR-012)

## Phase 4: Evidence Comparability (P2)

**Goal**: Allow operators to diff two runs.

- [ ] T015 [US4] Create `scripts/lab/diff_evidence.py` to compare two packs
- [ ] T016 [US4] Implement diff logic in `scripts/lab/diff_evidence.py` (Compare checks by ID, detect status changes, new/missing checks)
- [ ] T017 [US4] Implement reporting in `scripts/lab/diff_evidence.py` to write `reports/diff.json` and console summary (FR-009)
- [ ] T018 [US4] Integrate `pve-lab diff-evidence <runA> <runB>` command wrapper in `scripts/lab/pve-lab`

## Phase 5: Verification & Documentation

**Goal**: Verify the entire governance loop.

- [ ] T019 [US3] Run `scripts/lab/ci-verify.sh` to prove the gate works
- [ ] T020 [US1] Run a real suite `pve-lab suite hypervisor-nested-workload`, then run `verify-evidence` on the result
- [ ] T021 [US4] Run `diff-evidence` on two real runs
- [ ] T022 Update `docs/operations.md` with governance commands and catalog maintenance guide
