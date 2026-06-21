# Migrate host-bind NFS services to the in-guest NFS pattern

**Status**: Idea (Backlog) — sparse stub, not yet specced

## Why

Two services still use the **host-mount + `pct set` bind** pattern (NFS on the PVE host →
bind-mounted into the LXC via the Tier-2 orchestrator), instead of the in-guest NFS pattern
(`features_mount = "nfs"` + an Ansible mount) used by jellyfin and financial-scenario. The host-bind
path has a manual/orchestrator seam (PVE `/etc/fstab`, `pct set`, `rebuild-config.json`) that isn't
fully "everything in code". Migrating removes that seam and makes all NFS-backed services consistent.

## Scope

- **nextcloud** — `/mnt/nextcloud` ← `/mnt/nas/homelab_nextcloud` (easier first candidate).
- **immich** — `mp0 /mnt/immich`, `mp1 /mnt/immich-external/photo` (heavier: `immich_ctid: 101` and its
  binds are hardwired into the DR/rebuild orchestrator).

## Watch-outs (expand when specced)

- **uid/gid mapping** differs between an unprivileged-LXC bind mount (idmap) and in-guest NFS (server
  squash) — both apps are ownership-sensitive; verify ownership before cutover.
- `shared_nfs_mount` is **read-only** and asserts `SD-003` RO — needs an rw-capable generalization.
- immich is coupled to the DR orchestrator (`rebuild-config.json`, `rebuild-mounts.sh`, DR drill).
- P1 data services → backup-first, maintenance-window cutover (bytes stay on the NAS; plumbing only).

See [047-financial-scenario-v2-deploy](./047-financial-scenario-v2-deploy.md) (D-006) for the
in-guest pattern this would converge on.
