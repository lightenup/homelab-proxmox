# Jellyfin Media Mount (in-guest)

Goal: ensure Jellyfin can access shared media via an **in-container** NFS mount at `/media/video`.

Spec 023 policy is **no host-path bind mounts in Terraform**, so the PVE host does not need to mount the export for Jellyfin.

## Implementation

- Ansible role: `ansible/roles/shared_nfs_mount`
- Mount: `192.168.1.109:/volume1/video` → `/media/video`
- Options: `ro,nofail,_netdev,x-systemd.automount`

## Verification (inside the container)

```bash
findmnt --target /media/video
findmnt -n -o OPTIONS --target /media/video
```

Expected: the options contain `ro`.

## Evidence (deploy runs)

During `pve-service-deploy apply`, the run evidence pack includes:

- `reports/workload/shared-nfs-mount.txt`
- `reports/assertions.workload.json` (includes `SD-003`)
- `reports/healthcheck/jellyfin.txt` (includes a mount check)

## Backup share

The Jellyfin backup (`service_backups.jellyfin`, spec 091) writes to `/mnt/jellyfin/backups`,
bind-mounted from the Synology share `homelab_jellyfin` via the host mount
`/mnt/nas/homelab_jellyfin` (`proxmox_mounts` role) and `service_mountpoints.jellyfin.backups`.

Create the share by hand in DSM:

1. Control Panel → Shared Folder → create `homelab_jellyfin`.
2. Edit → NFS Permissions → add a rule for `192.168.1.112` (the PVE host) with the same
   privilege, squash and security settings as the `homelab_financial_scenario` rule.
3. Confirm from `pve`: `showmount -e 192.168.1.109 | grep homelab_jellyfin`, then apply
   `host_proxmox.yml` (mount) and deploy Jellyfin (bind mount, then the backup role).

Export settings used: _record here when the share is created (match `homelab_financial_scenario`)._
