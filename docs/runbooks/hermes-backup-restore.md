# Hermes Backup & Restore

Backup and recovery for the Hermes AI workspace (spec `065-hermes-ai-workspace`), on the LXC
at `192.168.1.221`.

## What is protected, and what deliberately is not

`data-model.md` § *Workspace state* defines what must survive:

| Part | Where | Backed up | Rebuildable |
|---|---|---|---|
| Conversations, accounts, settings, saved prompts, scheduled runs | SQLite (`webui.db`) | yes | **no** |
| Uploaded documents | local disk | yes | no — the originals |
| Vector index | local disk (`vector_db/`) | yes | yes, but expensively |

**Excluded on purpose:**

- **`cache/`** — Hugging Face model weights downloaded at runtime. `AUDIO_TTS_ENGINE=transformers`
  alone pulls ~1.2 GB of SpeechT5 + HiFiGAN. Measured 2026-09-21, before this exclusion existed:
  the archive was **755 MB, of which 99.8% was model cache**, and the irreplaceable state was
  ~2 MB. It re-downloads on demand — the first voice request after a restore is slow, and that
  is the whole cost.
- **`webui.db-wal` / `webui.db-shm`** — the live write-ahead log belongs to the *running*
  database, not to the point-in-time snapshot placed beside it in the archive. Shipping both
  pairs a consistent database with a WAL from a different moment.

The database is captured with `sqlite3.Connection.backup()` inside the container, not `cp` —
a WAL-mode database can be torn mid-copy.

## Automated backup

A systemd timer on the LXC, daily at `04:45` (`service_backups.hermes.schedule`, installed by the `service_backup` role), writing to the
Synology via the host NFS mount + bind mount (`/mnt/hermes/backups`). GFS retention: 7 daily,
4 weekly, 6 monthly.

```bash
systemctl list-timers hermes-backup.timer      # when it next runs, when it last did
journalctl -u hermes-backup.service -n 30      # what happened last time
```

Staleness is alerted: `BackupStale{backup="hermes"}` (warning) fires when no successful run has
been recorded for 36 hours, or none ever. The series `backup_last_success_timestamp_seconds{backup="hermes"}`
comes from the backup script itself via node_exporter's textfile collector, so a timer that
silently stops firing is visible.

### Manual backup

```bash
ssh root@192.168.1.221 'systemctl start hermes-backup.service'
```

## Verifying a backup without touching production

**Run this rather than assuming.** It extracts the latest archive, stands a second Open WebUI
up on `hermes_restore_test_port` (8081) against it, waits for health, then reads the restored
database back out of the running instance and asserts it is intact and populated. Torn down
unconditionally afterwards, pass or fail.

```bash
cd ansible
ansible-playbook playbooks/hermes-restore-drill.yml -i inventories/prod/hosts.yml
```

The drill instance is deliberately given **no gateway credentials and no tool servers** — the
question is whether the state comes back, not whether every integration works, and a
throwaway container has no business holding the gateway key or spending its request allowance.

## Disaster recovery (real restore)

`restore_hermes.sh` is deployed on the LXC beside the backup script.

```bash
ssh root@192.168.1.221
restore_hermes.sh                                   # most recent archive
restore_hermes.sh /mnt/hermes/backups/hermes-backup-YYYYMMDD-HHMMSS.tar.gz
```

It verifies the archive **before** stopping anything — tarball readable, `webui.db` present,
`integrity_check` clean — because discovering a corrupt archive after the stack is down turns
a restore into an outage. It then stops the stack, **moves the current workspace aside** to
`…/open-webui.superseded-<timestamp>` rather than deleting it, installs the restored copy,
starts the stack and waits for health.

**Nothing is deleted automatically.** The superseded directory is left for you to remove once
you are satisfied — a restore from the wrong archive is then itself recoverable.

## Full rebuild from code

If the LXC is gone entirely:

```bash
gh workflow run lxc-deploy-lab.yml --ref main -f service=hermes -f apply=true
```

Terraform recreates the container, Ansible reinstalls the stack, then run `restore_hermes.sh`
to bring the workspace back. Prerequisites that live outside the LXC and must already exist:
the vault variables, the `homelab_hermes` NFS share on the Synology, and the host mount on
`pve` (`proxmox_mounts`).

## What a real rebuild is actually like

Measured 2026-09-21 by destroying the LXC and rebuilding it (spec `065`, T048/SC-006). The
cycle works — conversations, memory, account, settings and the MCP registration all returned,
`integrity_check ok` — but two things will surprise you:

- **The first deploy after a destroy may fail on the network check**, with
  `192.168.1.221 is unreachable`. The container was created correctly; the check is a
  single un-retried `ping` racing a booting container. **Just run the deploy again** — see
  [backlog `077`](../backlog/077-cold-create-network-check-race.md).
- **The SSH host key changes**, because it is a new machine. Ansible is unaffected (the
  inventory sets `StrictHostKeyChecking=no`), but your own `ssh` will refuse with
  `REMOTE HOST IDENTIFICATION HAS CHANGED`. Clear the stale entry:
  `ssh-keygen -R 192.168.1.221`.

Order matters: **rebuild first, restore second.** The rebuild recreates the admin account
from the vault bootstrap and leaves an empty workspace; `restore_hermes.sh` then replaces it
wholesale with the backed-up one.

## Gotchas

- **The model cache is not in the backup** (by design). The first voice request after a
  restore re-downloads ~1.2 GB and will feel broken. It is not.
- **Restore replaces the live workspace.** Use the drill, not `restore_hermes.sh`, to answer
  "is this backup any good".
- **Chats are the cheap part.** `webui.db` is under a megabyte; the vector index is the part
  that is expensive to rebuild, because re-embedding costs inference time against a
  rate-limited single host.
