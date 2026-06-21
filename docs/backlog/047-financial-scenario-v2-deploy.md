# Feature Specification: Financial-Scenario v2 Deploy (Stateful)

**Feature Branch**: `047-financial-scenario-v2-deploy`
**Created**: 2026-06-20
**Updated**: 2026-06-21 — PFS `0.2.2` shipped (PFS `046`+`047`); open questions resolved, decisions locked.
**Status**: Ready for planning — detailed spec (was: high-level draft)
**Input**: Host the next version of the `personal-financial-scenarios` app (released as **`v0.2.2`**),
which introduces (1) a single-engine topology where the MCP server is a thin HTTP client of the api
(PFS `046`) and (2) a persisted scenario store backed by SQLite on the api service (PFS `047`).
Update the existing homelab deploy to match — without regressing the LAN/tailnet-only posture or the
gated pipeline.

## Summary

The original deploy ([046-financial-scenario-deploy](./046-financial-scenario-deploy.md)) hosts PFS
`0.1.0` as a **stateless** 3-container stack (`api`, `mcp`, `gui`), persisting only the
reference-data bind-mount. PFS `v0.2.2` changes two things the homelab deploy must track:

1. **MCP becomes a stateless HTTP client of the api** (PFS `046`). The `mcp` container no longer runs
   its own engine or loads reference data — it forwards all traffic to `api:8000` via the
   `API_BASE_URL` env var (`services/api/src/mcp_server/client.py:21`). Deployment effect: the `mcp`
   container's `reference_data` bind-mount is **removed**, it gains `API_BASE_URL: http://api:8000`,
   and it gains `depends_on: api` (service_healthy) so it never starts before its authority.
2. **The api gains a persisted SQLite scenario store** (PFS `047`). For the first time the backend
   holds **user-generated state** — saved scenarios authored from the GUI (`source: gui`) or by an
   MCP agent (`source: mcp`). The api reads/writes `SCENARIOS_DB_PATH` (default
   `/app/data/scenarios.db`, see `services/api/src/api/deps.py:5`). Deployment effect: a **new
   persistent host bind-mount** at `/app/data` on the `api` service that survives container
   recreation and image upgrades — and, unlike reference data (which originates in the app repo),
   this data exists **only** on the host, so it needs a real backup story.

Everything else from `046` is unchanged: a single GHCR-pulled image pair, GUI-only published port
with nginx fronting `/api`, `/docs`, `/mcp`, the GHCR pull credential, the LAN/tailnet-only posture
(no Caddy route, no landing-page card), the image-baked MCP shared-secret gate, and the blackbox
liveness monitoring contract.

## What changes vs. 046 (at a glance)

| Area | 046 (current) | 047 (this item) |
| --- | --- | --- |
| Image tag | `financial_scenario_version: 0.1.0` | bump to `0.2.2` (PFS `046`+`047`) |
| `mcp` container | own engine, reference-data bind-mount | stateless HTTP client; **no** reference-data mount; `API_BASE_URL: http://api:8000`; `depends_on: api` (service_healthy) |
| `api` state | reference-data bind-mount only | reference-data **+ new `scenarios.db` bind-mount** at `/app/data` |
| Backups | out of scope (data originates in repo) | **in scope** — `scenarios.db` is host-only user data (new backup role + timer → Synology NFS) |
| Topology | two independent engine copies | single engine authority on `api` |

## User Scenarios

### US1 — Upgrade in place without losing data (P1)
As the operator, I bump the pinned tag to `0.2.2` and redeploy through the existing gated pipeline;
the stack comes up healthy on the new single-engine topology, and **previously saved scenarios and
reference-data edits survive** the image re-pull.

**Acceptance**:
1. **Given** a running `0.1.0` stack, **When** I set `financial_scenario_version: "0.2.2"` and run the
   playbook, **Then** all three containers reach `healthy` and the GUI serves 200 on port 3000.
2. **Given** reference-data edits exist on the host, **When** the upgrade runs, **Then** the
   reference-data bind-mount is preserved unchanged (no re-seed over existing data).
3. **Given** an existing `scenarios.db` on the host, **When** the upgrade runs, **Then** it is
   **never clobbered or re-initialised** — saved scenarios remain listed and openable.

### US2 — Agent-authored scenarios appear in the GUI (P1)
As an operator using an MCP client over the tailnet (through the nginx `/mcp` gate), I save a scenario
via MCP; it is persisted on the `api` service and is then selectable in the GUI for comparison.

**Acceptance**:
1. **Given** the stack is healthy, **When** I `save_scenario` via the gated `/mcp` endpoint, **Then**
   the api persists it with `source: mcp` to `/app/data/scenarios.db`.
2. **Given** an agent-authored scenario exists, **When** I open the GUI comparison list, **Then** it
   appears, badged as agent-authored, and opens with freshly computed results.

### US3 — Saved scenarios are backed up (P2)
As the operator, `scenarios.db` is included in the homelab backup regime (à la
`nextcloud_backup`/`immich_backup`) so a lost LXC does not lose hand-built scenarios.

**Acceptance**:
1. **Given** the backup timer is installed, **When** it fires, **Then** a **consistent** (WAL-safe)
   snapshot of `scenarios.db` is written to the Synology NFS backup share.
2. **Given** several daily/weekly/monthly snapshots exist, **When** the prune step runs, **Then**
   GFS retention is applied (same policy shape as `nextcloud_backup`).
3. **Given** a snapshot exists, **When** the operator restores it over a fresh `/app/data` and starts
   the stack, **Then** the restored scenarios are listed and openable.

## Functional Requirements

- **FR-001**: Pin the PFS image tag to `0.2.2` via `financial_scenario_version` in
  `ansible/group_vars/services/vars.yml` (the canonical location after
  [consolidate-service-versions](./consolidate-service-versions.md), now **delivered**).
- **FR-002**: Add a persistent **host bind-mount** for the api scenario store, mounting
  `{{ financial_scenario_data_dir }}/scenarios` → `/app/data` on the **`api` service only**. This
  matches the durable-data convention used by immich (`{{ immich_data_dir }}/postgres:/var/lib/...`)
  rather than a docker named volume. The `mcp` service MUST NOT mount it (api is the single writer).
- **FR-003**: The compose template MUST NOT set `SCENARIOS_DB_PATH` — the app default
  `/app/data/scenarios.db` is correct given the mount point in FR-002. (Document the override path so
  a future relocation is a one-liner.)
- **FR-004**: Reconfigure the `mcp` service: **remove** its `reference_data` bind-mount, **add**
  `API_BASE_URL: http://api:8000`, and **add** `depends_on: api` with `condition: service_healthy`.
  Keep `MCP_TRANSPORT: http` and `MCP_PORT: 8001` (required for the server to bind the port).
- **FR-005**: Preserve first-deploy-vs-upgrade safety for **both** stateful mounts:
  - Reference data: keep the existing seed-when-empty logic (seed from image on first deploy only).
  - `scenarios.db`: ensure the host `scenarios` dir exists with correct ownership/mode, but **never**
    seed, copy, or initialise a DB file — the app creates and migrates it idempotently on startup
    (`CREATE TABLE IF NOT EXISTS`, WAL, run once in lifespan). The role MUST NOT clobber an existing
    DB on upgrade.
- **FR-006**: Mount the backup destination **in-guest** (jellyfin pattern, Spec `023`: no host-path
  bind mounts in Terraform), so the PVE host needs **no** `/etc/fstab` entry and no `pct set` bind
  mount. The financial-scenario LXC mounts
  `192.168.1.109:/volume1/homelab_financial_scenario` → `/mnt/financial-scenario/backups` with
  `rw,nofail,_netdev,x-systemd.automount`. The existing `shared_nfs_mount` role is hardcoded
  **read-only** (asserts `SD-003` RO) and cannot be reused verbatim; either parameterise it for rw or
  perform the mount inside the backup role.
- **FR-007**: Enable in-guest NFS on the LXC: add `features_mount = "nfs"` to the `lxc_service`
  module call in `terraform/services/financial-scenario/main.tf` (copy from
  `terraform/services/jellyfin/main.tf:27`). Required for an unprivileged LXC to mount NFS in-guest;
  apply is image-independent (sets only an LXC feature flag).
- **FR-008**: Add a `financial_scenario_backup` role + systemd service/timer mirroring
  `nextcloud_backup`/`immich_backup`:
  - Take a **consistent** snapshot of the WAL-mode SQLite DB — use the online-backup path, not a raw
    `cp` (a raw copy under concurrent writes can capture a torn DB). Acceptable mechanisms: run
    SQLite's online backup / `VACUUM INTO` from inside the api container
    (`docker exec financial_scenario_api python -c "import sqlite3; ..."`), or quiesce equivalently.
  - Archive the snapshot (+ a copy of the rendered `docker-compose.yml` for reference) to the
    in-guest NFS mount from FR-006 (`/mnt/financial-scenario/backups`).
  - Apply GFS retention (daily/weekly/monthly) with the same policy shape as `nextcloud_backup`
    (`*_retention_days/weeks/months`, `*_schedule`).
- **FR-009**: No change to the exposure posture, the GHCR pull, the GUI-only port model, the
  image-baked MCP shared-secret gate, or the monitoring contract from `046`.

## Resolved decisions (Decision Log)

- **D-001 (was Q-001) — store path**: The api reads `SCENARIOS_DB_PATH`, default
  `/app/data/scenarios.db` (`services/api/src/api/deps.py:5`; migration run in `app.py:32`). Mount
  the host dir at `/app/data`; do **not** set the env var (default is correct). *Resolved.*
- **D-002 (was Q-002) — backup mechanism**: Full `financial_scenario_backup` role + systemd timer in
  this release (operator-chosen). DB is WAL-mode → MUST use a **consistent online backup**, not raw
  `cp`. Destination = **Synology NFS** (operator-chosen), GFS retention. *Resolved.*
- **D-003 (was Q-003) — LXC sizing**: Single-engine topology means `api` now also serves all MCP
  traffic, but workload is light (one human, a few agents). Expect 2c/2048MB still fits; confirm
  headroom during planning, bump only if the api shows memory pressure under concurrent saves.
- **D-004 (was Q-004) — MCP secret**: Still **image-baked** in the GUI nginx gate
  (`services/gui/nginx.conf`, literal `mcp-local-secret`); PFS `046`/`047` did **not** make it
  env-configurable. Carry forward `046`'s posture — no per-deploy MCP token here. Making it
  vault-configurable remains a separate PFS change.
- **D-005 — storage mechanism (the api `scenarios.db` mount, *inside* the LXC)**: **Host bind-mount**
  on the LXC filesystem (`{{ financial_scenario_data_dir }}/scenarios:/app/data`), not a docker named
  volume — matches the immich/jellyfin durable-data convention and makes the DB directly reachable by
  the backup role. (The app's own `docker-compose.yml` uses a named `scenarios-data` volume; the
  homelab deviates deliberately for backup ergonomics and repo consistency.)
- **D-006 — backup-destination mount pattern (NAS → LXC)**: **In-guest NFS mount** (jellyfin
  pattern, `features_mount = "nfs"` + an Ansible mount), **not** the immich/nextcloud host-mount +
  bind pattern. Rationale: keeps the whole deploy self-contained in Terraform + Ansible with **no PVE
  `/etc/fstab` edit and no `pct set` bind-mount** (the host-mount path has a manual seam — e.g.
  `homelab_nextcloud` is in PVE fstab but absent from the `proxmox_mounts` role). Backups still land
  on the same NAS (`192.168.1.109:/volume1/homelab_financial_scenario`); the PVE host simply does not
  need to see them, and DR can mount the share independently. Conforms to Spec `023`.

## Operator pre-requisite (one-time, outside the codified pipeline)

Exactly one step has no repo automation — creating the NFS share on the Synology NAS (DSM UI). The
NAS is `192.168.1.109`, exports under `/volume1/<name>`. Everything downstream (the in-guest mount,
the LXC feature flag, the backup role) is codified in FR-006/FR-007/FR-008 and runs through the gated
pipeline — **not** manual prep.

- **Synology NAS — create the NFS share** ✅ *done by operator (2026-06-21)*:
  - Shared folder `homelab_financial_scenario` → export `/volume1/homelab_financial_scenario`.
  - NFS permission rule for the LXC IP `192.168.1.217/32` (prod) and lab `192.168.20.218/32`, **rw**,
    same squash/mapping as the existing `homelab_immich` / `homelab_nextcloud` shares.
  - Verify from the LXC once it exists: `showmount -e 192.168.1.109`.

**No PVE host mount is required** (D-006): unlike the `homelab_immich` / `homelab_nextcloud` entries
in the PVE `/etc/fstab`, this service uses the in-guest NFS pattern — the financial-scenario LXC
mounts the share directly (FR-006), so there is nothing to add to the PVE host fstab or `pct set`.

## Dependencies

- **PFS `046` + `047`, shipped as `v0.2.2`** — hard prerequisite; the image tag this deploy pins. ✅ done.
- **[consolidate-service-versions](./consolidate-service-versions.md)** — ✅ delivered
  (`specs/047-consolidate-service-versions/`); `financial_scenario_version` already lives in
  `group_vars/services/vars.yml`.
- **[046-financial-scenario-deploy](./046-financial-scenario-deploy.md)** — the baseline this extends.
- **Synology NFS share** `homelab_financial_scenario` (operator pre-req above, ✅ done) — mounted
  in-guest by the backup role (FR-006), modelled on `shared_nfs_mount` (jellyfin) for the mount and
  `nextcloud_backup` for the snapshot/retention/timer.

## Out of Scope (carried from 046 unless noted)

- Public exposure / Caddy route / landing-page card — still excluded (LAN/tailnet-only).
- App source changes — done in the PFS repo (`046`/`047`); this only pulls and runs pinned tags.
- App-level Prometheus metrics — still blackbox liveness only.
- LLM-backed catalog ingestion — `EXTRACTION_BASE_URL` stays unset/empty.
- Migrating legacy browser-local scenarios — explicitly out of scope in PFS `047`; nothing to do here.
- Making the MCP shared secret vault-configurable — needs a PFS change (see D-004).
- **Backups are now IN scope** (the one deliberate reversal from 046's "out of scope").

## Verification (acceptance)

1. **Upgrade safety**: deploy `0.1.0`, save a scenario, bump to `0.2.2`, re-run the playbook —
   the previously saved scenario is still listed and openable; reference-data edits intact.
2. **Topology**: `docker inspect financial_scenario_mcp` shows no reference-data mount and
   `API_BASE_URL=http://api:8000`; mcp starts only after api is healthy.
3. **Persistence**: `scenarios.db` exists under `{{ financial_scenario_data_dir }}/scenarios` on the
   host; `docker compose down && up` preserves saved scenarios.
4. **Backup**: trigger the timer; a consistent snapshot lands on the NFS share; restoring it over a
   fresh `/app/data` reproduces the saved scenarios. `sqlite3 <snapshot> "PRAGMA integrity_check;"`
   returns `ok`.
5. **Posture unchanged**: only port 3000 is published; `/mcp` still requires the shared secret;
   blackbox liveness probe stays green.
