# Quickstart — Rebuild Acceptance Gate Hardening (020)

1) Run rebuild with verification (lab host):
- `pve-lab rebuild --profile rebuild-hypervisor-nested-workload --apply --verify`
- Expect TEARDOWN-001/002 evidence under `reports/cleanup/`, VAL-001 listed as PASS or SKIP (allow_missing), and verify.json + summary.verification populated.

2) Run rebuild without verification (explicit skip):
- `pve-lab rebuild --profile rebuild-hypervisor-nested-workload --apply --no-verify`
- Expect summary.verification.status=SKIP with reason; no "verification skipped" WARN from suite.

3) Offline verification of fixtures:
- `scripts/lab/ci-verify.sh` (runs all fixtures including new teardown/verification cases)
- Confirm expected PASS/FAIL outcomes without WARN spam for optional validation fetch.

4) Validate optional validation report behavior:
- Simulate unavailable validation endpoint; run rebuild; ensure VAL-001 is SKIP with reason, no WARN in console, checks.json remains contract-valid.
