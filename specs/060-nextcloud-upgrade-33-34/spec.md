# Feature Specification: Nextcloud Major Upgrade 32 → 34

**Feature Branch**: `060-nextcloud-upgrade-33-34`
**Created**: 2026-07-09
**Status**: Draft
**Input**: User description: "docs/backlog/057-nextcloud-upgrade-33-34.md — Upgrade the Nextcloud
service from major 32 to 34 in sequential steps (32→33→34) through the gated pipeline, with a
backup/restore drill around each hop, as the prerequisite for adopting the Euro-Office document
server (its connector requires Nextcloud 33–35). Retire the flaky built-in office editor as part of
the app-compatibility pass."

> **Numbering note**: sourced from backlog item `docs/backlog/057-nextcloud-upgrade-33-34.md`. The
> Spec Kit tooling assigns the next global feature number (**060**); the `057` in the backlog is the
> queue id, not this feature's number. Blocks the Euro-Office deploy (backlog `058`).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Nextcloud reaches 34 healthy, with data intact (Priority: P1)

As the homelab operator, I advance Nextcloud from major 32 to 34 so a modern office connector can be
adopted, and every existing user, file, and share survives the upgrade unchanged.

**Why this priority**: This is the feature's core outcome. Without a healthy landing on 34 the
downstream office-suite work cannot begin, and a mishandled major upgrade risks irreplaceable user
files — so "arrives on 34 with data intact" is the non-negotiable P1.

**Independent Test**: Advance the target major by one (32→33), run the gated deploy, and confirm the
instance reports the new version, is out of maintenance mode, has no pending database upgrade, passes
its health check, and a known user's files are intact. Repeat for 33→34. Delivers a fully upgraded,
data-preserving instance even if nothing else in the feature is done.

**Acceptance Scenarios**:

1. **Given** Nextcloud on 32, **When** the target is set to 33 and the deploy runs, **Then** the
   instance reports version 33.x, maintenance mode is off, no database upgrade is pending, and an
   existing user's files load.
2. **Given** Nextcloud on 33, **When** the target is set to 34 and the deploy runs, **Then** the
   instance reports 34.x with the same health conditions satisfied.
3. **Given** either hop, **When** the deploy completes, **Then** the public address for Nextcloud
   still resolves to the login page and the reverse proxy is unchanged.

---

### User Story 2 - Backup taken and restore proven before each hop (Priority: P1)

As the operator, before each major hop I capture a full backup and prove it restores, so a failed
upgrade can be rolled back to a known-good instance rather than leaving data at risk.

**Why this priority**: A major upgrade is the highest-risk operation against irreplaceable data. A
backup that has never been restored is not a trustworthy rollback. This is co-P1 with Story 1 —
the upgrade must not proceed unprotected.

**Independent Test**: Run the backup, restore its artefact into a scratch target, and confirm the
database imports cleanly and a sentinel file is byte-identical to the source; record the artefact as
the hop's rollback point.

**Acceptance Scenarios**:

1. **Given** a pre-upgrade state, **When** the backup runs, **Then** a dated artefact containing the
   database, file data, and instance config exists on the backup target and passes an integrity
   check.
2. **Given** that artefact, **When** a restore drill runs, **Then** the database imports without
   error and a sentinel file's checksum matches the source.
3. **Given** a hop that fails its post-upgrade health check, **When** the operator restores the
   pre-hop artefact, **Then** the instance returns to the prior major, healthy.

---

### User Story 3 - App compatibility reconciled; legacy office editor removed (Priority: P2)

As the operator, I confirm every enabled app is compatible with the target major and remove the
unreliable built-in office editor, so no incompatible app blocks the upgrade and no dead editor
lingers ahead of the replacement office suite.

**Why this priority**: Incompatible apps are the most common cause of a stuck Nextcloud upgrade, and
the built-in editor is being retired anyway — but this is P2 because it supports the upgrade rather
than being the upgrade itself.

**Independent Test**: After landing on 34, confirm the built-in office editor app is absent, every
remaining enabled app reports a 34-compatible version, and re-running the upgrade routine is a no-op.

**Acceptance Scenarios**:

1. **Given** the app set on 32, **When** the upgrade to 33 begins, **Then** the built-in office
   editor app and its connector are removed from the managed enabled-apps set and uninstalled.
2. **Given** the instance on 34, **When** app updates are applied, **Then** all enabled apps are at
   34-compatible versions and none is disabled by incompatibility.

---

### Edge Cases

- **Skipped major** (target advanced 32→34 directly): the upgrade must fail safely without touching
  data, and must not leave the instance stuck in maintenance mode.
- **Upgrade stalls in maintenance mode**: the deploy must surface the state and the runbook must
  define the manual recovery, rather than reporting a false success.
- **Database migration exceeds the window**: the deploy must not report success while a database
  upgrade is still pending.
- **Connector version ceiling**: the instance must not be advanced past major **35** while the
  target office connector supports only 33–35.
- **Backup target unavailable**: the pre-hop backup must fail closed and block the hop rather than
  upgrading unprotected.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The upgrade MUST proceed one major version at a time (32→33→34); it MUST NOT attempt to
  skip a major.
- **FR-002**: Before each major hop, the system MUST capture a full, integrity-checked backup
  (database + file data + instance config) and MUST NOT begin the hop if the backup fails.
- **FR-003**: The system MUST exercise and verify a restore of the pre-hop backup, and record the
  artefact as that hop's rollback point, before the hop is treated as protected.
- **FR-004**: Each hop MUST complete the instance's upgrade routine, leave maintenance mode off on
  success, and leave no pending database upgrade.
- **FR-005**: After each hop the post-deploy health check MUST pass and the instance MUST report the
  expected target version.
- **FR-006**: The system MUST remove the built-in office editor app and its connector from the
  managed enabled-apps set and uninstall them.
- **FR-007**: The system MUST confirm the remaining enabled apps are compatible with the target
  major and MUST NOT report success while any enabled app is disabled by incompatibility.
- **FR-008**: The upgrade MUST end on major **34** and MUST NOT advance the instance beyond major
  **35**.
- **FR-009**: The upgrade MUST run through the existing gated pipeline (no out-of-band manual
  upgrade) and MUST leave the reverse proxy configuration unchanged.
- **FR-010**: On a failed hop, the runbook MUST define a restore-from-artefact rollback returning the
  instance to the prior major.

### Key Entities

- **Nextcloud instance**: the running service being upgraded — carries a version, a maintenance
  state, a pending-database-upgrade state, and a set of enabled apps.
- **Backup artefact**: a dated bundle (database dump + file data + instance config) with an integrity
  checksum, serving as a per-hop rollback point.
- **Upgrade target**: the intended major version, advanced one step at a time from 32 to 34, bounded
  above by 35.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The instance reports major **34**, is out of maintenance mode, and has no pending
  database upgrade.
- **SC-002**: 100% of pre-existing users, files, and shares are intact after the upgrade; a sentinel
  document is byte-identical to its pre-upgrade copy.
- **SC-003**: For **each** of the two hops, a restore drill of the pre-hop artefact succeeded before
  that hop ran.
- **SC-004**: The built-in office editor app is absent, re-running the upgrade routine is a no-op,
  and no enabled app is incompatible with 34.
- **SC-005**: The public Nextcloud address serves the login page unchanged and the reverse-proxy
  configuration is untouched.
- **SC-006**: The target office connector's dependency (major ≥ 33) is satisfied — installing it on
  the resulting instance succeeds (verified as a dry check by the downstream Euro-Office feature).

## Assumptions

- **Version gate (verified)**: the Euro-Office connector `eurooffice` (v11.0.0/v11.0.1) declares
  `<nextcloud min-version="33" max-version="35"/>`; the current instance is pinned at 32. Target 34
  sits mid-window and matches the connector's guidance; do not exceed 35 while on this connector.
- **Sequential majors**: Nextcloud disallows skipping majors, so the path is exactly 32→33→34.
- **Mechanism**: the existing service pipeline (version pin bump + upgrade routine) and the existing
  Nextcloud backup path to NFS are the delivery mechanisms; this feature adds the *restore-drill*
  verification and the per-hop rollback discipline.
- **App set today**: the two office apps (connector + built-in editor) are removed here; `deck`,
  `calendar`, `weather_status`, `twofactor_totp`, `bruteforcesettings` are assumed to have
  33/34-compatible releases (to be confirmed per hop during planning).
- **Current state**: the instance is healthy on 32 (restored 2026-07-08) and the NFS backup target is
  reachable.

## Dependencies & Scope

- **Blocks**: backlog `058-eurooffice-deploy` (its connector needs the instance on major ≥ 33).
- **Out of scope**: deploying Euro-Office; any reverse-proxy change; advancing beyond major 34.
