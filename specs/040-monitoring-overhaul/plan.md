# Implementation Plan: Monitoring & Observability Overhaul

**Branch**: `040-monitoring-overhaul` | **Date**: 2026-03-01 | **Spec**: `specs/040-monitoring-overhaul/spec.md`

## Summary

This plan transforms the homelab monitoring from a minimal two-target Prometheus setup into a comprehensive observability platform covering all 7 service containers with infrastructure metrics (node_exporter), application metrics for Caddy and Immich, unified alerting that replaces Uptime Kuma, and an extensible self-registration pattern using Ansible `hostvars`-based monitoring contracts. The approach follows the existing IaC patterns: a new `node_exporter` role deployed via `lxc_base`, monitoring contracts in service role defaults, and template-driven aggregation in the `monitoring_stack` role.

## Technical Context

**Language/Version**: Ansible (YAML/Jinja2), Prometheus 3.x PromQL, Grafana 12.x JSON Schema v1
**Primary Dependencies**: Ansible roles, Docker Compose, Prometheus node_exporter v1.10.2
**Storage**: Prometheus TSDB (Docker volume), Grafana SQLite (Docker volume)
**Testing**: `ansible-lint`, `yamllint`, `promtool check config`, `promtool check rules`, Ansible `--check` mode
**Target Platform**: Debian-stable LXC containers on Proxmox VE
**Project Type**: Infrastructure-as-Code (Ansible roles + Jinja2 templates)
**Performance Goals**: <5 min alert delivery, <5s dashboard load (24h range), <50 MB agent RAM (NFR-001–NFR-004)
**Constraints**: <4 GB RAM total on monitoring LXC (NFR-002), <25 GB TSDB disk with 15-day retention (NFR-005)
**Scale/Scope**: 7 LXC containers, 9 scrape targets (7 node_exporter + 2 app metrics), ~15 alert rules

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Principle | Status | Evidence |
|---|-----------|--------|----------|
| I | Spec-Driven Workflow | ✅ PASS | All work traces to `specs/040-monitoring-overhaul/spec.md`. Plan references FR/AC/SC identifiers. |
| II | Secrets Policy | ✅ PASS | No new secrets introduced. Existing SMTP creds stay in vault. Kuma secrets removed from vault. node_exporter has no secrets. |
| III | Separation of Concerns | ✅ PASS | Terraform not touched. All changes are Ansible configuration inside existing LXCs. No container creation/sizing changes. |
| IV | Dual-Provisioning Parity | ✅ PASS | All changes are Ansible playbooks runnable from both CI/CD (self-hosted runner) and laptop. No CI-only paths. Service scope allowlist already includes all 7 services. No new service to add. |
| WF-1 | Test-Driven Changes | ✅ PASS | `promtool check config/rules` for Prometheus validation; `ansible-lint` for role quality; `--check` mode for dry-run; explicit verification tasks in monitoring_stack role. |
| WF-2 | CI/CD Expectations | ✅ PASS | No destructive automation. Uptime Kuma cleanup is additive (removes dead container, idempotent). All changes deploy via existing playbook pipeline. |
| NET-1 | Static IPs | ✅ PASS | All service IPs from inventory (192.168.1.211–216). node_exporter port 9100, Caddy metrics 2019, Immich metrics 8081/8082 — all defined as variables, not scattered. |
| SEC-1 | No plaintext secrets | ✅ PASS | Reviewed: no new secrets. Existing SMTP config in vault. Kuma secrets removed. |

## Project Structure

### Documentation (this feature)

```text
specs/040-monitoring-overhaul/
├── spec.md                  # Feature specification (existing)
├── plan.md                  # This file
├── research.md              # Phase 0 research output
├── data-model.md            # Entity definitions and variable registry
├── quickstart.md            # Deployment guide
├── contracts/               # API/config contracts
│   ├── monitoring-contract-schema.yml
│   ├── prometheus-scrape-config.yml
│   ├── alertmanager-config.yml
│   └── alert-rules.yml
└── tasks.md                 # Implementation tasks (Phase 2 - /speckit.tasks)
```

### Source Code (repository root)

```text
ansible/
├── roles/
│   ├── node_exporter/                   # NEW ROLE — infrastructure metrics agent
│   │   ├── defaults/main.yml            # Version pin, port, collector flags
│   │   ├── tasks/main.yml               # Download, install, configure, start
│   │   ├── templates/
│   │   │   └── node_exporter.service.j2 # Systemd unit template
│   │   └── handlers/main.yml            # Restart handler
│   │
│   ├── lxc_base/
│   │   └── tasks/main.yml               # MODIFIED — include node_exporter role
│   │
│   ├── monitoring_stack/
│   │   ├── defaults/main.yml            # MODIFIED — version alignment (FR-026)
│   │   ├── tasks/main.yml               # MODIFIED — add Kuma cleanup, alert validation
│   │   ├── tasks/kuma_cleanup.yml        # NEW — stop/remove Uptime Kuma container
│   │   ├── tasks/validate_alerts.yml     # NEW — promtool check before activation
│   │   ├── tasks/provision_dashboards.yml # NEW — aggregate dashboards from service roles
│   │   ├── templates/prometheus.yml.j2   # MODIFIED — self-registration scrape configs
│   │   ├── templates/alertmanager.yml.j2 # MODIFIED — updated inhibition rules
│   │   ├── templates/monitoring-stack.service.j2 # MODIFIED — remove "(Uptime Kuma)"
│   │   ├── files/prometheus/alerts.yml   # PRESERVED — Synology alerts (renamed to synology_alerts.yml)
│   │   ├── files/prometheus/infrastructure_alerts.yml # NEW — infrastructure + service-down rules
│   │   ├── files/prometheus/service_alerts.yml.j2     # NEW TEMPLATE — aggregated from contracts
│   │   ├── files/grafana/dashboards/synology-nas.json           # PRESERVED (FR-019)
│   │   └── files/grafana/dashboards/infrastructure-overview.json # NEW (FR-016)
│   │
│   ├── reverse_proxy/
│   │   ├── defaults/main.yml            # MODIFIED — add caddy_metrics_*, monitoring_contract
│   │   ├── templates/Caddyfile.j2       # MODIFIED — add metrics global option + dedicated :9180 site block
│   │   └── files/grafana/dashboards/caddy-reverse-proxy.json # NEW (FR-017, owned by service)
│   │
│   ├── immich/
│   │   ├── defaults/main.yml            # MODIFIED — add immich_metrics_*, monitoring_contract
│   │   ├── templates/.env.j2            # MODIFIED — add IMMICH_TELEMETRY_INCLUDE
│   │   ├── templates/docker-compose.yml.j2 # MODIFIED — expose metrics ports
│   │   └── files/grafana/dashboards/immich-photo-service.json # NEW (FR-018, owned by service)
│   │
│   ├── jellyfin/
│   │   └── defaults/main.yml            # MODIFIED — add monitoring_contract (node_exporter only)
│   │
│   ├── nextcloud/
│   │   └── defaults/main.yml            # MODIFIED — add monitoring_contract (node_exporter only)
│   │
│   ├── proxmox_backup/
│   │   ├── defaults/main.yml            # MODIFIED — remove kuma_only, kuma_push_url
│   │   ├── tasks/main.yml               # MODIFIED — remove kuma_only include/condition
│   │   ├── tasks/configure_kuma.yml     # DELETED
│   │   ├── templates/proxmox-backup.conf.j2       # MODIFIED — remove KUMA_URL
│   │   └── templates/proxmox-config-backup.sh.j2  # MODIFIED — remove send_kuma_notification
│   │
│   └── uptime_kuma/                     # DELETED — entire directory (FR-020)
│
├── host_vars/
│   └── monitoring/
│       ├── vars.yml                     # MODIFIED — remove Kuma vars, add alert_down_threshold
│       └── vault.yml.example            # MODIFIED — remove Kuma secrets
│
├── group_vars/
│   └── proxmox_hosts/
│       └── vars.yml                     # MODIFIED — remove commented kuma_url
│
└── playbooks/
    └── monitoring.yml                   # UNCHANGED (roles list unchanged)

docs/
├── operations.md                        # MODIFIED — update Kuma references
├── operations/
│   ├── backups-proxmox-config.md        # MODIFIED — remove Kuma monitoring section
│   └── backups-proxmox-config-email-decommission.md # MODIFIED — remove kuma_only state
└── architecture.md                      # MODIFIED — update monitoring references
```

**Structure Decision**: This is an Infrastructure-as-Code project using Ansible roles. The structure follows the existing `ansible/roles/<name>/` convention. One new role (`node_exporter`) is created; all other changes modify existing roles. No new directory patterns are introduced.

## Implementation Steps

### Step 1: Create node_exporter Ansible Role
- **Files**:
  - `ansible/roles/node_exporter/defaults/main.yml` — CREATE
  - `ansible/roles/node_exporter/tasks/main.yml` — CREATE
  - `ansible/roles/node_exporter/templates/node_exporter.service.j2` — CREATE
  - `ansible/roles/node_exporter/handlers/main.yml` — CREATE
- **Description**: Create a new Ansible role that downloads node_exporter v1.10.2 binary, creates a `node_exporter` system user, installs a systemd unit with LXC-appropriate collector flags, enables and starts the service. The role is idempotent: if the binary is already at the correct version, skip download. The systemd unit uses `--no-collector.hwmon --no-collector.thermal_zone` etc. for LXC environments (see research.md R-02).
- **Traces to**: FR-001, FR-002, US-1
- **Dependencies**: None
- **Parallel-safe**: Yes

### Step 2: Integrate node_exporter into lxc_base Role
- **Files**:
  - `ansible/roles/lxc_base/tasks/main.yml` — MODIFY
- **Description**: Add `include_role: name=node_exporter` to the end of `lxc_base/tasks/main.yml`. This ensures every LXC that uses `lxc_base` (all service playbooks do) automatically gets node_exporter deployed. Guard with `when: node_exporter_enabled | default(true)` so it can be disabled per-host if needed.
- **Traces to**: FR-001, FR-003, DL-10
- **Dependencies**: Step 1
- **Parallel-safe**: No (depends on Step 1)

### Step 3: Add Monitoring Contracts to Service Roles (node_exporter only)
- **Files**:
  - `ansible/roles/jellyfin/defaults/main.yml` — MODIFY
  - `ansible/roles/nextcloud/defaults/main.yml` — MODIFY
- **Description**: Add a `monitoring_contract` variable to each service role's defaults with `enabled: true` and a single scrape target for node_exporter (port 9100, path /metrics). These services have no native application metrics — only infrastructure metrics via node_exporter. The contract uses the standardised schema from `contracts/monitoring-contract-schema.yml`.
- **Traces to**: FR-007, US-4
- **Dependencies**: None (schema only, no runtime dependency)
- **Parallel-safe**: Yes

### Step 4: Enable Caddy Metrics and Add Monitoring Contract
- **Files**:
  - `ansible/roles/reverse_proxy/defaults/main.yml` — MODIFY
  - `ansible/roles/reverse_proxy/templates/Caddyfile.j2` — MODIFY
- **Description**: Add `caddy_metrics_enabled` and `caddy_metrics_port` (9180) variables to reverse_proxy defaults. Modify `Caddyfile.j2` to include `servers { metrics }` in the global options block and add a dedicated `:{{ caddy_metrics_port }}` site block with `metrics /metrics` (conditional on `caddy_metrics_enabled`). The admin API stays on localhost:2019 (default) — not exposed externally. Add `monitoring_contract` with scrape targets for both node_exporter (9100) and Caddy metrics (9180), plus alert rules for high 5xx error rate. Include dashboard file reference.
- **Traces to**: FR-004, FR-006, FR-007, FR-015, US-3
- **Dependencies**: None
- **Parallel-safe**: Yes (with Step 3)

### Step 5: Enable Immich Telemetry and Add Monitoring Contract
- **Files**:
  - `ansible/roles/immich/defaults/main.yml` — MODIFY
  - `ansible/roles/immich/templates/.env.j2` — MODIFY
  - `ansible/roles/immich/templates/docker-compose.yml.j2` — MODIFY
- **Description**: Add `immich_metrics_enabled`, `immich_metrics_port` (8081), `immich_microservices_metrics_port` (8082) variables to immich defaults. Modify `.env.j2` to add `IMMICH_TELEMETRY_INCLUDE=all` (conditional on `immich_metrics_enabled`). Modify `docker-compose.yml.j2` to expose ports 8081 and 8082 on the immich-server container. Add `monitoring_contract` with scrape targets for node_exporter (9100), Immich API (8081), and Immich microservices (8082), plus alert rule for job backlog. Include dashboard file reference.
- **Traces to**: FR-005, FR-006, FR-007, FR-015, US-3
- **Dependencies**: None
- **Parallel-safe**: Yes (with Steps 3, 4)

### Step 6: Align Monitoring Stack Version Defaults
- **Files**:
  - `ansible/roles/monitoring_stack/defaults/main.yml` — MODIFY
- **Description**: Update the four version pins in `defaults/main.yml` to match `group_vars/monitoring/vars.yml`: `prometheus_version: "v3.8.1"`, `grafana_version: "12.3.1"`, `telegraf_version: "1.37.0"`, `alertmanager_version: "v0.30.0"`. Also update `grafana_domain` default from `"monitoring.local"` to align with group_vars pattern. Add new defaults for monitoring contract aggregation variables.
- **Traces to**: FR-026, US-5
- **Dependencies**: None
- **Parallel-safe**: Yes

### Step 7: Update Prometheus Configuration Template (Self-Registration)
- **Files**:
  - `ansible/roles/monitoring_stack/templates/prometheus.yml.j2` — MODIFY
- **Description**: Rewrite the scrape_configs section to: (1) preserve the existing `prometheus` self-monitoring and `telegraf-snmp` static targets, (2) add a `node-exporter` job that iterates over `groups['services']` using `hostvars` to generate static targets for all service LXCs, (3) iterate over all hosts' `monitoring_contract.scrape_targets` to generate application-level scrape configs. Update `rule_files` to load from `/etc/prometheus/alerts/` directory (glob) instead of a single file. This implements FR-003 and FR-008.
- **Traces to**: FR-003, FR-008, FR-027, US-4
- **Dependencies**: Steps 3, 4, 5 (contract schemas must be defined)
- **Parallel-safe**: No

### Step 8: Create Infrastructure Alert Rules
- **Files**:
  - `ansible/roles/monitoring_stack/files/prometheus/alerts/infrastructure_alerts.yml` — CREATE
- **Description**: Create a new alert rules file with: (1) `ServiceDown` — `up == 0` for 2m (FR-012), (2) `HighCPUUsage` — >85% for 10m (FR-013), (3) `HighMemoryUsage` — >85% for 5m (FR-013), (4) `DiskSpaceWarning` — >85% for 5m (FR-013), (5) `DiskSpaceCritical` — >95% for 2m (FR-013). All rules use `component` labels for inhibition targeting. PromQL expressions target node_exporter metric names.
- **Traces to**: FR-012, FR-013, US-1, US-2
- **Dependencies**: None
- **Parallel-safe**: Yes

### Step 9: Reorganize Existing Alert Rules
- **Files**:
  - `ansible/roles/monitoring_stack/files/prometheus/alerts.yml` — DELETE (moved)
  - `ansible/roles/monitoring_stack/files/prometheus/alerts/synology_alerts.yml` — CREATE (moved content)
- **Description**: Move the existing Synology alerts from `alerts.yml` to `alerts/synology_alerts.yml` to support the directory-based rule loading pattern. Content is preserved unchanged (FR-019). The `alerts/` subdirectory allows Prometheus to load all `.yml` files via a glob pattern.
- **Traces to**: FR-019, FR-027
- **Dependencies**: Step 7 (Prometheus config must reference new path)
- **Parallel-safe**: No (coordinated with Step 7)

### Step 10: Create Service-Specific Alert Rules Template
- **Files**:
  - `ansible/roles/monitoring_stack/templates/service_alerts.yml.j2` — CREATE
- **Description**: Create a Jinja2 template that iterates over all hosts' `monitoring_contract.alert_rules` and generates a Prometheus alert rules file. Each service's alert rules are rendered into a separate `group` within the file. The template validates that job_names and alert names are unique across contracts. This is deployed alongside the static infrastructure and Synology alert files.
- **Traces to**: FR-009, FR-015, US-4
- **Dependencies**: Steps 3, 4, 5 (contracts must define alert_rules)
- **Parallel-safe**: Yes (with Step 8)

### Step 11: Update Alertmanager Configuration (Inhibition Rules)
- **Files**:
  - `ansible/roles/monitoring_stack/templates/alertmanager.yml.j2` — MODIFY
- **Description**: Replace the existing `inhibit_rules` section with updated rules using `source_matchers`/`target_matchers` syntax (Alertmanager v0.30.0). Add four inhibition rules: (1) SynologyNASDown suppresses ServiceDown (FR-028), (2) SynologyNASDown suppresses Synology.* (existing, migrated syntax), (3) ServiceDown suppresses infrastructure threshold alerts (FR-029), (4) critical suppresses warning (severity hierarchy). See `contracts/alertmanager-config.yml` for exact specification.
- **Traces to**: FR-028, FR-029, US-2
- **Dependencies**: Step 8 (infrastructure alerts define the label schema)
- **Parallel-safe**: No

### Step 12: Create Infrastructure Overview Dashboard
- **Files**:
  - `ansible/roles/monitoring_stack/files/grafana/dashboards/infrastructure-overview.json` — CREATE
- **Description**: Create a Grafana dashboard JSON (Schema v1) showing CPU usage, memory usage, disk usage, and network throughput for all service containers. Use `timeseries` panel type (Grafana 12.x). Template variable for instance selection. Panels use node_exporter metric names: `node_cpu_seconds_total`, `node_memory_MemAvailable_bytes`, `node_filesystem_avail_bytes`, `node_network_receive_bytes_total`. 30s auto-refresh.
- **Traces to**: FR-016, US-1, SC-001
- **Dependencies**: None (JSON file, no runtime dependency)
- **Parallel-safe**: Yes

### Step 13: Create Caddy Reverse Proxy Dashboard
- **Files**:
  - `ansible/roles/reverse_proxy/files/grafana/dashboards/caddy-reverse-proxy.json` — CREATE
- **Description**: Create a Grafana dashboard JSON for Caddy metrics: HTTP request rate (`caddy_http_requests_total`), response time distribution (`caddy_http_request_duration_seconds`), error rate breakdown by status code, upstream health status (`caddy_reverse_proxy_upstreams_healthy`). 30s auto-refresh. File lives in the reverse_proxy role (service owns its dashboard per FR-010, SC-005). The monitoring_contract's `dashboard_file` references this path. The monitoring_stack role copies it at deploy time via `provision_dashboards.yml`.
- **Traces to**: FR-010, FR-017, US-3, SC-003, SC-005
- **Dependencies**: None
- **Parallel-safe**: Yes (with Step 12)

### Step 14: Create Immich Photo Service Dashboard
- **Files**:
  - `ansible/roles/immich/files/grafana/dashboards/immich-photo-service.json` — CREATE
- **Description**: Create a Grafana dashboard JSON for Immich metrics: API request rate, background job queue sizes (`immich_jobs_waiting`), processing throughput. Based on community dashboard ID 22555 patterns, adapted for Grafana 12.x. 30s auto-refresh. File lives in the immich role (service owns its dashboard per FR-010, SC-005). The monitoring_contract's `dashboard_file` references this path. The monitoring_stack role copies it at deploy time via `provision_dashboards.yml`.
- **Traces to**: FR-010, FR-018, US-3, SC-004, SC-005
- **Dependencies**: None
- **Parallel-safe**: Yes (with Steps 12, 13)

### Step 15: Create Dashboard Provisioning Task
- **Files**:
  - `ansible/roles/monitoring_stack/tasks/provision_dashboards.yml` — CREATE
- **Description**: Create a task file that iterates over all hosts' `monitoring_contract` variables via `hostvars`, finds contracts with `dashboard_file` defined, and copies each dashboard JSON from the service role's files directory (`{{ playbook_dir }}/../roles/<role>/files/...`) to the Grafana dashboards path on the monitoring host. This ensures the monitoring_stack role never references service names directly — it only follows contract references. The existing `synology-nas.json` and the new `infrastructure-overview.json` continue to be deployed from the monitoring_stack role (they are cross-service dashboards). This task is included from `grafana_provision.yml`.
- **Traces to**: FR-010, FR-011, US-4, SC-005
- **Dependencies**: Steps 4, 5, 13, 14 (contracts and dashboards must exist)
- **Parallel-safe**: No

### Step 16: Add Kuma Cleanup Tasks to Monitoring Stack
- **Files**:
  - `ansible/roles/monitoring_stack/tasks/kuma_cleanup.yml` — CREATE
  - `ansible/roles/monitoring_stack/tasks/main.yml` — MODIFY
- **Description**: Create a new task file that: (1) checks if `uptime-kuma` Docker container exists, (2) stops and removes it, (3) removes the Docker volume, (4) removes any Kuma data directory. Add `include_tasks: kuma_cleanup.yml` as the first task in `main.yml` (before Docker install). All tasks are idempotent — they check existence before acting.
- **Traces to**: FR-023, US-6
- **Dependencies**: None
- **Parallel-safe**: Yes

### Step 17: Add Alert Validation Task to Monitoring Stack
- **Files**:
  - `ansible/roles/monitoring_stack/tasks/validate_alerts.yml` — CREATE
  - `ansible/roles/monitoring_stack/tasks/main.yml` — MODIFY
- **Description**: Create a task that runs `promtool check rules` on all alert rule files before the monitoring stack is restarted. If any rule file has invalid syntax, the task fails with a clear error message identifying the file. This is added to `main.yml` after config deployment but before the compose stack restart.
- **Traces to**: FR-030, US-4 (edge case: invalid alert rule)
- **Dependencies**: Steps 8, 9, 10 (alert files must exist)
- **Parallel-safe**: No

### Step 18: Update Monitoring Stack Task Orchestration
- **Files**:
  - `ansible/roles/monitoring_stack/tasks/main.yml` — MODIFY
  - `ansible/roles/monitoring_stack/tasks/compose_stack.yml` — MODIFY
  - `ansible/roles/monitoring_stack/tasks/create_directories.yml` — MODIFY
- **Description**: Update the task orchestration in `main.yml` to: (1) include `kuma_cleanup.yml` first, (2) create the `alerts/` subdirectory in `create_directories.yml`, (3) deploy alert rule files and service alert template in `compose_stack.yml`, (4) include `validate_alerts.yml` before stack restart, (5) include `provision_dashboards.yml` in `grafana_provision.yml`. Update `compose_stack.yml` to copy all alert files to the Prometheus config directory and template the service alerts file.
- **Traces to**: FR-031, FR-032
- **Dependencies**: Steps 8, 9, 10, 15, 16, 17
- **Parallel-safe**: No

### Step 19: Update Monitoring Stack Service Description
- **Files**:
  - `ansible/roles/monitoring_stack/templates/monitoring-stack.service.j2` — MODIFY
- **Description**: Remove `(Uptime Kuma)` from the `Description=` line in the systemd service file.
- **Traces to**: FR-020, US-6
- **Dependencies**: None
- **Parallel-safe**: Yes

### Step 20: Delete Uptime Kuma Role
- **Files**:
  - `ansible/roles/uptime_kuma/` — DELETE entire directory (12 files)
- **Description**: Remove the entire Uptime Kuma Ansible role directory from the repository. This includes defaults, tasks, templates, and the JavaScript configuration script. The monitoring playbook does not reference this role (confirmed by inspection), so deletion has no playbook impact.
- **Traces to**: FR-020, US-6
- **Dependencies**: Step 16 (Kuma container already cleaned up on host)
- **Parallel-safe**: Yes

### Step 21: Remove Kuma Variables from Host Vars
- **Files**:
  - `ansible/host_vars/monitoring/vars.yml` — MODIFY
  - `ansible/host_vars/monitoring/vault.yml.example` — MODIFY
- **Description**: Remove from `vars.yml`: the `monitoring_targets` list, `uptime_kuma_api_url`, `uptime_kuma_api_wait_timeout`, `uptime_kuma_api_retry_delay`, `uptime_kuma_api_max_retries`. Preserve the `alert_down_threshold` and `healthcheck_url` sections. Remove from `vault.yml.example`: `uptime_kuma_admin_user` and `uptime_kuma_admin_password` lines and their comment header.
- **Traces to**: FR-021, FR-022, US-6
- **Dependencies**: Step 20 (role that used these vars is deleted)
- **Parallel-safe**: Yes (with Step 20)

### Step 22: Clean Up proxmox_backup Role's Kuma Integration
- **Files**:
  - `ansible/roles/proxmox_backup/tasks/configure_kuma.yml` — DELETE
  - `ansible/roles/proxmox_backup/tasks/main.yml` — MODIFY
  - `ansible/roles/proxmox_backup/defaults/main.yml` — MODIFY
  - `ansible/roles/proxmox_backup/templates/proxmox-backup.conf.j2` — MODIFY
  - `ansible/roles/proxmox_backup/templates/proxmox-config-backup.sh.j2` — MODIFY
- **Description**: Delete `configure_kuma.yml`. From `tasks/main.yml`: remove the `kuma_only` include block and update the email disable condition from `proxmox_backup_email_mode in ['kuma_only', 'disabled']` to `proxmox_backup_email_mode == 'disabled'`; remove the `kuma` tag. From `defaults/main.yml`: change default `proxmox_backup_email_mode` from `"kuma_only"` to `"disabled"`, remove `proxmox_backup_kuma_push_url`, update mode documentation comment to remove `kuma_only`. From `proxmox-backup.conf.j2`: remove `KUMA_URL` line. From `proxmox-config-backup.sh.j2`: remove `send_kuma_notification` function and its two call sites.
- **Traces to**: FR-024, US-6
- **Dependencies**: None (code path is already dead — group_vars set mode to "disabled")
- **Parallel-safe**: Yes

### Step 23: Remove Kuma References from Group Vars
- **Files**:
  - `ansible/group_vars/proxmox_hosts/vars.yml` — MODIFY
- **Description**: Remove the commented-out `proxmox_backup_kuma_url` line and its comment header from `group_vars/proxmox_hosts/vars.yml`.
- **Traces to**: FR-024, US-6
- **Dependencies**: None
- **Parallel-safe**: Yes (with Step 22)

### Step 24: Update Operational Documentation (Kuma Cleanup)
- **Files**:
  - `docs/operations.md` — MODIFY
  - `docs/operations/backups-proxmox-config.md` — MODIFY
  - `docs/operations/backups-proxmox-config-email-decommission.md` — MODIFY
  - `docs/architecture.md` — MODIFY
- **Description**: Update `docs/operations.md`: Replace the "Email Decommissioning & Kuma Migration" section to reflect that Kuma is decommissioned and monitoring uses Prometheus/Alertmanager. Update `docs/operations/backups-proxmox-config.md`: Remove the "Uptime Kuma (Primary)" monitoring subsection and KUMA_URL configuration. Update `docs/operations/backups-proxmox-config-email-decommission.md`: Remove the `kuma_only` state from the state machine table and all Kuma-related transitions and procedures. Update `docs/architecture.md`: Remove the "Target: Uptime Kuma Push notifications" line from the monitoring section.
- **Traces to**: FR-025, US-6
- **Dependencies**: Steps 20–23 (code changes complete before doc updates)
- **Parallel-safe**: No (docs should reflect final code state)

### Step 25: Lint and Validate All Changes
- **Files**: (validation only, no file modifications)
- **Description**: Run `ansible-lint` on all modified roles and playbooks. Run `yamllint` on all new/modified YAML files. Validate Prometheus config with `promtool check config` on the generated prometheus.yml. Validate alert rules with `promtool check rules` on all alert files. Run `ansible-playbook --check playbooks/monitoring.yml` for dry-run validation.
- **Traces to**: FR-030, FR-031, FR-032, US-5
- **Dependencies**: All previous steps
- **Parallel-safe**: No (must run after all changes)

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| node_exporter binary not available for architecture | Deployment fails on affected LXC | Pin exact version + architecture in role defaults. Download URL is deterministic. Verified: v1.10.2 has linux-amd64 release. |
| Caddy metrics port reachable from LAN | Low: port 9180 serves only /metrics, no admin capabilities | Dedicated metrics-only site block (`:9180 { metrics /metrics }`). Admin API stays on localhost:2019 (default, unreachable externally). No config reload or management exposed. |
| Immich metrics ports conflict with existing services | Deployment fails, Immich unavailable | Ports 8081/8082 are unoccupied on the Immich LXC (only 2283 in use). Verified: no existing services on these ports. |
| Self-registration template generates invalid Prometheus config | Monitoring stack fails to start | Step 16 adds `promtool check config` validation before stack restart. Invalid config fails the playbook before activation. |
| Uptime Kuma container removal on live system | Brief monitoring gap during cleanup | Kuma was already not authoritative (A-010: not in monitoring playbook). Cleanup runs before new stack deployment. Gap is expected and documented. |
| Alertmanager inhibition rules suppress legitimate alerts | Missed notifications | Inhibition rules use exact label matching (`equal: [instance]`). Tested against specific scenarios in contracts/alertmanager-config.yml. Rules follow established pattern from existing Synology inhibition. |
| Historical Prometheus data compatibility with config changes | Queries return unexpected results | Prometheus 3.x is backward-compatible with existing TSDB data. New targets simply add new time series. No existing series are modified. |

## Testing Strategy

### Static Validation (pre-deployment)
- **ansible-lint**: All new/modified roles pass with zero errors
- **yamllint**: All new/modified YAML files pass
- **promtool check config**: Generated prometheus.yml validates
- **promtool check rules**: All alert rule files validate
- **Where**: Locally and in CI pipeline

### Dry-Run Validation
- **ansible-playbook --check**: Monitoring playbook in check mode reports expected changes only
- **Where**: Locally against inventory

### Integration Verification (post-deployment)
- **Prometheus targets**: `http://192.168.1.214:9090/targets` — all targets show "UP" (SC-001, SC-002)
- **Grafana dashboards**: All 4 dashboards render without errors (SC-001, SC-003, SC-004, SC-008)
- **Alert status**: `http://192.168.1.214:9093` — zero active alerts when all healthy (SC-002)
- **Idempotency**: Second playbook run shows zero changes (SC-009)
- **Where**: On live monitoring stack after deployment

### Kuma Decommission Verification
- `docker ps | grep kuma` returns nothing on monitoring LXC (SC-006)
- `grep -r "kuma\|uptime_kuma" ansible/` returns zero hits in active code (SC-006)
- `ansible-playbook playbooks/monitoring.yml` succeeds with no Kuma errors (SC-006)
- `ansible-playbook playbooks/backup_proxmox.yml` succeeds with no Kuma errors (SC-006)

### Self-Registration Verification
- `grep -r "caddy\|immich" ansible/roles/monitoring_stack/` returns zero hits — service names never appear in monitoring role (SC-005)
- Add a mock monitoring contract to a test host → re-deploy → verify new target appears (SC-005, US-4)

### Coverage Target
- 100% of acceptance criteria from all 6 user stories are mechanically verifiable
- 100% of alert rules validated by `promtool check rules`
- 100% of Prometheus config validated by `promtool check config`

## Complexity Tracking

No constitution violations to justify. All principles PASS.

## Plan Amendment (Implementation Phase)

### Step 4 — Caddy Metrics Approach

**Original plan**: Expose Caddy admin API on `0.0.0.0:2019` via `caddy_admin_listen` and enable
metrics via `servers { metrics }` in global options.

**As-built**: The admin API remains on `localhost:2019` (default, unreachable externally).
A dedicated site block `:{caddy_metrics_port}` with `metrics /metrics` is added instead.
This is more secure: no admin capabilities are exposed, only the `/metrics` endpoint on port 9180.

**Rationale**: Exposing the admin API on all interfaces creates an unnecessary attack surface.
The dedicated site approach achieves the same Prometheus scraping goal with zero admin exposure.
