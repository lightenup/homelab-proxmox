# Data Model: Monitoring Tier C — Security & Availability Probing

**Feature Branch**: `042-monitoring-tier-c`
**Date**: 2026-03-02

## Entities

### 1. HTTPS Probe Target

A public-facing URL tested by the blackbox exporter. Defined statically in Prometheus scrape config.

| Field | Type | Source | Example |
|-------|------|--------|---------|
| url | string | prometheus.yml.j2 static config | `https://grafana.hus-sky.no` |
| module | string | blackbox.yml config | `https_2xx` |
| scrape_interval | duration | prometheus.yml.j2 | `30s` |

**Initial instances** (5):
- `https://grafana.hus-sky.no`
- `https://immich.hus-sky.no`
- `https://nextcloud.hus-sky.no`
- `https://jellyfin.hus-sky.no`
- `https://adguard.hus-sky.no`

**Metrics produced per target** (via blackbox exporter):
| Metric | Type | Labels | Unit |
|--------|------|--------|------|
| `probe_success` | gauge | `instance`, `job` | boolean (0/1) |
| `probe_duration_seconds` | gauge | `instance`, `job` | seconds |
| `probe_dns_lookup_time_seconds` | gauge | `instance`, `job` | seconds |
| `probe_ssl_earliest_cert_expiry` | gauge | `instance`, `job` | Unix timestamp |
| `probe_http_status_code` | gauge | `instance`, `job` | integer |
| `probe_http_redirects` | gauge | `instance`, `job` | count |

### 2. fail2ban Jail

A fail2ban configuration unit monitoring a log source for auth failures.

| Field | Type | Source | Varies By |
|-------|------|--------|-----------|
| name | string | jail config | per jail |
| enabled | boolean | jail.d/*.local | per jail |
| logpath | string | jail.d/*.local | per jail |
| maxretry | integer | jail.d/*.local | per jail |
| bantime | integer (seconds) | jail.d/*.local | per jail |
| findtime | integer (seconds) | jail.d/*.local | per jail |
| filter | string | filter.d/*.conf | per jail |

**Jail instances**:

| Host | Jail | logpath | maxretry | bantime | findtime |
|------|------|---------|----------|---------|----------|
| reverse_proxy | sshd | /var/log/auth.log | 5 | 3600 | 600 |
| nextcloud | sshd | /var/log/auth.log | 5 | 3600 | 600 |
| nextcloud | nextcloud | /mnt/nextcloud/data/nextcloud.log | 3 | 86400 | 43200 |
| jellyfin | sshd | /var/log/auth.log | 5 | 3600 | 600 |
| jellyfin | jellyfin | /var/log/jellyfin/log_*.log | 3 | 86400 | 43200 |

### 3. fail2ban Metrics Exporter Instance

A process on each fail2ban-enabled host exposing metrics.

| Field | Type | Source | Value |
|-------|------|--------|-------|
| binary_path | string | Ansible defaults | `/opt/fail2ban-exporter/fail2ban_exporter` |
| port | integer | Ansible defaults | 9191 |
| socket_path | string | Ansible defaults | `/var/run/fail2ban/fail2ban.sock` |

**Metrics produced per exporter instance**:
| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `f2b_up` | gauge | — | Exporter is running |
| `f2b_jail_count` | gauge | — | Number of configured jails |
| `f2b_jail_banned_current` | gauge | `jail` | Currently banned IPs |
| `f2b_jail_banned_total` | gauge | `jail` | Total bans since startup |
| `f2b_jail_failed_current` | gauge | `jail` | Current failure count |
| `f2b_jail_failed_total` | gauge | `jail` | Total failures since startup |
| `f2b_config_jail_ban_time` | gauge | `jail` | Ban duration config |
| `f2b_config_jail_find_time` | gauge | `jail` | Find time config |
| `f2b_config_jail_max_retries` | gauge | `jail` | Max retries config |

### 4. Security Alert Rules

Six alert rules in a dedicated file.

| Alert Name | Condition (PromQL) | For | Severity | Source |
|------------|-------------------|-----|----------|--------|
| EndpointDown | `probe_success{job="blackbox-https"} == 0` | 2m | critical | blackbox |
| TLSCertExpiringSoon | `(probe_ssl_earliest_cert_expiry{job="blackbox-https"} - time()) / 86400 < 14` | 15m | warning | blackbox |
| TLSCertExpiryCritical | `(probe_ssl_earliest_cert_expiry{job="blackbox-https"} - time()) / 86400 < 7` | 15m | critical | blackbox |
| HighProbeLatency | `probe_duration_seconds{job="blackbox-https"} > 5` | 5m | warning | blackbox |
| Fail2banHighBanRate | `sum by (instance) (increase(f2b_jail_banned_total[1h])) > 10` | 5m | warning | fail2ban |
| Fail2banDown | `up{job=~"fail2ban-exporter.*"} == 0` | 2m | critical | fail2ban |

### 5. Inhibition Rules

Four new rules added to existing alertmanager.yml.j2.

| # | Source Alert | Target Alert(s) | Match Label | Precedent |
|---|-------------|-----------------|-------------|-----------|
| 5 | EndpointDown | TLSCertExpiringSoon, TLSCertExpiryCritical | instance | New (FR-020) |
| 6 | EndpointDown | HighProbeLatency | instance | New (FR-020) |
| 7 | Fail2banDown | Fail2banHighBanRate | instance | New (FR-021a) |
| 8 | Fail2banDown | ServiceDown | instance | SynologyNASDown→ServiceDown (FR-021b) |

## Relationships

```
Prometheus ──scrapes──> blackbox-exporter ──probes──> HTTPS Endpoints (5)
                                                       │
                                                       ├── probe_success → EndpointDown alert
                                                       ├── probe_duration_seconds → HighProbeLatency alert
                                                       └── probe_ssl_earliest_cert_expiry → TLSCert* alerts

Prometheus ──scrapes──> fail2ban-exporter (3 hosts)
                                │
                                ├── up == 0 → Fail2banDown alert
                                └── f2b_jail_banned_total → Fail2banHighBanRate alert

Alertmanager ── inhibition rules ──> suppress downstream alerts
Grafana ── Security Overview dashboard ──> queries all above metrics
```
