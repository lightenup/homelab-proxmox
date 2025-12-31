# Data Model: Evidence Governance Strictness (019e1)

## Error Codes (Verifier)

| Code | Category | Title | Description | Remediation |
| :--- | :--- | :--- | :--- | :--- |
| **CAT-005** | Catalog | Title Mismatch | Check title in `checks.json` differs from Catalog SSOT. | Update emitter to match catalog or remove title from emitter. |
| **CAT-006** | Catalog | Phase Mismatch | Check phase in `checks.json` differs from Catalog SSOT. | Update emitter to match catalog. |
| **CAT-007** | Catalog | Phase Missing | Check entry in `checks.json` is missing `phase` field. | Update emitter to include phase. |
| **CAT-008** | Catalog | Severity Mismatch | Check severity in `checks.json` differs from Catalog SSOT. | Update emitter to match catalog. |
| **OWN-003** | Ownership | Source Mismatch | `source` field does not match Catalog `owner`. | Ensure `source` is "ansible" for ansible-owned checks, etc. |
| **OWN-004** | Ownership | Ansible Provenance | Ansible check not found in referenced assertion report. | Ensure Ansible task actually ran and generated the assertion. |
| **OWN-005** | Ownership | Harness Provenance | Harness check references assertion report as primary evidence. | Harness checks should not claim to be from Ansible. |

## Schema Updates

### `checks.json`

The `checks` array objects MUST now include:

```json
{
  "check_id": "ENV-001",
  "title": "...",
  "phase": "bootstrap",       // NEW: Required, must match catalog
  "source": "harness",        // NEW: Required, "harness" or "ansible"
  "severity": "blocker",
  "result": "PASS",
  ...
}
```

### `summary.json`

The summary object will include verification status:

```json
{
  ...
  "verification": {
    "status": "PASS",       // "PASS" | "FAIL" | "SKIP"
    "report_path": "reports/verify.json"
  }
}
```
