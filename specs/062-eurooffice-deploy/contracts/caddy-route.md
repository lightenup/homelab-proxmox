# Contract: Caddy Route (`caddy_services` entry + template)

## New entry in `ansible/group_vars/services/vars.yml` → `caddy_services`
```yaml
  - host: eurooffice
    ip: "{{ eurooffice_ip }}"
    port: "{{ eurooffice_port }}"
    title: "Euro-Office"
    desc: "Online document editing"
    enabled: true
    user_facing: true
    proxy_timeout: "300s"      # NEW optional field (see template change)
```

## Template change — `ansible/roles/reverse_proxy/templates/service.caddy.j2`
Add an optional transport block, gated on the new field so existing entries are byte-for-byte
unchanged:

```caddy
{{ item.host }}.{{ caddy_base_domain }} {
    reverse_proxy {{ item.ip }}:{{ item.port }} {
        header_up X-Forwarded-Proto https
        header_up X-Real-IP {remote_host}
        header_up X-Forwarded-For {remote_host}
{% if item.proxy_timeout is defined %}
        transport http {
            read_timeout {{ item.proxy_timeout }}
            write_timeout {{ item.proxy_timeout }}
        }
{% endif %}
    }
}
```

## Contract assertions (SC-004)
- `caddy validate` passes (role already runs it).
- WebSocket upgrade: Caddy `reverse_proxy` upgrades `Connection: Upgrade` automatically — no extra
  directive; editor `wss://` establishes.
- `X-Forwarded-Proto: https` already present (required by the document server behind TLS).
- Existing entries without `proxy_timeout` render identically (no diff) — extend-before-add (IV).

**Verify**: `curl -I https://eurooffice.hus-sky.no/healthcheck` → `200` over TLS.
