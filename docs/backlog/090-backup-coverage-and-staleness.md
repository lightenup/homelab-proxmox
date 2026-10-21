# Backlog: backups that fail silently, and the coverage nobody wrote down

**Status**: Backlog — raised 2026-10-21 while measuring for [`089`](./089-log-aggregation.md).
Spec only. **High priority**: the PVE host's configuration backup has not succeeded since at least
2026-01-19, and nothing noticed.
**Order**: Before [`091`](./091-monitoring-stack-version-currency.md), which wants a monitoring
backup in place before it upgrades Grafana. Independent of `089`.

## Why this exists

The estate has **no Proxmox guest backups** (`pvesh get /cluster/backup` is `[]`, and Proxmox lists
all 12 LXCs as not backed up). The owner confirmed on 2026-10-21 that this is deliberate: an LXC
is rebuilt from Terraform and Ansible, and only state that cannot be rebuilt is backed up, per
service, to the Synology. That decision is not written down anywhere. Checking it against the live
estate shows that three of the backups it relies on do not run, and that only one backup of seven
would raise an alert if it stopped.

## Current state (measured 2026-10-21)

| Host | State that cannot be rebuilt | Backup today | Live result | Age alert |
|---|---|---|---|---|
| PVE host | `/etc`, `/var/lib/pve-cluster` | `proxmox_backup`, daily, age-encrypted to NAS | **Failing since at least 2026-01-19**, every run: `line 14: /run/lock/proxmox-backup.lock: Read-only file system`. The unit has `ProtectSystem=strict` with `ReadWritePaths=` that omit the lock directory | **None.** `docs/architecture.md` says a `ServiceDown` alert on the host's node_exporter covers it, but the PVE host has no node_exporter and Prometheus does not scrape it |
| monitoring | Prometheus TSDB (15 d), Grafana state, Alertmanager silences | `backup-monitoring.sh`, cron 03:00, to `/mnt/nas/backups/monitoring` | **Never succeeded in its log**, which starts 2026-07-09: 91 nightly `Backup directory … does not exist`. `monitoring_nfs_enabled: false`, and `/mnt/nas` does not exist | None |
| immich | Postgres (photos are on NFS) | `immich_backup` role exists | **Not installed**: the role is only in `playbooks/backup.yml`, which no workflow runs. No timer or cron on the host | None |
| nextcloud | MariaDB, config (data on NFS) | `nextcloud_backup`, timer 04:00 | Success 2026-10-21 | None |
| financial-scenario | `scenarios.db` | `financial_scenario_backup`, timer 04:15 | Success 2026-10-21 | None |
| hermes | SQLite, documents, vector index | `hermes_backup`, timer 04:45 | Success 2026-10-21 | **Yes**, the only one (`hermes_backup_last_success_timestamp_seconds`, 36 h) |
| llm-router | Postgres: virtual keys, budgets, spend logs | None | — | — |
| jellyfin | Library database and config under `/var/lib/jellyfin` (media on NFS) | None | — | — |
| proxy | Caddy config (declarative); certificates (reissuable) | None | — | — |
| ntfy | None: declarative (`082` FR-010) | None, documented | — | — |
| market-model | None: disposable cache (`048`) | None, documented | — | — |
| eurooffice | None: documents live in Nextcloud (`062`) | None, documented | — | — |
| homeassistant | Empty LXC, not in the inventory | — | — | — |

Also stale: `docs/operations/monitoring/quickstart.md` § 7.2 mounts the NAS from an address that is
not the Synology's address in the inventory.

## Requirements

- **FR-001 — The decision is written down.** The backup policy ("rebuild from config, back up
  only what cannot be rebuilt") and the table above are recorded in `docs/architecture.md` §
  Backup & Monitoring. Each host is marked: backed up, rebuilt from config, or disposable, with
  the reason. The claim that `ServiceDown` covers the PVE backup is corrected.
- **FR-002 — Every host with state that cannot be rebuilt is decided.** For llm-router, jellyfin
  and proxy, decide whether their local state is rebuildable. If not, they get a backup. For
  example: are llm-router's virtual keys reconciled from vault on deploy, or only created once?
  Can losing Jellyfin's library database (watch history, users) be accepted?
- **FR-003 — Every backup that should run, runs.**
  - PVE host: the lock path is writable under the unit's sandboxing.
  - monitoring: the NAS share is mounted, or monitoring is declared rebuildable and the script
    and cron are removed.
  - immich: the backup is installed by the playbook the pipeline runs, not by a playbook nothing
    runs.
- **FR-004 — Every backup reports success as a metric.** Each backup writes a
  last-success timestamp. Prometheus can read it from every host that runs a backup, including
  the PVE host, which needs a scrape target for it (node_exporter's textfile collector, as the
  `improvement-candidates` "`pve` node_exporter" item proposes). The `hermes_backup` pattern is
  the model.
- **FR-005 — One staleness rule covers all backups.** A single `BackupStale` rule (constitution
  IV, not one copy per service) raises `warning` when any backup's last success is older than
  its schedule allows (proposal: 36 h for daily jobs). It replaces the hermes-only rule.
- **FR-006 — A backup that has never succeeded is also stale.** A missing timestamp alerts the
  same way as an old one, so a backup that has never succeeded, like monitoring's, cannot look
  healthy.

## Success criteria

- **SC-001**: For every host marked "backed up", a backup newer than 36 h exists on the NAS, and
  `BackupStale` is quiet.
- **SC-002**: Breaking one backup on purpose (on a test target) raises `BackupStale` for that
  backup only, within its window. Removing its timestamp file raises it too (FR-006).
- **SC-003**: The PVE configuration backup runs to completion from its timer, and its archive
  decrypts.
- **SC-004**: One restore per backup class is exercised and recorded: the existing
  `restore-drill.yml` for immich, plus the PVE configuration archive. Other classes are recorded
  as not drilled.
- **SC-005**: `docs/architecture.md` lists every host in the inventory with its backup class.

## Open questions

- Monitoring: mount the NAS (the role supports it behind `monitoring_nfs_enabled`) or declare it
  rebuildable? Its state is 15 days of metrics, Grafana's non-provisioned state, and silences.
- Should backup timestamps reach Prometheus through node_exporter's textfile collector on each
  host (the PVE host needs node_exporter first), or a Pushgateway?
  `improvement-candidates` lists both.
- Do this with [`073`](./073-consolidate-backup-roles.md) (consolidate the backup roles) or
  before it? FR-004 and FR-005 touch every backup role anyway.

## Dependencies

- **Closes** the "Backup job monitoring" item in `improvement-candidates.md`, and most of the
  "`pve` node_exporter" item.
- **Related**: [`073`](./073-consolidate-backup-roles.md), and [`089`](./089-log-aggregation.md),
  whose collector on the PVE host would have made these failures searchable but would not have
  alerted on them.
