# Implementation Plan: Euro-Office Document Server Deploy

**Branch**: `062-eurooffice-deploy` | **Date**: 2026-07-10 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/062-eurooffice-deploy/spec.md`

## Summary

Deploy the Euro-Office document server (AGPLv3 ONLYOFFICE DocumentServer fork, pinned `9.3.1`) as a
`docker_compose_v2` service on a new dedicated unprivileged LXC, following the exact shape of the
existing `market-model` service (Terraform `lxc_service` module → per-service Ansible role → gated
`pve-service-deploy` pipeline). Publish it at `eurooffice.hus-sky.no` via a `caddy_services` entry
(Caddy `reverse_proxy` already upgrades WebSockets; add a longer read/write timeout for the editor),
and wire it into the existing Nextcloud 34 instance by installing/enabling/configuring the
`eurooffice` connector app through `occ`. JWT is shared between server and connector from the Ansible
vault. Documents remain in Nextcloud (no user-data backup); persistent volumes retain the server's
config/caches only.

## Technical Context

**Language/Version**: HCL (Terraform, `telmate/proxmox`), YAML (Ansible 2.x), Jinja2, Caddyfile — no new language
**Primary Dependencies**: `modules/lxc_service` (Terraform), `geerlingguy.docker` + `community.docker.docker_compose_v2` + `community.docker.docker_login` (Ansible), official image `ghcr.io/euro-office/documentserver:9.3.1`, Nextcloud `eurooffice` connector app v11.0.1
**Storage**: Docker named/bind volumes on the LXC's local disk for data/logs/config (`/opt/eurooffice-data`); no NFS bind-mount (documents live in Nextcloud). No user-data backup in scope.
**Testing**: `terraform plan` (non-destructive gate), Ansible preflight asserts + post-apply `uri` healthcheck (`/healthcheck` → 200), blackbox liveness probe, manual `.docx` round-trip via Nextcloud + admin connector test
**Target Platform**: Debian stable unprivileged LXC on Proxmox (PVE), nesting enabled, running Docker
**Project Type**: Infrastructure (single) — Terraform (existence/sizing) + Ansible (in-guest config), per Constitution III
**Performance Goals**: Editor loads and round-trips a `.docx/.xlsx/.pptx`; WebSocket (`wss://`) established; `/healthcheck` → 200 within pipeline healthcheck window
**Constraints**: Image pinned (never `latest`); `EXAMPLE_ENABLED=false`; `JWT_ENABLED=true` with a shared ≥32-char vault secret identical on both sides; ~300 s proxy timeout; preflight verifies Nextcloud ≥ 33 and ~4 GB PVE RAM headroom; exactly one office connector enabled
**Scale/Scope**: Single-node homelab; one document server; a handful of concurrent editors

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Spec-Driven Workflow** — ✅ Driven from `specs/062-eurooffice-deploy/`; `tasks.md` follows via `/speckit.tasks`.
- **II. Secrets Policy (NON-NEGOTIABLE)** — ✅ JWT secret and GHCR pull token live in `ansible/group_vars/services/vault.yml`; templates reference vars only; `no_log` on secret tasks. No secret committed.
- **III. Separation of Concerns** — ✅ Terraform owns the LXC's existence/sizing (`lxc_service` module); Ansible owns in-guest Docker/compose config and the Nextcloud `occ` connector wiring. No mixing.
- **IV. Code Economy (YAGNI)** — ✅ Reuses `lxc_service`, `geerlingguy.docker`, the `caddy_services` list, host_vars healthcheck/monitoring contract, and the `nextcloud` role's `occ` patterns. New artifacts (one Terraform service dir, one `eurooffice` role, one playbook) are justified: a document server is a distinct service with no existing home. The Caddy per-service timeout is added as an **optional** field so existing entries are unchanged (extend-before-add).
- **V. Dual-Provisioning Parity** — ✅ New service added to the workflow `service` dropdowns (`lxc-deploy-lab`, `lxc-promote-lab`, `lxc-promote-prod`) **in this PR**; `pve-service-deploy --service eurooffice` runs identically locally and in CI (it maps slug → `ansible/playbooks/eurooffice.yml`). Vault on PVE for CI, local `vault.yml` for laptop.
- **Provider Strategy** — ✅ `telmate/proxmox` via `lxc_service`; no provider migration.
- **Networking** — ✅ Static IP for the new LXC, defined centrally in `service_ips` (tfvars) + `group_vars/services/vars.yml`; no scattered IP strings.
- **Token Privilege Tiers** — ✅ Terraform uses Tier 1 only; orchestrator post-create uses Tier 2 for nesting/features; no `root@pam` in `.tf`.

**Result**: PASS — no violations; Complexity Tracking not required.

## Project Structure

### Documentation (this feature)

```text
specs/062-eurooffice-deploy/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output (config entities / contracts)
├── quickstart.md        # Phase 1 output (deploy + verify runbook)
├── contracts/           # Phase 1 output (occ keys, compose env, caddy route, monitoring)
│   ├── compose-env.md
│   ├── connector-occ.md
│   ├── caddy-route.md
│   └── monitoring-contract.md
├── checklists/
│   └── requirements.md  # From /speckit.specify
└── tasks.md             # /speckit.tasks output (NOT created here)
```

### Source Code (repository root)

```text
terraform/
├── main.tf                                  # + module "eurooffice_lxc" (4/4096/15, nesting via features)
├── services/eurooffice/                     # NEW: main.tf + outputs.tf (mirrors services/market-model/)
└── environments/
    ├── lab.tfvars  / lab.tfvars.template     # + service_ips["eurooffice"]
    └── prod.tfvars.template                  # + service_ips["eurooffice"]

ansible/
├── playbooks/eurooffice.yml                 # NEW: lxc_base → geerlingguy.docker → eurooffice
├── roles/eurooffice/                        # NEW role (mirrors roles/market_model/)
│   ├── defaults/main.yml                     #   image, dirs, ports, registry
│   ├── tasks/preflight.yml                   #   GHCR creds, pinned tag, JWT ≥32, RAM headroom, Docker up
│   ├── tasks/main.yml                        #   dirs → docker_login → compose template → up → healthcheck
│   ├── templates/docker-compose.yml.j2       #   JWT_ENABLED, JWT_SECRET, EXAMPLE_ENABLED=false, volumes
│   └── handlers/main.yml                      #   Restart eurooffice
├── roles/nextcloud/                          # EXTEND: install/enable/configure eurooffice connector via occ
│   ├── defaults/main.yml                      #   eurooffice_* connector vars; drop richdocuments* already removed
│   └── tasks/main.yml (or connector.yml)      #   app:install eurooffice; occ config:app:set DocumentServerUrl/Internal/jwt
├── roles/reverse_proxy/templates/service.caddy.j2  # EXTEND: optional per-service transport timeout
├── host_vars/eurooffice.yml                  # NEW: healthcheck_url + monitoring_contract (liveness + alert)
└── group_vars/services/
    ├── vars.yml                               # + eurooffice_version pin, ip/port, caddy_services entry
    └── vault.yml                              # + eurooffice_jwt_secret (encrypted; ≥32 chars)

.github/workflows/
├── lxc-deploy-lab.yml                        # + "eurooffice" in service choice options
├── lxc-promote-lab.yml                       # + "eurooffice"
└── lxc-promote-prod.yml                      # + "eurooffice"
```

**Structure Decision**: Infrastructure single-project layout. The document server is a new service
cloned from the `market-model` reference (closest analog: single-image `docker_compose_v2` in a
dedicated LXC, no NFS, published via `caddy_services`, health/monitoring via host_vars). The
Nextcloud-side connector is configuration of an existing service, so it extends the `nextcloud` role
rather than adding a new one. The Caddy timeout is an additive optional field on the existing
`service.caddy.j2` template.

## Complexity Tracking

> No Constitution violations — section intentionally empty.
