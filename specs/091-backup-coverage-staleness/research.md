# Research: Backup Coverage and Staleness

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Date**: 2026-10-23

Findings come from the repo on branch `091-backup-coverage-staleness` and from read-only checks on
2026-10-23: `findmnt --mountpoint` on four service LXCs, and two Prometheus queries against
`192.168.1.214:9090`. A further live check (the hermes mount as the `node_exporter` user) was not
run; R9 lists it as the first quickstart step.

## R1 — The existing destination check does not check anything (FR-004)

- **Finding**: `hermes_backup/tasks/main.yml:7-11` and `financial_scenario_backup/tasks/main.yml:10-14`
  run `findmnt --target <path>` and fail on rc≠0. `--target` resolves a path to the mount that
  *contains* it, so it returns 0 for any path, even one sitting on `/`. A missing bind mount would
  pass. The scripts only test `-d` and `-w`. Immich asserts on `ansible_mounts` (deploy time only);
  Nextcloud has no check at all. Today all four destinations *are* NAS mounts (checked live:
  `/mnt/hermes/backups`, `/mnt/financial-scenario/backups`, `/mnt/immich`, `/mnt/nextcloud`, all
  `nfs` from `192.168.1.109`), so no archive has gone to local disk.
- **Finding**: the mount to check is not always the backup directory. Nextcloud writes to
  `/mnt/nextcloud/backups`, which is a plain directory on the `/mnt/nextcloud` data mount; Immich
  writes to `/mnt/immich/backups` on the `/mnt/immich` mount.
- **Decision**: Each backup declares its **mount point** separately from its directory. The check is
  exact, `findmnt --mountpoint <mount> --types nfs,nfs4` (rc≠0 if that path is not itself an NFS
  mount), and runs **twice**: as a deploy-time task (FR-004's "deploy must fail") and at the top of
  every run of the script (FR-004's "refuses to run"). The script never creates the mount point and
  creates the backup directory only beneath a verified mount, and only if it is missing, with mode
  `0750`. An existing directory keeps its mode (Nextcloud's is `0777`), so the switch never changes
  permissions on a share that may squash root.
- **Alternatives considered**: `mountpoint -q` (passes for any mount type, including an accidental
  tmpfs or a bind of local disk; rejected). Checking only at deploy time (the mount can drop between
  deploy and 04:00; rejected). Asserting on `ansible_mounts` (deploy-time only; rejected).

## R2 — Shape of the shared role (FR-003, FR-005)

- **Finding**: The four roles share, after normalising names, an identical GFS prune block,
  byte-identical `handlers/main.yml`, and identical inline service and timer units. They differ in
  the snapshot step, the destination check (R1), cleanup traps (Immich and Nextcloud leak their temp
  dir on failure), `set` flags (Immich lacks `-u`), and hermes' metric. Unit names are
  `<x>-backup.{service,timer}`; scripts are `/usr/local/bin/backup_<x>.sh`; archives are
  `<x>-backup-YYYYmmdd-HHMMSS.tar.gz` containing one top-level directory of the same name. The
  restore drills derive the directory from the archive name.
- **Decision**: One role `service_backup` with one script template. The script does, in order:
  runtime mount check → `mktemp` work dir with an `EXIT` trap → the service's snapshot function into
  the work dir → `tar -czf` to `<name>.tar.gz.partial` in the backup directory → `mv` to the final
  name → success timestamp (R4) → GFS prune. Prune runs after the timestamp, as today in hermes, so a
  prune error fails the unit (visible in the journal) without hiding a good archive.
  - **Snapshot steps** live in the shared role as `templates/snapshot/<backup>.sh.j2`, each defining
    one shell function `snapshot()` that writes into `$WORK_DIR`. The main template pulls the right
    one in with `{% include 'snapshot/' ~ service_backup_name ~ '.sh.j2' %}`. A per-service file is
    the smallest unit that holds a genuinely different step; putting it in the service's own role
    would need a cross-role template path, which Ansible does not resolve cleanly.
  - **Names do not change**: unit names, script paths, archive names, directories and schedules stay
    as they are, so the switch overwrites files in place, leaves no orphaned units, and the prune
    keeps treating old and new archives as one series (FR-005). Only the success-metric file changes
    (R4).
  - **Retention** (7/4/6) is written once, in the shared role's defaults. It is the same for every
    backup, so the eight per-service retention variables go (constitution IV).
  - **Restore templates** used by the drills (`docker-compose.restore.yml.j2` for Immich and hermes,
    `restore_hermes.sh.j2`) move to `roles/service_backup/templates/restore/`, and the two drill
    playbooks' `src:` paths change with them.
- **Alternatives considered**: Keep four thin roles that `include_role` a common one (rejected by the
  spec: no wrappers). A `script` parameter pointing at a file in the service role (cross-role path,
  rejected). Moving prune into a separate tool (no second consumer; rejected).

## R3 — Where each backup's settings live, and the expected set (FR-007, FR-014)

- **Finding**: Backup variables are spread over `group_vars/services/vars.yml` (three services) and
  `roles/nextcloud/defaults/main.yml` (Nextcloud). Lab deploys use the prod inventory with
  `-e deploy_environment=lab` (`playbooks/immich.yml:12`); there is no lab service inventory.
  The monitoring host's templates can read `hostvars` for every inventory host, including
  `proxmox` in `proxmox_hosts`.
- **Decision**: One map, `service_backups`, in `group_vars/all/vars.yml` (both the service plays and
  the monitoring play must read it, and `proxmox_hosts` is not in `services`):

  ```yaml
  service_backups:
    nextcloud:          { host: nextcloud,          mount: /mnt/nextcloud,                  dir: /mnt/nextcloud/backups,          schedule: "*-*-* 04:00:00" }
    financial-scenario: { host: financial-scenario, mount: /mnt/financial-scenario/backups, dir: /mnt/financial-scenario/backups, schedule: "*-*-* 04:15:00" }
    immich:             { host: immich,             mount: /mnt/immich,                     dir: /mnt/immich/backups,             schedule: "*-*-* 04:30:00" }
    hermes:             { host: hermes,             mount: /mnt/hermes/backups,             dir: /mnt/hermes/backups,             schedule: "*-*-* 04:45:00" }
    jellyfin:           { host: jellyfin,           mount: /mnt/jellyfin/backups,           dir: /mnt/jellyfin/backups,           schedule: "*-*-* 05:00:00" }
  ```

  The map key is the `backup` label value and also the stem of every name the role derives:
  `<key>-backup.{service,timer}`, `<key>-backup-<ts>.tar.gz` and `snapshot/<key>.sh.j2`. These are
  today's names, so nothing on disk is renamed. The script path stays `/usr/local/bin/backup_<x>.sh`,
  with `<x>` being the key with `-` replaced by `_`. Each service playbook applies
  `service_backup` with `service_backup_name: <key>` and
  `when: (deploy_environment | default('prod')) != 'lab'` (FR-007; replaces
  `immich_require_nas_mount` for the backup role). The monitoring template builds the expected set
  from the same map plus `groups['proxmox_hosts']`, under the same lab switch.
- **Rationale**: One list drives both installation and alerting, so they cannot drift. A host that
  leaves the inventory drops out of both in the same change (spec edge case).
- **Alternatives considered**: A per-host `service_backup` dict in each `host_vars` file (the
  monitoring template would loop all hosts looking for it — workable, but spreads five entries over
  five files). A hand-kept list in the alert template (forbidden by FR-014).

## R4 — The success record (FR-012)

- **Finding**: Hermes writes `hermes_backup_success` and `hermes_backup_last_success_timestamp_seconds`
  to `<textfile dir>/hermes_backup.prom`, atomically (`.$$` then `mv`) on success; on failure it
  rewrites the file non-atomically. Every LXC's node_exporter reads
  `/var/lib/node_exporter/textfile_collector` (owned by `node_exporter`, 0755). The variable
  `node_exporter_textfile_directory` is undefined outside the `node_exporter` role, hence the
  inline defaults in three roles.
- **Decision**: One small writer script, `/usr/local/bin/backup-success-metric <backup>`, installed
  by the `node_exporter` role (it owns the directory, runs on every LXC through `lxc_base`, and will
  run on `pve` per R6). It writes exactly:

  ```text
  # HELP backup_last_success_timestamp_seconds Unix time of the last successful backup run.
  # TYPE backup_last_success_timestamp_seconds gauge
  backup_last_success_timestamp_seconds{backup="<backup>"} <epoch>
  ```

  to `backup_<backup>.prom.tmp` and renames it to `backup_<backup>.prom`, mode 0644. It writes only
  on success; failures write nothing, so staleness is the only failure signal (no `_success` gauge —
  nothing would consume it). Both consumers call it: the `service_backup` script and
  `proxmox-config-backup.sh` (after `verify_backup` succeeds in `main()`). This is the "reuses only
  the timestamp writer" in FR-003, and two consumers justify the file (constitution IV).
- **Migration**: after hermes switches over, the old `hermes_backup.prom` is deleted as a documented
  one-off step (quickstart), not a permanent cleanup task.
- **Alternatives considered**: An inline shell function copied into both scripts (two copies of
  one thing; rejected). Pushgateway (owner decision: textfile collector).

## R5 — The `BackupStale` rule (FR-013, FR-014)

- **Finding**: Rules are static files under `monitoring_stack/files/prometheus/alerts/` plus
  `templates/service_alerts.yml.j2`, all loaded from `alerts/*.yml` and checked with
  `promtool check rules` at deploy time (`validate_alerts.yml`). The `node-exporter` job sets no
  labels, so `instance` is `IP:9100`. The only `absent()` use today is `HermesAgentCronStale`.
  `HermesBackupStale` lives in `host_vars/hermes.yml:52-62` (36 h, `for: 0m`, warning). Warning
  routes to `pushover-warning`.
- **Decision**: A new template `monitoring_stack/templates/backup_alerts.yml.j2`, rendered next to
  `service_alerts.yml`, with one group and one rule:

  ```yaml
  - alert: BackupStale
    expr: |
      (time() - max by (backup) (backup_last_success_timestamp_seconds) > 129600)
      {% for name in expected %}or absent(backup_last_success_timestamp_seconds{backup="{{ name }}"})
      {% endfor %}
    for: 15m
    labels: { severity: warning }
  ```

  `absent()` with an equality matcher carries `backup="<name>"` into the alert, so both branches
  name the backup. `max by (backup)` drops `instance`, so a backup is judged by name wherever it
  runs. `for: 15m` absorbs a scrape gap or node_exporter restart without delaying a real 36 h breach
  meaningfully. The annotation points at `journalctl -u <unit>` on the host. `HermesBackupStale` is
  deleted from `host_vars/hermes.yml`.
- **Rationale**: A separate template because `service_alerts.yml.j2` is per-host and keyed on
  `monitoring_contract`; backups are a cross-host list. One rule with one expression meets
  constitution IV's "consolidate before adding".
- **Accepted behaviour**: a host that is down makes its metric absent, so `BackupStale` fires next to
  `ServiceDown`. Correct: that backup is not running.
- **Alternatives considered**: One rule per backup (five-plus near-copies; rejected). Absent check
  without the `or` loop, e.g. `count(...) < N` (does not say which backup; rejected).

## R6 — node_exporter on the Proxmox host (FR-012, FR-016)

- **Finding**: The `node_exporter` role (release tarball, pinned 1.12.1 in `group_vars/all`, amd64)
  is applied only via `lxc_base`. Its `node_exporter_disabled_collectors` default (hwmon,
  thermal_zone, powersupplyclass, nvme, mdadm, infiniband, fibrechannel, wifi) is tuned for LXCs.
  The `node-exporter` scrape job loops over `groups['services']`. PVE is `proxmox`
  (`192.168.1.112`) in `proxmox_hosts`; `host_proxmox.yml` applies `proxmox_host` and
  `tailscale_host` to it, operator-only (principle V exception from `089`).
- **Decision**:
  - Add `node_exporter` to the roles in `playbooks/host_proxmox.yml`.
  - In `group_vars/proxmox_hosts/vars.yml`, set
    `node_exporter_disabled_collectors: [infiniband, fibrechannel, wifi]`, keeping hwmon,
    thermal_zone, nvme, mdadm and powersupplyclass, which report real hardware on bare metal.
  - Extend the `node-exporter` job's loop to `groups['services'] + groups['proxmox_hosts']`, under the
    lab switch, so PVE gets `job="node-exporter"` and the existing CPU/memory/disk rules apply to it.
  - In `proxmox-backup.service.j2`, add `{{ node_exporter_textfile_directory }}` to `ReadWritePaths=`
    (the unit runs under `ProtectSystem=strict`), and update `test_pve_backup_unit_sandbox`, which
    asserts the exact line.
- **Risk**: The existing filesystem rules may fire for the host's NFS mounts under `/mnt/nas/*` or
  `/mnt/pve/*`. The quickstart checks active alerts right after the first scrape; if noisy, the fix is
  an exclude on the PVE host only.
- **Alternatives considered**: Debian's `prometheus-node-exporter` apt package (different version and
  flags from the rest of the estate; rejected). `pve-exporter` for guest state (out of scope; that is
  the rest of the improvement candidate).

## R7 — PVE timer fires twice (FR-011)

- **Finding**: `proxmox-backup.timer.j2:11-25` renders `OnCalendar=daily` from
  `proxmox_backup_schedule` *and* `OnCalendar=*-*-* 02:00:00` from `proxmox_backup_time`, both set in
  role defaults and `group_vars/proxmox_hosts/vars.yml`.
- **Decision**: When `proxmox_backup_time` is defined, render only `OnCalendar=*-*-* <time>:00`;
  otherwise use the schedule branch as today. One guard test asserts the template cannot emit two
  `OnCalendar=` lines when `proxmox_backup_time` is set.

## R8 — Immich `.env` out of the archive (FR-008)

- **Finding**: `backup_immich.sh.j2:35-53` copies `docker-compose.yml` and `.env` into the archive.
  `playbooks/restore-drill.yml:59-63` copies `.env` out of the archive and fails if it is missing.
  `.env` is rendered by `roles/immich/tasks/main.yml:47-52` from `roles/immich/templates/.env.j2`
  (needs `immich_version`, `immich_upload_location`, `immich_data_dir`, `immich_db_password`,
  `immich_metrics_enabled`). The drill already asserts `immich_db_password`.
- **Decision**: The Immich snapshot keeps `dump.sql` and `docker-compose.yml`, drops `.env`. The drill
  renders `.env` from `../roles/immich/templates/.env.j2` into its restore dir instead of copying it
  (it already loads the variables it needs through the group_vars symlink plus
  `roles/immich/defaults/main.yml`). A real restore re-renders `.env` through the normal Immich
  deploy. `docs/runbooks/immich-backup-restore.md` says so. Old archives keep their `.env` and age
  out (spec Clarifications).
- **Check for other archives (FR-008 "no other archive gains one")**: Nextcloud's archive has
  `config.php`, which holds the instance secret and DB password. It is in today's archive, the
  backlog requires the file list to stay the same, and FR-008 only forbids *gaining* one, so it
  stays. Hermes excludes `.env` and `config.yaml` already. Jellyfin's `/etc/jellyfin` holds XML
  settings without credentials (checked at implementation; T-task asserts the archive list).

## R9 — Hermes' NAS mount missing from `node_filesystem_*` (FR-015)

- **Finding (live, 2026-10-23)**: `/mnt/hermes/backups` *is* an NFS mount from
  `192.168.1.109:/volume1/homelab_hermes`. Prometheus has
  `node_filesystem_device_error{instance="192.168.1.221:9100",mountpoint="/mnt/hermes/backups"} = 1`,
  so node_exporter sees the mount but its `statfs` fails, and size/avail series are not emitted.
  The other NAS mounts (immich, financial-scenario, nextcloud) report normally. Archive files on the
  hermes share are owned `nobody:nogroup`, the financial-scenario ones `root:root`: the Synology NFS
  squash setting for `homelab_hermes` differs from the others.
- **Decision**: Likely cause is the share's permissions denying the unprivileged `node_exporter`
  user search access to the mount root (the root-run backup works because root is squashed to a
  user that can write). Confirm first with `runuser -u node_exporter -- stat -f /mnt/hermes/backups`
  and `ls -ld` on hermes (quickstart step 0; not run during planning). Fix by aligning
  `homelab_hermes`'s NFS export (squash mapping) with `homelab_financial_scenario`'s on the Synology,
  recorded in the quickstart. No code change expected. If the cause turns out to be something else,
  fixing it is still in scope (FR-015).
- **Guard**: none in code; verification is the live query in the quickstart.

## R10 — Jellyfin backup (FR-009)

- **Finding**: Jellyfin is a native apt install (`roles/jellyfin`). The repo names no data paths;
  the Debian package defaults are `/var/lib/jellyfin` (data, DB at `data/jellyfin.db`) and
  `/etc/jellyfin` (config). No role installs the `sqlite3` CLI. Host-path bind mounts are applied
  by `scripts/lab/pve-service-deploy` from `service_mountpoints` in the rendered tfvars, with an
  allowlist of `/mnt/nas/` sources; PVE-side NFS mounts are the `nas_nfs_mounts` list in
  `roles/proxmox_mounts/tasks/main.yml`.
- **Decision**:
  - Snapshot: host `python3` `sqlite3.Connection.backup()` of `jellyfin.db` into `$WORK_DIR`, the
    pattern hermes already uses for its agent DBs. No new package and no downtime (spec
    Clarifications). Then `cp -a /etc/jellyfin`. The DB path is checked on the host at
    implementation and set in the snapshot template.
  - Destination, in this order:
    1. **Manual on the Synology**: create share `homelab_jellyfin` with an NFS export to
       `192.168.1.112`, same settings as `homelab_financial_scenario`.
    2. Add `/mnt/nas/homelab_jellyfin` to `nas_nfs_mounts` and apply `host_proxmox.yml --tags mounts`
       from an operator machine.
    3. Add `jellyfin.backups = { mp = "/mnt/jellyfin/backups", volume = "/mnt/nas/homelab_jellyfin" }`
       to `terraform/environments/prod.tfvars.template`, and re-render the runner's `prod.tfvars`
       (it is reused when present, and the drift check compares top-level keys only).
    4. Pipeline deploy of jellyfin, which applies `pct set -mpN` and then `service_backup`.
  - No `scripts/lab/**` change (that path is protected).

## R11 — Monitoring's backup removal (FR-010)

- **Finding**: `roles/monitoring_stack/tasks/backup_cron.yml` installs
  `/usr/local/sbin/backup-monitoring.sh` from `templates/backup-monitoring.sh.j2` and a cron entry
  "Backup monitoring stack" logging to `/var/log/monitoring-backup.log`. It is included from
  `tasks/main.yml:101-103`. Its variables are in `defaults/main.yml:35-38` and
  `group_vars/monitoring/vars.yml:59-62`. `monitoring_nfs_enabled: false` and the `nfs_*` variables
  (`group_vars/monitoring/vars.yml:65-70`) exist only to mount that destination;
  `monitoring_stack/tasks/main.yml:18-22` includes `nfs_mount` behind it.
- **Decision**: Delete the template, `backup_cron.yml`, its include, the `backup_*` variables, the
  `monitoring_nfs_enabled` / `nfs_*` variables and the `nfs_mount` include in `monitoring_stack`.
  The `nfs_mount` role itself stays if anything else uses it (checked at implementation). The live
  cron entry, script and log are removed by a documented one-off command (quickstart), the same way
  `089` handled one-off recreates.

## R12 — Tests (FR-017)

- **Finding**: Tests are pytest under `python/tests/`, run in PR CI by `scripts/ci/python-tests.sh`.
  Test dependencies are pytest and PyYAML only (no Jinja2). No test renders templates and CI has no
  promtool. The `089` guard file `test_backup_log_rotation_config.py` has four tests that name
  `immich_backup` paths and one that asserts the PVE sandbox line.
- **Decision**: One new guard file, `python/tests/guardrails/test_service_backup.py`, text/YAML
  assertions in the `089` style:
  - the four old role directories and `backup-monitoring.sh.j2` do not exist; `HermesBackupStale`
    appears nowhere under `ansible/`;
  - every key in `service_backups` has a snapshot template, and every service playbook that applies
    `service_backup` passes a key that exists in the map, with the lab `when:`;
  - the script template contains the exact `findmnt --mountpoint` check before the snapshot call, the
    `.partial` → `mv`, and calls `backup-success-metric` only after the `mv`;
  - `backup_alerts.yml.j2` loops over `service_backups` and `proxmox_hosts` with `absent(` and no
    literal backup names;
  - `proxmox-backup.timer.j2` emits a single `OnCalendar` when `proxmox_backup_time` is defined;
  - the Immich snapshot template does not reference `.env`.
  Update the existing `089` tests that name `immich_backup` paths to the new ones (same intent), and
  `test_pve_backup_unit_sandbox` for the extra `ReadWritePaths` entry. `promtool check rules` keeps
  running at deploy time; the quickstart also runs it locally against the rendered file before
  deploy. Live behaviour (archives, restores, alert firing) is verified in the quickstart.
