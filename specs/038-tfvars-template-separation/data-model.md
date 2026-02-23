# Data Model: TFvars Template Separation

**Date**: 2026-02-23 | **Branch**: `038-tfvars-template-separation`

## Entities

### 1. CI Template File (`.tfvars.template`)

**Purpose**: Authoritative source of non-secret configuration for CI provisioning. Contains real infrastructure values and sentinel markers for runtime-injected secrets.

**Location**: `terraform/environments/{env}.tfvars.template`

**Structure** (HCL key-value pairs):
```hcl
# CI template — real non-secret values, sentinels for secrets.
# Do not edit rendered values here; update the template and re-provision.

proxmox_api_url          = "https://192.168.1.112:8006/api2/json"   # real value
proxmox_api_token_id     = "terraform@pve!terraform-token"           # non-secret constant
proxmox_api_token_secret = "__INJECT_TOKEN_SECRET__"                 # sentinel marker
proxmox_node             = "pve"                                     # real value
# ... other non-secret configuration ...
```

**Fields**:
| Field | Type | Description |
|-------|------|-------------|
| All Terraform variables | HCL values | Real non-secret values matching `terraform/variables.tf` |
| `proxmox_api_token_secret` | Sentinel | `__INJECT_TOKEN_SECRET__` — replaced at runtime |

**Validation Rules**:
- Must contain exactly one sentinel marker: `__INJECT_TOKEN_SECRET__`
- All non-secret values must be real infrastructure values (not placeholders)
- Must define the same top-level key set as the rendered output

---

### 2. Documentation Example File (`.tfvars.example`)

**Purpose**: Human-readable starting point for new operators. Contains safe placeholders and instructional comments.

**Location**: `terraform/environments/{env}.tfvars.example`

**Structure** (HCL key-value pairs with comments):
```hcl
# Documentation example — safe placeholders for new operators.
# Copy to terraform/environments/{env}.tfvars and replace placeholders.

proxmox_api_url          = "<pve-api-url>"          # e.g. https://192.168.1.100:8006/api2/json
proxmox_api_token_id     = "<token-id>"             # e.g. terraform@pve!terraform-token
proxmox_api_token_secret = "<your-token-secret>"    # from Proxmox API token
# ... other placeholders with instructions ...
```

**Validation Rules**:
- Must NOT contain real infrastructure values (IPs, SSH keys, hostnames)
- Must NOT contain sentinel markers (`__INJECT_*__`)
- All secret-adjacent fields use `<descriptive-placeholder>` format

---

### 3. Rendered File (`.tfvars`)

**Purpose**: Final configuration consumed by Terraform. Produced by the provisioner from a CI template + runtime secrets.

**Location**: `${TFVARS_DIR}/{env}.tfvars` (default: `/var/lib/homelab-proxmox/tfvars/prod.tfvars`)

**Fields**:
| Field | Type | Description |
|-------|------|-------------|
| All Terraform variables | HCL values | Real values for all fields |
| `proxmox_api_token_secret` | String | Actual secret value (never committed) |

**Validation Rules**:
- Must NOT contain any sentinel markers (`__INJECT_*__`)
- Must contain a valid `proxmox_api_token_id` matching `terraform@pve!terraform-token`
- Must contain a non-empty, non-placeholder `proxmox_api_token_secret`

**State Transitions**:
```
[does not exist] → render from template → [rendered + validated]
[rendered + validated] → re-render from template → [rendered + validated] (with change warnings if values differ)
[rendered + validated] → no secret available → [validated only] (existing file preserved, FR-007)
```

---

### 4. Sentinel Marker

**Purpose**: Unambiguous placeholder in CI templates, replaced by the provisioner at runtime.

**Format**: `__INJECT_<NAME>__`

**Defined Sentinels**:
| Sentinel | Environment Variable | Description |
|----------|---------------------|-------------|
| `__INJECT_TOKEN_SECRET__` | `PROXMOX_API_TOKEN_SECRET` | Proxmox API token secret |

**Recognition Rules**:
- Only recognized in HCL value positions (right-hand side of `=` assignments)
- Ignored inside comments (lines starting with `#`)
- The pattern `__INJECT_[A-Z_]+__` is used for post-injection validation

---

### 5. Validation Evidence (Extended)

**Purpose**: Structured artifact recording provisioner actions, validation results, drift findings, and warnings.

**Location**: `${EVIDENCE_ROOT}/reports/prod-tfvars/validation.json`

**Schema** (extended from existing):
```json
{
  "timestamp": "2026-02-23T08:00:00Z",
  "template_source": "file:/path/to/prod.tfvars.template",
  "rendered_path": "/var/lib/homelab-proxmox/tfvars/prod.tfvars",
  "validation_status": "pass",
  "token_id": "terraform@pve!terraform-token",
  "secret_present": true,
  "file_hash": "a1b2c3d4...",
  "validation_errors": [],
  "drift_results": {
    "provisioning_gaps": [],
    "manual_additions": []
  },
  "change_warnings": []
}
```

**New Fields** (all optional for backward compatibility):
| Field | Type | Description |
|-------|------|-------------|
| `drift_results` | Object | Key-set drift between template and rendered file |
| `drift_results.provisioning_gaps` | Array of strings | Keys in template but missing from rendered file |
| `drift_results.manual_additions` | Array of strings | Keys in rendered file but not in template |
| `change_warnings` | Array of objects | Non-secret value differences between existing rendered and template |
| `change_warnings[].key` | String | The configuration key that differs |
| `change_warnings[].old_value` | String | Value in the existing rendered file |
| `change_warnings[].new_value` | String | Value from the template |

---

## Relationships

```
CI Template (.tfvars.template)
    │
    ├── [rendered by provisioner] ──→ Rendered File (.tfvars)
    │       ↑
    │       └── [sentinel injection] ← Environment Variable (PROXMOX_API_TOKEN_SECRET)
    │
    ├── [drift detection] ←──────────→ Rendered File (.tfvars)
    │
    └── [fallback lookup] ←── Documentation Example (.tfvars.example)

Validation Evidence
    ├── records: template_source (which file was used)
    ├── records: validation_status (pass/fail)
    ├── records: drift_results (key-set comparison)
    └── records: change_warnings (non-secret value diffs)
```
