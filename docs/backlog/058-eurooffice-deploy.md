# Feature Specification: Euro-Office Document Server Deploy

**Feature Branch**: `058-eurooffice-deploy`
**Created**: 2026-07-08
**Status**: Backlog — **blocked on [`057-nextcloud-upgrade-33-34`](./057-nextcloud-upgrade-33-34.md)**
(connector needs NC 33–35; instance is on 32).
**Input**: Deploy the Euro-Office document server (AGPLv3 sovereign fork of ONLYOFFICE
DocumentServer) on its own gated LXC running the official GHCR image via docker compose, front it at
`eurooffice.hus-sky.no` through Caddy, and wire it into Nextcloud via the `eurooffice` connector so
users get in-browser collaborative editing with strong MS-Office fidelity — replacing the flaky
built-in CODE.

## Summary

Give Nextcloud a real online office suite. Euro-Office is the **AGPLv3, EU-sovereign fork of
ONLYOFFICE DocumentServer** (pinned upstream at 9.3.1), so it inherits ONLYOFFICE's OOXML-native
engine (best-in-class `.docx/.xlsx/.pptx` fidelity) with no trademark or commercial-edition
restrictions. It ships a first-class multi-arch Docker image on GHCR, so it deploys as a
`docker_compose_v2` service on a dedicated `lxc_service` LXC — the same shape as `financial-scenario`
and `market-model` — fronted by the existing Caddy reverse proxy and connected to Nextcloud via the
`eurooffice` connector app (v11.0.1).

This replaces the built-in CODE (`richdocumentscode`) removed in `057`. The document server is
compute-heavy (parses/renders untrusted documents) but holds no original user data (documents live
in Nextcloud); its persistent state is caches + config, so no user-data backup is in scope beyond the
config/JWT secret.

**Hard dependency**: the `eurooffice` connector requires Nextcloud **33–35**; this item MUST NOT
start until `057` lands the instance on 34.

## User Scenarios & Testing

### User Story 1 - Editing a document from Nextcloud works end-to-end (P1)

A user opens a `.docx` in Nextcloud Files; it opens in the Euro-Office in-browser editor, edits save
back to Nextcloud, and a second user co-edits live.

**Acceptance**:
1. **Given** the connector points at the document server, **When** a user opens/creates a
   `.docx/.xlsx/.pptx`, **Then** the editor loads and edits persist back to Nextcloud storage.
2. **Given** two logged-in users, **When** both open the same document, **Then** edits appear
   collaboratively.
3. **Given** the admin connector test, **When** it runs, **Then** the conversion/round-trip check
   reports success.

### User Story 2 - Deploy comes up healthy through the gated pipeline (P1)

**Acceptance**:
1. **Given** the pinned image tag, **When** the apply runs, **Then** the container is `Up (healthy)`
   and the document-server health endpoint returns 200.
2. **Given** a re-run, **When** the apply repeats, **Then** it is idempotent (no unintended
   recreation) and the version stays pinned.

### User Story 3 - Reachable and secured at eurooffice.hus-sky.no (P2)

**Acceptance**:
1. **Given** a `caddy_services` entry for eurooffice, **When** the reverse proxy applies, **Then**
   `eurooffice.hus-sky.no` serves over TLS and upgrades WebSocket connections.
2. **Given** the connector config, **When** Nextcloud validates it, **Then** the public
   `DocumentServerUrl` and the LAN `DocumentServerInternalUrl` callback both succeed with a shared
   JWT.

### Edge Cases

- **JWT mismatch** between NC and the server → editor fails to load; both sides share an identical
  ≥32-char vault secret; mismatch is a clear failure.
- **`EXAMPLE_ENABLED=true` left on** → unauthenticated example app exposed; MUST be off in prod.
- **WebSocket not upgraded** by the proxy → editor spins forever; the route MUST pass WS upgrade
  (Caddy `reverse_proxy` does this; a health assertion should cover it).
- **NC below 33** → connector install refused; preflight MUST verify NC ≥ 33.
- **Host RAM exhaustion** — server wants ~4 GB; preflight MUST confirm PVE headroom.
- **`latest` tag drift** → MUST pin a specific version tag (e.g. `:9.3.1`).

## Requirements

- **FR-001**: Run from a **pinned** GHCR tag (`ghcr.io/euro-office/documentserver:<pinned>`), never
  `latest`, via `docker_compose_v2` on a dedicated `lxc_service` LXC (nesting enabled).
- **FR-002**: Size the LXC for the server (baseline **4 vCPU / 4 GB RAM / 15 GB disk**; confirm PVE
  headroom in preflight).
- **FR-003**: JWT enabled (`JWT_ENABLED=true`) with a shared ≥32-char secret from the Ansible vault,
  identical on server and connector.
- **FR-004**: Example app disabled in production (`EXAMPLE_ENABLED=false`).
- **FR-005**: Persistent volumes for data/logs/config so restart/upgrade preserves config/caches;
  documents stay in Nextcloud (no user-data backup scope).
- **FR-006**: A `caddy_services` entry publishes `eurooffice.hus-sky.no` → server upstream, over
  TLS, with WebSocket upgrade and an adequate proxy timeout.
- **FR-007**: Install/enable the `eurooffice` connector (v11.0.1) and configure it idempotently via
  `occ`: public `DocumentServerUrl` (`https://eurooffice.hus-sky.no/`), LAN
  `DocumentServerInternalUrl` (`http://<lxc-ip>/`), shared `jwt_secret`.
- **FR-008**: Run through the gated LAB→PROD pipeline with a post-apply healthcheck on the
  document-server health endpoint; expose a blackbox liveness monitoring contract.
- **FR-009**: Preflight-verify Nextcloud ≥ 33; MUST NOT proceed otherwise.
- **FR-010**: `richdocumentscode`/`richdocuments` already removed (in `057`); MUST NOT leave two
  office connectors enabled.
- **FR-011**: Record the image tag in the central version-pin location.

## Success Criteria

- **SC-001**: Opening/creating a `.docx/.xlsx/.pptx` from Nextcloud Files loads the Euro-Office
  editor and edits persist back.
- **SC-002**: Two users co-edit live; the admin connector test reports success.
- **SC-003**: Pipeline deploys idempotently; container `Up (healthy)`; health endpoint 200;
  post-apply healthcheck passes.
- **SC-004**: `https://eurooffice.hus-sky.no/healthcheck` → 200 over TLS; editor WebSocket connects.
- **SC-005**: Image pinned (not `latest`); `EXAMPLE_ENABLED=false`; JWT enabled with a vault
  ≥32-char secret matching both sides.
- **SC-006**: Only `eurooffice` is enabled as the office connector; built-in CODE is gone.
- **SC-007**: Service appears in monitoring (blackbox liveness).

## Research & decisions

**What it is**: the community fork of **ONLYOFFICE DocumentServer** (upstream **9.3.1 build 37**) —
same OOXML-native engine (top `.docx/.xlsx/.pptx` fidelity) minus ONLYOFFICE's trademark /
commercial-edition restrictions (no CE connection-count cap). Bundles nginx → docservice → Postgres
+ RabbitMQ + Redis.

**License**: **AGPLv3**, free of charge, self-hostable, no paid edition (support subscriptions don't
exist yet). Practical impact for private homelab self-host: **none** — source-disclosure only
triggers on *modifying* the server and serving it to third parties over a network.

**Docker image**: **`ghcr.io/euro-office/documentserver`**, multi-arch (amd64 + arm64),
version-tagged (`:9.3.1`). Env: `JWT_ENABLED`, `JWT_SECRET` (≥32), `EXAMPLE_ENABLED=false` in prod.
Volumes: data `/var/lib/euro-office/documentserver`, logs `/var/log/...`, config `/etc/...`. Fits the
repo's `docker_compose_v2`-in-LXC convention (preferred over the reference repo's native `.deb` +
Apache).

**Connector**: app id `eurooffice`, **v11.0.1** (2026-06-30), `<nextcloud min-version="33"
max-version="35"/>` → hard block on NC 32 (see `057`). `occ` keys: `DocumentServerUrl` (public
https), `DocumentServerInternalUrl` (LAN http callback), `jwt_secret` (shared HS256).

**Reverse proxy (our Caddy)**: needs public HTTPS host, **WebSocket upgrade**, `X-Forwarded-Proto:
https`, long (~300 s) timeout. Caddy `reverse_proxy` handles WS + TLS (Domeneshop DNS) → **one
`caddy_services` entry** (upstream `<lxc-ip>:80`), same workflow as financial-scenario. No Apache
vhost.

**Sizing** (from the Proxmox reference deploy `Rich-Hacks/eurooffice-nextcloud`): 4 vCPU / 4 GB /
512 MB swap / 15 GB, unprivileged + nesting. Confirm PVE RAM headroom first.

**Risk / fallbacks**: young project (frozen at ONLYOFFICE 9.3.1) — a doc server parses untrusted
files, so track Euro-Office's security-patch cadence vs upstream and revisit the pinned tag. If it
proves unmaintained: upstream **ONLYOFFICE Document Server** (more maintained; CE connection limits)
or **standalone Collabora** (most-proven; ODF-best, weaker OOXML).

**Sources**: license (https://nextcloud.com/blog/euro-office-license-compliance-and-what-open-source-means/);
Docker install (https://euro-office.github.io/documentation/installation/docker/) + GHCR package
`ghcr.io/euro-office/documentserver`; ONLYOFFICE fork @ 9.3.1 + native stack + sizing
(`Rich-Hacks/eurooffice-nextcloud`); connector dependency via `gh api`
(`Euro-Office/eurooffice-nextcloud` `appinfo/info.xml` @ v11.0.1); NC integration docs
(https://euro-office.github.io/documentation/integration/nextcloud/).

## Verification (acceptance)

1. **Deploy**: run the pipeline; terraform creates the LXC; `docker compose` reports the container
   `healthy`; `GET /healthcheck` on the server → 200; gate green.
2. **Route**: `curl https://eurooffice.hus-sky.no/healthcheck` → 200 over TLS; browser shows the
   editor's `wss://` connection established.
3. **Editing**: create a `.docx` from the Files `+` menu, type, close, reopen → content persists;
   open in a second session → live co-editing; admin connector test passes.
4. **Security posture**: `EXAMPLE_ENABLED=false`; JWT enabled with a vault ≥32-char secret matching
   both sides; image pinned (not `latest`).
5. **Single connector**: `occ app:list` shows `eurooffice` enabled and `richdocumentscode` absent.
6. **Monitoring**: blackbox liveness probe for eurooffice is green in the monitoring contract.

## Dependencies

- **Blocked by**: [`057-nextcloud-upgrade-33-34`](./057-nextcloud-upgrade-33-34.md).
- **Assumes**: ~4 GB PVE RAM headroom; GHCR image reachable from the deploy host; Caddy (proxy 108)
  healthy; `caddy_services` route-add is the known workflow.
- **Out of scope**: the NC upgrade (`057`); migrating existing documents (they stay in Nextcloud);
  desktop editors.
