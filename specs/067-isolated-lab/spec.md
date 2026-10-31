# Feature Specification: Real isolated lab for the gated pipeline

**Feature Branch**: `067-isolated-lab`

**Created**: 2026-10-30

**Status**: Delivered 2026-10-31 (PRs #302-#315). Open: SC-007 tracking, 2 of 5 promotions recorded (T068).

**Input**: User description: "docs/backlog/067-lab-prod-same-address-space.md". The owner decisions
in its section *Decisions for the spec (2026-10-30)* are binding. Backlog `096` (one state location
per service) is folded into this feature.

## Clarifications

### Session 2026-10-30

- Q: How should integrations that use production credentials against internet services (public
  certificates via the DNS API, the private-network overlay key, paid model keys, email and push
  alerts) behave in lab? → A: Switched off in lab, per service, and listed (FR-011).
- Q: When does each service's state move to the new layout? → A: All 12 at once, in one supervised
  step, each verified with a production plan reporting "No changes" before the next (FR-013).
- Q: Once LAB no longer touches production, what happens to the standalone LAB workflows ("LXC
  Deploy (LAB)" and "LXC Promote (LAB)")? → A: Both are removed. The promotion workflow (LAB
  rehearsal, then PROD) is the only entry point (FR-018).
- Q: How does the nightly check report a container that is tracked by no state, or by more than
  one? → A: Through the existing alerting path. It publishes a metric that monitoring collects from
  the host, and an alert fires for "untracked or double-tracked > 0" and for "check is stale"
  (FR-014).
- Q: How much memory must stay free on the host while a lab copy runs? → A: 6 GB. A lab copy is
  not started when the host's available memory minus the lab copy's configured memory would be
  below 6 GB (FR-004).
- Q: What does the lifecycle workflow (add / change / delete a service) do with its `lab` target?
  → A: `prod` stays the real target. `lab` runs the same ephemeral, isolated rehearsal as the
  promotion's first stage, for add and change. `lab` with delete is refused, with an explanation
  (FR-020).
- Q: Does every LAB run prove on its own that production was not touched? → A: Yes. Each LAB run
  fingerprints production before and after (production states, plus the production containers'
  IDs, addresses and configuration), and any difference fails the run and is stored in its
  evidence (FR-021).

## Background

The pipeline promotes a service in two stages: LAB, then PROD. Today the LAB stage is not a
rehearsal:

- It deploys the **real production container** for the service: same host, same bridge, same
  address and same Terraform state as PROD. So a LAB apply *is* a production change, and the
  PROD stage that follows is close to a no-op.
- On 2026-10-28 this created a second container with a production IP address. A container that
  no state tracked had gone unnoticed for months.

This feature gives every service a real lab copy: short-lived, on an isolated network, with its
own state, and unable to touch production.

## User Scenarios & Testing *(mandatory)*

The actor is the **operator**, the person who owns the homelab and starts pipeline runs. The
pipeline itself also acts on the operator's behalf.

### User Story 1 - A LAB run rehearses a deploy without touching production (Priority: P1)

The operator starts the LAB stage for a service. The pipeline creates a throwaway lab copy of
that service on the isolated lab network, deploys the service's normal configuration to it,
checks that it is healthy, and removes it. Production is untouched: no production container,
production state, production data or production monitoring changes.

**Why this priority**: This is the whole point of the feature. Without it, "lab first, then prod"
is a false sense of safety, and every LAB run is an unreviewed production change.

**Independent Test**: Run the LAB stage for one service (for example `ntfy`). Record the
production container list, every production state and the service's production configuration
before and after. Then confirm three things. Nothing in production changed. A lab copy existed on
the lab network during the run and passed its health check. No lab copy remains afterwards.

**Acceptance Scenarios**:

1. **Given** a service whose production copy is running, **When** the operator runs its LAB stage,
   **Then** a lab copy is created at the service's lab address, deployed and health-checked, and
   then removed, and the production copy, production state and production configuration are
   byte-for-byte unchanged.
2. **Given** a LAB run whose deploy or health check fails, **When** the run ends, **Then** the lab
   copy and its scratch storage are removed anyway, and the run reports failure so the PROD stage
   refuses to proceed without an explicit override.
3. **Given** a LAB run that was aborted mid-way (runner killed), **When** the next LAB run for any
   service starts (or a scheduled clean-up runs), **Then** leftover lab copies and scratch storage
   from the aborted run are removed before anything else happens.
4. **Given** any LAB run, **When** it executes, **Then** the lab copy cannot reach any address on
   the production LAN except the explicitly listed exceptions, and cannot reach production
   services, NAS shares, monitoring or the phone notification channel.

---

### User Story 2 - Lab and production each have their own state, in honest places (Priority: P1)

Every service has exactly one state for its lab copy and one state for its production copy. Each
lives in a location whose name says which environment it belongs to, and both are backed up. The
existing states move there without any production container being changed. A nightly check
reports any container on the host that is tracked by no state, or by more than one.

**Why this priority**: The lab of Story 1 cannot exist while lab and production share one state.
A lab run would then overwrite production's record or destroy the production container. The
untracked container found on 2026-10-28 is the failure the nightly check exists to catch.

**Independent Test**: After migration, for every service: a production plan reports no changes,
the lab state is separate from the production state, and both appear in the next configuration
backup. Then create a container that no state tracks, on purpose, and confirm the nightly check
reports it by the next morning.

**Acceptance Scenarios**:

1. **Given** the current shared, partly misnamed state layout, **When** the migration runs for a
   service, **Then** a dated copy of the old state is kept first, the production state moves to its
   production location, and a production plan for the service reports no changes.
2. **Given** all services migrated, **When** the operator lists the state locations, **Then** each
   service has one production state and (once a LAB run has happened) no lingering lab resources,
   and the old shared layout is gone.
3. **Given** a container on the host that no state tracks, or that two states track, **When** the
   nightly check runs, **Then** it reports the container by name and ID, and states which case it is.
4. **Given** the nightly configuration backup, **When** it runs after migration, **Then** every
   service's production state is included.

---

### User Story 3 - The PROD stage is a real deployment again (Priority: P2)

Lab and production no longer share a container or a state. So the PROD stage plans and applies
against production on its own. Its plan shows the real production change, which the operator
reviews before approving.

**Why this priority**: It turns the existing approval gate from a formality into a real
review point. It depends on Stories 1 and 2.

**Independent Test**: Change a service's configuration and run the full promotion. The LAB stage
deploys the change to the lab copy only. The PROD plan shows the change against the production
copy. The production copy changes only after the PROD stage is approved and applied.

**Acceptance Scenarios**:

1. **Given** a configuration change, **When** the LAB stage has run, **Then** the production copy
   does not yet have the change, and the PROD plan shows it.
2. **Given** a LAB run that failed, **When** the operator starts the PROD stage, **Then** it refuses
   to apply unless the existing override is given explicitly.

---

### User Story 4 - The same lab path works from a laptop (Priority: P3)

The operator can run the same lab rehearsal from a developer machine with the same arguments.
It has the same isolation, clean-up and result as a pipeline run (constitution V).

**Why this priority**: Required by the constitution, and it is how the operator debugs a failing
LAB run. It adds no new capability beyond Story 1.

**Independent Test**: Run the lab rehearsal for one service from a laptop. Confirm it creates,
checks and removes the lab copy exactly as the pipeline does, and leaves production untouched.

**Acceptance Scenarios**:

1. **Given** a laptop with the documented access, **When** the operator runs the lab rehearsal for
   a service, **Then** the outcome matches a pipeline LAB run for the same service and commit.

---

### Edge Cases

- **Leftover lab copy from an aborted run** at the address the new run wants: it is removed first.
  The duplicate-container guard still stops any lab copy that would clash with a *production*
  container's name or address.
- **Two LAB runs at once**: there is one runner, so runs are serialised. If concurrency ever
  appears, two runs for the same service must not share a lab copy.
- **Lab copy needs another service** (for example the AI workspace needs the model gateway, and the
  document editor is used from the file service): that service is unreachable in lab. Checks that
  depend on it are skipped in lab and listed per service. They are never pointed at production.
- **Services whose own job is infrastructure** (the reverse proxy and the monitoring stack), and
  the model gateway: their lab copies must not obtain public certificates, change public DNS, join
  the private network overlay, make paid calls, probe production endpoints or send alerts. See FR-005, FR-009 and FR-011.
- **Service with NAS mounts**: in lab each mount is an empty per-run local directory. Checks that
  expect existing user data are skipped in lab. The roles' own "mount is present" checks pass,
  because a directory is mounted.
- **First lab run for a brand-new service**: works the same way; no production copy is required.
- **Large images** (the AI workspace pulls about 12 GB): the run is slower (see SC-004) but must
  not fail on time limits sized for today's runs.
- **Host short on memory**: at most one lab copy exists at a time. A lab copy must not start if
  doing so would leave less than 6 GB of the host's memory available. The run fails with a message
  giving the available and required figures instead. With today's figures (about 20 GB available,
  at most about 6 GB for the largest lab copy) every service fits.
- **State migration interrupted part-way**: the one supervised migration step stops at the first
  service whose plan does not report "No changes". Services already migrated stay migrated, and the
  dated copies allow the rest to be redone. No production container is changed at any point.

## Requirements *(mandatory)*

### Functional Requirements

**Lab copies (Story 1)**

- **FR-001**: The LAB stage MUST, for every service in the pipeline's service list, create a lab
  copy of the service on the isolated lab network, deploy the service's normal configuration to it,
  verify it, and remove it. The LAB stage MUST NOT create, change or remove any production
  container, production state, production data or production monitoring configuration.
- **FR-002**: A lab copy's address MUST be the production address's last part on the lab network.
  For example, production `192.168.1.212` becomes lab `10.99.0.212`. Lab addresses MUST NOT collide
  with addresses already used on the lab network.
- **FR-003**: The lab copy and its scratch storage MUST be removed at the end of every LAB run,
  whether it passed or failed. Leftovers from aborted runs MUST be removed before a new LAB run
  proceeds, and also by a scheduled clean-up, so none survives longer than a day.
- **FR-004**: At most one lab copy MUST exist at a time. A LAB run MUST refuse to start a lab copy
  when the host's currently available memory, minus the lab copy's configured memory, would be
  below **6 GB**. The run then fails with a message that gives both figures.
- **FR-005**: LAB verification MUST check the lab copy directly at its lab address from the host.
  It MUST NOT use the reverse proxy, public DNS names, certificates or external probes. No LAB check
  may contact a production endpoint.
- **FR-006**: Where a production mount exists, a lab copy MUST receive an empty per-run local
  directory instead of the NAS share. A lab copy MUST NOT have access to any NAS share.

**Isolation (Story 1)**

- **FR-007**: Lab copies MUST be able to reach the internet (package and image downloads) and the
  lab network's gateway. They MUST NOT be able to reach any address on the production LAN except
  exceptions that this specification's plan lists and justifies one by one. Name resolution MUST
  work without such an exception if possible.
- **FR-008**: The isolation MUST be verifiable. A LAB run, or a dedicated check, demonstrates that
  a lab copy's attempt to reach a production service is refused.
- **FR-009**: Lab copies MUST NOT be monitored, backed up, probed or alerted on. No scrape target,
  blackbox probe, backup timer or phone alert may be created for a lab copy.

**Secrets (Story 1)**

- **FR-010**: LAB deploys use the production secrets (owner decision: accepted risk, mitigated by
  minutes of lifetime and by FR-007). Existing production-only gates MUST stay closed in lab. For
  example, the AI workspace's Home Assistant credential is enabled only in production.
- **FR-011**: Lab copies MUST NOT use production credentials against **internet** services in a
  way that has an effect outside the lab: public certificate issuance, public DNS changes, joining
  the private network overlay, outbound notifications or paid model calls. Such integrations are
  **switched off in lab, per service**, and the plan lists each switch. As of 2026-10-30 they are:
  - **reverse proxy**: serves internal certificates only and makes no certificate-authority or DNS
    provider calls. Its lab check is that it starts and serves locally.
  - **model gateway** (`llm-router`): runs without the private-network overlay sidecar and makes no
    paid model calls. Its lab check is that the gateway answers.
  - **monitoring stack**: alert delivery has no receivers in lab (no email, no push).

  A service added later that holds such a credential MUST declare its lab switch in the same
  change.

**State (Story 2, absorbs 096)**

- **FR-012**: Each service MUST have one production state and one lab state, in separate,
  honestly named locations. Production states MUST be included in the nightly configuration
  backup. Lab states are temporary and need no backup.
- **FR-013**: Migrating the existing states MUST keep a dated copy of each before changing it,
  proceed one service at a time, and end with a production plan that reports no changes for that
  service. The old shared layout MUST then be removed: the misnamed `lab/` links, the unused
  `prod/` folders, the legacy fallback path and the obsolete per-service resources in the old
  combined root. The migration happens **all at once, in one supervised step** for all 12
  services, each verified with a production plan that reports no changes before the next service
  starts. The old layout is removed the same day, and the feature does not ship with the old and
  new layouts side by side.
- **FR-014**: A nightly check MUST compare the containers on the host with the production states
  and report any container that is tracked by no state or by more than one, and name it. Lab
  copies found outside a running LAB run count as leftovers and are reported too. It reports
  through the existing alerting path, the same one the backup-staleness alerts use: it publishes
  the counts and the time of its last successful run as metrics that monitoring collects from the
  host. An alert reaches the operator's phone when either count is above zero, and when the check
  has not completed successfully for more than 26 hours. The names of the offending containers
  are available to the operator from the check's own output.

**Pipeline behaviour (Story 3)**

- **FR-015**: The PROD stage MUST plan and apply against the production state only, and its plan
  MUST show the real production change. The existing rule that the PROD stage refuses to proceed
  after a failed LAB stage, unless explicitly overridden, MUST stay in force.
- **FR-016**: The existing duplicate-container guard MUST keep refusing any creation that clashes
  with a production container's name or address. Lab copies MUST NOT be reported as clashes with
  production (they use different addresses), and MUST NOT slip past it against a leftover lab copy.
- **FR-017**: The existing guard against a lab monitoring deploy overwriting production monitoring
  (backlog 072) MUST keep working. The lab inventory MUST list the lab copies, so lab deploys have
  real targets, and production monitoring MUST be unaffected by any LAB run.
- **FR-018**: The promotion workflow (LAB rehearsal, then the approved PROD stage) MUST be the only
  pipeline entry point for deploying a service. The standalone LAB workflows ("LXC Deploy (LAB)" and
  "LXC Promote (LAB)") MUST be removed, along with every reference to them: other workflows,
  documentation, runbooks and the agent guide. Historical feature specs (`specs/0NN-*/`) are records
  of past work and keep their references. The pipeline's job names and the operator
  documentation MUST describe the new behaviour: LAB is an isolated rehearsal and PROD is the real
  deployment. The 2026-10-28 warnings that "a LAB apply changes production" are replaced.

**Parity (Story 4)**

- **FR-019**: The lab rehearsal MUST run from a developer laptop with the same arguments and the
  same isolation, clean-up and verification as in the pipeline (constitution V). Any step that
  can only run on the host is documented, with the equivalent way to run it from a laptop.

**Lifecycle workflow**

- **FR-020**: The lifecycle workflow (add, change or delete a service) MUST act on production when
  its target is `prod`, keeping its existing confirmations for destructive changes, data deletion
  and production applies. With target `lab`, add and change MUST run the same ephemeral, isolated
  rehearsal as the promotion's LAB stage (FR-001 to FR-009) and change nothing in production.
  Delete with target `lab` MUST be refused, with a message explaining that there is no standing lab
  copy to delete. The `lab` target MUST NOT resolve to any production container or state.

**Proof on every run (Story 1)**

- **FR-021**: Every LAB run MUST record a fingerprint of production before the lab copy is created
  and again after it is removed. The fingerprint covers a checksum of every production state, and
  the production containers' IDs, names, addresses, configuration and running workload identity
  (as defined in SC-001). Any difference MUST fail the
  run, even if the lab copy itself passed. Both fingerprints and the difference MUST be kept in the
  run's evidence, so a failed run shows what changed. A failure here triggers the PROD stage's
  existing refusal to proceed after a failed LAB stage.

### Key Entities

- **Service**: one of the 12 services in the pipeline's service list (eurooffice,
  financial-scenario, hermes, homeassistant, immich, jellyfin, llm-router, market-model,
  monitoring, nextcloud, ntfy, reverse_proxy). It has one production copy and, during a LAB run
  only, one lab copy.
- **Lab copy**: a short-lived container for a service on the lab network at the mirrored address.
  It has per-run scratch storage, exists only during a LAB run, and is never monitored or backed up.
- **State (per service, per environment)**: the record of which containers the infrastructure tool
  manages. One for production, which is durable and backed up. One for lab, which is temporary.
- **Isolation exception**: a single production-LAN destination a lab copy may reach, with its
  justification. The list is expected to be empty or nearly so.
- **LAB run result**: pass or fail, with the production fingerprints from before and after the run
  (FR-021) as evidence that production was untouched. It feeds the PROD stage's gate.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For each of the 12 services, a LAB run leaves production unchanged. Every production
  state, the production container list and the service's production configuration are identical
  before and after the run. "Production configuration" means each production container's Proxmox
  configuration plus the identity of the workload running in it (its application containers),
  so a redeploy or restart inside a production container counts as a change. This is checked automatically by every LAB run (FR-021), not only once
  at acceptance, and a deliberately injected production change during a test run makes that run
  fail.
- **SC-002**: After any LAB run, passed, failed or aborted, no lab copy and no scratch storage
  remains longer than one day; after a run that ends normally, none remains at all.
- **SC-003**: From a lab copy, 100% of attempts to reach production services are refused, apart
  from the listed exceptions.
- **SC-004**: A LAB run takes at most the measured fresh-deploy cost on top of today's run. That is
  about 1–3 extra minutes for small services and up to about 9 extra minutes for the largest
  (backlog 067, "Measured cost of 2"); no run fails on a time limit.
- **SC-005**: After migration, a production plan for every service reports no changes, and every
  production state appears in the next nightly configuration backup.
- **SC-006**: A container that no state tracks (or that two states track) raises an alert on the
  operator's phone within 24 hours of appearing, and a check that stops running raises its own
  alert within 26 hours.
- **SC-007**: Over the first five promotions after the feature ships, every PROD plan shows the
  change being promoted rather than "no changes", and no production change happens before the
  PROD stage is approved.
- **SC-008**: A lab rehearsal started from a laptop gives the same result as the pipeline for the
  same service and commit.

## Assumptions

- The lab runs on the existing production host, on the existing isolated bridge (`vmbr99`,
  `10.99.0.0/24`). Measured on 2026-10-30: about 20 GB of the host's 31 GB is free, and the
  services' addresses (`.211`–`.222`) do not collide with what already uses the lab range (`.1`,
  `.10`, `.11`).
- There is one pipeline runner, so LAB runs are serialised. The 6 GB margin of FR-004 only ever has
  to fit one lab copy (the largest, the AI workspace, about 6 GB configured).
- A lab copy starts empty every run. Restores and migrations of real data are not exercised in
  lab; the restore drills cover the backups.
- Name resolution for lab copies uses public resolvers rather than a production-LAN exception,
  unless the plan finds a reason it cannot.
- The production vault is used in lab (owner decision). A separate lab vault is out of scope.
- Out of scope: a lab reverse proxy or lab domain, monitoring of lab copies, a second physical host,
  the nested lab hypervisor as a place for lab copies, and a pull-through image cache (unless the
  plan finds the measured run-time cost unacceptable).
- The existing restore drills, the duplicate-container guard (`ct_conflicts`), the lab monitoring
  guard (072) and the PROD-only credential gates (095 R-016 addendum) stay and are adapted, not
  replaced.
- The nested lab hypervisor rig (`lab-pve-01`, the confidence suite and `lab-rig`) keeps its
  current addresses and purpose and is not changed by this feature, other than sharing the bridge.
