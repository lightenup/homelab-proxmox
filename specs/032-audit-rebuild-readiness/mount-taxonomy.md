# Storage/Mount Taxonomy

**Feature**: 032-audit-rebuild-readiness
**Date**: 2026-02-05

## Categories

1. **Host NFS Mount (PVE)**
   - Managed via Ansible role on PVE (expected: `/etc/fstab` managed by `ansible.posix.mount`).
   - Example: `/mnt/nas/homelab_immich` (Synology export).

2. **Host Bind Mount into LXC (PVE → LXC)**
   - Managed via PVE LXC config `mpX` or `pct set`.
   - Baseline for Immich (per storage baseline and runtime evidence).

3. **In-Guest NFS Mount (LXC)**
   - NFS mounted inside the container; used for shared media (e.g., Jellyfin `/media/video`).

4. **Terraform LXC mountpoints (provider-backed)**
   - `mountpoints` passed via Terraform module; should align with policy and operational guardrails.

## Policy Notes

- The constitution baseline allows host NFS mounts with bind mounts into LXCs for Immich.
- Spec 023 calls out host-path bind mounts as an anti-pattern for shared media and prefers in-guest NFS for shared media services.
- Audit should flag bind mounts **outside the Immich baseline** as policy exceptions requiring review.
