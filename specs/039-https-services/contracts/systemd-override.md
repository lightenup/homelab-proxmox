# Contract: Systemd Override for Caddy Secrets

**Purpose**: Defines the systemd drop-in override that injects Domeneshop credentials into the Caddy process.

## File: `/etc/systemd/system/caddy.service.d/domeneshop.conf`

```ini
# Managed by Ansible — DO NOT EDIT MANUALLY
[Service]
EnvironmentFile=/etc/caddy/domeneshop.env
```

## File: `/etc/caddy/domeneshop.env`

```
# Managed by Ansible — DO NOT EDIT MANUALLY
# Domeneshop DNS API credentials for ACME DNS-01 challenges
DOMENESHOP_API_TOKEN={{ domeneshop_api_token }}
DOMENESHOP_API_SECRET={{ domeneshop_api_secret }}
```

## Security Constraints

| Property | Requirement |
|---|---|
| File owner | `root:root` |
| File mode | `0600` |
| In git repo | **Never** — generated on target from vault |
| In vault | `domeneshop_api_token` and `domeneshop_api_secret` in `ansible/group_vars/services/vault.yml` |
| Template variable source | Ansible vault (encrypted at rest) |

## Ansible Handler Trigger

When either file changes:
1. `systemctl daemon-reload`
2. `systemctl restart caddy`
