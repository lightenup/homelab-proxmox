# Data Model — Rebuild Acceptance Gate Hardening (020)

## Entities

### TeardownAction
- **Fields**: resource_type (vm|lxc), id (int), phase (cleanup), attempts (list of Attempt), final_status (PASS|FAIL), evidence_path (reports/cleanup/teardown-*.txt), started_at, ended_at.
- **Attempt**: command, exit_code, stdout, stderr, timestamp.
- **Relationships**: Linked from checks.json entries TEARDOWN-001/002 via evidence_refs.

### VerificationReport
- **Fields**: status (PASS|FAIL|SKIP), report_path (reports/verify.json), verifier_version, reasons (list), timestamp, contract_version.
- **Relationships**: Written by verify_evidence.py; summarized into summary.json and checks.json (existing governance rules).

### ValidationFetch (VAL-001)
- **Fields**: status (PASS|SKIP|FAIL if required), evidence_path (reports/validation.json optional), reason (if SKIP/FAIL), allow_missing (bool), phase (validation).
- **Relationships**: Catalog entry VAL-001; appears in checks.json with allow_missing semantics.

### EvidencePackSummary
- **Fields**: verification (status, report_path, verifier_version, reason if SKIP/FAIL), phases (baseline-host, baseline-templates, suite, cleanup, validation), generated_at.
- **Relationships**: summary.json; references VerificationReport and overall pack structure.

## Relationships Overview
- checks.json entries reference TeardownAction evidence (TEARDOWN-001/002) and ValidationFetch (VAL-001) artifacts.
- summary.json embeds VerificationReport fields and aligns with reports/verify.json.
- Fixtures model these entities via static evidence files for offline ci-verify.sh.
