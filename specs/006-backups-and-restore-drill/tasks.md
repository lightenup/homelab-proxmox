# Tasks: Backups & Restore Drill

## Phase 1: Backup Implementation

- [x] T001 Define backup variables in `ansible/group_vars/services/vars.yml` (`immich_backup_path`, `immich_backup_retention_days`, `immich_backup_retention_weeks`, `immich_backup_retention_months`, `immich_backup_schedule`, `immich_db_container_name`).
- [x] T002 Create `ansible/roles/immich_backup` directory structure.
- [x] T003 Create `ansible/roles/immich_backup/templates/backup_immich.sh.j2` (Script to dump DB, backup `docker-compose.yml` & `.env`, compress, save to NAS, and prune old files based on D/W/M policy; MUST fail if mount is missing).
- [x] T004 Implement tasks in `ansible/roles/immich_backup/tasks/main.yml` to ensure backup directory exists and deploy the script.
- [x] T005 Implement Systemd timer/service tasks in `ansible/roles/immich_backup/tasks/main.yml` for daily execution at 04:30 AM.
- [x] T006 Create `ansible/playbooks/backup.yml` to run the backup role on demand.
- [x] T007 Run `ansible/playbooks/backup.yml` and verify a backup file is created on the NAS.

## Phase 2: Restore Drill Implementation

- [x] T008 Create `ansible/playbooks/restore-drill.yml`.
- [x] T009 Implement task to find the latest backup file in `immich_backup_path`.
- [x] T010 Create `ansible/roles/immich_backup/templates/docker-compose.restore.yml.j2` (Test stack config listening on port 2284).
- [x] T011 Implement tasks to deploy test stack, wait for DB, and restore the dump using `docker exec`.
- [x] T012 Implement task to verify `http://localhost:2284/api/server/ping` returns 200.
- [x] T013 Implement task to tear down the test stack (docker-compose down -v) ensuring it runs even if verification fails.
- [x] T014 Run `ansible/playbooks/restore-drill.yml` and verify success.

## Phase 3: Documentation

- [x] T015 Create `docs/immich-backup-restore.md` with manual restore instructions and drill explanation.
