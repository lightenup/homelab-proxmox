# Data Model: Lab Harness Confidence Suite

**Feature**: `019c-lab-confidence-suite`

## Evidence Pack Structure

The Evidence Pack is a directory named `artifacts/019-lab/<runid>/` containing the following structure:

```text
artifacts/019-lab/<runid>/
├── evidence_manifest.json  # Metadata about the run and evidence
├── checks.json             # Structured validation results
├── summary.json            # High-level run summary (legacy/compat)
├── run.log                 # Full execution log
├── logs/                   # Raw logs collected from the VM
│   ├── journal.log
│   └── ...
├── config/                 # Configuration snapshots
│   ├── pveversion.txt
│   ├── pvesh_version.txt
│   ├── apt_policy.txt
│   └── systemctl_status.txt
└── validation/             # Validation artifacts
    └── ...
```

## JSON Schemas

### `evidence_manifest.json`

```json
{
  "run_id": "lab-20251230-120000",
  "profile": "hypervisor-control-plane",
  "timestamp": "2025-12-30T12:00:00Z",
  "artifacts": {
    "logs": ["journal.log"],
    "config": ["pveversion.txt", "apt_policy.txt"]
  }
}
```

### `checks.json`

```json
{
  "run_id": "lab-20251230-120000",
  "checks": [
    {
      "id": "OS_DEBIAN_13",
      "status": "PASS",
      "message": "OS is Debian 13 (Trixie)",
      "timestamp": "2025-12-30T12:01:00Z"
    },
    {
      "id": "REPO_SIGNED_BY",
      "status": "FAIL",
      "message": "Proxmox repo missing signed-by directive",
      "timestamp": "2025-12-30T12:01:05Z"
    }
  ]
}
```
