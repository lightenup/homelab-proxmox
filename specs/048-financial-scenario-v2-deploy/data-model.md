# Data Model: Financial-Scenario v2 Deploy (Stateful)

This is an infrastructure feature; the application owns its own schema. The "entities" here are the
durable artifacts the deploy creates, mounts, and backs up. Field-level scenario schema is internal to
the PFS app and is **not** managed by this repo.

## Scenario store (managed by the app, hosted by us)

- **What**: A SQLite database holding user-generated saved scenarios, created and migrated by the
  `api` service on startup (`CREATE TABLE IF NOT EXISTS`, WAL mode, run once in lifespan).
- **Host location**: `{{ financial_scenario_data_dir }}/scenarios/` (default
  `/opt/financial-scenario-data/scenarios/`), created `0755` owner `root` (matches the reference-data
  dir; the api container runs as root, so it can write `scenarios.db` there — see research FR-005).
- **Container location**: `/app/data/` (bind-mount), DB file `/app/data/scenarios.db` (app default;
  `SCENARIOS_DB_PATH` left unset).
- **Sidecar files**: `scenarios.db-wal`, `scenarios.db-shm` (WAL mode) live alongside the DB.
- **Writer**: `api` only (single writer). `mcp` never mounts or writes it.
- **Lifecycle**: created on first app start; never seeded, copied, or initialised by Ansible; never
  clobbered on upgrade. Survives container recreation and image re-pull.
- **Key record attribute (app-owned)**: each saved scenario carries a `source` of `gui` or `mcp`
  (drives the agent-authored badge in the GUI). Surfaced here only to explain US2.

## Reference data (carried over from 046, unchanged)

- **What**: App reference data baked into the api image; seeded to the host once on first deploy.
- **Host location**: `{{ financial_scenario_data_dir }}/reference_data/`.
- **Container location**: `/app/config/reference_data/` on **`api` only** in `0.2.2` (the `mcp` mount
  is removed — `mcp` no longer loads reference data).
- **Lifecycle**: seed-when-empty on first deploy; operator/catalog edits persist; never re-seeded over
  existing data.

## Backup snapshot artifact (new)

- **What**: A consistent point-in-time archive of the scenario store plus the rendered compose file.
- **Production**: SQLite online backup (`.backup()`) of `scenarios.db` → temp snapshot `.db`, tarred
  with `docker-compose.yml`, gzipped.
- **Name**: `financial-scenario-backup-YYYYMMDD-HHMMSS.tar.gz` (matches the
  `<service>-backup-<ts>.tar.gz` convention shared with nextcloud/immich for the GFS prune regex).
- **Archive contents**:
  - `scenarios.db` — the consistent snapshot (single file; WAL already merged by the online backup).
  - `docker-compose.yml` — the rendered stack definition for reference.
- **Destination**: `/mnt/financial-scenario/backups/` (in-guest NFS mount →
  `192.168.1.109:/volume1/homelab_financial_scenario`).
- **Retention**: GFS — keep `_retention_days` daily, `_retention_weeks` Sundays, `_retention_months`
  first-of-month; same policy shape as `nextcloud_backup`.
- **Integrity invariant**: a restored `scenarios.db` MUST pass `PRAGMA integrity_check` → `ok`, run via
  `docker exec financial_scenario_api python -c "import sqlite3; ..."` (no host `sqlite3` dependency).

## Configuration variables (new / changed)

Defined in `ansible/group_vars/services/vars.yml` (canonical service-version + service config home):

| Variable | Value | Notes |
|----------|-------|-------|
| `financial_scenario_version` | `"0.2.2"` (was `0.1.0`) | FR-001 |
| `financial_scenario_backup_path` | `/mnt/financial-scenario/backups` | in-guest NFS target |
| `financial_scenario_backup_nfs_server` | `192.168.1.109` | Synology |
| `financial_scenario_backup_nfs_export` | `/volume1/homelab_financial_scenario` | rw export |
| `financial_scenario_backup_retention_days` | `7` | mirror nextcloud/immich |
| `financial_scenario_backup_retention_weeks` | `4` | |
| `financial_scenario_backup_retention_months` | `6` | |
| `financial_scenario_backup_schedule` | `*-*-* 04:15:00` | offset from nextcloud 04:00 / immich 04:30 |

Existing role defaults reused unchanged: `financial_scenario_data_dir` (`/opt/financial-scenario-data`),
`financial_scenario_install_dir` (`/opt/financial-scenario`), `financial_scenario_api_image`,
`financial_scenario_gui_port`.
