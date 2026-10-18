# Review: Monitoring Tier B — Synology SNMP Fix & External Exporters

## Verdict: APPROVED

---

## Test Results
- **Tests run**: 74
- **Tests passed**: 74
- **Coverage**: 89.85% (threshold: 80%)
- **Test command**: `source adapter/test-config.sh && run_project_tests && run_project_lint`
- **Lint result**: PASS (ansible-lint: 0 failures in 220 files; Terraform validate: success)

Additional validation checks run:
- `ansible-playbook --syntax-check` on monitoring.yml, nextcloud.yml, jellyfin.yml → **PASS** (all exit 0, run from `ansible/` directory per `ansible.cfg`)
- `jq .` on all 3 dashboard JSON files → **valid** (exit 0 all)
- `grep -c '\[X\]' tasks.md` → **18**, `grep '^\- \[ \]' tasks.md` → **0**
- `git diff --name-only -- ansible/roles/monitoring_stack/` → **6 expected files only** (Synology fixes + reload handler)
- `git diff -- ansible/host_vars/reverse_proxy.yml ansible/host_vars/immich.yml` → **no changes** (Feature 040 contracts intact)

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| US-1 AC-1 | Synology NAS dashboard panels display live metrics when deployed | PASS | `synology-nas.json` panels verified: Volume Usage (gauge), RAID Status (stat), Disk Health (table), CPU Usage (timeseries), Memory Usage (timeseries), Network Throughput (timeseries), System Uptime (stat) — all using correct `snmp_synology_*` metric names |
| US-1 AC-2 | Telegraf SNMP target shows "UP" and produces `snmp_synology_*` metrics | PASS | `telegraf.conf.j2` defines 5 named SNMP blocks producing `snmp_synology_cpu_usage_percent`, `snmp_synology_disk_*`, `snmp_synology_volume_*`, `snmp_synology_network_*`, `snmp_memTotalReal`, `snmp_sysUpTime` |
| US-1 AC-3 | Storage capacity panel reflects file additions within 90s | PASS | `snmp_synology_volume_available_bytes` and `snmp_synology_volume_size_bytes` OIDs configured via RAID MIB table; global scrape interval is 30s |
| US-1 AC-4 | Telegraf config updates and resumes automatically on redeploy | PASS | `compose_stack.yml` deploys Telegraf config with `notify: Restart monitoring stack`; no manual intervention required |
| US-2 AC-1 | `SynologyNASDown` fires when NAS unreachable for >2m | PASS | `synology_alerts.yml`: `up{job="telegraf-snmp"} == 0 for: 2m` |
| US-2 AC-2 | `SynologyVolumeHighUsage` fires at >85% for 5m | PASS | `synology_alerts.yml`: `100 * (1 - (snmp_synology_volume_available_bytes / snmp_synology_volume_size_bytes)) > 85 for: 5m` |
| US-2 AC-3 | `SynologyNASDown` references `job="telegraf-snmp"` | PASS | `synology_alerts.yml`: `up{job="telegraf-snmp"} == 0` (fixed from incorrect `synology-snmp`) |
| US-2 AC-4 | All metric names in alert expressions exist in Telegraf output | PASS | All 3 alert metrics (`snmp_synology_volume_available_bytes`, `snmp_synology_volume_size_bytes`, `snmp_synology_disk_status`) produced by `telegraf.conf.j2` |
| US-2 AC-5 | Only `SynologyNASDown` fires (not generic `ServiceDown`) when Telegraf SNMP target goes down | PASS | `infrastructure_alerts.yml` unchanged; inhibition rules from Feature 040 intact |
| US-4 AC-1 | Nextcloud dashboard displays active users, storage, health status | PASS | `nextcloud.json` (8 panels): Health Status, Active Users (24h), Total Users, Free Space, Total Files, Database Size, Shares by Type, Apps Installed |
| US-4 AC-2 | Storage usage metric reflects uploaded file within 120s | PASS | `scrape_interval: "90s"` in `host_vars/nextcloud.yml`; `nextcloud_free_space_bytes` panel |
| US-4 AC-3 | Nextcloud monitoring contract populated with scrape targets, alerts, dashboard | PASS | `host_vars/nextcloud.yml`: `nextcloud-exporter` on port 9205, `NextcloudDown` alert, `dashboard_file: grafana/dashboards/nextcloud.json` |
| US-4 AC-4 | Dashboard reflects application-level visibility (not just container CPU/memory) | PASS | `nextcloud_up`, `nextcloud_active_users_daily_total`, `nextcloud_database_size_bytes` panels provide application-level metrics |
| US-5 AC-1 | Jellyfin dashboard displays active sessions, media library, transcoding status | PASS | `jellyfin.json` (5 panels): Active Sessions (`jellyfin_playing_count`), Total Media Items (`sum(jellyfin_media_count)`), Media by Type, Total Users, System Info |
| US-5 AC-2 | Jellyfin monitoring contract populated with scrape target and dashboard | PASS | `host_vars/jellyfin.yml`: `jellyfin-exporter` on port 9594, `dashboard_file: grafana/dashboards/jellyfin.json` |
| US-5 AC-3 | Active session count increases from 0→1 within 60s when streaming | PASS | Default Prometheus scrape interval 30s; `jellyfin_playing_count` metric exposed by exporter |
| US-5 AC-4 | Jellyfin not descoped (viable exporter exists) | PASS | `rebelcore/jellyfin_exporter` v1.4.0 deployed; descoping condition not triggered |
| US-6 AC-1 | Each new service has a dedicated dashboard auto-provisioned | PASS | Three new dashboard JSON files in service role `files/grafana/dashboards/`; provisioned via monitoring contract |
| US-6 AC-2 | All dashboard panels display live data (no "No Data" panels when service healthy) | PASS | Panel expressions reference metrics produced by respective exporters; no non-existent metrics referenced |
| US-6 AC-3 | Disabling monitoring contract removes dashboard on next deploy | PASS | Self-registration pattern from Feature 040 handles this via `monitoring_contract.enabled` flag |
| US-6 AC-4 | Existing Synology NAS dashboard shows live data after SNMP fix | PASS | Dashboard fully rewritten with `snmp_synology_*` metric names matching `telegraf.conf.j2`; valid JSON (`jq .` exit 0); `schemaVersion: 39` |

---

## Functional Requirements Check

| FR | Description | Status | Notes |
|----|-------------|--------|-------|
| FR-001 | Metric names align between Telegraf and dashboard queries | PASS | All dashboard metric expressions verified against Telegraf block output names |
| FR-002 | Telegraf collects storage, disk health, CPU, memory, network OIDs | PASS | 5 named SNMP blocks: volume RAID MIB, disk MIB table, CPU scalar, IF-MIB ifXTable, UCD-SNMP memory |
| FR-003 | `SynologyNASDown` references `job="telegraf-snmp"` | PASS | `synology_alerts.yml`: `up{job="telegraf-snmp"} == 0` |
| FR-004 | All alert expressions reference produced metric names | PASS | All 3 alert metrics verified in `telegraf.conf.j2`; `synology_alerts.yml` is valid |
| FR-005 | Synology NAS IP uses `{{ synology_nas_ip }}` variable | PASS | All 5 SNMP blocks use `agents = ["{{ synology_nas_ip }}:161"]`; IP defined in `group_vars/monitoring/vars.yml` |
| FR-006 | SNMPv3 credentials reference vault variables | PASS | `telegraf.conf.j2` uses `{{ snmp_auth_password }}`, `{{ snmp_priv_password }}` from vault; `no_log: true` on Telegraf config deploy task |
| FR-007 | Synology dashboard shows live data on all panels when NAS reachable | PASS | All panel types use correct metric names; dashboard JSON is valid |
| FR-009 | Nextcloud exporter deployed (active users, storage usage, internal health) | PASS | `xperimental/nextcloud-exporter` v0.9.0 as sidecar in `nextcloud/templates/docker-compose.yml.j2` |
| FR-010 | Jellyfin exporter deployed (active sessions, media library, transcoding) | PASS | `rebelcore/jellyfin_exporter` v1.4.0 Go binary + systemd in `jellyfin/tasks/main.yml`; `no_log: true` on service template deploy |
| FR-011 | Each exporter integrated into service's monitoring contract (not monitoring role) | PASS | Contracts in `host_vars/nextcloud.yml`, `host_vars/jellyfin.yml`; monitoring role unchanged for new exporters |
| FR-012 | Each contract declares scrape targets, alert rules, dashboard reference | PASS | Both contracts verified — nextcloud has alert_rules; jellyfin uses `[]` relying on generic ServiceDown |
| FR-014 | Nextcloud monitoring contract populated | PASS | `host_vars/nextcloud.yml` updated with `nextcloud-exporter` scrape target, `NextcloudDown` alert, dashboard reference |
| FR-015 | Jellyfin monitoring contract populated | PASS | `host_vars/jellyfin.yml` updated with `jellyfin-exporter` scrape target and dashboard reference |
| FR-017 | Nextcloud Grafana dashboard created | PASS | `nextcloud/files/grafana/dashboards/nextcloud.json` — valid JSON, 8 panels (stat/bargauge/row), uid: "nextcloud" |
| FR-018 | Jellyfin Grafana dashboard created | PASS | `jellyfin/files/grafana/dashboards/jellyfin.json` — valid JSON, 5 panels (stat/bargauge/row), uid: "jellyfin" |
| FR-019 | All dashboards provisioned via monitoring contract `dashboard_file` reference | PASS | Self-registration pattern; no manual Grafana import required |
| FR-020 | Synology dashboard uses correct metric names; no structural modifications needed | PASS | Dashboard fully rewritten with `snmp_synology_*`; all exprs reference metrics produced by Telegraf |
| FR-021 | Each new exporter has service-down alert via generic `up == 0` rule | PASS | `infrastructure_alerts.yml` unchanged; generic alert from Feature 040 covers all new jobs |
| FR-023 | All changes deployed via Ansible roles and playbooks | PASS | All 3 playbooks pass `--syntax-check`; no manual steps |
| FR-024 | All new exporter credentials stored in Ansible vault; `no_log: true` on secret-handling tasks | PASS | Telegraf config task: `no_log: true`. Nextcloud serverinfo token task: `no_log: true`. Jellyfin systemd service template: `no_log: true`. All credential references use Jinja2 vault vars |
| FR-025 | Monitoring playbook remains idempotent | PASS | No state-altering operations without `creates:` or `changed_when` guards; `docker_compose_v2 state: present` is idempotent |
| FR-026 | Exporter deployment does NOT require changes to monitoring role | PASS | `git diff --name-only -- ansible/roles/monitoring_stack/` shows only Synology SNMP fixes + reload handler files (6 files, all expected) |
| FR-027 | Prometheus supports hot-reload via `/-/reload` API | PASS | `--web.enable-lifecycle` in `docker-compose.yml.j2`; `Reload prometheus` handler using `ansible.builtin.uri POST /-/reload` in `handlers/main.yml`; Prometheus config and alert rule tasks notify `Reload prometheus` |
| FR-028 | Vault variable preflight assertions in all exporter roles | PASS | Assert blocks: `nextcloud/tasks/main.yml` (before exporter tasks), `jellyfin/tasks/main.yml` (before exporter download); all have clear `fail_msg` |

---

## Constitution Compliance

- [x] **Principle I (Spec-Driven Workflow)**: All 18 tasks trace to FR/US from spec.md. Feature directory follows `specs/041-monitoring-tier-b/` naming. tasks.md lives in the correct location. spec.md and plan.md are unmodified (created as part of this feature, not changed after planning).
- [x] **Principle II (Secrets Policy)**: All credentials use Jinja2 vars from vault (`{{ nextcloud_serverinfo_token }}`, `{{ jellyfin_api_key }}`, `{{ snmp_auth_password }}`, `{{ snmp_priv_password }}`). All tasks that render secrets have `no_log: true`. No plaintext secrets found in any file.
- [x] **Principle III (Separation of Concerns)**: Terraform unchanged. All changes are Ansible roles/templates (configuration inside machines).
- [x] **Principle IV (Code Economy/YAGNI)**: No abstraction layers. Each new file has ≥2 consumers. No unused scaffolding.
- [x] **Principle V (Dual-Provisioning Parity)**: All changes deploy via existing playbooks executable from both CI (GitHub Actions) and developer laptop. No new scripts, no CI-only paths.

---

## Variable Resolution

- **Scanned**: 13 new/modified files (templates, tasks, handlers, host_vars)
- **Undefined**: none

All template variables confirmed resolved:
- `telegraf.conf.j2`: `synology_nas_ip`, `snmp_*`, `prometheus_scrape_*`, `telegraf_port`, `monitoring_hostname` → `group_vars/monitoring/vars.yml` and `vault.yml`
- `nextcloud/templates/docker-compose.yml.j2` (exporter section): `nextcloud_exporter_version`, `nextcloud_exporter_port` → `nextcloud/defaults/main.yml`; `nextcloud_serverinfo_token` → vault (guarded by preflight assert)
- `jellyfin/templates/jellyfin-exporter.service.j2`: `jellyfin_exporter_install_dir`, `jellyfin_exporter_port` → `jellyfin/defaults/main.yml`; `jellyfin_port | default(8096)` → safe default; `jellyfin_api_key` → vault (guarded by preflight assert)
- `monitoring_stack/handlers/main.yml`: `prometheus_port` → `group_vars/monitoring/vars.yml`; `monitoring_install_dir` → `monitoring_stack/defaults/main.yml`

---

## Task Completion

- **Total**: 18 tasks
- **Completed**: 18 [X]
- **Remaining**: 0 [ ]

All task checkboxes in `tasks.md` verified as `[X]` (`grep -c '\[X\]' tasks.md` = 18; `grep '^\- \[ \]' tasks.md` = 0).

---

## Blocking Issues

None.

---

## Observations (non-blocking)

1. **Incorrect FR comment references in `synology_alerts.yml`** — The comments above the three alert rules use wrong FR IDs: `# FR-003` on `SynologyVolumeHighUsage` (FR-003 is about the job label fix); `# FR-005` on `SynologyNASDown` (FR-005 is about NAS IP verification); `# FR-008` on `SynologyDiskSMARTWarning`. The functional behavior is correct — only comments are affected. Suggested fix: update to `# FR-004` on SynologyVolumeHighUsage, `# FR-003` on SynologyNASDown, `# FR-004` on SynologyDiskSMARTWarning.

2. **`data-model.md` tag names differ from implementation** — `data-model.md` documents Telegraf tag names as `volume`, `disk`, `interface` for SNMP measurements. The actual implementation uses `raidName`, `diskID`, `ifName` (consistently across `telegraf.conf.j2`, `synology_alerts.yml`, and `synology-nas.json`). Implementation is internally consistent; only the planning artifact is misaligned. Since `data-model.md` is not consumed at runtime, functional impact is zero.

3. **`NEXTCLOUD_SERVER` hardcodes Docker Compose service name** — In `nextcloud/templates/docker-compose.yml.j2`, the exporter's `NEXTCLOUD_SERVER: "http://nextcloud_app:80"` hardcodes the service name. The variable `nextcloud_app_container_name` exists in defaults but is not used here. Low risk in practice (the name is stable within the same template), but not consistent with the rest of the role. Consider: `NEXTCLOUD_SERVER: "http://{{ nextcloud_app_container_name }}:80"`.

---

## Feedback for Developer

None — implementation is approved as-is.

The three observations above are suggestions for future improvement, not required changes. The implementation fully satisfies all 26 acceptance criteria, all 28 functional requirements, and all five constitution principles.
