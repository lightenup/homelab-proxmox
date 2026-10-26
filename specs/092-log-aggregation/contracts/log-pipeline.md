# Contract: Log Pipeline

**Feature**: [spec.md](../spec.md) | **Data model**: [data-model.md](../data-model.md) | **Research**: [research.md](../research.md)

This file describes the interfaces that other parts of the estate, and later features, rely on.
Each clause is checked either by a guard test (marked **[test]**) or by a quickstart step
(marked **[qs §n]**).

## C1 — Store (Loki in `monitoring_stack`)

- Image `grafana/loki:{{ loki_version }}`, service and container name `loki`, on the compose
  project's default network. **[test]**
- Ports: `127.0.0.1:3100:3100` only. The port is never bound to a LAN address. **[test]** **[qs §3]**
- Config `/opt/monitoring/loki/loki.yaml` (template `loki.yaml.j2`), mounted read-only. It must
  contain these keys **[test]**:

  ```yaml
  auth_enabled: false
  schema_config: { configs: [{ store: tsdb, object_store: filesystem, schema: v13, index: { period: 24h } }] }
  ingester: { wal: { replay_memory_ceiling: 256MB } }
  limits_config:
    retention_period: 720h
    reject_old_samples_max_age: 168h
    max_line_size: 256KB
    max_line_size_truncate: true
    ingestion_rate_mb: 4
    ingestion_burst_size_mb: 8
    per_stream_rate_limit: 1MB
    max_global_streams_per_user: 5000
    deletion_mode: filter-and-delete
  compactor:
    retention_enabled: true
    delete_request_store: filesystem
    delete_request_cancel_period: 10m
  ruler:
    storage: { type: local, local: { directory: /etc/loki/rules } }
    alertmanager_url: http://alertmanager:9093
    enable_api: true
  pattern_ingester: { enabled: false }
  analytics: { reporting_enabled: false }
  ```

- Data in the named volume `loki_data`, which is not backed up (FR-014). Rules are bind-mounted
  read-only from `/opt/monitoring/loki/rules` to `/etc/loki/rules`, with the tenant directory
  `fake/`.
- Memory limit `mem_limit: 1g`. **[test]**
- No compose healthcheck: the image has no shell (R2). Liveness is `up{job="loki"}` together with
  `ServiceDown`.
- Deploy validates `-verify-config` and `lokitool rules check` **before** `docker compose up`.
  **[test]**
- Grafana data source `Loki` (`type: loki`, `url: http://loki:3100`, `editable: false`), from
  `files/grafana/provisioning/datasources/loki.yml` with its own copy task. **[test]**

## C2 — Push endpoint (relay)

- `http://{{ monitoring_host_ip }}:{{ alloy_relay_port }}/loki/api/v1/push` (`3101`), served by the monitoring host's
  Alloy (`loki.source.api`). Only Loki's push API is served on this port. Query, delete and
  rules endpoints are not reachable from the LAN. **[qs §3]**
- The relay forwards with incoming labels and timestamps kept, and has
  `max_backoff_retries = 0`.

## C3 — Collector (Alloy, every expected host)

- Installed from `https://github.com/grafana/alloy/releases/download/v{{ alloy_version }}/alloy-{{ alloy_version }}-1.amd64.deb`,
  checksum verified against the release `SHA256SUMS`. **[test]**
- Runs as the `alloy` user, in groups `adm` and `systemd-journal`, plus `docker` when
  `alloy_docker_logs`. **[test]** **[qs §2]**
- systemd drop-in with `MemoryHigh={{ alloy_memory_high }}` and `MemoryMax={{ alloy_memory_max }}`.
  **[test]**
- HTTP server on `{{ ansible_host }}:{{ alloy_http_port }}` (`12345`, `group_vars/all`). Prometheus scrapes `/metrics` from it.
- Per-host throttle: `stage.limit { rate = {{ alloy_rate_limit }}  burst = {{ alloy_rate_burst }}  drop = false }`
  first in the shared pipeline (R9). **[test]**
- On Docker hosts, the deploy fails if any running container has no `max-size` log option
  (FR-003, R9). The check is skipped when Docker is not installed yet. **[test]**
- Sources:
  - journal (`max_age = "{{ alloy_journal_max_age }}"`);
  - Docker over the socket when `alloy_docker_logs`;
  - files from `alloy_file_logs`.

  Every source passes through all `alloy_redaction_patterns` before `loki.write`.
  **[test]** **[qs §5]**
- `loki.write` endpoint `max_backoff_retries = 0`. No WAL and no experimental stability flag.
  **[test]**
- `alloy validate` runs before the restart handler.
- Labels exactly as in data-model §1.
- On pve only: the VMID→name map for `oom-kill:` lines, rendered from `pct list` at deploy.
- Installed only when `deploy_environment != 'lab'`. **[test]**

## C4 — Log rules file (Loki ruler)

- Single file `/opt/monitoring/loki/rules/fake/log_alerts.yaml`, from `log_alerts.yaml.j2`. It
  is not rendered on the LAB path. **[test]**
- Groups:
  - `log_estate`:
    - `KernelOomKill`, warning;
    - `SshLoginNotAllowed`, warning, one rule each for the LXCs and for pve;
    - `SudoByUnexpectedUser`, warning, one rule each for the LXCs and for pve.
  - `log_services`: every `monitoring_contract.log_alert_rules` entry with `enabled: true`.
- Every rule has a `severity` label. Annotations `summary` and `description` are present.
  `summary` names the host and, where it applies, the LXC, user, source, key or service.
- `SshLoginNotAllowed` expression shape, rendered from `ssh_login_allowlist` (illustrative):

  ```logql
  sum by (host, user, src, method, fp) (count_over_time(
    {env="prod", host!="proxmox", ident=~"sshd|sshd-session"} |= "Accepted "
    | regexp `Accepted (?P<method>\S+) for (?P<user>\S+) from (?P<src>\S+) port \d+ ssh2(?:: \S+ (?P<fp>SHA256:\S+))?`
    | (user!~"root|ansible" or fp!="SHA256:NH5z…" or src!="192.168.1.112")
    | (user!="root" or fp!~"SHA256:cqi3…|SHA256:3\\+Ln…" or (src!=ip("192.168.1.0/24") and src!="192.168.1.112"))
    [5m])) > 0
  ```

  Each entry renders one clause, which is true when the login does **not** match the entry. A
  login alerts only when every clause is true. The literal `ssh2` before the optional key group
  is required: with `\S+` there, the fingerprint is never captured (R3, tested with Go
  `regexp`).
- `SudoByUnexpectedUser` expression shape:
  `{…, ident="sudo"} | regexp "^\\s*(?P<sudo_user>\\S+) : " | sudo_user != "" | sudo_user != "<expected>"`.
  The `sudo_user != ""` filter drops the PAM session lines, which share the identifier (R3).
  **[test]**
- `lokitool rules lint` is never run against this file (R10). **[test]**

## C5 — Pipeline alerts (Prometheus)

- `alerts/log_pipeline_alerts.yml` from `log_pipeline_alerts.yml.j2`, with the rules in research
  R14 and `component: logging`. It is validated by the existing promtool loop. **[test]**
- New scrape jobs in `prometheus.yml.j2` **[test]**:
  - `loki`: target `loki:3100`.
  - `alloy`: one target `<ansible_host>:{{ alloy_http_port }}` per expected host, `instance` =
    inventory hostname, `no_down_alert: "true"`. The same targets on every path (R12).
- `log_pipeline_alerts.yml` is rendered only when `deploy_environment != 'lab'`. A LAB-path run
  leaves the production file as it is (FR-017, SC-009). **[test]**

## C6 — Per-service declaration (consumed from `host_vars`)

- `monitoring_contract.log_alert_rules`: data-model §3. **[test]**
- `alloy_file_logs`: `nextcloud` (`/mnt/nextcloud/data/nextcloud.log`, `tail_from_end: true`)
  and `jellyfin` (`/var/log/jellyfin/*.log`). **[test]**

## C7 — SSH configuration (LXCs only)

- `lxc_base` installs `/etc/ssh/sshd_config.d/10-homelab-auth.conf` with
  `PasswordAuthentication no` and `KbdInteractiveAuthentication no`, validated by `sshd -t` and
  applied by an `ssh` reload. It runs on every path. **[test]** **[qs §2]**
- Nothing targeting `proxmox_hosts` sets `PasswordAuthentication`. **[test]**
