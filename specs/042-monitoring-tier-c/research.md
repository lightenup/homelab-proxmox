# Research: Monitoring Tier C — Security & Availability Probing

**Feature Branch**: `042-monitoring-tier-c`
**Date**: 2026-03-02

## Research Questions & Findings

### RQ-1: HTTPS Probe Technology Choice

**Decision**: Prometheus blackbox_exporter (`prom/blackbox-exporter:v0.28.0`)

**Rationale**: The blackbox exporter is the Prometheus ecosystem's standard tool for synthetic HTTPS probing. It runs as a single container, supports the multi-target pattern (one exporter probes many URLs via relabeling), and exposes exactly the metrics needed: `probe_success`, `probe_duration_seconds`, `probe_ssl_earliest_cert_expiry`, `probe_dns_lookup_time_seconds`. It follows HTTP redirects natively and extracts TLS certificate metadata during the probe.

**Alternatives considered**:
- **Uptime Kuma**: Already decommissioned in Feature 040 (kuma_cleanup.yml). Would re-introduce a separate monitoring UI, violating the unified Prometheus/Grafana stack design.
- **Custom curl script + textfile collector**: More fragile, no redirect metrics, no TLS cert parsing. Higher maintenance.
- **Grafana Synthetic Monitoring**: Requires Grafana Cloud or a separate agent. Overkill for a homelab.

**Key configuration details**:
- Docker image: `prom/blackbox-exporter:v0.28.0` (latest stable, 2025-12-04)
- Module: `https_2xx` with `follow_redirects: true`, `fail_if_not_ssl: true`
- Port: 9115 (default)
- Memory: ~10-25 MB RSS (well within NFR-001's 50 MB limit)
- Scrape pattern: Static scrape config in prometheus.yml.j2 using Prometheus multi-target relabeling (per FR-006)
- **NOT** using monitoring contracts for probe targets because these are external URLs, not per-service exporter endpoints

### RQ-2: fail2ban Metrics Exporter Choice

**Decision**: hctrdev/fail2ban-prometheus-exporter v0.10.3 (Go binary)

**Rationale**: Most actively maintained fail2ban exporter (244 commits, 20 tags, latest release April 2025). Single static Go binary — no runtime dependencies. Reads fail2ban state directly from the Unix socket (no CLI dependency). Exposes comprehensive jail metrics: `f2b_jail_banned_current`, `f2b_jail_banned_total`, `f2b_jail_failed_current`, `f2b_jail_failed_total`, `f2b_config_jail_*`. ~10-15 MB RSS.

**Alternatives considered**:
- **jangrewe/prometheus-fail2ban-exporter (Python)**: Abandoned since July 2022 (8 commits, no releases). Would require Python runtime.
- **Textfile collector via node_exporter**: DIY approach requiring cron scripts. No real-time metrics. More fragile. node_exporter's textfile directory would need configuration.
- **prometheus-community Ansible role**: Exists but this project uses custom roles, not the prometheus-community collection. We'll follow the existing binary + systemd pattern from jellyfin-exporter.

**Key deployment details**:
- Binary download from GitLab releases
- Deployed as systemd service (matching jellyfin-exporter pattern)
- Port: 9191 (default)
- Requires root access to read fail2ban socket (`/var/run/fail2ban/fail2ban.sock`)
- No secrets needed (reads local socket, not API)
- Integrated via monitoring contract pattern (per FR-015)

### RQ-3: Nextcloud fail2ban Log Accessibility

**Decision**: Nextcloud authentication failure logs ARE accessible to fail2ban on the LXC host at `/mnt/nextcloud/data/nextcloud.log`.

**Rationale**: Nextcloud's Docker Compose maps `/mnt/nextcloud/data:/var/www/html/data`. Nextcloud writes `nextcloud.log` to its data directory by default. The log is JSON-formatted with `remoteAddr` and `message` fields that match "Login failed:" — a well-documented pattern with official fail2ban filter regex from Nextcloud docs.

**Log path on LXC host**: `/mnt/nextcloud/data/nextcloud.log`
**Contingency**: If NAS mount is unavailable, the nextcloud jail won't function but sshd jail continues. This is acceptable per FR-011's contingency clause.

### RQ-4: Jellyfin fail2ban Log Feasibility

**Decision**: Jellyfin authentication failure logs ARE parseable by fail2ban. The Jellyfin jail is FEASIBLE (upgrading from SHOULD to WILL implement).

**Rationale**: Jellyfin runs as a native Debian package (not Docker) on the Jellyfin LXC. Logs are written to `/var/log/jellyfin/log_*.log`. The auth failure pattern is: `Authentication request for .* has been denied (IP: "<ADDR>")`. This is documented in Jellyfin's official fail2ban guide. However, auth failures are logged at `Information` level — Jellyfin's logging config must be set to at least `Info` level.

**Prerequisite**: Ensure Jellyfin logging level is `Information` or lower in `/etc/jellyfin/logging.json`.

### RQ-5: fail2ban Jail Tuning Parameters

**Decision**: Conservative defaults suitable for a homelab with limited external exposure.

| Parameter | sshd | nextcloud | jellyfin |
|-----------|------|-----------|----------|
| maxretry | 5 | 3 | 3 |
| findtime | 600 (10 min) | 43200 (12 hr) | 43200 (12 hr) |
| bantime | 3600 (1 hr) | 86400 (24 hr) | 86400 (24 hr) |

**Rationale**: SSH gets standard-ish settings (5 retries, 1hr ban). Web application logins get stricter settings (3 retries, 24hr ban, 12hr window) because legitimate users rarely fail 3 times and brute-force attacks are more automated. These are operational tuning parameters (DL-10) and can be adjusted after baseline data collection.

### RQ-6: Alert Rule Metric Expressions

**Verified PromQL expressions for all 6 security alert rules**:

| Alert | Expression | Job Label |
|-------|-----------|-----------|
| EndpointDown | `probe_success{job="blackbox-https"} == 0` | blackbox-https |
| HighProbeLatency | `probe_duration_seconds{job="blackbox-https"} > 5` | blackbox-https |
| TLSCertExpiringSoon | `(probe_ssl_earliest_cert_expiry{job="blackbox-https"} - time()) / 86400 < 14` | blackbox-https |
| TLSCertExpiryCritical | `(probe_ssl_earliest_cert_expiry{job="blackbox-https"} - time()) / 86400 < 7` | blackbox-https |
| Fail2banHighBanRate | `sum by (instance) (increase(f2b_jail_banned_total[1h])) > 10` | fail2ban-exporter |
| Fail2banDown | `up{job=~"fail2ban-exporter.*"} == 0` | fail2ban-exporter-* |

### RQ-7: Inhibition Rule Design

**New inhibition rules (3 rules) follow the same structural pattern as existing rules in alertmanager.yml.j2**:

1. **EndpointDown → TLSCertExpiringSoon/TLSCertExpiryCritical**: Match on `instance` label. When an endpoint is down, certificate checks are meaningless.
2. **EndpointDown → HighProbeLatency**: Match on `instance` label. When an endpoint is down, latency is irrelevant (timeout reads as high latency).
3. **Fail2banDown → Fail2banHighBanRate**: Match on `instance` label. When the exporter is down, ban rate data is stale.
4. **Fail2banDown → ServiceDown**: Match on `instance` label. The specific Fail2banDown alert supersedes the generic ServiceDown for fail2ban exporter targets. (Follows SynologyNASDown → ServiceDown precedent from Feature 040.)

### RQ-8: Dashboard Provisioning Pattern

**Decision**: Security Overview dashboard is a built-in dashboard (like `infrastructure-overview.json` and `synology-nas.json`), deployed directly by the `grafana_provision.yml` task.

**Rationale**: The dashboard spans multiple services (blackbox probes + fail2ban across 3 hosts). It doesn't belong to any single service's monitoring contract. This follows the precedent from Feature 040 where infrastructure-overview.json and synology-nas.json are built-in dashboards deployed by the monitoring stack role directly.
