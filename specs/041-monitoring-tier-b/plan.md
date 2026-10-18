# Implementation Plan: Monitoring Tier B — Synology SNMP Fix & External Exporters

**Branch**: `041-monitoring-tier-b` | **Date**: 2026-03-01 | **Spec**: `specs/041-monitoring-tier-b/spec.md`
**Input**: Feature specification from `/specs/041-monitoring-tier-b/spec.md`

## Summary

This feature restores the broken Synology SNMP metrics pipeline (Priority 1), fixes non-functional alert rules, and adds application-level metrics for two services that currently lack them — Nextcloud and Jellyfin (Priority 2/3). The approach leverages the self-registration pattern (monitoring contracts in host_vars) established in Feature 040, deploys community-maintained exporters via service roles, and keeps the central monitoring role free of service-specific configuration.

## Technical Context

**Language/Version**: Ansible 2.x (YAML/Jinja2), Telegraf TOML, Grafana JSON, Go binaries
**Primary Dependencies**: Docker (geerlingguy.docker), Telegraf 1.37.0, Prometheus v3.8.1, Grafana 12.3.1
**Storage**: N/A (metrics stored in Prometheus TSDB, already provisioned)
**Testing**: `ansible-lint`, `promtool check rules`, `jq` JSON validation, manual dashboard verification
**Target Platform**: Proxmox LXC containers (Debian stable), Docker containers
**Project Type**: Infrastructure-as-Code (Ansible roles + Jinja2 templates)
**Performance Goals**: Exporter scrape < 10s, dashboard load < 5s (24h range), exporter RAM < 50MB each
**Constraints**: No plaintext secrets, no changes to monitoring role for new exporters, idempotent deploys
**Scale/Scope**: 7 LXCs, 1 NAS, 4 exporters (1 fix + 3 new)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Principle | Status | Evidence |
|---|-----------|--------|----------|
| I | Spec-Driven Workflow | ✅ PASS | All steps trace to FR/US in spec.md. Plan output to specs/041-monitoring-tier-b/. |
| II | Secrets Policy | ✅ PASS | SNMP creds (existing vault), Nextcloud token, Jellyfin API key → all in `ansible/group_vars/services/vault.yml` or `monitoring/vault.yml`. No plaintext secrets. |
| III | Separation of Concerns | ✅ PASS | Terraform unchanged. All changes are Ansible roles/playbooks (configuration inside machines). |
| IV | Code Economy (YAGNI) | ✅ PASS | Each exporter has 2+ consumers (dashboard + alert rules). No wrapper abstractions or indirection layers. Jellyfin proceeds only because a viable exporter exists (research confirmed). |
| V | Dual-Provisioning Parity | ✅ PASS | All changes are Ansible playbooks executable from both CI (GitHub Actions self-hosted runner) and developer laptop. No new scripts, no CI-only paths. Existing playbooks (`monitoring.yml`, `nextcloud.yml`, `jellyfin.yml`) already in both contexts. |

**Post-Design Re-check**: ✅ All five principles still PASS after Phase 1 design completion. No unnecessary abstraction introduced.

## Project Structure

### Documentation (this feature)

```text
specs/041-monitoring-tier-b/
├── spec.md                          # Feature specification (input)
├── plan.md                          # This file (architecture + implementation steps)
├── research.md                      # Phase 0: exporter research, OID research
├── data-model.md                    # Phase 1: entities, port registry, credential registry
├── quickstart.md                    # Phase 1: deployment guide
├── contracts/
│   └── monitoring-contract.schema.yml  # Monitoring contract schema reference
└── tasks.md                         # Phase 2 output (created by /speckit.tasks)
```

### Source Code (files created or modified)

```text
# MODIFIED files
ansible/roles/monitoring_stack/templates/telegraf.conf.j2    — Rewrite SNMP inputs: table queries, new OIDs, metric naming
ansible/roles/monitoring_stack/files/prometheus/alerts/synology_alerts.yml — Fix job label, metric names in alert rules
ansible/roles/monitoring_stack/files/grafana/dashboards/synology-nas.json — Rewrite dashboard with consistent metric names
ansible/roles/monitoring_stack/templates/docker-compose.yml.j2 — Add --web.enable-lifecycle to Prometheus command
ansible/roles/monitoring_stack/handlers/main.yml             — Add Reload prometheus handler (POST /-/reload)
ansible/roles/monitoring_stack/tasks/compose_stack.yml       — Split notify: Prometheus config → Reload prometheus, compose/telegraf/alertmanager → Restart monitoring stack
ansible/host_vars/nextcloud.yml                              — Populate monitoring contract (scrape targets, alerts, dashboard)
ansible/host_vars/jellyfin.yml                               — Populate monitoring contract (scrape targets, dashboard)
ansible/roles/nextcloud/templates/docker-compose.yml.j2      — Add nextcloud-exporter sidecar service
ansible/roles/nextcloud/defaults/main.yml                    — Add exporter version variable
ansible/roles/nextcloud/tasks/main.yml                       — Add serverinfo token provisioning task
ansible/roles/jellyfin/tasks/main.yml                        — Add exporter binary download + systemd service
ansible/roles/jellyfin/defaults/main.yml                     — Add exporter version/port variables
ansible/roles/monitoring_stack/templates/docker-compose.yml.j2 — Add --web.enable-lifecycle to Prometheus command
ansible/roles/monitoring_stack/handlers/main.yml             — Add Reload prometheus handler (POST /-/reload)
ansible/roles/monitoring_stack/tasks/compose_stack.yml       — Split notify: Prometheus config → Reload prometheus

# CREATED files
ansible/roles/nextcloud/files/grafana/dashboards/nextcloud.json  — Grafana dashboard
ansible/roles/jellyfin/files/grafana/dashboards/jellyfin.json    — Grafana dashboard
ansible/roles/jellyfin/templates/jellyfin-exporter.service.j2    — Systemd service unit
ansible/roles/jellyfin/handlers/main.yml                         — Restart handler for exporter (modify existing)
```

**Structure Decision**: Follows existing repo layout. Each service role owns its exporter deployment, dashboard JSON, and monitoring contract. The monitoring_stack role discovers exporters via contracts — no service-specific code added to it.

## Complexity Tracking

No constitution violations. No complexity justifications needed.

## Architecture Overview

### Component Topology

```
┌─────────────────────────────────────────────────────────────────────┐
│ Monitoring LXC (192.168.1.214)                                      │
│  ┌────────────┐  ┌──────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ Prometheus  │  │ Grafana  │  │ Alertmanager │  │  Telegraf    │  │
│  │  :9090      │  │  :3000   │  │    :9093     │  │   :9273      │  │
│  └─────┬──────┘  └────┬─────┘  └──────────────┘  └──────┬───────┘  │
│        │              │                                   │          │
└────────┼──────────────┼───────────────────────────────────┼──────────┘
         │              │                                   │
   ┌─────┴──────────────┴───────────────────────────────────┴─────────┐
   │ Scrape Targets                    SNMP Poll                       │
   │                                                                   │
   │                  ┌──────────────┐ ┌──────────────┐ ┌───────────┐│
   │                  │ Nextcloud LXC│ │ Jellyfin LXC │ │ Synology  ││
   │                  │ .216         │ │ .215         │ │ NAS .109  ││
   │                  │              │ │              │ │           ││
   │                  │ node:9100    │ │ node:9100    │ │ SNMP:161  ││
   │                  │ exporter:9205│ │ exporter:9594│ │(UDP,SNMPv3)│
   │                  └──────────────┘ └──────────────┘ └───────────┘│
   └──────────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Synology NAS**: Telegraf (on monitoring LXC) polls NAS via SNMPv3 → transforms OIDs to named metrics → exposes on `:9273/metrics` → Prometheus scrapes `telegraf-snmp` job
3. **Nextcloud**: `nextcloud-exporter` container (sidecar in nextcloud compose) queries serverinfo API → exposes on `:9205/metrics` → Prometheus scrapes `nextcloud-exporter` job
4. **Jellyfin**: `jellyfin_exporter` binary (systemd on jellyfin LXC) queries Jellyfin API → exposes on `:9594/metrics` → Prometheus scrapes `jellyfin-exporter` job

### Key Design Decisions

| Decision | Choice | Trade-off |
|----------|--------|-----------|
| Metric naming alignment | Rewrite Telegraf to produce `snmp_synology_*` metrics and rewrite dashboard to match | Both Telegraf config AND dashboard change, but produces clean, consistent naming going forward |
| SNMP table vs scalar queries | Table queries for disks, volumes, interfaces | More complex Telegraf config, but handles multiple disks/volumes/interfaces automatically |
| Nextcloud exporter placement | Docker sidecar in nextcloud compose | Can reach nextcloud_app via Docker network (no external auth needed for internal URL) |
| Jellyfin exporter placement | Go binary + systemd on jellyfin LXC | No Docker on jellyfin LXC; binary install follows node_exporter pattern |
| Jellyfin monitoring status | Proceed (not descoped) | `rebelcore/jellyfin_exporter` v1.4.0 is viable — spec's descoping condition not met |

## Technology Choices

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Nextcloud exporter | `xperimental/nextcloud-exporter` v0.9.0 | 273 stars, MIT, Docker image, token auth, covers required metrics (R2) |
| Jellyfin exporter | `rebelcore/jellyfin_exporter` v1.4.0 | 34 stars, Apache-2.0, Go binary, actively maintained Feb 2026 (R3) |
| Synology volume OIDs | RAID MIB (1.3.6.1.4.1.6574.3) | Bytes directly, no multiplication needed (R4) |
| Synology network OIDs | IF-MIB ifXTable (1.3.6.1.2.1.31.1.1.1) | 64-bit counters, no wrap at 4GB (R4) |

## Implementation Steps

### Step 1: Fix Telegraf SNMP Configuration (Synology Metrics Pipeline)

- **Files**: `ansible/roles/monitoring_stack/templates/telegraf.conf.j2`
- **Description**: Rewrite the `[[inputs.snmp]]` section to:
  1. Replace scalar field queries (`.0` suffix) with SNMP table queries for disks, volumes, and network interfaces
  2. Add volume capacity OIDs (RAID MIB: raidFreeSize, raidTotalSize)
  3. Add network throughput OIDs (IF-MIB: ifHCInOctets, ifHCOutOctets)
  4. Add Synology CPU utilization OID (cpuUtilization, direct percentage)
  5. Use `name` parameter on each input block to produce `snmp_synology_*` prefixed metrics
  6. Convert disk/RAID scalar queries to table queries with proper tag columns (diskID, raidName, ifName)
  7. Retain existing memory fields (memTotalReal, memAvailReal, memBuffer, memCached) and system fields (sysDescr, sysUpTime, sysName)
  8. Retain all existing global tags, SNMPv3 auth config, and output plugin config
- **Dependencies**: None
- **Parallel-safe**: Yes
- **Traces to**: FR-001, FR-002, FR-005, FR-006, US-1
- **Done-condition**: `ansible-playbook --syntax-check playbooks/monitoring.yml` passes; Jinja2 template renders valid TOML (no unclosed brackets or missing fields)

### Step 2: Fix Synology Alert Rules

- **Files**: `ansible/roles/monitoring_stack/files/prometheus/alerts/synology_alerts.yml`
- **Description**:
  1. Change `SynologyNASDown` expr from `up{job="synology-snmp"}` to `up{job="telegraf-snmp"}`
  2. Change `SynologyVolumeHighUsage` expr to use `snmp_synology_volume_available_bytes` and `snmp_synology_volume_size_bytes` (with `volume` label from table query)
  3. Change `SynologyDiskSMARTWarning` expr to use `snmp_synology_disk_status` (integer comparison, not string match — diskStatus returns integer where 1=Normal)
  4. Update annotation templates to reference correct label names (`volume` instead of `$labels.volume` where appropriate, `disk` from disk table tag)
- **Dependencies**: Step 1 (must know the exact metric names produced)
- **Parallel-safe**: No (depends on Step 1 metric names)
- **Traces to**: FR-003, FR-004, US-2
- **Done-condition**: `docker run --rm -v $(pwd)/alerts:/rules prom/prometheus:v3.8.1 promtool check rules /rules/synology_alerts.yml` returns exit code 0; no alert rule references a metric name not produced by Step 1

### Step 3: Rewrite Synology NAS Dashboard

- **Files**: `ansible/roles/monitoring_stack/files/grafana/dashboards/synology-nas.json`
- **Description**: Rewrite the dashboard JSON to:
  1. Fix the malformed JSON (current file has overlapping panel definitions)
  2. Use consistent `snmp_synology_*` metric names from Step 1
  3. Include panels: Storage Capacity gauge (per volume), Disk Health table, CPU Usage graph, Memory Usage graph, Network Throughput graph, System Uptime stat
  4. Use `volume` tag for multi-volume panels, `disk` tag for multi-disk panels, `interface` tag for network panels
  5. Dashboard queries for memory: use `snmp_memTotalReal * 1024` (UCD-SNMP reports KB)
  6. Compatible with Grafana 12.3.1 (no deprecated panel types)
  7. Set `schemaVersion: 39` (Grafana 12.x), unique `uid: "synology-nas-health"`
- **Dependencies**: Step 1 (metric names must match)
- **Parallel-safe**: No (depends on Step 1 metric names)
- **Traces to**: FR-007, FR-020, US-1, US-6
- **Done-condition**: `jq . synology-nas.json` returns valid JSON (exit code 0); all panel `expr` fields reference only metric names from Step 1

### Step 7: Update Nextcloud Host Vars (Monitoring Contract)

- **Files**: `ansible/host_vars/nextcloud.yml` (MODIFY)
- **Description**: Populate the currently empty monitoring contract:
  1. Add scrape target: `nextcloud-exporter` on port 9205, path `/metrics`, interval `90s`
  2. Add alert rules: `NextcloudDown` (nextcloud_up == 0 for 5m)
  3. Add dashboard file reference: `grafana/dashboards/nextcloud.json`
  4. Retain existing healthcheck config unchanged
- **Dependencies**: None
- **Parallel-safe**: Yes
- **Traces to**: FR-014, US-4
- **Done-condition**: `monitoring_contract.scrape_targets` has length 1; `monitoring_contract.dashboard_file` is not null

### Step 8: Add Nextcloud Exporter to Docker Compose

- **Files**:
  - `ansible/roles/nextcloud/templates/docker-compose.yml.j2` (MODIFY)
  - `ansible/roles/nextcloud/defaults/main.yml` (MODIFY)
  - `ansible/roles/nextcloud/tasks/main.yml` (MODIFY)
- **Description**:
  1. Add `nextcloud_exporter` service to docker-compose.yml.j2: image `ghcr.io/xperimental/nextcloud-exporter:{{ nextcloud_exporter_version }}`, port 9205, env vars `NEXTCLOUD_SERVER=http://nextcloud_app:80`, `NEXTCLOUD_AUTH_TOKEN={{ nextcloud_serverinfo_token }}`, depends_on nextcloud_app
  2. Add `nextcloud_exporter_version: "0.9.0"` to defaults/main.yml
  3. Add task in main.yml to configure serverinfo token via `occ config:app:set serverinfo token --value="{{ nextcloud_serverinfo_token }}"` (after Nextcloud is running and installed)
  4. Token sourced from vault: `nextcloud_serverinfo_token`
- **Dependencies**: Step 7 (contract must reference port 9205)
- **Parallel-safe**: No (modifying same role as Step 7 depends on)
- **Traces to**: FR-009, FR-011, FR-012, US-4
- **Done-condition**: `ansible-playbook --syntax-check playbooks/nextcloud.yml` passes; docker-compose template contains `nextcloud_exporter` service

### Step 9: Create Nextcloud Grafana Dashboard

- **Files**: `ansible/roles/nextcloud/files/grafana/dashboards/nextcloud.json` (CREATE)
- **Description**: Create a Grafana dashboard JSON with panels:
  1. Active Users (stat): `nextcloud_active_users_daily_total`
  2. Total Users (stat): `nextcloud_users_total`
  3. Free Space (gauge): `nextcloud_free_space_bytes`
  4. Total Files (stat): `nextcloud_files_total`
  5. Database Size (stat): `nextcloud_database_size_bytes`
  6. System Health (stat): `nextcloud_up`
  7. Shares by Type (bar): `nextcloud_shares_total`
  8. Unique `uid: "nextcloud"`, title: "Nextcloud"
  9. Compatible with Grafana 12.3.1
- **Dependencies**: None
- **Parallel-safe**: Yes
- **Traces to**: FR-017, FR-019, US-4, US-6
- **Done-condition**: `jq . nextcloud.json` returns valid JSON; uid is unique

### Step 10: Update Jellyfin Host Vars (Monitoring Contract)

- **Files**: `ansible/host_vars/jellyfin.yml` (MODIFY)
- **Description**: Populate the currently empty monitoring contract:
  1. Add scrape target: `jellyfin-exporter` on port 9594, path `/metrics`
  2. Dashboard file reference: `grafana/dashboards/jellyfin.json`
  3. No custom alert rules (relies on generic ServiceDown from infrastructure_alerts.yml)
  4. Retain existing healthcheck config unchanged
- **Dependencies**: None
- **Parallel-safe**: Yes
- **Traces to**: FR-015, US-5
- **Done-condition**: `monitoring_contract.scrape_targets` has length 1; `monitoring_contract.dashboard_file` is not null

### Step 11: Add Jellyfin Exporter to Role

- **Files**:
  - `ansible/roles/jellyfin/defaults/main.yml` (MODIFY)
  - `ansible/roles/jellyfin/tasks/main.yml` (MODIFY)
  - `ansible/roles/jellyfin/templates/jellyfin-exporter.service.j2` (CREATE)
  - `ansible/roles/jellyfin/handlers/main.yml` (MODIFY)
- **Description**:
  1. Add to defaults: `jellyfin_exporter_version: "1.4.0"`, `jellyfin_exporter_port: 9594`, `jellyfin_exporter_install_dir: "/opt/jellyfin-exporter"`
  2. Add tasks to main.yml:
     a. Create install directory
     b. Download `jellyfin_exporter` binary from GitHub releases (architecture-aware, `linux-amd64`)
     c. Deploy systemd service from template
     d. Enable and start service
  3. Create systemd service template with `JELLYFIN_ADDRESS` and `JELLYFIN_TOKEN` environment variables
  4. Add/update handler for restarting exporter service
  5. Jellyfin API key sourced from vault: `jellyfin_api_key`
- **Dependencies**: Step 10 (contract must reference port 9594)
- **Parallel-safe**: No (modifying same role as Step 10 depends on)
- **Traces to**: FR-010, FR-011, FR-012, US-5
- **Done-condition**: `ansible-playbook --syntax-check playbooks/jellyfin.yml` passes; systemd service template exists; binary download URL is valid

### Step 12: Create Jellyfin Grafana Dashboard

- **Files**: `ansible/roles/jellyfin/files/grafana/dashboards/jellyfin.json` (CREATE)
- **Description**: Create a Grafana dashboard JSON with panels:
  1. Active Sessions (stat): `jellyfin_playing_count` or similar
  2. Media Library (stat): `jellyfin_media_*` totals by type
  3. Connected Users (stat): `jellyfin_users_*`
  4. System Status (stat): `jellyfin_system_*`
  5. Unique `uid: "jellyfin"`, title: "Jellyfin Media Server"
  6. Compatible with Grafana 12.3.1
- **Dependencies**: None
- **Parallel-safe**: Yes
- **Traces to**: FR-018, FR-019, US-5, US-6
- **Done-condition**: `jq . jellyfin.json` returns valid JSON; uid is unique

### Step 13: Enable Prometheus Hot-Reload and Split Handlers

- **Files**:
  - `ansible/roles/monitoring_stack/templates/docker-compose.yml.j2` (MODIFY)
  - `ansible/roles/monitoring_stack/handlers/main.yml` (MODIFY)
  - `ansible/roles/monitoring_stack/tasks/compose_stack.yml` (MODIFY)
- **Description**:
  1. Add `--web.enable-lifecycle` to the Prometheus `command` list in `docker-compose.yml.j2` — enables the `POST /-/reload` API endpoint
  2. Add a new handler `Reload prometheus` in `handlers/main.yml` that sends `POST http://localhost:9090/-/reload` via `ansible.builtin.uri` (lightweight, no container restart)
  3. Split notify handlers in `compose_stack.yml`: Prometheus config (`prometheus.yml`) and alert rule deploys notify `Reload prometheus` instead of `Restart monitoring stack`; docker-compose, Telegraf, and Alertmanager changes continue to notify `Restart monitoring stack`
  4. Keep the existing `Restart monitoring stack` handler for changes that require container recreation (compose file, Telegraf config, Alertmanager config)
- **Dependencies**: None (modifies monitoring_stack internals only)
- **Parallel-safe**: Yes (independent of Steps 1-12)
- **Traces to**: FR-027
- **Done-condition**: `ansible-playbook --syntax-check playbooks/monitoring.yml` passes; handler file contains both `Reload prometheus` and `Restart monitoring stack`; docker-compose template contains `--web.enable-lifecycle`

### Step 14: Add Vault Variable Preflight Assertions

- **Files**:
  - `ansible/roles/nextcloud/tasks/main.yml` (MODIFY — prepend exporter assertions)
  - `ansible/roles/jellyfin/tasks/main.yml` (MODIFY — prepend exporter assertions)
- **Description**: Add `ansible.builtin.assert` tasks at the beginning of each exporter deployment section that verify required vault variables are defined:
  2. Nextcloud: assert `nextcloud_serverinfo_token` is defined (before exporter tasks, not before the entire role)
  3. Jellyfin: assert `jellyfin_api_key` is defined (before exporter tasks, not before the entire role)
  4. Each assertion must use `fail_msg` with a human-readable message naming the missing variable and pointing to the vault file
- **Dependencies**: Steps 5, 8, 11 (roles must exist)
- **Parallel-safe**: No (modifies files also touched by other steps)
- **Traces to**: FR-028
- **Done-condition**: Each role's tasks file contains an assert block; running with undefined vault vars produces a clear error message (not a Jinja2 traceback)

### Step 15: Validate All Alert Rules

- **Files**: All alert YAML files
- **Description**: Run Prometheus rule validation against all alert files:
  1. `synology_alerts.yml` (fixed in Step 2)
  2. `infrastructure_alerts.yml` (unchanged, regression check)
  3. `service_alerts.yml.j2` (template — render with test data and validate)
- **Dependencies**: Steps 1-12 (all changes complete)
- **Parallel-safe**: No (final validation)
- **Traces to**: FR-004, FR-021, US-2
- **Done-condition**: `promtool check rules` returns exit code 0 for all static rule files; `ansible-lint` passes for all modified playbooks

### Step 16: End-to-End Verification

- **Files**: None (verification only)
- **Description**: Run full verification suite:
  1. `ansible-playbook --syntax-check` for all affected playbooks (monitoring, nextcloud, jellyfin)
  2. `ansible-lint` on all modified roles
  3. `jq .` validation on all dashboard JSON files
  4. Verify no secrets in plaintext (grep for passwords/tokens in non-vault files)
  5. Verify idempotency: no role writes to monitoring_stack for new exporters
  6. Verify all monitoring contracts have unique job names
  7. Verify all dashboard UIDs are unique
  8. Verify `--web.enable-lifecycle` is present in Prometheus command (Step 13)
  9. Verify vault assertion tasks exist in nextcloud, jellyfin roles (Step 14)
- **Dependencies**: Steps 1-15 (everything must be complete)
- **Parallel-safe**: No (final gate)
- **Traces to**: FR-023, FR-024, FR-025, FR-026, FR-027, FR-028, SC-007, SC-008
- **Done-condition**: All syntax checks pass; ansible-lint returns 0; all JSON files are valid; no plaintext secrets found outside vault files; no service-specific exporter code in `ansible/roles/monitoring_stack/`; Prometheus reload handler exists; vault assertions present in exporter roles

## Risk Assessment

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Synology SNMP OIDs differ on actual DSM version | Telegraf produces zero metrics for affected OIDs | Medium | Research confirmed OIDs for DSM 7.x; operator can verify via `snmpwalk` before deploy |
| SNMPv3 credentials rotated since Feature 017 | Telegraf auth fails, zero metrics | Medium | FR-006 requires verification; credentials in vault can be updated by operator |
| Nextcloud serverinfo app disabled | Exporter returns errors | Low | App is bundled and enabled by default; task verifies via `occ app:list` |
| Jellyfin exporter binary unavailable for platform | Download fails | Low | LXC is amd64 Debian; binary published for linux-amd64 |
| Grafana 12.3.1 deprecates panel types used | Dashboard panels don't render | Low | Using only `stat`, `timeseries`, `table`, `gauge` — all current in Grafana 12.x |
| Port conflict on service LXC | Exporter fails to bind | Very Low | All exporter ports (9618, 9205, 9594) are standard and don't conflict with service ports |
| New scrape targets exceed monitoring LXC resources | Prometheus OOM | Very Low | 3 additional lightweight targets; NFR-002 allows 4GB RAM, well within budget |

## Testing Strategy

### Syntax & Lint (automated, pre-deploy)

- `ansible-playbook --syntax-check` for `monitoring.yml`, `nextcloud.yml`, `jellyfin.yml`
- `ansible-lint` on all modified roles
- `jq .` on all dashboard JSON files
- `promtool check rules` on `synology_alerts.yml`

### Contract Validation (automated, pre-deploy)

- Verify each host_vars file parses as valid YAML
- Verify `monitoring_contract.scrape_targets[].job_name` is unique across all host_vars files
- Verify `monitoring_contract.dashboard_file` paths exist under the corresponding role's `files/` directory

### Integration (manual, post-deploy)

- **SC-001**: Synology NAS dashboard shows live data on all panels
- **SC-002**: Block SNMP traffic → `SynologyNASDown` fires within 3 minutes
- **SC-005**: Nextcloud dashboard shows active users and storage
- **SC-006**: All scrape targets show "UP" in Prometheus targets page
- **SC-007**: `git diff ansible/roles/monitoring_stack/` shows no service-specific exporter config
- **SC-008**: Re-run each playbook → no changes (idempotent)
- **SC-009**: Existing Caddy and Immich dashboards still show data (regression check)

### Coverage Target

All 22 acceptance criteria from the 6 user stories are addressed by implementation steps. Each AC maps to at least one step's done-condition or the integration test checklist.
