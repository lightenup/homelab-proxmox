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
