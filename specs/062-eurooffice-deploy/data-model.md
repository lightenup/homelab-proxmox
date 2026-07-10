# Phase 1 Data Model: Euro-Office Document Server Deploy

This is an infrastructure feature — the "entities" are configuration objects and their invariants,
not database tables. Each maps to a spec entity/requirement.

## Entity: Document Server LXC

Terraform-owned existence/sizing (`modules/lxc_service` call in `terraform/main.tf`).

| Field | Value | Source / Rule |
|-------|-------|---------------|
| name / hostname | `eurooffice-lxc` / `eurooffice` | mirrors market-model naming |
| cores / memory / disk | 4 / 4096 MB / 15 GB | FR-002; reference sizing (D-007) |
| features | `nesting=1` | Docker-in-LXC requires nesting (unlike market-model) |
| ip | `var.service_ips["eurooffice"]` | central `service_ips` (Networking rule); proposed `.219` |
| unprivileged | true | baseline decision |

**Invariant**: IP defined in exactly one place per environment (`service_ips`), referenced by
`group_vars` for the Caddy route and connector URLs.

## Entity: Document Server Container (compose)

Ansible-owned (`roles/eurooffice/templates/docker-compose.yml.j2`).

| Field | Value | Rule (FR) |
|-------|-------|-----------|
| image | `{{ eurooffice_image }}:{{ eurooffice_version }}` | FR-001 pinned, never `latest` |
| env `JWT_ENABLED` | `true` | FR-003 |
| env `JWT_SECRET` | `{{ eurooffice_jwt_secret }}` (vault, ≥32) | FR-003 (`no_log`) |
| env `EXAMPLE_ENABLED` | `false` | FR-004 |
| volumes | data / logs / config under `/opt/eurooffice-data` | FR-005 |
| published port | `80:80` (`eurooffice_port = 80`, F1) | one port for LAN callback + Caddy upstream + probe |
| healthcheck | `GET /healthcheck` 200 | FR-008 |
| restart | `unless-stopped` | parity w/ market-model |

**State transition**: `absent → present (Up, health: starting → healthy)`; re-apply is idempotent
(no recreation unless the pinned tag or compose content changes) — SC-003.

## Entity: JWT Secret

| Attribute | Value | Rule |
|-----------|-------|------|
| location | `group_vars/services/vault.yml` → `eurooffice_jwt_secret` | Secrets Policy (II) |
| length | ≥ 32 chars | FR-003; preflight assert |
| shared with | connector `jwt_secret` (identical value) | FR-003/FR-007; mismatch = clear fail |

## Entity: Nextcloud Connector (`eurooffice` app)

Ansible-owned on the **nextcloud** host (`roles/nextcloud`, via `occ`).

| occ key | Value | Rule |
|---------|-------|------|
| `app:install` + `app:enable` | `eurooffice` (v11.0.1) | FR-007 |
| `config:app:set eurooffice DocumentServerUrl` | `https://eurooffice.hus-sky.no/` | FR-007 (public) |
| `config:app:set eurooffice DocumentServerInternalUrl` | `http://<eurooffice-ip>/` | FR-007 (LAN callback) |
| `config:app:set eurooffice jwt_secret` | `{{ eurooffice_jwt_secret }}` | FR-003 (`no_log`) |
| preflight | Nextcloud ≥ 33 | FR-009 hard block |
| exclusivity | `richdocumentscode`/`richdocuments` absent | FR-010 (already in `nextcloud_apps_remove`) |

**Invariant**: exactly one office connector enabled after apply (SC-006).

## Entity: Reverse-Proxy Route (`caddy_services` entry)

| Field | Value | Rule |
|-------|-------|------|
| host | `eurooffice` | FR-006 → `eurooffice.hus-sky.no` |
| ip / port | `{{ eurooffice_ip }}` / `{{ eurooffice_port }}` | central vars |
| enabled / user_facing | `true` / `true` | published + on landing page |
| transport timeout | ~300 s (new optional field) | FR-006 (long editor sockets) |

TLS + WebSocket upgrade provided by Caddy `reverse_proxy` (SC-004).

## Entity: Version Pin

`group_vars/services/vars.yml` "Service versions" block → `eurooffice_version: "9.3.1"` (FR-011),
alongside `eurooffice_ip: "192.168.1.219"` / `eurooffice_port: 80` in the config section (prod
network, mirroring `market_model_ip`; not added to the divergent `192.168.20.x` lab.tfvars — analyze
I1/I2).

## Entity: Monitoring Contract

`host_vars/eurooffice.yml`: `healthcheck_url` (`/healthcheck`, 200, lan) + `monitoring_contract`
liveness `http_2xx` probe + `EuroOfficeDown` critical alert (`probe_success == 0 for 5m`) — SC-007.
