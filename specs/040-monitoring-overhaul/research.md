# Research: Monitoring & Observability Overhaul

**Branch**: `040-monitoring-overhaul` | **Date**: 2026-03-01

## R-01: Infrastructure Metrics Agent Selection

**Decision**: Prometheus node_exporter v1.10.2, deployed as a standalone binary with systemd unit.

**Rationale**:
- node_exporter is the canonical Prometheus infrastructure metrics agent — zero integration friction with the existing Prometheus stack.
- Standalone static binary (~11 MB) runs on all LXCs regardless of whether Docker is installed (C-004: Jellyfin and Reverse Proxy run natively).
- Resource footprint: <15 MB RSS, negligible CPU — well within NFR-001's 50 MB limit.
- Default port 9100 on `/metrics` — industry standard, no port conflicts with existing services.

**Alternatives Considered**:
- **Telegraf agent**: Already used for SNMP but heavier (~100 MB). Would add Docker dependency on non-Docker LXCs.
- **Grafana Alloy**: Feature-rich but overkill for basic infrastructure metrics. Larger binary and memory footprint.
- **cAdvisor**: Docker-only; useless for native services (Jellyfin, Caddy).

## R-02: LXC-Specific Collector Configuration

**Decision**: Disable hardware-specific collectors that are meaningless inside LXC containers.

**Rationale**: LXCs are OS-level virtualisation — they share the host kernel and have no real hardware devices. Collectors like `hwmon`, `thermal_zone`, `powersupplyclass`, `nvme`, `mdadm`, `infiniband`, `fibrechannel`, and `wifi` produce no data and waste CPU cycles scanning for non-existent sysfs entries.

**Collectors to DISABLE** (via `--no-collector.<name>`):
- `hwmon` — no hardware sensors
- `thermal_zone` — no thermal zones
- `powersupplyclass` — no PSU
- `nvme` — no physical NVMe
- `mdadm` — no software RAID in LXC
- `infiniband` — no IB adapters
- `fibrechannel` — no FC
- `wifi` — no wireless

**Collectors to KEEP**: `cpu`, `meminfo`, `filesystem`, `diskstats`, `netdev`, `loadavg`, `uname`, `time`, `textfile`, `stat`, `vmstat`, `conntrack`, `entropy`, `filefd`, `sockstat`

**Filesystem exclusion**: `--collector.filesystem.mount-points-exclude="^/(sys|proc|dev|run)($|/)"` to reduce noise from virtual filesystems.

## R-03: Prometheus 3.x Compatibility

**Decision**: Existing prometheus.yml.j2 syntax is compatible with Prometheus 3.x. Two minor adjustments needed.

**Rationale**: Prometheus v3.x did NOT change `scrape_configs` YAML structure. The scrape config syntax (`static_configs`, `relabel_configs`, job definitions) is identical to v2.x. Key changes that affect us:

| Change | Impact | Action |
|--------|--------|--------|
| `no-default-scrape-port` is now default | Ports must be explicit in targets | Already done — existing targets use explicit ports |
| Alertmanager v1 API removed | Must use v2 API | Alertmanager v0.30.0 already uses v2 |
| `source_match`/`target_match` deprecated | Use `source_matchers`/`target_matchers` in alertmanager.yml | Must update existing inhibit_rules syntax |
| PromQL `.` matches newlines | Alert expressions may behave differently | No regex patterns in current alerts — no impact |
| `fallback_scrape_protocol` | Needed if targets don't set Content-Type | Add for safety on node_exporter targets |

**No breaking changes** to the core scrape config or alert rule format.

## R-04: Caddy Prometheus Metrics

**Decision**: Enable Caddy's built-in metrics via the `metrics` global option, scrape from admin API on port 2019.

**Rationale**:
- Caddy natively supports Prometheus metrics — no external exporter needed (A-003 confirmed).
- The admin API (port 2019) serves metrics at `/metrics` by default.
- Adding `metrics` to the global options block in Caddyfile enables all HTTP metrics.

**Configuration change** to `Caddyfile.j2`:
```caddyfile
{
    acme_dns ...
    log { output stdout }
    servers {
        metrics
    }
}
```

**Metrics exposed** (all `caddy_` prefixed):
- `caddy_http_requests_total` — request count by server/handler
- `caddy_http_request_duration_seconds` — round-trip histogram
- `caddy_http_response_duration_seconds` — TTFB histogram
- `caddy_http_request_size_bytes` / `caddy_http_response_size_bytes`
- `caddy_http_requests_in_flight` — concurrency gauge
- `caddy_http_request_errors_total` — error count
- `caddy_reverse_proxy_upstreams_healthy` — upstream health gauge
- Standard `go_*` and `process_*` runtime metrics

**Port**: 2019 (admin API — LAN-only, not exposed via HTTPS reverse proxy per FR-006/C-003). Caddy's admin API binds to `localhost:2019` by default; must be changed to `0.0.0.0:2019` or the LXC's IP to be reachable from the monitoring container.

**Admin API listen address**: Add `admin 0.0.0.0:2019` to Caddyfile global options (or use the LXC's IP).

## R-05: Immich Prometheus Metrics

**Decision**: Enable Immich telemetry via `IMMICH_TELEMETRY_INCLUDE=all` environment variable.

**Rationale**:
- Immich supports opt-in Prometheus metrics — data stays local (A-004 confirmed).
- Two metrics endpoints exposed: API on port 8081, microservices on port 8082.
- Requires explicit Docker port mapping since these ports aren't exposed by default.

**Configuration change** to `.env.j2`:
```env
IMMICH_TELEMETRY_INCLUDE=all
```

**Configuration change** to `docker-compose.yml.j2`:
```yaml
immich-server:
  ports:
    - "{{ immich_port }}:2283"
    - "{{ immich_metrics_port | default(8081) }}:8081"
    - "{{ immich_microservices_metrics_port | default(8082) }}:8082"
```

**Metrics categories**: API request counts/times, host CPU/memory, IO/database queries, repository metrics, background job metrics.

**Community Grafana dashboard**: ID 22555 on Grafana Labs — can be used as a base for FR-018.

## R-06: Self-Registration Pattern Design

**Decision**: Use `hostvars`-based aggregation with a standardised `monitoring_contract` variable defined in each service role's defaults.

**Rationale**:
- Ansible's `hostvars` provides cross-host variable access at template render time — no additional tooling needed.
- Each service role defines a `monitoring_contract` dict in its `defaults/main.yml` with: `enabled`, `scrape_targets[]`, `alert_rules[]`, `dashboard_file`.
- The monitoring stack's `prometheus.yml.j2` template iterates over all hosts in the inventory, reading their `monitoring_contract` from `hostvars`.
- This is the simplest approach that satisfies FR-007/FR-008 without external service discovery (Consul, DNS-SD).

**Pattern**:
```yaml
# In service role defaults/main.yml
monitoring_contract:
  enabled: true
  scrape_targets:
    - job_name: "caddy"
      port: 2019
      path: "/metrics"
      scrape_interval: "30s"
  alert_rules: []  # Defined inline or as a file reference
  dashboard_file: "caddy-dashboard.json"  # Optional
```

**Template aggregation** in `prometheus.yml.j2`:
```jinja2
{% for host in groups['services'] | default([]) %}
{% set contract = hostvars[host].monitoring_contract | default({}) %}
{% if contract.enabled | default(false) %}
{% for target in contract.scrape_targets | default([]) %}
  - job_name: '{{ target.job_name }}'
    scrape_interval: {{ target.scrape_interval | default(prometheus_scrape_interval) }}
    static_configs:
      - targets: ['{{ hostvars[host].ansible_host }}:{{ target.port }}']
        labels:
          instance: '{{ host }}'
    metrics_path: {{ target.path | default('/metrics') }}
{% endfor %}
{% endif %}
{% endfor %}
```

**Alternatives Considered**:
- **Prometheus `file_sd_configs`**: More dynamic but requires writing JSON files to the Prometheus container — adds complexity without benefit since Ansible already controls deployment.
- **Prometheus HTTP service discovery**: Overkill for 7 static LXCs. Adds a service discovery endpoint to maintain.
- **Consul/Nomad**: Not deployed in this homelab; adding a service mesh for 7 containers is excessive.

## R-07: Alertmanager Inhibition Strategy

**Decision**: Three inhibition rule sets covering the hierarchy: agent-down → threshold-suppression, specific-alert → generic-suppression, critical → warning-suppression.

**Rationale**:

1. **Agent-down suppresses threshold alerts** (FR-029): When a node_exporter target is unreachable (`up{job="node-exporter"} == 0`), CPU/memory/disk threshold alerts for that container use stale data. Inhibit them.

2. **SynologyNASDown suppresses generic ServiceDown** (FR-028): The existing `SynologyNASDown` alert is more specific than the generic `ServiceDown` rule. Use label-based inhibition so the Synology-specific alert takes precedence.

3. **Critical suppresses warning**: Standard severity hierarchy — if a critical alert fires, suppress the warning for the same instance.

**Syntax**: Must use `source_matchers`/`target_matchers` (not deprecated `source_match`/`target_match`) for Alertmanager v0.30.0 compatibility.

**Timing consideration**: The source alert (e.g., ServiceDown with `for: 2m`) must fire before the target alerts. Infrastructure threshold alerts use `for: 5m+` which guarantees the 2-minute ServiceDown fires first.

## R-08: Grafana Dashboard Provisioning

**Decision**: Use classic Schema v1 JSON dashboards with the existing file-based provisioning mechanism.

**Rationale**:
- Schema v2 is experimental in Grafana 12.x (requires `kubernetesDashboards` feature flag) — not production-ready for self-managed instances.
- The existing provisioning pattern (YAML provider pointing to a dashboards directory, JSON files mounted read-only) works unchanged.
- New dashboards are added as JSON files alongside the existing `synology-nas.json`.

**Dashboard organization**: Use subdirectories for logical grouping:
- `dashboards/synology-nas.json` — existing (preserved per FR-019)
- `dashboards/infrastructure-overview.json` — new (FR-016)
- `dashboards/caddy-reverse-proxy.json` — new (FR-017)
- `dashboards/immich-photo-service.json` — new (FR-018)

The existing provisioning YAML already scans the dashboards directory recursively with a 10s update interval.

## R-09: node_exporter Deployment Approach

**Decision**: Create a new `node_exporter` Ansible role, included from `lxc_base` role for universal deployment.

**Rationale**:
- DL-10 decided to deploy via a shared base role, not per-service.
- Including from `lxc_base` ensures every LXC automatically gets node_exporter as new services are added.
- The role handles: binary download, user creation, systemd unit, collector flags.

**Alternatives Considered**:
- **Deploy from monitoring_stack role**: Would create a cross-host deployment pattern that's unusual for Ansible (monitoring role SSHing to other hosts). Violates the "one host per play" convention.
- **Deploy inline in lxc_base**: Would bloat the base role. Better to have a dedicated role with clear responsibility.
- **Deploy via each service's playbook**: Would require adding the role to every playbook manually — defeats the "extensible" pattern goal.

**Implementation**: `lxc_base/tasks/main.yml` includes the `node_exporter` role, so every playbook that uses `lxc_base` (all service playbooks do) automatically deploys node_exporter.

## R-10: Monitoring Playbook Scope

**Decision**: The monitoring playbook continues to target only the `monitoring` host. node_exporter is deployed by service playbooks via `lxc_base`.

**Rationale**:
- The monitoring playbook (`ansible/playbooks/monitoring.yml`) targets `hosts: monitoring` and deploys `lxc_base`, `mdns_base`, `monitoring_stack`.
- node_exporter on other LXCs is deployed when each service's playbook runs (they all include `lxc_base` as their first role).
- This preserves the existing deployment model: each service playbook is self-contained.

**Implication**: After initial rollout, all service playbooks must be run once to deploy node_exporter to existing LXCs. Subsequent deployments of any service playbook will be idempotent.

## R-11: Uptime Kuma Container Cleanup

**Decision**: Add a cleanup task to the monitoring_stack role that stops and removes the Uptime Kuma Docker container and its data volume if they exist.

**Rationale**:
- FR-023 requires the Kuma container to be stopped and removed on the monitoring LXC.
- Since the monitoring playbook is the one that runs on the monitoring host, the cleanup task belongs in the monitoring_stack role.
- The task is idempotent: if Kuma is already gone, it does nothing.

**Implementation**: Add a task early in `monitoring_stack/tasks/main.yml` that:
1. Checks if the `uptime-kuma` Docker container exists
2. Stops and removes it if present
3. Removes the Docker volume if present
4. Removes the Kuma data directory if present
