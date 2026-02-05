# Rebuild Readiness Assessment

**Feature**: 032-audit-rebuild-readiness
**Date**: 2026-02-05

## Dependencies & Prerequisites

- PVE install media + compatible version.
- NAS access and NFS exports available.
- Age private key for Proxmox backup.
- Access to repo artifacts (Terraform state, Ansible inventory) if used.

## Evidence Mapping

| Requirement | Evidence | Status |
| --- | --- | --- |
| Baseline steps documented | rebuild-baseline.md | ✅ |
| Runtime inventory captured | runtime-inventory.md | ✅ |
| Host mounts verified | runtime-inventory.md | ✅ |
| Immich bind mounts verified | runtime-inventory.md | ✅ |
| Jellyfin shared mount verified | runtime-inventory.md | ✅ |

## Gaps & Blockers

- `/mnt/nas/photo` host mount is used by Immich but not clearly managed by Ansible (see FND-002).
- `proxmox_mounts` role not wired into host playbook (see FND-001).
- In-guest mount validation for monitoring, reverse proxy, and homeassistant completed (no mounts detected).
