# Contract: Backup & Restore

## In-guest NFS mount (FR-006/FR-007)

- **TF feature flag**: `features_mount = "nfs"` on `financial_scenario_lxc` (applied host-side by the
  orchestrator via `pct set`; image-independent, no recreate).
- **Mount** (performed in `financial_scenario_backup` role):
  - src: `192.168.1.109:/volume1/homelab_financial_scenario`
  - target: `/mnt/financial-scenario/backups`
  - opts: `rw,nolock,nofail,_netdev,x-systemd.automount`
- **`nolock`**: required for a `rw` NFS mount in an unprivileged LXC — without it `mount.nfs`
  tries to start `rpc.statd` (NSM) and fails with `Operation not permitted`. A single-writer
  backup destination needs no client-side NLM/NSM locking.
- **Resilience**: `nofail` + `x-systemd.automount` → NAS-down at boot does not block the LXC.
- **Contract assertion**: `findmnt --target /mnt/financial-scenario/backups` shows the NFS source,
  rw. `showmount -e 192.168.1.109` lists the export.

## Backup script contract (`backup_financial_scenario.sh`)

Mirrors `backup_nextcloud.sh` / `backup_immich.sh` structure (`set -euo pipefail`, temp workdir, tar,
GFS prune). Steps:

1. **Consistent snapshot** — online backup inside the api container (NOT a raw copy):
   ```bash
   docker exec financial_scenario_api python -c \
     "import sqlite3; \
      s=sqlite3.connect('file:/app/data/scenarios.db?mode=ro', uri=True); \
      d=sqlite3.connect('/app/data/.backup-snapshot.db'); \
      s.backup(d); d.close(); s.close()"
   ```
   Then copy `.backup-snapshot.db` out to the workdir and **remove it from `/app/data`** (so it is not
   itself backed up next run). If `scenarios.db` does not yet exist (fresh deploy, no saves), the
   script logs and exits 0 — nothing to back up is not a failure.
2. **Include compose** — copy `{{ financial_scenario_install_dir }}/docker-compose.yml` into the
   workdir.
3. **Archive** — `tar -czf $BACKUP_DIR/financial-scenario-backup-<TS>.tar.gz -C $TEMP_DIR <name>`.
4. **GFS prune** — identical algorithm to `backup_nextcloud.sh` (`get_date` regex on the `YYYYMMDD`
   token; keep < `RETENTION_DAYS`, keep Sundays < `RETENTION_WEEKS*7`, keep 1st-of-month <
   `RETENTION_MONTHS*30`).

**Contract assertions**:
- Triggering `systemctl start financial-scenario-backup.service` writes a `*.tar.gz` to the NFS share.
- Snapshot integrity (no host `sqlite3` dependency — run inside the api container):
  `docker cp <extracted scenarios.db> financial_scenario_api:/tmp/verify.db &&
   docker exec financial_scenario_api python -c "import sqlite3; print(sqlite3.connect('/tmp/verify.db').execute('PRAGMA integrity_check').fetchone()[0])"` → `ok`.
- No `.backup-snapshot.db` left under `{{ financial_scenario_data_dir }}/scenarios`.

## systemd units (mirror nextcloud/immich)

- `financial-scenario-backup.service` — `Type=oneshot`, `After=docker.service network.target`,
  `ExecStart=/usr/local/bin/backup_financial_scenario.sh`, `User=root`.
- `financial-scenario-backup.timer` — `OnCalendar={{ financial_scenario_backup_schedule }}`,
  `Persistent=true`, enabled + started.

## Restore contract (manual / quickstart)

1. Stop stack: `docker compose -f {{ financial_scenario_install_dir }}/docker-compose.yml down`.
2. Restore over a fresh store:
   `tar -xzf <archive> -C /tmp && cp /tmp/<name>/scenarios.db {{ financial_scenario_data_dir }}/scenarios/scenarios.db`
   (ensure no stale `-wal`/`-shm` sidecars remain).
3. Integrity-check via the container (no host `sqlite3`): `docker exec financial_scenario_api python -c "import sqlite3; print(sqlite3.connect('/app/data/scenarios.db').execute('PRAGMA integrity_check').fetchone()[0])"` → `ok`.
4. Start stack; confirm restored scenarios are listed and openable in the GUI (SC-004).
