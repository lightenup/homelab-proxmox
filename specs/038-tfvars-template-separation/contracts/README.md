# Contracts: TFvars Template Separation

This directory documents the contract changes for feature 038.

## Evidence Schema Extension

The existing `scripts/lab/contracts/evidence-tfvars-proof.schema.json` is extended with two optional fields:

### `drift_results` (optional)

Reports key-set differences between the CI template and the rendered tfvars file.

```json
{
  "drift_results": {
    "provisioning_gaps": ["key_in_template_missing_from_rendered"],
    "manual_additions": ["key_in_rendered_not_in_template"]
  }
}
```

- `provisioning_gaps`: Keys present in the CI template but absent from the rendered file. These indicate configuration that the template defines but the rendered file lacks — likely a provisioning issue.
- `manual_additions`: Keys present in the rendered file but absent from the CI template. These indicate manual additions to the rendered file that have not been backported to the template. Warning only, not a failure.

### `change_warnings` (optional)

Reports non-secret value differences between the existing rendered file and the new render from the template.

```json
{
  "change_warnings": [
    {
      "key": "network_gateway",
      "old_value": "192.168.1.99",
      "new_value": "192.168.1.1"
    }
  ]
}
```

- Only emitted when a rendered file already existed before the current provisioning run.
- Only covers simple (non-nested, non-secret) values.
- The provisioner still overwrites with template values (template is source of truth). The warning is for auditability only.

## Sentinel Contract

| Sentinel | Env Var | Description |
|----------|---------|-------------|
| `__INJECT_TOKEN_SECRET__` | `PROXMOX_API_TOKEN_SECRET` | Proxmox API token secret |

### Rules
- Sentinels use the format `__INJECT_<NAME>__`
- Only recognized in HCL value positions (right-hand side of `=`), not in comments
- Post-injection validation fails if any sentinel pattern remains in the rendered output
