# Contract: Verification Output and Summary

## Purpose
Standardize verification artifacts so rebuild and suite produce unambiguous, machine-readable outputs.

## Artifacts
- `reports/verify.json` (machine-readable result from verify_evidence.py)
- Optional `reports/verify.txt` (human-readable)
- `summary.json` verification block

## verify.json Schema (minimal)
- status: PASS | FAIL | SKIP
- verifier_version: string
- contract_version: string (existing governance field)
- reasons: array[string] (present for FAIL/SKIP)
- timestamp: ISO-8601

## summary.json Verification Block
- summary.verification.status: PASS | FAIL | SKIP
- summary.verification.report_path: string (default `reports/verify.json`)
- summary.verification.verifier_version: string
- summary.verification.reason: string (if SKIP/FAIL)

## Behavior Rules
- If rebuild intends to verify, suite suppresses "verification skipped" warnings and logs deferral as info.
- When `--no-verify` is set, status = SKIP with reason; no WARN in console.
- Verification failure sets non-zero exit and aligns verify.json and summary.json.
