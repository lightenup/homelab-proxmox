# Feature Specification: Financial-Scenario v2 Deploy (Stateful)

**Feature Branch**: `048-financial-scenario-v2-deploy`
**Created**: 2026-06-21
**Status**: Draft
**Input**: Host the next version of the `personal-financial-scenarios` app (released as **`v0.2.2`**), which introduces (1) a single-engine topology where the MCP server is a thin HTTP client of the api and (2) a persisted scenario store backed by SQLite on the api service. Update the existing homelab deploy to match — without regressing the LAN/tailnet-only posture or the gated pipeline.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Upgrade in place without losing data (Priority: P1)

As the operator, I bump the pinned image tag to `0.2.2` and redeploy through the existing gated pipeline; the stack comes up healthy on the new single-engine topology, and previously saved scenarios and reference-data edits survive the image re-pull.

**Why this priority**: This is the core of the release — adopting the new topology while guaranteeing that the first-ever piece of host-only user state (saved scenarios) is never lost during an upgrade. A regression here means data loss, which is unacceptable.

**Independent Test**: Deploy `0.1.0`, save a scenario, set the version to `0.2.2`, re-run the playbook, and confirm all three containers reach healthy, the GUI serves traffic, and the previously saved scenario plus reference-data edits remain intact.

**Acceptance Scenarios**:

1. **Given** a running `0.1.0` stack, **When** I set the pinned version to `0.2.2` and run the playbook, **Then** all three containers reach `healthy` and the GUI serves a 200 on its published port.
2. **Given** reference-data edits exist on the host, **When** the upgrade runs, **Then** the reference-data store is preserved unchanged (no re-seed over existing data).
3. **Given** an existing saved-scenario store on the host, **When** the upgrade runs, **Then** it is never clobbered or re-initialised — saved scenarios remain listed and openable.

---

### User Story 2 - Agent-authored scenarios appear in the GUI (Priority: P1)

As an operator using an MCP client over the tailnet (through the gated `/mcp` endpoint), I save a scenario via MCP; it is persisted on the api service and is then selectable in the GUI for comparison.

**Why this priority**: The single-engine topology exists so that agent-authored and GUI-authored scenarios share one authoritative store. Validating the round-trip proves the new topology is wired correctly and the persisted store is genuinely shared.

**Independent Test**: With the stack healthy, save a scenario through the gated `/mcp` endpoint, then open the GUI comparison list and confirm the agent-authored scenario appears and opens with freshly computed results.

**Acceptance Scenarios**:

1. **Given** the stack is healthy, **When** I save a scenario via the gated `/mcp` endpoint, **Then** the api persists it tagged as agent-authored to the shared scenario store.
2. **Given** an agent-authored scenario exists, **When** I open the GUI comparison list, **Then** it appears, badged as agent-authored, and opens with freshly computed results.

---

### User Story 3 - Saved scenarios are backed up (Priority: P2)

As the operator, the saved-scenario store is included in the homelab backup regime (à la the existing nextcloud/immich backups) so a lost LXC does not lose hand-built scenarios.

**Why this priority**: Backups protect the new host-only state against catastrophic loss. It is P2 rather than P1 because the upgrade and topology change (P1) deliver the release; backup hardens it. The store originates only on the host, so without this the data has no recovery path.

**Independent Test**: Install the backup timer, trigger it, confirm a consistent snapshot lands on the NAS backup share, then restore that snapshot over a fresh store and confirm the restored scenarios are listed and openable.

**Acceptance Scenarios**:

1. **Given** the backup timer is installed, **When** it fires, **Then** a consistent (WAL-safe) snapshot of the scenario store is written to the NAS backup share.
2. **Given** several daily/weekly/monthly snapshots exist, **When** the prune step runs, **Then** grandfather-father-son retention is applied with the same policy shape as the existing nextcloud backup.
3. **Given** a snapshot exists, **When** the operator restores it over a fresh store and starts the stack, **Then** the restored scenarios are listed and openable.

---

### Edge Cases

- **First deploy vs. upgrade**: On a brand-new LXC with no existing store, the scenario store must be created by the app itself (idempotent table creation on startup), and the host directory must exist with correct ownership/mode — but the deploy must never seed, copy, or initialise a database file. On upgrade, an existing store must never be clobbered.
- **Backup under concurrent writes**: Because the store is WAL-mode SQLite, a raw file copy taken during a concurrent write can capture a torn database. The backup must use a consistent online-backup mechanism, not a plain copy.
- **MCP starts before api**: The MCP container is now a thin client of the api; if it starts before the api is healthy it has no authority to forward to. It must wait for the api to be healthy before starting.
- **NAS share unavailable at boot**: The in-guest backup mount must not block the LXC from booting if the NAS is temporarily unreachable.
- **Restore validation**: A restored snapshot must pass an integrity check before it is trusted as a recovery source.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The deploy MUST pin the application image tag to `0.2.2` via the canonical service-version configuration.
- **FR-002**: The deploy MUST provide a persistent host bind-mount for the api scenario store, mounted into the api container only, matching the durable-data convention used by other stateful services (host bind-mount, not a docker named volume). The MCP service MUST NOT mount it — the api is the single writer.
- **FR-003**: The deploy MUST rely on the application's default store path rather than overriding it, given the mount point established in FR-002. The override path MUST be documented so a future relocation is a single change.
- **FR-004**: The deploy MUST reconfigure the MCP service to be a stateless HTTP client of the api: remove its reference-data bind-mount, point it at the api base URL, and make it wait for the api to be healthy before starting, while preserving the transport/port settings the server needs to bind.
- **FR-005**: The deploy MUST preserve first-deploy-vs-upgrade safety for both stateful stores: keep seed-when-empty logic for reference data (seed from image on first deploy only), and for the scenario store ensure the host directory exists with correct ownership/mode but never seed, copy, or initialise a database file. An existing store MUST NOT be clobbered on upgrade.
- **FR-006**: The deploy MUST mount the backup destination in-guest (the LXC mounts the NAS share directly), requiring no PVE host fstab entry and no host bind-mount, conforming to the in-guest NFS convention. The mount MUST be resilient to the NAS being unavailable at boot.
- **FR-007**: The deploy MUST enable in-guest NFS on the LXC (the LXC feature flag required for an unprivileged container to mount NFS in-guest).
- **FR-008**: The deploy MUST add a backup role plus systemd service/timer mirroring the existing homelab backup roles that: takes a consistent (WAL-safe) online-backup snapshot of the scenario store, archives the snapshot together with a copy of the rendered compose file to the in-guest NAS mount, and applies grandfather-father-son retention with the same policy shape as the existing nextcloud backup.
- **FR-009**: The deploy MUST NOT change the exposure posture, the registry pull credential, the GUI-only published-port model, the image-baked MCP shared-secret gate, or the monitoring contract carried over from the prior deploy.

### Key Entities *(include if feature involves data)*

- **Saved scenario**: A user-generated financial scenario authored from the GUI or by an MCP agent, persisted in the api's scenario store. Carries a source attribution (GUI vs. agent-authored). This is the first host-only user state in the stack and the subject of the new backup story.
- **Scenario store**: The persisted SQLite database holding saved scenarios, living on a host bind-mount on the api service, created and migrated idempotently by the application on startup.
- **Reference data**: Application reference data that originates in the app image and is seeded on first deploy only; carried over unchanged from the prior deploy.
- **Backup snapshot**: A consistent point-in-time copy of the scenario store (plus the rendered compose file), written to the NAS backup share and subject to GFS retention.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After upgrading from `0.1.0` to `0.2.2` via the playbook, 100% of previously saved scenarios and reference-data edits survive — none are lost or re-initialised.
- **SC-002**: After the upgrade, all three containers reach a healthy state and the GUI serves traffic on its published port, with the MCP service starting only after the api is healthy.
- **SC-003**: A scenario saved via the gated MCP endpoint is selectable in the GUI comparison list and opens with freshly computed results, confirming a single shared store.
- **SC-004**: A triggered backup produces a snapshot on the NAS share that passes an integrity check, and restoring it over a fresh store reproduces 100% of the saved scenarios.
- **SC-005**: GFS retention keeps the expected number of daily/weekly/monthly snapshots and prunes the rest, matching the existing nextcloud backup policy.
- **SC-006**: The exposure posture is unchanged — only the GUI port is published, the MCP endpoint still requires the shared secret, and the blackbox liveness probe stays green.

## Assumptions

- The application released as `v0.2.2` behaves as described: MCP is a thin HTTP client of the api, and the api creates and migrates its scenario store idempotently on startup (idempotent table creation, WAL mode, run once at lifespan).
- The current LXC sizing (2 cores / 2048 MB) remains sufficient now that the api also serves all MCP traffic; the workload is light (one human plus a few agents). Sizing will be confirmed during planning and bumped only if the api shows memory pressure under concurrent saves.
- The MCP shared secret remains image-baked; making it per-deploy/vault-configurable is out of scope and requires a separate application change.
- The NAS backup share has already been created by the operator (one-time, outside the codified pipeline) with read/write permission for the LXC IPs; everything downstream is codified and runs through the gated pipeline.
- The backup mechanism uses the application's own SQLite online-backup capability (executed inside the api container) or an equivalent consistent-snapshot path, rather than a raw file copy.

## Dependencies

- **Application `v0.2.2`** (the single-engine topology + persisted scenario store) — hard prerequisite; the image tag this deploy pins.
- **Canonical service-version configuration** — already delivered; the pinned version lives in the shared services vars.
- **The prior financial-scenario deploy** — the baseline this extends (topology, exposure posture, registry pull, monitoring contract).
- **NAS backup share** (operator pre-requisite, already created) — mounted in-guest by the backup role, modelled on the existing jellyfin NFS mount for the mount and the nextcloud backup for the snapshot/retention/timer.

## Out of Scope

- Public exposure, reverse-proxy route, or landing-page card — the service stays LAN/tailnet-only.
- Application source changes — done in the app repo; this deploy only pulls and runs pinned tags.
- App-level metrics beyond blackbox liveness.
- LLM-backed catalog ingestion — the extraction integration stays unset.
- Migrating legacy browser-local scenarios — explicitly out of scope upstream; nothing to do here.
- Making the MCP shared secret vault-configurable — needs a separate application change.
