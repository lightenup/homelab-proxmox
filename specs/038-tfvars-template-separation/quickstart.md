# Quickstart: TFvars Template Separation

**Date**: 2026-02-23 | **Branch**: `038-tfvars-template-separation`

## What Changed

The `.tfvars.example` files no longer serve as CI templates. Two distinct file types now exist:

| File Type | Purpose | Contains | Used By |
|-----------|---------|----------|---------|
| `.tfvars.template` | CI provisioning | Real values + sentinel markers | `pve-service-deploy` (CI + laptop) |
| `.tfvars.example` | Documentation | Safe placeholders + instructions | New operators (manual copy) |

## For CI Pipeline Operators

**No action required.** The provisioner automatically discovers `.tfvars.template` files. If you previously set `PROD_TFVARS_TEMPLATE`, it still works as an override.

### How Sentinel Injection Works

The CI template contains:
```hcl
proxmox_api_token_secret = "__INJECT_TOKEN_SECRET__"
```

The provisioner replaces `__INJECT_TOKEN_SECRET__` with the value of `PROXMOX_API_TOKEN_SECRET` at runtime. If the secret is missing, the provisioner fails with a clear error listing the un-injected sentinel.

### Template Lookup Order

1. `PROD_TFVARS_TEMPLATE` environment variable (explicit override)
2. `terraform/environments/prod.tfvars.template` (primary CI template)
3. `terraform/environments/prod.tfvars.example` (backward-compatibility fallback)

## For New Operators

1. Copy the example file:
   ```bash
   cp terraform/environments/prod.tfvars.example terraform/environments/prod.tfvars
   ```
2. Replace all `<placeholder>` values with your real infrastructure details.
3. The file is gitignored — your secrets stay local.

## For Developers

### Key Files

| File | Role |
|------|------|
| `terraform/environments/prod.tfvars.template` | Prod CI template (committed) |
| `terraform/environments/lab.tfvars.template` | Lab CI template (committed, future use) |
| `terraform/environments/prod.tfvars.example` | Prod documentation example (committed) |
| `terraform/environments/lab.tfvars.example` | Lab documentation example (committed) |
| `scripts/lab/lib/tfvars.sh` | Provisioner library (sentinel injection, validation, drift detection) |
| `scripts/lab/contracts/evidence-tfvars-proof.schema.json` | Evidence schema (extended with drift + warnings) |

### Running Tests

```bash
# Python tests (includes new evidence-artifact contract tests)
PYTHONPATH=python/src python3 -m pytest python/tests/ -ra

# ShellCheck (bash lint)
shellcheck scripts/lab/lib/tfvars.sh

# Specific test file for this feature
PYTHONPATH=python/src python3 -m pytest python/tests/orchestrator/test_tfvars_template.py -v
```

### Evidence Artifact Changes

The `validation.json` evidence now includes two optional new fields:
- `drift_results`: Reports key-set differences between template and rendered file.
- `change_warnings`: Reports non-secret value changes (old → new) for auditability.

These fields are optional — older evidence packs without them remain valid.
