# Tasks: Monitoring & Observability Overhaul

**Input**: Design documents from `specs/040-monitoring-overhaul/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US-1, US-2, US-3)
- Include exact file paths in descriptions

## Inventory Note

The production inventory (`ansible/inventories/prod/hosts.yml`) currently contains 5 hosts in the
`services` group: `reverse_proxy`, `immich`, `monitoring`, `jellyfin`, `nextcloud`. AdGuard
(192.168.1.210) and Home Assistant (192.168.1.212) are listed in the spec's FR-001 but are not
yet in the production inventory. The extensible pattern ensures they will automatically receive
node_exporter and be scraped when added to the inventory in the future.

## Design Correction: Monitoring Contract Scrape Targets

The plan Steps 3, 4, and 5 state that monitoring contracts should include node_exporter as a
scrape target. This is **incorrect** — it would create duplicate scrape configs because the
Prometheus template (Step 7) already generates a dedicated `node-exporter` job by iterating
over `groups['services']`. The prometheus scrape config contract (`contracts/prometheus-scrape-config.yml`)
confirms this separation: the `node-exporter` job is group-based, and monitoring contracts
only declare application-level scrape targets (Caddy port 2019, Immich ports 8081/8082).

**Correction applied in these tasks:**
- Jellyfin/Nextcloud contracts: `scrape_targets: []` (empty — node_exporter handled by group)
- Reverse Proxy contract: only `caddy` job on port 2019 (no node_exporter target)
- Immich contract: only `immich-api` (8081) and `immich-microservices` (8082) (no node_exporter target)

---

## Phase 1: Foundational (Shared Infrastructure)

**Purpose**: Create the node_exporter role and integrate it into the base role that all LXCs use.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T001 [P] [US-1] Create node_exporter Ansible role
  - **Create**: `ansible/roles/node_exporter/defaults/main.yml`
    - Variables: `node_exporter_version: "1.10.2"`, `node_exporter_port: 9100`, `node_exporter_user: "node_exporter"`, `node_exporter_enabled: true`, `node_exporter_disabled_collectors` list (hwmon, thermal_zone, powersupplyclass, nvme, mdadm, infiniband, fibrechannel, wifi per research.md R-02), `node_exporter_textfile_dir`, `node_exporter_filesystem_mount_exclude` regex
  - **Create**: `ansible/roles/node_exporter/tasks/main.yml`
    - Tasks: check current version (skip if matching), create system user, download binary from `https://github.com/prometheus/node_exporter/releases/download/v{{ node_exporter_version }}/node_exporter-{{ node_exporter_version }}.linux-amd64.tar.gz`, extract to `/usr/local/bin/node_exporter`, deploy systemd unit from template, enable and start service. Guard all tasks with `when: node_exporter_enabled | default(true)`
  - **Create**: `ansible/roles/node_exporter/templates/node_exporter.service.j2`
    - Systemd unit: `User={{ node_exporter_user }}`, `ExecStart=/usr/local/bin/node_exporter` with `--web.listen-address=:{{ node_exporter_port }}` and `--no-collector.X` for each disabled collector, `--collector.filesystem.mount-points-exclude` regex
  - **Create**: `ansible/roles/node_exporter/handlers/main.yml`
    - Handler: `Restart node_exporter` → `ansible.builtin.systemd: name=node_exporter state=restarted daemon_reload=yes`
  - **Traces to**: FR-001, FR-002, A-005, C-004, DL-09, R-01, R-02
  - **Done-when**: `ansible-lint ansible/roles/node_exporter/` exits 0 AND all 4 files exist AND `grep 'node_exporter_version.*1.10.2' ansible/roles/node_exporter/defaults/main.yml` matches AND `grep 'no-collector' ansible/roles/node_exporter/templates/node_exporter.service.j2` matches

- [ ] T002 [US-1] Integrate node_exporter into lxc_base role
  - **Modify**: `ansible/roles/lxc_base/tasks/main.yml`
    - Append at end of file: `include_role: name=node_exporter` with `when: node_exporter_enabled | default(true)` and `tags: [node_exporter]`
  - **Traces to**: FR-001, FR-003, DL-10, R-09
  - **Dependencies**: T001
  - **Done-when**: `grep -A2 'include_role' ansible/roles/lxc_base/tasks/main.yml | grep 'node_exporter'` matches AND `ansible-lint ansible/roles/lxc_base/` exits 0

**Checkpoint**: node_exporter role exists and is wired into lxc_base. Running any service playbook will deploy node_exporter to that service's LXC.

---

## Phase 2: US-5 — Monitoring Stack Version Alignment (Priority: P2)

**Goal**: Eliminate the defaults/group_vars version mismatch so the codebase is internally consistent.

**Independent Test**: Compare version strings in `defaults/main.yml` against `group_vars/monitoring/vars.yml` — they must match for all 4 components.

- [ ] T003 [P] [US-5] Align monitoring_stack version defaults to match group_vars
  - **Modify**: `ansible/roles/monitoring_stack/defaults/main.yml`
    - Change `prometheus_version: "v2.48.0"` → `"v3.8.1"`
    - Change `grafana_version: "10.2.0"` → `"12.3.1"`
    - Change `telegraf_version: "1.28"` → `"1.37.0"`
    - Change `alertmanager_version: "v0.26.0"` → `"v0.30.0"`
  - **Traces to**: FR-026, SC-007
  - **Dependencies**: None
  - **Done-when**: `grep 'prometheus_version.*v3.8.1' ansible/roles/monitoring_stack/defaults/main.yml` matches AND `grep 'grafana_version.*12.3.1' ansible/roles/monitoring_stack/defaults/main.yml` matches AND `grep 'telegraf_version.*1.37.0' ansible/roles/monitoring_stack/defaults/main.yml` matches AND `grep 'alertmanager_version.*v0.30.0' ansible/roles/monitoring_stack/defaults/main.yml` matches

**Checkpoint**: Version defaults match group_vars. SC-007 satisfied.

---

## Phase 3: US-1 + US-4 — Infrastructure Health Baseline + Extensible Pattern Foundation (Priority: P1/P2)

**Goal**: Deploy infrastructure metrics collection for all service containers, create the self-registration pattern for scrape config generation, and provide an infrastructure overview dashboard.

**Independent Test**: After deployment, verify Prometheus targets page shows all service LXCs reporting node_exporter metrics.

### Alert Rules

- [ ] T005 [P] [US-1,US-2] Create infrastructure alert rules file
  - **Create**: `ansible/roles/monitoring_stack/files/prometheus/alerts/infrastructure_alerts.yml`
    - Group name: `infrastructure_alerts`, interval: `30s`
    - Rules per `contracts/alert-rules.yml`:
      - `ServiceDown`: `up == 0` for 2m, severity: critical, component: availability (FR-012)
      - `HighCPUUsage`: `100 - (avg by(instance)(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > 85` for 10m, severity: warning, component: infrastructure (FR-013)
      - `HighMemoryUsage`: `100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) > 85` for 5m, severity: warning, component: infrastructure (FR-013)
      - `DiskSpaceWarning`: `>85%` filesystem for 5m, severity: warning, component: infrastructure (FR-013)
      - `DiskSpaceCritical`: `>95%` filesystem for 2m, severity: critical, component: infrastructure (FR-013)
    - All rules must include `component` label for inhibition targeting (FR-028, FR-029)
  - **Traces to**: FR-012, FR-013, SC-010, DL-05
  - **Dependencies**: None
  - **Done-when**: File exists AND `yamllint ansible/roles/monitoring_stack/files/prometheus/alerts/infrastructure_alerts.yml` exits 0 AND file contains all 5 alert names (ServiceDown, HighCPUUsage, HighMemoryUsage, DiskSpaceWarning, DiskSpaceCritical)

- [ ] T006 [P] [US-1] Reorganize existing Synology alert rules into alerts/ subdirectory
  - **Create**: `ansible/roles/monitoring_stack/files/prometheus/alerts/synology_alerts.yml` — copy EXACT content from existing `alerts.yml` (3 rules: SynologyVolumeHighUsage, SynologyNASDown, SynologyDiskSMARTWarning)
  - **Delete**: `ansible/roles/monitoring_stack/files/prometheus/alerts.yml` (original file, after content is moved)
  - **Traces to**: FR-019, FR-027, SC-008
  - **Dependencies**: None
  - **Done-when**: `test -f ansible/roles/monitoring_stack/files/prometheus/alerts/synology_alerts.yml` exits 0 AND `test ! -f ansible/roles/monitoring_stack/files/prometheus/alerts.yml` exits 0 AND `diff <(sort alerts/synology_alerts.yml) <(sort alerts.yml.bak)` shows content preserved (verify content matches original before deleting)

### Prometheus Self-Registration

- [ ] T007 [US-1,US-4] Update Prometheus configuration template for self-registration
  - **Modify**: `ansible/roles/monitoring_stack/templates/prometheus.yml.j2`
    - Change `rule_files` from `['/etc/prometheus/alerts.yml']` to `['/etc/prometheus/alerts/*.yml']`
    - Preserve existing `prometheus` self-monitoring and `telegraf-snmp` static scrape configs unchanged
    - Add `node-exporter` job after existing configs: iterate `groups['services'] | default([])` to generate static targets with `{{ hostvars[host].ansible_host }}:{{ hostvars[host].node_exporter_port | default(9100) }}` and `instance: '{{ host }}'` label
    - Add application metrics section: iterate `groups['services'] | default([])`, for each host read `hostvars[host].monitoring_contract | default({})`, if `contract.enabled | default(false)`, iterate `contract.scrape_targets | default([])` to generate per-target scrape configs with job_name, port, path, scrape_interval, and instance label
    - Generated config must match the structure in `contracts/prometheus-scrape-config.yml`
  - **Traces to**: FR-003, FR-008, FR-027, SC-005
  - **Dependencies**: T011, T012 (contracts with actual scrape targets must be defined for template logic validation)
  - **Done-when**: Template contains `groups['services']` loop AND `monitoring_contract` loop AND preserves `job_name: 'prometheus'` and `job_name: 'telegraf-snmp'` AND `grep -c 'caddy\|immich\|jellyfin\|nextcloud\|adguard\|homeassistant' ansible/roles/monitoring_stack/templates/prometheus.yml.j2` returns 0 (no hardcoded service names — SC-005)

### Dashboard

- [ ] T008 [P] [US-1] Create infrastructure overview Grafana dashboard JSON
  - **Create**: `ansible/roles/monitoring_stack/files/grafana/dashboards/infrastructure-overview.json`
    - Grafana Schema v1 JSON, compatible with Grafana 12.x (FR-027)
    - Unique `uid` field (e.g., `"infrastructure-overview"`)
    - Template variable for instance selection (all hosts in services group)
    - Panels using `timeseries` panel type:
      - CPU usage: `100 - (avg by(instance)(rate(node_cpu_seconds_total{mode="idle"}[$__rate_interval])) * 100)`
      - Memory usage: `100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)`
      - Disk usage: `100 * (1 - node_filesystem_avail_bytes / node_filesystem_size_bytes)`
      - Network throughput: `rate(node_network_receive_bytes_total[$__rate_interval])` / transmit
    - Auto-refresh: 30s
    - Datasource: Prometheus (uid from provisioning)
  - **Traces to**: FR-016, FR-027, SC-001, NFR-003
  - **Dependencies**: None
  - **Done-when**: `python3 -c "import json; d=json.load(open('ansible/roles/monitoring_stack/files/grafana/dashboards/infrastructure-overview.json')); assert 'uid' in d; assert any('node_cpu' in str(p) for p in d.get('panels',[]))"` exits 0

**Checkpoint**: Infrastructure metrics scraping pattern defined. Alert rules created. Dashboard JSON ready. All config artifacts ready for deployment orchestration (Phase 6).

---

## Phase 4: US-2 — Unified Service Availability Alerting (Priority: P1)

**Goal**: Replace Uptime Kuma with Prometheus-native service availability alerting using the generic `ServiceDown` rule and proper inhibition rules to avoid duplicate alerts.

**Independent Test**: Stop a monitored service, verify that the ServiceDown alert would fire. Verify inhibition rules prevent duplicate alerts for Synology targets.

- [ ] T009 [US-2] Update Alertmanager configuration with inhibition rules
  - **Modify**: `ansible/roles/monitoring_stack/templates/alertmanager.yml.j2`
    - Replace existing `inhibit_rules` section with updated rules using `source_matchers`/`target_matchers` syntax (Alertmanager v0.30.0 — R-03)
    - Add 4 inhibition rules per `contracts/alertmanager-config.yml`:
      1. SynologyNASDown suppresses ServiceDown for same instance (FR-028, SC-011)
      2. SynologyNASDown suppresses Synology.* alerts for same instance (existing rule, migrated syntax)
      3. ServiceDown (component=availability) suppresses infrastructure threshold alerts (component=infrastructure) for same instance (FR-029)
      4. Critical severity suppresses warning for same alertname+instance
    - Preserve route tree and receivers sections unchanged (existing SMTP config)
  - **Traces to**: FR-028, FR-029, SC-011, DL-11, DL-12, R-07
  - **Dependencies**: T005 (infrastructure alerts define the component labels used in inhibition matching)
  - **Done-when**: Template contains `source_matchers` (not deprecated `source_match`) AND contains all 4 inhibition rule blocks AND does NOT contain deprecated `source_match:`/`target_match:` keys AND `ansible-lint ansible/roles/monitoring_stack/` exits 0

- [ ] T010 [US-2,US-4] Create alert rule validation task
  - **Create**: `ansible/roles/monitoring_stack/tasks/validate_alerts.yml`
    - Task: run `promtool check rules` via Docker: `docker run --rm -v {{ prometheus_config_path }}:/etc/prometheus:ro prom/prometheus:{{ prometheus_version }} promtool check rules /etc/prometheus/alerts/synology_alerts.yml /etc/prometheus/alerts/infrastructure_alerts.yml /etc/prometheus/alerts/service_alerts.yml`
    - Task must fail the playbook with a clear error if any rule file is invalid (FR-030)
    - Task has `changed_when: false` (read-only check)
  - **Traces to**: FR-030, SC-010
  - **Dependencies**: T005, T006 (alert files must exist in the spec to define the paths)
  - **Done-when**: `ansible-lint ansible/roles/monitoring_stack/tasks/validate_alerts.yml` exits 0 AND file contains `promtool check rules` AND file contains `changed_when: false`

**Checkpoint**: Alertmanager config ready with inhibition rules. Validation task ready. ServiceDown alert (in T005's infrastructure_alerts.yml) replaces Uptime Kuma HTTP checks.

---

## Phase 5: US-3 — Application-Level Service Metrics (Priority: P1)

**Goal**: Enable native Prometheus metrics on Caddy (reverse proxy) and Immich (photo service), declare their monitoring contracts, and provide dedicated dashboards.

**Independent Test**: After deployment, `curl http://192.168.1.211:2019/metrics` returns Caddy metrics and `curl http://192.168.1.213:8081/metrics` returns Immich metrics.

### Caddy Metrics

- [ ] T011 [P] [US-3] Enable Caddy metrics and add monitoring contract to reverse_proxy role
  - **Modify**: `ansible/roles/reverse_proxy/defaults/main.yml`
    - Add variables: `caddy_metrics_enabled: true`, `caddy_metrics_port: 2019`, `caddy_admin_listen: "0.0.0.0:2019"`
    - Add `monitoring_contract`:
      ```yaml
      monitoring_contract:
        enabled: true
        scrape_targets:
          - job_name: "caddy"
            port: 2019
            path: "/metrics"
            scrape_interval: "30s"
        alert_rules:
          - alert: "CaddyHighErrorRate"
            expr: "sum(rate(caddy_http_requests_total{code=~\"5..\"}[5m])) / sum(rate(caddy_http_requests_total[5m])) > 0.05"
            for: "5m"
            severity: "warning"
            summary: "Caddy high 5xx error rate"
            description: "More than 5% of Caddy responses are 5xx errors over the last 5 minutes (current: {{ $value | printf \"%.2f\" }}%)."
        dashboard_file: "roles/reverse_proxy/files/grafana/dashboards/caddy-reverse-proxy.json"
      ```
  - **Modify**: `ansible/roles/reverse_proxy/templates/Caddyfile.j2`
    - Add to global options block (conditional on `caddy_metrics_enabled`):
      ```caddyfile
      servers {
          metrics
      }
      admin {{ caddy_admin_listen }}
      ```
    - Admin listen on `0.0.0.0:2019` makes metrics reachable from monitoring LXC (R-04)
    - Metrics endpoint must NOT be exposed via public HTTPS reverse proxy (FR-006, C-003)
  - **Traces to**: FR-004, FR-006, FR-007, FR-015, A-003, R-04, DL-03
  - **Dependencies**: None
  - **Done-when**: `grep 'caddy_metrics_enabled' ansible/roles/reverse_proxy/defaults/main.yml` matches AND `grep 'monitoring_contract' ansible/roles/reverse_proxy/defaults/main.yml` matches AND `grep 'metrics' ansible/roles/reverse_proxy/templates/Caddyfile.j2` matches AND `grep 'caddy_metrics_enabled' ansible/roles/reverse_proxy/templates/Caddyfile.j2` matches (conditional)

### Immich Metrics

- [ ] T012 [P] [US-3] Enable Immich telemetry and add monitoring contract to immich role
  - **Modify**: `ansible/roles/immich/defaults/main.yml`
    - Add variables: `immich_metrics_enabled: true`, `immich_metrics_port: 8081`, `immich_microservices_metrics_port: 8082`
    - Add `monitoring_contract`:
      ```yaml
      monitoring_contract:
        enabled: true
        scrape_targets:
          - job_name: "immich-api"
            port: 8081
            path: "/metrics"
            scrape_interval: "30s"
          - job_name: "immich-microservices"
            port: 8082
            path: "/metrics"
            scrape_interval: "30s"
        alert_rules:
          - alert: "ImmichJobBacklogHigh"
            expr: "immich_jobs_waiting > 500"
            for: "10m"
            severity: "warning"
            summary: "Immich job backlog growing on {{ $labels.instance }}"
            description: "Immich has more than 500 waiting jobs for 10 minutes (current: {{ $value }})."
        dashboard_file: "roles/immich/files/grafana/dashboards/immich-photo-service.json"
      ```
  - **Modify**: `ansible/roles/immich/templates/.env.j2`
    - Add line (conditional on `immich_metrics_enabled`): `IMMICH_TELEMETRY_INCLUDE=all` (R-05)
  - **Modify**: `ansible/roles/immich/templates/docker-compose.yml.j2`
    - Add port mappings to immich-server service (conditional on `immich_metrics_enabled`):
      ```yaml
      - "{{ immich_metrics_port }}:8081"
      - "{{ immich_microservices_metrics_port }}:8082"
      ```
  - **Traces to**: FR-005, FR-006, FR-007, FR-015, A-004, R-05, DL-03
  - **Dependencies**: None
  - **Done-when**: `grep 'immich_metrics_enabled' ansible/roles/immich/defaults/main.yml` matches AND `grep 'monitoring_contract' ansible/roles/immich/defaults/main.yml` matches AND `grep 'IMMICH_TELEMETRY' ansible/roles/immich/templates/.env.j2` matches AND `grep '8081' ansible/roles/immich/templates/docker-compose.yml.j2` matches

### Service-Specific Alert Rules

- [ ] T013 [US-3,US-4] Create service-specific alert rules Jinja2 template
  - **Create**: `ansible/roles/monitoring_stack/templates/service_alerts.yml.j2`
    - Jinja2 template that iterates over `groups['services'] | default([])`, reads `hostvars[host].monitoring_contract | default({})`, and for each contract with `enabled` and non-empty `alert_rules`, generates a Prometheus alert rules group
    - Group name derived from `{{ host }}_alerts`
    - Each alert rule rendered with: alert name, expr, for, labels (severity, component), annotations (summary, description)
    - If no service declares alert rules, file should still be valid YAML (empty groups list)
    - Template must NOT reference any service by name (SC-005)
  - **Traces to**: FR-009, FR-015, SC-005
  - **Dependencies**: T011, T012 (contracts with alert_rules must be defined to verify template logic)
  - **Done-when**: `ansible-lint ansible/roles/monitoring_stack/` exits 0 AND `grep -c 'caddy\|immich' ansible/roles/monitoring_stack/templates/service_alerts.yml.j2` returns 0 AND template contains `hostvars` and `monitoring_contract` iteration logic

### Dashboards

- [ ] T014 [P] [US-3] Create Caddy reverse proxy Grafana dashboard JSON
  - **Create**: `ansible/roles/reverse_proxy/files/grafana/dashboards/caddy-reverse-proxy.json`
    - Note: `ansible/roles/reverse_proxy/files/` directory does not exist — create intermediate directories
    - Grafana Schema v1 JSON, compatible with Grafana 12.x (FR-027)
    - Unique `uid` field (e.g., `"caddy-reverse-proxy"`)
    - Panels using `timeseries` panel type:
      - HTTP request rate: `sum(rate(caddy_http_requests_total[$__rate_interval]))`
      - Response time distribution: `histogram_quantile(0.99, rate(caddy_http_request_duration_seconds_bucket[$__rate_interval]))`
      - Error rate breakdown: `sum by(code)(rate(caddy_http_requests_total{code=~"[45].."}[$__rate_interval]))`
      - Upstream health: `caddy_reverse_proxy_upstreams_healthy`
    - Auto-refresh: 30s, Datasource: Prometheus
  - **Traces to**: FR-010, FR-017, SC-003, SC-005
  - **Dependencies**: None
  - **Done-when**: `python3 -c "import json; d=json.load(open('ansible/roles/reverse_proxy/files/grafana/dashboards/caddy-reverse-proxy.json')); assert d.get('uid') == 'caddy-reverse-proxy'; assert any('caddy_http' in str(p) for p in d.get('panels',[]))"` exits 0

- [ ] T015 [P] [US-3] Create Immich photo service Grafana dashboard JSON
  - **Create**: `ansible/roles/immich/files/grafana/dashboards/immich-photo-service.json`
    - Note: `ansible/roles/immich/files/` directory does not exist — create intermediate directories
    - Grafana Schema v1 JSON, compatible with Grafana 12.x (FR-027)
    - Unique `uid` field (e.g., `"immich-photo-service"`)
    - Panels using `timeseries` and `stat` panel types:
      - API request rate: based on Immich HTTP metrics
      - Background job queue sizes: `immich_jobs_waiting` (by job type)
      - Processing throughput: `immich_jobs_completed` rate
    - Based on community dashboard patterns (R-05, dashboard ID 22555)
    - Auto-refresh: 30s, Datasource: Prometheus
  - **Traces to**: FR-010, FR-018, SC-004, SC-005
  - **Dependencies**: None
  - **Done-when**: `python3 -c "import json; d=json.load(open('ansible/roles/immich/files/grafana/dashboards/immich-photo-service.json')); assert d.get('uid') == 'immich-photo-service'; assert any('immich_' in str(p) for p in d.get('panels',[]))"` exits 0

**Checkpoint**: Caddy and Immich configured to expose metrics. Monitoring contracts declared. Dashboards and service alert template ready. All artifacts for US-3 created.

---

## Phase 6: US-4 — Extensible Monitoring Deployment Integration (Priority: P2)

**Goal**: Wire up the self-registration pattern in the monitoring_stack role's deployment tasks so that monitoring contracts are aggregated at deploy time.

**Independent Test**: Verify that the monitoring_stack role's code contains zero hardcoded references to Caddy, Immich, or any other service name (SC-005).

- [ ] T016 [US-4] Create dashboard provisioning task
  - **Create**: `ansible/roles/monitoring_stack/tasks/provision_dashboards.yml`
    - Task: iterate over `groups['services'] | default([])`, for each host read `hostvars[host].monitoring_contract | default({})`, if contract has `dashboard_file` defined and `enabled`, copy the JSON file from `{{ playbook_dir }}/../{{ contract.dashboard_file }}` to `{{ grafana_dashboards_path }}/` on the monitoring host
    - Use `ansible.builtin.copy` with `src` pointing to the role-relative path
    - Task must NOT reference any service name — it follows contract references only (SC-005)
  - **Traces to**: FR-010, FR-011, SC-005
  - **Dependencies**: T014, T015 (dashboard JSON files must exist)
  - **Done-when**: `ansible-lint ansible/roles/monitoring_stack/tasks/provision_dashboards.yml` exits 0 AND `grep -c 'caddy\|immich' ansible/roles/monitoring_stack/tasks/provision_dashboards.yml` returns 0 AND file contains `hostvars` and `monitoring_contract` and `dashboard_file`

- [ ] T017 [US-4] Update monitoring_stack create_directories.yml — add alerts subdirectory
  - **Modify**: `ansible/roles/monitoring_stack/tasks/create_directories.yml`
    - Add task: Create Prometheus alerts directory `{{ prometheus_config_path }}/alerts` with mode 0755
  - **Traces to**: FR-031
  - **Dependencies**: None
  - **Done-when**: `grep 'alerts' ansible/roles/monitoring_stack/tasks/create_directories.yml` matches AND `ansible-lint ansible/roles/monitoring_stack/tasks/create_directories.yml` exits 0

- [ ] T018 [US-4] Update monitoring_stack compose_stack.yml — deploy alert files and service template
  - **Modify**: `ansible/roles/monitoring_stack/tasks/compose_stack.yml`
    - **Replace** the existing "Deploy Prometheus alert rules" task (which copies `alerts.yml` to `{{ prometheus_config_path }}/alerts.yml`) with:
      1. Copy `synology_alerts.yml` to `{{ prometheus_config_path }}/alerts/synology_alerts.yml`
      2. Copy `infrastructure_alerts.yml` to `{{ prometheus_config_path }}/alerts/infrastructure_alerts.yml`
      3. Template `service_alerts.yml.j2` to `{{ prometheus_config_path }}/alerts/service_alerts.yml`
    - All three tasks notify `Restart monitoring stack` handler
    - **Remove** the `docker compose up -d` task from this file (moved to main.yml for validation ordering — see T020)
  - **Traces to**: FR-009, FR-019, FR-031
  - **Dependencies**: T005, T006, T013 (alert files and template must exist)
  - **Done-when**: File references `alerts/synology_alerts.yml` AND `alerts/infrastructure_alerts.yml` AND `service_alerts.yml.j2` AND does NOT contain the old `alerts.yml` single-file copy AND does NOT contain `docker compose up -d`

- [ ] T019 [US-4] Update monitoring_stack grafana_provision.yml — include dashboard provisioning
  - **Modify**: `ansible/roles/monitoring_stack/tasks/grafana_provision.yml`
    - Add task after existing dashboard copy: `include_tasks: provision_dashboards.yml`
    - Existing Synology NAS dashboard copy is preserved (FR-019)
    - Add copy of `infrastructure-overview.json` to `{{ grafana_dashboards_path }}/` (deployed directly by monitoring_stack role, not via self-registration)
  - **Traces to**: FR-010, FR-016, FR-019
  - **Dependencies**: T008 (infrastructure dashboard JSON), T016 (provisioning task)
  - **Done-when**: File includes `provision_dashboards.yml` AND copies `infrastructure-overview.json` AND preserves `synology-nas.json` copy

- [ ] T020 [US-4] Update monitoring_stack main.yml — task orchestration
  - **Modify**: `ansible/roles/monitoring_stack/tasks/main.yml`
    - **Add** `include_tasks: kuma_cleanup.yml` as the FIRST task (before docker.yml) with `tags: [cleanup]`
    - **Add** `include_tasks: validate_alerts.yml` AFTER `grafana_provision.yml` with `tags: [validate]`
    - **Add** "Start monitoring stack" task AFTER `validate_alerts.yml`:
      ```yaml
      - name: Start monitoring stack
        ansible.builtin.command:
          cmd: docker compose up -d
          chdir: "{{ monitoring_base_path }}"
        register: docker_compose_result
        changed_when: "'Created' in docker_compose_result.stdout or 'Started' in docker_compose_result.stdout"
        tags: [compose]
      ```
    - This ensures: kuma cleanup → docker install → directory creation → config deployment → dashboard provisioning → alert validation → stack start → backup cron → mdns → verify
    - The `docker compose up -d` was removed from compose_stack.yml (T018) and moved here to allow validation between config deploy and stack start
  - **Traces to**: FR-030, FR-031, FR-032
  - **Dependencies**: T010 (validate_alerts.yml), T016 (provision_dashboards.yml), T018 (compose_stack.yml no longer starts stack)
  - **Done-when**: File includes `kuma_cleanup.yml` (first include) AND includes `validate_alerts.yml` AND contains `docker compose up -d` AND the order is: kuma_cleanup → docker → directories → compose_stack → grafana_provision → validate_alerts → compose_up → backup → mdns → verify

**Checkpoint**: Monitoring stack deployment fully orchestrated. Self-registration wired end-to-end. All monitoring artifacts deployed in correct order with validation.

---

## Phase 7: US-6 — Uptime Kuma Decommission (Priority: P2)

**Goal**: Completely remove Uptime Kuma from the codebase, the monitoring container, and all cross-role references.

**Independent Test**: `grep -ri 'kuma' ansible/` returns zero results in active code (excluding git history).

### Monitoring Stack Cleanup

- [ ] T021 [US-6] Create Kuma cleanup task in monitoring_stack
  - **Create**: `ansible/roles/monitoring_stack/tasks/kuma_cleanup.yml`
    - Tasks (all idempotent):
      1. Check if `uptime-kuma` Docker container exists (`docker ps -a --filter name=uptime-kuma --format '{{ "{{" }}.Names{{ "}}" }}'`)
      2. Stop and remove container if present (`docker rm -f uptime-kuma`)
      3. Check if Docker volume exists and remove (`docker volume rm` if present)
      4. Remove Kuma data directory if present (`/opt/monitoring/uptime-kuma` or similar)
    - Each task guarded by `when:` condition checking existence first
  - **Traces to**: FR-023, SC-006
  - **Dependencies**: None
  - **Done-when**: `ansible-lint ansible/roles/monitoring_stack/tasks/kuma_cleanup.yml` exits 0 AND file contains `uptime-kuma` container name AND all tasks have idempotency guards

- [ ] T022 [P] [US-6] Update monitoring_stack service description — remove Kuma reference
  - **Modify**: `ansible/roles/monitoring_stack/templates/monitoring-stack.service.j2`
    - Change `Description=Monitoring Stack (Uptime Kuma)` → `Description=Monitoring Stack`
  - **Traces to**: FR-020, SC-006
  - **Dependencies**: None
  - **Done-when**: `grep -c 'Kuma\|kuma' ansible/roles/monitoring_stack/templates/monitoring-stack.service.j2` returns 0

### Uptime Kuma Role Removal

- [ ] T023 [P] [US-6] Delete Uptime Kuma Ansible role directory
  - **Delete**: `ansible/roles/uptime_kuma/` — entire directory (12 files: defaults/main.yml, tasks/{main,check_setup,setup_admin,login,wait_for_api,get_monitors,provision_monitors,verify_monitors,configure_smtp}.yml, files/configure_uptime_kuma.js, templates/monitoring_config.json.j2)
  - **Traces to**: FR-020, SC-006
  - **Dependencies**: None (monitoring playbook does not reference this role — A-010)
  - **Done-when**: `test ! -d ansible/roles/uptime_kuma/` exits 0

### Variable Cleanup

- [ ] T024 [P] [US-6] Remove Kuma variables from monitoring host_vars and vault example
  - **Modify**: `ansible/host_vars/monitoring/vars.yml`
    - Remove: `monitoring_targets` list (4 entries), `uptime_kuma_api_url`, `uptime_kuma_api_wait_timeout`, `uptime_kuma_api_retry_delay`, `uptime_kuma_api_max_retries`
    - Preserve: `alert_down_threshold: 2`, `healthcheck_url` config, all other variables
  - **Modify**: `ansible/host_vars/monitoring/vault.yml.example`
    - Remove: `uptime_kuma_admin_user` and `uptime_kuma_admin_password` lines and any associated comment header
    - Preserve: SMTP credential examples
  - **Traces to**: FR-021, FR-022, SC-006
  - **Dependencies**: T023 (role that used these vars is deleted)
  - **Done-when**: `grep -c 'uptime_kuma\|monitoring_targets' ansible/host_vars/monitoring/vars.yml` returns 0 AND `grep -c 'uptime_kuma' ansible/host_vars/monitoring/vault.yml.example` returns 0 AND `grep 'alert_down_threshold' ansible/host_vars/monitoring/vars.yml` still matches (preserved)

### proxmox_backup Role Cleanup

- [ ] T025 [P] [US-6] Clean proxmox_backup role's Kuma integration
  - **Delete**: `ansible/roles/proxmox_backup/tasks/configure_kuma.yml`
  - **Modify**: `ansible/roles/proxmox_backup/defaults/main.yml`
    - Change `proxmox_backup_email_mode: "kuma_only"` → `"disabled"`
    - Remove `proxmox_backup_kuma_push_url` variable
    - Update mode documentation comment to list only: `enabled`, `disabled` (remove `kuma_only`)
  - **Modify**: `ansible/roles/proxmox_backup/tasks/main.yml`
    - Remove the `configure_kuma.yml` include block (the `when: proxmox_backup_email_mode == 'kuma_only'` conditional)
    - Change disable_email condition from `proxmox_backup_email_mode in ['kuma_only', 'disabled']` to `proxmox_backup_email_mode == 'disabled'`
    - Remove `kuma` tag from tag lists
  - **Modify**: `ansible/roles/proxmox_backup/templates/proxmox-backup.conf.j2`
    - Remove the `KUMA_URL="{{ proxmox_backup_kuma_url | default('') }}"` line
  - **Modify**: `ansible/roles/proxmox_backup/templates/proxmox-config-backup.sh.j2`
    - Remove the `send_kuma_notification()` function definition (~lines 63-95)
    - Remove the two call sites for `send_kuma_notification` in the `cleanup()` function (~lines 115, 134)
  - **Traces to**: FR-024, SC-006, DL-14
  - **Dependencies**: None (code path is already dead — group_vars set mode to "disabled" per A-011)
  - **Done-when**: `test ! -f ansible/roles/proxmox_backup/tasks/configure_kuma.yml` exits 0 AND `grep -ci 'kuma' ansible/roles/proxmox_backup/defaults/main.yml` returns 0 AND `grep -ci 'kuma' ansible/roles/proxmox_backup/tasks/main.yml` returns 0 AND `grep -ci 'kuma\|KUMA' ansible/roles/proxmox_backup/templates/proxmox-backup.conf.j2` returns 0 AND `grep -ci 'kuma' ansible/roles/proxmox_backup/templates/proxmox-config-backup.sh.j2` returns 0 AND `ansible-lint ansible/roles/proxmox_backup/` exits 0

- [ ] T026 [P] [US-6] Remove Kuma references from proxmox_hosts group_vars
  - **Modify**: `ansible/group_vars/proxmox_hosts/vars.yml`
    - Remove the commented-out `# proxmox_backup_kuma_url: "https://kuma.example.com/api/push/..."` lines (approximately 2 lines: comment header + value)
  - **Traces to**: FR-024, SC-006
  - **Dependencies**: None
  - **Done-when**: `grep -ci 'kuma' ansible/group_vars/proxmox_hosts/vars.yml` returns 0

**Checkpoint**: All Uptime Kuma code, variables, secrets, and cross-role references removed. SC-006 satisfied.

---

## Phase 8: Documentation & Validation

**Purpose**: Update all documentation that references Uptime Kuma and validate the entire changeset.

### Documentation Updates

- [ ] T027 [P] [US-6] Update docs/operations.md — remove Kuma mode references
  - **Modify**: `docs/operations.md`
    - Replace the "Email Decommissioning & Kuma Migration" section content to reflect: Kuma is decommissioned, monitoring uses Prometheus `up` metric + Alertmanager for service availability, email mode is `disabled` (actual state per A-011, A-012)
    - Remove `kuma_only` mode references
  - **Traces to**: FR-025
  - **Done-when**: `grep -ci 'kuma_only' docs/operations.md` returns 0

- [ ] T028 [P] [US-6] Update docs/operations/backups-proxmox-config.md — remove Kuma monitoring section
  - **Modify**: `docs/operations/backups-proxmox-config.md`
    - Remove "Uptime Kuma (Primary)" monitoring subsection and KUMA_URL configuration references
    - Update monitoring section to reflect that backup success/failure is logged to systemd journal (DL-15)
  - **Traces to**: FR-025
  - **Done-when**: `grep -ci 'KUMA_URL\|Uptime Kuma' docs/operations/backups-proxmox-config.md` returns 0

- [ ] T029 [P] [US-6] Update docs/operations/backups-proxmox-config-email-decommission.md — remove kuma_only state
  - **Modify**: `docs/operations/backups-proxmox-config-email-decommission.md`
    - Remove `kuma_only` state from the state machine table
    - Remove Kuma-related transitions and procedures (e.g., "Verify Kuma Monitoring" steps)
    - Update state machine to only include: `enabled`, `disabled` states
  - **Traces to**: FR-025
  - **Done-when**: `grep -ci 'kuma_only' docs/operations/backups-proxmox-config-email-decommission.md` returns 0

- [ ] T030 [P] [US-6] Update docs/architecture.md — update monitoring references
  - **Modify**: `docs/architecture.md`
    - Remove `**Target**: Uptime Kuma Push notifications (Heartbeat).` line from the "Backup & Monitoring" section
    - Update monitoring description to reflect Prometheus/Alertmanager-based monitoring with node_exporter across all service containers
  - **Traces to**: FR-025
  - **Done-when**: `grep -ci 'Uptime Kuma' docs/architecture.md` returns 0

### Validation

- [ ] T031 Run ansible-lint on all modified and new roles
  - **Command**: `ansible-lint ansible/roles/node_exporter/ ansible/roles/lxc_base/ ansible/roles/monitoring_stack/ ansible/roles/reverse_proxy/ ansible/roles/immich/ ansible/roles/proxmox_backup/`
  - **Traces to**: FR-031, FR-032
  - **Dependencies**: All previous tasks
  - **Done-when**: Command exits 0 with no errors

- [ ] T032 Run yamllint on all new and modified YAML files
  - **Command**: Run yamllint on each new/modified `.yml` file in the changeset
  - **Traces to**: FR-031
  - **Dependencies**: All previous tasks
  - **Done-when**: Command exits 0 with no errors (warnings acceptable)

- [ ] T033 Verify SC-005: monitoring_stack role has zero service name references
  - **Command**: `rg -i 'caddy|immich|jellyfin|nextcloud|adguard|homeassistant' ansible/roles/monitoring_stack/ -g '*.yml' -g '*.j2' -g '*.json' --count`
  - **Traces to**: SC-005
  - **Dependencies**: All previous tasks
  - **Done-when**: Command returns 0 matches (no service names hardcoded in monitoring_stack role)

- [ ] T034 Verify SC-006: no Kuma references remain in active codebase
  - **Command**: `rg -i 'uptime.kuma|kuma_only' ansible/ docs/ --count` (excluding git-ignored files)
  - **Traces to**: SC-006
  - **Dependencies**: All previous tasks (especially T023-T030)
  - **Done-when**: Command returns 0 matches

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Foundational)**: No dependencies — can start immediately
- **Phase 2 (US-5)**: No dependencies — can run in parallel with Phase 1
- **Phase 3 (US-1+US-4)**: T007 depends on Phase 1 (T002) and Phase 5 (T011, T012 for contract validation). Other tasks in Phase 3 are parallel-safe.
- **Phase 4 (US-2)**: T009 depends on T005 (alert labels). T010 depends on T005, T006.
- **Phase 5 (US-3)**: Independent of other phases (except T013 depends on T011/T012 for contract validation)
- **Phase 6 (US-4 integration)**: Depends on Phases 3, 4, 5 — all artifacts must exist
- **Phase 7 (US-6)**: Independent — can run in parallel with Phases 3-5
- **Phase 8 (Validation)**: Depends on ALL previous phases

### Parallel Opportunities

```
Phase 1:  T001 ──► T002
                         ├──► Phase 3 (T007 depends on T002, T011, T012)
Phase 2:  T003           │
                         │
Phase 3:  T005, T006, T008  (all parallel)
          T007 (depends on T011, T012 for contract validation)
                         │
Phase 4:  T009, T010     │  (parallel with Phase 5)
                         │
Phase 5:  T011, T012     │  (parallel with Phase 4)
          T013 (depends on T011, T012)
          T014, T015     (parallel)
                         │
Phase 6:  T016, T017, T018, T019, T020  (sequential dependencies)
                         │
Phase 7:  T021-T026      │  (all parallel, can run alongside Phases 3-5)
                         │
Phase 8:  T027-T030 (parallel docs), T031-T034 (sequential validation)
```

### Critical Path

T001 → T002 → T011/T012 → T007 → T018 → T020 → T031 (validation)

---

## File Manifest

### Files Created (15)

| # | File Path | Task |
|---|-----------|------|
| 1 | `ansible/roles/node_exporter/defaults/main.yml` | T001 |
| 2 | `ansible/roles/node_exporter/tasks/main.yml` | T001 |
| 3 | `ansible/roles/node_exporter/templates/node_exporter.service.j2` | T001 |
| 4 | `ansible/roles/node_exporter/handlers/main.yml` | T001 |
| 5 | `ansible/roles/monitoring_stack/files/prometheus/alerts/infrastructure_alerts.yml` | T005 |
| 6 | `ansible/roles/monitoring_stack/files/prometheus/alerts/synology_alerts.yml` | T006 |
| 7 | `ansible/roles/monitoring_stack/files/grafana/dashboards/infrastructure-overview.json` | T008 |
| 8 | `ansible/roles/monitoring_stack/tasks/validate_alerts.yml` | T010 |
| 9 | `ansible/roles/monitoring_stack/templates/service_alerts.yml.j2` | T013 |
| 10 | `ansible/roles/reverse_proxy/files/grafana/dashboards/caddy-reverse-proxy.json` | T014 |
| 11 | `ansible/roles/immich/files/grafana/dashboards/immich-photo-service.json` | T015 |
| 12 | `ansible/roles/monitoring_stack/tasks/provision_dashboards.yml` | T016 |
| 13 | `ansible/roles/monitoring_stack/tasks/kuma_cleanup.yml` | T021 |

### Files Modified (25)

| # | File Path | Task |
|---|-----------|------|
| 1 | `ansible/roles/lxc_base/tasks/main.yml` | T002 |
| 2 | `ansible/roles/monitoring_stack/defaults/main.yml` | T003 |
| 3 | `ansible/roles/monitoring_stack/templates/prometheus.yml.j2` | T007 |
| 4 | `ansible/roles/monitoring_stack/templates/alertmanager.yml.j2` | T009 |
| 5 | `ansible/roles/reverse_proxy/defaults/main.yml` | T011 |
| 6 | `ansible/roles/reverse_proxy/templates/Caddyfile.j2` | T011 |
| 7 | `ansible/roles/immich/defaults/main.yml` | T012 |
| 8 | `ansible/roles/immich/templates/.env.j2` | T012 |
| 9 | `ansible/roles/immich/templates/docker-compose.yml.j2` | T012 |
| 10 | `ansible/roles/monitoring_stack/tasks/create_directories.yml` | T017 |
| 11 | `ansible/roles/monitoring_stack/tasks/compose_stack.yml` | T018 |
| 12 | `ansible/roles/monitoring_stack/tasks/grafana_provision.yml` | T019 |
| 13 | `ansible/roles/monitoring_stack/tasks/main.yml` | T020 |
| 14 | `ansible/roles/monitoring_stack/templates/monitoring-stack.service.j2` | T022 |
| 15 | `ansible/host_vars/monitoring/vars.yml` | T024 |
| 16 | `ansible/host_vars/monitoring/vault.yml.example` | T024 |
| 17 | `ansible/roles/proxmox_backup/defaults/main.yml` | T025 |
| 18 | `ansible/roles/proxmox_backup/tasks/main.yml` | T025 |
| 19 | `ansible/roles/proxmox_backup/templates/proxmox-backup.conf.j2` | T025 |
| 20 | `ansible/roles/proxmox_backup/templates/proxmox-config-backup.sh.j2` | T025 |
| 21 | `ansible/group_vars/proxmox_hosts/vars.yml` | T026 |
| 22 | `docs/operations.md` | T027 |
| 23 | `docs/operations/backups-proxmox-config.md` | T028 |
| 24 | `docs/operations/backups-proxmox-config-email-decommission.md` | T029 |
| 25 | `docs/architecture.md` | T030 |

### Files Deleted (14)

| # | File Path | Task |
|---|-----------|------|
| 1 | `ansible/roles/monitoring_stack/files/prometheus/alerts.yml` | T006 |
| 2 | `ansible/roles/uptime_kuma/defaults/main.yml` | T023 |
| 3 | `ansible/roles/uptime_kuma/tasks/main.yml` | T023 |
| 4 | `ansible/roles/uptime_kuma/tasks/check_setup.yml` | T023 |
| 5 | `ansible/roles/uptime_kuma/tasks/setup_admin.yml` | T023 |
| 6 | `ansible/roles/uptime_kuma/tasks/login.yml` | T023 |
| 7 | `ansible/roles/uptime_kuma/tasks/wait_for_api.yml` | T023 |
| 8 | `ansible/roles/uptime_kuma/tasks/get_monitors.yml` | T023 |
| 9 | `ansible/roles/uptime_kuma/tasks/provision_monitors.yml` | T023 |
| 10 | `ansible/roles/uptime_kuma/tasks/verify_monitors.yml` | T023 |
| 11 | `ansible/roles/uptime_kuma/tasks/configure_smtp.yml` | T023 |
| 12 | `ansible/roles/uptime_kuma/files/configure_uptime_kuma.js` | T023 |
| 13 | `ansible/roles/uptime_kuma/templates/monitoring_config.json.j2` | T023 |
| 14 | `ansible/roles/proxmox_backup/tasks/configure_kuma.yml` | T025 |

---

## Constitution Check

| # | Principle | Status | Evidence |
|---|-----------|--------|----------|
| I | Spec-Driven Workflow | ✅ PASS | Every task traces to FR/US/SC identifiers in spec.md. No tasks add unrequested functionality. |
| II | Secrets Policy | ✅ PASS | No new secrets introduced. Existing SMTP creds remain in vault. Kuma secrets removed (T024). node_exporter requires no secrets. |
| III | Separation of Concerns | ✅ PASS | All changes are Ansible configuration. No Terraform files touched. No container creation/sizing changes. |
| IV | Code Economy (YAGNI) | ✅ PASS | Empty monitoring contracts for jellyfin/nextcloud removed (were stubs with no current function). All new files justified: node_exporter role (new capability, 4 files), alert files (distinct rule sets), dashboards (spec-required), task files (match existing monitoring_stack pattern of ~8 separate task files). Self-registration loops have 2+ consumers today (Caddy + Immich). Variables are multi-use or environment-specific. |
| V | Dual-Provisioning Parity | ✅ PASS | All tasks produce Ansible roles/playbooks runnable from CI (self-hosted runner) and developer laptop. No CI-only paths introduced. |
| WF-1 | Test-Driven Changes | ✅ PASS | T010 adds promtool validation. T031-T034 provide ansible-lint, yamllint, and grep-based verification. |
| WF-2 | CI/CD Expectations | ✅ PASS | No destructive automation. Kuma cleanup (T021) is idempotent. No new workflows needed. |
| NET-1 | Static IPs | ✅ PASS | All IPs sourced from inventory `ansible_host`. Ports defined as variables in role defaults (9100, 2019, 8081, 8082). |
| SEC-1 | No plaintext secrets | ✅ PASS | No secrets in any new file. Alertmanager template uses existing vault-encrypted SMTP vars. |

---

## Self-Critique

### Strengths
- Every task has mechanically verifiable done-conditions using grep, test, ansible-lint, yamllint, or python3 checks
- File manifest is comprehensive (13 created + 25 modified + 14 deleted = 52 file operations)
- Design correction documented (monitoring contract scrape targets vs. group-based node_exporter job)
- YAGNI compliance: empty monitoring contracts for jellyfin/nextcloud removed per Constitution Principle IV (Code Economy) — they were stubs with no current function; monitoring contracts added only to services with actual app metrics (Caddy, Immich)
- Parallel opportunities clearly marked with dependency chain
- Constitution check passes all principles including the new YAGNI principle

### Issues Found
- **[severity: low]** The production inventory currently only has 5 of the 7 services listed in FR-001 (AdGuard and Home Assistant are missing). This is documented in the Inventory Note and is consistent with A-006, but the developer should be aware that FR-001's "every service container" claim is aspirational until these hosts are added to the inventory.
- **[severity: low]** T010's promtool validation uses `docker run` which requires the Prometheus image to be available. On first deployment before `docker compose pull`, this adds ~30s pull time. The developer could add `docker pull prom/prometheus:{{ prometheus_version }}` as a prerequisite or accept the one-time delay.
- **[severity: low]** T018 restructures compose_stack.yml by removing the `docker compose up -d` command and moving it to main.yml (T020). This is a refactoring of the existing task orchestration that the plan doesn't explicitly call out. The rationale (validation between config deploy and stack start) is sound but should be tested for idempotency.
- **[severity: low]** Plan Steps 3, 4, 5 call for node_exporter scrape targets in monitoring contracts, but the Prometheus scrape config contract shows node_exporter handled by a separate group-based job. This tasks.md corrects the discrepancy — monitoring contracts only declare application-level metrics. The plan should be amended to reflect this if a future revision is made.
- **[severity: low]** The plan calls for monitoring contracts on jellyfin and nextcloud (Step 3). This tasks.md omits them per Constitution Principle IV (YAGNI) — these contracts have empty scrape_targets, empty alert_rules, and null dashboard_file, serving no current function. They can be added in a future iteration when those services gain native metrics.

### Verdict
ACCEPT — All issues are low severity and documented. No blocking gaps.

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Commit after each phase completion (at checkpoint markers)
- Run `ansible-lint` incrementally after each role modification
- The monitoring playbook (`ansible/playbooks/monitoring.yml`) is UNCHANGED — its role list (`lxc_base`, `mdns_base`, `monitoring_stack`) remains the same
