# Phase 1 Data Model: Market-Model Service Deploy

This is an infrastructure deploy; "entities" are the persisted/declared artifacts the deploy creates
or depends on, not application tables. The application owns its schema (market-model `006`).

## Path-set store (`path-sets.sqlite`)

- **What**: The service's only persistent state — a SQLite file the **api** role creates and migrates
  on startup at `/app/data/path-sets.sqlite`, backed by host bind-mount `{{ market_model_data_dir }}/data`.
- **Owner/permissions**: Host dir owned by **uid `100` / gid `65534`** (mode `0755`), the non-root
  `appuser` identity the image runs as (D-006). The deploy MUST NOT seed, copy, or initialise the
  `.db` file.
- **Writers**: Exactly one — the `api` container. The `mcp` container mounts no data volume.
- **Lifecycle**: Survives restart and upgrade (bind-mount persists). Treated as a **disposable
  cache** — not backed up (D-001). On wipe, recreated on next startup with the curated library
  re-seeded from the image.
- **Rows**:
  - **Curated library row** (`curated-stress`): seeded from image-baked YAML on every startup via
    idempotent `INSERT OR IGNORE` — re-seed never clobbers.
  - **Assembled sets**: content-addressed `sha256:` ids; identical inputs reproduce a byte-identical
    blob + id.
  - **Generated sets**: reproducible from the recipe encoded in the PathSet `version` string (the
    auto-picked seed is recorded there).

## Path set (application object, served over api/mcp)

- **Identity**: `id` + `version`. Consumers (orchestrator/PFS) carry both downstream; that pair alone
  re-runs an assembly/draw per the reproducibility contract.
- **Validation/state**: Owned by the app, not this deploy. The deploy only verifies a round-trip
  (generate → get by id returns the byte-identical blob).

## Service version pin (`market_model_version`)

- **What**: The single source of truth for the deployed image tag, in
  `ansible/group_vars/services/vars.yml`.
- **Rules**: A real published GHCR tag (first release `0.3.0`), never empty, never `latest`
  (asserted in preflight, FR-009). Bumping it + re-running the playbook performs an in-place upgrade.

## LXC declaration (`market_model_lxc`)

- **What**: An unprivileged Debian 12 LXC declared via the `lxc_service` Terraform module.
- **Attributes**: `cores=2`, `memory=2048`, `disk_gb=16`; static `ip = service_ips["market-model"]`;
  standard bridge/gateway/nameserver/searchdomain/ssh keys. **No `features_mount`** (no in-guest NFS).
- **Inventory**: Exposed via the Terraform `ansible_inventory` output → generated `hosts.yml`.

## Monitoring contract (`host_vars/market-model.yml`)

- **What**: Blackbox liveness only (no app metrics), mirroring `financial-scenario.yml`.
- **Fields**: `healthcheck_url {scheme: http, port: 8000, path: /healthz}`, `healthcheck_profile: lan`,
  `healthcheck_expect_status: 200`; `monitoring_contract.liveness_targets` probing
  `http://<market-model-ip>:8000/healthz` (`module: http_2xx`); alert `MarketModelDown`
  (`probe_success == 0 for 5m`, severity critical).
