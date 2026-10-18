# Implementation Plan: Self-Hosted Nextcloud Deployment

**Branch**: `034-add-nextcloud` | **Date**: 2026-02-22 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/034-add-nextcloud/spec.md`

## Summary

Deploy a self-hosted Nextcloud instance as a dedicated LXC container with Docker Compose (Nextcloud + MariaDB + Redis), NFS-backed user data on Synology NAS, built-in Collabora CODE for collaborative editing, and automated database backups. The deployment follows the exact Terraform + Ansible patterns established by Immich and Jellyfin, integrating with the existing reverse proxy and monitoring infrastructure.

## Technical Context

**Language/Version**: HCL (Terraform ≥ 1.5.7), YAML (Ansible), Jinja2 (templates), Bash (backup scripts)
**Primary Dependencies**: `telmate/proxmox` Terraform provider (= 2.9.11), `community.docker.docker_compose_v2` Ansible module, `geerlingguy.docker` Ansible role
**Storage**: MariaDB 11 (local disk), Redis 7 (local disk), user files on Synology NAS via NFS
**Testing**: Ansible preflight checks, Docker healthchecks, HTTP health probes, `terraform validate`, `terraform fmt -check`
**Target Platform**: Proxmox VE LXC (Debian stable), Docker Compose inside LXC
**Project Type**: Infrastructure-as-Code (Terraform + Ansible)
**Performance Goals**: <5 users, service accessible within 3 minutes of reboot, collaborative editing <5s sync
**Constraints**: LAN-only access, no public internet exposure, NFS for user data only (never for DB)
**Scale/Scope**: 1 LXC, 3 Docker containers, ~15 new files, ~5 modified files

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| I. Spec-Driven Workflow | ✅ PASS | All tasks trace to FR/US IDs from spec.md; tasks.md is generated from this plan |
| II. Secrets Policy | ✅ PASS | Secrets referenced as Ansible variables (`{{ nextcloud_db_password }}`), supplied at runtime; .env template rendered with mode 0600; no secrets in git |
| III. Separation of Concerns | ✅ PASS | Terraform: LXC existence, sizing, bind mounts; Ansible: Docker Compose, app config, backup. Clear boundary. |
| Provider Strategy | ✅ PASS | Uses existing `telmate/proxmox` provider via `lxc_service` module; no provider change |
| Networking | ✅ PASS | Static IP `192.168.20.216/24` in `service_ips` map; centralized in tfvars |
| Access Control | ✅ PASS | SSH via Terraform-injected public keys; Ansible as root (homelab tradeoff) |
| State Management | ✅ PASS | Local Terraform state on PVE host; no remote state introduction |
| Storage | ✅ PASS | NFS from Synology for user data; local disk for DB (per NFS gotchas in research.md §9) |
| Services Model | ✅ PASS | One LXC (`nextcloud-lxc`) running Docker Compose with 3 containers |
| Test-Driven Changes | ✅ PASS | Preflight checks, healthchecks, `terraform validate`, `terraform fmt` |
| Repo Layout | ✅ PASS | `terraform/services/nextcloud/`, `ansible/roles/nextcloud/`, `specs/034-*` |

## Project Structure

### Documentation (this feature)

```text
specs/034-add-nextcloud/
├── plan.md                                # This file
├── research.md                            # Phase 0 output — technology decisions
├── data-model.md                          # Phase 1 output — entity definitions
├── quickstart.md                          # Phase 1 output — deployment guide
├── contracts/
│   ├── terraform-service.hcl              # Terraform module interface contract
│   ├── ansible-role-interface.yml         # Ansible role interface contract
│   └── docker-compose-contract.yml        # Docker Compose stack contract
├── checklists/
│   └── requirements.md                    # Spec quality checklist
└── tasks.md                               # Implementation tasks (from /speckit.tasks)
```

### Source Code (repository root)

```text
terraform/
├── main.tf                                # ADD: nextcloud_lxc module block
├── outputs.tf                             # ADD: nextcloud to ansible_inventory
├── environments/
│   ├── prod.tfvars.example                # ADD: nextcloud IP + mountpoints
│   └── lab.tfvars.example                 # ADD: nextcloud IP + mountpoints
└── services/nextcloud/                    # NEW: per-service Terraform wrapper
    ├── main.tf                            # Module instantiation
    ├── variables.tf                       # Pass-through variables (identical to immich)
    ├── outputs.tf                         # Inventory output
    └── providers.tf                       # Provider config (telmate/proxmox = 2.9.11)

ansible/
├── roles/nextcloud/                       # NEW: main service role
│   ├── defaults/main.yml                  # Default variables
│   ├── tasks/main.yml                     # Service deployment flow
│   ├── tasks/preflight.yml                # Pre-deployment validation
│   ├── templates/docker-compose.yml.j2    # 3-service Docker Compose stack
│   ├── templates/.env.j2                  # Runtime environment variables
│   └── handlers/main.yml                  # Restart handler
├── roles/nextcloud_backup/                # NEW: backup role
│   ├── tasks/main.yml                     # Systemd timer + script deployment
│   ├── templates/backup_nextcloud.sh.j2   # Backup script (mysqldump + config copy)
│   └── handlers/main.yml                  # Systemd daemon-reload
├── roles/reverse_proxy/templates/
│   └── nextcloud.caddy.j2                # NEW: Caddy site config for Nextcloud
├── roles/reverse_proxy/tasks/main.yml     # MODIFY: add Nextcloud caddy deploy task
├── playbooks/nextcloud.yml                # NEW: per-service playbook
├── playbooks/services.yml                 # NEW: aggregator (site.yml already references this)
├── group_vars/services/vars.yml           # MODIFY: add nextcloud_* variables
└── host_vars/nextcloud.yml                # NEW: healthcheck config

docs/
└── naming-and-mdns.md                     # MODIFY: add nextcloud.local row
```

**Structure Decision**: Follows the established per-service pattern (Terraform wrapper + Ansible role + playbook), matching Immich (base service) and Jellyfin (NFS mounts) as reference implementations. No new structural conventions introduced.

## Architecture Overview

### Component Flow

```
Terraform → LXC Container (4 cores, 4 GB RAM, 32 GB disk)
  ├── NFS bind mount: /mnt/nas/homelab_nextcloud → /mnt/nextcloud (inside LXC)
  └── Static IP: 192.168.20.216/24

Ansible → Inside LXC:
  ├── lxc_base role (base packages, SSH)
  ├── geerlingguy.docker role (Docker CE)
  ├── nextcloud role (Docker Compose stack):
  │   ├── nextcloud_app (Nextcloud 30 + Apache + built-in CODE)
  │   │   ├── /var/www/html → local disk (app code, config.php)
  │   │   └── /var/www/html/data → NAS (/mnt/nextcloud/data)
  │   ├── nextcloud_db (MariaDB 11)
  │   │   └── /var/lib/mysql → local disk (/opt/nextcloud/mariadb)
  │   └── nextcloud_redis (Redis 7 Alpine)
  │       └── /data → local disk (/opt/nextcloud/redis)
  ├── nextcloud_backup role (systemd timer + mysqldump script)
  └── Caddy reverse proxy config (http://nextcloud.local → 192.168.20.216:8080)
```

### Key Design Decisions

1. **MariaDB over PostgreSQL**: Nextcloud's recommended DB engine, best community support (research.md §1).

2. **Built-in CODE over separate Collabora**: Integrated collaborative editing engine sufficient for <5 users, no extra container (research.md §2). Matches spec assumption.

3. **Jinja-rendered templates** (not `${VAR}` shell interpolation): Docker Compose and .env files are Ansible Jinja2 templates, following the exact Immich pattern where secrets like `POSTGRES_PASSWORD: {{ immich_db_password }}` are rendered at deploy time. The `.env` file (mode 0600) holds runtime environment variables for the containers via `env_file:`.

4. **Caddy hostname-based routing**: The Nextcloud Caddy config uses `http://nextcloud.local` as the site address, coexisting with Immich's `:80` catch-all. Caddy merges imported site blocks into virtual hosts — requests with `Host: nextcloud.local` route to Nextcloud, all other `:80` traffic routes to Immich. **DNS resolution note**: mDNS from the Nextcloud LXC advertises `192.168.20.216` (the LXC IP). For proxy-routed access, a DNS entry or `/etc/hosts` entries are needed to resolve `nextcloud.local` → `192.168.20.211` (proxy IP). Direct access via `http://192.168.20.216:8080` always works as a fallback (FR-012 edge case in spec).

5. **`features_mount` is informational**: The `features_mount = "nfs"` variable is declared in the `lxc_service` module but NOT applied in the Terraform resource block (the module comment says "mount feature is applied host-side by orchestrator via `pct set`"). It is included for documentation and future use. The actual NFS bind mount is handled by the `mountpoints` variable which creates `proxmox_lxc` mountpoint blocks.

6. **`services.yml` gap**: `site.yml` references `import_playbook: services.yml` but this file does not exist. This plan creates it as an aggregator, unblocking the full `site.yml` execution.

## Technology Choices

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Database | MariaDB 11 | Nextcloud-recommended, best community support, PHP ecosystem alignment |
| Collaborative editing | Built-in CODE (`richdocumentscode`) | Simplest for <5 users, no extra container, matches spec assumption |
| Caching | Redis 7 + APCu | Redis for distributed cache + file locking (required for NFS); APCu for local cache |
| Docker image variant | `nextcloud:30` (Apache) | Simpler than FPM+nginx, sufficient for this scale |
| Data storage | NFS mount → NAS (user data); local disk (DB) | NFS for data resilience; local for DB performance/integrity |
| Backup | `mysqldump --single-transaction` via systemd timer | Standard approach, matches `immich_backup` pattern |
| 2FA | TOTP via `twofactor_totp` app | Built-in, no external dependencies |
| Reverse proxy | Caddy (hostname-based virtual host) | Existing infrastructure; `http://nextcloud.local` site block |
| LXC resources | 4 cores, 4 GB RAM, 32 GB disk | Covers Nextcloud + MariaDB + Redis + built-in CODE comfortably |

## Implementation Steps

### Step 1: Terraform — Per-Service Wrapper

- **Files**: `terraform/services/nextcloud/main.tf`, `variables.tf`, `outputs.tf`, `providers.tf` (all NEW)
- **Description**: Create the per-service Terraform wrapper for standalone Nextcloud LXC provisioning. Clone the exact pattern from `terraform/services/jellyfin/` (which includes `features_mount` and `mountpoints`). Set `cores=4`, `memory=4096`, `disk_gb=32`. Use `source = "../../modules/lxc_service"`.
- **Dependencies**: None
- **Parallel-safe**: Yes
- **Traces to**: FR-018, FR-014, FR-015

### Step 2: Terraform — Environment Variables

- **Files**: `terraform/environments/prod.tfvars.example`, `terraform/environments/lab.tfvars.example` (both MODIFY)
- **Description**: Add `nextcloud = "192.168.20.216/24"` to `service_ips` map. Add `nextcloud = { data = { mp = "/mnt/nextcloud", volume = "/mnt/nas/homelab_nextcloud" } }` to `service_mountpoints` map.
- **Dependencies**: None
- **Parallel-safe**: Yes
- **Traces to**: FR-014, FR-018

### Step 3: Terraform — Root Module Integration

- **Files**: `terraform/main.tf`, `terraform/outputs.tf` (both MODIFY)
- **Description**: Add `module "nextcloud_lxc"` block to root `main.tf` following the Jellyfin pattern (includes `features_mount = "nfs"` and `mountpoints`). Add `nextcloud = module.nextcloud_lxc.ipv4` to the `ansible_inventory` output's `services` map.
- **Dependencies**: None (root module is independent of per-service wrappers)
- **Parallel-safe**: Yes
- **Traces to**: FR-018

### Step 4: Terraform — Validation

- **Files**: None (verification only)
- **Description**: Run `terraform fmt -check` and `terraform validate` on root module and `services/nextcloud/` directory. Fix any formatting or validation errors.
- **Dependencies**: Step 1, Step 2, Step 3
- **Parallel-safe**: No
- **Traces to**: FR-016

### Step 5: Ansible — Host Variables

- **Files**: `ansible/host_vars/nextcloud.yml` (NEW)
- **Description**: Create healthcheck configuration. Use `healthcheck_profile: lan` (not `both`) since Nextcloud is LAN-only. Use `/login` path (returns 200 when installed). Match the pattern from `host_vars/immich.yml`.
- **Dependencies**: None
- **Parallel-safe**: Yes
- **Traces to**: FR-015 (health observable)

### Step 6: Ansible — Group Variables

- **Files**: `ansible/group_vars/services/vars.yml` (MODIFY)
- **Description**: Append the `nextcloud_*` configuration block following the `immich_*` naming pattern. Include version, port, paths, domain, container names, and backup config. **Secrets are NOT defined here** — they follow the same external-supply mechanism as `immich_db_password` (runtime vars/vault).
- **Dependencies**: None
- **Parallel-safe**: Yes
- **Traces to**: All FRs (enables configuration)

### Step 7: Ansible — Nextcloud Role Defaults

- **Files**: `ansible/roles/nextcloud/defaults/main.yml` (NEW)
- **Description**: Create role defaults with safe default values. Include app enable/disable lists: enable `richdocuments`, `richdocumentscode`, `deck`, `twofactor_totp`, `bruteforcesettings`; disable `photos`, `weather_status`, `firstrunwizard`, `recommendations`. Secrets are NOT in defaults.
- **Dependencies**: None
- **Parallel-safe**: Yes
- **Traces to**: FR-006, FR-010, FR-011, FR-013, FR-020

### Step 8: Ansible — Nextcloud Role Templates

- **Files**: `ansible/roles/nextcloud/templates/docker-compose.yml.j2`, `ansible/roles/nextcloud/templates/.env.j2` (both NEW)
- **Description**: Create the Docker Compose template (3 services: nextcloud, mariadb, redis) and .env template. **Pattern**: Follow the Immich approach — use Jinja `{{ var }}` for all template variables (image version, ports, volume paths, secrets). The compose file uses `env_file: - .env` for runtime environment variables. The .env file is mode 0600. MariaDB command includes `--transaction-isolation=READ-COMMITTED --log-bin=binlog --binlog-format=ROW`. Healthchecks on all services.
- **Dependencies**: None
- **Parallel-safe**: Yes
- **Traces to**: FR-001 through FR-014a, FR-019

### Step 9: Ansible — Nextcloud Role Tasks

- **Files**: `ansible/roles/nextcloud/tasks/main.yml`, `tasks/preflight.yml`, `handlers/main.yml` (all NEW)
- **Description**: Create the main deployment task file, preflight checks, and restart handler. Task flow matches Immich: preflight → create dirs → template compose + .env → start stack → wait for port → wait for install → configure apps (occ) → set config values → health check. **occ command specifics**: use exact syntax `php occ config:system:set redis host --value="redis"`, `php occ config:system:set redis port --value=6379 --type=integer`, etc. All occ commands are idempotent — use `changed_when: false` for config commands, `failed_when` + `register` for app installs.
- **Dependencies**: Step 7 (defaults), Step 8 (templates)
- **Parallel-safe**: No
- **Traces to**: FR-001 through FR-020

### Step 10: Ansible — Reverse Proxy Caddy Configuration

- **Files**: `ansible/roles/reverse_proxy/templates/nextcloud.caddy.j2` (NEW), `ansible/roles/reverse_proxy/tasks/main.yml` (MODIFY)
- **Description**: Create the Caddy site config using `http://nextcloud.local` as site address (hostname-based virtual host). Add deploy task following the exact Immich pattern: template → validate → notify restart. The template file is a standalone valid Caddyfile (required for `caddy validate` on the individual snippet). Include `header_up X-Forwarded-Proto http`, `header_up X-Real-IP {remote_host}`, `header_up X-Forwarded-For {remote_host}`.
- **Dependencies**: None
- **Parallel-safe**: Yes
- **Traces to**: FR-012

### Step 11: Ansible — Nextcloud Backup Role

- **Files**: `ansible/roles/nextcloud_backup/tasks/main.yml`, `templates/backup_nextcloud.sh.j2`, `handlers/main.yml` (all NEW)
- **Description**: Create backup role following the `immich_backup` pattern. Systemd timer + oneshot service → backup script. Script: enable maintenance mode → `mysqldump --single-transaction --default-character-set=utf8mb4` → copy `config.php` → disable maintenance mode (via `trap` to ensure cleanup on failure) → compress → GFS retention pruning. **DB password sourcing**: the script sources `.env` from `{{ nextcloud_install_dir }}` to get `MYSQL_PASSWORD`. **Note**: `MYSQL_ROOT_PASSWORD` in the .env is first-run only (MariaDB ignores it after initial database creation).
- **Dependencies**: Step 8 (for .env pattern)
- **Parallel-safe**: Yes
- **Traces to**: FR-021, FR-022

### Step 12: Ansible — Nextcloud Playbook

- **Files**: `ansible/playbooks/nextcloud.yml` (NEW)
- **Description**: Create per-service playbook with two plays: (1) base provisioning with `lxc_base` role, (2) service deployment with `geerlingguy.docker` + `nextcloud` + `nextcloud_backup` roles. Include NAS mount conditional: `nextcloud_require_nas_mount: "{{ (deploy_environment | default('prod')) != 'lab' }}"`. Backup role is included in the same playbook (not separate, unlike Immich which added it retroactively).
- **Dependencies**: Step 9 (nextcloud role), Step 11 (backup role)
- **Parallel-safe**: No
- **Traces to**: FR-015, FR-016

### Step 13: Ansible — Services Aggregator Playbook

- **Files**: `ansible/playbooks/services.yml` (NEW)
- **Description**: Create the aggregator playbook that `site.yml` already references via `import_playbook: services.yml`. Import all per-service playbooks with tags: `immich.yml`, `jellyfin.yml`, `nextcloud.yml`. Only include playbooks confirmed to exist. **Note**: `reverse_proxy.yml` does NOT exist as a standalone playbook — excluded.
- **Dependencies**: Step 12 (nextcloud playbook)
- **Parallel-safe**: No
- **Traces to**: FR-016

### Step 14: Ansible — Site Playbook Verification

- **Files**: `ansible/playbooks/site.yml` (VERIFY, likely no changes needed)
- **Description**: Verify that `site.yml`'s existing `import_playbook: services.yml` reference now works with the newly created `services.yml`. No modification expected.
- **Dependencies**: Step 13
- **Parallel-safe**: No
- **Traces to**: FR-016

### Step 15: Documentation — Network Registry Update

- **Files**: `docs/naming-and-mdns.md` (MODIFY)
- **Description**: Add `| nextcloud.local | 192.168.20.216 | Nextcloud Cloud Storage |` to the addressing table. Follow the existing row format.
- **Dependencies**: None
- **Parallel-safe**: Yes
- **Traces to**: FR-012

## Task Dependency Graph

```
Batch 1 (all parallel): Steps 1, 2, 3, 5, 6, 7, 8, 10, 11, 15
Batch 2 (after Batch 1): Steps 4, 9
Batch 3 (after Batch 2): Step 12
Batch 4 (after Batch 3): Steps 13, 14
```

```
S-01 ──┐
S-02 ──┤
S-03 ──┼──► S-04 (Terraform validation)
       │
S-05 ──┤
S-06 ──┤
S-07 ──┼──► S-09 (Nextcloud role tasks)
S-08 ──┘         │
                 ├──► S-12 (Playbook)
S-11 ────────────┘         │
                           ├──► S-13 (services.yml)
                           │         │
                           │         └──► S-14 (site.yml verify)
S-10 ──┤
S-15 ──┘ (parallel, no deps)
```

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| NFS mount unavailable at boot | Service fails to start, potential data path confusion | Preflight check in Ansible; `nextcloud_require_nas_mount` conditional; Docker `restart: always` retries |
| MariaDB data corruption from NFS | Database corruption, data loss | DB data on local disk only (never NFS); documented in contracts and templates |
| Caddy hostname routing requires DNS rewrite | `nextcloud.local` resolves to LXC IP, not proxy IP | Direct IP access as fallback; DNS entry documented in quickstart; existing pattern for all services |
| Nextcloud first-install timeout | Ansible task fails on slow first-run | Extended `wait_for` timeout (300s); separate poll for `status.php` `"installed":true` |
| `features_mount` not applied by Terraform | NFS mount feature not set on LXC | Document that host-side `pct set` handles this; Ansible preflight verifies mount availability |
| Secrets exposed in git | Credential leak | Secrets as Ansible variables (runtime-supplied); .env mode 0600; no secrets in templates; constitution gate II |
| `services.yml` import breaks existing playbooks | `site.yml` execution failure | Only import confirmed-existing playbooks; test with `ansible-playbook --syntax-check` |
| Built-in CODE performance insufficient | Slow collaborative editing | Spec assumes <5 users; upgrade path documented to separate Collabora container |

## Testing Strategy

- **Terraform validation**: `terraform fmt -check` and `terraform validate` on root module and `services/nextcloud/` (Step 4)
- **Ansible syntax check**: `ansible-playbook --syntax-check playbooks/nextcloud.yml` and `playbooks/services.yml`
- **Preflight checks**: NAS mount availability, Docker running, disk space, required variables (built into role)
- **Docker healthchecks**: MariaDB (`healthcheck.sh --connect --innodb_initialized`), Redis (`redis-cli ping`), Nextcloud (`curl /status.php`)
- **HTTP health probe**: `GET /login` returns 200 (host_vars healthcheck config)
- **Caddy validation**: `caddy validate --adapter caddyfile --config %s` on individual snippet
- **Coverage target**: Not applicable (IaC project — validation via `terraform validate`, `ansible --syntax-check`, and runtime healthchecks replace unit test coverage)

## Traceability Matrix

| Requirement | Steps |
|-------------|-------|
| FR-001 (web file management) | 8, 9 |
| FR-002 (file versioning) | 9 (Nextcloud built-in) |
| FR-003 (trash bin) | 9 (Nextcloud built-in) |
| FR-004 (sharing) | 9 (Nextcloud built-in) |
| FR-005 (WebDAV) | 9 (Nextcloud built-in) |
| FR-006 (collaborative editing) | 7, 9 (richdocuments + richdocumentscode) |
| FR-007 (multi-user editing <5s) | 8 (Redis), 9 (CODE setup) |
| FR-008 (Markdown editing) | 9 (text app, bundled) |
| FR-009 (user management) | 9 (Nextcloud built-in) |
| FR-010 (2FA TOTP) | 7, 9 (twofactor_totp) |
| FR-011 (brute-force) | 7, 9 (bruteforcesettings + whitelist) |
| FR-012 (reverse proxy) | 10 (Caddy config) |
| FR-013 (Kanban/Deck) | 7, 9 (deck app) |
| FR-014 (user data on NAS) | 1, 2, 3, 8 (volume mapping) |
| FR-014a (DB survives rebuild) | 8 (local volume), 11 (backup) |
| FR-015 (auto-start) | 1, 3 (onboot), 8 (restart: always) |
| FR-016 (idempotent deploy) | 9 (idempotent occ), 12, 13 |
| FR-017 (version upgrades) | 6, 7 (version var), 9 (pull: always) |
| FR-018 (dedicated LXC) | 1, 2, 3 |
| FR-019 (rate limiting) | 9 (trusted_proxies), 8 (Redis) |
| FR-020 (excluded apps disabled) | 7, 9 (apps_disable list) |
| FR-021 (backup) | 11 (backup role) |
| FR-022 (restore) | 11 (backup enables restore) |

## Self-Critique Resolution

Issues from the previous planning iteration and their resolutions:

### [RESOLVED — Medium] Caddy mDNS/DNS Routing (was T-10)

**Issue**: Immich's Caddy config uses `:80` (catch-all). Adding `http://nextcloud.local` requires DNS resolution to the proxy IP, not the Nextcloud LXC IP. mDNS from the LXC advertises the LXC's own IP.

**Resolution**: Use `http://nextcloud.local` as the Caddy site address. Caddy correctly handles hostname-based virtual hosting: requests with `Host: nextcloud.local` route to Nextcloud; all other `:80` traffic falls through to Immich's catch-all. DNS resolution to the proxy IP is documented as a configuration step (a DNS entry or `/etc/hosts`). Direct access via `http://192.168.20.216:8080` always works as a fallback. This is an existing infrastructure pattern limitation, not a Nextcloud-specific issue.

### [RESOLVED — Medium] Docker Compose Env Var Pattern (was T-08)

**Issue**: The previous plan suggested `${VAR}` shell-style interpolation in `docker-compose.yml.j2` for secrets. The actual codebase pattern (Immich) uses Jinja `{{ var }}` directly in the compose template.

**Resolution**: Updated Step 8 and the docker-compose contract to use Jinja `{{ var }}` rendering, matching the Immich pattern exactly. Secrets (like `POSTGRES_PASSWORD: {{ immich_db_password }}`) are rendered at Ansible template time. The `.env` file holds runtime container environment variables.

### [RESOLVED — Low] occ Redis Config Syntax (was T-09)

**Issue**: Redis configuration via `occ config:system:set` requires specific syntax with `--type` flags and proper quoting.

**Resolution**: Documented exact occ syntax in Step 9: `php occ config:system:set redis host --value="redis"`, `php occ config:system:set redis port --value=6379 --type=integer`, `php occ config:system:set redis password --value="$REDIS_PASSWORD"`.

### [RESOLVED — Low] MYSQL_ROOT_PASSWORD First-Run Only (was T-08)

**Issue**: `MYSQL_ROOT_PASSWORD` is only used by MariaDB on first database initialization. Changing it afterward has no effect.

**Resolution**: Documented in Step 11 backup role description. No design change needed — this is expected MariaDB behavior.

### [RESOLVED — Low] features_mount Not Applied by Module (new finding)

**Issue**: The `features_mount` variable is declared in `lxc_service` module's `variables.tf` but NOT referenced in the module's `main.tf` resource block. The comment says "mount feature is applied host-side by orchestrator via `pct set`".

**Resolution**: Documented in Architecture Overview point 5. The `features_mount = "nfs"` is included for documentation purposes and future use. The actual NFS bind mount works via the `mountpoints` variable's dynamic `mountpoint` blocks. Ansible preflight checks verify mount availability regardless.

## Complexity Tracking

No constitution violations requiring justification. All principles PASS.
