# Contract: Caddy Site Block Templates

**Purpose**: Defines the structure of per-service Caddy site configuration files.

## Pattern: Standard HTTPS Reverse Proxy Site Block

All service site blocks follow this pattern after the HTTPS migration:

```caddy
# Template: <service>.caddy.j2
<subdomain>.{{ caddy_base_domain }} {
    reverse_proxy {{ <service>_ip }}:{{ <service>_port }} {
        header_up X-Forwarded-Proto https
        header_up X-Real-IP {remote_host}
        header_up X-Forwarded-For {remote_host}
    }
}
```

## Service-Specific Contracts

### Nextcloud (`nextcloud.caddy.j2`)

```caddy
nextcloud.{{ caddy_base_domain }} {
    reverse_proxy {{ nextcloud_ip }}:{{ nextcloud_port }} {
        header_up X-Forwarded-Proto https
        header_up X-Real-IP {remote_host}
        header_up X-Forwarded-For {remote_host}
    }
}
```

**Changes from current**: Replaces `http://nextcloud.local` site address.

### Immich (`immich.caddy.j2`)

```caddy
immich.{{ caddy_base_domain }} {
    reverse_proxy {{ immich_ip }}:{{ immich_port }} {
        header_up X-Forwarded-Proto https
        header_up X-Real-IP {remote_host}
        header_up X-Forwarded-For {remote_host}
    }
}
```

**Changes from current**: Replaces `:80` catch-all site address.

### Grafana (`grafana.caddy.j2`) — NEW

```caddy
grafana.{{ caddy_base_domain }} {
    reverse_proxy {{ monitoring_ip }}:{{ grafana_port }} {
        header_up X-Forwarded-Proto https
        header_up X-Real-IP {remote_host}
        header_up X-Forwarded-For {remote_host}
    }
}
```

### Jellyfin (`jellyfin.caddy.j2`) — NEW

```caddy
jellyfin.{{ caddy_base_domain }} {
    reverse_proxy {{ jellyfin_ip }}:{{ jellyfin_port }} {
        header_up X-Forwarded-Proto https
        header_up X-Real-IP {remote_host}
        header_up X-Forwarded-For {remote_host}
    }
}
```

### AdGuard (`adguard.caddy.j2`) — NEW

```caddy
adguard.{{ caddy_base_domain }} {
    reverse_proxy {{ adguard_ip }}:{{ adguard_web_port }} {
        header_up X-Forwarded-Proto https
        header_up X-Real-IP {remote_host}
        header_up X-Forwarded-For {remote_host}
    }
}
```

### Home Assistant (`homeassistant.caddy.j2`) — NEW (conditional)

```caddy
{% if homeassistant_active | default(false) %}
ha.{{ caddy_base_domain }} {
    reverse_proxy {{ homeassistant_ip }}:{{ homeassistant_port }} {
        header_up X-Forwarded-Proto https
        header_up X-Real-IP {remote_host}
        header_up X-Forwarded-For {remote_host}
    }
}
{% endif %}
```

**Note**: Inactive by default (FR-015, A-009). Enabled when `homeassistant_active: true`.

## Invariants

1. All site blocks use FQDN addresses (e.g., `nextcloud.hus-sky.no`) — no `http://` prefix, no port
2. Caddy's automatic HTTPS handles TLS termination for all FQDN site blocks
3. `X-Forwarded-Proto` is always `https` (backends receive HTTPS-aware headers)
4. No `tls` directive in site blocks — global `acme_dns` applies to all
