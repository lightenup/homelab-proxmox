# Contract: Caddyfile Global Configuration

**Purpose**: Defines the structure of the main Caddyfile template after HTTPS migration.

## Template: `Caddyfile.j2`

```
{
    acme_dns {{ caddy_acme_dns_provider }} {{ caddy_acme_dns_provider_name }}
    log {
        output stdout
    }
}

import {{ caddy_conf_dir }}/*.caddy
```

## Invariants

1. `auto_https off` is REMOVED (FR-011)
2. `acme_dns` is set globally — all imported site blocks inherit DNS-01 challenge (R-008)
3. The `import` directive continues to load per-service site configs from `conf.d/`
4. The Domeneshop API credentials (`DOMENESHOP_API_TOKEN`, `DOMENESHOP_API_SECRET`) are read from the process environment, not from the Caddyfile

## Environment Variables Required

| Variable | Source | Description |
|---|---|---|
| `DOMENESHOP_API_TOKEN` | Ansible vault → systemd EnvironmentFile | API token for DNS-01 challenges |
| `DOMENESHOP_API_SECRET` | Ansible vault → systemd EnvironmentFile | API secret for DNS-01 challenges |
```
