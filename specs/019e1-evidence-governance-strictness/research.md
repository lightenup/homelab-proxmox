# Research: Evidence Governance Strictness (019e1)

## Current State Analysis

### Artifact Structure (`checks.json`)
Analysis of `artifacts/019-lab/lab-20251231-121220/checks.json` reveals:
*   **Missing Fields**: `phase` and `source` are missing from the top-level check objects.
*   **Existing Fields**: `check_id`, `title`, `severity`, `result`, `reason`, `evidence_refs`, `timestamp`.
*   **Harness Checks**: `evidence_refs` is `[""]` (empty string), which is invalid for strict governance.
*   **Ansible Checks**: `evidence_refs` correctly includes `source: ansible` and `file: assertions.*.json`.

### Harness Integration
*   **Injection Point**: `cmd_run` in `scripts/lab/pve-lab` is the main entry point.
*   **Finalization**: `evidence_finalize` is called at the end of `cmd_run`.
*   **Proposal**: Inject `cmd_verify_evidence "$artifact_dir"` immediately after `evidence_finalize`.

## Decisions

### 1. Strictness Enforcement
*   **Decision**: We will enforce `phase` and `source` presence in `checks.json`.
*   **Implication**: We must update `scripts/lab/lib/checks.sh` (or wherever `serialize_checks` lives) to include these fields from the internal `CHECKS_ARRAY`.
*   **Implication**: We must update `scripts/lab/lib/evidence.sh` (or `checks.sh`) to ensure `record_check` captures `phase` and `source`.

### 2. Harness Self-Verification
*   **Decision**: `pve-lab` will run verification by default.
*   **Flag**: Add `--no-verify` to skip it (useful for debugging or rapid dev).
*   **Failure**: If verification fails, the suite run exits with status 1, even if the tests passed. This ensures we don't produce "successful" runs with broken evidence.

### 3. Ansible Provenance
*   **Decision**: The verifier will parse the `assertions.*.json` file referenced in `evidence_refs`.
*   **Logic**:
    1.  Find `file: ...` in `evidence_refs`.
    2.  Load that JSON file.
    3.  Verify `check_id` exists in that file's keys.
*   **Benefit**: Prevents "ghost checks" where Ansible claims to have run something but didn't actually report it.

## Plan Updates
*   Added task to update `scripts/lab/lib/checks.sh` to serialize `phase` and `source`.
*   Added task to update `scripts/lab/lib/evidence.sh` to capture `phase` and `source` (if not already).
