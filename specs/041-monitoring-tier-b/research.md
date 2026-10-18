# Research: Monitoring Tier B — External Exporters & Synology SNMP Fix

**Branch**: `041-monitoring-tier-b` | **Date**: 2026-03-01

## R2: Nextcloud Prometheus Exporter

**Decision**: Use `xperimental/nextcloud-exporter` v0.9.0

**Rationale**: De facto standard (273 stars, 38 forks), actively maintained (last release Oct 2025), Docker image available, token-based auth (no admin password exposure), covers active users, storage, health.

**Alternatives Considered**:

| Exporter | Stars | Status | Why Not |
|----------|-------|--------|---------|
| `trazfr/prometheus-nextcloud-exporter` | 4 | Maintained | Negligible adoption, no Docker image |
| Nextcloud 33 native `/metrics` | N/A | Future | Not available on NC 32 |

**Key Facts**:
- Docker image: `ghcr.io/xperimental/nextcloud-exporter:0.9.0`
- Default port: **9205**
- Auth: Serverinfo API token (preferred) or username/password
- Requires `serverinfo` Nextcloud app (bundled, enabled by default)
- Token setup: `occ config:app:set serverinfo token --value "$TOKEN"`
- Config: `NEXTCLOUD_SERVER`, `NEXTCLOUD_AUTH_TOKEN`, `NEXTCLOUD_LISTEN_ADDRESS`
- Key metrics: `nextcloud_active_users_daily_total`, `nextcloud_users_total`, `nextcloud_free_space_bytes`, `nextcloud_files_total`, `nextcloud_database_size_bytes`, `nextcloud_up`
- Gap: Does not expose cron job execution status (indirect via `nextcloud_up`)
- Recommended scrape interval: 90s (to reduce API load)

---

## R3: Jellyfin Prometheus Exporter

**Decision**: Use `rebelcore/jellyfin_exporter` v1.4.0 — Jellyfin monitoring should **PROCEED** (not descoped)

**Rationale**: The spec's descoping condition ("Given no viable community exporter exists") is **not met**. `rebelcore/jellyfin_exporter` is actively maintained (last commit Feb 2026, 15 releases), has Docker support, Grafana dashboard, and covers media/session/user metrics. Jellyfin also has a built-in `/metrics` endpoint, but it only exposes .NET runtime metrics (no application-level data).

**Alternatives Considered**:

| Exporter | Stars | Status | Why Not |
|----------|-------|--------|---------|
| `rafaelvieiras/jellyfin-exporter` | 19 | Stale (Jun 2023) | Unmaintained for 2+ years |
| Jellyfin built-in `/metrics` | N/A | .NET only | No media, session, or user metrics |

**Key Facts**:
- Docker image: `rebelcore/jellyfin-exporter` (also available as Go binary)
- Default port: **9594**
- Auth: Jellyfin API key (created via admin dashboard)
- Config: `JELLYFIN_ADDRESS`, `JELLYFIN_TOKEN`
- Key metrics: `jellyfin_media_*` (by type), `jellyfin_playing_*` (current sessions), `jellyfin_users_*`, `jellyfin_system_*`
- Deployment note: Jellyfin is APT-installed (no Docker), so exporter runs as Go binary + systemd service

---

## R4: Synology SNMP OIDs for Volume & Network Metrics

**Decision**: Use Synology RAID MIB table queries (volumes) + IF-MIB ifXTable (network), with `name` overrides to produce `snmp_synology_*` prefixed metrics. Switch from scalar field queries to SNMP table queries.

**Rationale**: The current Telegraf config uses hardcoded `.0` scalar OIDs that only get the first row, breaking with multiple disks/volumes/interfaces. Table queries enumerate all rows automatically. The Synology RAID MIB provides volume free/total size in bytes directly (Counter64), avoiding the hrStorage multiplication math.

**Alternatives Considered**:

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| Synology RAID MIB for volumes | Bytes directly, Synology-specific | DSM 7.0+ only | ✅ Chosen |
| HOST-RESOURCES-MIB hrStorage | Standard, works everywhere | Requires multiplication (size × alloc_units) | Rejected |

### OID Table: Storage Volume Capacity (RAID MIB)

| OID | MIB Name | Telegraf Field | Tag |
|-----|----------|----------------|-----|
| `1.3.6.1.4.1.6574.3.1.1.2` | raidName | — | `volume` (is_tag) |
| `1.3.6.1.4.1.6574.3.1.1.3` | raidStatus | `status` | — |
| `1.3.6.1.4.1.6574.3.1.1.4` | raidFreeSize | `available_bytes` | — |
| `1.3.6.1.4.1.6574.3.1.1.5` | raidTotalSize | `size_bytes` | — |

Measurement name: `snmp_synology_volume` → `snmp_synology_volume_available_bytes`, `snmp_synology_volume_size_bytes`

### OID Table: Network Throughput (IF-MIB ifXTable)

| OID | MIB Name | Telegraf Field | Tag |
|-----|----------|----------------|-----|
| `1.3.6.1.2.1.31.1.1.1.1` | ifName | — | `interface` (is_tag) |
| `1.3.6.1.2.1.31.1.1.1.6` | ifHCInOctets | `rx_bytes` | — |
| `1.3.6.1.2.1.31.1.1.1.10` | ifHCOutOctets | `tx_bytes` | — |
| `1.3.6.1.2.1.31.1.1.1.15` | ifHighSpeed | `speed_mbps` | — |

Measurement name: `snmp_synology_network` → `snmp_synology_network_rx_bytes`, `snmp_synology_network_tx_bytes`

### OID Table: Disk Health (Disk MIB — convert from scalar to table)

| OID | MIB Name | Telegraf Field | Tag |
|-----|----------|----------------|-----|
| `1.3.6.1.4.1.6574.2.1.1.2` | diskID | — | `disk` (is_tag) |
| `1.3.6.1.4.1.6574.2.1.1.5` | diskStatus | `status` | — |
| `1.3.6.1.4.1.6574.2.1.1.6` | diskTemperature | `temperature_celsius` | — |

Measurement name: `snmp_synology_disk` → `snmp_synology_disk_status`, `snmp_synology_disk_temperature_celsius`

### OID Table: CPU (Synology System MIB — replaces raw counters)

| OID | MIB Name | Telegraf Field |
|-----|----------|----------------|
| `1.3.6.1.4.1.6574.1.7.1` | cpuUtilization | `usage_percent` |

Measurement name: `snmp_synology_cpu` → `snmp_synology_cpu_usage_percent`

### Naming Strategy

Use the Telegraf SNMP input `name` parameter to set measurement name per input block. With `outputs.prometheus_client` (metric_version=2), metrics are exposed as `{measurement}_{field_name}`. This produces the exact metric names the dashboard expects.

### Memory Note

UCD-SNMP-MIB memory values are in KB. Use PromQL in dashboard to convert: `snmp_memTotalReal * 1024`. Alternatively, use Synology System MIB `memUtilization` (1.3.6.1.4.1.6574.1.7.2) for direct percentage. Decision: keep existing UCD-SNMP fields for detailed breakdown, adjust dashboard queries to multiply by 1024.
