# Tasks: Monitoring & Observability Overhaul

**Input**: Design documents from `specs/040-monitoring-overhaul/`
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/ ✓, quickstart.md ✓

**Tests**: Not requested — validation uses `promtool`, `ansible-lint`, `yamllint`, and `--check` mode (Phase 9).

**Organization**: Phases 1–2 are setup/foundational; Phases 3–8 follow user story priority order (US1/US2/US3 as P1, then US4/US5/US6 as P2); Phase 9 is polish and static validation.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no blocking dependencies)
- **[Story]**: Which user story this task belongs to (US1–US6 map to spec user stories)
- Exact file paths are in each task description

---

## Phase 1: Setup — node_exporter Ansible Role

**Purpose**: Create the new `node_exporter` role structure. All four files are independent and can be authored in parallel. This role is the prerequisite for every user story that depends on infrastructure metrics.

**Plan step**: Step 1

- [X] T001 [P] Create `ansible/roles/node_exporter/defaults/main.yml` — define `node_exporter_version: "1.10.2"`, `node_exporter_port: 9100`, `node_exporter_user: "node_exporter"`, `node_exporter_enabled: true`, and `node_exporter_disabled_collectors` list (hwmon, thermal_zone, powersupplyclass, nvme, mdadm, infiniband, fibrechannel, wifi) per research.md R-02
- [X] T002 [P] Create `ansible/roles/node_exporter/tasks/main.yml` — tasks to download node_exporter binary (idempotent: skip if correct version already installed), create system user `node_exporter`, install binary to `/usr/local/bin/`, template the systemd unit, enable and start service; include filesystem mount-point exclusion flag `--collector.filesystem.mount-points-exclude`
- [X] T003 [P] Create `ansible/roles/node_exporter/templates/node_exporter.service.j2` — systemd unit file that starts node_exporter with `--web.listen-address=:{{ node_exporter_port }}` and all `--no-collector.<name>` flags from `node_exporter_disabled_collectors`; runs as `node_exporter` system user
- [X] T004 [P] Create `ansible/roles/node_exporter/handlers/main.yml` — single handler `Restart node_exporter` that executes `systemctl restart node_exporter`

**Checkpoint**: Role files exist. `ansible-lint ansible/roles/node_exporter/` returns zero errors.

---

## Phase 2: Foundational — Blocking Prerequisites

**Purpose**: Changes that must be complete before any user story implementation can begin. Includes lxc_base integration (blocks US1 deployment), Synology alert reorganization (blocks new alert directory structure), and version alignment (blocks correct template authoring). Phase 3+ cannot start until this phase is complete.

**Plan steps**: Steps 2, 6, 9

- [X] T005 Modify `ansible/roles/lxc_base/tasks/main.yml` — append `include_role: name=node_exporter` with guard `when: node_exporter_enabled | default(true)` at the end of the task list; ensures every LXC running lxc_base automatically gets node_exporter deployed (plan DL-10)
- [X] T006 [P] Modify `ansible/roles/monitoring_stack/defaults/main.yml` — update four version pins to match `ansible/group_vars/monitoring/vars.yml`: `prometheus_version: "v3.8.1"`, `grafana_version: "12.3.1"`, `telegraf_version: "1.37.0"`, `alertmanager_version: "v0.30.0"`; add new defaults for monitoring contract aggregation (covers FR-026/US5 primary requirement)
- [X] T007 [P] Create `ansible/roles/monitoring_stack/files/prometheus/alerts/synology_alerts.yml` — copy content verbatim from existing `ansible/roles/monitoring_stack/files/prometheus/alerts.yml` (three Synology alert rules preserved per FR-019); the `alerts/` directory is created by this file's existence in git
- [X] T008 Delete `ansible/roles/monitoring_stack/files/prometheus/alerts.yml` — remove old flat-file location now that content has moved to `alerts/synology_alerts.yml`; depends on T007 being complete

**Checkpoint**: `ls ansible/roles/monitoring_stack/files/prometheus/` shows `alerts/` directory only; `alerts/synology_alerts.yml` contains the original three Synology rules; `alerts.yml` no longer exists.

---

## Phase 3: User Story 1 — Infrastructure Health Baseline (Priority: P1) 🎯 MVP

**Goal**: Every service container exposes CPU/memory/disk/network metrics via node_exporter; Prometheus scrapes all 7 containers using a group-based job; infrastructure alert rules fire for resource exhaustion; infrastructure overview dashboard shows all containers in one view.

**Independent Test**: After deploying all service playbooks and the monitoring playbook, open `http://192.168.1.214:9090/targets` and confirm the `node-exporter` job shows 7 targets all reporting UP. Open Grafana and verify the Infrastructure Overview dashboard shows live data for all 7 containers (SC-001).

**Plan steps**: Steps 7, 8, 12, 18 (partial — directories and alert file deployment)

- [X] T009 [US1] Modify `ansible/roles/monitoring_stack/templates/prometheus.yml.j2` — (1) update `rule_files` section to load from `alerts/*.yml` glob instead of single `alerts.yml`; (2) add `node-exporter` scrape job iterating over `groups['services']` via hostvars to generate static targets (all service IPs on port 9100, adds `instance` label = inventory hostname); (3) add application-level scrape jobs by iterating over all hosts' `hostvars[host].monitoring_contract.scrape_targets` when `monitoring_contract.enabled` is true; preserve existing `prometheus` self-monitor and `telegraf-snmp` static targets unchanged
- [X] T010 [P] [US1] Create `ansible/roles/monitoring_stack/files/prometheus/alerts/infrastructure_alerts.yml` — alert rules group `infrastructure_alerts` with evaluation interval 30s, containing five rules: `ServiceDown` (up==0 for 2m, severity=critical, component=availability), `HighCPUUsage` (>85% for 10m, severity=warning, component=infrastructure), `HighMemoryUsage` (>85% for 5m, severity=warning, component=infrastructure), `DiskSpaceWarning` (>85% for 5m, severity=warning, component=infrastructure), `DiskSpaceCritical` (>95% for 2m, severity=critical, component=infrastructure) — use exact PromQL expressions from `contracts/alert-rules.yml`
- [X] T011 [P] [US1] Create `ansible/roles/monitoring_stack/files/grafana/dashboards/infrastructure-overview.json` — download community dashboard "Node Exporter Full" (Grafana Labs ID 1860, latest revision) via `curl -o dashboard.json https://grafana.com/api/dashboards/1860/revisions/latest/download`; customize: set UID to `infra-overview`, title to "Infrastructure Overview", replace hardcoded datasource UIDs with `${DS_PROMETHEUS}`, replace any deprecated `graph` panels with `timeseries` for Grafana 12.x compatibility, set auto-refresh 30s; the community dashboard covers CPU, memory, disk, network and more — strip unused panels if needed to keep the dashboard focused on the 7-LXC overview
- [X] T012 [P] [US1] Modify `ansible/roles/monitoring_stack/tasks/create_directories.yml` — add task to create `{{ prometheus_config_path }}/alerts/` directory with the same owner/mode as sibling directories; this directory receives the deployed alert rule files at play time

**Checkpoint**: `promtool check config` on rendered prometheus.yml passes; `promtool check rules` on `infrastructure_alerts.yml` and `synology_alerts.yml` both pass; infrastructure overview dashboard JSON validates against Grafana schema.

---

## Phase 4: User Story 2 — Unified Service Availability Alerting (Priority: P1)

**Goal**: Alertmanager uses updated inhibition rules that prevent duplicate alerts: SynologyNASDown suppresses generic ServiceDown for the same Synology target; agent-down suppresses infrastructure threshold alerts for that container; critical severity suppresses warning for same alertname+instance. The `ServiceDown` rule (created in T010) replaces all Uptime Kuma HTTP checks.

**Independent Test**: Stop a monitored service; verify exactly one alert email is received within 5 minutes (SC-002). Confirm the email identifies service name and endpoint. Restart the service; verify a recovery email arrives within 2 minutes. Confirm no duplicate alerts when Telegraf SNMP target goes down (SC-011).

**Plan step**: Step 11

- [X] T013 [US2] Modify `ansible/roles/monitoring_stack/templates/alertmanager.yml.j2` — replace existing `inhibit_rules` block with four rules using Alertmanager v0.30.0 `source_matchers`/`target_matchers` syntax (NOT deprecated `source_match`/`target_match`): (1) `alertname="SynologyNASDown"` → suppresses `alertname="ServiceDown"` on matching `instance`; (2) `alertname="SynologyNASDown"` → suppresses `alertname=~"Synology.*"` on matching `instance` (migrated from existing rule); (3) `alertname="ServiceDown", component="availability"` → suppresses `component="infrastructure"` on matching `instance`; (4) `severity="critical"` → suppresses `severity="warning"` on matching `alertname` + `instance` — exact specification in `contracts/alertmanager-config.yml`

**Checkpoint**: `amtool check-config` on rendered alertmanager.yml passes. `grep "source_match:" ansible/roles/monitoring_stack/templates/alertmanager.yml.j2` returns zero matches (no deprecated syntax).

---

## Phase 5: User Story 3 — Application-Level Service Metrics (Priority: P1)

**Goal**: Caddy exposes Prometheus metrics on port 2019 (LAN-only); Immich exposes API and microservices metrics on ports 8081/8082; both have monitoring_contracts with service-specific alert rules (CaddyHighErrorRate, ImmichJobBacklogHigh); dedicated dashboards provisioned per service; service_alerts.yml.j2 aggregates per-service alert rules from all contracts.

**Independent Test**: Generate HTTP traffic through the reverse proxy; verify `curl http://192.168.1.211:2019/metrics` returns caddy_http_requests_total. Upload photos to Immich; verify `curl http://192.168.1.213:8081/metrics` returns immich_jobs_waiting. Open Caddy and Immich Grafana dashboards and confirm live data (SC-003, SC-004).

**Plan steps**: Steps 4, 5, 10, 13, 14

- [X] T014 [P] [US3] Modify `ansible/roles/reverse_proxy/defaults/main.yml` — add: `caddy_metrics_enabled: true`, `caddy_metrics_port: 9180`; add full `monitoring_contract` dict with `enabled: true`, one scrape target `{job_name: "caddy", port: 9180, path: "/metrics", scrape_interval: "30s"}`, one alert rule `CaddyHighErrorRate` (PromQL from `contracts/alert-rules.yml`), `dashboard_file: "grafana/dashboards/caddy-reverse-proxy.json"`
- [X] T015 [P] [US3] Modify `ansible/roles/reverse_proxy/templates/Caddyfile.j2` — in the global options block, conditionally add (when `caddy_metrics_enabled`) `servers { metrics }` inside the existing block; after the global block and before the `import` directive, add a dedicated metrics site block `:{{ caddy_metrics_port }} { metrics /metrics }` (conditional on `caddy_metrics_enabled`); the admin API stays on `localhost:2019` (default, not exposed externally); must not interfere with existing `acme_dns` or `log` directives
- [X] T016 [P] [US3] Create `ansible/roles/reverse_proxy/files/grafana/dashboards/caddy-reverse-proxy.json` — hand-author a minimal Grafana Schema v1 JSON dashboard (no community dashboard exists for Caddy) with UID `caddy-proxy`, title "Reverse Proxy (Caddy)", auto-refresh 30s; four `timeseries` panels: HTTP request rate (`rate(caddy_http_requests_total[5m])`), response time P95 (`histogram_quantile(0.95, rate(caddy_http_request_duration_seconds_bucket[5m]))`), error rate by status code (4xx/5xx breakdown), and upstream health (`caddy_reverse_proxy_upstreams_healthy` as stat panel); Grafana 12.x schema only
- [X] T017 [P] [US3] Modify `ansible/roles/immich/defaults/main.yml` — add: `immich_metrics_enabled: true`, `immich_metrics_port: 8081`, `immich_microservices_metrics_port: 8082`; add full `monitoring_contract` dict with `enabled: true`, two scrape targets `{job_name: "immich-api", port: 8081, ...}` and `{job_name: "immich-microservices", port: 8082, ...}`, one alert rule `ImmichJobBacklogHigh` (PromQL from `contracts/alert-rules.yml`), `dashboard_file: "grafana/dashboards/immich-photo-service.json"`
- [X] T018 [P] [US3] Modify `ansible/roles/immich/templates/.env.j2` — add `IMMICH_TELEMETRY_INCLUDE=all` line conditional on `immich_metrics_enabled | default(false)`; place in the application configuration section after existing environment variables
- [X] T019 [P] [US3] Modify `ansible/roles/immich/templates/docker-compose.yml.j2` — on the `immich-server` service, add port mappings `"{{ immich_metrics_port }}:8081"` and `"{{ immich_microservices_metrics_port }}:8082"` conditional on `immich_metrics_enabled | default(false)`; these ports are not exposed via the public-facing reverse proxy (FR-006)
- [X] T020 [P] [US3] Create `ansible/roles/immich/files/grafana/dashboards/immich-photo-service.json` — download community dashboard "Immich Overview" (Grafana Labs ID 22555, latest revision) via `curl -o dashboard.json https://grafana.com/api/dashboards/22555/revisions/latest/download`; customize: set UID to `immich-photos`, title to "Photo Service (Immich)", replace hardcoded datasource UIDs with `${DS_PROMETHEUS}`, replace any deprecated panel types with Grafana 12.x equivalents, set auto-refresh 30s
- [X] T021 [US3] Create `ansible/roles/monitoring_stack/templates/service_alerts.yml.j2` — Jinja2 template that iterates over `groups['all']` inventory hosts via `hostvars`, collects hosts where `hostvars[host].monitoring_contract.enabled | default(false)` is true and `hostvars[host].monitoring_contract.alert_rules | default([])` is non-empty, and renders each service's alert rules into a separate named `groups` entry; output is a valid Prometheus alert rules YAML file; template must handle empty/missing contracts gracefully (no alert_rules → no group emitted for that host)

**Checkpoint**: `curl http://192.168.1.211:9180/metrics` returns `caddy_http_requests_total` after Caddy deployment. `curl http://192.168.1.213:8081/metrics` returns Immich metrics after Immich deployment. `promtool check rules` on a rendered service_alerts.yml passes. `grep -r "caddy\|immich" ansible/roles/monitoring_stack/` returns zero hits (SC-005 — monitoring role has no service-name awareness).

---

## Phase 6: User Story 4 — Extensible Monitoring Onboarding (Priority: P2)

**Goal**: Every service role declares a `monitoring_contract` variable in its defaults; monitoring_stack aggregates all contracts without any service-specific knowledge; dashboard provisioning copies service-owned dashboards automatically; alert validation runs before stack restart to fail-fast on syntax errors; compose_stack.yml deploys all alert files.

**Independent Test**: After adding a mock `monitoring_contract` to a service role's defaults and re-running the monitoring playbook, the new scrape target appears in `http://192.168.1.214:9090/targets` and any declared dashboard is accessible in Grafana — with zero edits to any file in `ansible/roles/monitoring_stack/` (SC-005, US-4 AC-4).

**Plan steps**: Steps 3, 15, 17, 18 (compose_stack.yml and grafana_provision.yml)

- [X] T022 [P] [US4] Modify `ansible/roles/jellyfin/defaults/main.yml` — add `monitoring_contract` variable: `enabled: true`, `scrape_targets: []` (no native application metrics for Jellyfin in this iteration), `alert_rules: []`, `dashboard_file: null`; jellyfin's infrastructure metrics are covered by the group-based node-exporter job in prometheus.yml.j2 (T009), not a per-service scrape target
- [X] T023 [P] [US4] Modify `ansible/roles/nextcloud/defaults/main.yml` — add `monitoring_contract` variable: `enabled: true`, `scrape_targets: []`, `alert_rules: []`, `dashboard_file: null`; same rationale as T022 for Nextcloud
- [X] T024 [US4] Create `ansible/roles/monitoring_stack/tasks/provision_dashboards.yml` — Ansible task file that iterates over `groups['all']` hosts via `hostvars`, finds contracts where `monitoring_contract.dashboard_file` is defined and non-null, and copies each dashboard JSON from `{{ playbook_dir }}/../roles/<role>/files/<dashboard_file>` to the Grafana dashboards directory on the monitoring host; must never reference any service name directly (role path comes from the contract's host association via hostvars lookup); the monitoring_stack's own dashboards (synology-nas.json, infrastructure-overview.json) are deployed by a sibling task in compose_stack.yml, not this file
- [X] T025 [P] [US4] Create `ansible/roles/monitoring_stack/tasks/validate_alerts.yml` — Ansible task file that runs `promtool check rules {{ prometheus_config_path }}/alerts/*.yml` using `command` module; fails with error message identifying the specific failing file if any rule has invalid syntax (FR-030); this task runs after all alert files are deployed to the host but before the Compose stack is restarted
- [X] T026 [US4] Modify `ansible/roles/monitoring_stack/tasks/grafana_provision.yml` — add `include_tasks: provision_dashboards.yml` call after the existing dashboard copy tasks; this wires service-owned dashboards into the Grafana provisioning flow
- [X] T027 [US4] Modify `ansible/roles/monitoring_stack/tasks/compose_stack.yml` — add tasks to: (1) copy `infrastructure_alerts.yml` to `{{ prometheus_config_path }}/alerts/infrastructure_alerts.yml`; (2) copy `synology_alerts.yml` to `{{ prometheus_config_path }}/alerts/synology_alerts.yml`; (3) template `service_alerts.yml.j2` to `{{ prometheus_config_path }}/alerts/service_alerts.yml`; these run before the Compose stack is started/restarted

**Checkpoint**: `grep -r "caddy\|immich\|jellyfin\|nextcloud" ansible/roles/monitoring_stack/` returns zero hits (SC-005). Mock monitoring_contract added to a service role → monitoring playbook re-run → new target appears in Prometheus targets page without modifying any monitoring_stack file (US-4 AC-4).

---

## Phase 7: User Story 5 — Monitoring Stack Version Alignment (Priority: P2)

**Goal**: The monitoring_stack role defaults file version pins match the already-deployed versions in group_vars; new configuration templates use Prometheus 3.x and Alertmanager v0.30.0 syntax.

**Note**: The primary code change for this user story is **T006** in Phase 2 (foundational prerequisite). T006 must complete before any Phase 3+ templates are authored. The task below is a mechanically verifiable confirmation step that FR-026 is satisfied.

**Independent Test**: `grep "prometheus_version\|grafana_version\|telegraf_version\|alertmanager_version" ansible/roles/monitoring_stack/defaults/main.yml` shows v3.8.1, 12.3.1, 1.37.0, v0.30.0 respectively — matching group_vars values (SC-007).

**Plan step**: Step 6

- [X] T028 [US5] Verify `ansible/roles/monitoring_stack/defaults/main.yml` version pins and syntax compliance: run `grep -E "prometheus_version|grafana_version|telegraf_version|alertmanager_version" ansible/roles/monitoring_stack/defaults/main.yml` and confirm outputs are `v3.8.1`, `12.3.1`, `1.37.0`, `v0.30.0`; run `grep "source_match:" ansible/roles/monitoring_stack/templates/alertmanager.yml.j2` and confirm output is empty (no deprecated syntax); this task is a static audit with no file modifications — it confirms T006 and T013 are correctly completed

**Checkpoint**: `grep "source_match:" ansible/roles/monitoring_stack/templates/alertmanager.yml.j2` returns empty. All four version variables in defaults/main.yml match group_vars/monitoring/vars.yml.

---

## Phase 8: User Story 6 — Uptime Kuma Decommission (Priority: P2)

**Goal**: Uptime Kuma container stopped and removed from monitoring LXC; entire uptime_kuma Ansible role directory deleted; all Kuma variables removed from host_vars, vault example, and group_vars; proxmox_backup role's dead kuma_only code path cleaned up; all operational documentation updated; monitoring_stack/tasks/main.yml wired with kuma_cleanup.yml (first) and validate_alerts.yml (before restart).

**Independent Test**: After deployment: `docker ps` on monitoring LXC shows no uptime-kuma container; `find ansible/ -name "*.yml" -o -name "*.j2" | xargs grep -li "kuma"` returns zero hits in active code files; `ansible-playbook playbooks/monitoring.yml` succeeds with no Kuma errors; `ansible-playbook playbooks/backup_proxmox.yml` succeeds with no Kuma errors (SC-006).

**Plan steps**: Steps 16, 19, 20, 21, 22, 23, 24

- [X] T029 [P] [US6] Create `ansible/roles/monitoring_stack/tasks/kuma_cleanup.yml` — idempotent task file that: (1) checks if Docker container named `uptime-kuma` exists; (2) stops and removes it if present (`docker rm -f uptime-kuma`); (3) removes the Docker volume `uptime-kuma_data` if present; (4) removes any residual Kuma config directory; all tasks use `failed_when: false` or `ignore_errors: true` to be idempotent when Kuma is already absent (FR-023)
- [X] T030 [P] [US6] Modify `ansible/roles/monitoring_stack/templates/monitoring-stack.service.j2` — remove `(Uptime Kuma)` from the `Description=` line; no other changes to this file
- [X] T031 [P] [US6] Delete `ansible/roles/uptime_kuma/` — remove the entire directory including all subdirectories and files (FR-020); the monitoring playbook does not reference this role (confirmed: `ansible/playbooks/monitoring.yml` roles are `lxc_base`, `mdns_base`, `monitoring_stack` only), so deletion has no playbook impact
- [X] T032 [P] [US6] Modify `ansible/host_vars/monitoring/vars.yml` — remove the following variables: `monitoring_targets` (list), `uptime_kuma_api_url`, `uptime_kuma_api_wait_timeout`, `uptime_kuma_api_retry_delay`, `uptime_kuma_api_max_retries`; preserve all other variables including `alert_down_threshold` and any healthcheck variables (FR-021)
- [X] T033 [P] [US6] Modify `ansible/host_vars/monitoring/vault.yml.example` — remove `uptime_kuma_admin_user` and `uptime_kuma_admin_password` lines and their comment header; preserve all other example vault entries (FR-022)
- [X] T034 [P] [US6] Delete `ansible/roles/proxmox_backup/tasks/configure_kuma.yml` — remove the file entirely (FR-024); this task file contains the dead Kuma push-monitor configuration code
- [X] T035 [US6] Modify `ansible/roles/proxmox_backup/tasks/main.yml` — remove the `kuma_only` conditional include block that references `configure_kuma.yml`; update the email-disable condition from `proxmox_backup_email_mode in ['kuma_only', 'disabled']` to `proxmox_backup_email_mode == 'disabled'`; remove the `kuma` tag from any task that has it; depends on T034 (configure_kuma.yml must be deleted first)
- [X] T036 [P] [US6] Modify `ansible/roles/proxmox_backup/defaults/main.yml` — change default value of `proxmox_backup_email_mode` from `"kuma_only"` to `"disabled"`; remove `proxmox_backup_kuma_push_url` variable; update the inline mode documentation comment to remove `kuma_only` from the list of valid options (FR-024)
- [X] T037 [P] [US6] Modify `ansible/roles/proxmox_backup/templates/proxmox-backup.conf.j2` — remove the `KUMA_URL` configuration line and its surrounding comment (FR-024)
- [X] T038 [P] [US6] Modify `ansible/roles/proxmox_backup/templates/proxmox-config-backup.sh.j2` — remove the `send_kuma_notification` shell function definition and its two call sites (success and failure paths); remove any `KUMA_URL` variable reference (FR-024)
- [X] T039 [P] [US6] Modify `ansible/group_vars/proxmox_hosts/vars.yml` — remove the commented-out `proxmox_backup_kuma_url` line and its preceding comment header; no other changes to this file (FR-024)
- [X] T040 [US6] Modify `ansible/roles/monitoring_stack/tasks/main.yml` — add `include_tasks: kuma_cleanup.yml` as the **first** include in the task file (before any Docker or stack tasks); add `include_tasks: validate_alerts.yml` immediately before the Compose stack restart task; this single modification completes orchestration wiring for both US6 (Kuma cleanup) and US4 (alert validation); depends on T029 (kuma_cleanup.yml must exist) and T025 (validate_alerts.yml must exist)
- [X] T041 [P] [US6] Modify `docs/operations.md` — remove or replace the "Email Decommissioning & Kuma Migration" section to reflect that Uptime Kuma is decommissioned and monitoring uses Prometheus/Alertmanager; correct the stale "Current Mode: kuma_only (Email disabled, Kuma active)" statement to reflect actual state (mode is `"disabled"` per group_vars) (FR-025, A-012)
- [X] T042 [P] [US6] Modify `docs/operations/backups-proxmox-config.md` — remove the "Uptime Kuma (Primary)" monitoring subsection and KUMA_URL configuration instructions; update any references to monitoring modes to reflect the current state (FR-025)
- [X] T043 [P] [US6] Modify `docs/operations/backups-proxmox-config-email-decommission.md` — remove the `kuma_only` state from the state machine table; remove all Kuma-related transition steps and procedures; the state machine now has only `disabled` and `enabled` email modes (FR-025)
- [X] T044 [P] [US6] Modify `docs/architecture.md` — remove the "Target: Uptime Kuma Push notifications" line from the monitoring section; update monitoring architecture description to reflect unified Prometheus/Alertmanager alerting (FR-025)

**Checkpoint**: `find ansible/ -name "*.yml" -o -name "*.j2" | xargs grep -li "kuma" 2>/dev/null` returns zero hits. `ls ansible/roles/uptime_kuma/` returns "No such file". `grep "kuma_only" ansible/roles/proxmox_backup/defaults/main.yml` returns empty.

---

## Phase 9: Polish & Static Validation

**Purpose**: Run all static analysis tools against modified files. Catch syntax errors, lint violations, and configuration incompatibilities before deployment. These checks are the CI gate.

**Plan step**: Step 25

- [X] T045 [P] Run `ansible-lint ansible/roles/node_exporter/ ansible/roles/lxc_base/ ansible/roles/monitoring_stack/ ansible/roles/reverse_proxy/ ansible/roles/immich/ ansible/roles/jellyfin/ ansible/roles/nextcloud/ ansible/roles/proxmox_backup/` — must return zero errors or warnings
- [X] T046 [P] Run `yamllint ansible/roles/node_exporter/ ansible/roles/monitoring_stack/ ansible/roles/reverse_proxy/defaults/ ansible/roles/immich/defaults/ ansible/roles/jellyfin/defaults/ ansible/roles/nextcloud/defaults/` — must return zero errors on all new/modified YAML files
- [X] T047 [P] Run `promtool check rules ansible/roles/monitoring_stack/files/prometheus/alerts/infrastructure_alerts.yml ansible/roles/monitoring_stack/files/prometheus/alerts/synology_alerts.yml` — must return "SUCCESS: N rules found, 0 errors" for each file
- [X] T048 [P] Render `ansible/roles/monitoring_stack/templates/prometheus.yml.j2` in dry-run (use `ansible --check` or a test inventory stub) and validate with `promtool check config` — must return "SUCCESS: prometheus.yml is valid"
- [X] T049 Run `ansible-playbook --check ansible/playbooks/monitoring.yml` against the inventory — must complete with zero failures and report only expected changes (not `kuma_only` task errors, not missing variable errors); idempotency confirmed by running twice and seeing "changed=0" on the second run (SC-009)

**Checkpoint**: All five validation commands return zero errors. Second `--check` run reports `changed=0`.

---

## File Manifest

### Files Created (new)

| File | Plan Step | Task |
|------|-----------|------|
| `ansible/roles/node_exporter/defaults/main.yml` | Step 1 | T001 |
| `ansible/roles/node_exporter/tasks/main.yml` | Step 1 | T002 |
| `ansible/roles/node_exporter/templates/node_exporter.service.j2` | Step 1 | T003 |
| `ansible/roles/node_exporter/handlers/main.yml` | Step 1 | T004 |
| `ansible/roles/monitoring_stack/files/prometheus/alerts/synology_alerts.yml` | Step 9 | T007 |
| `ansible/roles/monitoring_stack/files/prometheus/alerts/infrastructure_alerts.yml` | Step 8 | T010 |
| `ansible/roles/monitoring_stack/files/grafana/dashboards/infrastructure-overview.json` | Step 12 | T011 |
| `ansible/roles/monitoring_stack/templates/service_alerts.yml.j2` | Step 10 | T021 |
| `ansible/roles/monitoring_stack/tasks/provision_dashboards.yml` | Step 15 | T024 |
| `ansible/roles/monitoring_stack/tasks/validate_alerts.yml` | Step 17 | T025 |
| `ansible/roles/monitoring_stack/tasks/kuma_cleanup.yml` | Step 16 | T029 |
| `ansible/roles/reverse_proxy/files/grafana/dashboards/caddy-reverse-proxy.json` | Step 13 | T016 |
| `ansible/roles/immich/files/grafana/dashboards/immich-photo-service.json` | Step 14 | T020 |

### Files Modified (existing)

| File | Plan Step | Task |
|------|-----------|------|
| `ansible/roles/lxc_base/tasks/main.yml` | Step 2 | T005 |
| `ansible/roles/monitoring_stack/defaults/main.yml` | Step 6 | T006 |
| `ansible/roles/monitoring_stack/templates/prometheus.yml.j2` | Step 7 | T009 |
| `ansible/roles/monitoring_stack/tasks/create_directories.yml` | Step 18 | T012 |
| `ansible/roles/monitoring_stack/templates/alertmanager.yml.j2` | Step 11 | T013 |
| `ansible/roles/monitoring_stack/tasks/grafana_provision.yml` | Step 18 | T026 |
| `ansible/roles/monitoring_stack/tasks/compose_stack.yml` | Step 18 | T027 |
| `ansible/roles/monitoring_stack/tasks/main.yml` | Steps 16, 17, 18 | T040 |
| `ansible/roles/monitoring_stack/templates/monitoring-stack.service.j2` | Step 19 | T030 |
| `ansible/roles/reverse_proxy/defaults/main.yml` | Step 4 | T014 |
| `ansible/roles/reverse_proxy/templates/Caddyfile.j2` | Step 4 | T015 |
| `ansible/roles/immich/defaults/main.yml` | Step 5 | T017 |
| `ansible/roles/immich/templates/.env.j2` | Step 5 | T018 |
| `ansible/roles/immich/templates/docker-compose.yml.j2` | Step 5 | T019 |
| `ansible/roles/jellyfin/defaults/main.yml` | Step 3 | T022 |
| `ansible/roles/nextcloud/defaults/main.yml` | Step 3 | T023 |
| `ansible/roles/proxmox_backup/tasks/main.yml` | Step 22 | T035 |
| `ansible/roles/proxmox_backup/defaults/main.yml` | Step 22 | T036 |
| `ansible/roles/proxmox_backup/templates/proxmox-backup.conf.j2` | Step 22 | T037 |
| `ansible/roles/proxmox_backup/templates/proxmox-config-backup.sh.j2` | Step 22 | T038 |
| `ansible/host_vars/monitoring/vars.yml` | Step 21 | T032 |
| `ansible/host_vars/monitoring/vault.yml.example` | Step 21 | T033 |
| `ansible/group_vars/proxmox_hosts/vars.yml` | Step 23 | T039 |
| `docs/operations.md` | Step 24 | T041 |
| `docs/operations/backups-proxmox-config.md` | Step 24 | T042 |
| `docs/operations/backups-proxmox-config-email-decommission.md` | Step 24 | T043 |
| `docs/architecture.md` | Step 24 | T044 |

### Files Deleted

| File | Plan Step | Task |
|------|-----------|------|
| `ansible/roles/monitoring_stack/files/prometheus/alerts.yml` | Step 9 | T008 |
| `ansible/roles/uptime_kuma/` (entire directory) | Step 20 | T031 |
| `ansible/roles/proxmox_backup/tasks/configure_kuma.yml` | Step 22 | T034 |

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1 (Setup)
  → Phase 2 (Foundational) [T005 depends on T001-T004]
    → Phase 3 (US1): T009 depends on T006, T007, T008
    → Phase 4 (US2): T013 depends on T010 (infrastructure alert label schema)
    → Phase 5 (US3): T021 depends on T014, T017 (contracts define alert schemas)
      → Phase 6 (US4): T024 depends on T016, T020 (dashboard files must exist); T027 depends on T007, T010, T021
        → Phase 7 (US5): T028 depends on T006 (Phase 2) and T013 (Phase 4)
        → Phase 8 (US6): T040 depends on T029 (Phase 8) and T025 (Phase 6)
          → Phase 9 (Polish): All validation tasks depend on all prior phases complete
```

### Critical Ordering Notes

- **T006 must complete before T009, T013**: Version alignment determines which Prometheus 3.x/Alertmanager v0.30.0 syntax to use
- **T007 before T008**: Synology alerts must be created at new path before old path is removed
- **T034 before T035**: `configure_kuma.yml` must be deleted before main.yml references to it are removed
- **T029 + T025 before T040**: Both kuma_cleanup.yml and validate_alerts.yml must exist before main.yml is updated to include them

### Intra-Phase Parallel Opportunities

**Phase 1** — All four tasks parallel: T001 ∥ T002 ∥ T003 ∥ T004

**Phase 2** — T006 ∥ T007 in parallel; T005 and T008 sequential (T008 after T007):
```
T006 ∥ T007 → T008
T005 (after T001-T004)
```

**Phase 3 (US1)** — T010 ∥ T011 ∥ T012 in parallel with T009:
```
T009 ∥ T010 ∥ T011 ∥ T012
```

**Phase 5 (US3)** — T014-T020 all parallel; T021 after T014 + T017:
```
T014 ∥ T015 ∥ T016 ∥ T017 ∥ T018 ∥ T019 ∥ T020 → T021
```

**Phase 6 (US4)** — T022 ∥ T023 ∥ T025 in parallel; T024 after Phase 5 complete; T026 after T024; T027 after T021:
```
T022 ∥ T023 ∥ T025
T024 → T026
T027 (after T021 from Phase 5)
```

**Phase 8 (US6)** — Most tasks parallel; T035 after T034; T040 after T029+T025:
```
T029 ∥ T030 ∥ T031 ∥ T032 ∥ T033 ∥ T034 ∥ T036 ∥ T037 ∥ T038 ∥ T039 ∥ T041 ∥ T042 ∥ T043 ∥ T044
T034 → T035
T029 + T025(Phase 6) → T040
```

**Phase 9 (Polish)** — T045 ∥ T046 ∥ T047 ∥ T048 in parallel; T049 after T047 + T048:
```
T045 ∥ T046 ∥ T047 ∥ T048 → T049
```

---

## Summary

- **Total tasks**: 49
- **Tasks by phase**: Phase 1: 4 · Phase 2: 4 · Phase 3: 4 · Phase 4: 1 · Phase 5: 8 · Phase 6: 6 · Phase 7: 1 · Phase 8: 16 · Phase 9: 5
- **Estimated complexity**: High (6 user stories, 3 new Ansible roles/task files, 2 service integrations, full Kuma decommission)
- **Parallel tracks**: 8 independent parallel tracks identified across phases
- **Files created**: 13 · **Files modified**: 27 · **Files deleted**: 3

### Independent Test Criteria per User Story

| Story | Independent Test | Key Command |
|-------|-----------------|-------------|
| US1 | All 7 containers in Prometheus targets as UP | `curl http://192.168.1.214:9090/api/v1/targets` |
| US2 | Stop service → email within 5 min; restart → recovery email | Manual + check Alertmanager UI |
| US3 | Caddy/Immich metrics endpoints return data | `curl http://192.168.1.211:9180/metrics` |
| US4 | Monitoring role has no caddy/immich name references | `grep -r "caddy\|immich" ansible/roles/monitoring_stack/` returns empty |
| US5 | Version pins in defaults match group_vars | `grep "_version" ansible/roles/monitoring_stack/defaults/main.yml` |
| US6 | No Kuma container, files, or code references remain | `find ansible/ -name "*.yml" \| xargs grep -li "kuma"` returns empty |

### MVP Scope

Complete Phases 1–4 (Tasks T001–T013) to deliver US1 + US2: infrastructure metrics for all 7 containers and unified service availability alerting. This replaces Uptime Kuma's core function and provides the observability foundation, without requiring application-level metrics or the Kuma decommission steps.

### Implementation Strategy

1. **Phase 1 → Phase 2**: Build node_exporter role, integrate into lxc_base, align versions, reorganize alert files — foundation complete
2. **Phase 3 (US1)**: Wire Prometheus config, create infrastructure alerts and overview dashboard — infrastructure metrics live
3. **Phase 4 (US2)**: Update Alertmanager inhibition rules — unified alerting complete (MVP deliverable)
4. **Phase 5 (US3)**: Enable Caddy/Immich metrics, create dashboards — application metrics live
5. **Phase 6 (US4)**: Complete extensibility wiring — zero-touch onboarding pattern complete
6. **Phases 7–8 (US5+US6)**: Version confirmation + full Kuma decommission
7. **Phase 9**: Static validation gate before deployment
