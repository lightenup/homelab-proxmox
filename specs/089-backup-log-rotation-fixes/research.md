# Research: Backup and Log Rotation Quick Fixes

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Date**: 2026-10-21

All findings come from the repo at branch `089-backup-log-rotation-fixes` and one read-only check on
`pve` as `ci` on 2026-10-21. That check showed `proxmox-backup.service` with `Result=exit-code` and a
last timer firing at 02:04. `/mnt/nas-backup` is already NFSv3-mounted at host level.

## R1 — How the Proxmox backup gets its lock (Fix 1, FR-001)

- **Finding**: `proxmox-config-backup.sh.j2:12` hard-codes `LOCK_FILE="/run/lock/proxmox-backup.lock"`.
  The unit sets `ProtectSystem=strict`, which makes all of `/run` read-only. Its `ReadWritePaths=`
  lists only the staging base and the NAS mount point.
- **Decision**: Add `/run/lock` to `ReadWritePaths=` in `proxmox-backup.service.j2`. The script is
  unchanged.
- **Rationale**: This is a one-line change. The lock path stays the same for timer runs and manual
  runs of the script (the runbooks tell operators to run it directly), so the two still exclude each
  other. `/run/lock` is a world-writable, sticky tmpfs that is cleared at boot, so a stale lock
  cannot survive a reboot. `flock` locks also release when the process dies. Widening write access
  to a world-writable lock directory exposes nothing new.
- **Alternatives considered**:
  - `RuntimeDirectory=proxmox-backup` with the lock moved to `/run/proxmox-backup/`. This is the
    systemd-native option, but it needs a script change. Manual runs outside systemd would then
    lack the directory or use a different lock, so manual and timer runs would no longer exclude
    each other. Rejected.
  - `ReadWritePaths=-/run/lock/proxmox-backup.lock` (the file only). The file may not exist before
    the first run; the `-` prefix silently skips it, so the first run would still fail. Rejected.

## R2 — The second defect: the hidden decryption key (Fix 1, FR-002)

- **Finding**: `verify_backup()` (script lines 401–434) runs `age -d -i ${AGE_KEY_PATH}`, with the
  default `/root/.age/proxmox-backup.key`. `ProtectHome=true` makes `/root` inaccessible inside the
  unit, so once the lock is fixed, verification fails and the run exits non-zero. The
  `REPO_PATH` collection (also under `/root`) is disabled (`proxmox_backup_repo_path` is commented
  out in `group_vars/proxmox_hosts/vars.yml:42`), so it is not affected.
- **Decision**: `ProtectHome=read-only`. The user chose this on 2026-10-21; the spec's
  Clarifications and FR-002 record it.
- **Rationale**: The smallest change that keeps the script's built-in decrypt check. Nothing under
  `/root` becomes writable.
- **Alternatives considered**: Drop the on-host decrypt check, so the private key need not be on
  the host. Move the key out of `/root`. The user rejected both: the first changes the script and
  runbooks, the second needs a manual key move.
- **Residual risk**: `ci` cannot read `/root/.age` to confirm the key is present. The quickstart
  checks it as root before the first run (spec Assumptions).

## R3 — Other sandbox interactions in the Proxmox backup run (Fix 1, SC-001)

Checked so the first successful run is not blocked by a third defect:

| Operation | Path | Under the sandbox |
|-----------|------|-------------------|
| Mount the NAS | `/mnt/nas-backup` | Already mounted at host level, so `mount_nas()` skips the mount. The mount point is in `ReadWritePaths`. |
| Unmount at exit (`cleanup`) | `/mnt/nas-backup` | Takes place in the unit's private mount namespace and does not propagate to the host. Harmless. |
| Staging | `/var/backups/proxmox-staging` | In `ReadWritePaths`. |
| Logging | `systemd-cat`, stdout and stderr | Journal socket, allowed. |
| Reading config | `/etc/pve`, `/etc/network`, `/mnt/nas/homelab_ci` | Read-only access is enough. |
| `mktemp` / `/tmp` | private `/tmp` | `PrivateTmp=true`, writable. |

- **Decision**: No further unit changes. If the first live run still fails, the spec makes the fix
  in scope (Assumptions). The quickstart captures the journal for diagnosis.

## R4 — How the Proxmox backup is deployed (Fix 1, FR-003)

- **Finding**: No workflow deploys `backup_proxmox.yml`. It is imported by `site.yml` and run by hand
  through `task ansible:backup` (`Taskfile.yml:247`) or `scripts/backup/run_proxmox_backup.sh`. Both
  use `-i inventories/static/hosts.yml`, which **does not exist**. The real inventory is
  `inventories/prod/hosts.yml`, where the `proxmox_hosts` group contains `proxmox` at
  `192.168.1.112`.
- **Decision**: The existing deploy path is the manual playbook run. Fix the inventory path where
  it serves this playbook: `Taskfile.yml:247`, `scripts/backup/run_proxmox_backup.sh:32`, and the
  operator commands in `docs/operations/backups-proxmox-config*.md`. Deploy with
  `task ansible:backup`. Other stale `inventories/static` references are a follow-up.
- **Rationale**: FR-003 requires the existing path, not a hand edit on the host. The path is broken,
  so it must be repaired to satisfy FR-003.
- **CI limitation (constitution principle V)**: checked 2026-10-21 from `ci@pve`. `ssh -i
  ~/.ssh/id_lxc_deploy root@192.168.1.112` gives `Permission denied (publickey,password)`, and
  `sudo -l` shows passwordless sudo only for `qm`, `pct`, `pvesm`, `pvesh`, `pveversion`, `systemctl`,
  `journalctl` and a few file commands. So CI cannot run a playbook against the host as root. That
  is intended by the privilege tiers. Decision (spec Clarifications, analysis session): use
  principle V's documented-exception clause. FR-014 puts the limitation and the operator command in
  `docs/operations/backups-proxmox-config.md`.
- **Alternatives considered**: Run through `proxmox-apply.yml`. That runs `pve-lab rebuild`, not
  `site.yml`. Rejected. Give CI root on the host: a privilege-model change, rejected for this
  feature.

## R5 — Where `immich_backup` goes, and the NAS guard (Fix 2, FR-004, FR-005)

- **Finding**: Other services apply their backup role in the same play as the service role, after
  it. `nextcloud.yml` uses `geerlingguy.docker`, `nextcloud`, `nextcloud_backup`. The role's
  variables (`immich_backup_path: /mnt/immich/backups`, schedule `*-*-* 04:30:00`, retention) are
  already in `group_vars/services/vars.yml:431-435`.
- **Finding**: `immich_require_nas_mount` is set in `immich.yml` and defaulted in the `immich` role,
  but no task reads it. Nothing checks that `/mnt/immich` is a mount. If it is missing,
  `immich_backup`'s first task would create `/mnt/immich/backups` on the container's root disk, and
  backups would silently stay on the container.
- **Decision**: Add `immich_backup` to the second play of `playbooks/immich.yml`, after `immich`. Add
  one `assert` task at the top of `roles/immich_backup/tasks/main.yml`. When
  `immich_require_nas_mount` is true (prod), it fails unless `/mnt/immich` is in `ansible_mounts`.
  In the lab, where it is false, the assert is skipped and the backup writes locally.
- **Rationale**: This matches the existing pattern. The assert uses the variable that already
  expresses "the NAS is required here", and it prevents a backup that looks healthy but is not off
  the container (spec edge case).
- **Alternatives considered**: Put the guard in the `immich` role. That would protect photos as
  well, but it widens scope beyond this fix and changes a role the spec does not touch. Recorded as
  a follow-up, not done.

## R6 — Removing `playbooks/backup.yml` (Fix 2, FR-006)

- **Finding**: Live references: `docs/runbooks/immich-backup-restore.md:30` ("Manual Backup").
  References in historical specs (`specs/006-*`) and in the backlog stay as they are, per FR-006.
- **Decision**: Delete `ansible/playbooks/backup.yml`. In the runbook, replace the playbook command
  with `systemctl start immich-backup.service` and keep the direct-script alternative.

## R7 — Setting the log limits once for every Docker host (Fix 3, FR-008, FR-009)

- **Finding**: `geerlingguy.docker` writes `/etc/docker/daemon.json` only when
  `docker_daemon_options` is non-empty. It notifies `restart docker` and then runs
  `meta: flush_handlers` (`tasks/main.yml:77`), so the daemon restarts **before** the service's own
  compose tasks in the same play.
- **Finding**: In `inventories/prod/hosts.yml`, every Docker host, including `monitoring`, is in the
  `services` group, so `group_vars/services/vars.yml` reaches all of them. `monitoring.yml`
  additionally loads `group_vars/monitoring/vars.yml`, which does not set `docker_daemon_options`. The
  lab's generated host is also in `services`.
- **Finding**: Docker hosts are those whose playbook or role uses `geerlingguy.docker`: immich,
  monitoring (through `monitoring_stack/tasks/docker.yml`), nextcloud, financial-scenario,
  market-model, eurooffice, llm-router, hermes and ntfy. `jellyfin.yml` and `reverse_proxy.yml` do
  not use it, which confirms the spec's assumption.
- **Decision**: Add to `group_vars/services/vars.yml`, next to the existing Docker block:
  `docker_daemon_options: {log-driver: json-file, log-opts: {max-size: "10m", max-file: "3"}}`.
- **Rationale**: One definition reaches all 9 hosts with no per-host or monitoring-specific copy.
  `log-driver` is stated explicitly, so the meaning does not depend on Docker's default. `log-opts`
  values must be strings in `daemon.json`.
- **Alternatives considered**: `logging:` in each compose file. That means nine edits and drift.
  Rejected. Adding `live-restore`: the user rejected it on 2026-10-21.

## R8 — Recreating containers (Fix 3, FR-010)

- **Finding**: `docker_compose_v2` (and `docker compose up -d` in `monitoring_stack`) recreates a
  container only when its compose definition hash changes. Daemon `log-opts` are applied when a
  container is created and are not part of that hash. A deploy restarts the containers but keeps
  their old log config.
- **Decision**: A one-off operator step per host, right after that host's pipeline deploy. It
  recreates every compose project on the host from that project's own working directory, using
  `docker compose ls` to discover them. The exact command is in [quickstart.md](./quickstart.md);
  the contract is in [contracts/runtime-config.md](./contracts/runtime-config.md). No code is added
  (the user chose this on 2026-10-21).
- **Rationale**: This is a one-time migration. Any later recreate (version bumps) keeps the limits
  automatically, because they are now the daemon default.
- **Note**: The transient `financial-scenario-seed` container runs only on first deploy and is
  removed straight away, so it never holds a log worth rotating.

## R9 — Verifying the log cap (Fix 3, SC-006)

- **Decision**: On each host, `docker inspect` every container and check
  `.HostConfig.LogConfig.Config` for `max-size=10m` and `max-file=3`. Then `du` the container's
  `*-json.log*` files and confirm no container's total exceeds 30 MB. Both checks are in the
  quickstart.
