# Phase 0 Research: Euro-Office Document Server Deploy

All open questions from the spec/backlog resolved below. No `NEEDS CLARIFICATION` remain.

## D-001 — Deployment shape: which existing service to clone

- **Decision**: Clone the **`market-model`** pattern (Terraform `services/market-model/` +
  `lxc_service` module call, `roles/market_model`, `host_vars/market-model.yml`, `caddy_services`
  entry, `playbooks/market-model.yml`).
- **Rationale**: It is the closest analog — a single upstream image run via
  `community.docker.docker_compose_v2` on a dedicated LXC with **no NFS bind-mount**, published
  through the shared `caddy_services` list, with health/monitoring expressed in host_vars. Euro-Office
  has the same footprint (no host-side user data). Reusing it satisfies Code Economy (IV).
- **Alternatives**: `financial-scenario` (adds a backup role + NFS mount we don't need);
  `nextcloud` (multi-container stack with MariaDB/Redis — heavier than needed). Rejected.

## D-002 — Pinned image tag

- **Decision**: `ghcr.io/euro-office/documentserver:v9.3.2` (the real Euro-Office image), recorded as
  `eurooffice_version: "v9.3.2"` in `group_vars/services/vars.yml`. Public GHCR image — no credentials.
- **History / correction**: An earlier revision of this decision pivoted to `onlyoffice/documentserver:9.3`
  on the belief that Euro-Office publishes no Docker image. **That was a false negative.** The Euro-Office
  GHCR image does exist and is public/multi-arch (amd64+arm64); the earlier "404" came from two mistakes:
  (a) the tags are **`v`-prefixed** (`v9.3.2`, not `9.3.2`), and (b) manifest checks omitted the
  `Accept: application/vnd.oci.image.index.v1+json` header, so GHCR returned 404 for the multi-arch
  image index. Re-verified via the registry API: tags `latest`, `v9.3.1`, `v9.3.2`, `v9.3.2-rc.1` all
  return HTTP 200 with an anonymous token.
- **Rationale**: Euro-Office is the intended product (AGPL fork of ONLYOFFICE 9.3.x) and gives correct
  Euro-Office editor branding. Pin `v9.3.2` (latest stable release, 2026-06-25) for reproducibility;
  the `!= "latest"` preflight assertion enforces a pinned tag.
- **Accepted risk**: the Euro-Office README labels the Docker image "for testing and integration
  purposes" (deb/rpm packages planned, no date). Acceptable for a homelab; documents live in Nextcloud
  so the container holds only caches/config, and rollback to `onlyoffice/documentserver:9.3` is trivial.
- **Alternatives**: `latest` — rejected (unpinned drift). `onlyoffice/documentserver:9.3` — the
  production-grade upstream; kept as the documented rollback target since the connector protocol is
  identical.

## D-003 — Container config surface (env + volumes)

- **Decision**: Compose env `JWT_ENABLED=true`, `JWT_SECRET={{ eurooffice_jwt_secret }}` (vault, ≥32
  chars), `EXAMPLE_ENABLED=false`. Persist three bind-mount volumes under `/opt/eurooffice-data/`
  (per the Euro-Office Docker docs): `data` → `/var/lib/euro-office/documentserver`,
  `logs` → `/var/log/euro-office/documentserver`, `config` → `/etc/euro-office/documentserver`.
  Publish container `:80` on the LXC for the LAN callback + Caddy upstream.
- **Rationale**: The Euro-Office image uses rebranded internal paths (`/var/lib|/var/log|/etc/euro-office/documentserver`),
  documented in its Docker install guide. Bind-mounts under `/opt/eurooffice-data` keep parity with
  `market_model_data_dir` for easy inspection. Bundled Postgres/RabbitMQ/Redis run inside the image
  with defaults (no external DB needed — homelab scale). `.deb` + Apache install rejected — violates
  the repo's `docker_compose_v2`-in-LXC convention.
- **Alternatives**: Named Docker volumes — rejected for same inspection/parity reasons.

## D-004 — Reverse proxy: WebSocket + timeout

- **Decision**: One `caddy_services` entry (`host: eurooffice`, `ip`/`port` referencing new central
  vars, `enabled: true`, `user_facing: true`). Extend `service.caddy.j2` with an **optional**
  per-service transport read/write timeout (~300 s) applied only when the entry sets it; all existing
  entries keep current behavior.
- **Rationale**: Caddy `reverse_proxy` upgrades WebSockets natively (no extra directive needed) and
  the template already sends `X-Forwarded-Proto https`. The only gap versus the ONLYOFFICE proxy
  contract is the long timeout for large-document conversions/long-lived editor sockets.
- **Alternatives**: A bespoke `eurooffice.caddy` outside the `caddy_services` loop — rejected; it
  would fork the single declarative route source (the loop also reconciles/removes orphans).
- **Verify**: `curl https://eurooffice.hus-sky.no/healthcheck` → 200 over TLS; browser dev-tools show
  `wss://` established.

## D-005 — Nextcloud connector install + config

- **Decision**: Extend the existing `nextcloud` role to `occ app:install eurooffice` + `app:enable`,
  then `occ config:app:set eurooffice DocumentServerUrl --value https://eurooffice.hus-sky.no/`,
  `DocumentServerInternalUrl --value http://<eurooffice-lan-ip>/`, and the shared `jwt_secret`
  (from the same vault var, `no_log`). Configuration is idempotent (occ `config:app:set` is
  declarative; install guarded against "already installed").
- **Rationale**: The connector is Nextcloud-side config of an existing service — extend-before-add
  (IV). The role already has the `app:install`/`app:enable`/`config:app:set` idioms and the
  `nextcloud_apps_remove` list already removes `richdocumentscode`/`richdocuments` (FR-010 satisfied
  by prior work; re-assert here).
- **Alternatives**: A standalone `eurooffice_connector` role — rejected; duplicates the nextcloud
  `occ` plumbing for no separation-of-concerns benefit.
- **Verify at implement time**: confirm the app id is `eurooffice` and that it is installable from the
  Nextcloud app store on NC 34 (min-version 33 / max 35). If the app store id differs or it is not
  publishable via `occ app:install`, fall back to fetching the release tarball into the apps volume.
  Confirm the exact `config:app:set` keys against the Euro-Office Nextcloud integration doc.

## D-006 — Preflight guards

- **Decision**: Preflight asserts, mirroring `roles/market_model/tasks/preflight.yml`:
  (a) GHCR pull creds present; (b) `eurooffice_version` pinned (defined, non-empty, ≠ `latest`);
  (c) `eurooffice_jwt_secret` defined and `| length >= 32`; (d) Docker daemon running. Nextcloud
  ≥ 33 is asserted on the **nextcloud** host before the connector step (read `occ status` /
  `nextcloud_version`); PVE ~4 GB RAM headroom is confirmed by the orchestrator/preflight before the
  LXC is created.
- **Rationale**: Encodes every failure edge case (JWT mismatch/short, example-app, latest drift,
  NC < 33, RAM exhaustion) as a hard, early stop. Constitution "Test-Driven Changes" — non-destructive
  validation first.
- **Alternatives**: Rely on runtime failures — rejected (opaque, late).

## D-007 — Sizing & IP allocation

- **Decision**: LXC at **4 vCPU / 4096 MB / 15 GB**, unprivileged + nesting (via `features`), static
  IP added to `service_ips` in `lab.tfvars(.template)` and `prod.tfvars.template` plus
  `group_vars/services/vars.yml`. Proposed next free host: **`.219`** on each network (prod
  `192.168.1.219`, lab `192.168.20.219`) — confirm against the live allocation at implement time.
- **Rationale**: Matches the reference deploy sizing (backlog D-007) and the central-IP rule
  (Networking principle). `market-model` runs 2/2048/16 with no NFS and no `features_mount`; Euro-
  Office needs more RAM/CPU and **nesting** (`features` on the module call), unlike market-model.
- **Alternatives**: Smaller RAM — rejected (server wants ~4 GB; RAM exhaustion is a named edge case).

## D-008 — Health & monitoring contract

- **Decision**: `host_vars/eurooffice.yml` sets `healthcheck_url` (scheme `http`, the published port,
  path `/healthcheck`, expect 200, profile `lan`) and a `monitoring_contract` with a `liveness_targets`
  blackbox `http_2xx` probe on `http://<ip>:<port>/healthcheck` plus an `EuroOfficeDown` critical
  alert (`probe_success == 0 for 5m`) — mirroring `host_vars/market-model.yml`.
- **Rationale**: Reuses the established healthcheck + monitoring-contract mechanism; satisfies FR-008
  and SC-003/004/007 with no new monitoring machinery.

## Sources

- Euro-Office Docker install: <https://euro-office.github.io/documentation/installation/docker/>;
  GHCR `ghcr.io/euro-office/documentserver`.
- Nextcloud integration: <https://euro-office.github.io/documentation/integration/nextcloud/>.
- Connector dependency (`<nextcloud min="33" max="35"/>`, v11.0.1): `Euro-Office/eurooffice-nextcloud`
  `appinfo/info.xml` via `gh api`.
- Sizing / native stack / ONLYOFFICE 9.3.1 fork: `Rich-Hacks/eurooffice-nextcloud`.
- License impact: <https://nextcloud.com/blog/euro-office-license-compliance-and-what-open-source-means/>.
- In-repo reference: `terraform/services/market-model/`, `ansible/roles/market_model/`,
  `ansible/host_vars/market-model.yml`, `ansible/roles/reverse_proxy/templates/service.caddy.j2`,
  `ansible/roles/nextcloud/tasks/main.yml`.
