# Home Assistant Backup & Restore

Backup and recovery for Home Assistant (container install, PR #293) on LXC 112 at
`192.168.1.212`.

## What is protected, and what deliberately is not

The archive is `/config` from the container (`/opt/homeassistant/config` on the LXC):

| Part | Where | Backed up |
|---|---|---|
| Owner and users, refresh and long-lived tokens (including `hermes`'s) | `.storage/auth*` | yes |
| Integrations, devices, entities, areas, HTTP/trusted-proxy settings, exposure to Assist | `.storage/` | yes |
| Hand-edited YAML, automations, scripts, scenes | `configuration.yaml`, `*.yaml` | yes |
| History (recorder) | `home-assistant_v2.db` | yes, copied with SQLite's online backup |

**Excluded on purpose:** `home-assistant_v2.db-wal` / `-shm` (they belong to the running database,
not the snapshot beside them), HA's own `backups/`, and the regenerated `tts/` and `deps/`.

**The archive is as sensitive as the instance.** `.storage/auth` holds every user's tokens, so
whoever has the archive can act as any user, `hermes` included. It stays on the NAS share
`homelab_homeassistant`.

## Automated backup

A systemd timer on the LXC, daily at `05:15` (`service_backups.homeassistant.schedule`, installed
by the `service_backup` role), writing to the Synology through the host NFS mount and bind mount
(`/mnt/homeassistant/backups`). GFS retention: 7 daily, 4 weekly, 6 monthly. Success is published
as `backup_last_success_timestamp_seconds{backup="homeassistant"}`, and the backup staleness
alerts cover it.

```bash
systemctl list-timers homeassistant-backup.timer
journalctl -u homeassistant-backup.service -n 30
```

## Restore drill (non-destructive)

```bash
cd ansible
ansible-playbook playbooks/homeassistant-restore-drill.yml -i inventories/prod/hosts.yml
```

Add `-e homeassistant_restore_archive=<path>` to drill one specific archive instead of the newest.
Run it from a machine that can SSH to the LXC as root. `ci@pve` can, using the vault password file the
pipeline uses (`--vault-password-file /var/lib/homelab-proxmox/vault/.ansible_vault_pass`).

It extracts the newest archive into a `0700` directory under `/tmp`, then:

1. **Checks the archive itself:** `configuration.yaml`, `.storage/auth`,
   `.storage/core.config_entries` and the database are present, there is at least one non-system
   user and one integration entry, and the database passes `integrity_check` and has recorded
   states.
2. **Starts a second Home Assistant with no network** (`network_mode: none`) on the extracted
   copy. With a network it would log in to the same cloud accounts, talk to the same devices
   and run the same automations as a second controller of the house. Integrations fail to set
   up, which is expected.
3. **Asks it whether it is onboarded:** `/api/onboarding` must answer `404`. A fresh install
   answers `200` with the onboarding steps, so `200` means `.storage` did not come back. `/api/`
   must answer `401`.
4. **Tears everything down** in `always:`, whether it passed or failed at any step. That includes
   a bad archive: extraction and the archive checks are inside the block, so the extracted
   tokens never stay behind.

First run, 2026-10-30, archive `homeassistant-backup-20261030-051506`: 2 users, 16 integration
entries, 2,065 recorded states, onboarding `404`, API `401`, 13 s in total. The same check on an
empty `/config` answered onboarding `200`, so the assert fails on an empty restore. A truncated
archive (fails at extraction) and one without `.storage/auth` (fails the archive check) both
left nothing behind.

## Disaster recovery (real restore)

There is no restore script; the steps are short. Two rules shape them:

- **Check the archive while Home Assistant is still running.** A bad archive found after the
  stack is down turns a restore into an outage.
- **Stop at the first error.** If the steps run on after a failed one, `docker compose up` starts
  on an empty `config/`. Home Assistant then comes up as a *fresh install waiting for
  onboarding*, reachable at `ha.hus-sky.no`, and whoever opens it first creates the owner.

On the LXC (`ssh pve`, then `sudo pct exec 112 -- bash`), pick the archive:

```bash
ls -t /mnt/homeassistant/backups/homeassistant-backup-*.tar.gz | head -3
```

Then paste this block as a whole, with `A` set to the chosen archive. `bash -euo pipefail`
stops at the first failing command, and nothing is stopped until the archive is extracted and
checked:

```bash
A=/mnt/homeassistant/backups/homeassistant-backup-YYYYMMDD-HHMMSS.tar.gz bash -euo pipefail <<'EOF'
STAGE=$(mktemp -d /tmp/ha-restore.XXXXXX)            # 0700
tar -xzf "$A" -C "$STAGE"
NEW="$STAGE/$(basename "$A" .tar.gz)/config"
for f in configuration.yaml .storage/auth .storage/core.config_entries; do
  test -f "$NEW/$f" || { echo "archive lacks $f, nothing was stopped"; exit 1; }
done
echo "archive checked: $NEW"

cd /opt/homeassistant
docker compose down
OLD="config.superseded-$(date +%Y%m%d-%H%M%S)"
mv config "$OLD"                                      # set aside, not deleted
mv "$NEW" ./config
docker compose up -d
for i in $(seq 1 36); do
  curl -fsS -o /dev/null http://localhost:8123/manifest.json && { echo "up; old config in /opt/homeassistant/$OLD"; exit 0; }
  sleep 5
done
echo "not up after 3 minutes: check 'docker logs homeassistant'; old config in /opt/homeassistant/$OLD"
exit 1
EOF
```

If it stops before `docker compose down`, the live instance was never touched. If it fails after
the swap, the old config is in `/opt/homeassistant/config.superseded-*`: stop the stack, move
`config` aside, move the superseded copy back and start it again.

Then check `https://ha.hus-sky.no`. The trusted-proxy setting is in `.storage/http`, so it comes
back with the archive. Also check that Hermes still lists its Home Assistant tools; the `hermes`
token is in the restored `.storage/auth`. If the LXC itself was rebuilt, deploy `homeassistant`
through the pipeline first. It seeds `configuration.yaml` only when missing, so restore over the
fresh config afterwards. Remove the superseded directory and the `/tmp/ha-restore.*` staging
directory once you are satisfied.
