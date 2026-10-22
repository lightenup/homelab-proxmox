# Data Model: Backup and Log Rotation Quick Fixes

**Feature**: [spec.md](./spec.md) | **Date**: 2026-10-21

This feature adds no data store. The entities are the artifacts the fixes produce or record. Field
names describe what an operator can observe; they are not a schema.

## Proxmox configuration archive

Produced by `proxmox-backup.service` on `pve` and written to the NAS.

| Field | Value / rule |
|-------|--------------|
| Location | `/mnt/nas-backup/` on `pve`, i.e. NAS `/volume1/homelab_backups/proxmox` |
| Name | `proxmox-backup-YYYYMMDD-HHMMSS.tar.zst.age` |
| Encryption | age, to the recipient `proxmox_backup_age_public_key` |
| Validity | at least 1 KiB, decrypts with the age private key, the decrypted zstd stream lists as tar |
| Freshness (SC-001) | newest archive mtime under 24 h |
| Retention | 30 daily and 12 monthly (unchanged) |

**State of a run**: timer fires → lock acquired → collect → encrypt → transfer → verify → prune →
`Result=success`. Each failure exits non-zero, and the unit shows `Result=exit-code`.

## Immich database archive

Produced by `immich-backup.service` on the `immich` container. Read by `playbooks/restore-drill.yml`.

| Field | Value / rule |
|-------|--------------|
| Location | `/mnt/immich/backups/` (NAS bind mount in prod; local disk in lab) |
| Name | `immich-backup-YYYYMMDD-HHMMSS.tar.gz` |
| Contents | `dump.sql` (pg_dump of `immich`), `docker-compose.yml`, `.env` |
| Schedule | `*-*-* 04:30:00`, `Persistent=true` |
| Retention | 7 days, Sundays for 4 weeks, the 1st of each month for 6 months (unchanged) |
| Validity (SC-004) | the restore drill restores it and the restored Immich answers `/api/server/ping` |

**Precondition (prod)**: `/mnt/immich` is a mount. If it is not, the deploy fails (research R5).

## Container host

| Field | Value / rule |
|-------|--------------|
| In-scope set | immich, monitoring, nextcloud, financial-scenario, market-model, eurooffice, llm-router, hermes, ntfy |
| Daemon logging default | `json-file`, `max-size=10m`, `max-file=3` |
| Done when | every running container was created after the deploy that applied the default, and reports those log options |

**State**: `not-started` → `deployed` (daemon default applied, containers still have old config) →
`recreated` (every container carries the limit) → `verified` (no container's logs exceed 30 MB).

## Rollout record

A table in [quickstart.md](./quickstart.md), one row per container host: host, deploy run id,
recreate date, all containers limited (yes/no), verified ≤ 30 MB (yes/no), notes. A row is
`verified` when both yes/no columns are yes. SC-005 holds when all 9 rows are `verified`.
