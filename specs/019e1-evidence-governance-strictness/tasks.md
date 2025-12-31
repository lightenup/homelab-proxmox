---
description: "Task list for feature 019e1-evidence-governance-strictness"
---

# Tasks: Evidence Governance Strictness

**Input**: Design documents from `specs/019e1-evidence-governance-strictness/`
**Prerequisites**: `019e` (Evidence Governance)

**Tests**:
- Offline CI tests via `scripts/lab/ci-verify.sh`
- Manual verification via `pve-lab suite ...` (auto-verify)

## Phase 1: Verifier Strictness (P1)

**Goal**: Update the verifier to enforce strict catalog compliance and ownership rules.

- [x] T001 [US1] Update `scripts/lab/verify_evidence.py` to enforce `phase` and `source` presence in `checks.json` (FR-005c, FR-007a)
- [x] T002 [US1] Update `scripts/lab/verify_evidence.py` to validate `title`, `phase`, `severity` against catalog (FR-005b, FR-005c, FR-005d)
- [x] T003 [US3] Update `scripts/lab/verify_evidence.py` to enforce ownership rules (FR-007b, FR-007c, FR-007d)

## Phase 2: Harness Updates (P1)

**Goal**: Ensure the harness emits compliant evidence and runs self-verification.

- [x] T004 [US2] Update `scripts/lab/lib/checks.sh` to include `phase` and `source` in serialized JSON output
- [x] T005 [US2] Update `scripts/lab/lib/evidence.sh` `record_check` to accept/pass `phase` and `source`
- [x] T006 [US4] Update `scripts/lab/pve-lab` to support `--no-verify` flag
- [x] T007 [US4] Update `scripts/lab/pve-lab` to run `verify-evidence` automatically and record result in `summary.json` (FR-008, FR-008d)

## Phase 3: Diff Tool Updates (P2)

**Goal**: Ensure diff tool remains usable even if titles are missing in packs.

- [x] T008 [US5] Update `scripts/lab/diff_evidence.py` to load catalog for title resolution and enforce profile_id match (FR-009, FR-010)

## Phase 4: Fixtures & Verification (P1)

**Goal**: Validate the strictness rules with negative tests.

- [x] T009 [US5] Create `invalid-title-mismatch` fixture
- [x] T010 [US5] Create `invalid-phase-missing` fixture
- [x] T011 [US5] Create `invalid-owner-mismatch` fixture
- [x] T012 [US5] Create `invalid-ansible-check-not-in-assertion-report` fixture
- [x] T013 [US5] Run `scripts/lab/ci-verify.sh` to validate new fixtures
- [x] T014 [US4] Run real suite `pve-lab suite hypervisor-nested-workload` and verify auto-verification works
