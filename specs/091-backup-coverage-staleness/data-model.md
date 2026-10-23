# Data Model: Backup Coverage and Staleness

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Date**: 2026-10-23

No database. The "entities" are configuration records in the inventory, files on hosts and the NAS,
and time series in Prometheus.

## Backup definition (`service_backups` map, `group_vars/all/vars.yml`)

One entry per service backup. The key is the backup name. Research R3.

| Field | Type | Rule |
|-------|------|------|
| key | string, `[a-z-]+` | Unique. Used as the `backup` label, and as the stem of the unit, archive and snapshot template names. |
| `host` | inventory hostname | Must be in `groups['services']`. One host may have several backups. |
| `mount` | absolute path | Must be an NFS mount point inside the LXC (bind mount from `/mnt/nas/<share>` on `pve`). Checked at deploy and at every run (R1). |
| `dir` | absolute path | Equal to `mount` or beneath it. Created with mode 0750 only after the mount check passes, and only if missing; an existing directory keeps its mode. |
| `schedule` | systemd `OnCalendar` | Unchanged for the four migrated backups (FR-005). Jellyfin: `*-*-* 05:00:00`. |

Derived, not stored: unit `<key>-backup.{service,timer}`; script `/usr/local/bin/backup_<key with _>.sh`;
archive `<dir>/<key>-backup-YYYYmmdd-HHMMSS.tar.gz`; metric file `backup_<key>.prom`.

Retention is not per entry: 7 daily / 4 weekly / 6 monthly for every backup (shared role defaults).

| Key | Host | Mount | Dir | Schedule | Snapshot contents |
|-----|------|-------|-----|----------|-------------------|
| `nextcloud` | nextcloud | `/mnt/nextcloud` | `/mnt/nextcloud/backups` | 04:00 | `dump.sql`, `config.php`, `docker-compose.yml` |
| `financial-scenario` | financial-scenario | `/mnt/financial-scenario/backups` | same | 04:15 | `scenarios.db`, `docker-compose.yml` |
| `immich` | immich | `/mnt/immich` | `/mnt/immich/backups` | 04:30 | `dump.sql`, `docker-compose.yml` (no `.env`) |
| `hermes` | hermes | `/mnt/hermes/backups` | same | 04:45 | `open-webui/`, `agent/`, `agent-manifest.sha256`, `docker-compose.yml` |
| `jellyfin` | jellyfin | `/mnt/jellyfin/backups` | same | 05:00 | `jellyfin.db`, `etc-jellyfin/` |

## Archive (file on the NAS)

- Name `<key>-backup-YYYYmmdd-HHMMSS.tar.gz`, gzip tar with one top-level directory
  `<key>-backup-YYYYmmdd-HHMMSS/`. The restore drills rely on this.
- **States**: `…tar.gz.partial` (being written; never matched by prune or drills) → `…tar.gz`
  (complete) → deleted by prune once outside every retention bucket.
- **Retention rule** (unchanged): age from the date in the filename. Keep if age < 7 days; or Sunday
  and age < 28 days; or the 1st of the month and age < 180 days.

## Success record (textfile on each host)

- File `<textfile dir>/backup_<key>.prom` (PVE: `backup_proxmox.prom`), mode 0644, written by
  `/usr/local/bin/backup-success-metric <key>` through a temp file and rename.
- Series `backup_last_success_timestamp_seconds{backup="<key>"}` = Unix time of the end of the last
  run that completed the archive. `instance` and `job` are added by the scrape.
- **States**: absent (never succeeded on this host) → present and fresh (< 36 h) → present and stale
  (≥ 36 h). Only a success moves it forward; failures leave it unchanged.

## Expected-backup set (rendered into `backup_alerts.yml`)

- Production: every key in `service_backups`, plus `proxmox` for each host in
  `groups['proxmox_hosts']`.
- Lab (`deploy_environment == 'lab'`): empty. No backups are installed there (FR-007).
- Changing the set is a change to the map or the inventory, in the same commit as the backup itself.

## Backup class (per inventory host, `docs/architecture.md`)

| Class | Hosts |
|-------|-------|
| Backed up | `proxmox` (host config), immich, nextcloud, financial-scenario, hermes, jellyfin |
| Rebuilt from configuration | monitoring, llm-router, reverse_proxy, ntfy |
| Disposable / no own state | market-model (cache), eurooffice (documents live in Nextcloud) |
| Not in scope | pi-runner, synology (infra group; listed with "not a Proxmox guest"), homeassistant (not in the inventory) |

Each row in the document carries the reason (backlog table).
