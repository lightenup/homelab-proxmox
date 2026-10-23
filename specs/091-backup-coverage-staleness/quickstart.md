# Quickstart: Backup Coverage and Staleness

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Contract**: [contracts/backup-contract.md](./contracts/backup-contract.md)

The validation and rollout guide. Every step is read-only unless it says it changes something. Host
IPs and names are from `ansible/inventories/prod/hosts.yml`. Prometheus is `http://192.168.1.214:9090`.

## 0. Before implementation

### 0.1 Hermes mount metric (FR-015, research R9)

On hermes (`192.168.1.221`), as root:

```bash
ls -ld /mnt/hermes/backups
runuser -u node_exporter -- stat -f /mnt/hermes/backups
journalctl -u node_exporter --since -1h | grep -i hermes
```

Expected today: `stat -f` fails with permission denied. Compare the share's NFS export with
`homelab_financial_scenario` in Synology DSM (Control Panel → Shared Folder → Edit → NFS
Permissions: squash setting). Align them, then check:

```bash
curl -s 'http://192.168.1.214:9090/api/v1/query' \
  --data-urlencode 'query=node_filesystem_avail_bytes{mountpoint="/mnt/hermes/backups"}'
```

Done when it returns one series and `node_filesystem_device_error` for that mount is `0`. Record the
cause and fix in the table in §5.

### 0.2 Jellyfin NAS share (FR-009, research R10)

Manual, on the Synology: create share `homelab_jellyfin`, with an NFS export to `192.168.1.112`
using the same settings as `homelab_financial_scenario`. On jellyfin, confirm the DB path:
`ls -l /var/lib/jellyfin/data/jellyfin.db`.

### 0.3 Baseline archive lists (per service, just before its deploy)

Not done up front. For each of the four migrated backups, **immediately before** that service's
pipeline deploy in §3, run the old backup once by hand and save its file list (on the service host,
as root). Last night's archive is not a usable baseline: hermes' `open-webui/` and `agent/` gain
files every day.

```bash
systemctl start <key>-backup.service            # old role's script, still installed
f=$(ls -t <dir>/<key>-backup-*.tar.gz | head -1)
tar -tzf "$f" | sed 's|^[^/]*/||' | sort > /root/091-baseline-<key>.txt
```

This adds one archive for that day; retention treats it like any other daily archive.

## 1. Static checks (before any deploy)

From the repo root:

```bash
pre-commit run --all-files
bash scripts/ci/python-tests.sh
cd ansible && for p in playbooks/{nextcloud,financial-scenario,immich,hermes,jellyfin,monitoring,host_proxmox,backup_proxmox}.yml; do
  ansible-playbook --syntax-check -i inventories/prod/hosts.yml "$p"; done
```

Render the rule file locally with the monitoring host's variables, then check it (needs Docker):

```bash
ansible -i inventories/prod/hosts.yml monitoring -c local -m template \
  -a "src=roles/monitoring_stack/templates/backup_alerts.yml.j2 dest=/tmp/backup_alerts.yml"
docker run --rm -v /tmp:/w --entrypoint promtool prom/prometheus:v3.8.1 check rules /w/backup_alerts.yml
```

Expected: no errors, and the rendered expression lists `absent(…{backup="…"})` for nextcloud,
financial-scenario, immich, hermes, jellyfin and proxmox.

```bash
git ls-files ansible/roles | grep -E '^(ansible/roles/(financial_scenario|hermes|immich|nextcloud)_backup/|.*backup-monitoring)' ; echo "rc=$?"
grep -rn HermesBackupStale ansible/ ; echo "rc=$?"
```

Expected: both print nothing and `rc=1` (SC-006).

## 2. Proxmox host (operator machine only — principle V exception)

From `ansible/`, with root SSH to `pve` and `.vault-pass.txt`:

```bash
ansible-playbook -i inventories/prod/hosts.yml playbooks/host_proxmox.yml --vault-password-file .vault-pass.txt   # node_exporter, jellyfin NFS mount
task ansible:backup                                                                                               # timer + sandbox + metric
```

Check on `pve`:

```bash
systemctl cat proxmox-backup.timer | grep -c '^OnCalendar='     # 1
systemctl show proxmox-backup.service -p ReadWritePaths         # includes /var/lib/node_exporter/textfile_collector
findmnt --mountpoint /mnt/nas/homelab_jellyfin                  # nfs
systemctl start proxmox-backup.service && systemctl status proxmox-backup.service --no-pager
cat /var/lib/node_exporter/textfile_collector/backup_proxmox.prom
curl -s localhost:9100/metrics | grep backup_last_success
scripts/backup/verify_proxmox_backup.sh "$(ls -t /mnt/nas-backup/*.tar.zst.age | head -1)"   # exit 0 (SC-004)
```

## 3. Service switch-over, one at a time (FR-006)

Order: financial-scenario → hermes → immich → nextcloud → jellyfin. Each is a normal pipeline deploy
(`Prod 1 → Prod 2`) of that service, preceded by its §0.3 baseline run. Do not start the next until
the current one is recorded in §5. Run the new backup straight after the deploy, so the two runs see
the same data.

After each deploy, on the service host:

```bash
systemctl list-timers '<key>-backup.timer'                                    # one timer, next run at its slot
systemctl start <key>-backup.service && journalctl -u <key>-backup.service -n 30 --no-pager
f=$(ls -t <dir>/<key>-backup-*.tar.gz | head -1)
tar -tzf "$f" | sed 's|^[^/]*/||' | sort | diff /root/091-baseline-<key>.txt -  # empty (immich: only "-.env")
cat /var/lib/node_exporter/textfile_collector/backup_<key>.prom
ls <dir>/*.partial 2>/dev/null                                                 # nothing
```

Per service:

- **hermes**: remove the old metric file: `rm /var/lib/node_exporter/textfile_collector/hermes_backup.prom`.
  Run `playbooks/hermes-restore-drill.yml` (SC-003).
- **immich**: `tar -tzf "$f" | grep -c '\.env$'` prints `0`. Run `playbooks/restore-drill.yml` with
  `group_vars/services/secrets.yml` loaded; it must pass with `.env` rendered, not extracted
  (SC-003, FR-008).
- **nextcloud**: confirm maintenance mode is off afterwards (`occ maintenance:mode`). Manual restore
  into a scratch MariaDB container: load `dump.sql`, check table count; `php -l config.php`. Record.
- **financial-scenario**: `sqlite3 scenarios.db 'pragma integrity_check; select count(*) from scenarios;'`
  on the extracted file. Record.
- **jellyfin**: confirm `findmnt --mountpoint /mnt/jellyfin/backups` is `nfs` before starting.
  No baseline; check the archive has `jellyfin.db` and `etc-jellyfin/`, and that
  `pragma integrity_check` on the extracted DB returns `ok`. Restore once on a scratch copy: stop
  Jellyfin, swap in the DB and `/etc/jellyfin` from the archive, start, log in, check one user's
  watch history, swap back. Record.

Destination check (once, on financial-scenario, during its window). The bind mount cannot be
removed from inside the LXC, so run a copy of the script pointed at a path that is not a mount:

```bash
findmnt --mountpoint /mnt/financial-scenario/backups --types nfs,nfs4; echo rc=$?   # 0
sed 's|^BACKUP_MOUNT=.*|BACKUP_MOUNT=/mnt/financial-scenario|' \
  /usr/local/bin/backup_financial_scenario.sh > /tmp/091-mountcheck.sh
bash /tmp/091-mountcheck.sh; echo rc=$?                                              # non-zero
ls -t /mnt/financial-scenario/backups | head -1                                      # unchanged
stat -c %Y /var/lib/node_exporter/textfile_collector/backup_financial-scenario.prom  # unchanged
rm /tmp/091-mountcheck.sh
```

This relies on the script setting the mount in one `BACKUP_MOUNT=` line and checking it before
anything else (contract C1, step 1). Covers acceptance scenario US2-3.

## 4. Monitoring (last)

Pipeline deploy of `monitoring`. Then:

```bash
curl -s http://192.168.1.214:9090/api/v1/targets | python3 -c 'import sys,json;[print(t["labels"]["instance"],t["health"]) for t in json.load(sys.stdin)["data"]["activeTargets"] if t["labels"]["job"]=="node-exporter"]' | grep 192.168.1.112   # up
curl -s http://192.168.1.214:9090/api/v1/query --data-urlencode 'query=time() - backup_last_success_timestamp_seconds' # 6 series, all < 129600
curl -s http://192.168.1.214:9090/api/v1/alerts | grep -c BackupStale                                                  # 0 (SC-001)
curl -s http://192.168.1.214:9090/api/v1/alerts | python3 -m json.tool | grep -E '"alertname"' | sort | uniq -c          # no new noise from pve filesystems (R6 risk)
```

On the monitoring host: `crontab -l | grep -c backup-monitoring` is `0`; if not, remove the entry
(`crontab -e`), `rm /usr/local/sbin/backup-monitoring.sh /var/log/monitoring-backup.log`. One-off.

### 4.1 Deliberate break (SC-002)

On financial-scenario: `mv backup_financial-scenario.prom /root/` in the textfile directory. Within
`for` (15 min) plus a scrape, `BackupStale{backup="financial-scenario"}` fires, and no other
`BackupStale`. Pushover receives a warning. Move the file back; the alert clears.

For the staleness branch, write an old timestamp the same way
(`backup_last_success_timestamp_seconds{backup="financial-scenario"} <now − 37 h>`), confirm the alert,
then run the backup service to restore a real value.

## 5. Record

| Item | Date | Result | Notes |
|------|------|--------|-------|
| 0.1 hermes mount metric cause / fix | 2026-10-23 | Cause: `/mnt/hermes` in the hermes LXC is `0700 root`, so `node_exporter` gets `Permission denied` on `statfs` of `/mnt/hermes/backups`. Not the export: both shares mount identically (`nfs vers=3 rw`), the host fstab entries match, and `/mnt/financial-scenario` is `0755`. Fix: `service_backup` sets the mount's parent to `0755`; applies on the hermes deploy | Read-only via `ci@pve` + `sudo pct exec 110`. No DSM change needed for hermes |
| 2 PVE: one timer trigger, metric, verify script exit 0 | 2026-10-23 | PASS | One `OnCalendar=*-*-* 02:00:00`; `ReadWritePaths` includes the textfile dir; run `Result=success`; `backup_last_success_timestamp_seconds{backup="proxmox"}` fresh; `verify_proxmox_backup.sh` exit 0, 33 files. `host_proxmox.yml` first needed HashiCorp's new apt key added on pve, then stops at `tailscale_host` (variable names drifted, pre-existing, not touched); node_exporter 1.12.1 was installed before that. `backup_proxmox.yml` ran clean. Prod `prod.tfvars` hand-edited for `jellyfin.backups` (T042, backup `prod.tfvars.bak.20261023-162151`) |
| 3 financial-scenario: diff empty, manual restore | 2026-10-23 | PASS | Baseline (old role) `docker-compose.yml`, `scenarios.db`; Prod 1 run 39979163150 (plan no-op), Prod 2 run 39981160294; new run `Result=success`, diff empty, metric fresh, no `.partial`, timer still 04:15, names unchanged; restore: `integrity_check` ok, 1 row in `stored_scenarios` |
| 3 hermes: diff empty, drill passes | 2026-10-23 | PASS | Baseline 1366 entries (old role); Prod 1 run 39982549123 (plan no-op), Prod 2 run 39983171716; new run `Result=success`; diff vs baseline has only agent `cron/output/*` files (2 added, 2 removed, written by the agent every ~16 min between the two runs), nothing else; timer 04:45 unchanged. `/mnt/hermes` now `0755`, `node_exporter` can `statfs` the mount and `node_filesystem_avail_bytes{mountpoint="/mnt/hermes/backups"}` exists (FR-015, 0.1 fix confirmed); old `hermes_backup.prom` removed, no `hermes_backup_*` series. `hermes-restore-drill.yml`: failed=0 (1 account, 29 conversations, manifest match, heartbeat ran), torn down |
| 3 immich: diff = `.env` only, drill passes | 2026-10-23 | PASS | Baseline `.env`, `docker-compose.yml`, `dump.sql` (old role); Prod 1 run 39984393165 (plan no-op), Prod 2 run 39984896454; new run `Result=success`; diff vs baseline exactly `< .env`, archive has 0 `.env` entries (FR-008); timer 04:30 unchanged; live containers untouched. `restore-drill.yml` run as `ci@pve` with a temp vault password file and the PVE `secrets.yml`: failed=0, `.env` rendered from `roles/immich/templates/.env.j2`, DB restored, API `pong`, stack torn down. It cannot run from the operator Mac: `immich_db_password` is only in the PVE vault store |
| 3 nextcloud: diff empty, manual restore | 2026-10-23 | PASS | Baseline `config.php`, `docker-compose.yml`, `dump.sql` (old role); Prod 1 run 39987436006 (plan no-op), Prod 2 run 39987980053; new run `Result=success`, diff empty, maintenance mode off afterwards (also after the refusal test), metric fresh, no `.partial`, timer 04:00 unchanged; refusal test exit 2, nothing created. Restore: dump loaded into a scratch `mariadb:11` (no network), 161 tables = live 161, 2 `oc_users` rows, container removed. Note: `/mnt/nextcloud/backups` is now `0755` (was flipped to `0777` by the old role after every deploy; the nextcloud role sets `0755`); backups still write as the export owner |
| 3 jellyfin: archive contents, manual restore | 2026-10-23 | PASS (no swap-back) | Prod 1 run 39988394935 (Terraform plan no-op; the deploy script applied `mp1` and ran `pct reboot` on the LXC, a brief Jellyfin restart; Jellyfin healthy after, HTTP 200), Prod 2 run 39988903566. `/mnt/jellyfin/backups` is NFS (`homelab_jellyfin`). First run by hand before monitoring was switched: `Result=success`; archive 6.1 MB with `jellyfin.db` (22,450,176 B, identical to live) and the six `/etc/jellyfin` files, no cache/metadata; archived DB `integrity_check` ok, 1 user, 5804 items; timer 05:00; refusal test exit 2. Deviation: did not swap the archived DB into the live Jellyfin (it is the only copy of users and watch history); integrity and contents checked instead. `/etc/jellyfin` holds no credential (only an empty `CertificatePassword` tag) |
| 3 destination check refuses a non-mount | 2026-10-23 | PASS (financial-scenario) | Script copy with `BACKUP_MOUNT=/root` exits 2 ("not an NFS mount"), creates nothing, metric unchanged |
| 4 monitoring: pve target up, 6 series fresh, BackupStale quiet, cron gone | 2026-10-23 | PASS | Prod 1 run 39989256770 (no-op plan; Prometheus unchanged after the LAB stage: 41 targets, 33 rules), Prod 2 run 39989686306. After: 42 targets, `node-exporter` 12 up / 0 down, `pve` `192.168.1.112:9100` up; 13 rule groups / 33 rules (`HermesBackupStale` gone, `backup_alerts`/`BackupStale` ok, inactive, for 15m, 6 `absent()` terms); 6 `backup_last_success_timestamp_seconds` series fresh (proxmox, financial-scenario, hermes, immich, nextcloud, jellyfin); no alerts firing. Old cron entry, `/usr/local/sbin/backup-monitoring.sh` and `/var/log/monitoring-backup.log` were still present and were removed by hand (crontab saved to `/root/crontab.pre-091.bak` in the monitoring LXC; the log showed the old job had only ever logged "Backup directory ... does not exist") |
| 4.1 deliberate break (absent and stale) | 2026-10-23 | PASS | On financial-scenario. Absent: moved `backup_financial-scenario.prom` away at 18:50:09; `BackupStale{backup="financial-scenario"}` fired at 19:06:05 (about 16 min = `for: 15m` plus a scrape), and no other `BackupStale`; restored the file at 19:06:06, cleared by 19:07:07. Stale: wrote a timestamp 37 h old at 19:07:07; fired at 19:23:14, only financial-scenario; ran the real backup (`Result=success`), cleared by 19:24:16. Delivery: Alertmanager `alertmanager_notifications_total` pushover 2 → 5 and webhook (ntfy) 2 → 5, rising together across the test. Final metric is a real value; the script ran one more real backup on exit, so one extra archive for that day |
