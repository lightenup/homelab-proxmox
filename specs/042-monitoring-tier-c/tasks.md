# Tasks: Monitoring Tier C — Security & Availability Probing

**Input**: Design documents from `/specs/042-monitoring-tier-c/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, quickstart.md

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Summary

- **Total tasks**: 20
- **Estimated complexity**: Medium-High
- **Parallel tracks**: 3 independent tracks (blackbox/US-1/US-2, fail2ban/US-3, alerts+dashboard/US-4/US-5)
- **Task count by story**: US-1/US-2: 4, US-3: 6, US-4: 1, US-5: 2, Cross-cutting wiring: 1, Validation: 6

---

## Phase 1: Setup

Not applicable. Features 040 (Monitoring Overhaul) and 041 (Monitoring Tier B) are mandatory prerequisites — Prometheus, Grafana, Alertmanager, Docker Compose stack, monitoring contract self-registration pattern, and Prometheus hot-reload (`--web.enable-lifecycle`) must already be deployed and operational.

---

## Phase 2: Foundational

Not applicable. Phase 3 (HTTPS probing) and Phase 4 (fail2ban) are independently implementable — no shared infrastructure needs building before either can begin.

---

## Phase 3: User Stories 1 & 2 — HTTPS Endpoint Probing + TLS Certificate Monitoring (Priority: P1) 🎯 MVP

**Goal**: Deploy the Prometheus blackbox_exporter as a container in the monitoring Docker Compose stack and configure 5 HTTPS probe targets via static scrape config in Prometheus, exposing metrics for probe success, response latency, DNS lookup time, and TLS certificate expiry per endpoint. TLS certificate expiry metrics (same infrastructure) satisfy US-2.

**Independent Test**: After deploying `ansible-playbook ansible/playbooks/monitoring.yml`, open the Prometheus targets page — `blackbox-exporter` and `blackbox-https` jobs show "UP" with 5 probe targets. Query `probe_success{job="blackbox-https"}` — 5 series returned, all value 1. Query `(probe_ssl_earliest_cert_expiry{job="blackbox-https"} - time()) / 86400` — 5 series showing >60 days until expiry.

### Implementation for User Stories 1 & 2

- [X] T001 [P] [US1/US2] Create `ansible/roles/monitoring_stack/templates/blackbox.yml.j2` — single `https_2xx` module under `modules:` with `prober: http`, `timeout: 10s`, `http.method: GET`, `http.follow_redirects: true`, `http.fail_if_not_ssl: true`, `http.preferred_ip_protocol: "ip4"`, `http.tls_config.insecure_skip_verify: false`

  **Done-condition**: File exists. `grep 'https_2xx' ansible/roles/monitoring_stack/templates/blackbox.yml.j2` returns 1 match. `grep 'follow_redirects: true' ansible/roles/monitoring_stack/templates/blackbox.yml.j2` returns 1 match.

- [X] T002 [P] [US1/US2] Add blackbox exporter variables to `ansible/roles/monitoring_stack/defaults/main.yml` (append `blackbox_exporter_version: "v0.28.0"`, `blackbox_exporter_port: 9115`, `blackbox_config_path: "{{ monitoring_install_dir }}/blackbox"` — uses `monitoring_install_dir` matching existing path pattern in defaults) and to `ansible/group_vars/monitoring/vars.yml` (append `blackbox_exporter_version: "v0.28.0"`, `blackbox_exporter_port: 9115`, plus `blackbox_https_targets` list with 5 entries: `https://grafana.hus-sky.no`, `https://immich.hus-sky.no`, `https://nextcloud.hus-sky.no`, `https://jellyfin.hus-sky.no`, `https://adguard.hus-sky.no` — do NOT add `blackbox_config_path` to vars.yml, the default is sufficient, same pattern as `telegraf_config_path`)

  **Done-condition**: `grep -c 'blackbox' ansible/roles/monitoring_stack/defaults/main.yml` returns 3. `grep -c 'hus-sky.no' ansible/group_vars/monitoring/vars.yml` returns 5.

- [X] T003 [US1/US2] Add `blackbox-exporter` service block to `ansible/roles/monitoring_stack/templates/docker-compose.yml.j2` after the `alertmanager` service — `container_name: blackbox-exporter`, `image: prom/blackbox-exporter:{{ blackbox_exporter_version }}`, `command: ['--config.file=/etc/blackbox/blackbox.yml']`, `ports: ["{{ blackbox_exporter_port }}:9115"]`, `volumes: ["{{ blackbox_config_path }}:/etc/blackbox:ro"]`, `environment: [TZ={{ timezone }}]`, `restart: unless-stopped`, healthcheck on `http://localhost:9115/metrics` matching the Telegraf container healthcheck pattern

  **Done-condition**: `grep -c 'blackbox-exporter' ansible/roles/monitoring_stack/templates/docker-compose.yml.j2` returns at least 2 (container_name + image line). Service block follows same indentation as `telegraf` service.

- [X] T004 [US1/US2] Add two scrape_config blocks to `ansible/roles/monitoring_stack/templates/prometheus.yml.j2` after the application metrics loop: (1) `job_name: 'blackbox-exporter'` self-monitoring job targeting `blackbox-exporter:9115`; (2) `job_name: 'blackbox-https'` probe job with `scrape_interval: 30s`, `metrics_path: /probe`, `params: {module: [https_2xx]}`, Jinja2 loop over `blackbox_https_targets | default([])` in `static_configs`, and 3 `relabel_configs` rules (target→param_target, param_target→instance, address→blackbox-exporter:9115); add comment `# HTTPS endpoint probes — static targets, NOT via monitoring contracts (FR-006, C-007)`

  **Done-condition**: `grep 'blackbox-https' ansible/roles/monitoring_stack/templates/prometheus.yml.j2` returns 1 match. `grep 'blackbox-exporter' ansible/roles/monitoring_stack/templates/prometheus.yml.j2` returns at least 2 matches (both job names). `grep 'FR-006' ansible/roles/monitoring_stack/templates/prometheus.yml.j2` returns 1 match.

**Checkpoint**: After T001–T004, `ansible-playbook --syntax-check ansible/playbooks/monitoring.yml` exits 0. Blackbox exporter container and 5-target probe job defined.

---

## Phase 4: User Story 3 — Brute-Force Detection and Blocking (Priority: P2)

**Goal**: Deploy fail2ban on 3 externally-exposed LXCs (reverse_proxy, nextcloud, jellyfin) with per-host jail configurations (sshd on all; nextcloud auth on nextcloud; jellyfin auth on jellyfin), deploy the hctrdev/fail2ban-prometheus-exporter on each host, and integrate all exporters into Prometheus via monitoring contracts.

**Independent Test**: After deploying `ansible-playbook ansible/playbooks/fail2ban.yml`, SSH to each host and run `fail2ban-client status` — expected jails are listed per host. Run `curl http://<host-ip>:9191/metrics` — `f2b_jail_banned_current` and `f2b_jail_banned_total` metrics returned per jail. Check Prometheus targets page — three `fail2ban-exporter-*` jobs show "UP".

### Implementation for User Story 3

- [X] T005 [P] [US3] Create `ansible/roles/fail2ban/defaults/main.yml` with variables `fail2ban_exporter_version: "0.10.3"`, `fail2ban_exporter_port: 9191`, `fail2ban_exporter_install_dir: "/opt/fail2ban-exporter"`, `fail2ban_exporter_arch: "linux_amd64"` (underscore — matches GitLab release asset naming), `fail2ban_socket_path: "/var/run/fail2ban/fail2ban.sock"`, `fail2ban_sshd_maxretry: 5`, `fail2ban_sshd_bantime: 3600`, `fail2ban_sshd_findtime: 600`; and `ansible/roles/fail2ban/handlers/main.yml` with 3 handlers: `Restart fail2ban` (service state: restarted), `Reload systemd daemon` (systemd daemon_reload: true), `Restart fail2ban exporter` (service state: restarted); follow `ansible/roles/jellyfin/handlers/main.yml` pattern

  **Done-condition**: Both files exist. `grep -c 'fail2ban' ansible/roles/fail2ban/defaults/main.yml` returns at least 5. `grep -c 'name:' ansible/roles/fail2ban/handlers/main.yml` returns 3.

- [X] T006 [P] [US3] Create `ansible/roles/fail2ban/files/filter.d/nextcloud.conf` with `[Definition]` section, `failregex` matching Nextcloud JSON auth failure format: `Login failed.*"remoteAddr":"<HOST>"` (plus optionally `Trusted domain error.*"remoteAddr":"<HOST>"`); and `ansible/roles/fail2ban/files/filter.d/jellyfin.conf` with `[Definition]` section, `failregex` matching `Authentication request for .* has been denied \(IP: "<ADDR>"\)`; both with empty `ignoreregex`

  **Done-condition**: Both files exist with `[Definition]` section headers. `grep '<HOST>\|<ADDR>' ansible/roles/fail2ban/files/filter.d/nextcloud.conf ansible/roles/fail2ban/files/filter.d/jellyfin.conf` returns 2 matches (one per file).

- [X] T007 [P] [US3] Create `ansible/roles/fail2ban/templates/jail.local.j2` — `[DEFAULT]` section with `banaction = iptables-multiport`, then `{% for jail in fail2ban_jails %}` loop generating `[{{ jail.name }}]` sections with `enabled = true`, `filter = {{ jail.filter | default(jail.name) }}`, `logpath = {{ jail.logpath | default('/var/log/auth.log') }}`, `maxretry = {{ jail.maxretry }}`, `bantime = {{ jail.bantime }}`, `findtime = {{ jail.findtime }}`; and `ansible/roles/fail2ban/templates/fail2ban-exporter.service.j2` — systemd unit following `ansible/roles/jellyfin/templates/jellyfin-exporter.service.j2` pattern with `After=network.target fail2ban.service`, `Wants=fail2ban.service`, `ExecStart={{ fail2ban_exporter_install_dir }}/fail2ban_exporter --socket {{ fail2ban_socket_path }} --web.listen-address :{{ fail2ban_exporter_port }}`, `Restart=on-failure`, `RestartSec=5s`, `NoNewPrivileges=true`

  **Done-condition**: `grep '{% for jail in fail2ban_jails %}' ansible/roles/fail2ban/templates/jail.local.j2` returns 1 match. Exporter service file has `[Unit]`, `[Service]`, `[Install]` sections.

- [X] T008 [US3] Create `ansible/roles/fail2ban/tasks/main.yml` — 10-task sequence: (1) `apt install fail2ban` (state: present, cache_valid_time: 3600); (2) deploy custom filter files from `files/filter.d/` to `/etc/fail2ban/filter.d/` via `ansible.builtin.copy`, notify `Restart fail2ban`; (3) deploy `jail.local.j2` → `/etc/fail2ban/jail.local` via `ansible.builtin.template`, notify `Restart fail2ban`; (4) enable/start fail2ban service; (5) create `{{ fail2ban_exporter_install_dir }}` directory; (6) download exporter archive from GitLab releases URL `https://gitlab.com/hctrdev/fail2ban-prometheus-exporter/-/releases/v{{ fail2ban_exporter_version }}/downloads/fail2ban_exporter_{{ fail2ban_exporter_version }}_{{ fail2ban_exporter_arch }}.tar.gz` (note: `v` prefix on version in URL path, underscores in asset filename); (7) extract binary via `ansible.builtin.unarchive remote_src: true` (binary name inside tarball: `fail2ban_exporter`); (8) set `mode: '0755'` on `{{ fail2ban_exporter_install_dir }}/fail2ban_exporter`; (9) deploy `fail2ban-exporter.service.j2` → `/etc/systemd/system/fail2ban-exporter.service`, notify `[Reload systemd daemon, Restart fail2ban exporter]`; (10) enable/start fail2ban-exporter service; follow `ansible/roles/jellyfin/tasks/main.yml` exporter section pattern

  **Done-condition**: File exists. `grep -c 'ansible.builtin' ansible/roles/fail2ban/tasks/main.yml` returns at least 8. Task file includes `apt`, `copy`, `template`, `service`, `file`, `get_url`, `unarchive` module types. `ansible-playbook --syntax-check` of a playbook referencing this role exits 0.

- [X] T009 [US3] Create `ansible/playbooks/fail2ban.yml` — two plays: play 1 `name: "Configure base for fail2ban hosts"`, `hosts: reverse_proxy,nextcloud,jellyfin`, `become: true`, `roles: [lxc_base]`; play 2 `name: "Deploy fail2ban and metrics exporter"`, same hosts, `become: true`, `roles: [fail2ban]`; follow `ansible/playbooks/reverse_proxy.yml` structure

  **Done-condition**: `ansible-playbook --syntax-check -i ansible/inventories/prod/hosts.yml ansible/playbooks/fail2ban.yml` exits 0. `grep -c 'lxc_base\|fail2ban' ansible/playbooks/fail2ban.yml` returns at least 2 (one role per play).

- [X] T010 [US3] Update `ansible/host_vars/reverse_proxy.yml` — append `fail2ban_jails` list with sshd entry `{name: sshd, maxretry: 5, bantime: 3600, findtime: 600}` and add `{job_name: "fail2ban-exporter-reverse-proxy", port: 9191, path: "/metrics"}` to `monitoring_contract.scrape_targets`; update `ansible/host_vars/nextcloud.yml` — append `fail2ban_jails` with sshd + nextcloud entries (nextcloud logpath: `/mnt/nextcloud/data/nextcloud.log`, maxretry: 3, bantime: 86400, findtime: 43200) and add `fail2ban-exporter-nextcloud` scrape target; update `ansible/host_vars/jellyfin.yml` — append `fail2ban_jails` with sshd + jellyfin entries (jellyfin logpath: `/var/log/jellyfin/log_*.log`, maxretry: 3, bantime: 86400, findtime: 43200) and add `fail2ban-exporter-jellyfin` scrape target; retain all existing content in each file

  **Done-condition**: `grep 'fail2ban_jails' ansible/host_vars/reverse_proxy.yml ansible/host_vars/nextcloud.yml ansible/host_vars/jellyfin.yml` returns 3 matches. `grep 'fail2ban-exporter' ansible/host_vars/reverse_proxy.yml ansible/host_vars/nextcloud.yml ansible/host_vars/jellyfin.yml` returns 3 matches. `grep -c 'nextcloud.log' ansible/host_vars/nextcloud.yml` returns 1. `grep -c 'jellyfin/log_' ansible/host_vars/jellyfin.yml` returns 1.

**Checkpoint**: After T005–T010, `ansible-playbook --syntax-check ansible/playbooks/fail2ban.yml` exits 0. Each host_vars file has `fail2ban_jails` and a unique `fail2ban-exporter-*` entry in `monitoring_contract.scrape_targets`.

---

## Phase 5: User Story 4 — Security Overview Dashboard (Priority: P2)

**Goal**: Create a single "Security Overview" Grafana dashboard consolidating all security and availability metrics into 9 panels across 3 sections (Endpoint Health, TLS Certificates, fail2ban Activity), provisioned automatically by the monitoring stack.

**Independent Test**: After deploying `ansible-playbook ansible/playbooks/monitoring.yml`, open Grafana → "Security Overview" dashboard — loads within 5 seconds, 9 panels display across 3 sections with live data. No "No Data" indicators when all services are running.

### Implementation for User Story 4

- [X] T011 [P] [US4] Create `ansible/roles/monitoring_stack/files/grafana/dashboards/security-overview.json` — Grafana 12.x compatible JSON with `uid: "security-overview"`, `title: "Security Overview"`, `schemaVersion: 39`, `editable: false`, datasource `"${DS_PROMETHEUS}"`; **Section 1 — Endpoint Health**: (1) "HTTPS Endpoint Status" stat panel using `probe_success{job="blackbox-https"}` with value mappings 0=Down/red, 1=Up/green; (2) "Probe Response Time" timeseries using `probe_duration_seconds{job="blackbox-https"}` unit `s`; (3) "Probe Success Rate (24h)" gauge using `avg_over_time(probe_success{job="blackbox-https"}[24h]) * 100` unit `percent`; **Section 2 — TLS Certificates**: (4) "Certificate Expiry (days)" bargauge using `(probe_ssl_earliest_cert_expiry{job="blackbox-https"} - time()) / 86400` thresholds red <7, yellow <14, green ≥30; (5) "Certificate Expiry Timeline" timeseries same expr unit `d`; **Section 3 — fail2ban Activity**: (6) "Active Bans by Host" stat panel using `f2b_jail_banned_current`; (7) "Ban Rate (hourly)" timeseries using `increase(f2b_jail_banned_total[1h])`; (8) "Failed Auth Attempts" timeseries using `increase(f2b_jail_failed_total[1h])`; (9) "Jail Status" table using `f2b_config_jail_max_retries`; use `stat`, `timeseries`, `gauge`, `bargauge`, `table` panel types — NO deprecated `graph` panels; follow `ansible/roles/monitoring_stack/files/grafana/dashboards/synology-nas.json` structure

  **Done-condition**: `python3 -c "import json; d=json.load(open('ansible/roles/monitoring_stack/files/grafana/dashboards/security-overview.json')); assert d['uid']=='security-overview'; assert d.get('schemaVersion',0)>=39; print('OK')"` exits 0 and prints "OK". `grep -c '"graph"' ansible/roles/monitoring_stack/files/grafana/dashboards/security-overview.json` returns 0.

**Checkpoint**: After T011, `security-overview.json` is valid and Grafana 12.x compatible. Dashboard deployment is wired in Phase 7 (T014).

---

## Phase 6: User Story 5 — Alert Noise Reduction + Cross-Cutting Alert Rules (Priority: P3)

**Goal**: Create 6 security alert rules and 4 Alertmanager inhibition rules so that root-cause alerts suppress downstream symptom alerts — EndpointDown suppresses TLSCert* and HighProbeLatency for the same endpoint; Fail2banDown suppresses Fail2banHighBanRate and the generic ServiceDown for the same host.

**Independent Test**: After deploying `ansible-playbook ansible/playbooks/monitoring.yml`, check Prometheus alerts page — all 6 security rules show status "inactive" (not "error"). Stop a backend service for 3 minutes — only EndpointDown alert email received, not TLSCertExpiringSoon or HighProbeLatency.

### Implementation for User Story 5

- [X] T012 [P] [US1/US2/US3/US5] Create `ansible/roles/monitoring_stack/files/prometheus/alerts/security_alerts.yml` — static file (NOT a Jinja2 template) following `synology_alerts.yml` structure; single group `security_alerts` with `interval: 30s`; 6 rules using Prometheus template syntax for annotations (NOT Jinja2): (1) `EndpointDown` — `expr: probe_success{job="blackbox-https"} == 0`, `for: 2m`, `severity: critical`, `component: availability`; (2) `TLSCertExpiringSoon` — `expr: (probe_ssl_earliest_cert_expiry{job="blackbox-https"} - time()) / 86400 < 14`, `for: 15m`, `severity: warning`, `component: security`; (3) `TLSCertExpiryCritical` — same expr with `< 7`, `for: 15m`, `severity: critical`; (4) `HighProbeLatency` — `expr: probe_duration_seconds{job="blackbox-https"} > 5`, `for: 5m`, `severity: warning`, `component: performance`; (5) `Fail2banHighBanRate` — `expr: sum by (instance) (increase(f2b_jail_banned_total[1h])) > 10`, `for: 5m`, `severity: warning`, `component: security`; (6) `Fail2banDown` — `expr: up{job=~"fail2ban-exporter.*"} == 0`, `for: 2m`, `severity: critical`, `component: availability`; all alerts include `summary` and `description` annotations using `{{ $labels.instance }}` and `{{ $value }}` template expressions

  **Done-condition**: `grep -c '- alert:' ansible/roles/monitoring_stack/files/prometheus/alerts/security_alerts.yml` returns 6. `python3 -c "import yaml; yaml.safe_load(open('ansible/roles/monitoring_stack/files/prometheus/alerts/security_alerts.yml'))"` exits 0. `grep '{%' ansible/roles/monitoring_stack/files/prometheus/alerts/security_alerts.yml` returns no matches (no Jinja2 syntax).

- [X] T013 [P] [US5] Add 4 inhibition rules to `ansible/roles/monitoring_stack/templates/alertmanager.yml.j2` after existing rules 1–4, using `source_matchers`/`target_matchers`/`equal` syntax (Alertmanager v0.30.0, not deprecated `source_match`): rule 5 with comment `# 5. EndpointDown suppresses TLS cert expiry alerts for unreachable endpoints (FR-020)` — source `alertname = "EndpointDown"`, target `alertname =~ "TLSCert.*"`, equal `['instance']`; rule 6 comment `# 6. EndpointDown suppresses latency alerts for unreachable endpoints (FR-020)` — source `alertname = "EndpointDown"`, target `alertname = "HighProbeLatency"`, equal `['instance']`; rule 7 comment `# 7. Fail2banDown suppresses ban rate alerts when exporter unreachable (FR-021a)` — source `alertname = "Fail2banDown"`, target `alertname = "Fail2banHighBanRate"`, equal `['instance']`; rule 8 comment `# 8. Fail2banDown suppresses generic ServiceDown for fail2ban exporter targets (FR-021b)` — source `alertname = "Fail2banDown"`, target `alertname = "ServiceDown"`, equal `['instance']`; follow exact YAML indentation of existing rules 1–4

  **Done-condition**: `grep -c 'source_matchers:' ansible/roles/monitoring_stack/templates/alertmanager.yml.j2` returns 8 (4 existing + 4 new). `grep -c 'EndpointDown\|Fail2banDown' ansible/roles/monitoring_stack/templates/alertmanager.yml.j2` returns at least 6.

**Checkpoint**: After T012–T013, alertmanager template has 8 inhibition rules and security_alerts.yml has 6 rules. Both wired into monitoring stack in Phase 7 (T014).

---

## Phase 7: Integration Wiring

**Goal**: Wire all new components (blackbox exporter, security alert rules, Security Overview dashboard) into the monitoring_stack role's deploy and verify task files so the existing `monitoring.yml` playbook automatically deploys and verifies all new Tier C components.

### Implementation

- [X] T014 [US1/US2/US3/US4] Update 4 monitoring_stack task files to deploy and verify new components:

  - `ansible/roles/monitoring_stack/tasks/create_directories.yml`: add "Create Blackbox config directory" task using `ansible.builtin.file path: "{{ blackbox_config_path }}" state: directory mode: '0755'` following existing directory creation tasks pattern

  - `ansible/roles/monitoring_stack/tasks/compose_stack.yml`: add (a) "Deploy Blackbox exporter configuration" using `ansible.builtin.template src: blackbox.yml.j2 dest: "{{ blackbox_config_path }}/blackbox.yml" mode: '0644'` with `notify: Restart monitoring stack`; and (b) "Deploy security alert rules" using `ansible.builtin.copy src: prometheus/alerts/security_alerts.yml dest: "{{ prometheus_config_path }}/alerts/security_alerts.yml" mode: '0644'` with `notify: Reload prometheus` — following exact pattern of existing "Deploy infrastructure alert rules" and "Deploy Synology alert rules" tasks

  - `ansible/roles/monitoring_stack/tasks/grafana_provision.yml`: add "Deploy Security Overview dashboard" using `ansible.builtin.copy src: grafana/dashboards/security-overview.json dest: "{{ grafana_dashboards_path }}/security-overview.json" mode: '0644'` following exact pattern of "Deploy Synology NAS dashboard" and "Deploy infrastructure overview dashboard" tasks

  - `ansible/roles/monitoring_stack/tasks/verify.yml`: add `{name: blackbox-exporter}` to the container status check loop; add `{name: blackbox-exporter, port: "{{ blackbox_exporter_port }}"}` to the port listening wait loop; add `{name: blackbox-exporter, url: "http://localhost:{{ blackbox_exporter_port }}/metrics"}` to the HTTP endpoint check loop

  **Done-condition**: `grep 'blackbox' ansible/roles/monitoring_stack/tasks/create_directories.yml` returns 1 match. `grep 'security_alerts' ansible/roles/monitoring_stack/tasks/compose_stack.yml` returns 1 match. `grep 'blackbox' ansible/roles/monitoring_stack/tasks/compose_stack.yml` returns at least 1 match. `grep 'security-overview' ansible/roles/monitoring_stack/tasks/grafana_provision.yml` returns 1 match. `grep -c 'blackbox-exporter' ansible/roles/monitoring_stack/tasks/verify.yml` returns at least 3 (container + port + HTTP check loops).

**Checkpoint**: After T014, `ansible-playbook --syntax-check ansible/playbooks/monitoring.yml` exits 0. All new components are wired into the monitoring_stack role's task orchestration.

---

## Phase 8: Validation

**Purpose**: Mechanically verify all changes for syntax correctness, structural validity, and constitution compliance before declaring the feature complete.

- [X] T015 Syntax-check both playbooks — run `ansible-playbook --syntax-check -i ansible/inventories/prod/hosts.yml ansible/playbooks/fail2ban.yml` AND `ansible-playbook --syntax-check -i ansible/inventories/prod/hosts.yml ansible/playbooks/monitoring.yml`

  **Done-condition**: Both commands exit 0 with no syntax errors reported.

- [X] T016 [P] Validate security alert rules file — run `python3 -c "import yaml; yaml.safe_load(open('ansible/roles/monitoring_stack/files/prometheus/alerts/security_alerts.yml'))"` for YAML validity; confirm `grep -c '- alert:' ansible/roles/monitoring_stack/files/prometheus/alerts/security_alerts.yml` returns 6; verify each alert rule has `expr`, `for`, `labels`, and `annotations` YAML keys

  **Done-condition**: YAML parse exits 0. Grep returns exactly 6. All 6 rules have required keys.

- [X] T017 [P] Validate Security Overview dashboard JSON — run `python3 -c "import json; d=json.load(open('ansible/roles/monitoring_stack/files/grafana/dashboards/security-overview.json')); assert d['uid']=='security-overview', 'wrong uid'; assert d.get('schemaVersion',0)>=39, 'old schema'; print('OK')"` and confirm it exits 0

  **Done-condition**: Python command exits 0 and prints "OK". No assertion errors about uid or schemaVersion.

- [X] T018 [P] Verify no plaintext secrets in new/modified files — run `rg -i 'password|secret|token|api.key' ansible/roles/fail2ban/ ansible/roles/monitoring_stack/files/prometheus/alerts/security_alerts.yml ansible/roles/monitoring_stack/files/grafana/dashboards/security-overview.json ansible/roles/monitoring_stack/templates/blackbox.yml.j2`; any matches must be in Jinja2 variable references (`{{ ... }}`), Prometheus template expressions (`{{ $labels...`), or annotation text — not plaintext credential values; verify vault files are unmodified via `git diff --name-only -- ansible/group_vars/*/vault.yml`

  **Done-condition**: No plaintext credential values found. `git diff --name-only -- ansible/group_vars/*/vault.yml` returns empty (vault files unmodified).

- [X] T019 [P] Verify monitoring contract port and job-name uniqueness — confirm port 9191 (fail2ban-exporter) does not conflict with existing ports (9100=node_exporter, 9180=caddy, 8081/8082=immich, 9618=adguard, 9205=nextcloud, 9594=jellyfin, 9090=prometheus, 3000=grafana, 9273=telegraf, 9093=alertmanager); confirm port 9115 (blackbox-exporter) does not conflict; confirm 3 new job names (`fail2ban-exporter-reverse-proxy`, `fail2ban-exporter-nextcloud`, `fail2ban-exporter-jellyfin`) are unique across all monitoring contracts

  **Done-condition**: Port 9191 and 9115 appear only in new fail2ban/blackbox config files. `grep 'fail2ban-exporter' ansible/host_vars/*.yml` returns exactly 3 matches. No job name collisions across `ansible/host_vars/*.yml`.

- [X] T020 Verify file manifest — run `git diff --name-only` and confirm output includes the 23 expected files (11 created + 3 host_vars + 9 modifications); verify 4 files are unchanged: `ansible/host_vars/immich.yml`, `ansible/host_vars/adguard.yml`, `ansible/playbooks/monitoring.yml`, `scripts/lab/service-scope-allowlist.json`

  **Done-condition**: `git diff --name-only -- ansible/host_vars/immich.yml ansible/host_vars/adguard.yml ansible/playbooks/monitoring.yml scripts/lab/service-scope-allowlist.json` returns empty (these files must not change).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: N/A — Features 040 + 041 prerequisite
- **Phase 2 (Foundational)**: N/A — No shared blockers
- **Phase 3 (US-1/US-2, P1)**: No dependencies — can start immediately
  - T001, T002 in parallel (different files)
  - T003, T004 after T002 (need variable names)
- **Phase 4 (US-3, P2)**: Independent of Phase 3 — can run fully in parallel
  - T005, T006, T007 in parallel (different files)
  - T008 after T005+T006+T007; T009 after T008; T010 after T005
- **Phase 5 (US-4, P2)**: Independent — can run in parallel with Phases 3+4
  - T011 has no dependencies
- **Phase 6 (US-5, P3)**: Independent — can run in parallel with Phases 3+4+5
  - T012, T013 in parallel (different files)
- **Phase 7 (Wiring)**: Depends on T001+T002 (blackbox template+vars), T011 (dashboard JSON), T012 (security_alerts.yml)
  - T014 after all above content-creation tasks
- **Phase 8 (Validation)**: Depends on ALL Phases 3–7; T016–T019 can run in parallel; T015 and T020 require all code tasks done

### Dependency Graph

```
# Phase 3 (US-1/US-2):
[T001 ‖ T002]
T002 → T003
T002 → T004

# Phase 4 (US-3):
[T005 ‖ T006 ‖ T007]
[T005 + T006 + T007] → T008 → T009
T005 → T010

# Phase 5 (US-4):
T011  (no dependencies)

# Phase 6 (US-5 + cross-cutting):
[T012 ‖ T013]  (no dependencies)

# Phase 7 (Wiring):
[T001 + T002 + T011 + T012] → T014

# Phase 8 (Validation):
[T001–T014] → T015
T012 → T016
T011 → T017
[T001–T014] → T018
[T002 + T010] → T019
[T001–T014] → T020
```

### Optimal Implementation Order

```
Batch 1 (all parallel — 8 tasks):
  T001, T002, T005, T006, T007, T011, T012, T013

Batch 2 (after their dependencies):
  T003 (after T002)
  T004 (after T002)
  T008 (after T005+T006+T007)
  T010 (after T005)

Batch 3 (after their dependencies):
  T009 (after T008)
  T014 (after T001+T002+T011+T012 — all from Batch 1)

Batch 4 (validation — after all code):
  T015, T016, T017, T018, T019, T020
```

---

## Parallel Execution Examples

### Three Independent Tracks (Phases 3, 4, 5+6)

```bash
# Track A: Blackbox infrastructure (US-1/US-2)
T001: "Create blackbox.yml.j2"
T002: "Add blackbox vars to defaults + group_vars"
  → T003: "Add blackbox-exporter to docker-compose.yml.j2"
  → T004: "Add blackbox scrape configs to prometheus.yml.j2"

# Track B: fail2ban infrastructure (US-3)
T005: "Create fail2ban defaults + handlers"
T006: "Create fail2ban filter files (nextcloud + jellyfin)"
T007: "Create fail2ban templates (jail.local.j2 + exporter.service.j2)"
  → T008: "Create fail2ban tasks/main.yml"
    → T009: "Create fail2ban.yml playbook"
T010: "Update host_vars for 3 fail2ban hosts" (after T005)

# Track C: Alert rules + dashboard (US-4/US-5)
T011: "Create security-overview.json dashboard"
T012: "Create security_alerts.yml with 6 alert rules"
T013: "Add 4 inhibition rules to alertmanager.yml.j2"
```

### Within Phase 4 (fail2ban role)

```bash
# Launch all role scaffolding in parallel:
T005: "fail2ban defaults/main.yml + handlers/main.yml"
T006: "filter.d/nextcloud.conf + filter.d/jellyfin.conf"
T007: "templates/jail.local.j2 + templates/fail2ban-exporter.service.j2"

# Then sequentially:
T008: "tasks/main.yml" (needs T005+T006+T007 complete)
T009: "playbooks/fail2ban.yml" (needs T008 complete)
```

---

## Implementation Strategy

### MVP First (Phase 3 Only — US-1 + US-2)

1. Complete T001–T004: Blackbox exporter infrastructure
2. Partially complete T014: Add only the blackbox-related tasks (create_directories + compose_stack blackbox config + verify.yml checks)
3. **STOP and VALIDATE**: Deploy monitoring playbook. Verify blackbox-exporter container running. Check 5 HTTPS probes return `probe_success=1`. Check TLS cert expiry metric shows >60 days.
4. P1 user stories (US-1 + US-2) complete for endpoint probing and cert monitoring (SC-001, SC-002, SC-003, SC-004).

### Incremental Delivery

1. Phase 3 (blackbox) + partial T014 → Deploy + validate → SC-001, SC-002, SC-003, SC-004 ✓
2. Phase 4 (fail2ban) → Deploy + validate → SC-005, SC-006 ✓
3. Phases 5+6 (alerts, inhibitions, dashboard) + complete T014 → Deploy + validate → SC-007, SC-008 ✓
4. Phase 8 (validation) → Confirm SC-009, SC-010, SC-011, SC-012 ✓

---

## File Manifest

### Files CREATED (11)

| File | Task | Story |
|------|------|-------|
| `ansible/roles/monitoring_stack/templates/blackbox.yml.j2` | T001 | US-1/US-2 |
| `ansible/roles/fail2ban/defaults/main.yml` | T005 | US-3 |
| `ansible/roles/fail2ban/handlers/main.yml` | T005 | US-3 |
| `ansible/roles/fail2ban/files/filter.d/nextcloud.conf` | T006 | US-3 |
| `ansible/roles/fail2ban/files/filter.d/jellyfin.conf` | T006 | US-3 |
| `ansible/roles/fail2ban/templates/jail.local.j2` | T007 | US-3 |
| `ansible/roles/fail2ban/templates/fail2ban-exporter.service.j2` | T007 | US-3 |
| `ansible/roles/fail2ban/tasks/main.yml` | T008 | US-3 |
| `ansible/playbooks/fail2ban.yml` | T009 | US-3 |
| `ansible/roles/monitoring_stack/files/prometheus/alerts/security_alerts.yml` | T012 | US-1/US-2/US-3/US-5 |
| `ansible/roles/monitoring_stack/files/grafana/dashboards/security-overview.json` | T011 | US-4 |

### Files MODIFIED (12)

| File | Task | Story | Change |
|------|------|-------|--------|
| `ansible/roles/monitoring_stack/defaults/main.yml` | T002 | US-1/US-2 | Add blackbox_exporter_version, port, config_path |
| `ansible/group_vars/monitoring/vars.yml` | T002 | US-1/US-2 | Add blackbox vars + blackbox_https_targets list (5 URLs) |
| `ansible/roles/monitoring_stack/templates/docker-compose.yml.j2` | T003 | US-1/US-2 | Add blackbox-exporter container service block |
| `ansible/roles/monitoring_stack/templates/prometheus.yml.j2` | T004 | US-1/US-2 | Add blackbox-exporter + blackbox-https scrape jobs |
| `ansible/host_vars/reverse_proxy.yml` | T010 | US-3 | Add fail2ban_jails (sshd) + fail2ban-exporter scrape target |
| `ansible/host_vars/nextcloud.yml` | T010 | US-3 | Add fail2ban_jails (sshd+nextcloud) + fail2ban-exporter scrape target |
| `ansible/host_vars/jellyfin.yml` | T010 | US-3 | Add fail2ban_jails (sshd+jellyfin) + fail2ban-exporter scrape target |
| `ansible/roles/monitoring_stack/templates/alertmanager.yml.j2` | T013 | US-5 | Add inhibition rules 5–8 |
| `ansible/roles/monitoring_stack/tasks/create_directories.yml` | T014 | US-1/US-2 | Add blackbox config directory creation |
| `ansible/roles/monitoring_stack/tasks/compose_stack.yml` | T014 | US-1/US-2/US-3 | Add blackbox config template + security alerts copy tasks |
| `ansible/roles/monitoring_stack/tasks/grafana_provision.yml` | T014 | US-4 | Add security-overview.json copy task |
| `ansible/roles/monitoring_stack/tasks/verify.yml` | T014 | US-1/US-2 | Add blackbox-exporter to 3 verification check loops |

### Files UNCHANGED (verified in T020)

| File | Reason |
|------|--------|
| `ansible/roles/monitoring_stack/templates/service_alerts.yml.j2` | Service alert rules auto-aggregated from contracts; no changes needed |
| `ansible/roles/monitoring_stack/tasks/provision_dashboards.yml` | Service dashboard auto-discovery unchanged; security-overview is a built-in dashboard |
| `ansible/roles/monitoring_stack/tasks/main.yml` | Task orchestration unchanged; compose_stack.yml handles new deployments |
| `ansible/roles/monitoring_stack/handlers/main.yml` | Existing handlers (Reload prometheus, Restart monitoring stack) sufficient |
| `ansible/playbooks/monitoring.yml` | Already includes monitoring_stack role; no playbook changes needed |
| `ansible/host_vars/immich.yml` | Immich contract unchanged; must not regress |
| `ansible/host_vars/adguard.yml` | AdGuard contract unchanged; must not regress |
| `scripts/lab/service-scope-allowlist.json` | All affected services already in allowlist |

---

## Constitution Compliance

| # | Principle | Status | Evidence |
|---|-----------|--------|----------|
| I | Spec-Driven Workflow | ✅ PASS | All 20 tasks trace to FRs and user stories in spec.md. tasks.md lives at `specs/042-monitoring-tier-c/tasks.md`. |
| II | Secrets Policy | ✅ PASS | T018 mechanically verifies no plaintext secrets. fail2ban exporter reads local socket — no credentials. Existing SMTP/Grafana secrets remain in vault, unmodified. |
| III | Separation of Concerns | ✅ PASS | Terraform unchanged — all 3 fail2ban LXCs already exist. Ansible owns all configuration: packages, jail configs, exporter binaries, monitoring stack config. |
| IV | Code Economy (YAGNI) | ✅ PASS | New `fail2ban` role justified by 3 concrete consumers. `security_alerts.yml` is a static file (no template abstraction where unnecessary). Jail list parameterized because it genuinely varies per host. No wrapper layers. |
| V | Dual-Provisioning Parity | ✅ PASS | `fail2ban.yml` playbook runnable from both CI (self-hosted runner) and developer laptop. All affected services already in `service-scope-allowlist.json`. No new CI-only paths. |

---

## Requirement Traceability

| Requirement | Task(s) | Done-Condition |
|-------------|---------|----------------|
| FR-001 (HTTPS probe on monitoring host) | T001, T003 | blackbox-exporter container in docker-compose with port 9115 |
| FR-002 (probe in Docker Compose stack) | T003 | blackbox-exporter service block follows Telegraf pattern |
| FR-003 (5 probe endpoints) | T002 | `blackbox_https_targets` has 5 URLs in group_vars/monitoring/vars.yml |
| FR-004 (probe metrics: success, status, cert, duration, DNS) | T001, T004 | `https_2xx` module + Prometheus scrape with relabeling exposes all 5 metric types |
| FR-005 (follow redirects) | T001 | `follow_redirects: true` in blackbox.yml.j2 `https_2xx` module |
| FR-006 (static scrape config, not monitoring contracts) | T004 | Blackbox scrape uses `static_configs` with Jinja2 loop; comment references FR-006 and C-007 |
| FR-007 (cert expiry metric in days) | T012 | TLSCertExpiringSoon alert expr: `(probe_ssl_earliest_cert_expiry - time()) / 86400` |
| FR-008 (14d warning, 7d critical, 15m sustained) | T012 | Two TLS alert rules with `< 14`/`< 7` thresholds and `for: 15m` |
| FR-009 (fail2ban on 3 hosts) | T009, T010 | Playbook targets 3 hosts; host_vars define `fail2ban_jails` |
| FR-010 (sshd jail on all 3) | T010 | All 3 host_vars files have sshd jail entry |
| FR-011 (nextcloud jail) | T006, T010 | nextcloud.conf filter + nextcloud jail with `/mnt/nextcloud/data/nextcloud.log` in nextcloud host_vars |
| FR-012 (jellyfin jail, SHOULD) | T006, T010 | jellyfin.conf filter + jellyfin jail with `/var/log/jellyfin/log_*.log` in jellyfin host_vars |
| FR-013 (fail2ban via Ansible) | T008 | fail2ban role with `apt install` + systemd service management |
| FR-014 (fail2ban metrics exporter) | T005, T007, T008 | hctrdev exporter binary + systemd service deploying via get_url+unarchive |
| FR-015 (exporter via monitoring contracts) | T010 | `fail2ban-exporter-*` entries in `monitoring_contract.scrape_targets` in host_vars |
| FR-016 (exporter accessible from monitoring host) | T005, T010 | Port 9191 in defaults; scrape target entries reference host IP:9191 |
| FR-017 (dedicated security alert rules file) | T012, T014 | `security_alerts.yml` file + copy task in `compose_stack.yml` |
| FR-018 (6 alert rules with specified conditions) | T012 | 6 rules with correct PromQL expr, `for`, severity per data-model.md |
| FR-019 (alerts via existing email channel) | T012 | No new receivers in alertmanager; rules inherit default email route |
| FR-020 (EndpointDown suppresses TLSCert + HighProbeLatency) | T013 | Inhibit rules 5+6 in alertmanager.yml.j2 |
| FR-021 (Fail2banDown suppresses HighBanRate + ServiceDown) | T013 | Inhibit rules 7+8 in alertmanager.yml.j2 |
| FR-022 (inhibition rules follow existing pattern) | T013 | Rules use `source_matchers`/`target_matchers`/`equal`, identical to rules 1–4 |
| FR-023 (built-in Security Overview dashboard) | T011, T014 | security-overview.json + copy task in grafana_provision.yml |
| FR-024 (9 dashboard panels in 3 sections) | T011 | Dashboard JSON has 9 panels: 3 endpoint health, 2 TLS, 4 fail2ban |
| FR-025 (Grafana 12.x compatible) | T011 | `schemaVersion: 39`, no deprecated `graph` panel types |
| FR-026 (all via Ansible) | T008, T009, T014 | fail2ban role + playbook; monitoring_stack task updates |
| FR-027 (idempotent) | T008, T014 | `apt state: present`, `service enabled: true state: started`, `template`/`copy` modules are idempotent |
| FR-028 (no secrets in repo) | T018 | Validation task verifies no plaintext secrets in new/modified files |
| FR-029 (dual-provisioning parity) | T009 | fail2ban.yml runnable from CI and laptop; all services in `service-scope-allowlist.json` |
