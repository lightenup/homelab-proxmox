# Data Model: Pipeline Promotion UX

**Branch**: `024-pipeline-promotion-ux`  
**Date**: 2026-01-09  
**Status**: Complete

This document defines the data entities, schemas, and relationships for the Pipeline Promotion UX feature.

---

## Entity Overview

This feature introduces or extends the following entities:

1. **Evidence Pack** (extended) - Audit bundle for deploy runs
2. **tfvars Provisioning Proof** (new) - Redacted proof that PROD tfvars was validated
3. **LAB Snapshot** (new) - Container and service state summary
4. **Workflow Input (LAB Deploy)** (new) - Dispatcher inputs for LAB-only workflow
5. **Workflow Input (Promote)** (new) - Dispatcher inputs for promotion workflow

---

## 1. Evidence Pack (Extended)

**Description**: Per-run directory containing logs, reports, and artifacts that prove what happened during a deployment. Extended to include tfvars provisioning proof and LAB snapshot.

### Structure

```text
evidence/${RUN_ID}/
├── metadata.json                           # EXISTING: run metadata (service, environment, etc.)
├── preflight.txt                           # EXISTING: prerequisite checks log
├── blast-radius.json                       # EXISTING: destructive change detection
├── reports/
│   ├── plan/
│   │   ├── plan.txt                        # EXISTING: Terraform plan output
│   │   ├── summary.txt                     # EXISTING: plan summary
│   │   ├── exitcode.txt                    # EXISTING: plan exit code
│   │   └── tfvars.txt                      # EXISTING: tfvars content (redacted)
│   ├── apply/
│   │   ├── apply.txt                       # EXISTING: Terraform apply output
│   │   ├── summary.txt                     # EXISTING: apply summary
│   │   └── exitcode.txt                    # EXISTING: apply exit code
│   ├── prod-tfvars/                        # NEW: PROD-only section
│   │   ├── provisioning.txt                # NEW: redacted summary of provisioning
│   │   ├── validation.json                 # NEW: validation proof (see schema below)
│   │   └── prod.tfvars.sha256              # NEW: hash of rendered file
│   └── lab-snapshot.json                   # NEW: LAB inventory snapshot (see schema below)
└── logs/
    ├── terraform.log                       # EXISTING: detailed Terraform log
    └── ansible.log                         # EXISTING: Ansible configuration log (if applicable)
```

### New Fields

#### `reports/prod-tfvars/` (conditional: PROD runs only)

**Purpose**: Prove that prod.tfvars was provisioned and validated without exposing secrets.

**Files**:
- `provisioning.txt`: Human-readable summary (e.g., "Provisioned at 2026-01-09T08:00:00Z, token_id=terraform@pve!terraform-token")
- `validation.json`: Structured validation proof (see tfvars Provisioning Proof entity)
- `prod.tfvars.sha256`: SHA256 hash of rendered file (64-character hex string)

**Validation rules**:
- Required when `metadata.json` has `environment: "prod"`
- Not present for LAB runs
- Offline verification checks schema compliance and `validation_status: "pass"`

#### `reports/lab-snapshot.json` (universal: all runs)

**Purpose**: Capture container state, service evidence pointers, and mount validation.

**Schema**: See LAB Snapshot entity below

**Validation rules**:
- Required for all runs (LAB and PROD)
- Must conform to `evidence-lab-snapshot.schema.json`
- Offline verification checks presence of required fields (`containers`, `services`)

### Relationships

- Evidence Pack → tfvars Proof: 1:0..1 (PROD runs only)
- Evidence Pack → LAB Snapshot: 1:1 (all runs)
- Evidence Pack → Workflow Run: 1:1 (one evidence pack per workflow run)

---

## 2. tfvars Provisioning Proof

**Description**: JSON document proving that `prod.tfvars` was rendered, validated, and contains required fields without exposing secret values.

### Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "title": "PROD tfvars Provisioning Proof",
  "properties": {
    "timestamp": {
      "type": "string",
      "format": "date-time",
      "description": "When prod.tfvars was provisioned (ISO 8601)",
      "example": "2026-01-09T08:00:00Z"
    },
    "template_source": {
      "type": "string",
      "description": "Source of template (e.g., 'heredoc', 'file:path/to/template')",
      "example": "heredoc"
    },
    "rendered_path": {
      "type": "string",
      "description": "Absolute path to rendered prod.tfvars",
      "example": "/var/lib/homelab-proxmox/tfvars/prod.tfvars"
    },
    "validation_status": {
      "type": "string",
      "enum": ["pass", "fail"],
      "description": "Result of validation checks"
    },
    "token_id": {
      "type": "string",
      "pattern": "^terraform@pve!terraform-token$",
      "description": "Proxmox API token ID (non-secret, safe to include)"
    },
    "secret_present": {
      "type": "boolean",
      "description": "True if secret is non-empty and non-placeholder"
    },
    "file_hash": {
      "type": "string",
      "pattern": "^[a-f0-9]{64}$",
      "description": "SHA256 hash of rendered prod.tfvars"
    },
    "validation_errors": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Validation errors if validation_status is fail (empty array if pass)"
    }
  },
  "required": [
    "timestamp",
    "template_source",
    "rendered_path",
    "validation_status",
    "token_id",
    "secret_present",
    "file_hash"
  ]
}
```

### Field Descriptions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `timestamp` | string (ISO 8601) | Yes | Provisioning time |
| `template_source` | string | Yes | Template origin (e.g., "heredoc") |
| `rendered_path` | string | Yes | Absolute path to prod.tfvars |
| `validation_status` | enum | Yes | "pass" or "fail" |
| `token_id` | string | Yes | Proxmox token ID (must equal `terraform@pve!terraform-token`) |
| `secret_present` | boolean | Yes | True if secret validated as non-empty/non-placeholder |
| `file_hash` | string | Yes | SHA256 hash (64 hex chars) |
| `validation_errors` | array[string] | No | Errors if validation failed (empty for pass) |

### Validation Rules

1. **Token ID check**: Must equal `terraform@pve!terraform-token`
2. **Secret presence**: Must be true (secret non-empty and not in placeholder list)
3. **Hash format**: Must be 64-character hex string (SHA256)
4. **Status check**: Must be "pass" for evidence to be valid

### Example

```json
{
  "timestamp": "2026-01-09T08:00:00Z",
  "template_source": "heredoc",
  "rendered_path": "/var/lib/homelab-proxmox/tfvars/prod.tfvars",
  "validation_status": "pass",
  "token_id": "terraform@pve!terraform-token",
  "secret_present": true,
  "file_hash": "a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef123456",
  "validation_errors": []
}
```

---

## 3. LAB Snapshot

**Description**: JSON document capturing container state, service evidence pointers, and mount validation at a point in time.

### Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "title": "LAB Inventory Snapshot",
  "properties": {
    "generated_at": {
      "type": "string",
      "format": "date-time",
      "description": "Snapshot generation timestamp (ISO 8601)"
    },
    "environment": {
      "type": "string",
      "enum": ["lab", "prod"],
      "description": "Target environment for snapshot"
    },
    "containers": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "vmid": {
            "type": "integer",
            "description": "Proxmox container ID"
          },
          "hostname": {
            "type": "string",
            "description": "Container hostname"
          },
          "status": {
            "type": "string",
            "enum": ["running", "stopped"],
            "description": "Container status"
          },
          "ipv4": {
            "type": "string",
            "description": "Primary IPv4 address (optional, may be empty)"
          }
        },
        "required": ["vmid", "hostname", "status"]
      },
      "description": "List of all containers on Proxmox host"
    },
    "services": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "service": {
            "type": "string",
            "description": "Service slug (from allowlist)"
          },
          "state_path": {
            "type": "string",
            "description": "Terraform state directory path"
          },
          "terraform_module": {
            "type": "string",
            "description": "Terraform module name (optional)"
          }
        },
        "required": ["service", "state_path"]
      },
      "description": "Services detected with state directories"
    },
    "latest_evidence": {
      "type": "object",
      "additionalProperties": {
        "type": "object",
        "properties": {
          "run_id": {
            "type": "string",
            "description": "Latest evidence run ID for this service"
          },
          "path": {
            "type": "string",
            "description": "Evidence pack path"
          }
        },
        "required": ["run_id", "path"]
      },
      "description": "Mapping of service to latest evidence metadata"
    },
    "mount_checks": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "container_vmid": {
            "type": "integer",
            "description": "Container VMID where mount was checked"
          },
          "mount_path": {
            "type": "string",
            "description": "Expected mount path (e.g., /media/video)"
          },
          "mounted": {
            "type": "boolean",
            "description": "True if mount path exists in /proc/mounts"
          },
          "read_only": {
            "type": "boolean",
            "description": "True if mount has 'ro' option (optional, only if mounted)"
          },
          "source": {
            "type": "string",
            "description": "Mount source (e.g., NFS share, optional)"
          }
        },
        "required": ["container_vmid", "mount_path", "mounted"]
      },
      "description": "Mount validation checks (optional, service-specific)"
    },
    "errors": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Non-fatal errors during snapshot collection"
    }
  },
  "required": ["generated_at", "environment", "containers", "services"]
}
```

### Field Descriptions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `generated_at` | string (ISO 8601) | Yes | Snapshot timestamp |
| `environment` | enum | Yes | "lab" or "prod" |
| `containers` | array[object] | Yes | All containers on host |
| `containers[].vmid` | integer | Yes | Proxmox container ID |
| `containers[].hostname` | string | Yes | Container hostname |
| `containers[].status` | enum | Yes | "running" or "stopped" |
| `containers[].ipv4` | string | No | IPv4 address (may be empty) |
| `services` | array[object] | Yes | Services with state directories |
| `services[].service` | string | Yes | Service slug |
| `services[].state_path` | string | Yes | Terraform state path |
| `services[].terraform_module` | string | No | Module name |
| `latest_evidence` | object | No | Service → evidence mapping |
| `latest_evidence[service].run_id` | string | Yes (if present) | Run ID |
| `latest_evidence[service].path` | string | Yes (if present) | Evidence path |
| `mount_checks` | array[object] | No | Mount validation results |
| `mount_checks[].container_vmid` | integer | Yes (if present) | Container VMID |
| `mount_checks[].mount_path` | string | Yes (if present) | Mount path |
| `mount_checks[].mounted` | boolean | Yes (if present) | Mount exists |
| `mount_checks[].read_only` | boolean | No | Read-only flag |
| `mount_checks[].source` | string | No | Mount source |
| `errors` | array[string] | No | Collection errors |

### Example

```json
{
  "generated_at": "2026-01-09T08:05:00Z",
  "environment": "lab",
  "containers": [
    {
      "vmid": 200,
      "hostname": "immich-lab",
      "status": "running",
      "ipv4": "192.168.1.50"
    },
    {
      "vmid": 201,
      "hostname": "jellyfin-lab",
      "status": "running",
      "ipv4": "192.168.1.51"
    }
  ],
  "services": [
    {
      "service": "immich",
      "state_path": "/var/lib/homelab-proxmox/state/services/immich",
      "terraform_module": "module.immich_lxc"
    },
    {
      "service": "jellyfin",
      "state_path": "/var/lib/homelab-proxmox/state/services/jellyfin",
      "terraform_module": "module.jellyfin_lxc"
    }
  ],
  "latest_evidence": {
    "immich": {
      "run_id": "20260109T075500Z-apply-lab-immich-abc123",
      "path": "/var/lib/homelab-proxmox/artifacts/service-deploy-runs/20260109T075500Z-apply-lab-immich-abc123"
    },
    "jellyfin": {
      "run_id": "20260109T074000Z-apply-lab-jellyfin-def456",
      "path": "/var/lib/homelab-proxmox/artifacts/service-deploy-runs/20260109T074000Z-apply-lab-jellyfin-def456"
    }
  },
  "mount_checks": [
    {
      "container_vmid": 200,
      "mount_path": "/media/video",
      "mounted": true,
      "read_only": true,
      "source": "192.168.1.109:/volume1/video"
    },
    {
      "container_vmid": 201,
      "mount_path": "/media/video",
      "mounted": true,
      "read_only": true,
      "source": "192.168.1.109:/volume1/video"
    }
  ],
  "errors": []
}
```

---

## 4. Workflow Input (LAB Deploy)

**Description**: Dispatcher inputs for the LAB-only deployment workflow.

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `service` | choice | Yes | Service to deploy (from allowlist) |
| `apply` | boolean | Yes | Plan+apply (true) or plan-only (false) |
| `confirm_destructive` | string | Conditional | Required when plan detects destructive changes |

### Validation Rules

1. **Service validation**: Must exist in `scripts/lab/service-scope-allowlist.json`
2. **Destructive confirmation**: When `blast-radius.json` shows `destructive: true`, must equal `"apply-lab-destructive"`
3. **No environment selector**: LAB workflow always targets LAB environment

### Workflow YAML

```yaml
on:
  workflow_dispatch:
    inputs:
      service:
        description: "Service to deploy"
        required: true
        type: choice
        options:
          - adguard
          - homeassistant
          - immich
          - jellyfin
          - monitoring
          - reverse_proxy
      apply:
        description: "Run plan+apply (true) or plan-only (false)"
        required: true
        type: boolean
        default: false
      confirm_destructive:
        description: "Required when plan has replace/destroy: 'apply-lab-destructive'"
        required: false
        type: string
```

---

## 5. Workflow Input (Promote)

**Description**: Dispatcher inputs for the LAB → PROD promotion workflow.

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `service` | choice | Yes | Service to promote (from allowlist) |
| `confirm_destructive_lab` | string | Conditional | Required when LAB plan is destructive |

### Validation Rules

1. **Service validation**: Must exist in `scripts/lab/service-scope-allowlist.json`
2. **LAB destructive confirmation**: When LAB plan shows `destructive: true`, must equal `"apply-lab-destructive"`

### Workflow YAML

```yaml
on:
  workflow_dispatch:
    inputs:
      service:
        description: "Service to promote"
        required: true
        type: choice
        options:
          - adguard
          - homeassistant
          - immich
          - jellyfin
          - monitoring
          - reverse_proxy
      confirm_destructive_lab:
        description: "Required when LAB plan is destructive: 'apply-lab-destructive'"
        required: false
        type: string
```

---

## Entity Relationships

```
Workflow Run (Promote)
├── Job: plan_lab
│   └── Evidence Pack (LAB plan)
│       ├── blast-radius.json
│       └── lab-snapshot.json
├── Job: apply_lab
│   └── Evidence Pack (LAB apply)
│       └── lab-snapshot.json
├── Job: plan_prod (requires approval)
│   └── Evidence Pack (PROD plan)
│       ├── blast-radius.json
│       ├── lab-snapshot.json
│       └── prod-tfvars/
│           ├── provisioning.txt
│           ├── validation.json
│           └── prod.tfvars.sha256
└── Job: apply_prod
    └── Evidence Pack (PROD apply)
        ├── lab-snapshot.json
        └── prod-tfvars/
            ├── provisioning.txt
            ├── validation.json
            └── prod.tfvars.sha256

Service Allowlist
├── Service: adguard
├── Service: homeassistant
├── Service: immich
├── Service: jellyfin
├── Service: monitoring
└── Service: reverse_proxy

LAB Snapshot
├── containers[] ← Proxmox pct list
├── services[] ← Terraform state directories
├── latest_evidence{} ← Evidence pack directories
└── mount_checks[] ← /proc/mounts in containers
```

---

## Summary

This data model defines 5 key entities:

1. **Evidence Pack**: Extended with tfvars proof (PROD) and LAB snapshot (all runs)
2. **tfvars Provisioning Proof**: JSON proof of prod.tfvars validation
3. **LAB Snapshot**: JSON summary of container/service state
4. **Workflow Input (LAB Deploy)**: Bounded inputs for LAB-only workflow
5. **Workflow Input (Promote)**: Bounded inputs for promotion workflow

All entities include validation rules, schema definitions, and examples to guide implementation.

