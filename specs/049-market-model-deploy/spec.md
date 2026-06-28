# Feature Specification: Market-Model Service Deploy

**Feature Branch**: `049-market-model-deploy`
**Created**: 2026-06-28
**Status**: Draft
**Input**: User description: "Deploy the `market-model` service (curated stress library + stochastic path generator, API + MCP surface) on the homelab as a gated, LAN/tailnet-only LXC, modelled on the financial-scenario deploy but simpler: one GHCR image run as two roles (api+mcp), no GUI/nginx/auth gate, no backup/NFS (regenerable cache store). Source backlog: `docs/backlog/048-market-model-deploy.md`."

## Summary

`market-model` is the sibling service to `personal-financial-scenarios` (PFS): PFS owns portfolio
accounting; market-model owns *market futures and their probability* (return paths per asset class
over a horizon). The two services never call each other — an orchestrator/agent carries path sets
between them over MCP. This feature stands market-model up on its own LXC, modelled on the
financial-scenario deploy (feature `048`), but deliberately simpler in two ways that fall out of
what market-model actually is:

1. **No GUI, no reverse-proxy front, no auth gate.** market-model has no human UI — it is an
   API/MCP service consumed by the agent/orchestrator. There is no GUI layer to front the API/MCP
   surfaces or to hold a shared secret. The API and MCP ports are published directly on the
   LAN/tailnet, and MCP is unauthenticated at the service — acceptable because the service is
   read/compute-only (no secrets, no destructive operations) and the whole host is LAN/tailnet-only.

2. **No backup, no shared-storage mount.** market-model's only state is a path-set store, and that
   store is a content-addressed, regenerable cache, not original user data. The curated library is
   seeded from image-baked reference data on every startup (idempotently); assembled sets carry
   content-addressed ids so re-requesting identical inputs reproduces an identical result; generated
   sets are reproducible from the recipe recorded in their version string, which the consumer carries
   downstream. Nothing in the store originates here-and-only-here the way PFS's hand-authored
   scenarios do, so the store is a disposable cache on a host-local mount: it survives
   restart/upgrade, but it is not backed up.

Everything else mirrors the financial-scenario deploy: a single pinned image pulled from the
container registry and run as two roles, a private bridge network, healthchecks with startup
ordering, the registry pull credential, a centrally pinned version, and a blackbox liveness
monitoring contract.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Deploy comes up healthy through the gated pipeline (Priority: P1)

As the operator, I provision the service host, pin the image version, and run the deploy; the
single-image API + MCP stack comes up healthy on the new host, reachable only on the LAN/tailnet.

**Why this priority**: This is the core deliverable — without a healthy, correctly-scoped deploy
there is no service. It is the minimum viable slice and gates every other scenario.

**Independent Test**: Provision the host, pin the version, run the deploy, and verify both roles
report healthy, the liveness endpoint returns success, and only the two intended ports are exposed.

**Acceptance Scenarios**:

1. **Given** the host exists and the image version is pinned, **When** the operator runs the deploy,
   **Then** both the API and MCP roles reach a healthy state and a request to the API liveness
   endpoint returns success.
2. **Given** the stack is up, **When** the operator requests the API root, **Then** the path-source
   index is returned (curated library plus stochastic-generator discovery).
3. **Given** the stack is up, **When** the operator inspects the running host, **Then** only the API
   port and the MCP port are published — there is no GUI role and no public/reverse-proxy route.

---

### User Story 2 - An MCP agent generates and retrieves path sets (Priority: P1)

As an operator or agent on the tailnet, I reach the MCP service directly, list available
calibrations and stress scenarios, generate a stochastic path set, and retrieve it by id.

**Why this priority**: The whole purpose of the service is to serve path sets to an orchestrator
over MCP; a healthy deploy that cannot serve a round-trip has no value. Equal priority to US1.

**Independent Test**: From a tailnet client, call the discovery operations, generate a path set, and
fetch it back by id, confirming the returned content is identical to what was stored.

**Acceptance Scenarios**:

1. **Given** the stack is healthy, **When** the MCP client lists calibrations and stress scenarios,
   **Then** both discovery surfaces return their entries (the MCP role forwards to the API role).
2. **Given** a calibration id, **When** the client requests a generated or assembled path set,
   **Then** the API persists it to the path-set store and returns its id and version.
3. **Given** a returned id, **When** the client retrieves the path set by that id, **Then** the
   stored content is returned unchanged.

---

### User Story 3 - Upgrade in place; the cache is disposable (Priority: P2)

As the operator, I bump the pinned version and redeploy; the stack comes up healthy on the new
image, and the path-set store is treated as a disposable cache — it persists across the upgrade, but
losing it is recoverable by re-request.

**Why this priority**: Upgrade-safety and disposability matter for ongoing operations but are not
required for the initial value delivery, so they rank below the first-deploy and round-trip slices.

**Independent Test**: With a running stack holding existing path sets, bump the version and
redeploy; confirm both roles are healthy on the new version and existing rows are intact. Separately,
wipe the store, restart, and confirm the stack recovers with the curated library re-seeded.

**Acceptance Scenarios**:

1. **Given** a running stack, **When** the operator bumps the pinned version and redeploys, **Then**
   both roles reach a healthy state on the new version.
2. **Given** an existing path-set store, **When** the upgrade runs, **Then** the store is never
   seeded-over or clobbered — the curated library is re-seeded idempotently and previously
   assembled/generated rows remain intact.
3. **Given** the host data directory is wiped (disaster scenario), **When** the stack restarts,
   **Then** it comes up healthy with the curated library re-seeded from the image, and previously
   assembled sets are reproducible by re-requesting identical inputs (content-addressed ids
   unchanged).

---

### Edge Cases

- **Unpinned or mutable version**: The deploy must refuse to proceed if the version pin is empty or
  set to a mutable tag, to keep deployments reproducible.
- **Non-root write permissions**: The service process runs non-root; if the host-local data
  directory is not writable by that identity, the service cannot create its store and fails to start.
  The deploy must ensure the directory is owned by the correct identity.
- **MCP role starts before API is ready**: The MCP role depends on the API; it must not be
  considered healthy until the API is healthy.
- **Auto-seeded generated set lost before the consumer records it**: For a generated set with an
  auto-picked seed, the store is briefly the sole holder of that draw's recipe until the consumer
  durably records its id and version. A store wipe in that gap loses that specific draw's recipe.
  This is an accepted caveat (see Assumptions).
- **Registry pull credential lacks access**: If the pull token cannot read the market-model image,
  the deploy must fail clearly rather than partially provision.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001 — Service host**: The deploy MUST provision a dedicated `market-model` service host
  using the standard service-host provisioning pattern, modelled on the financial-scenario host.
  Initial sizing is modest (suitable for one human plus a few agents) and is revisited only under
  observed memory pressure. The host MUST NOT mount any shared/network storage. A free service
  address MUST be allocated for it.
- **FR-002 — Version pin**: The deploy MUST source the image version from the central service
  version-pin location, set to a real published registry tag, never empty and never a mutable tag.
  The service address and the published ports MUST be defined alongside it.
- **FR-003 — Deploy automation**: The deploy MUST mirror the financial-scenario deploy automation,
  minus the reference-data seed steps and minus any backup wiring. It MUST ensure the install and
  host data directories exist with the data directory owned by the identity the service process runs
  as (so the non-root process can create its store), authenticate to the registry using the existing
  pull credential, render the run definition, pull and start the stack, and verify health. It MUST
  NOT seed, copy, or initialise the store file — the application creates and migrates it on startup.
- **FR-004 — Two roles from one image**: The deploy MUST run the single market-model image as two
  roles: an **API** role serving on the API port with the host data directory bind-mounted as its
  single writable store, and an **MCP** role serving on the MCP port configured to forward to the API
  role over the private network. The MCP role MUST start only after the API role is healthy and MUST
  NOT mount the data store (the API role is the sole writer).
- **FR-005 — No store-path override**: The run definition MUST rely on the application's default
  store location resolving to the bind-mounted data directory, and MUST NOT override the store path.
  The override mechanism MUST be documented so a future relocation is a single change.
- **FR-006 — Liveness endpoint**: The deploy MUST use the API's dedicated liveness endpoint as the
  health/liveness target for both the run-definition healthcheck and the deploy-time verification.
- **FR-007 — Health verification**: After the stack starts, the deploy MUST wait for the API port to
  accept connections and then confirm the liveness endpoint returns success, with retries, before
  declaring the deploy successful.
- **FR-008 — Monitoring contract**: The deploy MUST add a blackbox liveness monitoring contract for
  the host (mirroring financial-scenario): a liveness target probing the API liveness endpoint over
  the LAN profile, expecting success, and a critical alert that fires when the probe fails for a
  sustained period. A health-check wrapper script mirroring the financial-scenario one MUST be added.
- **FR-009 — Preflight checks**: The deploy MUST assert that the registry pull credentials are
  defined, that the version pin is a real non-mutable tag, and that the container runtime is
  available — mirroring the financial-scenario preflight, minus any auth-secret, shared-storage, or
  backup assertions.
- **FR-010 — Pipeline wiring**: The deploy MUST add the playbook/automation entrypoint mirroring the
  financial-scenario one (minus the backup role) and make the new host resolvable in the generated
  inventory via the per-service Terraform `ansible_inventory` output (the orchestrator reads this
  per-service output; the service is deployed standalone). Matching the reference service, it is
  **not** added to the aggregate `services.yml`/`site.yml` entrypoints or to the root
  `terraform/outputs.tf` inventory.
- **FR-011 — Network posture unchanged**: The service MUST remain LAN/tailnet-only — no
  reverse-proxy/public route and no landing-page entry. The two published ports MUST be reachable
  only on the LAN/tailnet.

### Key Entities *(include if feature involves data)*

- **Path set**: A set of return paths per asset class over a horizon, identified by an id and a
  version. Assembled sets carry content-addressed ids (identical inputs reproduce an identical id);
  generated sets carry a recipe encoded in their version that reproduces the draw. Consumers carry
  the id and version downstream.
- **Curated stress library**: A reference collection of stress scenarios seeded from image-baked
  data on every startup, idempotently (existing rows are never overwritten).
- **Path-set store**: The service's only persistent state — a host-local, regenerable cache holding
  the curated library and assembled/generated path sets. Survives restart/upgrade; not backed up.
- **Service version pin**: The single source of truth for which published image tag is deployed.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After a single deploy run from a pinned version, both service roles report healthy and
  the API liveness endpoint returns success.
- **SC-002**: Only the two intended ports (API and MCP) are exposed on the host; no GUI role, no
  public/reverse-proxy route, and no landing-page entry exist.
- **SC-003**: An operator/agent on the tailnet can generate a path set and retrieve it by id, and the
  retrieved content is identical to what was stored.
- **SC-004**: Bumping the pinned version and redeploying results in both roles healthy on the new
  version with all previously stored path sets intact and the curated library unchanged (re-seeded
  without clobbering).
- **SC-005**: After wiping the host data directory and restarting, the stack returns to healthy with
  the curated library re-seeded, and a previously assembled set is reproducible by re-requesting
  identical inputs (same content-addressed id).
- **SC-006**: The blackbox liveness probe for the service reports healthy in the monitoring contract,
  and its alert fires when the service is taken down.
- **SC-007**: A deploy attempt with an empty or mutable version pin is rejected by preflight before
  any change is applied.

## Assumptions

- **Hard prerequisite met**: The market-model image build/release (a separate item in the
  market-model repository) has shipped its first published registry image with provenance and SBOM,
  along with the liveness and root endpoints and the env-driven MCP entrypoint this deploy relies on.
  This deploy only pulls and runs a pinned tag; no application source changes are in scope.
- **Disposable cache, no backup** *(operator-confirmed)*: The path-set store holds only regenerable
  content, so no backup, shared-storage mount, or external share is provisioned. Accepted caveat: for
  an auto-seeded generated set, the store is briefly the sole holder of that draw's recipe between
  generation and the consumer durably recording the id and version; a store wipe in that gap loses
  that specific draw's recipe. This is judged acceptable because the consumer owns identity and the
  store survives restart/upgrade.
- **MCP published directly, no auth gate** *(recommended default; objectable)*: There is no GUI layer
  to host a shared-secret gate, and adding one for a UI-less, secret-less, read/compute-only service
  is disproportionate. The MCP and API ports are published directly on the LAN/tailnet; posture
  relies on the host being tailnet-only. A gate, if later wanted, is a separate item.
- **Non-root service identity**: The service process runs non-root, so the host data directory must
  be owned by that identity (unlike the financial-scenario host, whose root container uses a
  root-owned directory). The exact identity is the one baked into the published image; the deploy
  depends on that contract, and a follow-up in the market-model repo to pin an explicit, documented
  identity is recommended.
- **Shared registry credential**: The existing registry pull credential used for the
  financial-scenario images also has read access to the market-model image (same namespace token).
- **Reference pattern**: The financial-scenario deploy (feature `048`) is the template; this deploy
  removes its GUI, backup, and shared-storage aspects and reduces it to one image run as two roles.

## Out of Scope

- The image build/release — owned by the market-model repository; this feature only pulls and runs a
  pinned tag.
- Application source changes (path generation, persistence, liveness/root endpoints, MCP env wiring).
- Backups, shared-storage mounts, and external shares — explicitly excluded.
- A GUI, an MCP auth gate, a public/reverse-proxy route, or a landing-page entry — excluded
  (LAN/tailnet-only, UI-less service).
- Application-level metrics — blackbox liveness only, matching the financial-scenario parity.
