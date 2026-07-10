# Feature Specification: Euro-Office Document Server Deploy

**Feature Branch**: `062-eurooffice-deploy`
**Created**: 2026-07-10
**Status**: Draft
**Input**: Deploy the Euro-Office document server (AGPLv3 sovereign fork of ONLYOFFICE DocumentServer) on its own gated LXC running the official GHCR image via docker compose, front it at `eurooffice.hus-sky.no` through Caddy, and wire it into Nextcloud via the `eurooffice` connector so users get in-browser collaborative editing with strong MS-Office fidelity — replacing the flaky built-in CODE. (Source backlog: `docs/backlog/058-eurooffice-deploy.md`.)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Editing a document from Nextcloud works end-to-end (Priority: P1)

A user opens a `.docx` in Nextcloud Files; it opens in the Euro-Office in-browser editor, edits save back to Nextcloud, and a second user co-edits the same document live.

**Why this priority**: This is the whole point of the feature — a working, high-fidelity online office suite for Nextcloud. Without it the deploy delivers no user value.

**Independent Test**: From a browser signed into Nextcloud, create/open a `.docx/.xlsx/.pptx`, make edits, close and reopen to confirm persistence, then open the same document in a second session to confirm live co-editing. Run the admin connector test and confirm the conversion/round-trip check passes.

**Acceptance Scenarios**:

1. **Given** the connector points at the document server, **When** a user opens or creates a `.docx/.xlsx/.pptx`, **Then** the editor loads and edits persist back to Nextcloud storage.
2. **Given** two logged-in users, **When** both open the same document, **Then** each user's edits appear collaboratively for the other.
3. **Given** the admin connector test in Nextcloud, **When** it runs, **Then** the conversion/round-trip check reports success.

---

### User Story 2 - Deploy comes up healthy through the gated pipeline (Priority: P1)

An operator runs the gated LAB→PROD pipeline; Terraform provisions the LXC, the document-server container starts, becomes healthy, and re-runs are idempotent with the version staying pinned.

**Why this priority**: A repeatable, healthy, idempotent deploy is the foundation the editing experience and reverse-proxy exposure both depend on.

**Independent Test**: Run the pipeline against the pinned image tag; confirm the container reaches `Up (healthy)` and the document-server health endpoint returns 200. Re-run the apply and confirm no unintended container recreation and an unchanged pinned version.

**Acceptance Scenarios**:

1. **Given** the pinned image tag, **When** the apply runs, **Then** the container is `Up (healthy)` and the document-server health endpoint returns 200.
2. **Given** a completed deploy, **When** the apply repeats, **Then** it is idempotent (no unintended recreation) and the version stays pinned.

---

### User Story 3 - Reachable and secured at eurooffice.hus-sky.no (Priority: P2)

The document server is published at `eurooffice.hus-sky.no` over TLS with WebSocket upgrade, and Nextcloud reaches it both via the public URL and a LAN internal callback URL sharing a JWT secret.

**Why this priority**: Public TLS exposure with working WebSockets is required for the browser editor to function, but it builds on a healthy deploy (Story 2) and enables the editing experience (Story 1).

**Independent Test**: `curl https://eurooffice.hus-sky.no/healthcheck` returns 200 over TLS; in a browser the editor establishes a `wss://` connection; Nextcloud validates both the public `DocumentServerUrl` and the LAN `DocumentServerInternalUrl` callback with the shared JWT.

**Acceptance Scenarios**:

1. **Given** a reverse-proxy entry for eurooffice, **When** the reverse proxy applies, **Then** `eurooffice.hus-sky.no` serves over TLS and upgrades WebSocket connections.
2. **Given** the connector config, **When** Nextcloud validates it, **Then** the public `DocumentServerUrl` and the LAN `DocumentServerInternalUrl` callback both succeed with a shared JWT.

---

### Edge Cases

- **JWT mismatch** between Nextcloud and the document server → editor fails to load. Both sides MUST share an identical ≥32-char vault secret; a mismatch MUST surface as a clear failure.
- **Example app left enabled** (`EXAMPLE_ENABLED=true`) → an unauthenticated example app is exposed. It MUST be off in production.
- **WebSocket not upgraded** by the proxy → editor spins forever. The route MUST pass the WebSocket upgrade, and a health assertion should cover it.
- **Nextcloud below version 33** → connector install is refused. Preflight MUST verify Nextcloud ≥ 33 and stop otherwise.
- **Host RAM exhaustion** — the server wants ~4 GB. Preflight MUST confirm PVE headroom before provisioning.
- **`latest` tag drift** → a floating tag can silently change the running version. The image MUST be pinned to a specific version tag.
- **Two office connectors enabled at once** → built-in CODE (`richdocumentscode`/`richdocuments`) MUST already be removed so only one office connector is active.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The document server MUST run from a pinned GHCR image tag (never `latest`) via docker compose on a dedicated, unprivileged LXC service host with nesting enabled.
- **FR-002**: The LXC MUST be sized for the workload (baseline 4 vCPU / 4 GB RAM / 15 GB disk), and preflight MUST confirm PVE resource headroom before provisioning.
- **FR-003**: JWT signing MUST be enabled with a shared ≥32-char secret sourced from the Ansible vault, identical on both the document server and the Nextcloud connector.
- **FR-004**: The example app MUST be disabled in production (`EXAMPLE_ENABLED=false`).
- **FR-005**: Persistent volumes MUST retain data/logs/config across restart and upgrade so config and caches survive; original documents remain in Nextcloud (no user-data backup is in scope).
- **FR-006**: The reverse proxy MUST publish `eurooffice.hus-sky.no` to the document-server upstream over TLS, with WebSocket upgrade and an adequate (~300 s) proxy timeout.
- **FR-007**: The `eurooffice` Nextcloud connector MUST be installed, enabled, and configured idempotently: public `DocumentServerUrl` (`https://eurooffice.hus-sky.no/`), LAN `DocumentServerInternalUrl` (`http://<lxc-ip>/`), and the shared JWT secret.
- **FR-008**: The feature MUST deploy through the gated LAB→PROD pipeline with a post-apply healthcheck on the document-server health endpoint, and MUST expose a blackbox liveness monitoring contract.
- **FR-009**: Preflight MUST verify Nextcloud ≥ 33 and MUST NOT proceed otherwise.
- **FR-010**: The built-in CODE connector (`richdocumentscode`/`richdocuments`) MUST already be removed so that no more than one office connector is enabled.
- **FR-011**: The chosen image tag MUST be recorded in the repository's central version-pin location.

### Key Entities *(include if feature involves data)*

- **Document Server**: The Euro-Office (ONLYOFFICE fork) service that parses and renders documents for in-browser editing. Holds no original user data; its persistent state is caches + config. Fronted publicly and reached internally on the LAN.
- **Nextcloud Connector**: The `eurooffice` Nextcloud app that links Nextcloud Files to the document server. Configured with public and internal server URLs and a shared JWT secret; requires Nextcloud 33–35.
- **JWT Secret**: A shared ≥32-char signing secret held in the vault, identical on both the document server and the connector; the trust boundary between them.
- **Reverse-Proxy Route**: The public `eurooffice.hus-sky.no` entry terminating TLS and upgrading WebSocket connections to the document-server upstream.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Opening or creating a `.docx/.xlsx/.pptx` from Nextcloud Files loads the Euro-Office editor and edits persist back to Nextcloud.
- **SC-002**: Two users can co-edit the same document live, and the admin connector test reports success.
- **SC-003**: The pipeline deploys idempotently; the container is `Up (healthy)`; the health endpoint returns 200; the post-apply healthcheck passes.
- **SC-004**: `https://eurooffice.hus-sky.no/healthcheck` returns 200 over TLS, and the editor's WebSocket connection establishes.
- **SC-005**: The image is pinned (not `latest`); the example app is disabled; JWT is enabled with a vault ≥32-char secret matching both sides.
- **SC-006**: Only the `eurooffice` connector is enabled as the office provider; the built-in CODE connector is gone.
- **SC-007**: The service appears in monitoring via a green blackbox liveness probe.

## Assumptions

- The Nextcloud upgrade to 33/34 has already landed (delivered as `060-nextcloud-upgrade-33-34`; the original backlog referenced `057`), so the connector's Nextcloud 33–35 requirement is satisfied. This was the previously-blocking dependency and is now unblocked.
- The pinned Euro-Office image tag is `9.3.1` (upstream ONLYOFFICE 9.3.1 build 37) unless a newer patched tag is chosen at plan time; the multi-arch GHCR image `ghcr.io/euro-office/documentserver` is reachable from the deploy host.
- The `eurooffice` connector at v11.0.1 is the target version (Nextcloud min 33 / max 35).
- The deploy follows the same shape as existing `docker_compose_v2`-in-LXC services (e.g. `financial-scenario`, `market-model`), and the reverse-proxy route-add is the known existing workflow.
- ~4 GB PVE RAM headroom is available; the Caddy reverse proxy is healthy.

## Out of Scope

- The Nextcloud upgrade itself (delivered separately).
- Migrating existing documents — they remain in Nextcloud storage.
- Desktop office editors.
- Any user-data backup for the document server beyond its config/JWT secret (documents live in Nextcloud).

## Dependencies

- **Blocked by**: the Nextcloud 33–34 upgrade (delivered as `060-nextcloud-upgrade-33-34`) — now satisfied.
- **Assumes**: ~4 GB PVE RAM headroom; the GHCR image reachable from the deploy host; the Caddy reverse proxy healthy; the reverse-proxy route-add is the known workflow.

## Risks & Fallbacks

- Euro-Office is a young project frozen at ONLYOFFICE 9.3.1; a document server parses untrusted files, so its security-patch cadence versus upstream MUST be tracked and the pinned tag revisited periodically.
- If Euro-Office proves unmaintained, fallbacks are upstream ONLYOFFICE Document Server (more maintained, but Community Edition connection limits) or standalone Collabora (most-proven, best ODF, weaker OOXML fidelity).
