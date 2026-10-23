# Contract: Backups and Their Success Signal

**Feature**: [spec.md](../spec.md) | **Date**: 2026-10-23

The observable states this feature guarantees. `092` (log aggregation) relies on C4. Any change to
these is a breaking change for the alert, the restore drills or `092`.

## C1 — Service backup on a host (every key in `service_backups`, production only)

- `/etc/systemd/system/<key>-backup.timer` is enabled and active, with exactly one
  `OnCalendar=<schedule>` and `Persistent=true`.
- `/etc/systemd/system/<key>-backup.service` is `Type=oneshot` and runs
  `/usr/local/bin/backup_<key_>.sh`.
- A run does, and only does:
  1. exits non-zero, writing nothing, if `findmnt --mountpoint <mount> --types nfs,nfs4` fails;
  2. snapshots into a private temp dir that is removed on every exit path;
  3. writes `<dir>/<key>-backup-<ts>.tar.gz.partial`, then renames it to `.tar.gz`;
  4. calls `backup-success-metric <key>`;
  5. prunes `<dir>/<key>-backup-*.tar.gz` by the GFS rule (data-model).
- Any failure in steps 1–3 exits non-zero and leaves the success record unchanged.
- In lab (`deploy_environment=lab`) none of the above is installed.

## C2 — Success record writer (every LXC and `pve`)

- `/usr/local/bin/backup-success-metric <name>` (mode 0755, installed by the `node_exporter` role).
- Writes `backup_<name>.prom` in the node_exporter textfile directory atomically, containing one
  series `backup_last_success_timestamp_seconds{backup="<name>"} <unix seconds>` with `HELP` and
  `TYPE gauge` lines.
- Exit non-zero if the directory is missing. The callers treat that as a failed run.

## C3 — Staleness alert (monitoring host)

- One rule, `BackupStale`, severity `warning`, `for: 15m`, labelled with `backup`.
- Fires when `time() - backup_last_success_timestamp_seconds{backup=X} > 129600` (36 h), or when
  `backup=X` is in the expected set (data-model) and has no series.
- `HermesBackupStale` does not exist.

## C4 — Proxmox host metrics

- node_exporter 1.12.1 (the estate pin) runs on `pve` on `:9100` with the textfile collector at
  `/var/lib/node_exporter/textfile_collector`.
- Prometheus job `node-exporter` scrapes `192.168.1.112:9100`.
- `proxmox-backup.service` may write that textfile directory (`ReadWritePaths=`); otherwise its
  sandbox is the one in `089`'s contract C1.
- `proxmox-backup.timer` has exactly one `OnCalendar=*-*-* <proxmox_backup_time>:00`.
- On a verified successful run, `backup_last_success_timestamp_seconds{backup="proxmox"}` updates.

## C5 — Restore paths

| Backup | Restore | Archive layout it relies on |
|--------|---------|-----------------------------|
| immich | `playbooks/restore-drill.yml` | `<top>/dump.sql`; `.env` rendered from `roles/immich/templates/.env.j2`, not read from the archive |
| hermes | `playbooks/hermes-restore-drill.yml`, `/usr/local/bin/restore_hermes.sh` | `<top>/open-webui/webui.db`, `<top>/agent/`, `<top>/agent-manifest.sha256` |
| nextcloud, financial-scenario, jellyfin | manual, steps in the quickstart and the service runbook | data-model table |

Restore compose templates live at `roles/service_backup/templates/restore/<key>-compose.yml.j2`.
