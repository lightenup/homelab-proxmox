# Data Model: Monitoring Tier B

**Branch**: `041-monitoring-tier-b` | **Date**: 2026-03-01

## Entities

### 1. Monitoring Contract (host_vars)

The central data structure for service self-registration. Declared per-service in `ansible/host_vars/<service>.yml`. Consumed by the monitoring_stack role's Jinja2 templates to generate Prometheus scrape targets, alert rules, and dashboard provisioning.

```yaml
monitoring_contract:
  enabled: bool                      # Whether monitoring is active
  scrape_targets:                    # List of Prometheus scrape endpoints
    - job_name: string               # Prometheus job label (unique across all contracts)
      port: int                      # Exporter port on the service host
      path: string                   # Metrics path (default: /metrics)
      scrape_interval: string        # Override interval (default: global)
  alert_rules:                       # List of Prometheus alert rules
    - alert: string                  # Alert name (PascalCase)
      expr: string                   # PromQL expression
      for: string                    # Duration before firing
      severity: string               # warning | critical
      summary: string                # Human-readable summary (supports Go templates)
      description: string            # Detailed description (supports Go templates)
  dashboard_file: string | null      # Path relative to role's files/ directory
```

**Validation Rules**:
- `job_name` must be unique across all monitoring contracts
- `port` must not conflict with the service's application port or node_exporter (9100)
- `dashboard_file` path must exist under `ansible/roles/<service>/files/`
- Alert `expr` must reference only metrics that the service's scrape targets produce

### 2. Telegraf SNMP Metrics (Synology Pipeline)

Metrics produced by Telegraf's SNMP input plugin, exposed via `outputs.prometheus_client`.

| Measurement | Fields | Tags | Source |
|-------------|--------|------|--------|
| `snmp_synology_volume` | `available_bytes`, `size_bytes`, `status` | `volume`, `device`, `source` | RAID MIB table |
| `snmp_synology_network` | `rx_bytes`, `tx_bytes`, `speed_mbps` | `interface`, `device`, `source` | IF-MIB ifXTable |
| `snmp_synology_disk` | `status`, `temperature_celsius` | `disk`, `device`, `source` | Disk MIB table |
| `snmp_synology_cpu` | `usage_percent` | `device`, `source` | System MIB scalar |
| `snmp` | `memTotalReal`, `memAvailReal`, `memBuffer`, `memCached` | `device`, `source` | UCD-SNMP fields |
| `snmp` | `sysUpTime`, `sysDescr`, `sysName` | `device`, `source` | System MIB fields |

### 3. Exporter Scrape Targets (New)

| Service | Exporter | Port | Job Name | Deployment |
|---------|----------|------|----------|------------|
| AdGuard Home | `henrywhitaker3/adguard-exporter` | 9618 | `adguard-exporter` | Docker (adguard LXC) |
| Nextcloud | `xperimental/nextcloud-exporter` | 9205 | `nextcloud-exporter` | Docker sidecar (nextcloud LXC) |
| Jellyfin | `rebelcore/jellyfin_exporter` | 9594 | `jellyfin-exporter` | Go binary + systemd (jellyfin LXC) |

### 4. Port Registry

| Port | Service | Host | Direction |
|------|---------|------|-----------|
| 9100 | node_exporter | all service LXCs | scrape (monitoring→service) |
| 9273 | Telegraf SNMP | monitoring LXC | scrape (prometheus→telegraf, internal) |
| 9618 | AdGuard exporter | adguard LXC (192.168.1.210) | scrape (monitoring→adguard) |
| 9205 | Nextcloud exporter | nextcloud LXC (192.168.1.216) | scrape (monitoring→nextcloud) |
| 9594 | Jellyfin exporter | jellyfin LXC (192.168.1.215) | scrape (monitoring→jellyfin) |
| 161/UDP | SNMP | synology NAS (192.168.1.109) | poll (telegraf→synology) |

### 5. Credential Registry

| Credential | Storage | Used By | Provisioned By |
|------------|---------|---------|----------------|
| SNMP v3 auth/priv passwords | `ansible/group_vars/monitoring/vault.yml` | Telegraf SNMP input | Existing (Feature 017) |
| AdGuard admin username/password | `ansible/group_vars/services/vault.yml` | AdGuard exporter | New (this feature) |
| Nextcloud serverinfo API token | `ansible/group_vars/services/vault.yml` | Nextcloud exporter | New (this feature) |
| Jellyfin API key | `ansible/group_vars/services/vault.yml` | Jellyfin exporter | New (this feature) |

## State Transitions

### Alert Rule States

```
inactive → pending (threshold breached) → firing (for duration met) → resolved (condition cleared)
```

### Exporter Lifecycle

```
absent → deployed (ansible run) → running (systemd/docker) → scraped (prometheus discovers via contract)
```
