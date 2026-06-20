# Spec: Consolidate Service Version Variables into group_vars

**Created**: 2026-06-20
**Status**: Draft (Backlog)

## Summary

Service image versions are currently defined in three different places:
- `ansible/group_vars/services/vars.yml` — immich, financial-scenario
- `ansible/group_vars/monitoring/vars.yml` — prometheus, grafana, telegraf, alertmanager, blackbox-exporter
- `ansible/roles/nextcloud/defaults/main.yml` — nextcloud, nextcloud-exporter
- `ansible/roles/adguard/defaults/main.yml` — adguard-exporter

This means a version bump requires knowing which file a given service uses, rather than having one canonical place to look.

The goal is to move all version variables into the appropriate `group_vars` file, so every version pin lives alongside its peers and is visible without opening role internals.

## Change

1. Move `nextcloud_version` and `nextcloud_exporter_version` from `roles/nextcloud/defaults/main.yml` into `group_vars/services/vars.yml`.
2. Move `adguard_exporter_version` from `roles/adguard/defaults/main.yml` into `group_vars/services/vars.yml`.
3. Remove the version variables from the role `defaults/` files (or leave them absent — the group_vars value takes precedence anyway, but removing avoids confusion about which is canonical).

## Out of Scope

- Hardcoded images in compose templates (`mariadb:11`, `redis:7-alpine`) — these use floating minor-version tags and are a separate decision.
- Digest-pinned images (Immich's Postgres and Valkey entries) — intentionally locked inline for reproducibility; a different upgrade mechanism applies.

## Acceptance

After the change, all version bumps are done by editing `group_vars/services/vars.yml` or `group_vars/monitoring/vars.yml` only. No role `defaults/` file needs touching for a routine upgrade.
