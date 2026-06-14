# Feature Specification: Financial-Scenario Service Deploy

**Feature Branch**: `046-financial-scenario-deploy`
**Created**: 2026-06-14
**Status**: Draft (Backlog)
**Input**: User description: "Host the personal-financial-scenarios app (a 3-container Docker stack: FastAPI api, FastMCP server, React/nginx gui) in the homelab by pulling pre-built private images from GHCR onto a new LXC. Tailscale/LAN-only, no public route. MCP exposed over the tailnet behind its auth gate. Further development continues, so this must follow the existing deploy pipeline and conventions exactly — no shortcuts."

## Summary

The `personal-financial-scenarios` app is currently run only on a developer laptop. This feature
hosts it on the Proxmox homelab on a **new dedicated LXC** named `financial-scenario`
(`192.168.1.217`, the next free service IP), following the same one-LXC-per-service recipe used by
Immich, Nextcloud, Jellyfin, and AdGuard: a Terraform `lxc_service` module block, an Ansible role
rendering a `docker-compose.yml`, the gated lab→prod deploy pipeline, and the monitoring contract.

Unlike every existing service, the images are **private** and built in a *different* repository.
The app's own repo publishes two versioned images to GHCR
(`ghcr.io/lightenup/financial-scenario-api` and `…-gui`; see PFS backlog `045`); this feature
**pulls pinned tags** of those images — it never builds from source on the LXC. The `api` image
serves both the `api` container and the `mcp` container (same image, different `command`), so the
Compose stack is three containers from two images.

Two deliberate departures from the existing pattern, both first-of-their-kind in this repo:

1. **Authenticated registry pull.** No homelab service pulls a *private* image today — every
   existing `ghcr.io/...` reference is public. This feature adds a vault-backed
   `community.docker.docker_login` to `ghcr.io` so the private tags can be pulled.
2. **No public Caddy route.** The app holds personal financial data, so it is **Tailscale/LAN-only**.
   It is reachable directly at `192.168.1.217` over the LAN and over the tailnet (the Proxmox host
   already advertises `192.168.1.0/24` as a subnet router), with **no** `*.hus-sky.no` entry and no
   landing-page card. The MCP endpoint is reachable the same way, gated by its bearer token.

## User Scenarios & Testing

### User Story 1 - Deploy the Stack via the Existing Gated Pipeline (Priority: P1)

As the homelab operator, I want to deploy the `financial-scenario` stack by selecting it in the
existing lab deploy workflow, so that it provisions and runs exactly like every other service —
Terraform creates the LXC, Ansible pulls the pinned images and brings the three containers up
healthy — with no bespoke, out-of-pipeline steps.

**Why this priority**: This is the feature's reason to exist. Everything else (remote access,
persistence, monitoring) is meaningless until the stack runs on the LXC through the trusted,
evidence-producing pipeline.

**Independent Test**: Run `.github/workflows/lxc-deploy-lab.yml` with `service: financial-scenario`.
Verify Terraform creates the LXC at `192.168.1.217`, Ansible logs into GHCR, pulls the two pinned
images, and all three containers (`api`, `mcp`, `gui`) report healthy; an evidence pack is produced
like other services.

**Acceptance Scenarios**:

1. **Given** the GHCR images for the pinned version exist (PFS `045`) and the pull credential is in
   vault, **When** the operator runs the lab deploy for `financial-scenario`, **Then** the LXC is
   created, the images are pulled, and the three containers become healthy.
2. **Given** `financial-scenario` is registered in the pipeline, **When** the operator opens the
   `lxc-deploy-lab` workflow, **Then** `financial-scenario` is a selectable service and passes the
   `service-scope-allowlist.json` gate.
3. **Given** a lab deploy succeeded, **When** the operator runs the prod promotion flow
   (`lxc-promote-prod`), **Then** it promotes `financial-scenario` using the same bounded mechanism
   as other services with no service-specific pipeline code.

---

### User Story 2 - Reach the App over LAN and Tailnet, Not the Public Internet (Priority: P1)

As a user at home or travelling, I want to open the financial-scenario GUI at the LXC address over
my LAN or Tailscale, while it remains unreachable from the public internet, so that sensitive
financial scenarios are never publicly exposed.

**Why this priority**: The exposure posture is a hard requirement for sensitive data and is as
important as the deploy itself; getting it wrong (a public route) would be a privacy incident.

**Independent Test**: From a LAN client and from a tailnet client, open
`http://192.168.1.217:<gui_port>` and use the app. From outside (no LAN, no tailnet), confirm the
address is unreachable and that no `financial-scenario.hus-sky.no` (or any public name) resolves or
routes.

**Acceptance Scenarios**:

1. **Given** the stack is deployed, **When** a LAN or tailnet client opens
   `http://192.168.1.217:<gui_port>`, **Then** the GUI loads and the API responds.
2. **Given** the Tailscale-only posture, **When** the repository and the reverse-proxy config are
   inspected, **Then** there is **no** `caddy_services` entry, no Caddy site block, and no
   landing-page card for this service.
3. **Given** a client with neither LAN nor tailnet access, **When** it attempts to reach the
   service by IP or any hostname, **Then** the service is unreachable (no public route exists).

---

### User Story 3 - Use the MCP Server Remotely Behind an Auth Gate (Priority: P2)

As an operator using an AI assistant, I want to point an MCP client at the financial-scenario MCP
endpoint over the tailnet, authenticated by a bearer token, so that I can run scenario/compare
tools against the real engine — and so that an unauthenticated caller is rejected.

**Why this priority**: Exposing MCP was the reason the app's MCP server (PFS `044`) was built;
hosting it for remote use is a primary goal, but the stack is useful via the GUI even before MCP
access is wired, so it ranks below US1/US2.

**Independent Test**: From a tailnet client, call the MCP endpoint at the LXC address with a valid
bearer token and successfully list/invoke a tool. Repeat with no token / a wrong token and confirm
the request is rejected.

**Acceptance Scenarios**:

1. **Given** the MCP container is running with its auth token configured from vault, **When** a
   tailnet client connects with the correct bearer token, **Then** it can list and invoke MCP tools.
2. **Given** the auth gate, **When** a client connects without a token or with a wrong token,
   **Then** the request is rejected.
3. **Given** the LAN/tailnet-only posture, **When** the MCP port is inspected, **Then** it is
   reachable at the LXC address over LAN/tailnet but has no public route.

---

### User Story 4 - Admin/Catalog Edits Survive Image Re-Pulls (Priority: P2)

As an operator, I want reference-data and admin/catalog edits made in the running app to persist
across image upgrades, so that re-pulling a newer pinned image does not wipe curated catalog data.

**Why this priority**: The app's catalog-ingestion feature writes to its reference-data files; an
image is immutable and re-pulled on upgrade, so without a persistent mount those edits vanish. This
matters once the app is actually used, hence P2.

**Independent Test**: Make a reference-data/admin change in the app, then redeploy (re-pull the
image / recreate the container). Verify the change is still present after the container is recreated.

**Acceptance Scenarios**:

1. **Given** a host bind-mount for reference data, **When** the container is recreated from a new
   image tag, **Then** previously-written reference-data edits are still present.
2. **Given** a first-ever deploy with an empty host data dir, **When** the stack starts, **Then**
   the reference data is seeded (from the image's baked-in defaults) and the app starts cleanly.

---

### User Story 5 - Service Liveness Is Monitored Like Other Services (Priority: P3)

As the operator, I want the financial-scenario service registered in the existing health/monitoring
system so that I am alerted if it goes down, consistent with every other service.

**Why this priority**: Observability is expected homelab hygiene, but the service is functional
without it; it is the lowest-priority slice and can ship slightly after US1–US4.

**Independent Test**: With the service up, confirm it shows healthy in the existing
healthcheck/monitoring tooling. Stop a container and confirm the liveness probe reports it down and
the down-alert fires.

**Acceptance Scenarios**:

1. **Given** a `host_vars` healthcheck/monitoring contract for the service, **When** the monitoring
   roles are deployed, **Then** a liveness probe targets the service on the LXC IP.
2. **Given** the probe, **When** the GUI/API stops responding, **Then** the probe reports the
   service down and the configured down-alert fires after its `for:` window.

---

### Edge Cases

- **GHCR pull-credential missing/expired**: If the `read:packages` token is absent or expired, the
  `docker_login`/pull MUST fail loudly with a clear message (mirroring the existing roles' vault
  assertions, e.g. AdGuard/Nextcloud `assert ... is defined`), not silently fall back to a stale or
  public image.
- **First deploy vs upgrade**: First deploy has an empty host data dir (must seed); an upgrade
  re-pulls a new tag against an existing data dir (must not clobber). The role must handle both.
- **MCP without a token configured**: If the MCP auth secret is not in vault, the deploy MUST fail
  the same way as the GHCR credential check rather than exposing an unauthenticated MCP endpoint.
- **`EXTRACTION_BASE_URL` unset**: There is no LM Studio / LLM in the homelab. The catalog
  AI-ingestion admin feature will be inert; the engine, GUI, and MCP MUST be unaffected. This is an
  accepted limitation, not a failure.
- **IP/name collision**: `192.168.1.217` and the names `financial-scenario` /
  `financial_scenario_lxc` MUST NOT collide with the existing `.210–.216` allocations or module
  names.
- **Lab vs prod parity**: The `service_ips` entry must be added to **both** `lab.tfvars` and
  `prod.tfvars` templates, or promotion will fail for the missing environment.

## Requirements

### Functional Requirements

- **FR-001**: A new Terraform `module "financial_scenario_lxc"` MUST be declared (modeled on the
  Immich block in `terraform/main.tf`) using the shared `modules/lxc_service`, with
  `hostname = "financial-scenario"`, `ip = var.service_ips["financial-scenario"]`, and modest
  sizing (recommended **2** cores / **2048** MB / **16** GB). *(US1)*
- **FR-002**: `service_ips` MUST gain `financial-scenario = "192.168.1.217/24"` in **both**
  `terraform/environments/lab.tfvars.template` and `prod.tfvars.template` (and the live tfvars).
  *(US1)*
- **FR-003**: A new Ansible role `financial_scenario` MUST render
  `templates/docker-compose.yml.j2` describing three services — `api`, `mcp`, `gui` — built from
  **two** pinned GHCR images, where `mcp` reuses the api image with
  `command: ["python", "-m", "src.mcp_server.server"]`. Image versions MUST be pinned via role/group
  vars (no `:latest` in the deployed Compose). *(US1)*
- **FR-004**: The role's `tasks/main.yml` MUST: ensure install/data directories exist →
  **authenticate to `ghcr.io`** → template the Compose file → run
  `community.docker.docker_compose_v2` with `pull: always` → `wait_for` the GUI/API health, mirroring
  the structure of `roles/nextcloud/tasks/main.yml`. *(US1)*
- **FR-005**: A vault-backed registry login MUST be added (first in this repo): a
  `community.docker.docker_login` task using `ghcr_pull_username` + `ghcr_pull_token` (a
  `read:packages` PAT) stored in `ansible/group_vars/services/vault.yml`. The role MUST `assert`
  these are defined before pulling, failing with a clear remediation message. *(US1)*
- **FR-006**: A playbook `ansible/playbooks/financial_scenario.yml` MUST apply
  `lxc_base` → `geerlingguy.docker` → `financial_scenario`, matching the existing service playbooks.
  *(US1)*
- **FR-007**: Per-service vars MUST be added to `ansible/group_vars/services/vars.yml`:
  `financial_scenario_ip` (`192.168.1.217`), `financial_scenario_gui_port`,
  `financial_scenario_api_port`, `financial_scenario_mcp_port`, and the pinned image
  tag/version(s). *(US1)*
- **FR-008**: The GUI and API MUST be reachable at the LXC IP over LAN and tailnet. The service MUST
  have **no** `caddy_services` entry, **no** Caddy site block, and **no** landing-page card.
  *(US2)*
- **FR-009**: The MCP container MUST be exposed at the LXC IP over LAN/tailnet and MUST enforce its
  bearer-token auth gate (from PFS `044`), with the token supplied from vault. Unauthenticated
  requests MUST be rejected. *(US3)*
- **FR-010**: The app's reference-data directory MUST be a host bind-mount (recommended
  `/opt/financial-scenario-data/reference_data`) seeded on first deploy and preserved across image
  re-pulls. *(US4)*
- **FR-011**: A `host_vars/financial-scenario.yml` MUST define a `healthcheck_url` (GUI port, path
  `/`) and a `monitoring_contract` providing a **blackbox HTTP liveness probe** of the LXC IP plus a
  down-alert. Because the app exposes no Prometheus exporter, `scrape_targets` is empty/omitted.
  *(US5)*
- **FR-012**: The service MUST be registered in the gated deploy pipeline by adding
  `financial-scenario` to the `service` choice options in `.github/workflows/lxc-deploy-lab.yml` and
  `"financial-scenario": ["module.financial_scenario_lxc"]` to
  `scripts/lab/service-scope-allowlist.json`. No orchestrator (`python/src/...`) code change is
  required — it validates `--service` solely against the allowlist. *(US1)*
- **FR-013**: The deployed Compose MUST leave `EXTRACTION_BASE_URL` unset (or empty); the stack MUST
  start and serve healthy without any external LLM. *(Edge case)*
- **FR-014**: All changes MUST be deployable both from CI/CD (GitHub Actions, self-hosted runner)
  and from a developer laptop using the same roles, consistent with existing services. *(US1)*

### Key Entities

- **`financial-scenario` LXC**: Unprivileged container at `192.168.1.217`, 2c/2048MB/16GB, running
  Docker via `geerlingguy.docker`; one host for the whole stack.
- **GHCR images + pinned tags**: `ghcr.io/lightenup/financial-scenario-api` (serves `api` + `mcp`)
  and `…-gui`, pulled at a pinned `:X.Y.Z` defined in vars.
- **GHCR pull credential**: `ghcr_pull_username` + `ghcr_pull_token` (`read:packages` PAT) in the
  services vault; the single secret enabling authenticated private pulls.
- **MCP auth token**: Bearer/shared secret in vault, injected into the `mcp` container, enforcing the
  044 auth gate.
- **Reference-data bind-mount**: Host dir mapped into the api/mcp containers; the persistence
  boundary for catalog/admin edits.
- **Monitoring contract**: `host_vars` healthcheck + blackbox liveness probe + down-alert (no app
  exporter).

## Success Criteria

### Measurable Outcomes

- **SC-001**: Running `lxc-deploy-lab` with `service: financial-scenario` provisions the LXC, logs
  into GHCR, pulls the two pinned images, and brings all three containers healthy, producing an
  evidence pack like other services.
- **SC-002**: The GUI loads and the API responds at `http://192.168.1.217:<gui_port>` from both a
  LAN client and a tailnet client.
- **SC-003**: A repository search finds **no** `caddy_services` entry, Caddy site block, or
  landing-page card for `financial-scenario`, and no public hostname resolves/routes to it.
- **SC-004**: An MCP client on the tailnet lists and invokes a tool with a valid bearer token, and is
  rejected with no/invalid token.
- **SC-005**: A reference-data edit persists after the container is recreated from a new image tag.
- **SC-006**: Stopping the stack causes the liveness probe to report it down and the down-alert to
  fire after its `for:` window; with the stack up, the service shows healthy in the existing tooling.
- **SC-007**: A deliberately missing/expired GHCR token causes the deploy to fail with a clear,
  actionable message rather than silently using a stale or public image.
- **SC-008**: The service promotes to prod through `lxc-promote-prod` using the same bounded
  mechanism as other services, with `service_ips` present in both lab and prod tfvars.
- **SC-009**: The feature deploys successfully from both a GitHub Actions run and a developer laptop
  using the same Ansible roles.

## Assumptions

- **A-001**: The PFS images exist in GHCR at the pinned tag before this deploy runs (depends on PFS
  backlog `045`); their coordinates are `ghcr.io/lightenup/financial-scenario-{api,gui}` and they are
  private.
- **A-002**: The Proxmox host runs Tailscale as a subnet router advertising `192.168.1.0/24`
  (role `tailscale_router`, `tailscale_subnet_routes: "192.168.1.0/24"`), so tailnet clients reach
  `192.168.1.217` directly with no per-host Tailscale agent on the new LXC.
- **A-003**: `192.168.1.217` is free (`.210–.216` are the current allocations) and within the
  advertised subnet.
- **A-004**: The existing `lxc_service` Terraform module, `geerlingguy.docker` role, gated
  lab/prod workflows, and `community.docker` collection are available and unchanged in shape.
- **A-005**: The app's runtime config needs are limited to ports, the reference-data bind-mount, the
  MCP auth token, and leaving `EXTRACTION_BASE_URL` unset; no database is required (the app has none).
- **A-006**: The operator can mint a GitHub `read:packages` PAT and an MCP bearer token to place in
  the services vault.

## Out of Scope

- **Building images / app source changes** — Done in the PFS repo (backlog `045`); this feature only
  pulls and runs pinned tags.
- **Public exposure / a `*.hus-sky.no` route / landing-page card** — Explicitly excluded by the
  Tailscale/LAN-only posture. Revisit only if the access model for this service is deliberately
  changed (would also require an auth gate in front).
- **App-level Prometheus metrics / a Grafana dashboard** — The app exposes no exporter; monitoring is
  blackbox liveness only. A bespoke dashboard or app metrics is a later enhancement.
- **LLM-backed catalog ingestion** — No homelab LLM exists; `EXTRACTION_BASE_URL` stays unset and
  that admin feature is inert. Pointing it at a future homelab LLM is a separate item.
- **Backups of app data** — The reference data originates in the app repo and is bind-mounted;
  dedicated backup/restore for it (à la `immich_backup`/`nextcloud_backup`) is not included here.
- **Automatic image-update / redeploy on new GHCR releases** — Deploys remain operator-initiated
  via the existing pipeline with an explicit pinned tag bump.

## Dependencies

- **PFS backlog `045` (Publish Service Images to GHCR)** — hard prerequisite; without published
  private images there is nothing to pull. This spec consumes its image names, the `vX.Y.Z` tag
  convention, and the `read:packages`-token requirement.
- **`039-https-services` / reverse-proxy posture** — only to confirm this service deliberately does
  **not** use it (no Caddy route).
- **`042`/`043` monitoring stack** — reused for the blackbox liveness probe and alerting (US5).

## Decision Log

| # | Ambiguity | Decision | Rationale |
|---|-----------|----------|-----------|
| D-001 | Build on the LXC vs pull pre-built images | Pull pinned GHCR images; never build on the box. | Matches every existing homelab service; keeps build/test in the app repo and deploy here; avoids a build toolchain and slow rebuilds on the LXC. |
| D-002 | Public route vs LAN/tailnet-only | LAN/tailnet-only; no `caddy_services` entry, no public name. | Personal financial data must not be internet-exposed. The subnet router already makes the LXC IP reachable over the tailnet, so a clean access path exists without a public route. |
| D-003 | Three images vs two | Two images; `mcp` reuses the api image with a command override. | The app's Compose builds `api` and `mcp` from the same context/target; publishing/pulling two images is the minimal, accurate surface. |
| D-004 | Private-registry auth (none exists in repo) | Add a vault-backed `community.docker.docker_login` to `ghcr.io`. | First private pull in this repo; an explicit, asserted credential is the sound way to do it, consistent with the repo's vault-assertion convention. |
| D-005 | Expose MCP or keep internal | Expose MCP over LAN/tailnet behind the 044 bearer-token gate. | Hosting the MCP server for remote AI-assistant use is a primary goal; the auth gate keeps the new surface from being an open compute endpoint. |
| D-006 | Reference-data persistence | Host bind-mount seeded on first deploy. | The catalog/admin feature writes to reference data; immutable images are re-pulled on upgrade, so a persistent mount is required to avoid data loss. |
| D-007 | Monitoring shape (no app exporter) | Blackbox HTTP liveness probe + down-alert via `host_vars` `monitoring_contract`; no `scrape_targets`. | The app exposes no `/metrics`; liveness is the honest, available signal and matches the existing monitoring contract mechanism. |
| D-008 | LXC sizing | 2 cores / 2048 MB / 16 GB. | Stateless calc engine + static GUI + MCP; cheap to start, trivially bumped later if profiling shows a need. |
| D-009 | Service identifier across tools | `financial-scenario` (hostname, pipeline service id, allowlist key); `financial_scenario_lxc` / `financial_scenario` for Terraform module and Ansible role (underscores). | The hyphen form matches the workflow `choice` + allowlist convention; underscores match HCL/Ansible identifier norms. Consistency prevents pipeline-gate mismatches. |

## Open Questions

- **Q-001**: Exact port mapping for `gui`, `api`, and `mcp` on the LXC — publish all three on the
  host network/IP, or only `gui` + `mcp` (with `api` reachable only via the GUI nginx proxy as in the
  app's Compose)? Resolve during planning by reading the app's `docker-compose.yml` and
  `services/gui/nginx.conf` (the GUI already proxies `/api`, `/docs`, and `/mcp`).
- **Q-002**: Should the deployed stack reuse the app's own `docker-compose.yml` shape (GUI nginx
  fronting `/api` and `/mcp`) so only the GUI port needs publishing, simplifying FR-008/FR-009? This
  likely reduces exposed ports to one; confirm against the nginx `/mcp` auth-enforcement decision
  from PFS `044`.
- **Q-003**: Pin strategy for the image tag var — a single `financial_scenario_version` driving both
  images (they release together in PFS `045`) vs per-image tags. Single version is simpler if the app
  repo always tags both together.
- **Q-004**: Does the blackbox exporter need a new probe *profile* for a plain-HTTP target on a
  non-standard port/IP (existing probes are HTTPS subdomains), or does an `http_2xx`-style module
  already exist? Confirm in the `042` blackbox config during planning.
