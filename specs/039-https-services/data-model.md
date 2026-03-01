# Data Model: HTTPS for All Homelab Services

**Feature**: 039-https-services
**Date**: 2026-02-28

---

## Entities

### E-001: Service Subdomain Mapping

Defines the routing table for the reverse proxy. Each entry maps a public subdomain to a backend service.

| Field | Type | Description |
|---|---|---|
| `subdomain` | string | Public FQDN (e.g., `nextcloud.hus-sky.no`) |
| `backend_ip` | IPv4 | LAN IP of the service backend |
| `backend_port` | integer | Port the backend service listens on |
| `active` | boolean | Whether the site block is deployed and active |
| `extra_headers` | map | Additional proxy headers (e.g., `X-Forwarded-Proto`) |

**Instances** (from spec A-007):

| Subdomain | Backend IP | Port | Active | Notes |
|---|---|---|---|---|
| `nextcloud.hus-sky.no` | `192.168.1.216` | `8080` | Yes | Existing proxy target, domain change |
| `immich.hus-sky.no` | `192.168.1.213` | `2283` | Yes | Existing proxy target, domain change |
| `grafana.hus-sky.no` | `192.168.1.214` | `3000` | Yes | New proxy target (FR-010) |
| `jellyfin.hus-sky.no` | `192.168.1.215` | `8096` | Yes | New proxy target (FR-010) |
| `adguard.hus-sky.no` | `192.168.1.210` | `3000` | Yes | New proxy target (FR-010); port TBD — AdGuard Home default web UI is 3000 (see R-004) |
| `ha.hus-sky.no` | `192.168.1.212` | `8123` | No | Future placeholder (FR-015, A-009) |

**Source variables** (in `ansible/group_vars/`):
- `nextcloud_ip`, `immich_ip`, `monitoring_ip` — already defined in `services/vars.yml`
- `reverse_proxy_ip` — already defined in `services/vars.yml`
- New variables needed: `jellyfin_ip`, `adguard_ip`, `homeassistant_ip`, and corresponding ports

---

### E-002: TLS Certificate

Represents a Let's Encrypt certificate. Managed automatically by Caddy.

| Field | Type | Description |
|---|---|---|
| `domain` | string | The FQDN the certificate covers |
| `issuer` | string | Always `Let's Encrypt` (ACME) |
| `challenge_type` | string | Always `DNS-01` |
| `dns_provider` | string | `domeneshop` (via lego_deprecated) |
| `issued_at` | datetime | Certificate issuance timestamp |
| `expires_at` | datetime | Certificate expiry timestamp |
| `auto_renew` | boolean | Always `true` — Caddy handles this |

**Notes**:
- Individual certificates per subdomain (research R-007)
- Caddy stores certificate data in `/var/lib/caddy/.local/share/caddy/` by default
- No manual certificate files to manage

---

### E-003: DNS Rewrite Rule (AdGuard)

Split-horizon DNS entries so LAN clients resolve `*.hus-sky.no` to the reverse proxy LAN IP instead of going through the public DNS.

| Field | Type | Description |
|---|---|---|
| `domain` | string | The FQDN to rewrite (e.g., `nextcloud.hus-sky.no`) |
| `answer` | IPv4 | Target IP (`192.168.1.211` — reverse proxy) |

**Instances**:

| Domain | Answer |
|---|---|
| `nextcloud.hus-sky.no` | `192.168.1.211` |
| `immich.hus-sky.no` | `192.168.1.211` |
| `grafana.hus-sky.no` | `192.168.1.211` |
| `jellyfin.hus-sky.no` | `192.168.1.211` |
| `adguard.hus-sky.no` | `192.168.1.211` |

**Configuration method**: Manual via AdGuard Home web UI (decision D-002, research R-004)

---

### E-004: Registrar DNS Record (Domeneshop)

DNS A record(s) at the registrar for external resolution (Tailscale clients, public DNS).

| Field | Type | Description |
|---|---|---|
| `type` | string | `A` |
| `name` | string | `*` (wildcard) or individual subdomain |
| `value` | IPv4 | `192.168.1.211` (reverse proxy LAN IP) |
| `ttl` | integer | Registrar default |

**Configuration**: Wildcard `*.hus-sky.no → 192.168.1.211` (decision D-001)
**Method**: Manual one-time setup via Domeneshop web UI (assumption A-003)

---

### E-005: Vault Secret

Encrypted credentials for the Domeneshop DNS API.

| Field | Type | Description |
|---|---|---|
| `domeneshop_api_token` | string | API token from Domeneshop control panel |
| `domeneshop_api_secret` | string | API secret from Domeneshop control panel |

**Storage**: `ansible/group_vars/services/vault.yml` (existing encrypted vault file)
**Injection**: Via systemd EnvironmentFile → Caddy process (research R-003)

---

## State Transitions

### Certificate Lifecycle (managed by Caddy)

```
[Not Issued] → (Caddy starts with DNS provider) → [Issuing via DNS-01]
    → (ACME challenge succeeds) → [Valid]
    → (30 days before expiry) → [Renewing]
    → (renewal succeeds) → [Valid]
    → (renewal fails) → [Valid, retry pending] → (retry succeeds) → [Valid]
```

### Service Migration (one-time, operator-driven)

```
[HTTP on .local domain]
    → (Ansible deploys HTTPS config) → [HTTPS on hus-sky.no + .local trusted]
    → (Operator updates clients) → [HTTPS on hus-sky.no, .local deprecated]
    → (Future: remove .local trust) → [HTTPS only on hus-sky.no]
```

---

## Variable Registry

### New Variables Introduced

| Variable | Value | Location | Source |
|---|---|---|---|
| `caddy_base_domain` | `hus-sky.no` | `ansible/roles/reverse_proxy/defaults/main.yml` | FR-001 |
| `caddy_acme_dns_provider` | `lego_deprecated` | `ansible/roles/reverse_proxy/defaults/main.yml` | R-001 |
| `caddy_acme_dns_provider_name` | `domeneshop` | `ansible/roles/reverse_proxy/defaults/main.yml` | R-001 |
| `caddy_custom_binary` | `true` | `ansible/roles/reverse_proxy/defaults/main.yml` | FR-012 |
| `caddy_xcaddy_plugins` | `["github.com/caddy-dns/lego-deprecated"]` | `ansible/roles/reverse_proxy/defaults/main.yml` | R-001 |
| `domeneshop_api_token` | (vault) | `ansible/group_vars/services/vault.yml` | FR-013 |
| `domeneshop_api_secret` | (vault) | `ansible/group_vars/services/vault.yml` | FR-013 |
| `nextcloud_domain` | `nextcloud.hus-sky.no` | `ansible/group_vars/services/vars.yml` | FR-007 |
| `nextcloud_trusted_domains_extra` | `["nextcloud.local"]` | `ansible/roles/nextcloud/defaults/main.yml` | FR-008, D-004 |
| `nextcloud_overwrite_protocol` | `https` | `ansible/roles/nextcloud/defaults/main.yml` | FR-007 |
| `grafana_domain` | `grafana.hus-sky.no` | `ansible/group_vars/monitoring/vars.yml` | FR-009 |
| `grafana_protocol` | `https` | `ansible/group_vars/monitoring/vars.yml` | FR-009 |
| `jellyfin_ip` | `192.168.1.215` | `ansible/group_vars/services/vars.yml` | A-007, FR-010 |
| `jellyfin_port` | `8096` | `ansible/group_vars/services/vars.yml` | A-007, FR-010 |
| `adguard_ip` | `192.168.1.210` | `ansible/group_vars/services/vars.yml` | A-005, FR-010 |
| `adguard_web_port` | `3000` | `ansible/group_vars/services/vars.yml` | FR-010 |
| `homeassistant_ip` | `192.168.1.212` | `ansible/group_vars/services/vars.yml` | FR-015 |
| `homeassistant_port` | `8123` | `ansible/group_vars/services/vars.yml` | FR-015 |
| `go_version` | `1.22.0` | `ansible/roles/reverse_proxy/defaults/main.yml` | R-002 |

### Existing Variables Modified

| Variable | Old Value | New Value | Location |
|---|---|---|---|
| `nextcloud_domain` | `nextcloud.local` | `nextcloud.hus-sky.no` | `ansible/roles/nextcloud/defaults/main.yml` or `group_vars/services/vars.yml` |
| `grafana_domain` | `monitoring.local` | `grafana.hus-sky.no` | `ansible/group_vars/monitoring/vars.yml` |
