# Tasks: Monitoring Tier B — Synology SNMP Fix & External Exporters

**Input**: Design documents from `/specs/041-monitoring-tier-b/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/monitoring-contract.schema.yml

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US4)
- Include exact file paths in descriptions

## Summary

- **Total tasks**: 18
- **Estimated complexity**: Medium
- **Parallel tracks**: 3 independent tracks (Phases 3, 5 and 6 run concurrently; Phase 6B partially parallel; validation is a serial gate)
- **Task count by story**: US-1: 2, US-2: 1, US-4: 3, US-5: 4, US-6: 4 (cross-cutting), Cross-cutting: 2 (T021 reload, T022 vault assertions), Validation: 6

---

## Phase 1: Setup

Not applicable. Feature 040 (Monitoring Overhaul) is a mandatory prerequisite — Prometheus, Grafana, Telegraf, Alertmanager, and the self-registration pattern (monitoring contracts in host_vars) must already be deployed. Verify the prerequisite is met before beginning Phase 3.

---

## Phase 2: Foundational

Not applicable. Each user story is independently implementable at the file level. No shared infrastructure needs to be built before any story can begin. US-2 depends on US-1's metric names (see dependency graph), but there are no cross-story foundation blockers.

---

## Phase 3: User Stories 1 & 2 — Synology SNMP Pipeline Fix (Priority: P1) 🎯 MVP

**Goal**: Restore the broken Synology SNMP metrics pipeline so `snmp_synology_*` metrics flow from Telegraf to Prometheus, and all three Synology alert rules evaluate against actual metric names with the correct Prometheus job label.

**Independent Test**: Deploy `ansible-playbook ansible/playbooks/monitoring.yml`. Open Grafana → Synology NAS Health dashboard. All panels (storage capacity, disk health, CPU, memory, network) display live data with no "No Data" panels. On the Prometheus alerts page: `SynologyNASDown` references `job="telegraf-snmp"` and all three Synology rules show status "inactive" (not "error").

### Implementation

- [X] T001 [US1] Rewrite `ansible/roles/monitoring_stack/templates/telegraf.conf.j2` SNMP inputs section — replace single `[[inputs.snmp]]` block with five named blocks: `name="snmp_synology_cpu"` (scalar cpuUtilization OID `1.3.6.1.4.1.6574.1.7.1`, field `usage_percent`); `name="snmp_synology_disk"` (table query disk MIB `1.3.6.1.4.1.6574.2.1.1`, tag `diskID` `.2`, fields `status` `.5` and `temperature_celsius` `.6`); `name="snmp_synology_volume"` (table query RAID MIB `1.3.6.1.4.1.6574.3.1.1`, tag `raidName` `.2`, fields `status` `.3`, `available_bytes` `.4`, `size_bytes` `.5`); `name="snmp_synology_network"` (table query IF-MIB ifXTable `1.3.6.1.2.1.31.1.1.1`, tag `ifName` `.1`, fields `rx_bytes` `.6`, `tx_bytes` `.10`, `speed_mbps` `.15`); default `snmp` block retaining existing UCD-SNMP memory fields (`memTotalReal`, `memAvailReal`, `memBuffer`, `memCached`) and system fields (`sysDescr`, `sysUpTime`, `sysName`) — remove old scalar disk/RAID/CPU-counter OIDs (`disk1Status`, `disk1Temp`, `raid1Status`, `ssCpuRawUser`, etc.)
- [X] T002 [US2] Fix all three alert rules in `ansible/roles/monitoring_stack/files/prometheus/alerts/synology_alerts.yml` — (1) `SynologyNASDown`: change `up{job="synology-snmp"}` to `up{job="telegraf-snmp"}`; (2) `SynologyVolumeHighUsage`: update to use `snmp_synology_volume_available_bytes` and `snmp_synology_volume_size_bytes` with `raidName` label, expression `100 * (1 - (available / size)) > 85`; (3) `SynologyDiskSMARTWarning`: replace string regex on `status` label with integer comparison `snmp_synology_disk_status != 1`, update annotation to reference `{{ $labels.diskID }}` (depends on T001)
- [X] T003 [P] [US1] [US6] Rewrite `ansible/roles/monitoring_stack/files/grafana/dashboards/synology-nas.json` — replace malformed concatenated JSON with single valid object: `uid: "synology-nas-health"`, `schemaVersion: 39`, `DS_PROMETHEUS` datasource variable, panels using `snmp_synology_*` metric names from T001: storage capacity gauge per `raidName`, disk health table per `diskID` with value mappings (1=Normal/green), CPU timeseries (`snmp_synology_cpu_usage_percent`), memory timeseries (`snmp_memTotalReal * 1024` etc. for KB→bytes conversion), network throughput timeseries (`rate(snmp_synology_network_rx_bytes[5m])`) per `ifName`, system uptime stat (`snmp_sysUpTime / 100`), RAID status stat per `raidName`; all panel types `timeseries`/`stat`/`table`/`gauge` (no deprecated `graph`); Grafana 12.3.1 compatible (depends on T001, parallel with T002)

**Checkpoint**: After T001–T003, run `ansible-playbook --syntax-check ansible/playbooks/monitoring.yml` (exit 0) and `jq . ansible/roles/monitoring_stack/files/grafana/dashboards/synology-nas.json` (exit 0). Addresses SC-001 (dashboard shows live data), SC-002 (SynologyNASDown alert fires), SC-003 (alert rules evaluate correctly) on deployment.

---

## Phase 5: User Story 4 — Nextcloud Application Metrics (Priority: P2)

**Goal**: Deploy `xperimental/nextcloud-exporter` v0.9.0 as a Docker sidecar in the Nextcloud compose stack (192.168.1.216:9205), populate the Nextcloud monitoring contract, and provision a Nextcloud dashboard.

**Independent Test**: Run `ansible-playbook ansible/playbooks/nextcloud.yml`. Verify `curl http://192.168.1.216:9205/metrics` returns `nextcloud_*` metrics. Open Grafana → "Nextcloud" dashboard → active user count, storage usage, and health status display live data.

### Implementation

- [X] T008 [P] [US4] Populate monitoring_contract block in `ansible/host_vars/nextcloud.yml` — replace empty `scrape_targets: []` and `alert_rules: []` with: scrape_targets list entry `job_name: "nextcloud-exporter", port: 9205, path: "/metrics", scrape_interval: "90s"`; alert_rules list entry `NextcloudDown` (`expr: nextcloud_up == 0, for: "5m", severity: "critical"`, summary and description strings); `dashboard_file: "grafana/dashboards/nextcloud.json"` — retain existing healthcheck block unchanged
- [X] T009 [P] [US4] [US6] Create `ansible/roles/nextcloud/files/grafana/dashboards/nextcloud.json` — `uid: "nextcloud"`, `title: "Nextcloud"`, `schemaVersion: 39`, `DS_PROMETHEUS` datasource variable, 8 panels: Health Status stat (`nextcloud_up`, value mappings 0=Down/red 1=Up/green), Active Users (24h) stat (`nextcloud_active_users_daily_total`), Total Users stat (`nextcloud_users_total`), Free Space gauge (`nextcloud_free_space_bytes`, unit `bytes`, thresholds for low space), Total Files stat (`nextcloud_files_total`), Database Size stat (`nextcloud_database_size_bytes`, unit `bytes`), Shares by Type bargauge (`nextcloud_shares_total` by `type` label), Apps Installed stat (`nextcloud_apps_installed_total`)
- [X] T010 [US4] Add nextcloud-exporter sidecar to `ansible/roles/nextcloud/templates/docker-compose.yml.j2` (new service `nextcloud_exporter`: `image: ghcr.io/xperimental/nextcloud-exporter:{{ nextcloud_exporter_version }}`, `container_name: nextcloud_exporter`, `ports: ["{{ nextcloud_exporter_port }}:9205"]`, environment `NEXTCLOUD_SERVER=http://nextcloud_app:80` and `NEXTCLOUD_AUTH_TOKEN={{ nextcloud_serverinfo_token }}` and `NEXTCLOUD_LISTEN_ADDRESS=:9205`, `depends_on: [nextcloud_app]`, `restart: unless-stopped`); add `nextcloud_exporter_version: "0.9.0"` and `nextcloud_exporter_port: 9205` to `ansible/roles/nextcloud/defaults/main.yml`; add task to `ansible/roles/nextcloud/tasks/main.yml` to configure serverinfo token via `docker exec -u www-data {{ nextcloud_app_container_name }} php occ config:app:set serverinfo token --value="{{ nextcloud_serverinfo_token }}"` with `no_log: true` (token from vault `nextcloud_serverinfo_token`) (depends on T008)

**Checkpoint**: After T008–T010, run `ansible-playbook --syntax-check ansible/playbooks/nextcloud.yml` (exit 0) and `jq . ansible/roles/nextcloud/files/grafana/dashboards/nextcloud.json` (exit 0). Addresses SC-005 (Nextcloud dashboard shows users and storage) on deployment.

---

## Phase 6: User Story 5 — Jellyfin Application Metrics (Priority: P3)

**Goal**: Deploy `rebelcore/jellyfin_exporter` v1.4.0 as a Go binary + systemd service on the Jellyfin LXC (192.168.1.215:9594), populate the Jellyfin monitoring contract, and provision a Jellyfin dashboard.

**Independent Test**: Run `ansible-playbook ansible/playbooks/jellyfin.yml`. Verify `curl http://192.168.1.215:9594/metrics` returns `jellyfin_*` metrics. Open Grafana → "Jellyfin Media Server" dashboard → media library stats and active session count display live data.

### Implementation

- [X] T011 [P] [US5] Populate monitoring_contract block in `ansible/host_vars/jellyfin.yml` — replace empty `scrape_targets: []` with scrape_targets list entry `job_name: "jellyfin-exporter", port: 9594, path: "/metrics"`; retain `alert_rules: []` (relies on generic ServiceDown from `infrastructure_alerts.yml`); set `dashboard_file: "grafana/dashboards/jellyfin.json"` — retain existing healthcheck block unchanged
- [X] T012 [P] [US5] [US6] Create `ansible/roles/jellyfin/files/grafana/dashboards/jellyfin.json` — `uid: "jellyfin"`, `title: "Jellyfin Media Server"`, `schemaVersion: 39`, `DS_PROMETHEUS` datasource variable, 5 panels: Active Sessions stat (`jellyfin_playing_count`), Total Media Items stat (`sum(jellyfin_media_count)`), Media by Type bargauge (`jellyfin_media_count` by `type` label: Movie/Series/Episode etc.), Total Users stat (`jellyfin_users_count`), System Info stat (`jellyfin_system_info` via labels)
- [X] T013 [US5] Add exporter vars to `ansible/roles/jellyfin/defaults/main.yml` (`jellyfin_exporter_version: "1.4.0"`, `jellyfin_exporter_port: 9594`, `jellyfin_exporter_install_dir: "/opt/jellyfin-exporter"`, `jellyfin_exporter_arch: "linux-amd64"`); create systemd unit `ansible/roles/jellyfin/templates/jellyfin-exporter.service.j2` (`[Unit] After=network.target jellyfin.service`, `[Service] Type=simple ExecStart={{ jellyfin_exporter_install_dir }}/jellyfin_exporter`, `Environment=JELLYFIN_ADDRESS=http://127.0.0.1:{{ jellyfin_port | default(8096) }}`, `Environment=JELLYFIN_TOKEN={{ jellyfin_api_key }}`, `Environment=LISTEN_ADDRESS=:{{ jellyfin_exporter_port }}`, `Restart=on-failure`); add handler `Restart jellyfin exporter` to `ansible/roles/jellyfin/handlers/main.yml` (`ansible.builtin.service name: jellyfin-exporter state: restarted`) — keep existing `Restart jellyfin` handler; `{{ jellyfin_api_key }}` must reference vault variable (depends on T011)
- [X] T014 [US5] Add exporter deployment tasks to end of `ansible/roles/jellyfin/tasks/main.yml` — (1) create `{{ jellyfin_exporter_install_dir }}` directory; (2) download binary `ansible.builtin.get_url` from `https://github.com/rebelcore/jellyfin_exporter/releases/download/v{{ jellyfin_exporter_version }}/jellyfin_exporter-{{ jellyfin_exporter_version }}.{{ jellyfin_exporter_arch }}.tar.gz` to `/tmp/jellyfin_exporter.tar.gz`; (3) extract with `ansible.builtin.unarchive remote_src: true creates: {{ jellyfin_exporter_install_dir }}/jellyfin_exporter`; (4) set mode `0755` on binary; (5) deploy systemd service from template, `notify: ["Reload systemd daemon", "Restart jellyfin exporter"]`; (6) enable and start service; add `Reload systemd daemon` handler (`ansible.builtin.systemd daemon_reload: true`) to `ansible/roles/jellyfin/handlers/main.yml` (depends on T013)

**Checkpoint**: After T011–T014, run `ansible-playbook --syntax-check ansible/playbooks/jellyfin.yml` (exit 0) and `jq . ansible/roles/jellyfin/files/grafana/dashboards/jellyfin.json` (exit 0). Addresses SC-006 (all new scrape targets show UP) on deployment.

---

## Phase 6B: Prometheus Reload Handler & Vault Assertions (Cross-Cutting)

**Goal**: Enable Prometheus hot-reload (no full stack restart on config changes) and add preflight assertions so missing vault credentials fail fast with clear messages.

- [X] T021 [P] [FR-027] Enable Prometheus hot-reload — (1) add `'--web.enable-lifecycle'` to the Prometheus `command` list in `ansible/roles/monitoring_stack/templates/docker-compose.yml.j2`; (2) add new handler `Reload prometheus` to `ansible/roles/monitoring_stack/handlers/main.yml` using `ansible.builtin.uri url=http://localhost:{{ prometheus_port }}/-/reload method=POST status_code=200` (must be defined BEFORE `Restart monitoring stack` so flush order is correct); (3) update `ansible/roles/monitoring_stack/tasks/compose_stack.yml`: change `notify` on Prometheus config deploy, infrastructure alerts deploy, Synology alerts deploy, and service alerts deploy tasks from `Restart monitoring stack` to `Reload prometheus` — keep `Restart monitoring stack` on docker-compose deploy, Telegraf config deploy, and Alertmanager config deploy tasks
- [X] T022 [FR-028] Add vault variable preflight assertions — (1) add assert block in `ansible/roles/nextcloud/tasks/main.yml` BEFORE the serverinfo token provisioning task (not at top of file) verifying `nextcloud_serverinfo_token is defined` with `fail_msg: "Missing vault variable: nextcloud_serverinfo_token — run 'ansible-vault edit group_vars/services/vault.yml' to add it"`; (2) add assert block in `ansible/roles/jellyfin/tasks/main.yml` BEFORE the exporter download task verifying `jellyfin_api_key is defined` with `fail_msg: "Missing vault variable: jellyfin_api_key — run 'ansible-vault edit group_vars/services/vault.yml' to add it"` (depends on T010, T014)

**Checkpoint**: After T021–T022, run `ansible-playbook --syntax-check ansible/playbooks/monitoring.yml` (exit 0); verify `--web.enable-lifecycle` in docker-compose template; verify assert blocks exist in nextcloud, jellyfin task files.

---

## Phase 7: Polish & Cross-Cutting Verification

**Purpose**: Mechanically verify all changes for correctness, idempotency, and constitution compliance before declaring the feature complete.

- [X] T015 Validate Synology and infrastructure alert rules — run `docker run --rm --entrypoint promtool -v "$(pwd)/ansible/roles/monitoring_stack/files/prometheus/alerts:/rules" prom/prometheus:v3.8.1 check rules /rules/synology_alerts.yml /rules/infrastructure_alerts.yml` — both files must exit 0; confirms `SynologyNASDown` uses `job="telegraf-snmp"`, all expressions reference real metric names (depends on T002)
- [X] T016 [P] Validate all three dashboard JSON files — `jq . ansible/roles/monitoring_stack/files/grafana/dashboards/synology-nas.json` AND `jq . ansible/roles/nextcloud/files/grafana/dashboards/nextcloud.json` AND `jq . ansible/roles/jellyfin/files/grafana/dashboards/jellyfin.json` — all exit 0; UIDs are unique (`synology-nas-health`, `nextcloud`, `jellyfin`); no `"graph"` panel type in any file; all have `schemaVersion: 39` (depends on T003, T009, T012)
- [X] T017 [P] Verify monitoring contract uniqueness across all host_vars files — parse `nextcloud.yml`, `jellyfin.yml`, `reverse_proxy.yml`, `immich.yml` with `python3 -c "import yaml; ..."`; confirm 5 unique job_names (`caddy`, `immich-api`, `immich-microservices`, `nextcloud-exporter`, `jellyfin-exporter`); confirm all new exporter ports (9205, 9594) are unique and do not collide with node_exporter (9100) or any application port (depends on T008, T011)
- [X] T018 [P] Syntax-check all three affected playbooks — `ansible-playbook --syntax-check ansible/playbooks/monitoring.yml` AND `ansible/playbooks/nextcloud.yml` AND `ansible/playbooks/jellyfin.yml` — all must exit 0 (depends on T001–T014)
- [X] T019 [P] Verify monitoring_stack role changes are limited to Synology pipeline fixes and Prometheus reload handler — `git diff --name-only -- ansible/roles/monitoring_stack/` must output only: `templates/telegraf.conf.j2`, `files/prometheus/alerts/synology_alerts.yml`, `files/grafana/dashboards/synology-nas.json`, `templates/docker-compose.yml.j2`, `handlers/main.yml`, `tasks/compose_stack.yml` — no Nextcloud/Jellyfin exporter config in this role; verify `ansible/host_vars/reverse_proxy.yml` and `ansible/host_vars/immich.yml` are unmodified via `git diff -- ansible/host_vars/reverse_proxy.yml ansible/host_vars/immich.yml` (depends on T001–T022)
- [X] T020 [P] Verify no plaintext secrets in any created or modified file — grep all new/modified files for literal credential values; confirm all credential references use Jinja2 substitution (`{{ nextcloud_serverinfo_token }}`, `{{ jellyfin_api_key }}`); confirm all tasks that handle secrets have `no_log: true`; confirm vault file `ansible/group_vars/services/vault.yml` has not been modified by this feature (depends on T001–T014)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: N/A — Feature 040 prerequisite
- **Phase 2 (Foundational)**: N/A — No shared blockers
- **Phase 3 (US-1/US-2, P1)**: No dependencies — can start immediately
  - T001 → T002 (alert metric names must match T001's output)
  - T001 → T003 (dashboard queries must match T001's metric names)
  - T002 ‖ T003 (parallel after T001)
- **Phase 5 (US-4, P2)**: Independent of Phase 3
  - T008 ‖ T009 (different files, no dependencies between them)
  - T008 → T010 (compose port must match contract port)
- **Phase 6 (US-5, P3)**: Independent of Phases 3–5
  - T011 ‖ T012 (different files, no dependencies between them)
  - T011 → T013 (defaults reference port from contract)
  - T013 → T014 (tasks reference defaults/template/handler)
- **Phase 6B (Reload + Assertions)**: T021 parallel with all phases; T022 after T010, T014
- **Phase 7 (Validation)**: Depends on ALL Phases 3–6B complete; T016–T020 can run in parallel with each other

### Dependency Graph

```
T001 → T002
T001 → T003
[T002 ‖ T003]

[T008 ‖ T009]
T008 → T010

[T011 ‖ T012]
T011 → T013 → T014

T021 (parallel — independent of T001–T014)
T022 (after T010, T014)

T015 (after T002)
[T016 ‖ T017 ‖ T018 ‖ T019 ‖ T020] (after T001–T022)
```

### Implementation Order

1. T001 (no dependencies — start immediately) AND T021 (parallel — independent)
2. T002, T003 (parallel after T001) AND T008, T009, T011, T012 (parallel — independent stories)
3. T010 (after T008), T013 (after T011)
4. T014 (after T013), T022 (after T010, T014)
5. T015–T020 (parallel validation after all code tasks complete)

---

## Parallel Execution Examples

### Within Phase 3 (US-1/US-2)

```bash
# T001 first (sequential):
Task: "T001 - Rewrite telegraf.conf.j2 SNMP inputs"

# Then in parallel:
Task: "T002 - Fix synology_alerts.yml"
Task: "T003 - Rewrite synology-nas.json dashboard"
```

### Cross-Story Parallelism (Phases 3–6 are fully independent)

```bash
# All three phases can run simultaneously:
Task: "Phase 3 - Synology SNMP fix (T001→T002+T003)"
Task: "Phase 5 - Nextcloud monitoring (T008+T009→T010)"
Task: "Phase 6 - Jellyfin monitoring (T011+T012→T013→T014)"
```

---

## Implementation Strategy

### MVP First (Phase 3 Only — US-1 + US-2)

1. Complete Phase 3: T001 → T002 + T003
2. **STOP and VALIDATE**: Deploy monitoring playbook, verify Synology dashboard shows live data (SC-001), SynologyNASDown alert evaluates (SC-002), SynologyVolumeHighUsage shows "inactive" (SC-003)
3. P1 user stories (US-1, US-2) are now met

### Incremental Delivery

1. Phase 3 (Synology fix) → Deploy and validate → SC-001, SC-002, SC-003 ✓
2. Phase 5 (Nextcloud) → Deploy and validate → SC-005 ✓
3. Phase 6 (Jellyfin) → Deploy and validate → SC-006 ✓
4. Phase 7 (Validation) → Confirm SC-007 (no monitoring_stack regression), SC-008 (idempotency), SC-009 (Feature 040 monitoring still working)

### Parallel Team Strategy

With multiple implementers working simultaneously:

- **Implementer A**: Phase 3 (touches only `monitoring_stack` role)
- **Implementer B**: Phase 5 (touches only `nextcloud` role + `host_vars/nextcloud.yml`)
- **Implementer C**: Phase 6 (touches only `jellyfin` role + `host_vars/jellyfin.yml`)

All phases are fully independent at the file level. No merge conflicts expected.

---

## File Manifest

### Files CREATED (3)

| File | Task | Story |
|------|------|-------|
| `ansible/roles/nextcloud/files/grafana/dashboards/nextcloud.json` | T009 | US-4, US-6 |
| `ansible/roles/jellyfin/templates/jellyfin-exporter.service.j2` | T013 | US-5 |
| `ansible/roles/jellyfin/files/grafana/dashboards/jellyfin.json` | T012 | US-5, US-6 |

### Files MODIFIED (14)

| File | Task | Story | Change |
|------|------|-------|--------|
| `ansible/roles/monitoring_stack/templates/telegraf.conf.j2` | T001 | US-1 | Rewrite SNMP inputs with named table queries |
| `ansible/roles/monitoring_stack/files/prometheus/alerts/synology_alerts.yml` | T002 | US-2 | Fix job label, metric names, integer comparison |
| `ansible/roles/monitoring_stack/files/grafana/dashboards/synology-nas.json` | T003 | US-1, US-6 | Full rewrite (fix malformed JSON, new metric names) |
| `ansible/roles/monitoring_stack/templates/docker-compose.yml.j2` | T021 | FR-027 | Add --web.enable-lifecycle to Prometheus command |
| `ansible/roles/monitoring_stack/handlers/main.yml` | T021 | FR-027 | Add Reload prometheus handler (POST /-/reload) |
| `ansible/roles/monitoring_stack/tasks/compose_stack.yml` | T021 | FR-027 | Split notify: Prometheus config → Reload prometheus |
| `ansible/host_vars/nextcloud.yml` | T008 | US-4 | Populate monitoring contract (was empty) |
| `ansible/roles/nextcloud/templates/docker-compose.yml.j2` | T010 | US-4 | Add nextcloud-exporter sidecar service |
| `ansible/roles/nextcloud/defaults/main.yml` | T010 | US-4 | Add exporter version and port variables |
| `ansible/roles/nextcloud/tasks/main.yml` | T010 | US-4 | Add serverinfo token provisioning task |
| `ansible/host_vars/jellyfin.yml` | T011 | US-5 | Populate monitoring contract (was empty) |
| `ansible/roles/jellyfin/defaults/main.yml` | T013 | US-5 | Add exporter version, port, install_dir, arch |
| `ansible/roles/jellyfin/tasks/main.yml` | T014 | US-5 | Add binary download, extract, systemd service tasks |
| `ansible/roles/jellyfin/handlers/main.yml` | T013, T014 | US-5 | Add Restart and Reload systemd daemon handlers |

### Files UNCHANGED (verified in T019)

| File | Reason |
|------|--------|
| `ansible/roles/monitoring_stack/templates/prometheus.yml.j2` | Scrape targets auto-discovered from contracts; no manual changes needed |
| `ansible/roles/monitoring_stack/templates/service_alerts.yml.j2` | Alert rules auto-aggregated from contracts; no manual changes needed |
| `ansible/roles/monitoring_stack/tasks/provision_dashboards.yml` | Dashboard provisioning auto-discovers from contracts; no manual changes needed |
| `ansible/playbooks/monitoring.yml` | Already contains monitoring role; no playbook changes needed |
| `ansible/playbooks/nextcloud.yml` | Already references nextcloud role; no playbook changes needed |
| `ansible/playbooks/jellyfin.yml` | Already references jellyfin role; no playbook changes needed |
| `ansible/host_vars/reverse_proxy.yml` | Caddy contract from Feature 040; must not regress |
| `ansible/host_vars/immich.yml` | Immich contract from Feature 040; must not regress |

> **Note**: `docker-compose.yml.j2`, `handlers/main.yml`, and `tasks/compose_stack.yml` in the monitoring_stack role are now in the MODIFIED table (T021 — Prometheus reload handler). These are not service-specific exporter config — they are operational improvements to the monitoring stack itself.

---

## Constitution Compliance

| # | Principle | Status | Evidence |
|---|-----------|--------|----------|
| I | Spec-Driven Workflow | ✅ PASS | All 18 tasks trace to FR/US from spec.md. File lives at `specs/041-monitoring-tier-b/tasks.md`. Requirement traceability table covers all 24 FRs. |
| II | Secrets Policy | ✅ PASS | T020 verifies no plaintext secrets. All credentials use Jinja2 vars from vault (`{{ nextcloud_serverinfo_token }}`, `{{ jellyfin_api_key }}`). Tasks with secrets have `no_log: true`. |
| III | Separation of Concerns | ✅ PASS | Terraform unchanged. All changes are Ansible roles/templates (configuration inside machines). |
| IV | Code Economy (YAGNI) | ✅ PASS | No abstraction layers. Each new file has ≥2 consumers (dashboard + alert/scrape config). No unused scaffolding. |
| V | Dual-Provisioning Parity | ✅ PASS | All changes deploy via existing playbooks. No new scripts, no CI-only paths. |

---

## Requirement Traceability

| Requirement | Task(s) | Acceptance Check |
|-------------|---------|-----------------|
| FR-001 | T001, T003 | `snmp_synology_*` metric names match between telegraf.conf.j2 and synology-nas.json panel exprs |
| FR-002 | T001 | volume capacity, network throughput, disk health, CPU scalar OIDs present in rewritten template |
| FR-003 | T002 | `SynologyNASDown` expr contains `job="telegraf-snmp"` |
| FR-004 | T002, T015 | `promtool check rules synology_alerts.yml` exits 0; no expr references non-existent metric |
| FR-005 | T001 | SNMP agent address uses `{{ synology_nas_ip }}` variable (not hardcoded) |
| FR-006 | T001 | SNMPv3 auth params reference vault variables (not hardcoded) |
| FR-007 | T003 | Dashboard has panels for storage/disk/CPU/memory/network/uptime; `jq .` exits 0 |
| FR-009 | T010 | nextcloud docker-compose.yml.j2 contains `nextcloud_exporter` sidecar service on port 9205 |
| FR-010 | T014 | jellyfin tasks.yml downloads and deploys `rebelcore/jellyfin_exporter` binary + systemd service on port 9594 |
| FR-011 | T008, T011 | Each of nextcloud.yml, jellyfin.yml has monitoring_contract block in host_vars |
| FR-012 | T008, T011 | Both contracts declare scrape_targets, alert_rules, dashboard_file |
| FR-014 | T008 | `ansible/host_vars/nextcloud.yml` has populated monitoring_contract |
| FR-015 | T011 | `ansible/host_vars/jellyfin.yml` has populated monitoring_contract |
| FR-017 | T009 | `ansible/roles/nextcloud/files/grafana/dashboards/nextcloud.json` exists and is valid JSON |
| FR-018 | T012 | `ansible/roles/jellyfin/files/grafana/dashboards/jellyfin.json` exists and is valid JSON |
| FR-019 | T009, T012, T016 | All dashboards provisioned via contract `dashboard_file`; `jq .` exits 0 on each |
| FR-020 | T003 | Synology dashboard panel exprs reference only metrics from T001; no "No Data" when NAS is reachable |
| FR-021 | T015 | `infrastructure_alerts.yml` still passes promtool; generic `up == 0` rule covers new exporters |
| FR-023 | T018 | All three playbooks pass `--syntax-check` |
| FR-024 | T020 | No plaintext credential values in any file; all use Jinja2 vault refs |
| FR-025 | T018 | Playbooks pass `--syntax-check`; idempotency verified by re-running after initial deploy |
| FR-026 | T019 | `git diff --name-only -- ansible/roles/monitoring_stack/` shows only Synology fixes + reload handler files |
| FR-027 | T021 | `--web.enable-lifecycle` in docker-compose.yml.j2; `Reload prometheus` handler in handlers/main.yml; Prometheus config tasks notify `Reload prometheus` |
| FR-028 | T022 | `ansible.builtin.assert` blocks in nextcloud, jellyfin task files verify vault variables are defined with clear `fail_msg` |
