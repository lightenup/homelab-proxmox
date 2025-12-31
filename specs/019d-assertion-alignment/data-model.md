# Data Model: Assertion Alignment

## Assertion Report Schema

**File**: `reports/assertions.<phase>.json`

```json
{
  "run_id": "string",
  "profile_id": "string",
  "phase": "string",
  "timestamp": "ISO8601 string",
  "assertions": [
    {
      "check_id": "string (e.g., NET-001)",
      "title": "string",
      "result": "PASS | FAIL | SKIP | ERROR",
      "reason": "string (optional, required for FAIL)",
      "remediation": "string (optional, required for FAIL)",
      "evidence_refs": ["string (path relative to evidence root)"]
    }
  ]
}
```

## Entities

### Assertion Entry

| Field | Type | Description |
| :--- | :--- | :--- |
| `check_id` | String | Unique identifier for the check (e.g., `NET-001`). |
| `title` | String | Human-readable description of the check. |
| `result` | Enum | Outcome of the assertion. |
| `reason` | String | Failure message or skip reason. |
| `remediation` | String | Actionable advice to fix the failure. |
| `evidence_refs` | Array<String> | Paths to supporting evidence (logs, screenshots, etc.). |

### Result Enum

- **PASS**: Assertion condition met.
- **FAIL**: Assertion condition not met.
- **SKIP**: Assertion not applicable or explicitly skipped.
- **ERROR**: Assertion execution failed (e.g., command error).
