# Implementation Plan: Backup and Log Rotation Quick Fixes

**Branch**: `089-backup-log-rotation-fixes` | **Date**: 2026-10-21 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/089-backup-log-rotation-fixes/spec.md`

## Summary

Three small fixes, each independent:

1. **Proxmox config backup** (P1). In `proxmox-backup.service.j2`, add `/run/lock` to
   `ReadWritePaths=` so the script can take its lock, and set `ProtectHome=read-only` so its
   verification step can read the age key under `/root/.age`. Also repair the broken inventory path
   in the manual deploy entry points (`Taskfile.yml`, `scripts/backup/run_proxmox_backup.sh`) so the
   existing deploy path works.
2. **Immich DB backup** (P1). Add `immich_backup` to `playbooks/immich.yml` after `immich`. Add a
   prod-only assert that `/mnt/immich` is a mount, delete the unused `playbooks/backup.yml`, and
   update the one runbook that points at it.
3. **Docker log rotation** (P2). Set `docker_daemon_options` once in `group_vars/services/vars.yml`
   (`json-file`, `10m` × `3`). Roll it out host by host: pipeline deploy, then a documented one-off
   `docker compose up -d --force-recreate` per host, recorded in the quickstart.

No new roles, playbooks or scripts. One guard test file is added to the existing guardrail tests.
Research: [research.md](./research.md).

## Technical Context

**Language/Version**: Ansible (existing roles and playbooks), Jinja2 systemd unit template, Bash
(existing scripts; one path fix). No new language.

**Primary Dependencies**: `geerlingguy.docker` (vendored; uses `docker_daemon_options` and flushes
its restart handler mid-play), `community.docker.docker_compose_v2`, systemd sandboxing directives,
`age`, `zstd`.

**Storage**: Synology NAS over NFS: `/mnt/nas-backup` on `pve` and `/mnt/immich` bind mount on
`immich`. Container logs on each LXC's root disk under `/var/lib/docker/containers`.

**Testing**: Static checks (`ansible-playbook --syntax-check`, `ansible-lint` on the touched
files, greps for removed paths). One pytest guard file,
`python/tests/guardrails/test_backup_log_rotation_config.py`, uses PyYAML (already in
`python/requirements-test.txt`) and runs in PR CI through `scripts/ci/python-tests.sh`. It asserts
the unit sandbox lines, the prod inventory in the backup deploy entry points, `immich_backup` after
`immich` in `immich.yml`, that `playbooks/backup.yml` is gone, and the `docker_daemon_options`
value. Then the live checks in [quickstart.md](./quickstart.md). This meets the constitution's
test-driven rule: the guard test is the feasible automated part, and the live behaviour (backups
running, log caps) can only be shown on the estate.

**Target Platform**: the Proxmox VE host `pve`, plus Debian LXCs running Docker (9 hosts).

**Project Type**: Infrastructure configuration (Ansible-managed homelab).

**Performance Goals**: N/A. Archive freshness under 24 h (SC-001); per-container logs at most 30 MB
(SC-006).

**Constraints**: Keep the unit's existing hardening (FR-002); deploy only through existing paths
(FR-003, FR-004); one host at a time for the Docker rollout (FR-010, SC-007); the Mac cannot
`git push` (Zscaler), so push through the GitHub API (see `AGENTS.md`).

**Scale/Scope**: 1 Proxmox host, 1 Immich LXC, 9 Docker LXCs. About 9 files changed, 1 added (guard test) and 1
deleted.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Spec-driven workflow | PASS | Work comes from `specs/089-*`; tasks follow from `/speckit-tasks`. The runbook update ships in the same change (FR-006). |
| II. Secrets policy | PASS | No secrets touched. The age private key stays on `pve` and in the password manager. Only the existing public key is in vars. |
| III. Separation of concerns | PASS | Only Ansible changes, inside the host and the LXCs. No Terraform. |
| IV. Code economy | PASS | No new roles, playbooks, scripts or variables. One shared var for 9 hosts. The recreate is a documented one-off, not permanent code. `backup.yml` is deleted. The one added assert uses an existing, currently unread variable. The one new test file is required by the test-driven rule. |
| V. Dual-provisioning parity | PASS through the principle's documented-exception clause | Immich and Docker changes go through the existing pipeline, which also runs from a laptop through `pve-service-deploy`. The PVE host backup deploy can run **only from an operator machine**. CI's account on `pve` (`ci`) has no root SSH to the host (checked 2026-10-21: `Permission denied (publickey)`), and its passwordless sudo is limited to `qm`, `pct`, `systemctl` and similar, by design of the privilege tiers. Principle V allows a one-context step if the limitation is documented and an alternative is given. FR-014 and task T007 write that into `docs/operations/backups-proxmox-config.md`; the manual playbook run (`task ansible:backup`) is the alternative. A CI path needs a privilege-model change and is a follow-up. |
| CI/CD: no destructive automation without barriers | PASS | The Docker restart happens inside the existing gated `Prod 1 → Prod 2` deploy. The recreate is manual and done one host at a time. |
| Test-driven changes | PASS | Static checks, one automated guard test (FR-013), and live verification. |

**Post-design re-check (after Phase 1, revised after `/speckit.analyze`)**: All PASS. Principle V
for the PVE backup deploy relies on the documented-exception clause (FR-014), not on a CI path.

## Project Structure

### Documentation (this feature)

```text
specs/089-backup-log-rotation-fixes/
├── plan.md                    # This file
├── research.md                # Phase 0: R1–R9 decisions
├── data-model.md              # Phase 1: archives, container host, rollout record
├── quickstart.md              # Phase 1: static checks, live checks, rollout record
├── contracts/
│   └── runtime-config.md      # Unit sandbox, Immich install, daemon.json (relied on by 091/092)
├── checklists/
│   └── requirements.md
└── tasks.md                   # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
ansible/
├── roles/proxmox_backup/templates/proxmox-backup.service.j2   # ProtectHome=read-only; +/run/lock  (Fix 1)
├── playbooks/immich.yml                                       # + immich_backup after immich      (Fix 2)
├── roles/immich_backup/tasks/main.yml                         # + prod assert /mnt/immich mounted (Fix 2)
├── playbooks/backup.yml                                       # DELETED                           (Fix 2)
└── group_vars/services/vars.yml                               # + docker_daemon_options           (Fix 3)
Taskfile.yml                                                   # ansible:backup inventory → prod   (Fix 1)
scripts/backup/run_proxmox_backup.sh                           # inventories/static → prod         (Fix 1)
docs/operations/backups-proxmox-config{,-restore}.md           # inventories/static → prod; + deploy-limitation note (Fix 1, FR-014)
docs/runbooks/immich-backup-restore.md                         # manual backup → systemctl start   (Fix 2)
python/tests/guardrails/test_backup_log_rotation_config.py     # NEW guard test, all three fixes   (FR-013)
```

**Structure Decision**: Edit existing files, plus one guard test file. Every change sits in the
file that already owns the behaviour: the unit template for the sandbox, the service playbook for
which roles are applied, the shared service vars for daemon options.

## Implementation Notes by Fix

### Fix 1 — Proxmox config backup (research R1–R4)

- The unit change is exactly what contract C1 shows. The script is unchanged; the lock path stays
  `/run/lock/proxmox-backup.lock`.
- Deploying the template notifies `reload systemd` and `restart backup timer`, which already exist.
- Inventory fix, limited to the backup deploy path: `inventories/static/hosts.yml` becomes
  `inventories/prod/hosts.yml` in `Taskfile.yml:247`, `scripts/backup/run_proxmox_backup.sh:32`,
  `docs/operations/backups-proxmox-config-restore.md:564,615` and
  `docs/operations/backups-proxmox-config.md:472,475`. Other stale `inventories/static` references
  (`Taskfile.yml:223,235` for `host_proxmox.yml`, `scripts/healthcheck/healthcheck.py:42`,
  `docs/architecture/019-*`) are left for a follow-up.
- Before the first run, check as root that the private key is present (quickstart Fix 1, step 1).
- **Where it runs (principle V exception)**: from an operator machine with root SSH to `pve`
  (`192.168.1.112`) and `ansible/.vault-pass.txt`. Not from `ci@pve`, which has no root SSH to
  the host. `docs/operations/backups-proxmox-config.md` gets a short "Deploy path and CI
  limitation" section saying this (FR-014).

### Fix 2 — Immich DB backup (research R5–R6)

- `playbooks/immich.yml`, second play: `roles: [geerlingguy.docker, immich, immich_backup]`. The play
  already sets `immich_require_nas_mount` (false in the lab).
- `roles/immich_backup/tasks/main.yml`, new first task: `ansible.builtin.assert` that
  `'/mnt/immich' in (ansible_mounts | map(attribute='mount'))`,
  `when: immich_require_nas_mount | default(true) | bool`. Its fail message names the missing bind
  mount. Use `immich_backup_path | dirname` instead of a literal, so the check follows the variable.
- Delete `ansible/playbooks/backup.yml`. In `docs/runbooks/immich-backup-restore.md` ("Manual
  Backup"), replace the playbook command with `systemctl start immich-backup.service`.

### Fix 3 — Docker log rotation (research R7–R9)

- `group_vars/services/vars.yml`, under the existing `# Docker configuration (geerlingguy.docker)`
  block:
  ```yaml
  docker_daemon_options:
    log-driver: json-file
    log-opts:
      max-size: "10m"
      max-file: "3"
  ```
- No playbook or role edits. `monitoring_stack` imports `geerlingguy.docker` and inherits the var
  through the `services` group.
- Rollout and recreate: follow [quickstart.md](./quickstart.md), Fix 3. Immich is done with Fix 2.
  Nextcloud goes last.

## Risks

| Risk | Mitigation |
|------|------------|
| A third sandbox defect appears on the first PVE run | Research R3 checked the remaining paths. In scope per the spec. Quickstart step 4 captures the journal. |
| The age private key is not on `pve` | Checked before the first run. If missing, restore it from the password manager. |
| `/mnt/immich` is not a mount in prod and the assert fails the deploy | Intended: it fails rather than backing up locally. Check `findmnt` and the LXC bind mount. |
| The Docker restart on deploy affects a host's containers | Accepted (spec). One host at a time. Nextcloud goes last. |
| A project not visible to `docker compose ls` (not running) keeps the old log config | Its containers are not running and produce no logs. It picks up the limit when next started through its deploy. |

## Follow-ups (not in this feature)

- No CI path for `backup_proxmox.yml`. Principle V is met here through its documented exception; a
  CI path needs CI root access to `pve`, which is a privilege-model change.
- Remaining references to the non-existent `inventories/static/hosts.yml`: the `host_proxmox` tasks
  in `Taskfile.yml`, `scripts/healthcheck/healthcheck.py:42`, and
  `docs/architecture/019-proxmox-lab-harness.md:188`.
- `immich_require_nas_mount` is still not enforced by the `immich` role itself (photos path).
- Freshness alerting for both archives belongs to `091`. Shipping logs off the host belongs to
  `092`.

## Complexity Tracking

No constitution violations to justify.
