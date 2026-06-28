# Feature Specification: Market-Model Service Deploy

**Feature Branch**: `048-market-model-deploy`
**Created**: 2026-06-28
**Status**: Ready for development — hard prerequisite met: `market-model` `006` shipped its first GHCR image `ghcr.io/lightenup/market-model:0.3.0` (private, provenance + SBOM) on 2026-06-28.
**Input**: Host the `market-model` service (curated stress library + stochastic path generator,
API + MCP surface) on the homelab, in the same gated, LAN/tailnet-only fashion as
`financial-scenario` — a single GHCR-pulled image run as two roles (`api` + `mcp`) through the
existing `lxc_service` + `community.docker.docker_compose_v2` pipeline. This is the deploy side
only; the image build/release lives in the `market-model` repo
([`006-containerization-release`](../../../market-model/docs/backlog/006-containerization-release.md)).

## Summary

`market-model` is the sibling service to `personal-financial-scenarios` (PFS): PFS owns portfolio
accounting; market-model owns *market futures and their probability* (return paths per asset class
over a horizon). They never call each other — an orchestrator/agent carries path sets between them
over MCP. This item stands up market-model on its own LXC, modelled directly on the
[financial-scenario deploy](./047-financial-scenario-v2-deploy.md) (`specs/048-financial-scenario-v2-deploy/`),
but **simpler** in two deliberate ways that fall out of what market-model actually is:

1. **No GUI, no nginx, no auth gate.** market-model has no human UI — it is an API/MCP service
   consumed by the agent/orchestrator. There is no GUI nginx layer to front `/api`/`/mcp` or to hold
   an image-baked MCP shared secret (the mechanism PFS uses, `046`/`044`). So the `api` (8000) and
   `mcp` (8001) ports are **published directly** on the LAN/tailnet, and MCP is **unauthenticated**
   at the service — acceptable because the service is read/compute-only (no secrets, no destructive
   operations) and the whole host is LAN/tailnet-only (no Caddy route, no landing-page card).

2. **No backup, no NFS, no `features_mount=nfs`.** market-model's only state is a SQLite
   `path_sets` store, and that store is a **content-addressed, regenerable cache**, not original
   user data:
   - The curated library row (`curated-stress`) is **seeded from image-baked YAML** on every
     startup (`seed_curated_library`, `INSERT OR IGNORE` — idempotent).
   - Assembled sets carry **content-addressed `sha256:` ids**; re-POSTing the same inputs reproduces
     a byte-identical blob and id.
   - Generated sets are **reproducible from their recipe** — the auto-picked seed is recorded in the
     PathSet `version` string, and per market-model's own reproducibility contract (its
     Constitution IV/V) the consumer carries `id + version` downstream, which alone re-runs the draw.

   Unlike PFS's `scenarios.db` (hand-authored scenarios that exist nowhere else, hence 047's whole
   backup role + in-guest NFS + Synology share), nothing in market-model's store *originates here and
   only here*. It is a disposable cache on a host bind-mount: it survives restart/upgrade, but it is
   **not** backed up. (See D-001 for the one accepted caveat.)

Everything else mirrors financial-scenario: a single pinned GHCR image run as two commands from one
image, a private bridge network, healthchecks with `depends_on: service_healthy` ordering, the GHCR
pull credential, version pinned in `group_vars/services/vars.yml`, and a blackbox liveness
monitoring contract via `host_vars`.

## What differs vs. the financial-scenario deploy (at a glance)

| Area | financial-scenario (047) | market-model (this item) |
| --- | --- | --- |
| Images | two (`-api`, `-gui`) | **one** (`ghcr.io/lightenup/market-model`), run as two roles |
| Published port(s) | GUI only (`3000`), nginx fronts `/api`,`/docs`,`/mcp` | **`api:8000` + `mcp:8001` published directly** (no GUI/nginx) |
| MCP auth | image-baked shared-secret gate in GUI nginx | **none** (read/compute-only, tailnet-only) |
| Liveness target | GUI `/` on `3000` | **api `/healthz` on `8000`** (new endpoint, market-model `006`) |
| Stateful mount | `scenarios.db` (irreplaceable) → backed up | `path-sets.sqlite` (regenerable cache) → **not** backed up |
| Backup role / NFS | `financial_scenario_backup` + in-guest NFS + `features_mount=nfs` + Synology share | **none** |
| `features_mount` | `nfs` | **unset** (no in-guest NFS needed) |
| Reference data seed | host bind-mount, seeded-from-image on first deploy | **baked into the image** (no bind-mount, no seed task) |

## User Scenarios

### US1 — Deploy comes up healthy through the gated pipeline (P1)
As the operator, I provision the LXC (Terraform), pin the image tag, and run the playbook; the
single-image `api` + `mcp` stack comes up healthy on the new host, LAN/tailnet-only.

**Acceptance**:
1. **Given** the LXC exists and the tag is pinned, **When** I run the playbook, **Then** both the
   `api` and `mcp` containers reach `healthy` and `GET http://<host>:8000/healthz` returns 200.
2. **Given** the stack is up, **When** I `GET http://<host>:8000/`, **Then** the path-source index is
   returned (curated library + stochastic generator discovery).
3. **Given** the stack is up, **When** I inspect it, **Then** only `8000` (api) and `8001` (mcp) are
   published, nothing else; there is no GUI container and no Caddy route.

### US2 — An MCP agent generates and retrieves path sets (P1)
As an operator/agent over the tailnet, I reach the MCP service directly (port 8001), list
calibrations, generate a stochastic path set, and retrieve it by id.

**Acceptance**:
1. **Given** the stack is healthy, **When** the MCP client calls `list_calibrations` / `list_stress_scenarios`,
   **Then** both discovery surfaces return their entries (the mcp role forwards to `api:8000`).
2. **Given** a calibration id, **When** the client calls `generate_path_set` (or `assemble_path_set`),
   **Then** the api persists it to `/app/data/path-sets.sqlite` and returns its `id + version`.
3. **Given** a returned `id`, **When** the client calls `get_path_set(id)`, **Then** the byte-identical
   stored blob is returned.

### US3 — Upgrade in place; the cache is disposable (P2)
As the operator, I bump the pinned tag and redeploy; the stack comes up healthy on the new image, and
the path-set store is treated as a disposable cache (it persists across the upgrade, but losing it is
recoverable by re-request).

**Acceptance**:
1. **Given** a running stack, **When** I bump `market_model_version` and re-run the playbook, **Then**
   both containers reach `healthy` on the new tag.
2. **Given** an existing `path-sets.sqlite` on the host, **When** the upgrade runs, **Then** it is
   **never seeded-over or clobbered** — the app re-seeds the curated library idempotently
   (`INSERT OR IGNORE`) and leaves assembled/generated rows intact.
3. **Given** the host data dir is wiped (DR), **When** the stack restarts, **Then** it comes up
   healthy with the curated library re-seeded from the image; previously assembled sets are
   reproducible by re-POSTing identical inputs (content-addressed ids unchanged).

## Functional Requirements

- **FR-001 — LXC**: Add a `market-model` LXC via the `lxc_service` module, modelled on the
  `financial_scenario_lxc` block in `terraform/main.tf` (and mirrored under
  `terraform/services/market-model/` to match the per-service layout). Sizing `2c / 2048MB / 16GB`
  to start (numpy + the generator is light for one human + a few agents; revisit only under memory
  pressure — D-003). **Do NOT set `features_mount`** — no in-guest NFS is used. Allocate a free
  service IP in `service_ips["market-model"]` (operator prereq — see below).
- **FR-002 — version pin**: Add `market_model_version` to `ansible/group_vars/services/vars.yml`
  (the canonical version-pin location after `consolidate-service-versions`), pinned to a real GHCR
  tag (the first published market-model `006` release is `"0.3.0"`), never empty or `latest` (asserted
  in preflight, FR-009). Add `market_model_ip` and the published ports alongside it.
- **FR-003 — role**: Add a `market_model` Ansible role mirroring `financial_scenario`, **minus** the
  reference-data seed tasks and **minus** any backup wiring. It must: ensure the install dir and the
  host data dir exist (`{{ market_model_data_dir }}/data`, `0755`, **owned by UID `100` / GID `65534`** —
  the `006` image runs the api **non-root as `appuser` (uid 100, `adduser --system`)**, so the
  bind-mounted store dir MUST be writable by that uid or the app cannot create `path-sets.sqlite` on
  startup. This is the one place the role does **not** mirror `financial_scenario`, whose root
  container uses a `root:root` dir — see D-006. The app creates/migrates the SQLite file itself on
  startup, so the role MUST NOT seed, copy, or initialise a `.db`), authenticate to GHCR (reuse
  `ghcr_pull_username`/`ghcr_pull_token`),
  render the compose template, run `community.docker.docker_compose_v2` (`pull: always`,
  `remove_orphans: true`), and verify health (FR-007).
- **FR-004 — compose template**: A `docker-compose.yml.j2` with two services from the **one** image
  `{{ market_model_image }}:{{ market_model_version }}`:
  - `api`: default `CMD` (`uvicorn market_model.api.app:app --host 0.0.0.0 --port 8000`); publish
    `{{ market_model_api_port }}:8000`; bind-mount `{{ market_model_data_dir }}/data:/app/data`
    (the single writer); `/etc/localtime:/etc/localtime:ro`; `restart: unless-stopped`; healthcheck
    `GET http://localhost:8000/healthz` (FR-006).
  - `mcp`: `command: ["python", "-m", "market_model.mcp.server"]`; env `MCP_TRANSPORT=http`,
    `MCP_PORT=8001`, `API_BASE_URL=http://api:8000`; publish `{{ market_model_mcp_port }}:8001`;
    `depends_on: api` with `condition: service_healthy`; `restart: unless-stopped`; healthcheck =
    TCP connect to `localhost:8001` (FastMCP serves `/mcp`, not a health route — same pattern as PFS).
    The `mcp` service mounts **no** data volume (api is the sole store writer).
- **FR-005 — no DB env override**: The compose template MUST NOT set `MARKET_MODEL_DB_PATH` — the app
  default `data/path-sets.sqlite` resolves to `/app/data/path-sets.sqlite` under WORKDIR `/app`,
  which is exactly the FR-004 bind-mount. Document the override path so a future relocation is a
  one-liner.
- **FR-006 — liveness endpoint**: Use api `GET /healthz` (200) as the healthcheck/liveness target
  (a real endpoint added in market-model `006`, unlike PFS which probes `/docs`). The Ansible health
  verification (FR-007) hits `http://127.0.0.1:{{ market_model_api_port }}/healthz`.
- **FR-007 — health verification**: After compose up, `wait_for` the api port, then `uri` GET
  `/healthz` expecting 200 with retries (mirror `financial_scenario` role's wait/verify tasks).
- **FR-008 — monitoring contract**: Add `ansible/host_vars/market-model.yml` with a
  `monitoring_contract` (blackbox liveness only, mirroring `financial-scenario.yml`): a
  `liveness_targets` entry probing `http://<market-model-ip>:8000/healthz` (`module: http_2xx`) and a
  `MarketModelDown` alert (`probe_success == 0 for 5m`, critical). `healthcheck_url` → `{scheme: http,
  port: 8000, path: /healthz}`, `healthcheck_profile: lan`, `expect 200`. Add a
  `scripts/healthcheck/market-model.sh` wrapper mirroring `financial-scenario.sh`.
- **FR-009 — preflight**: Mirror `financial_scenario` preflight: assert the GHCR pull credentials are
  defined, assert `market_model_version` is a pinned non-`latest` tag, and check the Docker daemon.
  **No** MCP-secret assertion (there is no gate). **No** NFS/backup assertions.
- **FR-010 — playbook + wiring**: Add `ansible/playbooks/market-model.yml` (base + `geerlingguy.docker`
  + `market_model` roles, mirroring `financial-scenario.yml` minus the `_backup` role) and wire the
  host into the generated inventory (`ansible/inventories/generated/hosts.yml` via the Terraform
  `ansible_inventory` output) and `site.yml`/`services.yml` as appropriate.
- **FR-011 — posture unchanged**: LAN/tailnet-only. No Caddy/reverse-proxy route, no landing-page
  card, no public exposure. The two published ports are reachable only on the LAN/tailnet.

## Decisions (Decision Log)

- **D-001 — store is a disposable cache; no backup** *(operator-confirmed 2026-06-28)*. The
  `path_sets` SQLite store holds only regenerable content: the seeded curated library (from baked-in
  image YAML), content-addressed `sha256:` assemblies (reproducible from baked-in data + cheap
  request params), and generated draws (reproducible from the recipe encoded in the `version`
  string, which the consumer carries downstream per market-model's reproducibility contract). Nothing
  originates here-and-only-here the way PFS's hand-authored `scenarios.db` does. **Accepted caveat**:
  for an *auto-seeded* generated set, the store is the sole holder of the seed/recipe in the gap
  between generation and the consumer durably recording `id + version`; there is no
  regenerate-from-version endpoint, so a DB wipe in that gap loses that specific draw's recipe. Judged
  acceptable — the architecture's intent is that the consumer (orchestrator/PFS) owns the identity, and
  the bind-mount already survives restart/upgrade. **Drops** the entire 047 backup apparatus: no
  `market_model_backup` role, no in-guest NFS mount, no `features_mount=nfs`, no Synology share.
- **D-002 — MCP published directly, no auth gate** *(recommended default; objectable)*. There is no
  GUI/nginx layer to host a shared-secret gate, and adding one for a UI-less, secret-less,
  read/compute-only service is disproportionate. Publish `mcp:8001` (and `api:8000`) directly on the
  LAN/tailnet. Posture relies on the host being tailnet-only (no Caddy route). Matches market-model
  `006`'s own "publish api+mcp" decision. If a gate is later wanted, it is a separate item (reverse
  proxy in front, or an app-level token in market-model).
- **D-003 — LXC sizing**: `2c / 2048MB / 16GB` to start (same as financial-scenario). The generator
  uses numpy but workload is light (one human + a few agents). Revisit only under observed memory
  pressure during large `n_paths` generation.
- **D-004 — liveness = `/healthz`**: market-model `006` adds a dedicated `GET /healthz`; use it
  rather than `/docs` (cheaper, survives a hardened ENV that disables docs).
- **D-005 — one image, two roles**: Single `ghcr.io/lightenup/market-model` image; `api` runs the
  default uvicorn `CMD`, `mcp` overrides `command` to `python -m market_model.mcp.server` with the
  http-transport env. No second image (no GUI).
- **D-006 — non-root container; host data dir owned by uid 100** *(drift caught against the shipped
  `006` image, 2026-06-28)*. The `0.3.0` image runs the api **non-root** as `appuser`
  (`uid=100`, `gid=65534`/`nogroup`, from `adduser --system`), with `/app/data` owned by that uid.
  Unlike PFS (whose container runs as root and uses a `root:root` data dir), the market-model host
  bind-mount dir MUST be `chown`ed to **`100:65534`** so the non-root process can write
  `path-sets.sqlite` — a `root:root 0755` dir would be read-only to it and the service would fail to
  persist. **Coupling caveat / recommended follow-up in market-model**: uid 100 is auto-assigned by
  `adduser --system` and could drift if a future base image adds system users; market-model `006`
  should pin an explicit, documented UID in its Dockerfile (e.g. `--uid 1000`) so this deploy can
  depend on a stable contract rather than the current implicit `100`.

## Dependencies

- **market-model `006` (containerization & GHCR release)** — **hard prerequisite, ✅ shipped
  2026-06-28**: this deploy pins the image tag that `006` publishes
  (`ghcr.io/lightenup/market-model`, private — first release `0.3.0`, with provenance + SBOM). `006`
  also added the `GET /healthz` and `GET /` endpoints and the env-driven MCP entrypoint
  (`MCP_TRANSPORT`/`MCP_PORT`/`API_BASE_URL`, bind `0.0.0.0`) this template relies on — all verified
  in the published image. This item is now unblocked.
- **[consolidate-service-versions](./consolidate-service-versions.md)** — ✅ delivered; the
  `market_model_version` pin lives in `group_vars/services/vars.yml` alongside the other services.
- **[047-financial-scenario-v2-deploy](./047-financial-scenario-v2-deploy.md)** — the reference
  pattern this deploy is modelled on (minus GUI/backup/NFS).
- **GHCR pull credential** — reuse the existing `ghcr_pull_username` / `ghcr_pull_token` vault vars
  (the `lightenup` namespace token already pulls `financial-scenario-*`; it must also have access to
  `market-model`).

## Operator pre-requisites (one-time, outside the gated pipeline)

- **Allocate a service IP** for `market-model` in the `service_ips` map / network plan (a free
  address on the services bridge, e.g. the next free `192.168.1.x`). There is **no** NAS/NFS prereq
  (D-001) — unlike financial-scenario, no Synology share to create.
- **Confirm the GHCR pull token** has read access to `ghcr.io/lightenup/market-model` (same token
  used for `financial-scenario-*`).

## Out of Scope

- The image build/release — done in the `market-model` repo (`006`); this only pulls and runs a
  pinned tag.
- App source changes (path generation, persistence, the `/healthz` + `/` + MCP-env wiring) — all in
  market-model `006`.
- Backups, in-guest NFS, `features_mount=nfs`, Synology share — explicitly excluded (D-001).
- A GUI, an MCP auth gate, a Caddy/public route, or a landing-page card — excluded (LAN/tailnet-only,
  UI-less service).
- App-level Prometheus metrics — blackbox liveness only (parity with financial-scenario).

## Verification (acceptance)

1. **Deploy**: run the playbook; both containers reach `healthy`; `GET :8000/healthz` → 200 and
   `GET :8000/` returns the path-source index.
2. **Topology**: `docker inspect market_model_mcp` shows `API_BASE_URL=http://api:8000`,
   `MCP_TRANSPORT=http`, no data mount, and `depends_on` api healthy; `market_model_api` has the
   `/app/data` bind-mount and no others beyond localtime. The host `{{ market_model_data_dir }}/data`
   dir is owned by `100:65534` and the api (running as uid 100) successfully writes
   `path-sets.sqlite` into it (D-006 — a `root:root` dir would fail here).
3. **MCP round-trip**: over the tailnet, `generate_path_set` then `get_path_set(id)` returns the
   byte-identical blob; the row is present under `{{ market_model_data_dir }}/data/path-sets.sqlite`.
4. **Upgrade safety**: bump `market_model_version`, re-run — both containers healthy on the new tag;
   existing assembled/generated rows intact, curated library re-seeded idempotently (not clobbered).
5. **Disposability**: wipe the host data dir, restart — stack comes up healthy, curated library
   re-seeded from image; a previously assembled set is reproducible by re-POSTing identical inputs
   (same `sha256:` id).
6. **Posture**: only `8000` and `8001` are published; no GUI container, no Caddy route, no
   landing-page card; liveness probe green in the monitoring contract.
</content>
