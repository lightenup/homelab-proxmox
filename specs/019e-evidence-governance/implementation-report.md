# Implementation Report: Evidence Governance (019e)

**Date**: 2025-12-31
**Status**: Completed
**Feature**: Evidence Governance & CI Gate

## Executive Summary

We have successfully implemented a governance layer for the lab suite's evidence artifacts. This ensures that every lab run produces valid, complete, and compliant evidence packs that can be automatically verified and compared.

## Components Delivered

### 1. Check Catalog (SSOT)
*   **Location**: `scripts/lab/checks.d/catalog.json`
*   **Purpose**: Defines the Single Source of Truth for all checks (ID, Title, Severity, Owner).
*   **Status**: Populated with all checks from the `hypervisor-nested-workload` suite.

### 2. Evidence Verifier
*   **Location**: `scripts/lab/verify_evidence.py`
*   **Capabilities**:
    *   **Structure**: Validates JSON schema of `summary.json` and `checks.json`.
    *   **Catalog Compliance**: Ensures every check in the output is defined in the catalog.
    *   **Integrity**: Verifies that every file referenced in `evidence_refs` actually exists in the pack.
    *   **Wrapper Support**: Handles both raw list and wrapper-object formats for `checks.json`.

### 3. CI Verification Gate
*   **Location**: `scripts/lab/ci-verify.sh`
*   **Purpose**: Prevents regressions in the verifier or catalog.
*   **Fixtures**: `scripts/lab/fixtures/evidence-packs/` contains 5 scenarios (1 valid, 4 invalid).
*   **Result**: CI Gate passes all scenarios.

### 4. Evidence Diff Tool
*   **Location**: `scripts/lab/diff_evidence.py`
*   **Purpose**: Allows operators to compare two lab runs to detect drift or regressions.
*   **Output**: Generates a JSON report and a console summary of status changes (e.g., PASS -> FAIL).

### 5. Integration
*   **CLI**: `pve-lab` updated with new subcommands:
    *   `pve-lab verify-evidence <path>`
    *   `pve-lab diff-evidence <pathA> <pathB>`
*   **Documentation**: `docs/operations.md` updated with usage instructions.

## Verification Evidence

### CI Gate Output
```text
=== CI Verification Gate ===
Linting Catalog: .../scripts/lab/checks.d/catalog.json
PASS: Catalog JSON is valid
Running Fixtures...
Testing invalid-bad-evidence-ref... OK (Invalid pack rejected)
Testing invalid-catalog-mismatch... OK (Invalid pack rejected)
Testing invalid-duplicate-id... OK (Invalid pack rejected)
Testing invalid-missing-file... OK (Invalid pack rejected)
Testing valid... OK (Valid pack accepted)
CI Verification Passed
```

### Real Artifact Verification
Verified against artifact `artifacts/019-lab/lab-20251231-121220`. The tool correctly identified missing evidence files (expected for pre-governance artifacts) and validated the catalog definitions.

## Next Steps
1.  **Enforcement**: Add `scripts/lab/ci-verify.sh` to the project's main CI pipeline.
2.  **Maintenance**: Developers adding new checks must now register them in `catalog.json`.
