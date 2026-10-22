# Backlog: three quick fixes found while measuring for 090–092

**Status**: **Delivered 2026-10-22** — see [`specs/089-backup-log-rotation-fixes/`](../../specs/089-backup-log-rotation-fixes/).
Raised 2026-10-21. Implementing it found four more defects behind the first: the backup's secret
scan aborted on non-secrets, its failure mail hung under the sandbox (now ntfy, topic
`pve-backup`), and the Immich restore drill lacked its database password and used a database
image Immich v3 cannot start on.
**Order**: Before [`090`](./090-monitoring-stack-version-currency.md),
[`091`](./091-backup-coverage-and-staleness.md) and [`092`](./092-log-aggregation.md). They were
split out of `091` and `092` so they do not wait behind feature work.

All three were measured on the live estate on 2026-10-21 (read-only, via `pct exec` on `pve`).

## 1. The PVE host's configuration backup fails on every run

`proxmox-backup.service` has failed every run since at least 2026-01-19. The journal on `pve`
starts on 2026-01-02, and no successful run appears in it:

    /usr/local/sbin/proxmox-config-backup: line 14: /run/lock/proxmox-backup.lock: Read-only file system

`roles/proxmox_backup/templates/proxmox-backup.service.j2` sets `ProtectSystem=strict` with
`ReadWritePaths={{ proxmox_backup_staging_base }} {{ proxmox_backup_nas_mount_point }}`. The
lock directory is not in that list, so it is read-only inside the unit. That is the likely cause.
The fix has to be confirmed by a successful run.

- **FR-1.1**: The unit can take its lock: add the lock path to `ReadWritePaths=`, or move the lock
  under a path that is already writable (`RuntimeDirectory=` is the systemd-native option).
- **SC-1.1**: `proxmox-backup.service` completes from its timer, an archive newer than 24 h is on
  the NAS, and it decrypts with the age key.

## 2. Immich's database backup is not installed

`roles/immich_backup` exists, with a systemd timer and a restore drill (`playbooks/restore-drill.yml`),
but it is listed only in `playbooks/backup.yml`, which no workflow runs. The `immich` LXC has no
backup timer or cron. Photos are on the Synology over NFS. What is missing is Immich's Postgres
database (albums, users, metadata).

- **FR-2.1**: `immich_backup` is applied by the playbook the pipeline runs for immich
  (`playbooks/immich.yml`), as the other backup roles are for their services.
- **SC-2.1**: `immich-backup.timer` is active on the LXC, a run succeeds, and the existing
  restore drill passes against its archive.

## 3. No Docker host rotates its container logs

No Docker host has a `daemon.json` (`docker_daemon_options: {}` in `geerlingguy.docker`'s
defaults, never overridden), and no compose file sets `logging:`. Every container uses
`json-file` with no `max-size`, so logs grow until the disk is full. Current totals: nextcloud
245 MB, financial-scenario 149 MB, market-model 73 MB, immich 57 MB, eurooffice 57 MB.

- **FR-3.1**: Every Docker host sets `json-file` rotation (`max-size`, `max-file`) through
  `docker_daemon_options` in `group_vars/services/vars.yml`. The same values apply to
  `monitoring`, which gets Docker through `monitoring_stack`.
- **FR-3.2**: Rotation applies only to containers created after the change. The rollout recreates
  each service's containers through its normal deploy, one host at a time, and records which
  hosts are done.
- **SC-3.1**: No container on any Docker host has a json-file log larger than `max-size` ×
  `max-file`.

## Open questions (answered)

- Rotation values: **`10m` × `3`** per container (contract C3 in the spec). The largest
  per-container total after rollout was 2.1 MB.
- Changing `daemon.json` **does restart the Docker daemon** at deploy, and containers keep their
  old log settings until they are recreated. The rollout did an explicit recreate per host right
  after its deploy (quickstart, Fix 3).

## Dependencies

- None. `091` builds monitoring and alerting on top of fixes 1 and 2. `092` collects the logs
  that fix 3 rotates.
