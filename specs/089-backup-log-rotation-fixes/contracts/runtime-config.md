# Contract: Runtime Configuration Delivered by 089

**Feature**: [spec.md](../spec.md) | **Date**: 2026-10-21

These are the observable states the fixes guarantee. Later features depend on them: `091` (backup
staleness) watches the two archives, and `092` (log aggregation) reads the rotated log files. Any
change to these values is a breaking change for those features.

## C1 — `proxmox-backup.service` sandbox (on `pve`)

`/etc/systemd/system/proxmox-backup.service`, rendered from
`ansible/roles/proxmox_backup/templates/proxmox-backup.service.j2`, MUST contain exactly these
sandbox lines:

```ini
PrivateTmp=true
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/var/backups/proxmox-staging /mnt/nas-backup /run/lock
```

Compared with today: `ProtectHome` changes from `true` to `read-only`, and `/run/lock` is added to
`ReadWritePaths`. Nothing else changes.

Observable: `systemctl show proxmox-backup.service -p ProtectHome -p ReadWritePaths` shows the values
above. The lock file is `/run/lock/proxmox-backup.lock`, the same for timer and manual runs.

## C2 — Immich backup install (on `immich`)

After a normal pipeline deploy of `immich`:

- `immich-backup.timer` is `enabled` and `active`.
- `/usr/local/bin/backup_immich.sh` exists and is mode `0755`.
- In prod, `/mnt/immich` is a mount point. The deploy fails if it is not.
- `ansible/playbooks/backup.yml` does not exist.

## C3 — Docker daemon logging default (every container host)

`/etc/docker/daemon.json`, as written by `geerlingguy.docker` from `docker_daemon_options` in
`ansible/group_vars/services/vars.yml`:

```json
{
    "log-driver": "json-file",
    "log-opts": {
        "max-file": "3",
        "max-size": "10m"
    }
}
```

Observable on any running container created after rollout:

```text
docker inspect -f '{{.HostConfig.LogConfig.Type}} {{json .HostConfig.LogConfig.Config}}' <ctr>
→ json-file {"max-file":"3","max-size":"10m"}
```

The log files are `/var/lib/docker/containers/<id>/<id>-json.log` plus at most two rotated siblings,
`.1` and `.2`, each at most about 10 MB. `092` reads these paths.
