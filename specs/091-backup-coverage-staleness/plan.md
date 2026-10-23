# Implementation Plan: Backup Coverage and Staleness

**Branch**: `091-backup-coverage-staleness` | **Date**: 2026-10-23 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/091-backup-coverage-staleness/spec.md`

## Summary

Make every backup visible to monitoring, and maintain it once:

1. **One `service_backup` role** replaces `financial_scenario_backup`, `hermes_backup`,
   `immich_backup` and `nextcloud_backup`. It owns the units, handlers, an exact NFS destination
   check (deploy time and every run), GFS prune and the success record. Each service supplies one
   snapshot template. All five backups are listed in one `service_backups` map, which also drives
   the alert's expected set. Unit, script and archive names stay the same, so the switch is an
   in-place overwrite.
2. **Success timestamps** through node_exporter's textfile collector, written by one small writer
   (`backup-success-metric`) that the `node_exporter` role installs. Both the shared role and
   `proxmox_backup` call it.
3. **One `BackupStale` rule** (36 h, plus `absent()` per expected backup), rendered from the map and
   `proxmox_hosts`. It replaces `HermesBackupStale`.
4. **Proxmox host**: node_exporter with a bare-metal collector set, scraped by the `node-exporter`
   job; the timer's double `OnCalendar` fixed; its unit may write the textfile directory.
5. **Coverage**: Jellyfin backed up (online SQLite copy, 05:00, new NAS share). Monitoring's backup
   script and cron removed. Immich's `.env` dropped from the archive, and the drill renders it.
6. **Hermes' mount metric**: `statfs` fails for the `node_exporter` user (live, R9). The likely fix is
   the Synology export's squash setting, with no code change.
7. **Docs**: backup policy and host classes in `docs/architecture.md`; the false `ServiceDown` claim
   corrected in three docs; quickstart §7.2 removed.

Research: [research.md](./research.md). It found one defect the backlog did not record: the current
`findmnt --target` check passes for any path (R1).

## Technical Context

**Language/Version**: YAML (Ansible 2.x), Jinja2, Bash, Prometheus rule YAML; HCL only in
`prod.tfvars.template` (one mountpoint entry). No new language.

**Primary Dependencies**: existing `node_exporter` role (1.12.1 pin), `monitoring_stack` (Prometheus
v3.8.1, promtool at deploy), `proxmox_backup`, `proxmox_mounts`, `scripts/lab/pve-service-deploy`
(host-path bind mounts, unchanged), systemd timers, `findmnt` (util-linux), host `python3` `sqlite3`.

**Storage**: Synology NAS over NFS, bind-mounted into each LXC. One new share, `homelab_jellyfin`.
Success records are textfiles on each host's local disk.

**Testing**: one new pytest guard file `python/tests/guardrails/test_service_backup.py`
(text/YAML assertions, PyYAML only, R12). Existing `089` guard tests updated where they name moved
paths or the PVE sandbox line. `promtool check rules` at deploy and once locally (quickstart §1).
Live checks, restores and a deliberate break in [quickstart.md](./quickstart.md).

**Target Platform**: Proxmox VE host `pve` (192.168.1.112) and Debian LXCs: nextcloud,
financial-scenario, immich, hermes, jellyfin, monitoring.

**Project Type**: Infrastructure configuration (Ansible-managed homelab).

**Performance Goals**: N/A. Detection within 36 h + 15 min of a backup's last success (SC-002).

**Constraints**: Unprivileged LXCs: NAS only through host mount plus bind mount. PVE changes run
only from an operator machine (principle V exception, FR-016). `scripts/lab/**` is protected and is
not changed. Archives, names, schedules and retention of the four migrated backups unchanged
(FR-005). One service switched at a time (FR-006). The Mac cannot `git push` (Zscaler): push
through the GitHub API (`AGENTS.md`).

**Scale/Scope**: 6 backups (5 service + PVE) on 6 hosts; 1 new role replacing 4; about 25 files
changed, 4 role directories and 2 monitoring files deleted, 1 test file added.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Spec-driven workflow | PASS | Work comes from `specs/091-*`; docs ship in the same change (FR-001, FR-002). |
| II. Secrets policy | PASS | Immich's `.env` leaves the archive (FR-008). The drill renders it from the gitignored `secrets.yml`. Nextcloud's `config.php` stays as today (R8); no archive gains a credentials file. No secret goes into a metric or label. |
| III. Separation of concerns | PASS | Terraform: one tfvars template entry. Bind mounts stay with the orchestrator. Everything else is Ansible. |
| IV. Code economy | PASS | Four roles become one (net deletion). The map has five entries today and two consumers (install, alert). The writer script has two consumers (service backups, PVE). Eight per-service retention variables collapse to one default. One rule replaces a per-host rule. No wrappers. Migration clean-ups (hermes' old `.prom`, monitoring's cron) are documented one-offs, not permanent code. A new template for alerts is justified: `service_alerts.yml.j2` is per-host and contract-keyed, and backups are cross-host (R5). |
| V. Dual-provisioning parity | PASS through the documented-exception clause | Service and monitoring changes go through the existing pipeline and `pve-service-deploy` locally. PVE changes (`host_proxmox.yml`, `backup_proxmox.yml`) are operator-only, as recorded by `089`: CI has no root on `pve`. The NAS share creation is manual on the Synology in either context. The PVE limitation goes into `docs/operations/backups-proxmox-config.md` (T037, FR-016); the share steps go into `docs/operations/jellyfin-media-mount.md` (T030). |
| CI/CD: no destructive automation without barriers | PASS | Old roles are deleted in code only; on hosts the new role overwrites the same files. No archive is deleted except by the unchanged prune. Monitoring's script removal is manual. |
| Test-driven changes | PASS | Static checks, one guard test file covering the role contract, deploy-time promtool, and live verification including restores. |

**Post-design re-check (after Phase 1)**: All PASS. No new violations: the map lives in the existing
`group_vars/all/vars.yml`, the writer in the existing `node_exporter` role, and the rule template in
the existing `monitoring_stack` role.

## Project Structure

### Documentation (this feature)

```text
specs/091-backup-coverage-staleness/
├── plan.md                    # This file
├── research.md                # Phase 0: R1–R12
├── data-model.md              # Backup definition, archive, success record, expected set, classes
├── quickstart.md              # Pre-checks, static checks, rollout order, live checks, record
├── contracts/
│   └── backup-contract.md     # C1–C5 (relied on by 092)
├── checklists/
│   └── requirements.md
└── tasks.md                   # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
ansible/
├── group_vars/all/vars.yml                         # + service_backups map (R3)
├── group_vars/services/vars.yml                    # − *_backup_path/_retention_*/_schedule (3 services)
├── group_vars/proxmox_hosts/vars.yml               # + node_exporter_disabled_collectors (bare metal)
├── group_vars/monitoring/vars.yml                  # − backup_*, monitoring_nfs_enabled, nfs_*
├── host_vars/hermes.yml                            # − HermesBackupStale
├── roles/service_backup/                           # NEW (replaces the four below)
│   ├── defaults/main.yml                           #   retention 7/4/6
│   ├── handlers/main.yml
│   ├── tasks/main.yml                              #   deploy-time mount check, dir, script, units
│   └── templates/
│       ├── backup.sh.j2                            #   mount check → snapshot → .partial → mv → metric → prune
│       ├── snapshot/{nextcloud,financial-scenario,immich,hermes,jellyfin}.sh.j2
│       └── restore/{immich,hermes}-compose.yml.j2, restore_hermes.sh.j2   # moved
├── roles/{financial_scenario,hermes,immich,nextcloud}_backup/   # DELETED
├── roles/nextcloud/defaults/main.yml               # − nextcloud_backup_* vars
├── roles/node_exporter/{tasks/main.yml,files/backup-success-metric}   # + writer (C2)
├── roles/proxmox_backup/templates/
│   ├── proxmox-backup.timer.j2                     # single OnCalendar (R7)
│   ├── proxmox-backup.service.j2                   # + textfile dir in ReadWritePaths
│   └── proxmox-config-backup.sh.j2                 # + backup-success-metric proxmox after verify_backup
├── roles/proxmox_mounts/tasks/main.yml             # + /mnt/nas/homelab_jellyfin
├── roles/monitoring_stack/
│   ├── templates/prometheus.yml.j2                 # node-exporter job + proxmox_hosts
│   ├── templates/backup_alerts.yml.j2              # NEW: BackupStale (R5)
│   ├── tasks/compose_stack.yml                     # render backup_alerts.yml
│   ├── tasks/main.yml                              # − backup_cron include, − nfs_mount include
│   ├── tasks/backup_cron.yml                       # DELETED
│   ├── templates/backup-monitoring.sh.j2           # DELETED
│   └── defaults/main.yml                           # − backup_* vars
└── playbooks/
    ├── {nextcloud,financial-scenario,immich,hermes,jellyfin}.yml   # service_backup with name + lab when
    ├── host_proxmox.yml                            # + node_exporter
    ├── restore-drill.yml                           # render .env; new compose template path
    └── hermes-restore-drill.yml                    # new compose template path
terraform/environments/prod.tfvars.template          # + jellyfin.backups mountpoint
python/tests/guardrails/
├── test_service_backup.py                          # NEW (R12)
└── test_backup_log_rotation_config.py              # paths and sandbox line updated
docs/
├── architecture.md                                 # policy + every host's class (FR-001)
├── operations/backups-proxmox-config.md            # ServiceDown → BackupStale; deploy commands
├── operations/backups-proxmox-config-email-decommission.md   # same correction
├── operations/monitoring/quickstart.md             # remove §7.2 and the backup step
├── runbooks/immich-backup-restore.md               # .env re-rendered on restore
├── runbooks/hermes-backup-restore.md               # new metric name, BackupStale
└── backlog/improvement-candidates.md, backlog/091-*.md, backlog/073-*.md   # mark delivered/absorbed
```

**Structure Decision**: One new role in place of four, and one new alert template. Everything else
edits the file that already owns the behaviour. Per-service knowledge sits in one snapshot template
each and one map entry each.

## Implementation Notes

### Shared role (R1–R3)

- `tasks/main.yml`, in order: look up `service_backups[service_backup_name]`; assert
  `inventory_hostname == entry.host`; `command: findmnt --mountpoint {{ entry.mount }} --types nfs,nfs4`
  (`changed_when: false`, fail on rc≠0, message naming the bind mount and the tfvars entry); create
  `entry.dir` (0750) only if it does not exist yet — an existing directory keeps its mode, so a
  root-squashing export cannot fail the deploy; template the script to `/usr/local/bin/backup_{{ name | replace('-', '_') }}.sh`
  (0750); copy the service and timer units (content as today); enable and start the timer.
- `backup.sh.j2`: `set -euo pipefail`; `BACKUP_MOUNT=…` on one line; mount check; `WORK_DIR=$(mktemp -d)`
  plus `trap` cleanup; `{% include 'snapshot/' ~ service_backup_name ~ '.sh.j2' %}` then `snapshot`;
  `tar` to `.partial`, `mv`; `backup-success-metric <name>`; prune (today's block, glob quoted).
- Snapshot templates carry over the current steps verbatim, except: Immich drops `.env`; Nextcloud
  keeps its maintenance-mode trap, chained with the shared cleanup trap; financial-scenario and hermes
  keep the "nothing to back up yet" early `exit 0`, which writes no timestamp, so a never-populated
  service still alerts.
- Playbooks: replace `<x>_backup` in the roles list with
  `{ role: service_backup, service_backup_name: <key>, when: (deploy_environment | default('prod')) != 'lab' }`.
  `immich_require_nas_mount` stays for the `immich` role's own preflight.

### Monitoring (R4–R6)

- `prometheus.yml.j2` node-exporter job: loop `groups['services'] + (groups['proxmox_hosts'] if not lab else [])`.
- `backup_alerts.yml.j2` per R5. Its expected set is `service_backups.keys()` plus `'proxmox'` when
  `groups['proxmox_hosts']` is non-empty, both empty in lab. The annotation tells the reader to check
  `journalctl -u <backup>-backup.service` on the host (PVE: `proxmox-backup.service`), using
  `$labels.backup` inside a `{% raw %}` block so Jinja leaves Prometheus' template alone.
- `compose_stack.yml`: render it into `alerts/` next to `service_alerts.yml`, notifying the existing
  reload handler; `validate_alerts.yml` picks it up through its `alerts/*.yml` loop.

### Proxmox host (R6, R7)

- Deploy order: `host_proxmox.yml` (installs node_exporter and the writer, mounts the jellyfin share),
  then `backup_proxmox.yml`. The backup script calls the writer only after `verify_backup` returns 0.
- The writer is installed on `pve` by the same role task as on LXCs; `ReadWritePaths=` gains the
  textfile directory. `test_pve_backup_unit_sandbox` is updated to the new exact line.

### Jellyfin (R10)

- Snapshot: `python3 -c` with `sqlite3.connect(src).backup(sqlite3.connect(dst))` for
  `/var/lib/jellyfin/data/jellyfin.db`, then `cp -a /etc/jellyfin "$WORK_DIR/etc-jellyfin"`.
- Order: Synology share (manual) → `proxmox_mounts` entry and operator run → tfvars template entry and
  runner re-render → pipeline deploy of jellyfin.

### Rollout

Merge once, then switch services one at a time by deploying each (quickstart §3), PVE first and
monitoring last, so the new rule only lands once every expected timestamp exists. Between the merge
and each service's deploy, that service keeps running its old units unchanged.

## Risks

| Risk | Mitigation |
|------|------------|
| A snapshot template drifts from today's behaviour during the move | Steps carried over verbatim; per-service archive file-list diff against a run of the old backup taken just before the deploy (quickstart §0.3, §3). |
| The exact mount check fails on a host where the bind mount is actually missing | Intended (FR-004). The deploy fails with the tfvars entry named. All four were confirmed mounted on 2026-10-23. |
| The prune sees `.partial` files or misses old archives | The glob is `*.tar.gz`; names unchanged. Quickstart checks no `.partial` remains. |
| node_exporter on `pve` triggers existing filesystem or hardware rules | Checked right after the first scrape (quickstart §4). If noisy, exclude on the PVE host only. |
| PVE firewall blocks `:9100` from the monitoring LXC | Checked by the target being `up` (quickstart §4). If blocked, allow `192.168.1.214` in the host firewall. |
| The hermes metric cause is not the export squash setting | FR-015 keeps the fix in scope. Quickstart §0.1 diagnoses before any change. |
| The runner's rendered `prod.tfvars` is stale, so jellyfin gets no bind mount | Re-render explicitly (R10). The deploy-time mount check fails loudly if it is missing. |
| `BackupStale` fires for every backup if monitoring deploys before the services | Monitoring is deployed last (rollout order). |

## Follow-ups (not in this feature)

- Nextcloud passes the DB password on the `mariadb-dump` command line (visible in `ps`). Carried over
  unchanged; a `--defaults-extra-file` would fix it.
- Nextcloud's `config.php` (instance secret, DB password) remains in its archive.
- `pve-exporter` for guest and storage-pool state (the rest of "Proxmox host/guest + storage health").
- CI path for PVE host changes (needs a privilege-model change).
- The tfvars drift check compares top-level keys only (`scripts/lab/lib/tfvars.sh`).

## Complexity Tracking

No constitution violations to justify.
