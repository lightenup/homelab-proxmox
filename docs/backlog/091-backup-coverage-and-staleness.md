# Backlog: backups that fail silently, the coverage nobody wrote down, and five copies of one role

**Status**: Backlog — raised 2026-10-21 while measuring for [`092`](./092-log-aggregation.md);
**revised 2026-10-23** after `089` and `090` landed, re-measured on the live estate, and merged
with [`073`](./073-consolidate-backup-roles.md) (consolidate the backup roles), which is now part of
this item. Spec only, ready for `/speckit-specify`.
**Order**: After [`089`](./089-backup-and-log-rotation-quick-fixes.md) and
[`090`](./090-monitoring-stack-version-currency.md), both delivered. Before
[`092`](./092-log-aggregation.md), which reuses the PVE host node_exporter this item adds.

## Why this exists

The estate has **no Proxmox guest backups** (`pvesh get /cluster/backup` is `[]`). The owner
confirmed on 2026-10-21 that this is deliberate: an LXC is rebuilt from Terraform and Ansible, and
only state that cannot be rebuilt is backed up, per service, to the Synology. That decision is not
written down anywhere, and checking it against the live estate shows two problems:

1. **Failures are silent.** Only hermes publishes a backup metric, and its rule has no `absent()`,
   so a backup that never succeeded stays quiet. Monitoring's backup has failed every night since
   at least 2026-07-09 and nothing noticed. The PVE config backup failed from 2026-01-19 until
   `089` fixed it, also unnoticed: the PVE host is not scraped at all.
2. **The four service backup roles are copies.** Adding a success timestamp, a destination check or
   a fix means four edits (`073`). Doing the timestamp once in a consolidated role is the cheaper
   path, which is why `073` is folded in here.

## Current state (measured 2026-10-23)

| Host | State that cannot be rebuilt | Backup today | Live result | Metric / alert |
|---|---|---|---|---|
| PVE host | `/etc`, `/var/lib/pve-cluster` | `proxmox_backup`, age-encrypted to NAS | Fixed by `089` (success 2026-10-22). **The timer runs twice a day**: `proxmox-backup.timer.j2` renders both `OnCalendar=daily` and `OnCalendar=*-*-* 02:00:00` | **None.** No node_exporter on the host; Prometheus' `node-exporter` job iterates only `groups['services']` |
| immich | Postgres (photos on NFS) | `immich_backup`, 04:30 | Success 2026-10-21/22/23. **The archive includes the app's `.env` (secrets), mode 644 on the share**; `.env` is rendered by Ansible from `.env.j2` | None |
| nextcloud | MariaDB, `config.php` (data on NFS) | `nextcloud_backup`, 04:00 | Success 2026-10-21/22/23. **No destination check**: the role creates the directory with mode 0777, so with the mount missing it writes to local disk | None |
| financial-scenario | `scenarios.db` | `financial_scenario_backup`, 04:15 | Success every day; the 12–16 Oct gap on the share is GFS retention, not failures | None |
| hermes | SQLite, documents, vector index | `hermes_backup`, 04:45 | Success 2026-10-21/22/23 | `HermesBackupStale` (36 h), no `absent()`. **Its NAS mount is missing from `node_filesystem_*`**, unlike every other host's |
| monitoring | Prometheus TSDB (15 d), Grafana non-provisioned state, silences | `backup-monitoring.sh`, cron 03:00 | **Never succeeded** (log from 2026-07-09: `Backup directory … does not exist`, each line twice). `monitoring_nfs_enabled: false` would not help: it is an in-guest NFS mount and the LXC is unprivileged. The script also tars live TSDB without a snapshot | None |
| jellyfin | `jellyfin.db` (24 MB: users, watch history), `/etc/jellyfin` (32 KB). Metadata (1.2 GB) and trickplay (4.1 GB) regenerate | None | — | — |
| llm-router | None that matters: keys are generated **with the vault value** and team/caps re-applied on every deploy (`llm_router/tasks/virtual_keys.yml`). Only spend logs and counters are lost, and spend is structurally 0 (`071`) | None | — | — |
| proxy | None: Caddyfile is templated, ~12 certificates reissue over DNS-01 | None | — | — |
| ntfy | None: declarative (`082` FR-010) | None, documented | — | — |
| market-model | None: disposable cache (`048`) | None, documented | — | — |
| eurooffice | None: documents live in Nextcloud (`062`) | None, documented | — | — |
| homeassistant | Empty LXC, not in the inventory | — | — | — |

Wrong in the docs: `docs/architecture.md:24-28`, `docs/operations/backups-proxmox-config.md`
(~379-382) and `backups-proxmox-config-email-decommission.md` claim a `ServiceDown` alert on the PVE
host's node-exporter target covers the PVE backup. There is no such target, and `up == 0` would
not detect a failed job anyway. `docs/operations/monitoring/quickstart.md` §7.2 describes the
in-guest NAS mount that cannot work on the unprivileged monitoring LXC (the address `.109` is
right).

### The four service roles (from `073`)

| Role | Snapshot step | Destination check | Restore path today |
|---|---|---|---|
| `financial_scenario_backup` | `docker exec` Python `sqlite3.backup()` | `findmnt --target` | none |
| `hermes_backup` | SQLite backup in the container, plus documents, agent dir, sha256 manifest | `findmnt --target` | `restore_hermes.sh`, `playbooks/hermes-restore-drill.yml` |
| `immich_backup` | `docker exec pg_dump`, plus compose and `.env` | `assert` on `ansible_mounts`, gated on `immich_require_nas_mount` | `playbooks/restore-drill.yml` |
| `nextcloud_backup` | maintenance mode on, `mariadb-dump --single-transaction`, `config.php` | **none** | none |

Identical across all four: the 44-line GFS prune block (7 daily / 4 weekly / 6 monthly; differs
only in names, comments and whitespace), `handlers/main.yml` (byte-identical), and the inline systemd
service and timer (`Type=oneshot`, `After=docker.service`, `OnCalendar` + `Persistent=true`). Their
variables live in `group_vars/services/vars.yml`, except nextcloud's (`roles/nextcloud/defaults`).

`proxmox_backup` is **not** the same shape (1,295 lines: runs on the host, age encryption,
`ProtectSystem=strict` sandbox, its own NFS mount, secret scan, manifest, `find -mtime` retention)
and stays a separate role. It has no CI path (`089` recorded a Constitution V exception).

## Decisions (owner, 2026-10-23)

- **Monitoring is rebuildable.** Remove `backup-monitoring.sh` and its cron. Dashboards, rules and
  datasources are provisioned; up to 15 days of metrics, Grafana's non-provisioned state and
  silences are accepted losses.
- **Jellyfin gets a backup** of `jellyfin.db` and `/etc/jellyfin`. Metadata and trickplay are
  regenerated.
- **llm-router and proxy are rebuildable**, with the reasons in the table above.
- **One `service_backup` role** replaces the four service roles. `proxmox_backup` stays separate
  and reuses only the timestamp writer.
- **Timestamps go through node_exporter's textfile collector**, not a Pushgateway: every LXC
  already runs it with `--collector.textfile.directory=/var/lib/node_exporter/textfile_collector`,
  and hermes uses the pattern today. The PVE host gets node_exporter for this (and for `092`).
- **The defects found while measuring are in scope**: the PVE timer double-fire, immich's `.env`
  in the archive, nextcloud's missing destination check, and hermes' unmonitored NAS mount.

## Requirements

- **FR-001 — The decision is written down.** The policy ("rebuild from config, back up only what
  cannot be rebuilt") is recorded in `docs/architecture.md` § Backup & Monitoring, with every host
  in the inventory marked backed up, rebuilt from config, or disposable, and the reason. The
  `ServiceDown` claim is corrected there and in the two operations docs; quickstart §7.2 is
  corrected or removed.
- **FR-002 — One role for service backups.** A single `service_backup` role, applied once per
  service, replaces `financial_scenario_backup`, `hermes_backup`, `immich_backup` and
  `nextcloud_backup`. It owns the systemd service and timer, handlers, destination check, GFS prune
  and timestamp; each service supplies only its snapshot step and the paths to archive. The four
  old roles are deleted, not left as wrappers. Schedules, retention, destinations and archive names
  stay as they are today, so existing archives keep pruning correctly.
- **FR-003 — Every destination is checked.** Every service backup refuses to run, and fails, when
  its destination is not the NAS mount (`findmnt --target`). This closes nextcloud's write-to-local
  path.
- **FR-004 — Every backup that should run, runs.** Jellyfin gets a backup through `service_backup`
  (consistent copy of `jellyfin.db` plus `/etc/jellyfin`, to the NAS through the same host-mount
  pattern as the others). Monitoring's script and cron are removed. The PVE timer fires once a day,
  at `proxmox_backup_time`.
- **FR-005 — No secrets in service archives.** Immich's archive no longer contains `.env`; restore
  re-renders it from Ansible. No other archive gains a credentials file.
- **FR-006 — Every backup reports success as a metric.** Each backup, `proxmox_backup` included,
  writes `backup_last_success_timestamp_seconds{backup="<name>"}` atomically to the textfile
  collector on success. The PVE host runs node_exporter and is a Prometheus scrape target.
- **FR-007 — One staleness rule covers all backups.** A single `BackupStale` rule (constitution IV)
  raises `warning` when any backup's last success is older than 36 h. It replaces
  `HermesBackupStale`.
- **FR-008 — A backup that has never succeeded is also stale.** A missing timestamp for any
  expected backup alerts the same way as an old one. The expected set comes from the same
  inventory data that configures the backups, not a second hand-kept list.
- **FR-009 — Every NAS backup mount is monitored.** Hermes' `/mnt/hermes/backups` appears in
  `node_filesystem_*` like the others; find and fix why it does not today.

## Success criteria

- **SC-001**: For every host marked "backed up", a backup newer than 36 h exists on the NAS, and
  `BackupStale` is quiet.
- **SC-002**: Breaking one backup on purpose raises `BackupStale` for that backup only, within its
  window. Removing its timestamp raises it too (FR-008).
- **SC-003**: After the switch to `service_backup`, each of the five service backups (four migrated
  plus jellyfin) produces an archive whose contents match the pre-change archive's file list
  (except immich's `.env`), and a restore of each is exercised once and recorded: the existing
  drills for immich and hermes, and a recorded manual restore for nextcloud, financial-scenario
  and jellyfin.
- **SC-004**: The PVE configuration backup runs once per day with a timestamp in Prometheus, and
  its archive passes `scripts/backup/verify_proxmox_backup.sh`.
- **SC-005**: `docs/architecture.md` lists every host in the inventory with its backup class.
- **SC-006**: The old four role directories, `backup-monitoring.sh` and `HermesBackupStale` no
  longer exist in the repo.

## Constraints and risks

- Every LXC is unprivileged: NAS backups use the host mount plus bind mount (`pct set -mpN`), never
  an in-guest NFS mount. Jellyfin needs one added.
- The PVE host changes (node_exporter, timer, timestamp) have no CI deploy path; they are applied
  by hand under `089`'s Constitution V exception. node_exporter's LXC-specific disabled collectors
  (hwmon, nvme, …) must be reconsidered for a bare-metal host.
- The migration touches four working, relied-on backups. Each service is switched and checked one
  at a time, and the first run after the switch is compared against the previous night's archive.

## Dependencies

- **Absorbs** [`073`](./073-consolidate-backup-roles.md).
- **Closes** "Backup job monitoring" in `improvement-candidates.md`, and the node_exporter part
  of "Proxmox host/guest + storage health".
- **After** `089` and `090` (both delivered).
- **Before** [`092`](./092-log-aggregation.md), whose agent on the PVE host builds on the
  node_exporter and scrape target added here.
