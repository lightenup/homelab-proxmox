# Quickstart: Evidence Governance Strictness

## Running Self-Verification

The lab suite now automatically verifies evidence packs.

```bash
# Run the suite (verification happens automatically at the end)
scripts/lab/pve-lab suite hypervisor-nested-workload

# Skip verification (for debugging)
scripts/lab/pve-lab suite hypervisor-nested-workload --no-verify
```

## Manual Verification

You can still run verification manually on any artifact.

```bash
# Verify a specific pack
scripts/lab/pve-lab verify-evidence artifacts/019-lab/lab-20251231-121220
```

## Troubleshooting Verification Failures

If verification fails, check `reports/verify.json` in the artifact directory or look at the console output.

**Common Errors:**

*   `CAT-005 Title Mismatch`: The title in `checks.json` differs from `catalog.json`. Update the emitter (harness or Ansible) or the catalog.
*   `CAT-006 Phase Mismatch`: The phase in `checks.json` differs from `catalog.json`.
*   `OWN-004 Ansible Check Missing`: An Ansible check was reported in `checks.json` but not found in the referenced `assertions.*.json` file.

## Updating the Catalog

If you add a new check, you MUST add it to `scripts/lab/checks.d/catalog.json` before running the suite.

```json
"NEW-001": {
  "check_id": "NEW-001",
  "title": "My New Check",
  "owner": "harness",
  "phase": "bootstrap",
  "severity": "high",
  "source": "harness"
}
```
