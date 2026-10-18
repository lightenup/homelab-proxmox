# Implementation Plan: HTTPS for All Homelab Services

**Branch**: `039-https-services` | **Date**: 2026-02-28 | **Spec**: `specs/039-https-services/spec.md`
**Input**: Feature specification from `specs/039-https-services/spec.md`

---

## Summary

This feature enables HTTPS with valid Let's Encrypt certificates for all homelab services (Nextcloud, Immich, Grafana, Jellyfin) accessed via `<service>.hus-sky.no` subdomains. The approach replaces the stock Caddy binary with a custom xcaddy build including the Domeneshop DNS provider (via `caddy-dns/lego-deprecated`), configures DNS-01 ACME challenges for automatic certificate issuance and renewal, migrates existing services to their new HTTPS domains, and injects registrar API credentials securely via Ansible vault and systemd environment files. All work is Ansible-only — no Terraform changes.

## Technical Context

**Language/Version**: Ansible 2.10+, Jinja2 templates, Go 1.22+ (build dependency for xcaddy)
**Primary Dependencies**: Caddy v2 (custom build), xcaddy, `caddy-dns/lego-deprecated`, `go-acme/lego` v4.9.1
**Storage**: N/A (certificates managed by Caddy in `/var/lib/caddy/`)
**Testing**: `caddy validate` for config, `openssl s_client` for cert verification, `curl` for endpoint testing
**Target Platform**: Proxmox LXC (Debian stable), reverse proxy at 192.168.1.211
**Project Type**: Infrastructure-as-Code (Ansible roles, Jinja2 templates)
**Performance Goals**: Certificates issued within 5 minutes of first deploy (SC per spec US-3)
**Constraints**: No Terraform changes (A-008), no public internet exposure, secrets must never appear in plaintext in repo
**Scale/Scope**: 5 active services + 1 future placeholder, single reverse proxy LXC

## Constitution Check

*GATE: Must pass before implementation. Re-checked after design phase.*

| # | Principle | Status | Evidence |
|---|-----------|--------|----------|
| I | Spec-Driven Workflow | ✅ PASS | All work traces to `specs/039-https-services/spec.md`. Tasks will reference `tasks.md`. |
| II | Secrets Policy | ✅ PASS | Domeneshop API credentials stored in Ansible vault only. Injected via systemd EnvironmentFile with `0600` permissions. Never in Caddyfile templates, never committed to repo. See contract `systemd-override.md`. |
| III | Separation of Concerns | ✅ PASS | All changes are Ansible-only (configuration inside machines). No Terraform changes per A-008. Reverse proxy LXC already exists. |
| IV | Dual-Provisioning Parity | ✅ PASS | Same Ansible playbooks and roles work from both CI (GitHub Actions) and developer laptop. Vault secrets accessible in both contexts. No CI-only steps. |
| — | Token Privilege Tiers | ✅ PASS | No Terraform or Proxmox API operations. No tier changes needed. |
| — | Provider Strategy | ✅ N/A | No Terraform provider changes. |
| — | Networking (Static IPs) | ✅ PASS | All service IPs are static and defined centrally in `group_vars`. No new IPs introduced — only new variables referencing existing IPs. |
| — | Test-Driven Changes | ✅ PASS | Verification steps use `caddy validate`, `openssl s_client`, and `curl` — all non-destructive. |
| — | CI/CD Expectations | ✅ PASS | `reverse_proxy` already exists in the `lxc-deploy-lab.yml` workflow service dropdown. No new services added to Terraform. No new workflow entries needed. |
| — | Local Workflow Testing | ✅ PASS | No workflow changes in this feature. Existing workflows continue to work. |

**Post-Design Re-check**: All principles remain PASS. The lego-deprecated module is deprecated but functional — this is a technology risk, not a constitution violation.

## Project Structure

### Documentation (this feature)

```text
specs/039-https-services/
├── plan.md              # This file
├── research.md          # Phase 0 output — technology decisions
├── data-model.md        # Phase 1 output — entities and variable registry
├── quickstart.md        # Phase 1 output — deployment guide
├── contracts/
│   ├── caddyfile-global.md     # Caddyfile global config contract
│   ├── caddy-site-block.md     # Per-service site block contracts
│   └── systemd-override.md     # Systemd secrets injection contract
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
ansible/
├── roles/
│   └── reverse_proxy/
│       ├── defaults/main.yml           — MODIFIED: add caddy_base_domain, xcaddy, plugin vars
│       ├── tasks/main.yml              — MODIFIED: add xcaddy build, systemd override, new site deploys
│       ├── handlers/main.yml           — MODIFIED: add daemon-reload handler
│       ├── templates/
│       │   ├── Caddyfile.j2            — MODIFIED: remove auto_https off, add acme_dns
│       │   ├── immich.caddy.j2         — MODIFIED: FQDN site address
│       │   ├── nextcloud.caddy.j2      — MODIFIED: FQDN site address, https headers
│       │   ├── grafana.caddy.j2        — NEW: Grafana HTTPS proxy
│       │   ├── jellyfin.caddy.j2       — NEW: Jellyfin HTTPS proxy
│       │   ├── homeassistant.caddy.j2  — NEW: Home Assistant HTTPS proxy (conditional)
│       │   ├── domeneshop.env.j2       — NEW: systemd EnvironmentFile template
│       │   └── caddy-domeneshop.conf.j2 — NEW: systemd drop-in override template
│       └── vars/                       — (optional) role-internal vars
│
├── roles/
│   └── nextcloud/
│       ├── defaults/main.yml           — MODIFIED: update nextcloud_domain default, add migration vars
│       └── templates/.env.j2           — MODIFIED: HTTPS protocol, dual trusted domains
│
├── roles/
│   └── monitoring_stack/
│       ├── templates/docker-compose.yml.j2  — MODIFIED: update GF_SERVER_ROOT_URL
│       └── (group_vars change covers grafana_domain)
│
├── group_vars/
│   ├── services/
│   │   ├── vars.yml                    — MODIFIED: add service IPs/ports, nextcloud_domain
│   │   └── vault.yml                   — MODIFIED: add domeneshop_api_token, domeneshop_api_secret
│   └── monitoring/
│       └── vars.yml                    — MODIFIED: update grafana_domain, add grafana_protocol
│
└── playbooks/
    └── (no changes — existing playbooks apply the roles)
```

**Structure Decision**: This feature modifies existing Ansible roles and group vars. No new roles, playbooks, or Terraform files are created. The reverse_proxy role is the primary change target.

## Technology Choices

| Component | Choice | Rationale |
|-----------|--------|-----------|
| DNS Provider Module | `caddy-dns/lego-deprecated` | Only zero-dev-effort path for Domeneshop DNS-01 with Caddy. See research R-001. |
| Custom Binary Build | `xcaddy` on target LXC | Official Caddy build tool. Building on-target avoids cross-compilation. See R-002. |
| Secrets Injection | systemd EnvironmentFile drop-in | Standard approach for extending APT-managed systemd units. Never exposes secrets in config files. See R-003. |
| Certificate Strategy | Individual certs per subdomain | Caddy default behavior. Simpler config, easier debugging. See R-007. |
| Global ACME Config | `acme_dns` Caddyfile directive | DRY — applies to all site blocks. See R-008. |

## Implementation Steps

### Step 1: Add Service IP/Port Variables to Group Vars

- **Files**:
  - `ansible/group_vars/services/vars.yml` — add `jellyfin_ip`, `jellyfin_port`, `homeassistant_ip`, `homeassistant_port`
- **Description**: Centralize all service IP addresses and ports referenced by the reverse proxy role. Some variables already exist (immich, nextcloud, monitoring); add the missing ones for services newly placed behind the proxy.
- **Dependencies**: None
- **Parallel-safe**: Yes
- **Traces to**: FR-010 (new Caddy site blocks need backend addresses), constitution networking principle (IPs defined centrally)
- **Done-condition**: `ansible-playbook --syntax-check` passes for playbooks referencing these variables. Variables `jellyfin_ip`, `jellyfin_port`, `homeassistant_ip`, `homeassistant_port` are defined in `group_vars/services/vars.yml`.

### Step 2: Add Domeneshop API Credentials to Vault

- **Files**:
  - `ansible/group_vars/services/vault.yml` — add `domeneshop_api_token`, `domeneshop_api_secret`
- **Description**: Add encrypted placeholder entries to the vault file for the Domeneshop API credentials. Actual values are inserted by the operator at deploy time.
- **Dependencies**: None
- **Parallel-safe**: Yes (parallel with Step 1)
- **Traces to**: FR-013, US-5
- **Done-condition**: `ansible-vault view group_vars/services/vault.yml` shows `domeneshop_api_token` and `domeneshop_api_secret` keys. `rg 'domeneshop' --type-not yaml` returns no matches (secrets not in plaintext files).

### Step 3: Update Reverse Proxy Role Defaults

- **Files**:
  - `ansible/roles/reverse_proxy/defaults/main.yml` — add `caddy_base_domain`, `caddy_acme_dns_provider`, `caddy_acme_dns_provider_name`, `caddy_custom_binary`, `caddy_xcaddy_plugins`, `go_version`, `homeassistant_active`
- **Description**: Define default variables for the HTTPS configuration. These provide the domain, DNS provider, xcaddy build configuration, and Home Assistant conditional flag.
- **Dependencies**: None
- **Parallel-safe**: Yes (parallel with Steps 1-2)
- **Traces to**: FR-001, FR-012, FR-015
- **Done-condition**: All new variables are present in `defaults/main.yml` with documented defaults. `ansible-lint` passes on the role.

### Step 4: Update Caddyfile Global Template

- **Files**:
  - `ansible/roles/reverse_proxy/templates/Caddyfile.j2`
- **Description**: Remove `auto_https off` and add `acme_dns {{ caddy_acme_dns_provider }} {{ caddy_acme_dns_provider_name }}` to the global options block. This enables automatic HTTPS with DNS-01 challenges for all site blocks.
- **Dependencies**: Step 3 (variables must exist)
- **Parallel-safe**: No (depends on Step 3)
- **Traces to**: FR-011, FR-002, FR-003 (auto-renewal is inherent once DNS provider is configured)
- **Done-condition**: Template renders without `auto_https off`. Template includes `acme_dns` directive. Jinja2 syntax is valid.

### Step 5: Update Existing Caddy Site Templates (Immich, Nextcloud)

- **Files**:
  - `ansible/roles/reverse_proxy/templates/immich.caddy.j2`
  - `ansible/roles/reverse_proxy/templates/nextcloud.caddy.j2`
- **Description**: Replace the HTTP-only site addresses (`:80`, `http://nextcloud.local`) with FQDN addresses (`immich.{{ caddy_base_domain }}`, `nextcloud.{{ caddy_base_domain }}`). Update `X-Forwarded-Proto` to `https`. Add standard proxy headers.
- **Dependencies**: Step 3 (caddy_base_domain variable)
- **Parallel-safe**: Yes (parallel with Step 4)
- **Traces to**: FR-001, FR-004, FR-005 (DNS records prerequisite documented in quickstart.md)
- **Done-condition**: Templates use `{{ caddy_base_domain }}` for site addresses. No `http://` prefixes in site addresses. `X-Forwarded-Proto` is `https`.

### Step 6: Create New Caddy Site Templates (Grafana, Jellyfin, Home Assistant)

- **Files**:
  - `ansible/roles/reverse_proxy/templates/grafana.caddy.j2` — NEW
  - `ansible/roles/reverse_proxy/templates/jellyfin.caddy.j2` — NEW
  - `ansible/roles/reverse_proxy/templates/homeassistant.caddy.j2` — NEW
- **Description**: Create Caddy site block templates for the three new services plus the Home Assistant placeholder. Follow the contract in `contracts/caddy-site-block.md`. Home Assistant template is conditional on `homeassistant_active`.
- **Dependencies**: Step 1 (service IPs/ports), Step 3 (caddy_base_domain)
- **Parallel-safe**: Yes (parallel with Steps 4-5)
- **Traces to**: FR-010, FR-015, FR-006
- **Done-condition**: Four new `.caddy.j2` files exist. Each follows the contract pattern. Home Assistant template has conditional guard.

### Step 7: Create Systemd Override Templates

- **Files**:
  - `ansible/roles/reverse_proxy/templates/domeneshop.env.j2` — NEW
  - `ansible/roles/reverse_proxy/templates/caddy-domeneshop.conf.j2` — NEW
- **Description**: Create the systemd EnvironmentFile template (secrets) and the systemd drop-in override that references it. Follow the contract in `contracts/systemd-override.md`.
- **Dependencies**: Step 2 (vault variables must exist)
- **Parallel-safe**: Yes (parallel with Steps 4-6)
- **Traces to**: FR-013, US-5, D-006
- **Done-condition**: Both templates exist. The env template references `{{ domeneshop_api_token }}` and `{{ domeneshop_api_secret }}`. The conf template references the env file path.

### Step 8: Update Reverse Proxy Tasks (xcaddy Build + Deploy)

- **Files**:
  - `ansible/roles/reverse_proxy/tasks/main.yml`
- **Description**: Add tasks to:
  1. Install Go and xcaddy (build dependencies)
  2. Build custom Caddy binary with `xcaddy build --with github.com/caddy-dns/lego-deprecated`
  3. Use `dpkg-divert` to protect the custom binary from APT overwrites
  4. Replace `/usr/bin/caddy` with the custom binary
  5. Create systemd override directory
  6. Deploy the domeneshop.env file (mode 0600)
  7. Deploy the systemd drop-in override
  8. Deploy all site block templates (Grafana, Jellyfin, Home Assistant)
  9. Trigger handlers for daemon-reload and restart
- **Dependencies**: Steps 3-7 (all templates and variables must exist)
- **Parallel-safe**: No (this is the main integration step)
- **Traces to**: FR-012, FR-010, FR-013
- **Done-condition**: `ansible-lint` passes on the role. `ansible-playbook --syntax-check` passes. Task file contains all listed operations in correct order.

### Step 9: Update Reverse Proxy Handlers

- **Files**:
  - `ansible/roles/reverse_proxy/handlers/main.yml`
- **Description**: Add a `Reload systemd` handler (for `systemctl daemon-reload`) alongside the existing `Restart caddy` handler. Ensure handler ordering: daemon-reload before restart.
- **Dependencies**: Step 8 (tasks reference these handlers)
- **Parallel-safe**: Yes (parallel with Step 8 conceptually, but same role)
- **Traces to**: FR-013 (secrets injection requires daemon-reload)
- **Done-condition**: Handler file contains both `Reload systemd` (daemon-reload) and `Restart caddy` handlers.

### Step 10: Update Nextcloud Domain Configuration

- **Files**:
  - `ansible/roles/nextcloud/defaults/main.yml` — modify `nextcloud_domain` default, add `nextcloud_trusted_domains_extra`, `nextcloud_overwrite_protocol`
  - `ansible/roles/nextcloud/templates/.env.j2` — update OVERWRITEPROTOCOL, OVERWRITECLIURL, NEXTCLOUD_TRUSTED_DOMAINS
- **Description**: Migrate Nextcloud to the new `nextcloud.hus-sky.no` domain with HTTPS. Add backward compatibility for `nextcloud.local` in trusted domains. The `.env.j2` template will use the new protocol and domain variables.
- **Dependencies**: None (independent of reverse proxy changes)
- **Parallel-safe**: Yes (parallel with Steps 4-9)
- **Traces to**: FR-007, FR-008, FR-016 (data preserved — only URL/protocol changes, no data migration), D-004
- **Done-condition**: `nextcloud_domain` defaults to `nextcloud.hus-sky.no`. `.env.j2` renders `OVERWRITEPROTOCOL=https`. `NEXTCLOUD_TRUSTED_DOMAINS` includes both `nextcloud.hus-sky.no` and `nextcloud.local`. Template syntax is valid.

### Step 11: Update Grafana Domain Configuration

- **Files**:
  - `ansible/group_vars/monitoring/vars.yml` — change `grafana_domain`, add `grafana_protocol`
  - `ansible/roles/monitoring_stack/templates/docker-compose.yml.j2` — update `GF_SERVER_ROOT_URL`
- **Description**: Update Grafana's server domain and root URL to use `grafana.hus-sky.no` with HTTPS. The Docker Compose template's `GF_SERVER_ROOT_URL` must reflect the proxy URL (no port).
- **Dependencies**: None (independent of reverse proxy changes)
- **Parallel-safe**: Yes (parallel with Steps 4-10)
- **Traces to**: FR-009
- **Done-condition**: `grafana_domain` is `grafana.hus-sky.no` in `monitoring/vars.yml`. `GF_SERVER_ROOT_URL` renders as `https://grafana.hus-sky.no` (no port). Template syntax is valid.

### Step 12: Verification — Static Analysis

- **Files**: All modified files
- **Description**: Run `ansible-lint` on all modified roles and playbooks. Run `ansible-playbook --syntax-check` for affected playbooks. Verify no secrets in plaintext with `rg 'domeneshop' --type-not yaml` from repo root.
- **Dependencies**: Steps 1-11
- **Parallel-safe**: No (must run after all changes)
- **Traces to**: SC-005, SC-007, FR-014 (dual-provisioning parity verified — same playbooks used from CI and laptop), constitution II, constitution IV
- **Done-condition**: `ansible-lint` returns 0 on `ansible/roles/reverse_proxy`, `ansible/roles/nextcloud`, `ansible/roles/monitoring_stack`. `ansible-playbook --syntax-check` passes for `playbooks/services.yml` and `playbooks/monitoring.yml`. `rg 'DOMENESHOP_API_TOKEN=(?!{)' . --type-not yaml` returns zero matches (no hardcoded credentials).

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| `caddy-dns/lego-deprecated` becomes incompatible with future Caddy versions | Certificate renewal fails after Caddy upgrade | Pin Caddy version in xcaddy build. Migration path documented: switch to `libdns/domeneshop` when available. APT auto-updates disabled for caddy package. |
| Domeneshop API rate limiting during multiple DNS-01 challenges | Initial certificate issuance fails for some subdomains | Individual certs are issued sequentially by Caddy with built-in retry. 5-6 subdomains is well within any reasonable rate limit. |
| DNS propagation delay causes ACME challenge timeout | Certificate issuance fails on first attempt | Caddy retries automatically. Domeneshop DNS typically propagates within 60 seconds. `lego` defaults to 120s propagation timeout. |
| Nextcloud domain change breaks existing mobile app sessions | Users must re-authenticate | Dual-domain trust (D-004) allows gradual client migration. Document in quickstart.md. |
| xcaddy build fails on the proxy LXC (Go dependency issues) | Custom binary not available | Pin Go version. Consider pre-building binary on CI as fallback approach. |

## Testing Strategy

### Configuration Validation (Static — runs in CI and locally)

- `ansible-lint` on all modified roles
- `ansible-playbook --syntax-check` for affected playbooks
- Grep for plaintext secrets in non-vault files

### Runtime Verification (After deployment — manual or scripted)

- **Certificate verification**: `openssl s_client -connect <service>.hus-sky.no:443` for each service — verify issuer is `Let's Encrypt`, expiry > 60 days
- **HTTP response**: `curl -sI https://<service>.hus-sky.no` — verify 200/301/302 status
- **Mobile app**: Connect Nextcloud and Immich mobile apps to HTTPS URLs
- **Data preservation**: Verify Nextcloud files, Immich photos, Grafana dashboards accessible after migration
- **Secrets audit**: `rg 'DOMENESHOP' . --type-not yaml` returns zero matches in repo

### Coverage Target

- 100% of functional requirements have at least one verification step
- All 5 active services verified for valid HTTPS certificates
- Secrets policy verified by repo-wide search

## Complexity Tracking

No constitution violations. No complexity justifications needed.
