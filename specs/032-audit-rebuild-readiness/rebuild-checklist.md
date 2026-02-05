# Rebuild Checklist (PVE + NAS Restore)

**Feature**: 032-audit-rebuild-readiness
**Date**: 2026-02-05

## Checklist

- [ ] Fresh PVE installed and reachable (version compatible with backup).
- [ ] NAS reachable from PVE (network + DNS).
- [ ] Mount NAS backup share at `/mnt/nas-backup`.
- [ ] Retrieve age key and decrypt latest backup archive.
- [ ] Extract archive and verify manifest checksums.
- [ ] Restore LXC configs to `/etc/pve/lxc/`.
- [ ] Restore storage config to `/etc/pve/storage.cfg` and restart PVE services.
- [ ] Restore network config (`/etc/network/interfaces`) and validate before applying.
- [ ] Restore `fstab` and remount; validate NFS mounts.
- [ ] Restore IaC artifacts (Terraform state, Ansible inventory) if present.
- [ ] Run `terraform plan` for drift check (expect zero changes).
- [ ] Run `ansible-playbook --check` for drift check (expect zero changes).
- [ ] Start LXCs in dependency order; validate service health.

## Validation Signals

- `pct list` shows expected containers
- `pvesm status` shows expected storage
- `mount | grep nfs` shows expected mounts
