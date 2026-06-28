# Phase 0 Research: Market-Model Service Deploy

All open questions from the spec are resolved by the originating backlog
(`docs/backlog/048-market-model-deploy.md`) and the shipped market-model `006` image. No
`NEEDS CLARIFICATION` markers remain.

## D-001 — Path-set store is a disposable cache; no backup

- **Decision**: Provision **no** backup apparatus — no `market_model_backup` role, no in-guest NFS,
  no `features_mount=nfs`, no Synology share. The host bind-mount survives restart/upgrade but is not
  snapshotted.
- **Rationale**: Everything in `path-sets.sqlite` is regenerable: the curated library re-seeds from
  image-baked YAML idempotently (`INSERT OR IGNORE`); assembled sets carry content-addressed
  `sha256:` ids (identical inputs → identical blob); generated sets are reproducible from the recipe
  encoded in the `version` string, which the consumer carries downstream per market-model's
  reproducibility contract. Nothing originates here-and-only-here the way PFS's hand-authored
  `scenarios.db` does (which is why 048 needed a backup role + NFS).
- **Accepted caveat**: For an auto-seeded generated set, the store is briefly the sole holder of the
  seed/recipe between generation and the consumer durably recording `id + version`; there is no
  regenerate-from-version endpoint, so a wipe in that gap loses that draw's recipe. Judged acceptable
  — the consumer owns identity by design.
- **Alternatives considered**: Mirror 048's backup role + NFS (rejected: disproportionate for a
  regenerable cache; adds NFS feature flag, a Synology share prereq, a backup script, and a systemd
  timer with no recoverable data behind them).

## D-002 — MCP published directly, no auth gate

- **Decision**: Publish `api:8000` **and** `mcp:8001` directly on the LAN/tailnet; MCP is
  unauthenticated at the service.
- **Rationale**: PFS's MCP gate lives in a GUI nginx layer with an image-baked shared secret
  (PFS `044`/`046`). market-model has no GUI/nginx layer to host such a gate, and the service is
  UI-less, secret-less, and read/compute-only. Posture relies on the host being tailnet-only (no
  Caddy route). Matches market-model `006`'s own "publish api+mcp" decision.
- **Alternatives considered**: Add an nginx front + baked secret (rejected: builds a whole GUI image
  contract for a service that has no UI); app-level token (rejected: a market-model app change,
  out of scope — a separate item if ever wanted).

## D-003 — LXC sizing 2c / 2048MB / 16GB

- **Decision**: Same sizing as financial-scenario.
- **Rationale**: The stochastic generator uses numpy but the workload is light (one human + a few
  agents). Revisit only under observed memory pressure during large `n_paths` generation.
- **Alternatives considered**: Larger memory up front (rejected: YAGNI; no evidence of pressure).

## D-004 — Liveness target = api `GET /healthz`

- **Decision**: Use `/healthz` (200) as the compose healthcheck and the Ansible verify target.
- **Rationale**: market-model `006` ships a dedicated `GET /healthz` — cheaper than PFS's `/docs`
  probe and survives a hardened ENV that disables docs.
- **Alternatives considered**: Probe `/` (rejected: heavier; `/healthz` is purpose-built).

## D-005 — One image, two roles

- **Decision**: Single `ghcr.io/lightenup/market-model` image. `api` runs the default uvicorn `CMD`;
  `mcp` overrides `command` to `python -m market_model.mcp.server` with `MCP_TRANSPORT=http`,
  `MCP_PORT=8001`, `API_BASE_URL=http://api:8000`.
- **Rationale**: market-model ships one image (unlike PFS's `-api` + `-gui`); the two roles differ
  only by entrypoint/env. `mcp` mounts no data volume — `api` is the sole store writer.
- **Alternatives considered**: A second image (rejected: there is none; no GUI).

## D-006 — Non-root container; host data dir owned by uid 100

- **Decision**: `chown` the host data dir to **`100:65534`** (mode `0755`).
- **Rationale**: The `0.3.0` image runs the api non-root as `appuser` (`uid=100`, `gid=65534`, from
  `adduser --system`), with `/app/data` owned by that uid. A `root:root` dir (as financial-scenario
  uses, whose container runs as root) would be read-only to the process and the app would fail to
  create `path-sets.sqlite`. This is the **one** place the role does not mirror `financial_scenario`.
- **Coupling caveat / follow-up**: uid 100 is auto-assigned by `adduser --system` and could drift if
  a future base image adds system users; market-model `006` should pin an explicit documented UID
  (e.g. `--uid 1000`) so this deploy can depend on a stable contract. Tracked as a recommended
  upstream follow-up, not a blocker.
- **Alternatives considered**: Run the container as root / `user: "0:0"` override (rejected:
  defeats the image's non-root hardening); `chmod 0777` (rejected: looser than necessary).

## D-007 — No `MARKET_MODEL_DB_PATH` override

- **Decision**: Do not set `MARKET_MODEL_DB_PATH`; rely on the app default `data/path-sets.sqlite`
  resolving to `/app/data/path-sets.sqlite` under WORKDIR `/app`, which is exactly the bind-mount.
- **Rationale**: Fewer moving parts; the default already lands in the mounted dir. Document the
  override so a future relocation is a one-liner (mirrors 048's `SCENARIOS_DB_PATH` note).

## Service IP allocation (operator prereq)

- **Decision**: Allocate a free services-bridge address. Proposed: prod `192.168.1.218/24` (next
  free after financial-scenario `.217`), lab `192.168.20.219/24` (next free after financial-scenario
  lab `.218`). Operator confirms before apply.
- **Rationale**: No NAS/NFS prereq exists for this service (D-001) — IP allocation is the only
  one-time operator step beyond confirming the GHCR token reaches `ghcr.io/lightenup/market-model`.

## Reference pattern parity (what is reused vs. dropped vs. 048)

| Reused unchanged | Dropped vs. 048 | Changed vs. 048 |
| --- | --- | --- |
| `lxc_service` module, GHCR login, `docker_compose_v2` (`pull: always`, `remove_orphans`), `wait_for` + `uri` verify, blackbox monitoring contract, preflight (creds/pinned-tag/docker) | backup role, in-guest NFS, `features_mount=nfs`, Synology share, reference-data seed tasks, GUI image/role | one image as two roles (no `-gui`); publish `api:8000` + `mcp:8001` (no nginx front); data dir owner `100:65534` (not `root:root`); liveness `/healthz` (not `/docs`) |
