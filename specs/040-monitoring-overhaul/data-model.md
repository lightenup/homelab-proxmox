# Data Model: Monitoring & Observability Overhaul

**Branch**: `040-monitoring-overhaul` | **Date**: 2026-03-01

## Entities

### 1. Monitoring Contract

The central data structure enabling self-registration (FR-007). Declared in each service role's `defaults/main.yml` and aggregated by the monitoring stack at deploy time.

```yaml
# Schema: monitoring_contract
monitoring_contract:
  enabled: bool                        # Whether this service participates in monitoring
  scrape_targets:                      # List of Prometheus scrape targets
    - job_name: string                 # Unique job name (must not conflict across services)
      port: int                        # Port where metrics are served
      path: string                     # Metrics endpoint path (default: /metrics)
      scrape_interval: string          # Override global scrape interval (optional)
  alert_rules:                         # List of alert rule definitions
    - alert: string                    # Alert name (unique)
      expr: string                     # PromQL expression
      for: string                      # Duration before firing (e.g., "5m")
      severity: enum[warning,critical] # Alert severity level
      summary: string                  # Human-readable summary template
      description: string              # Detailed description template
  dashboard_file: string | null        # Relative path to dashboard JSON file in role
```

**Validation rules**:
- `job_name` must be unique across all monitoring contracts in the inventory
- `port` must be between 1024–65535
- `path` must start with `/`
- `severity` must be `warning` or `critical`
- `expr` must be valid PromQL (validated at deployment)

**State transitions**:
- `enabled: true` → service is scraped, alerts loaded, dashboard provisioned
- `enabled: false` → service is excluded from all monitoring config generation

### 2. Infrastructure Metrics Agent (node_exporter)

Per-container binary deployment managed by the `node_exporter` Ansible role.

```yaml
# Configuration variables (role defaults)
node_exporter_version: string          # e.g., "1.10.2"
node_exporter_port: int                # Default: 9100
node_exporter_user: string             # System user, default: "node_exporter"
node_exporter_disabled_collectors: list # LXC-inappropriate collectors
node_exporter_enabled: bool            # Default: true
```

**Instance per host**: One node_exporter per LXC container. Runs as systemd service.

### 3. Scrape Target (generated)

Not a stored entity — generated at deploy time by the `prometheus.yml.j2` template from monitoring contracts.

```yaml
# Generated scrape_config entry
- job_name: string
  scrape_interval: string
  scrape_timeout: string
  static_configs:
    - targets: ["<host_ip>:<port>"]
      labels:
        instance: string               # Ansible inventory hostname
  metrics_path: string
```

**Sources**:
- node_exporter targets from all services group hosts
- Application metrics targets from monitoring contracts
- Existing static targets (prometheus self, telegraf-snmp)

### 4. Alert Rule (generated)

Generated at deploy time by aggregating infrastructure-wide rules and per-service contract rules into alert YAML files.

```yaml
# Alert rule structure
groups:
  - name: string                       # Rule group name
    interval: string                   # Evaluation interval
    rules:
      - alert: string                  # Alert name
        expr: string                   # PromQL expression
        for: string                    # Pending duration
        labels:
          severity: string
          component: string            # Logical component (infrastructure, availability, etc.)
        annotations:
          summary: string              # Supports {{ $labels.X }} and {{ $value }}
          description: string
```

**Two sources**:
1. **Infrastructure-wide** (`infrastructure_alerts.yml`): Always present — ServiceDown, HighCPU, HighMemory, DiskWarning, DiskCritical
2. **Per-service** (from monitoring contracts): Only present when service contracts declare them

### 5. Dashboard (file-based)

JSON files provisioned to Grafana via the existing file-based dashboard provider.

```
# Dashboard files (Grafana Schema v1 JSON)
files/grafana/dashboards/
├── synology-nas.json                  # Existing — preserved (FR-019)
├── infrastructure-overview.json       # New — FR-016
├── caddy-reverse-proxy.json           # New — FR-017
└── immich-photo-service.json          # New — FR-018
```

**Schema**: Standard Grafana v1 JSON with `uid`, `title`, `panels[]`, `templating`, `time`, `annotations` fields. Panel types: `timeseries` (Grafana 12.x preferred), `stat`, `table`.

## Relationships

```
                     ┌─────────────────┐
                     │  Ansible        │
                     │  Inventory      │
                     │  (hosts.yml)    │
                     └────────┬────────┘
                              │ defines hosts
                              ▼
            ┌─────────────────────────────────────┐
            │         Service Roles               │
            │  (reverse_proxy, immich, etc.)       │
            │                                     │
            │  Each declares:                     │
            │  ├── monitoring_contract (defaults)  │
            │  ├── dashboard JSON (files/)         │
            │  └── node_exporter (via lxc_base)    │
            └─────────────────┬───────────────────┘
                              │ aggregated via hostvars
                              ▼
            ┌─────────────────────────────────────┐
            │       monitoring_stack role          │
            │                                     │
            │  Generates:                         │
            │  ├── prometheus.yml (scrape configs) │
            │  ├── alerts/*.yml (alert rules)      │
            │  ├── alertmanager.yml (routing)       │
            │  └── dashboards/*.json (provisioned)  │
            └─────────────────────────────────────┘
```

## Variable Registry

### New Variables (this feature)

| Variable | Defined In | Default | Used By |
|----------|-----------|---------|---------|
| `node_exporter_version` | `roles/node_exporter/defaults/main.yml` | `"1.10.2"` | node_exporter role |
| `node_exporter_port` | `roles/node_exporter/defaults/main.yml` | `9100` | node_exporter role, monitoring contracts |
| `node_exporter_enabled` | `roles/node_exporter/defaults/main.yml` | `true` | node_exporter role |
| `node_exporter_disabled_collectors` | `roles/node_exporter/defaults/main.yml` | `[hwmon, thermal_zone, ...]` | node_exporter systemd unit |
| `monitoring_contract` | Each service role's `defaults/main.yml` | `{enabled: false}` | prometheus.yml.j2, alert aggregation |
| `caddy_metrics_enabled` | `roles/reverse_proxy/defaults/main.yml` | `true` | Caddyfile.j2 |
| `caddy_metrics_port` | `roles/reverse_proxy/defaults/main.yml` | `9180` | Caddyfile.j2, monitoring_contract |
| `immich_metrics_enabled` | `roles/immich/defaults/main.yml` | `true` | .env.j2, docker-compose.yml.j2 |
| `immich_metrics_port` | `roles/immich/defaults/main.yml` | `8081` | docker-compose.yml.j2, monitoring_contract |
| `immich_microservices_metrics_port` | `roles/immich/defaults/main.yml` | `8082` | docker-compose.yml.j2, monitoring_contract |

### Modified Variables (this feature)

| Variable | File | Change |
|----------|------|--------|
| `prometheus_version` | `roles/monitoring_stack/defaults/main.yml` | `"v2.48.0"` → `"v3.8.1"` |
| `grafana_version` | `roles/monitoring_stack/defaults/main.yml` | `"10.2.0"` → `"12.3.1"` |
| `telegraf_version` | `roles/monitoring_stack/defaults/main.yml` | `"1.28"` → `"1.37.0"` |
| `alertmanager_version` | `roles/monitoring_stack/defaults/main.yml` | `"v0.26.0"` → `"v0.30.0"` |
| `proxmox_backup_email_mode` | `roles/proxmox_backup/defaults/main.yml` | Default changed from `"kuma_only"` → `"disabled"` |

### Removed Variables (this feature)

| Variable | Removed From |
|----------|-------------|
| `monitoring_targets` | `host_vars/monitoring/vars.yml` |
| `uptime_kuma_api_url` | `host_vars/monitoring/vars.yml` |
| `uptime_kuma_api_wait_timeout` | `host_vars/monitoring/vars.yml` |
| `uptime_kuma_api_retry_delay` | `host_vars/monitoring/vars.yml` |
| `uptime_kuma_api_max_retries` | `host_vars/monitoring/vars.yml` |
| `uptime_kuma_admin_user` | `host_vars/monitoring/vault.yml.example` (+ actual vault) |
| `uptime_kuma_admin_password` | `host_vars/monitoring/vault.yml.example` (+ actual vault) |
| `proxmox_backup_kuma_push_url` | `roles/proxmox_backup/defaults/main.yml` |
| `proxmox_backup_kuma_url` (commented) | `group_vars/proxmox_hosts/vars.yml` |

### Port Registry (this feature)

| Port | Service | Host(s) | Direction |
|------|---------|---------|-----------|
| 9100 | node_exporter | All service LXCs (210-216) | monitoring → service |
| 9180 | Caddy metrics (dedicated site block) | reverse_proxy (211) | monitoring → reverse_proxy |
| 8081 | Immich API metrics | immich (213) | monitoring → immich |
| 8082 | Immich microservices metrics | immich (213) | monitoring → immich |
| 9090 | Prometheus | monitoring (214) | existing |
| 3000 | Grafana | monitoring (214) | existing |
| 9273 | Telegraf | monitoring (214) | existing |
| 9093 | Alertmanager | monitoring (214) | existing |
