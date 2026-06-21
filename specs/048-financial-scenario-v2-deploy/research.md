# Research: Financial-Scenario v2 Deploy (Stateful)

All open questions from the originating backlog item were resolved in its Decision Log (D-001…D-006)
before this plan. This document records each decision in research format, plus the implementation
patterns verified against the live codebase. No `NEEDS CLARIFICATION` markers remain.

## D-001 / FR-002, FR-003 — Scenario store location & path

- **Decision**: Mount a host bind-mount `{{ financial_scenario_data_dir }}/scenarios` → `/app/data` on
  the **`api` service only**. Do **not** set `SCENARIOS_DB_PATH`; the app default
  `/app/data/scenarios.db` is correct once `/app/data` is the mount point.
- **Rationale**: The api reads `SCENARIOS_DB_PATH` (default `/app/data/scenarios.db`, per the app's
  `deps.py`) and runs its migration in lifespan startup. Mounting at the parent dir `/app/data` keeps
  the DB plus its WAL/SHM sidecar files together on the host. Leaving the env unset means one fewer
  override to drift; the override path is documented in the compose template comment so a future
  relocation is a one-liner.
- **Alternatives considered**: (a) Docker named volume `scenarios-data` (what the app's own compose
  uses) — rejected; a host bind-mount matches the immich/jellyfin durable-data convention and makes
  the DB directly reachable by the backup role without `docker volume inspect` indirection.
  (b) Setting `SCENARIOS_DB_PATH` explicitly — rejected as redundant noise (YAGNI, single-use var).

## D-005 — Storage mechanism (host bind-mount vs named volume)

- **Decision**: Host bind-mount on the LXC filesystem, api-only. The `mcp` service MUST NOT mount it.
- **Rationale**: `api` is the single writer in the single-engine topology; `mcp` forwards to `api` and
  holds no state. A second mount on `mcp` would imply a second writer and break the authority model.
  Mirrors `{{ immich_data_dir }}/postgres:/var/lib/...`.
- **Alternatives considered**: named volume (see D-001); bind-mount on both services (rejected — single
  writer).

## D-002 / FR-008 — Backup mechanism (consistent SQLite snapshot)

- **Decision**: Full `financial_scenario_backup` role + systemd service/timer. Snapshot is produced by
  SQLite's **online backup** run *inside* the api container, e.g.
  `docker exec financial_scenario_api python -c "import sqlite3; src=sqlite3.connect('file:/app/data/scenarios.db?mode=ro', uri=True); dst=sqlite3.connect('/app/data/<snapshot>.db'); src.backup(dst); dst.close(); src.close()"`,
  then the snapshot file is copied out, tarred with a copy of the rendered `docker-compose.yml`, and
  written to the in-guest NFS mount. GFS retention identical in shape to `nextcloud_backup`.
- **Rationale**: The store is WAL-mode. A raw `cp` (or `tar`) of `scenarios.db` under concurrent writes
  can capture a torn file (WAL not checkpointed into the main DB). `sqlite3`'s backup API (or
  `VACUUM INTO`) produces a transactionally consistent single-file snapshot safe to archive. Python +
  `sqlite3` are already present in the api image (the healthcheck uses `python -c "import urllib..."`).
- **Alternatives considered**: (a) raw `cp`/`tar` of the live DB — rejected (torn-DB risk).
  (b) Stop the stack, copy, restart — rejected (avoidable downtime; online backup is non-disruptive).
  (c) `VACUUM INTO` — acceptable equivalent; `.backup()` chosen as it streams pages and tolerates
  concurrent writers without holding a long write lock.
- **Snapshot cleanup**: the temporary snapshot `.db` written under `/app/data` must be removed after
  tarring so it is not itself backed up on the next run.

## D-006 / FR-006, FR-007 — Backup-destination mount pattern (NAS → LXC)

- **Decision**: **In-guest NFS mount** (jellyfin pattern): set `features_mount = "nfs"` on the LXC
  module (FR-007) and mount `192.168.1.109:/volume1/homelab_financial_scenario` →
  `/mnt/financial-scenario/backups` with opts `rw,nofail,_netdev,x-systemd.automount` from Ansible
  (FR-006). **No** PVE `/etc/fstab` entry, **no** `pct set` bind-mount.
- **Rationale**: Keeps the whole deploy self-contained in Terraform + Ansible and conforms to Spec
  `023` (no host-path bind mounts in Terraform). The immich/nextcloud host-mount + bind pattern has a
  manual PVE-fstab seam; the in-guest pattern avoids it. `nofail` + `x-systemd.automount` make the
  mount resilient to the NAS being unavailable at boot.
- **Where the mount lives**: performed **inside the `financial_scenario_backup` role**, not via
  `shared_nfs_mount`. `shared_nfs_mount` is hardcoded `ro` and asserts `SD-003` (read-only) into the
  evidence pack; it cannot serve a rw destination without conditional branching. A single one-off rw
  `ansible.builtin.mount` (same opts shape, minus `ro`) in the consuming role is the lower-coupling
  choice (see plan Complexity Tracking).
- **`features_mount` application**: the `lxc_service` module declares the feature but the comment notes
  it is applied host-side by the orchestrator via `pct set` (Tier 2), and `features` is in the module's
  `ignore_changes`. So the TF edit is image-independent and takes effect through the existing
  orchestrator post-create step — no LXC recreate.
- **Operator pre-req (done)**: the Synology share `homelab_financial_scenario` with rw export rules for
  `192.168.1.217/32` (prod) and `192.168.20.218/32` (lab) was created by the operator on 2026-06-21
  (out of pipeline; the only manual step). Verify in quickstart with `showmount -e 192.168.1.109`.

## D-004 / FR-009 — MCP shared secret stays image-baked

- **Decision**: No per-deploy MCP token. The auth gate remains in the GUI image's nginx with the
  literal `mcp-local-secret`. Carry forward `046`'s posture.
- **Rationale**: PFS `046`/`047` did not make the secret env-configurable; making it vault-configurable
  is a separate upstream change (out of scope). The preflight already documents this and asserts no MCP
  token.

## D-003 — LXC sizing

- **Decision**: Keep 2c/2048MB. Confirm headroom during rollout; bump only on observed memory pressure
  under concurrent saves.
- **Rationale**: Single-engine topology means `api` now also serves MCP traffic, but the workload is
  light (one human + a few agents) and `mcp` no longer loads its own engine/reference data, freeing
  memory. No TF `cores`/`memory` change in this feature.
- **Alternatives considered**: pre-emptive bump to 4096MB — rejected (YAGNI; no measured need).

## FR-004 — MCP becomes a stateless HTTP client

- **Decision**: In the compose template, for the `mcp` service: **remove** the `reference_data`
  bind-mount, **add** `API_BASE_URL: http://api:8000`, **add** `depends_on: api` with
  `condition: service_healthy`. Keep `MCP_TRANSPORT: http` and `MCP_PORT: 8001`.
- **Rationale**: The app's `client.py` reads `API_BASE_URL`; the engine and reference data now live
  only on `api`. `depends_on: service_healthy` guarantees `mcp` never starts before its authority.
  Transport/port stay set or the FastMCP server defaults to stdio and never binds the port.

## FR-005 — First-deploy vs. upgrade safety

- **Decision**: Reference data keeps the existing seed-when-empty logic (unchanged). For the scenario
  store, the role only ensures `{{ financial_scenario_data_dir }}/scenarios` exists with correct
  mode/ownership; it MUST NOT seed, copy, or initialise a `.db`. The app creates and migrates the DB
  idempotently on startup.
- **Rationale**: The store holds host-only user state. Any seed/copy step risks clobbering real data on
  upgrade. `ansible.builtin.file: state=directory` is idempotent and never touches an existing DB file.
- **Verification**: deploy `0.1.0`, save a scenario, bump to `0.2.2`, re-run — the saved scenario must
  survive (SC-001).
- **Directory ownership/mode**: create the `scenarios` dir `0755` owner `root` (matching the existing
  reference-data dir). The api container runs as **root** — `046` already persists reference-data
  writes to a `0755` root-owned bind-mount — so the container can write `scenarios.db` to a `0755`
  root dir. If a future image changes the api runtime UID
  (`docker inspect financial_scenario_api --format '{{.Config.User}}'`), set the dir owner to that UID.

## FR-001 — Version pin

- **Decision**: Set `financial_scenario_version: "0.2.2"` in `ansible/group_vars/services/vars.yml`
  (the canonical post-consolidation location). The preflight already rejects empty/`latest`.

## Restore verification approach

- **Decision**: Keep restore as a documented quickstart step (restore tar over a fresh `/app/data`,
  start stack, confirm scenarios listed; `sqlite3 <snapshot> "PRAGMA integrity_check;"` returns `ok`).
  Do **not** build an automated restore-test container (à la immich's restore compose).
- **Rationale**: immich needs a restore-test stack because Postgres restore is non-trivial; a
  single-file SQLite restore is a `cp` + integrity check. YAGNI — a codified restore drill is not
  warranted for the current risk.
