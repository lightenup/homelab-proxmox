---
description: "Task list for 091 backup coverage and staleness"
---

# Tasks: Backup Coverage and Staleness

**Input**: Design documents from `/specs/091-backup-coverage-staleness/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/backup-contract.md](./contracts/backup-contract.md),
[quickstart.md](./quickstart.md)

**Tests**: One new guard test file, `python/tests/guardrails/test_service_backup.py` (FR-017,
research R12), written in Phase 2 and seen to fail before the code. The `089` guard file
`test_backup_log_rotation_config.py` is updated where it names moved paths. Everything else is
static checks plus the live checks in `quickstart.md`.

**Organization**: Code phases follow the spec's user stories. All code merges in one PR. The live
rollout (Phase 8) then deploys host by host in the quickstart order: PVE → financial-scenario →
hermes → immich → nextcloud → jellyfin → monitoring. **Monitoring is deployed last**, or
`BackupStale` fires for every backup not yet switched.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1–US5, from spec.md
- Paths are repo-relative. Ansible commands run from `ansible/` unless stated.

## Path Conventions

- Ansible: `ansible/roles/`, `ansible/playbooks/`, `ansible/group_vars/`, `ansible/host_vars/`
- Tests: `python/tests/guardrails/`
- Docs: `docs/architecture.md`, `docs/operations/`, `docs/runbooks/`, `docs/backlog/`
- Live results: the Record table in `specs/091-backup-coverage-staleness/quickstart.md` §5
- Where live commands run: **PVE** (`host_proxmox.yml`, `backup_proxmox.yml`) only from an operator
  machine with root SSH to `pve` (192.168.1.112) and `ansible/.vault-pass.txt` (principle V
  exception). **Services and monitoring** through the normal pipeline (`Prod 1 → Prod 2`).
  **Synology** steps by hand in DSM.

---

## Phase 1: Setup

**Purpose**: Baseline before editing, and the two live facts the code depends on.

- [X] T001 Confirm the branch is `091-backup-coverage-staleness` and rebased on `origin/main` (`git fetch origin main && git log --oneline origin/main -1`). From `ansible/`, run `ansible-playbook -i inventories/prod/hosts.yml --syntax-check` on `playbooks/{nextcloud,financial-scenario,immich,hermes,jellyfin,monitoring,host_proxmox,backup_proxmox}.yml` and `bash scripts/ci/python-tests.sh` from the repo root. Record any pre-existing failure in `specs/091-backup-coverage-staleness/quickstart.md` §5 so it is not blamed on this feature.
- [X] T002 Run quickstart §0.1 on hermes (as root: `ls -ld /mnt/hermes/backups`, `runuser -u node_exporter -- stat -f /mnt/hermes/backups`, `journalctl -u node_exporter --since -1h | grep -i hermes`) and compare the Synology NFS export of `homelab_hermes` with `homelab_financial_scenario`. Record the confirmed cause in quickstart §5 row "0.1". This task is read-only; the fix is T030.
- [X] T003 On jellyfin (192.168.1.215), as root, run `ls -l /var/lib/jellyfin/data/jellyfin.db /etc/jellyfin` and `grep -ril -E 'password|apikey|secret' /etc/jellyfin || true`. Record the actual DB path, and whether `/etc/jellyfin` holds any credential, in quickstart §5 (notes of the jellyfin row). If the DB path differs from `/var/lib/jellyfin/data/jellyfin.db`, use the recorded path in T031. If `/etc/jellyfin` holds a credential, stop and raise it with the owner before T031 (FR-008).
- [X] T004 Read quickstart §0.3 and confirm, on each of nextcloud, financial-scenario, immich and hermes, that the old backup service can be started by hand (`systemctl cat <key>-backup.service`) and that `/root` has room for a file list. The baseline itself is taken in each Phase 8 task, immediately before that service's deploy, not now: hermes' data gains files daily, so last night's archive is not a usable baseline (FR-006).

---

## Phase 2: Foundational (guard test, map, writer)

**Purpose**: Shared pieces every story uses: the guard test (seen red first), the `service_backups`
map and the success-metric writer.

- [X] T005 Create `python/tests/guardrails/test_service_backup.py`, modelled on `python/tests/guardrails/test_backup_log_rotation_config.py` (same `_find_repo_root` helper, `from __future__ import annotations`, `pathlib`, `yaml.safe_load`; text assertions on `.j2` files). One function per group, each with a docstring naming the requirement:
  1. `test_old_backup_roles_removed` (FR-003, SC-006): none of `ansible/roles/{financial_scenario_backup,hermes_backup,immich_backup,nextcloud_backup}` exist; `ansible/roles/monitoring_stack/templates/backup-monitoring.sh.j2` and `ansible/roles/monitoring_stack/tasks/backup_cron.yml` do not exist; no file under `ansible/` contains `HermesBackupStale` or `hermes_backup_last_success`.
  2. `test_service_backups_map_shape` (FR-005, data-model): `ansible/group_vars/all/vars.yml` defines `service_backups`; every key matches `^[a-z-]+$`; every entry has exactly `host`, `mount`, `dir`, `schedule`; `dir == mount` or `dir.startswith(mount + "/")`; `host` is a host under `services` in `ansible/inventories/prod/hosts.yml`. Assert the four migrated schedules are unchanged: nextcloud `*-*-* 04:00:00`, financial-scenario `*-*-* 04:15:00`, immich `*-*-* 04:30:00`, hermes `*-*-* 04:45:00`.
  3. `test_every_backup_has_a_snapshot_and_a_playbook` (FR-003, FR-007): for each key, `ansible/roles/service_backup/templates/snapshot/<key>.sh.j2` exists and defines `snapshot()`; exactly one playbook in `ansible/playbooks/` applies role `service_backup` with `service_backup_name: <key>`, and that role entry has a `when` containing `deploy_environment` and `lab`. No playbook references a removed role name.
  4. `test_backup_script_order` (FR-004, contract C1): in `ansible/roles/service_backup/templates/backup.sh.j2`, there is exactly one line starting `BACKUP_MOUNT=`; `findmnt --mountpoint "$BACKUP_MOUNT" --types nfs,nfs4` appears; and the text offsets satisfy mount check < `snapshot` call < `.tar.gz.partial` < `mv ` < `backup-success-metric` < the prune loop. The script contains `set -euo pipefail` and a `trap`.
  5. `test_role_checks_mount_at_deploy` (FR-004): `ansible/roles/service_backup/tasks/main.yml` has a task running `findmnt --mountpoint` with `--types nfs,nfs4` before any task that creates the backup directory or the script, and no task uses mode `0777`.
  6. `test_backup_alert_from_inventory` (FR-013, FR-014, contract C3): `ansible/roles/monitoring_stack/templates/backup_alerts.yml.j2` contains `alert: BackupStale`, `129600`, `absent(backup_last_success_timestamp_seconds`, `service_backups` and `proxmox_hosts`, `deploy_environment`, and no literal `backup="nextcloud"` (or any other key from the map).
  7. `test_pve_timer_single_oncalendar` (FR-011): in `ansible/roles/proxmox_backup/templates/proxmox-backup.timer.j2`, the `OnCalendar=*-*-* {{ proxmox_backup_time }}:00` line and the `proxmox_backup_schedule` branches are in mutually exclusive branches of one `{% if proxmox_backup_time is defined %} … {% else %} … {% endif %}`.
  8. `test_pve_backup_reports_success` (FR-012): `ansible/roles/proxmox_backup/templates/proxmox-config-backup.sh.j2` calls `backup-success-metric proxmox` after `verify_backup` in `main()`; `ansible/playbooks/host_proxmox.yml` applies role `node_exporter`; `ansible/roles/monitoring_stack/templates/prometheus.yml.j2` node-exporter job references `proxmox_hosts`.
  9. `test_writer_installed_by_node_exporter` (contract C2): `ansible/roles/node_exporter/files/backup-success-metric` exists, writes to a `.tmp` file and `mv`s it, and contains `backup_last_success_timestamp_seconds{backup=`; `ansible/roles/node_exporter/tasks/main.yml` installs it to `/usr/local/bin/backup-success-metric` with mode `0755`.
  10. `test_immich_archive_has_no_env` (FR-008): `ansible/roles/service_backup/templates/snapshot/immich.sh.j2` does not contain `.env`; `ansible/playbooks/restore-drill.yml` renders `roles/immich/templates/.env.j2` and does not copy `.env` from the extracted archive.

  Run `.venv/bin/python -m pytest -c python/pytest.ini --no-cov python/tests/guardrails/test_service_backup.py` and confirm all 10 **fail** for the expected reasons. Do not mark done until seen red.
- [X] T006 Add the `service_backups` map to `ansible/group_vars/all/vars.yml` under a `# Service backups (091)` comment, with the four migrated entries only (jellyfin is added in T033): `nextcloud: {host: nextcloud, mount: /mnt/nextcloud, dir: /mnt/nextcloud/backups, schedule: "*-*-* 04:00:00"}`, `financial-scenario: {host: financial-scenario, mount: /mnt/financial-scenario/backups, dir: /mnt/financial-scenario/backups, schedule: "*-*-* 04:15:00"}`, `immich: {host: immich, mount: /mnt/immich, dir: /mnt/immich/backups, schedule: "*-*-* 04:30:00"}`, `hermes: {host: hermes, mount: /mnt/hermes/backups, dir: /mnt/hermes/backups, schedule: "*-*-* 04:45:00"}`. Add a one-line comment: the key is the `backup` label and the stem of unit/archive/snapshot names, and the same map drives `BackupStale`'s expected set. Data-model rule to keep verbatim: "`dir` Equal to `mount` or beneath it."
- [X] T007 [P] Create `ansible/roles/node_exporter/files/backup-success-metric` (Bash, `set -euo pipefail`): usage `backup-success-metric <name>`; reject a name not matching `^[a-z-]+$`; `DIR=/var/lib/node_exporter/textfile_collector`; exit 1 if `$DIR` is missing; write `# HELP backup_last_success_timestamp_seconds Unix time of the last successful backup run.`, `# TYPE backup_last_success_timestamp_seconds gauge` and `backup_last_success_timestamp_seconds{backup="<name>"} $(date +%s)` to `$DIR/backup_<name>.prom.tmp`, `chmod 0644`, then `mv -f` to `$DIR/backup_<name>.prom` (contract C2). In `ansible/roles/node_exporter/tasks/main.yml`, after the textfile directory task, add an `ansible.builtin.copy` installing it to `/usr/local/bin/backup-success-metric`, owner root, mode `0755`. It is a plain file with the literal path `/var/lib/node_exporter/textfile_collector`, not a template: `node_exporter_textfile_directory` is never overridden in the repo (check with `grep -rn node_exporter_textfile_directory ansible/` and stop if it is), and T009 relies on the same default.

**Checkpoint**: Guard is red; the map and writer exist. Stories can start.

---

## Phase 3: User Story 1 - A failed or missing backup raises an alert (Priority: P1) 🎯 MVP

**Goal**: Every backup's success is a metric; one `BackupStale` rule covers stale and never-succeeded
backups; the PVE host is scraped; hermes' NAS mount is monitored (FR-012–FR-015, SC-001, SC-002,
SC-004).

**Independent Test**: Guard tests 6–9 pass. After the PVE deploy and the monitoring deploy (Phase 8),
the PVE target is up, `backup_last_success_timestamp_seconds{backup="proxmox"}` is fresh, and the
deliberate break of quickstart §4.1 fires `BackupStale` for that backup only.

### Implementation for User Story 1

- [X] T008 [US1] In `ansible/roles/proxmox_backup/templates/proxmox-config-backup.sh.j2` `main()`, directly after `verify_backup` returns successfully and before the final "Backup process complete" log, add `/usr/local/bin/backup-success-metric proxmox`. Its failure must fail the run (it runs under `set -e`). Do not touch `cleanup()` or the success notification.
- [X] T009 [US1] In `ansible/roles/proxmox_backup/templates/proxmox-backup.service.j2`, append `{{ node_exporter_textfile_directory | default('/var/lib/node_exporter/textfile_collector') }}` to the existing `ReadWritePaths=` line. Change nothing else in the sandbox. Update `test_pve_backup_unit_sandbox` in `python/tests/guardrails/test_backup_log_rotation_config.py` so its exact expected line includes the new path.
- [X] T010 [P] [US1] In `ansible/playbooks/host_proxmox.yml`, add role `node_exporter` to the play targeting `proxmox_hosts`, after `proxmox_host`. In `ansible/group_vars/proxmox_hosts/vars.yml`, add `node_exporter_disabled_collectors: [infiniband, fibrechannel, wifi]` with a comment: bare metal, so hwmon, thermal_zone, nvme, mdadm and powersupplyclass stay on (research R6).
- [X] T011 [P] [US1] In `ansible/roles/monitoring_stack/templates/prometheus.yml.j2`, extend the `node-exporter` job's target loop (lines ~47-55) from `groups['services']` to `groups['services'] + (groups['proxmox_hosts'] if (deploy_environment | default('prod')) != 'lab' else [])`, keeping the existing `monitoring_contract.enabled` skip (default true) and `ansible_host:node_exporter_port` target form.
- [X] T012 [US1] Create `ansible/roles/monitoring_stack/templates/backup_alerts.yml.j2` (research R5, contract C3): one group `backup_alerts`, one rule `BackupStale`. Build `expected` as `service_backups.keys() | list` plus `['proxmox']` when `groups['proxmox_hosts'] | default([]) | length > 0`, and set it to `[]` when `deploy_environment | default('prod') == 'lab'`. Expression: `(time() - max by (backup) (backup_last_success_timestamp_seconds) > 129600)` followed by one `or absent(backup_last_success_timestamp_seconds{backup="<name>"})` per expected name. `for: 15m`, `labels: {severity: warning}`. Summary `Backup {{ $labels.backup }} has not succeeded in 36 hours`; description says it also fires when a backup has never succeeded, and to check `journalctl -u <backup>-backup.service` on the host (PVE: `proxmox-backup.service`). Wrap Prometheus `{{ $labels… }}` in `{% raw %}…{% endraw %}`. If the expected list is empty, render the rule with only the staleness term.
- [X] T013 [US1] In `ansible/roles/monitoring_stack/tasks/compose_stack.yml`, next to the task that renders `service_alerts.yml.j2`, add an `ansible.builtin.template` task rendering `backup_alerts.yml.j2` to the same `alerts/` directory as `backup_alerts.yml`, with the same owner/mode and the same notify handler. Confirm `tasks/validate_alerts.yml` checks it through its `alerts/*.yml` loop (no change expected).
- [X] T014 [P] [US1] Delete the `HermesBackupStale` rule and the comment block above it (lines ~47-62) from `ansible/host_vars/hermes.yml`. Leave `HermesAgentCronStale` and the other rules unchanged.

**Checkpoint**: Guard tests 6–9 pass. The rule renders and passes `promtool check rules` locally (quickstart §1).

---

## Phase 4: User Story 2 - One backup mechanism that refuses a wrong destination (Priority: P1)

**Goal**: `service_backup` replaces the four roles; exact NFS mount check at deploy and per run;
names, schedules, retention unchanged (FR-003–FR-007, SC-003, SC-006).

**Independent Test**: Guard tests 1–5 pass. After each service's deploy (Phase 8), its archive file
list matches the baseline, and the non-mount copy of the script (quickstart §3) exits non-zero.

### Implementation for User Story 2

- [X] T015 [US2] Create `ansible/roles/service_backup/defaults/main.yml` with `service_backup_retention_days: 7`, `service_backup_retention_weeks: 4`, `service_backup_retention_months: 6` (one place for all backups, research R2), and `ansible/roles/service_backup/handlers/main.yml` copied byte-for-byte from `ansible/roles/hermes_backup/handlers/main.yml` (`Reload systemd`, `daemon_reload: true`).
- [X] T016 [US2] Create `ansible/roles/service_backup/templates/backup.sh.j2` (contract C1). Set `_e = service_backups[service_backup_name]`. Order: `#!/bin/bash`, `set -euo pipefail`; `NAME={{ service_backup_name }}`; `BACKUP_MOUNT={{ _e.mount }}` (exactly one line starting `BACKUP_MOUNT=`); `BACKUP_DIR={{ _e.dir }}`; `if ! findmnt --mountpoint "$BACKUP_MOUNT" --types nfs,nfs4 >/dev/null; then echo "…not an NFS mount…" >&2; exit 2; fi`; `[ -d "$BACKUP_DIR" ] || mkdir -m 0750 "$BACKUP_DIR"` (create only, never chmod an existing one); `TIMESTAMP=$(date +%Y%m%d-%H%M%S)`, `BACKUP_NAME="${NAME}-backup-${TIMESTAMP}"`; `TEMP_DIR=$(mktemp -d)`, `WORK_DIR="$TEMP_DIR/$BACKUP_NAME"`, `mkdir "$WORK_DIR"`; a `cleanup()` that removes `$TEMP_DIR` and any `$BACKUP_DIR/$BACKUP_NAME.tar.gz.partial` and calls `snapshot_cleanup` if defined, set with `trap cleanup EXIT`; `{% include 'snapshot/' ~ service_backup_name ~ '.sh.j2' %}`; `snapshot`; `tar -czf "$BACKUP_DIR/$BACKUP_NAME.tar.gz.partial" -C "$TEMP_DIR" "$BACKUP_NAME"`; `mv "$BACKUP_DIR/$BACKUP_NAME.tar.gz.partial" "$BACKUP_DIR/$BACKUP_NAME.tar.gz"`; `/usr/local/bin/backup-success-metric "$NAME"`; then the GFS prune block carried over from `ansible/roles/hermes_backup/templates/backup_hermes.sh.j2` (`get_date` through `done`) with the glob quoted as `"$BACKUP_DIR"/"$NAME"-backup-*.tar.gz`, `shopt -s nullglob`, and the retention numbers from the T015 defaults. Retention rule to keep verbatim (data-model): "Keep if age < 7 days; or Sunday and age < 28 days; or the 1st of the month and age < 180 days."
- [X] T017 [US2] Create `ansible/roles/service_backup/tasks/main.yml`: (1) `set_fact` `_service_backup: "{{ service_backups[service_backup_name] }}"`; (2) `assert` `inventory_hostname == _service_backup.host`; (3) `command: findmnt --mountpoint {{ _service_backup.mount }} --types nfs,nfs4`, `changed_when: false`, `failed_when: rc != 0`, with a `fail_msg`-style message (via a following `fail` task or `failed_when` + `msg`) saying the bind mount is missing and to check `service_mountpoints.<host>` in the rendered `prod.tfvars`; (4) `stat` `_service_backup.dir`; only if it does not exist, `file` `state: directory`, mode `0750`. An existing directory keeps its owner and mode (Nextcloud's is `0777` today), so a root-squashing export cannot fail the deploy on a mode change; (5) `template` `backup.sh.j2` → `/usr/local/bin/backup_{{ service_backup_name | replace('-', '_') }}.sh`, mode `0750`; (6) `copy` content of `/etc/systemd/system/{{ service_backup_name }}-backup.service` (`[Unit] Description=… backup`, `After=docker.service network.target`; `[Service] Type=oneshot`, `User=root`, `ExecStart=<script>`) and `.timer` (`OnCalendar={{ _service_backup.schedule }}`, `Persistent=true`, `[Install] WantedBy=timers.target`), both notifying `Reload systemd`; (7) `flush_handlers`; (8) `systemd` timer `enabled: true`, `state: started`. Unit content must match today's units apart from the description text.
- [X] T018 [P] [US2] Create `ansible/roles/service_backup/templates/snapshot/financial-scenario.sh.j2`: a `snapshot()` function carrying over the steps of `ansible/roles/financial_scenario_backup/templates/backup_financial_scenario.sh.j2` verbatim (container `financial_scenario_api`, the "no `scenarios.db` yet → `exit 0`" branch, `docker exec … python` `sqlite3` backup to `/app/data/.backup-snapshot.db`, `docker cp` to `$WORK_DIR/scenarios.db`, remove the sidecar, copy `{{ financial_scenario_install_dir }}/docker-compose.yml` if present). Sidecar removal goes in `snapshot_cleanup()`.
- [X] T019 [P] [US2] Create `ansible/roles/service_backup/templates/snapshot/hermes.sh.j2`: `snapshot()` carrying over `ansible/roles/hermes_backup/templates/backup_hermes.sh.j2` steps verbatim (open-webui sqlite snapshot and tar-pipe with its excludes, `agent/` tar-pipe with its excludes, `agent-manifest.sha256`, host `python3` snapshots of agent DBs, `docker-compose.yml`, the "no `webui.db` → `exit 0`" branch). Drop `report_metric`, `report_failure_if_no_prior_success`, `METRICS_DIR` and the `hermes_backup_*` metric names entirely.
- [X] T020 [P] [US2] Create `ansible/roles/service_backup/templates/snapshot/immich.sh.j2`: `snapshot()` running `docker exec {{ immich_db_container_name }} pg_dump -U postgres immich > "$WORK_DIR/dump.sql"` and copying `{{ immich_install_dir }}/docker-compose.yml`. It MUST NOT copy `.env` (FR-008).
- [X] T021 [P] [US2] Create `ansible/roles/service_backup/templates/snapshot/nextcloud.sh.j2`: `snapshot()` carrying over `ansible/roles/nextcloud_backup/templates/backup_nextcloud.sh.j2` verbatim (read `MYSQL_*` from `{{ nextcloud_install_dir }}/.env`, fail if missing; `occ maintenance:mode --on`; `mariadb-dump --single-transaction --default-character-set=utf8mb4` to `$WORK_DIR/dump.sql`; `config.php` via `docker exec … cat`; `docker-compose.yml`). Maintenance mode off goes in `snapshot_cleanup()` so it runs on every exit. Container names from `nextcloud_app_container_name` / `nextcloud_db_container_name` (they stay in `roles/nextcloud/defaults/main.yml`).
- [X] T022 [US2] Move restore templates into the shared role (`git mv`): `ansible/roles/immich_backup/templates/docker-compose.restore.yml.j2` → `ansible/roles/service_backup/templates/restore/immich-compose.yml.j2`; `ansible/roles/hermes_backup/templates/docker-compose.restore.yml.j2` → `ansible/roles/service_backup/templates/restore/hermes-compose.yml.j2`; `ansible/roles/hermes_backup/templates/restore_hermes.sh.j2` → `ansible/roles/service_backup/templates/restore/restore_hermes.sh.j2`. In `ansible/roles/service_backup/tasks/main.yml` add a task, `when: service_backup_name == 'hermes'`, installing `restore_hermes.sh.j2` to `/usr/local/bin/restore_hermes.sh` mode `0755` as the hermes role did. Update `src:` in `ansible/playbooks/restore-drill.yml` and `ansible/playbooks/hermes-restore-drill.yml`, and the path in `test_immich_restore_drill_uses_the_service_images` in `python/tests/guardrails/test_backup_log_rotation_config.py`.
- [X] T023 [US2] In each of `ansible/playbooks/{financial-scenario,hermes,immich,nextcloud}.yml`, replace the old backup role in the roles list with `- role: service_backup` / `service_backup_name: <key>` / `when: (deploy_environment | default('prod')) != 'lab'`, in the same position (after the service role; before `fail2ban` in nextcloud). Keep `immich_require_nas_mount` / `nextcloud_require_nas_mount` play vars (their service roles still read them).
- [X] T024 [US2] Delete `ansible/roles/{financial_scenario_backup,hermes_backup,immich_backup,nextcloud_backup}` (`git rm -r`). Remove the now-unused vars: `financial_scenario_backup_*`, `hermes_backup_*` (keep `hermes_restore_test_port` if the drill uses it), `immich_backup_*` (keep `immich_db_container_name` and `immich_restore_test_port`) from `ansible/group_vars/services/vars.yml`, and `nextcloud_backup_*` from `ansible/roles/nextcloud/defaults/main.yml`. `grep -rn` each removed name under `ansible/` and `python/` and fix every remaining reference.
- [X] T025 [US2] Update the remaining `089` guard tests in `python/tests/guardrails/test_backup_log_rotation_config.py` that name `immich_backup`: `test_immich_playbook_applies_backup_role` now asserts the `Configure Immich` play applies `service_backup` with `service_backup_name: immich` after `immich`; `test_immich_backup_role_asserts_nas_mount` now asserts the `service_backup` mount-check task (or is removed if T005 test 5 covers it — keep one, not both).

**Checkpoint**: Guard tests 1–5 and 10 (snapshot part) pass; `ansible-playbook --syntax-check` passes on the four playbooks.

---

## Phase 5: User Story 3 - Every non-rebuildable host backed up, once a day (Priority: P2)

**Goal**: Jellyfin backed up; monitoring's backup removed; PVE timer fires once (FR-009–FR-011).

**Independent Test**: Guard tests 1 and 7 pass, and test 3 passes with the jellyfin entry. After the
jellyfin deploy, quickstart §3 jellyfin checks pass; on `pve` the timer has one `OnCalendar=`.

### Implementation for User Story 3

- [X] T026 [P] [US3] In `ansible/roles/proxmox_backup/templates/proxmox-backup.timer.j2`, restructure the `[Timer]` block to `{% if proxmox_backup_time is defined %}OnCalendar=*-*-* {{ proxmox_backup_time }}:00{% else %}` + the existing `daily`/`weekly`/`hourly`/custom branches + `{% endif %}`. Keep `Persistent=true` and `RandomizedDelaySec=300` (research R7).
- [X] T027 [P] [US3] Remove monitoring's backup (research R11): `git rm ansible/roles/monitoring_stack/templates/backup-monitoring.sh.j2 ansible/roles/monitoring_stack/tasks/backup_cron.yml`; remove its include from `ansible/roles/monitoring_stack/tasks/main.yml` (~lines 101-103) and the `nfs_mount` include behind `monitoring_nfs_enabled` (~lines 18-22); remove `backup_*` vars from `ansible/roles/monitoring_stack/defaults/main.yml` (~35-38) and `backup_*`, `monitoring_nfs_enabled`, `nfs_*` from `ansible/group_vars/monitoring/vars.yml` (~59-70). Run `grep -rn "nfs_mount" ansible/` and keep `ansible/roles/nfs_mount` only if another role or playbook still uses it; otherwise delete it too.
- [X] T028 [P] [US3] In `ansible/roles/proxmox_mounts/tasks/main.yml`, add `/mnt/nas/homelab_jellyfin` ← `192.168.1.109:/volume1/homelab_jellyfin` to `nas_nfs_mounts`, with the same options as `homelab_financial_scenario` (`rw,nofail`).
- [X] T029 [P] [US3] In `terraform/environments/prod.tfvars.template`, add to `service_mountpoints` a `jellyfin` entry `backups = { mp = "/mnt/jellyfin/backups", volume = "/mnt/nas/homelab_jellyfin" }` beside the existing `video` entry, in the same shape as hermes'. Add the same to `terraform/environments/prod.tfvars.example` if that file lists jellyfin. Do not change `scripts/lab/**` (protected).
- [ ] T030 [US3] **Manual, Synology DSM** (quickstart §0.2): create share `homelab_jellyfin` with an NFS rule for `192.168.1.112` matching `homelab_financial_scenario`'s (privilege, squash, security). Write these steps, with the export settings used, into a new `## Backup share` section of `docs/operations/jellyfin-media-mount.md`, so they are in an operator doc and not only in this feature's quickstart. Then apply the hermes fix that T002 confirmed (FR-015): if the cause is the `homelab_hermes` export, align it with `homelab_financial_scenario` here and record the setting changed. If T002 found a different cause (for example a node_exporter flag or the bind mount itself), fix it in the file that owns it instead, and add one assertion for that fix to `python/tests/guardrails/test_service_backup.py`. Record cause and fix in quickstart §5 either way.
- [X] T031 [US3] Add to `ansible/roles/service_backup/templates/snapshot/jellyfin.sh.j2` a `snapshot()` that runs host `python3 -c 'import sqlite3,sys; s=sqlite3.connect(sys.argv[1]); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.close(); s.close()' <db> "$WORK_DIR/jellyfin.db"` using the DB path recorded in T003, then `cp -a /etc/jellyfin "$WORK_DIR/etc-jellyfin"`. No metadata, cache or trickplay directories. No service stop.
- [X] T032 [US3] In `ansible/playbooks/jellyfin.yml`, add `- role: service_backup` / `service_backup_name: jellyfin` / `when: (deploy_environment | default('prod')) != 'lab'` after `jellyfin` in the workload play.
- [X] T033 [US3] Add `jellyfin: {host: jellyfin, mount: /mnt/jellyfin/backups, dir: /mnt/jellyfin/backups, schedule: "*-*-* 05:00:00"}` to `service_backups` in `ansible/group_vars/all/vars.yml`. Do this in the same commit as T031–T032 so the alert never expects a backup that is not installed.

**Checkpoint**: All guard tests pass; `ansible-playbook --syntax-check playbooks/jellyfin.yml playbooks/monitoring.yml playbooks/host_proxmox.yml` passes.

---

## Phase 6: User Story 4 - No secrets in service archives (Priority: P2)

**Goal**: Immich's archive has no `.env`; the drill renders it (FR-008).

**Independent Test**: Guard test 10 passes. After the immich deploy, `tar -tzf` shows no `.env` and
`playbooks/restore-drill.yml` passes.

### Implementation for User Story 4

- [X] T034 [US4] In `ansible/playbooks/restore-drill.yml`, replace the task that copies `{{ extracted_folder }}/.env` into the restore dir (~lines 59-63) with an `ansible.builtin.template` from `../roles/immich/templates/.env.j2` to `{{ restore_dir }}/.env`, mode `0600`. Add `../roles/immich/defaults/main.yml` to the play's `vars_files` if `immich_upload_location` / `immich_metrics_enabled` are not already in scope. Keep the existing `immich_db_password` assert.
- [X] T035 [P] [US4] In `docs/runbooks/immich-backup-restore.md`, state that archives no longer contain `.env`, that a restore re-renders it through the normal Immich deploy (or the drill renders it), and that archives from before 2026-10-23 still contain it until retention removes them (owner decision; no rewrite). Replace any `immich-backup` role names with `service_backup`.

**Checkpoint**: Guard test 10 passes.

---

## Phase 7: User Story 5 - The policy is written down and correct (Priority: P3)

**Goal**: Policy and every host's class in the architecture doc; the false `ServiceDown` claims
corrected (FR-001, FR-002, FR-016, SC-005).

**Independent Test**: Every host in `ansible/inventories/prod/hosts.yml` appears in the
`docs/architecture.md` table; `grep -n ServiceDown` in the three docs no longer ties it to the backup.

### Implementation for User Story 5

- [X] T036 [P] [US5] Rewrite `docs/architecture.md` § Backup & Monitoring (~lines 22-44): state the policy ("rebuild from configuration; back up only what cannot be rebuilt; no Proxmox guest backups"), then a table of every host in `ansible/inventories/prod/hosts.yml` (proxmox, reverse_proxy, immich, monitoring, jellyfin, nextcloud, financial-scenario, market-model, eurooffice, llm-router, hermes, ntfy, pi-runner, synology) with class (backed up / rebuilt from configuration / disposable / not a Proxmox guest) and the reason, from data-model "Backup class" and the backlog table. Replace line 27's `ServiceDown` claim with: "Monitoring: `BackupStale` (36 h, and never-succeeded) on `backup_last_success_timestamp_seconds`." Remove the stale `proxmox_backup_email_mode` line if that variable no longer exists (`grep -rn proxmox_backup_email_mode ansible/`).
- [X] T037 [P] [US5] In `docs/operations/backups-proxmox-config.md` § Monitoring (~lines 375-382), replace the `ServiceDown` / node-exporter text with: the host is scraped by the `node-exporter` job; `BackupStale{backup="proxmox"}` fires 36 h after the last verified run or if none was ever recorded; how to check `backup_proxmox.prom`. In the deploy section, state that `host_proxmox.yml` now also installs node_exporter, give the exact command (`ansible-playbook -i inventories/prod/hosts.yml playbooks/host_proxmox.yml --vault-password-file .vault-pass.txt` from `ansible/`), and that it is operator-only for the same reason as `backup_proxmox.yml` (FR-016). Fix the stale `site.yml --tags backup` line (~257) to the current command.
- [X] T038 [P] [US5] In `docs/operations/backups-proxmox-config-email-decommission.md` (~lines 9, 55-56), replace the `ServiceDown` claims with the `BackupStale` wording from T037.
- [X] T039 [P] [US5] In `docs/operations/monitoring/quickstart.md`, delete Step 7's backup content (~lines 340-394, including §7.2 "Mount NFS on Monitoring LXC" and "Backups will now run daily at 3:00 AM") and replace it with two sentences: the monitoring host is rebuilt from configuration and not backed up (link `docs/architecture.md`). Renumber later steps only if the doc cross-references them. Also update `docs/operations/monitoring/runbook-restore.md`, `automation.md` and `runbook-upgrades.md` where they reference `backup-monitoring.sh` (grep).
- [X] T040 [P] [US5] In `docs/runbooks/hermes-backup-restore.md`, replace `hermes_backup_*` metric names and `HermesBackupStale` with `backup_last_success_timestamp_seconds{backup="hermes"}` and `BackupStale`, and the role name with `service_backup`.

**Checkpoint**: Docs consistent; `grep -rn "HermesBackupStale\|backup-monitoring.sh\|hermes_backup_last" docs/ ansible/` returns only historical specs (none under `docs/operations` or `docs/runbooks`).

---

## Phase 8: Rollout and live verification (quickstart order)

**Purpose**: Merge once, then deploy host by host and record (FR-006, FR-018, SC-001–SC-004).
Each task records its result in quickstart §5 before the next starts.

- [X] T041 Run quickstart §1 static checks (pre-commit, python tests, syntax checks, local render of `backup_alerts.yml` + `promtool check rules`, the two `grep`s). All pass. Open the PR (`gh pr create`; push through the GitHub API per `AGENTS.md`) and merge after CI is green.
- [X] T042 Re-render the runner's `prod.tfvars` from `prod.tfvars.template` so it contains `service_mountpoints.jellyfin.backups` (research R10: an existing rendered file is reused and nested drift is not detected). Confirm with `grep -n homelab_jellyfin /var/lib/homelab-proxmox/tfvars/prod.tfvars` as `ci@pve`.
- [X] T043 PVE (operator machine): run `host_proxmox.yml` then `task ansible:backup`; run quickstart §2 checks, including `verify_proxmox_backup.sh` exit 0 (SC-004). Record.
- [X] T044 financial-scenario: §0.3 baseline run of the old backup; pipeline deploy; quickstart §3 generic checks, file-list diff empty, manual restore check, and the destination-check refusal test (US2-3). Record.
- [X] T045 hermes: §0.3 baseline run of the old backup; pipeline deploy; new backup run immediately after; quickstart §3 checks, diff empty; `rm` the old `hermes_backup.prom`; run `playbooks/hermes-restore-drill.yml`; confirm `node_filesystem_avail_bytes{mountpoint="/mnt/hermes/backups"}` now exists (FR-015). Record.
- [X] T046 immich: §0.3 baseline run of the old backup; pipeline deploy; quickstart §3 checks, diff shows only `-.env`; `playbooks/restore-drill.yml` passes with `.env` rendered (SC-003, FR-008). Record.
- [X] T047 nextcloud: §0.3 baseline run of the old backup; pipeline deploy; quickstart §3 checks, diff empty, maintenance mode off afterwards, manual restore into a scratch MariaDB. Record.
- [X] T048 jellyfin: pipeline deploy (applies the bind mount, then `service_backup`); `findmnt --mountpoint /mnt/jellyfin/backups` is `nfs`; trigger the first run by hand now (`systemctl start jellyfin-backup.service`), before T049 adds jellyfin to monitoring's expected set (spec edge case "Backup never ran since deploy"); archive contents and `pragma integrity_check`; manual restore and swap back. Record.
- [X] T049 monitoring: confirm every backup in the expected set (five services plus `proxmox`) has a `backup_*.prom` file on its host, then pipeline deploy; quickstart §4 checks (PVE target up, six fresh series, no `BackupStale`, no new noise from PVE filesystem/hardware rules, cron gone). Remove the old cron entry, script and log by hand if still present. Record.
- [X] T050 Deliberate break, quickstart §4.1: absent branch and stale branch, each fires `BackupStale{backup="financial-scenario"}` only and reaches Pushover, then clears (SC-002). Record.

---

## Phase 9: Polish & Cross-Cutting Concerns

- [X] T051 [P] Mark `docs/backlog/091-backup-coverage-and-staleness.md` and `docs/backlog/073-consolidate-backup-roles.md` delivered (Status line, link to `specs/091-backup-coverage-staleness/`). In `docs/backlog/improvement-candidates.md`, mark "Backup job monitoring" delivered and the node_exporter part of "Proxmox host/guest + storage health" delivered, leaving `pve-exporter` open.
- [X] T052 [P] Set `specs/091-backup-coverage-staleness/spec.md` Status to `Implemented (<date>)` and add the plan's Follow-ups (Nextcloud password on argv, `config.php` in archive, `pve-exporter`, PVE CI path, tfvars nested drift) to `docs/backlog/improvement-candidates.md` if not already there.
- [X] T053 Final `bash scripts/ci/python-tests.sh` and `pre-commit run --all-files` on `main` after merge; confirm quickstart §5 has every row filled.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: none. T002 and T003 feed T030 and T031.
- **Foundational (Phase 2)**: after Setup. T005 must be red before any story task. T006 and T007 block US1 and US2.
- **US1 (Phase 3)** and **US2 (Phase 4)**: after Phase 2; independent files, can run in parallel. T012 needs T006 (map).
- **US3 (Phase 5)**: T031–T033 need US2's role (T016, T017). T026–T029 are independent.
- **US4 (Phase 6)**: T034 needs T022 (moved immich compose path). T020 (US2) already drops `.env`.
- **US5 (Phase 7)**: independent; best done after US1–US3 so the docs describe what exists.
- **Rollout (Phase 8)**: after all code merged. Strict order T041 → T050. Monitoring (T049) last.
- **Polish (Phase 9)**: after Phase 8.

### Within Each Story

- Guard test (T005) red first, then the tasks that turn its groups green.
- Map (T006) before anything that reads `service_backups`.
- Snapshot templates (T018–T021, T031) after the main script (T016) defines the `snapshot`/`snapshot_cleanup` contract.

### Parallel Opportunities

- T007 alongside T006.
- US1: T010, T011, T014 in parallel; T008 → T009 sequential (same role); T012 → T013.
- US2: T018, T019, T020, T021 in parallel after T016.
- US3: T026, T027, T028, T029 in parallel.
- US5: T036–T040 all in parallel.

## Parallel Example: User Story 2

```bash
# After T015–T017:
Task: "T018 snapshot/financial-scenario.sh.j2"
Task: "T019 snapshot/hermes.sh.j2"
Task: "T020 snapshot/immich.sh.j2"
Task: "T021 snapshot/nextcloud.sh.j2"
```

## Implementation Strategy

### MVP

US1 + US2 together: the shared role is how service timestamps exist, and the alert is what makes
them worth having. Merge with US3–US5 in one PR (the old roles are deleted in it), then roll out
per Phase 8. If time is short, US5's docs can follow in a second PR; US3's Jellyfin entry must not
merge without its role and mount (T033 rule).

### Incremental Delivery

Per host in Phase 8: each deploy switches exactly one backup and is verified and recorded before
the next. The old roles are deleted in the merge, so a failed switch is fixed forward in
the shared role, or rolled back by deploying that service from the pre-merge commit (`git revert`
of the PR on a branch); unit, script and archive names are the same, so either way the files are
overwritten in place and existing archives are untouched.

## Notes

- [P] = different files, no dependency on an incomplete task.
- Do not rename units, scripts, archives or directories (FR-005).
- Do not add permanent clean-up tasks for migration leftovers; use the documented one-offs.
- Commit after each phase; push through the GitHub API (Zscaler).
