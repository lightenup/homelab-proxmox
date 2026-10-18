# Spec: Consolidate Service Version Variables into group_vars

**Created**: 2026-06-20
**Status**: Delivered — `specs/047-consolidate-service-versions/`

## Summary

Service image versions are currently split across role `defaults/` files and `group_vars`, meaning a version bump requires knowing which file a given service uses:

| Variable(s) | Current location |
|---|---|
| `immich_version`, `financial_scenario_version` | `group_vars/services/vars.yml` ✓ |
| `prometheus_version`, `grafana_version`, `telegraf_version`, `alertmanager_version`, `blackbox_exporter_version` | `group_vars/monitoring/vars.yml` ✓ |
| `nextcloud_version`, `nextcloud_exporter_version` | `roles/nextcloud/defaults/main.yml` ✗ |

The goal is to move the two outlier version variables into `group_vars/services/vars.yml` so that all service version pins live in one file and role internals don't need to be opened for routine upgrades.

## Changes

### 1. `ansible/group_vars/services/vars.yml`

Add a `# Service versions` section at the top of the file (matching the style of `group_vars/monitoring/vars.yml`) containing all service version pins:

```yaml
# Service versions
nextcloud_version: "32"
nextcloud_exporter_version: "0.9.0"
# immich_version and financial_scenario_version already present — move into this block
immich_version: "v2.4.0"
financial_scenario_version: "0.1.0"
```

The existing `immich_version` and `financial_scenario_version` entries stay in this file but are relocated into the new section.

### 2. `ansible/roles/nextcloud/defaults/main.yml`

Delete the `nextcloud_version` and `nextcloud_exporter_version` lines entirely. No comment, no placeholder — the role has no default for these; they must be set in inventory.

## Out of Scope

- **Image registry paths** (`financial_scenario_api_image`, `financial_scenario_gui_image`) — stable infrastructure values; left in role `defaults/`.
- **Hardcoded floating tags** in compose templates (`mariadb:11`, `redis:7-alpine`) — separate decision.
- **Digest-pinned images** (Immich's Postgres and Valkey) — intentionally locked inline for reproducibility; a different upgrade mechanism applies.

## Verification

1. Run the nextcloud playbook against a host and confirm no `undefined variable` errors — proving group_vars is resolved correctly without the role defaults.
2. Confirm `grep -r "nextcloud_version\|nextcloud_exporter_version" ansible/roles/` returns no results.
3. Confirm all four version pins appear under the `# Service versions` block in `group_vars/services/vars.yml`.

## Acceptance

After the change, all service version bumps are done by editing `group_vars/services/vars.yml` or `group_vars/monitoring/vars.yml` only. No role `defaults/` file needs touching for a routine upgrade.
