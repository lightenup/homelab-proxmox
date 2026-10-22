# Quickstart: Backup and Log Rotation Quick Fixes

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Contract**:
[contracts/runtime-config.md](./contracts/runtime-config.md)

This is the validation and rollout guide. Each fix is independent and can be done in any order;
Fix 1 and Fix 2 are P1. Record results in the tables at the end.

## Prerequisites

- Branch `089-backup-log-rotation-fixes`, pushed (see `AGENTS.md` for the Zscaler push path).
- **Fix 1 runs from an operator machine** that has root SSH to `pve` (`ssh root@192.168.1.112`
  works) and `ansible/.vault-pass.txt` (`ansible.cfg` sets `vault_password_file = .vault-pass.txt`).
  It cannot run from `ci@pve`: `ci` has no root SSH to the host (plan, principle V).
- **Fix 2 restore drill and Fix 3 recreate run as `ci@pve`**. Use the pipeline's copy of the repo,
  `/home/ci/homelab-proxmox` (rsynced by `lxc-apply-prod.yml`, so it holds the branch you just
  deployed), and the LXC deploy key `~/.ssh/id_lxc_deploy`, which can reach root on every service
  LXC. Reach a host with:
  ```bash
  ssh -i ~/.ssh/id_lxc_deploy -o StrictHostKeyChecking=no root@<host-ip>   # IPs: ansible/inventories/prod/hosts.yml
  ```
  A laptop holding the same key works the same way (principle V parity).
- **Vault password for Ansible on `ci@pve`**: create a temporary file and remove it afterwards,
  the same way the pipeline does:
  ```bash
  umask 077; pwfile="$(mktemp -t ansible-vault.XXXXXX)"; read -rs pw; printf '%s' "$pw" > "$pwfile"; unset pw
  export ANSIBLE_VAULT_PASSWORD_FILE="$pwfile"     # afterwards: rm -f "$pwfile"
  ```

## Static checks (before any deploy, FR-013)

```bash
cd ansible
ansible-playbook -i inventories/prod/hosts.yml playbooks/backup_proxmox.yml --syntax-check
ansible-playbook -i inventories/prod/hosts.yml playbooks/immich.yml --syntax-check
ansible-lint playbooks/immich.yml roles/immich_backup roles/proxmox_backup
test ! -e playbooks/backup.yml
rg -n "playbooks/backup\.yml" ../docs/runbooks          # expect no hits
cd .. && .venv/bin/python -m pytest -c python/pytest.ini --no-cov python/tests/guardrails/test_backup_log_rotation_config.py   # all pass (FR-013)
```

Expected: syntax checks pass, lint is clean for the touched files, the grep returns nothing, and
the guard test passes. For the `inventories/static` check, see tasks T008.

## Fix 1 — Proxmox host configuration backup

1. **Key present** (as root on `pve`, read-only): `test -s /root/.age/proxmox-backup.key && echo ok`.
   If it is missing, restore it from the password manager first (spec Assumptions).
2. **Deploy** (manual path, research R4), from the operator machine, repo root: `task ansible:backup`.
3. **Unit matches the contract** (C1):
   `systemctl show proxmox-backup.service -p ProtectHome -p ReadWritePaths`
   → `ProtectHome=read-only`; `ReadWritePaths` contains `/run/lock`.
4. **One run now**: `systemctl start proxmox-backup.service; systemctl show proxmox-backup.service -p Result`
   → `Result=success`. On failure: `journalctl -u proxmox-backup.service -n 100 --no-pager`. A new
   defect is in scope (spec Assumptions).
5. **Fresh archive on the NAS**: `ls -lt /mnt/nas-backup/proxmox-backup-*.tar.zst.age | head -1`
   → mtime under 24 h.
6. **Decrypts** (SC-001): `age -d -i /root/.age/proxmox-backup.key <archive> | zstd -d | tar -t | head`
   → lists `proxmox/` configuration entries.
7. **Timer armed** (SC-002): `systemctl is-enabled proxmox-backup.timer; systemctl is-active proxmox-backup.timer; systemctl list-timers proxmox-backup.timer`
   → `enabled`, `active`, and a NEXT time. Stopping the service during a run stops the timer as
   well; re-run the deploy, or `systemctl start proxmox-backup.timer`, if it shows `inactive`.
8. **Failure notification** (FR-016), once `ntfy_pve_backup_token` is in vault and ntfy is
   deployed: `scripts/healthcheck/ntfy-acl-check.sh` passes all 35 cells, and a message published
   with the `pve_backup` token to topic `pve-backup` arrives on the phone.

## Fix 2 — Immich database backup

1. **Deploy** through the normal pipeline:
   ```bash
   gh workflow run lxc-promote-prod.yml --ref 089-backup-log-rotation-fixes -f ref=089-backup-log-rotation-fixes -f service=immich
   gh workflow run lxc-apply-prod.yml   --ref 089-backup-log-rotation-fixes -f promotion_run_id=<promote run id> -f confirm_apply_prod=deploy-prod
   ```
   This deploy also applies the Docker log default. Do Fix 3's recreate step for `immich` right
   afterwards.
2. **Installed** (C2, SC-003), on `immich`:
   `systemctl is-enabled immich-backup.timer; systemctl is-active immich-backup.timer; findmnt /mnt/immich`
   → `enabled`, `active`, and a mount line.
3. **One run** (SC-004): `systemctl start immich-backup.service; systemctl show immich-backup.service -p Result`
   → `success`; `ls -lt /mnt/immich/backups | head -2` shows a new `immich-backup-*.tar.gz`.
4. **Restore drill** (SC-004), as `ci@pve` with `ANSIBLE_VAULT_PASSWORD_FILE` set (Prerequisites):
   `cd /home/ci/homelab-proxmox/ansible && ansible-playbook -i inventories/prod/hosts.yml playbooks/restore-drill.yml --private-key ~/.ssh/id_lxc_deploy -e @/var/lib/homelab-proxmox/vault/group_vars/services/secrets.yml`
   (`immich_db_password` is only in that gitignored file).
   → recap `failed=0`. The live Immich is untouched. Then `rm -f "$pwfile"`.

## Fix 3 — Container log rotation, one host at a time

Repeat for each host in task order (T021–T029: immich with Fix 2, then lowest-traffic first, then
nextcloud last):

1. **Deploy** through the pipeline (`lxc-promote-prod.yml` then `lxc-apply-prod.yml`, as above, with
   `-f service=<host>`). This writes `daemon.json` and restarts Docker (first brief interruption).
2. **Daemon default present** (C3): `cat /etc/docker/daemon.json` matches the contract.
3. **One-off recreate** (FR-010; second brief interruption), as root on the host (from `ci@pve`
   with `ssh -i ~/.ssh/id_lxc_deploy root@<host-ip>`):
   ```bash
   docker compose ls --format json | python3 -c 'import json,sys
   for p in json.load(sys.stdin): print(p["Name"], p["ConfigFiles"].split(",")[0])' |
   while read -r name file; do
     (cd "$(dirname "$file")" && docker compose -p "$name" up -d --force-recreate)
   done
   ```
   This recreates only running projects (no `--all`), from each project's own directory, so its
   `.env` and override files are used as at deploy time.
4. **Every container carries the limit**:
   ```bash
   docker ps -q | xargs docker inspect -f '{{.Name}} {{json .HostConfig.LogConfig.Config}}'
   ```
   → every line shows `{"max-file":"3","max-size":"10m"}`. Any container without it was not
   recreated: recreate its project and check again.
5. **Service healthy**: the pipeline's healthcheck for the host passes, or open its URL.
6. Record the row.

**Final sweep** (SC-006), once every row is done, on each host:

```bash
for d in /var/lib/docker/containers/*/; do du -cb "$d"*-json.log* 2>/dev/null | tail -1; done | sort -n | tail -3
```

→ the largest total is at most 31457280 bytes (30 MB). Fill that host's "Verified ≤ 30 MB" cell.

## Results

### Fix 1 and Fix 2

| Check | Result | Date / evidence |
|-------|--------|-----------------|
| Static checks and guard test | pass | 2026-10-22; guardrails 12/12 |
| PVE key present | pass | 2026-10-22; archive decrypts with `/root/.age/proxmox-backup.key` |
| PVE manual run `Result=success` | pass | 2026-10-22 07:03:45; deployed with `--skip-tags prerequisites` (apt on `pve` fails on HashiCorp's repo key, unrelated). Earlier runs: 2026-10-21 aborted by the secret scan (T034), failure mail hung 10 min (T035). Scan of `/mnt/nas/homelab_ci/infra_state` as root: no hits |
| PVE archive < 24 h on NAS, decrypts (SC-001) | pass | 2026-10-22; `proxmox-backup-20261022-070345.tar.zst.age`, lists `proxmox-config/` and `iac-artifacts/nas-state/` |
| PVE timer armed: enabled, active, NEXT set (SC-002) | pass | 2026-10-22; enabled, active, NEXT 2026-10-23 00:02. The timer also fired the missed run at 07:03:37 (`proxmox-backup-20261022-070338`) |
| ntfy `pve_backup` publisher: ACL check 35/35, test message received (FR-016) | pass | 2026-10-22; ntfy promote 39731922976 + apply 39733902488, PVE redeployed. ACL check 35/35 PASS. Test publish from `pve` with `/etc/proxmox-backup.conf` to `pve-backup` → 200; same token to `alerts` → 403. Owner confirmed receipt on the phone |
| Immich lab deploy (backup installed, NAS assert skipped) | pass, amended | 2026-10-21; run 39622632981 (39617192746 failed first). `c1d8eb4` skips all `immich_backup` tasks in the lab, which has no NAS mount, so no timer is installed there; the lab check proves only that the deploy is not broken |
| Immich timer enabled + active after pipeline deploy (SC-003) | pass | 2026-10-21; run 39625646532, timer enabled+active, NAS mount present |
| Immich run succeeds + restore drill `failed=0` (SC-004) | pass | 2026-10-22; drill `failed=0` against the scheduled `immich-backup-20261022-043007.tar.gz`. Two fixes (T036): pass `secrets.yml`, and restore into the service's own database image (the drill used `pgvecto-rs` without VectorChord, so Immich v3 exited) |

### Rollout record (FR-011, SC-005, SC-007)

The `#` column is the record's row number, not the execution order. Execution order is set by
tasks T021–T029: immich goes first, together with Fix 2.

| # | Host | Deploy run id | Recreated (date) | All containers limited | Verified ≤ 30 MB | Notes |
|---|------|---------------|------------------|------------------------|------------------|-------|
| 1 | ntfy | 39627481394 | 2026-10-21 | yes | yes (0.4 MB) | |
| 2 | market-model | 39629799440 | 2026-10-21 | yes (re-checked 2026-10-22: 2/2 limited) | yes (0.9 MB) | |
| 3 | financial-scenario | 39631272045 | 2026-10-21 | yes | yes (0.9 MB) | GHCR pull denied (pre-existing) |
| 4 | eurooffice | 39632627592 | 2026-10-21 | yes | yes (0.5 MB) | |
| 5 | llm-router | 39633680758 | 2026-10-21 | yes | yes (0.9 MB) | |
| 6 | hermes | 39635116408 | 2026-10-21 | yes | yes (0.8 MB) | |
| 7 | monitoring | 39636383434 | 2026-10-21 | yes | yes (2.1 MB) | LAB failed (pre-existing); `dnswatch` (hand-made `alpine` debug container, stopped since 2026-08, empty log, not in IaC) predates rotation, left for the owner to remove |
| 8 | immich | 39625646532 | 2026-10-21 | yes | yes (0.2 MB) | Done with Fix 2 |
| 9 | nextcloud | 39637718089 | 2026-10-21 | yes | yes (1.9 MB) | LAB failed (pre-existing) |

A row is `verified` when both yes/no columns are yes. SC-005 holds when all 9 rows are verified.

Final sweep, largest per-container total across all hosts (SC-006): 2083836 bytes (2.1 MB, monitoring), 2026-10-22. Limit 31457280.
