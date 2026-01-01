# Data Model: Rebuild Orchestrator (019f)

## Entities

### 1. Rebuild Profile
Defined in `scripts/lab/profiles.d/rebuild-hypervisor-nested-workload.profile`.

| Field | Value | Description |
|---|---|---|
| `PROFILE_ID` | `rebuild-hypervisor-nested-workload` | Unique identifier |
| `DISPLAY_NAME` | `Rebuild: Hypervisor Nested Workload` | Human-readable name |
| `SAFETY_LEVEL` | `safe` | Indicates non-destructive by default |
| `EXPECTED_DURATION` | `15m` | Estimated runtime |
| `PHASES` | `baseline-host`, `baseline-templates`, `suite` | Execution phases |

### 2. Baseline Checks
Defined in `scripts/lab/checks.d/catalog.json`.

#### Host Checks (`baseline-host`)
| ID | Title | Severity |
|---|---|---|
| `HOST-001` | Proxmox host reachable via SSH | blocker |
| `HOST-002` | Required bridge exists and has expected gateway IP | blocker |
| `HOST-003` | Required storage backend exists | blocker |
| `HOST-004` | Host nested virtualization enabled | high |

#### Template Checks (`baseline-templates`)
| ID | Title | Severity |
|---|---|---|
| `TPL-001` | Base template exists (VMID 9001) | blocker |
| `TPL-002` | Tier2 template exists (VMID 9002) | blocker |
| `TPL-003` | Templates are marked as templates | high |
| `TPL-004` | Templates have identity markers | high |
| `TPL-005` | Templates have cloud-init user and SSH key configured | high |
| `TPL-006` | Template metadata conforms to naming policy | medium |

### 3. Evidence Pack Structure
Extended standard evidence pack.

```
artifacts/019-lab/<runid>/
├── summary.json
├── provenance.json
├── checks.json
├── evidence_manifest.json
├── logs/
│   └── events.jsonl
└── reports/
    ├── host/
    │   ├── HOST-001-ssh.txt
    │   └── ...
    ├── templates/
    │   ├── TPL-001-qm-status-9001.txt
    │   └── ...
    └── verify.json
```

## Validation Rules

1. **Catalog Compliance**: All checks emitted in `checks.json` MUST exist in `catalog.json` with matching titles.
2. **Evidence References**: All `PASS` checks MUST reference at least one file in `reports/`.
3. **Run ID Consistency**: `summary.run_id` MUST match `provenance.run_id` and the directory name.
4. **Profile ID**: `summary.profile_id` MUST match the executed profile.
