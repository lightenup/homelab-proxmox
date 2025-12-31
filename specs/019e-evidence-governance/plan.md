# Implementation Plan - Evidence Governance & CI Gate

**Feature**: `019e-evidence-governance`
**Status**: Draft

## Phase 1: Check Catalog & Contract Definition (P1)

**Goal**: Establish the Single Source of Truth (SSOT) and the formal contract for evidence packs.

- [ ] T001 Create `scripts/lab/checks.d/catalog.json` with initial schema and populate with existing checks (ENV, CLEANUP, NET, PVE, GUARD, NEST, WORK).
- [ ] T002 Define `contract_version` (1.0.0) and update `scripts/lab/pve-lab` to inject it into `summary.json` and `evidence_manifest.json`.
- [ ] T003 Update `scripts/lab/pve-lab` and `ansible/roles/assertion_utils` to ensure all emitted checks include `source: "harness"|"ansible"`.

## Phase 2: Evidence Verifier (P1)

**Goal**: Implement the offline verification logic using Python stdlib.

- [ ] T004 Create `scripts/lab/verify_evidence.py` skeleton with argument parsing and JSON loading.
- [ ] T005 Implement `validate_structure()`: Check required files (FR-002), JSON parsing (FR-002a), and Run ID/Profile coherence (FR-002b/c).
- [ ] T006 Implement `validate_catalog()`: Check ID existence (FR-006), ownership (FR-007), phase (FR-008), and deprecation (FR-006a).
- [ ] T007 Implement `validate_integrity()`: Check ID uniqueness (FR-004/a/b) and evidence reference paths (FR-003/a/b).
- [ ] T008 Implement reporting: Write `reports/verify.json` and output console summary (FR-013).
- [ ] T009 Integrate `pve-lab verify-evidence <path>` command wrapper.

## Phase 3: CI Gate & Fixtures (P2)

**Goal**: Enable offline validation in CI to prevent regressions.

- [ ] T010 Create fixture directory structure `scripts/lab/fixtures/evidence-packs/`.
- [ ] T011 Create `valid` fixture pack (golden path).
- [ ] T012 Create invalid fixture packs: `invalid-missing-file`, `invalid-bad-evidence-ref`, `invalid-duplicate-id`, `invalid-catalog-mismatch`.
- [ ] T013 Create `scripts/lab/ci-verify.sh` to lint catalog and run verifier against all fixtures (FR-012).

## Phase 4: Evidence Comparability (P2)

**Goal**: Allow operators to diff two runs.

- [ ] T014 Create `scripts/lab/diff_evidence.py` (or add to verify script) to compare two packs.
- [ ] T015 Implement diff logic: Compare checks by ID, detect status changes, new/missing checks.
- [ ] T016 Implement reporting: Write `reports/diff.json` and console summary (FR-009).
- [ ] T017 Integrate `pve-lab diff-evidence <runA> <runB>` command wrapper.

## Phase 5: Verification & Documentation

**Goal**: Verify the entire governance loop.

- [ ] T018 Run `ci-verify.sh` to prove the gate works.
- [ ] T019 Run a real suite `pve-lab suite hypervisor-nested-workload`, then run `verify-evidence` on the result.
- [ ] T020 Run `diff-evidence` on two real runs.
- [ ] T021 Update `docs/operations.md` with governance commands and catalog maintenance guide.
