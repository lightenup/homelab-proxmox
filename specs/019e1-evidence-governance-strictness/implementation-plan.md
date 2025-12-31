# Implementation Plan - Evidence Governance Strictness (019e1)

The goal of this feature is to enforce strict governance on Evidence Packs, making the Check Catalog the Single Source of Truth (SSOT) for titles and semantics, enforcing ownership rules, and enabling self-verification for every suite run.

## User Review Required

> [!IMPORTANT]
> **Critical Items**
> *   **Strictness Impact**: Existing packs might fail verification if they have title drift or missing phases. This is expected behavior.
> *   **Auto-Verification**: Every suite run will now take slightly longer to run the verification step at the end.
> *   **Ansible Provenance**: We are enforcing that Ansible checks *must* appear in the assertion report. This prevents "ghost checks".

- [ ] **Confirm**: Are we okay with failing the suite run if verification fails? (FR-008b says yes).

## Proposed Changes

### Technical Context

**Existing Components**:
*   `scripts/lab/verify_evidence.py`: Current verifier (needs strictness updates).
*   `scripts/lab/checks.d/catalog.json`: Current SSOT.
*   `scripts/lab/pve-lab`: Harness (needs auto-verify integration).
*   `scripts/lab/ci-verify.sh`: Offline gate (needs new fixtures).

**New Logic**:
*   **Catalog Authority**: Verifier will load catalog and compare `title`, `phase`, `severity`.
*   **Ownership Enforcement**: Verifier will parse `reports/assertions.*.json` to prove Ansible check origin.
*   **Auto-Verify**: Harness will invoke verifier before exiting.

### Constitution Check

- [x] **Spec-Driven**: All work driven by `specs/019e1-evidence-governance-strictness/spec.md`.
- [x] **Secrets Policy**: No secrets involved in verification logic.
- [x] **Separation of Concerns**: Verification is Python (data processing), Harness is Bash (orchestration).
- [x] **No Remote State**: Verification is local.

### Gates

- [ ] **Gate 1**: `research.md` approved.
- [ ] **Gate 2**: `data-model.md` and contracts approved.
- [ ] **Gate 3**: Implementation complete and verified.

## Phase 0: Research & Validation

**Goal**: Confirm current artifact structure and identify gaps for strictness.

- [ ] **Task**: Analyze current `checks.json` structure from `019e` artifacts.
    *   Does it include `phase`?
    *   Does it include `title`? (Yes, but does it match catalog?)
    *   Does it include `severity`?
- [ ] **Task**: Analyze current `evidence_refs` for Ansible checks.
    *   Do they consistently point to `assertions.<phase>.json`?
- [ ] **Task**: Identify where in `pve-lab` to inject the auto-verification step.

**Output**: `research.md`

## Phase 1: Design & Contracts

**Goal**: Define the strict validation rules and error codes.

- [ ] **Task**: Define new error codes (CAT-005, CAT-006, OWN-002, etc.) in `data-model.md`.
- [ ] **Task**: Update `catalog.json` schema definition if needed (it seems stable).

**Output**: `data-model.md`

## Phase 2: Implementation

**Goal**: Implement strictness in Verifier and Auto-Verify in Harness.

### Step 1: Fixtures & CI Gate
- [ ] **Task**: Create new invalid fixtures (`invalid-title-mismatch`, `invalid-phase-missing`, `invalid-owner-mismatch`, `invalid-ansible-ghost`).
- [ ] **Task**: Update `ci-verify.sh` to include these new fixtures.

### Step 2: Verifier Strictness
- [ ] **Task**: Update `verify_evidence.py` to enforce:
    *   Title matching (FR-005b).
    *   Phase presence and matching (FR-005c).
    *   Severity matching (FR-005d).
    *   Ownership rules (FR-007).
    *   Ansible provenance (parse assertion reports).

### Step 3: Harness Integration
- [ ] **Task**: Update `pve-lab` to run `verify-evidence` after suite completion.
- [ ] **Task**: Implement `--no-verify` flag.
- [ ] **Task**: Ensure verification result is written to `summary.json`.

### Step 4: Diff Tool Update
- [ ] **Task**: Update `diff_evidence.py` to use catalog titles for display.

## Phase 3: Verification

**Goal**: Prove the system works.

- [ ] **Task**: Run `ci-verify.sh` (must pass all new fixtures).
- [ ] **Task**: Run a real suite `pve-lab suite hypervisor-nested-workload`.
    *   Verify it auto-runs verification.
    *   Verify it passes (or fix drift if it fails).
- [ ] **Task**: Manually tamper with the generated pack (change a title) and run `verify-evidence` to confirm it fails.

## Phase 4: Documentation

- [ ] **Task**: Update `docs/operations.md` with new strictness rules and troubleshooting steps.
