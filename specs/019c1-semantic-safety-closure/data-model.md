# Data Model: Semantic & Safety Closure

**Date**: 2025-12-31  
**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Research**: [research.md](./research.md)

## Overview

This document defines the concrete data structures for Profiles, Checks, Evidence Packs, Provenance, and JSONL Events. All structures are designed for machine readability, human comprehensibility, and historical comparability.

---

## Entity 1: Profile

**Purpose**: Named validation intent that declares prerequisites, execution phases, and expected checks.

### Fields

| Field | Type | Required | Constraints | Description |
|-------|------|----------|-------------|-------------|
| `profile_id` | string | ✅ | kebab-case, unique | Stable identifier (e.g., "hypervisor-nested-workload") |
| `display_name` | string | ✅ | 1-100 chars | Human-readable name |
| `tier` | integer | ✅ | 0-9 | Numeric tier (maps to legacy concept) |
| `mode` | string | ✅ | min\|plus\|custom | Mode within tier |
| `safety_level` | string | ✅ | standard\|strict | Guardrail enforcement level |
| `expected_duration_minutes` | integer | ✅ | 1-120 | Target execution time (informational) |
| `prerequisites` | array[string] | ✅ | 0-20 items | Host capability checks (e.g., "nested-kvm") |
| `checks` | array[string] | ✅ | 1-100 items | Check IDs this profile expects to execute |
| `phases` | array[object] | ✅ | 1-10 items | Execution phases with playbook/script paths |

### Phase Object Schema

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | ✅ | Phase name (e.g., "bootstrap", "tier2") |
| `type` | string | ✅ | playbook\|script\|role |
| `path` | string | ✅ | Relative path from repo root |

### Relationships

- Profile → [Check IDs] (declares expected checks)
- Profile → [Phases] (defines execution order)

### Validation Rules

1. `profile_id` MUST match `/^[a-z][a-z0-9-]*$/` (kebab-case)
2. `checks` array MUST NOT be empty
3. All check IDs in `checks` MUST match pattern `/^[A-Z]+-[0-9]{3}$/`
4. `phases` array MUST have at least one entry
5. All phase paths MUST exist in repository

### State Transitions

N/A (profiles are declarative, immutable definitions)

### Example

```json
{
  "profile_id": "hypervisor-nested-workload",
  "display_name": "Hypervisor with Nested Workload Validation",
  "tier": 2,
  "mode": "plus",
  "safety_level": "strict",
  "expected_duration_minutes": 10,
  "prerequisites": [
    "nested-kvm",
    "min-memory-4g"
  ],
  "checks": [
    "PVE-001", "PVE-002", "NET-001", "NEST-001",
    "WORK-001", "GUARD-001", "CLEANUP-001"
  ],
  "phases": [
    {"name": "bootstrap", "type": "playbook", "path": "ansible/playbooks/lab_bootstrap.yml"},
    {"name": "tier2", "type": "playbook", "path": "ansible/playbooks/lab_tier2_pve.yml"},
    {"name": "validation", "type": "role", "path": "ansible/roles/validation/tasks/main.yml"},
    {"name": "guardrails", "type": "script", "path": "scripts/lab/guardrails.sh"},
    {"name": "cleanup", "type": "script", "path": "scripts/lab/lib/cleanup.sh"}
  ]
}
```

---

## Entity 2: Check

**Purpose**: Stable validation unit with consistent pass/fail semantics and evidence linkage.

### Fields

| Field | Type | Required | Constraints | Description |
|-------|------|----------|-------------|-------------|
| `check_id` | string | ✅ | Namespace-### pattern | Stable, immutable identifier (e.g., "PVE-001") |
| `title` | string | ✅ | 10-100 chars | Human-readable description |
| `severity` | string | ✅ | blocker\|high\|medium\|low | Failure impact level |
| `expected` | string | ✅ | PASS\|FAIL | Expected outcome (supports negative tests) |
| `result` | string | ✅ | PASS\|FAIL\|SKIP\|ERROR | Actual outcome |
| `reason` | string | ✅ | 0-500 chars | Explanation of result (why passed/failed) |
| `evidence_refs` | array[string] | ❌ | 0-10 items | Relative paths to artifacts in evidence pack |
| `timestamp` | string | ✅ | ISO 8601 | When check completed (UTC) |
| `duration_ms` | integer | ❌ | 0-3600000 | Execution time in milliseconds |

### Relationships

- Check → [Evidence Artifacts] (via `evidence_refs`)
- Profile → [Checks] (via check_id references)

### Validation Rules

1. `check_id` MUST match `/^[A-Z]+-[0-9]{3}$/` (e.g., "PVE-001", "GUARD-003")
2. `result` MUST be one of: PASS, FAIL, SKIP, ERROR
3. `expected` MUST be one of: PASS, FAIL
4. If `result != expected` and `expected == FAIL`, set `result = ERROR` (guardrail breach)
5. If `severity == "blocker"` and `result == FAIL`, suite MUST abort
6. `timestamp` MUST be valid ISO 8601 format
7. `evidence_refs` paths MUST be relative to evidence pack root

### State Transitions

```
(not started) → (executing) → (completed: PASS/FAIL/SKIP/ERROR)
```

### Special Semantics

**Negative Tests**:
- `expected: FAIL` indicates this check validates a safety guardrail
- `result: FAIL` with `expected: FAIL` → Success (guard worked)
- `result: PASS` with `expected: FAIL` → ERROR (guard failed, safety hole)

**Blocker Severity**:
- Any check with `severity: blocker` and `result: FAIL` aborts suite immediately
- Lower severity checks continue execution to maximize diagnostic information

### Example (Positive Test)

```json
{
  "check_id": "PVE-002",
  "title": "PVE services running (pveproxy, pvedaemon, pve-cluster)",
  "severity": "high",
  "expected": "PASS",
  "result": "PASS",
  "reason": "All services active and running",
  "evidence_refs": ["reports/systemctl-status.txt"],
  "timestamp": "2025-12-31T12:34:56Z",
  "duration_ms": 234
}
```

### Example (Negative Test)

```json
{
  "check_id": "GUARD-001",
  "title": "Tier2 playbook rejects execution without lab_inventory=true",
  "severity": "blocker",
  "expected": "FAIL",
  "result": "FAIL",
  "reason": "Playbook correctly aborted with assertion: lab_inventory must be true",
  "evidence_refs": ["logs/guard-001-attempt.log"],
  "timestamp": "2025-12-31T12:35:23Z",
  "duration_ms": 145
}
```

---

## Entity 3: Checks Collection

**Purpose**: Array of all checks executed in a suite run, with metadata.

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `runid` | string | ✅ | Evidence pack identifier (lab-YYYYMMDD-HHMMSS) |
| `profile` | string | ✅ | Profile ID that was executed |
| `checks_count` | integer | ✅ | Total number of checks |
| `passed_count` | integer | ✅ | Checks with result=PASS |
| `failed_count` | integer | ✅ | Checks with result=FAIL (unexpected failures only) |
| `skipped_count` | integer | ✅ | Checks with result=SKIP |
| `error_count` | integer | ✅ | Checks with result=ERROR |
| `checks` | array[Check] | ✅ | Array of check objects |

### Example

```json
{
  "runid": "lab-20251231-123456",
  "profile": "hypervisor-nested-workload",
  "checks_count": 27,
  "passed_count": 24,
  "failed_count": 0,
  "skipped_count": 0,
  "error_count": 0,
  "checks": [
    { "check_id": "PVE-001", "result": "PASS", ... },
    { "check_id": "GUARD-001", "expected": "FAIL", "result": "FAIL", ... }
  ]
}
```

---

## Entity 4: Evidence Pack

**Purpose**: Structured directory containing all artifacts from a suite run.

### Directory Structure

```
artifacts/019-lab/{runid}/
├── checks.json                # Checks collection (Entity 3)
├── evidence_manifest.json     # Artifact inventory (Entity 5)
├── provenance.json            # Run context (Entity 6)
├── summary.json               # High-level results
├── logs/
│   ├── bootstrap.log          # Ansible playbook output
│   ├── tier2.log              # Ansible playbook output
│   └── commands.jsonl         # JSONL event stream
└── reports/
    ├── validation.json        # Structured validation results
    ├── pveversion.txt         # PVE version output
    └── systemctl-status.txt   # Service status checks
```

### Metadata (not a file, implicit)

| Field | Type | Description |
|-------|------|-------------|
| `runid` | string | Directory name (lab-YYYYMMDD-HHMMSS) |
| `created_at` | timestamp | Directory creation time |
| `completed_at` | timestamp | When summary.json was written |
| `status` | string | complete\|incomplete\|interrupted |

### Lifecycle

```
(created) → (collecting artifacts) → (finalized) / (interrupted)
```

### Validation Rules

1. `runid` MUST match `/^lab-[0-9]{8}-[0-9]{6}$/`
2. Required files MUST exist: checks.json, evidence_manifest.json, provenance.json, summary.json
3. All `evidence_refs` in checks.json MUST reference files that exist in pack
4. commands.jsonl MUST contain valid JSONL (one JSON object per line)

---

## Entity 5: Evidence Manifest

**Purpose**: Inventory of all artifacts in evidence pack with metadata.

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `runid` | string | ✅ | Evidence pack identifier |
| `created_at` | string | ✅ | ISO 8601 timestamp |
| `artifacts_count` | integer | ✅ | Total artifact count |
| `artifacts` | array[Artifact] | ✅ | List of all artifacts |

### Artifact Object Schema

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `path` | string | ✅ | Relative path from evidence pack root |
| `type` | string | ✅ | log\|report\|json\|text\|binary |
| `size_bytes` | integer | ✅ | File size |
| `produced_by` | string | ❌ | Check ID or phase that generated artifact |
| `sha256` | string | ❌ | Hex digest for integrity verification |

### Example

```json
{
  "runid": "lab-20251231-123456",
  "created_at": "2025-12-31T12:40:00Z",
  "artifacts_count": 8,
  "artifacts": [
    {
      "path": "checks.json",
      "type": "json",
      "size_bytes": 12456,
      "produced_by": "suite-orchestrator"
    },
    {
      "path": "logs/tier2.log",
      "type": "log",
      "size_bytes": 45678,
      "produced_by": "tier2-phase",
      "sha256": "abc123..."
    },
    {
      "path": "reports/systemctl-status.txt",
      "type": "text",
      "size_bytes": 2345,
      "produced_by": "PVE-002"
    }
  ]
}
```

---

## Entity 6: Provenance

**Purpose**: Immutable context capturing environment, versions, parameters of suite run.

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `runid` | string | ✅ | Evidence pack identifier |
| `timestamp` | string | ✅ | ISO 8601 timestamp (run start) |
| `controller` | object | ✅ | Controller environment details |
| `target` | object | ✅ | Target environment details |
| `profile` | string | ✅ | Profile ID executed |
| `parameters` | object | ✅ | CLI parameters and flags used |

### Controller Object Schema

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `os` | string | ✅ | Operating system (e.g., "macOS 14.2") |
| `bash_version` | string | ✅ | Bash version (e.g., "5.2.15") |
| `ansible_version` | string | ✅ | Ansible version (e.g., "2.15.0") |
| `jq_version` | string | ✅ | jq version (e.g., "1.6") |
| `git_commit` | string | ✅ | Git commit SHA of harness repo |
| `git_branch` | string | ✅ | Git branch name |
| `git_dirty` | boolean | ✅ | Whether working tree had uncommitted changes |

### Target Object Schema

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `hostname` | string | ✅ | Target hostname |
| `pveversion` | string | ✅ | Proxmox VE version string |
| `kernel` | string | ✅ | Linux kernel version |
| `distro` | string | ✅ | Distribution (e.g., "Debian 13") |
| `architecture` | string | ✅ | CPU architecture (e.g., "x86_64") |

### Parameters Object Schema

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `command` | string | ✅ | Full command invoked (e.g., "pve-lab suite hypervisor-nested-workload") |
| `keep` | boolean | ✅ | Whether --keep flag was used |
| `extra_args` | array[string] | ❌ | Additional arguments passed |

### Example

```json
{
  "runid": "lab-20251231-123456",
  "timestamp": "2025-12-31T12:30:00Z",
  "controller": {
    "os": "macOS 14.2 (23C64)",
    "bash_version": "5.2.15(1)-release",
    "ansible_version": "2.15.0",
    "jq_version": "1.6",
    "git_commit": "a1b2c3d4e5f6",
    "git_branch": "019c1-semantic-safety-closure",
    "git_dirty": true
  },
  "target": {
    "hostname": "pve-lab-9001.local",
    "pveversion": "proxmox-ve: 8.1.0 (running kernel: 6.5.13-3-pve)",
    "kernel": "6.5.13-3-pve",
    "distro": "Debian 13 (trixie)",
    "architecture": "x86_64"
  },
  "profile": "hypervisor-nested-workload",
  "parameters": {
    "command": "pve-lab suite hypervisor-nested-workload",
    "keep": false,
    "extra_args": []
  }
}
```

---

## Entity 7: JSONL Event

**Purpose**: Real-time structured event for observability during suite execution.

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `timestamp` | string | ✅ | ISO 8601 timestamp (UTC) |
| `event_type` | string | ✅ | Event type (see types below) |
| `runid` | string | ✅ | Evidence pack identifier |
| `data` | object | ✅ | Event-specific data |

### Event Types

| Type | Data Fields | Description |
|------|-------------|-------------|
| `suite_start` | `profile`, `expected_duration_minutes` | Suite execution begins |
| `phase_start` | `phase`, `type`, `path` | Execution phase begins |
| `check_start` | `check_id`, `title`, `severity` | Check execution begins |
| `check_complete` | `check_id`, `result`, `duration_ms` | Check execution completes |
| `phase_complete` | `phase`, `status`, `duration_ms` | Execution phase completes |
| `warning` | `message`, `check_id?` | Non-fatal warning |
| `error` | `message`, `check_id?` | Error condition |
| `suite_complete` | `status`, `passed_count`, `failed_count` | Suite execution ends |

### Example Events

```jsonl
{"timestamp":"2025-12-31T12:30:00Z","event_type":"suite_start","runid":"lab-20251231-123456","data":{"profile":"hypervisor-nested-workload","expected_duration_minutes":10}}
{"timestamp":"2025-12-31T12:30:01Z","event_type":"phase_start","runid":"lab-20251231-123456","data":{"phase":"bootstrap","type":"playbook","path":"ansible/playbooks/lab_bootstrap.yml"}}
{"timestamp":"2025-12-31T12:31:45Z","event_type":"check_start","runid":"lab-20251231-123456","data":{"check_id":"PVE-001","title":"Proxmox VE packages installed","severity":"high"}}
{"timestamp":"2025-12-31T12:31:45Z","event_type":"check_complete","runid":"lab-20251231-123456","data":{"check_id":"PVE-001","result":"PASS","duration_ms":234}}
{"timestamp":"2025-12-31T12:32:00Z","event_type":"warning","runid":"lab-20251231-123456","data":{"message":"Git working tree is dirty - results may not be reproducible"}}
{"timestamp":"2025-12-31T12:40:00Z","event_type":"suite_complete","runid":"lab-20251231-123456","data":{"status":"SUCCESS","passed_count":24,"failed_count":0}}
```

---

## Entity 8: Summary

**Purpose**: High-level suite run results (enhanced from existing format).

### Fields (Enhanced)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `runid` | string | ✅ | Evidence pack identifier |
| `profile` | string | ✅ | Profile ID executed (NEW) |
| `status` | string | ✅ | SUCCESS\|FAILURE\|INTERRUPTED |
| `start_time` | string | ✅ | ISO 8601 timestamp |
| `end_time` | string | ✅ | ISO 8601 timestamp |
| `duration_seconds` | integer | ✅ | Total execution time |
| `tier` | integer | ✅ | Legacy tier number (for compatibility) |
| `tier2_mode` | string | ❌ | Legacy mode (for compatibility) |
| `checks_summary` | object | ✅ | Check result counts (NEW) |
| `artifacts` | array[string] | ✅ | List of key artifacts |
| `references` | object | ✅ | Links to other artifacts (NEW) |

### Checks Summary Object

```json
{
  "total": 27,
  "passed": 24,
  "failed": 0,
  "skipped": 0,
  "errors": 0
}
```

### References Object

```json
{
  "checks": "checks.json",
  "provenance": "provenance.json",
  "evidence_manifest": "evidence_manifest.json",
  "event_stream": "logs/commands.jsonl"
}
```

### Example

```json
{
  "runid": "lab-20251231-123456",
  "profile": "hypervisor-nested-workload",
  "status": "SUCCESS",
  "start_time": "2025-12-31T12:30:00Z",
  "end_time": "2025-12-31T12:40:00Z",
  "duration_seconds": 600,
  "tier": 2,
  "tier2_mode": "plus",
  "checks_summary": {
    "total": 27,
    "passed": 24,
    "failed": 0,
    "skipped": 0,
    "errors": 0
  },
  "artifacts": [
    "checks.json",
    "provenance.json",
    "logs/tier2.log",
    "reports/validation.json"
  ],
  "references": {
    "checks": "checks.json",
    "provenance": "provenance.json",
    "evidence_manifest": "evidence_manifest.json",
    "event_stream": "logs/commands.jsonl"
  }
}
```

---

## Relationships Diagram

```
Profile
  ├─(declares)─> [Check IDs]
  └─(defines)──> [Phases]

Check
  └─(references)─> [Evidence Artifacts]

Evidence Pack (directory)
  ├─(contains)─> checks.json (Checks Collection)
  ├─(contains)─> evidence_manifest.json (Evidence Manifest)
  ├─(contains)─> provenance.json (Provenance)
  ├─(contains)─> summary.json (Summary)
  └─(contains)─> logs/commands.jsonl (JSONL Events)

Provenance
  └─(references)─> Profile

Summary
  └─(references)─> Profile

Evidence Manifest
  └─(catalogs)─> [All Artifacts in Evidence Pack]
```

---

## Next Steps

With data model complete:
1. Generate JSON schemas in `contracts/` directory
2. Create `quickstart.md` with usage examples
3. Update agent context with these structures
