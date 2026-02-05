# Rebuild Baseline (PVE + NAS Restore)

**Feature**: 032-audit-rebuild-readiness
**Date**: 2026-02-05
**Source**: [docs/operations/backups-proxmox-config-restore.md](docs/operations/backups-proxmox-config-restore.md)

## Baseline Definition

A full rebuild starts from a machine with only PVE installed, restores configuration from NAS backups over NFS, and validates that LXCs, storage, network, and IaC artifacts are consistent.

## Baseline Steps (Summary)

1. Mount NAS backup share and select latest backup.
2. Retrieve age key and decrypt backup archive.
3. Extract backup and verify manifest checksums.
4. Restore LXC configs to `/etc/pve/lxc/`.
5. Restore storage config to `/etc/pve/storage.cfg` and reload PVE services.
6. Restore network config to `/etc/network/interfaces` (test before reboot).
7. Restore `fstab` and remount.
8. Optionally restore IaC artifacts (Terraform state, Ansible inventory) and run drift checks.
9. Start LXCs in dependency order and validate services.

## Validation Signals

- `pct list` shows expected containers.
- `pvesm status` shows expected storage backends.
- `mount | grep nfs` shows expected NFS mounts.
- `terraform plan` and `ansible-playbook --check` show zero drift (if IaC artifacts restored).
