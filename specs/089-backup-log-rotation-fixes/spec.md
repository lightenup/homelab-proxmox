# Feature Specification: Backup and Log Rotation Quick Fixes

**Feature Branch**: `089-backup-log-rotation-fixes`

**Created**: 2026-10-21

**Status**: Draft

**Input**: User description: "089-backup-and-log-rotation-quick-fixes.md Prompt me" — source backlog item
[`docs/backlog/089-backup-and-log-rotation-quick-fixes.md`](../../docs/backlog/089-backup-and-log-rotation-quick-fixes.md).

## Context

Three small defects were found on 2026-10-21 while measuring the live estate (read-only) for the
backlog items `090` (monitoring stack version currency), `091` (backup coverage and staleness) and
`092` (log aggregation). They are split out so they do not wait behind that feature work. Two of
them are backups that do not run today; the third is unbounded log growth that will eventually fill
service disks.

1. The Proxmox host's configuration backup has failed on every scheduled run since at least
   2026-01-19. It cannot take its lock file because the lock location is read-only inside its
   sandboxed service.
2. Immich's database backup (albums, users, metadata) is defined in the repo, with a schedule and a
   restore drill, but it is never installed. The only playbook that applies it is not run by any
   workflow. Photos themselves are on the NAS and are not affected.
3. No container host bounds its container logs. Current largest totals: nextcloud 245 MB,
   financial-scenario 149 MB, market-model 73 MB, immich 57 MB, eurooffice 57 MB.

## Clarifications

### Session 2026-10-21

- Q: Which log rotation limits per container? → A: 10 MB per file, 3 files (30 MB cap per container).
- Q: Applying the logging change restarts the container runtime on each host, briefly stopping all
  its containers. How is that handled? → A: Ride each host's normal pipeline deploy, one host at a
  time. A short per-service outage at deploy time is acceptable; no maintenance window and no extra
  runtime options.
- Q: What happens to the stand-alone Immich backup playbook once the service playbook applies the
  backup? → A: Delete it. A first run is triggered by starting the backup service directly.
- Q: How is each fix proven? → A: Live checks recorded in a quickstart runbook, plus cheap static
  checks where they exist. No new automated test suites. (Refined in the analysis session below.)

### Session 2026-10-21 (planning)

- Correction to the rollout answer: a normal deploy restarts the container runtime but does not
  recreate containers, and log limits are fixed when a container is created. Q: How are containers
  recreated? → A: A one-off recreate per host, run right after that host's pipeline deploy and
  recorded in the rollout record. No new code. Each service has two brief interruptions in its
  own window.
- Q: The Proxmox backup verifies each archive by decrypting it with a private key stored in the
  administrator's home directory, which the service's sandbox hides. Which fix? → A: Let the
  service read the home directory but still not write it. This is the one allowed widening besides
  the lock.

### Session 2026-10-21 (analysis)

- Constitution principle V (dual-provisioning parity) applied to the Proxmox host backup deploy.
  CI cannot reach root on the Proxmox host by design (the privilege tiers), so this deploy can only
  run from an operator machine. Q: How is this resolved? → A: Use the principle's documented
  exception. The limitation is written down in the operator documentation and the plan, the manual
  playbook run is the alternative, and a CI path is a follow-up. No privilege change in this
  feature.
- The constitution's test-driven rule asks for automated tests where feasible. A static guard test
  for the configuration this feature changes is feasible and cheap, so one is added to the existing
  guardrail tests. This refines the earlier "no new automated test suites" answer: there is still
  no new suite, only one test file in the existing one.

## User Scenarios & Testing *(mandatory)*

The actor throughout is the homelab operator: the person who owns the estate, deploys through the
gated pipeline, and would have to restore from backup after a failure.

### User Story 1 - Proxmox host configuration is backed up again (Priority: P1)

The operator relies on a nightly encrypted archive of the Proxmox host's configuration on the NAS to
rebuild the host after a disk failure. Today no archive is produced. After this fix, each scheduled
run completes and leaves a fresh, decryptable archive on the NAS.

**Why this priority**: The host configuration is the base everything else is rebuilt from, and the
backup has been silently failing for at least nine months. It is the largest gap in recoverability.

**Independent Test**: Deploy the host configuration change, let the schedule (or a manual start of
the same service) run, then confirm a new archive on the NAS that decrypts with the operator's key.

**Acceptance Scenarios**:

1. **Given** the fix is deployed to the Proxmox host, **When** the scheduled backup runs, **Then**
   it completes without error and the service reports success.
2. **Given** a completed run, **When** the operator lists the NAS backup location, **Then** an
   archive newer than 24 hours is present.
3. **Given** that archive, **When** the operator decrypts it with the backup key, **Then** it
   decrypts and contains the host configuration.
4. **Given** the fix is deployed, **When** the service runs, **Then** the existing sandboxing of the
   service is kept. The only new write access is what the lock needs, and the only new read access
   is to the decryption key the service already uses to verify its archives.

---

### User Story 2 - Immich database is backed up on a schedule (Priority: P1)

The operator wants Immich's database (albums, users, sharing, metadata) backed up on a schedule
without remembering to run anything by hand. After this fix, the normal Immich deploy installs the
scheduled backup, and the existing restore drill proves the backup can be restored.

**Why this priority**: Without it, losing the Immich container loses all album and user structure,
even though the photo files survive. Equal to Story 1: another backup that does not run today.

**Independent Test**: Run the normal pipeline deploy for Immich, confirm the backup schedule is
active on the Immich container, trigger one run, and run the existing restore drill against the
resulting archive.

**Acceptance Scenarios**:

1. **Given** the normal Immich deploy has run, **When** the operator inspects the Immich container,
   **Then** the scheduled database backup is installed and active.
2. **Given** the schedule is active, **When** a backup run is triggered, **Then** it succeeds and
   writes a new archive.
3. **Given** that archive, **When** the operator runs the existing restore drill, **Then** the drill
   passes.
4. **Given** the change is merged, **When** the operator looks for the old stand-alone Immich backup
   playbook, **Then** it no longer exists, and no operator runbook tells them to run it.

---

### User Story 3 - Container logs stay bounded on every container host (Priority: P2)

The operator wants container logs to stop growing without limit, so no service fails because its
disk filled with logs. After this fix, every container host caps each container's logs at
10 MB × 3 files, and each host is moved over through its normal deploy, one at a time, with progress
recorded.

**Why this priority**: No disk is full today (the largest total is about 245 MB), so this is
preventive rather than an active outage. It also has to land before `092` (log aggregation), which
reads these files.

**Independent Test**: Deploy one container host, confirm its containers were recreated and carry the
rotation limit, and confirm no log file on it exceeds the cap. Repeat per host.

**Acceptance Scenarios**:

1. **Given** the change is merged, **When** any container host is deployed, **Then** its container
   runtime defaults to rotating logs at 10 MB per file and 3 files per container.
2. **Given** a host has been deployed with the new setting, **When** the operator inspects its
   containers, **Then** every container was recreated after the change and reports the rotation
   limit.
3. **Given** all container hosts are done, **When** the operator sweeps every host, **Then** no
   container log on any host exceeds 30 MB in total.
4. **Given** the rollout is in progress, **When** the operator checks the rollout record, **Then**
   it shows which hosts are done and which remain.
5. **Given** the monitoring host, which installs its container runtime through a different path,
   **When** it is deployed, **Then** it gets the same rotation limits as the other hosts.

---

### Edge Cases

- **Lock left over from a crashed run**: a stale lock must not block every later run. Placing the
  lock in a location the system clears between runs or at boot is acceptable.
- **NAS not mounted** when the Proxmox backup runs: the run must fail visibly, not write the archive
  to local disk instead. This is existing behaviour and must not regress.
- **Immich deploy where the NAS is not required** (the lab environment): the backup must not break
  the lab deploy.
- **First Immich deploy after the change**: the schedule is installed but has not run yet. The
  restore drill needs at least one archive, so verification triggers one run first.
- **Containers that are not recreated**: changing the runtime default does not affect existing
  containers. A host is only "done" when every container on it was recreated after the change.
- **Runtime restart during deploy**: applying the setting restarts the container runtime and briefly
  stops every container on that host. The recreate that follows interrupts them again briefly.
  This is accepted. Hosts are done one at a time, so only one service is affected at a time.
- **Immich backup location not on the NAS in production**: if the NAS share is missing inside the
  Immich container, the deploy must fail rather than install a backup that writes to local disk.
  In the lab, where the NAS is not required, the backup is installed and writes locally.
- **Existing oversized logs**: recreating a container discards its old log file, so the existing
  large files go away as each host is done. No separate clean-up step is needed.
- **A service that sets its own logging options**: none do today. If one does later, its own setting
  wins. That is acceptable and out of scope.

## Requirements *(mandatory)*

### Functional Requirements

**Fix 1 — Proxmox host configuration backup**

- **FR-001**: The Proxmox configuration backup service MUST be able to create, hold and release its
  lock while running under its current sandboxing.
- **FR-002**: The fix MUST NOT widen the service's write access beyond the system lock directory
  (`/run/lock`). The service MAY read, but not write, the administrator's home directory, so its
  built-in check can
  decrypt each archive with the existing key. All other hardening (read-only system, private temp,
  no privilege escalation) stays.
- **FR-003**: The fix MUST be applied through the existing Proxmox host configuration and deploy
  path, not by hand on the host.

**Fix 2 — Immich database backup**

- **FR-004**: The existing Immich backup role MUST be applied by the playbook the pipeline already
  runs for Immich, in the same way other services apply their backup roles.
- **FR-005**: After a normal Immich deploy, the scheduled database backup MUST be installed and
  enabled on the Immich container.
- **FR-006**: The stand-alone Immich backup   playbook, which no workflow runs, MUST be removed. Live operator
  documentation that tells the operator to run it (today: the Immich backup and restore runbook)
  MUST be updated in the same change to start the backup service instead. Completed historical
  specs are records and are left unchanged.
- **FR-007**: The existing restore drill MUST be usable unchanged against archives produced by the
  scheduled backup.

**Fix 3 — Container log rotation**

- **FR-008**: Every container host MUST set the container runtime's default logging so each
  container's log rotates at 10 MB per file and keeps at most 3 files.
- **FR-009**: The setting MUST be defined once, in the variables shared by all service hosts, and
  MUST apply to the monitoring host too, even though it installs its container runtime through its
  own role.
- **FR-010**: The rollout MUST work one host at a time. Run that service's normal pipeline deploy
  (which applies the setting), then immediately run a one-off recreate of every container on that
  host. The recreate is a documented operator step, not new automation.
- **FR-011**: The rollout MUST keep a record, in the feature's quickstart, of which container hosts
  are done and when. The in-scope hosts today are: immich, monitoring, nextcloud,
  financial-scenario, market-model, eurooffice, llm-router, hermes and ntfy.

**Verification**

- **FR-012**: The feature's quickstart MUST contain the live check for each fix: a fresh decryptable
  Proxmox archive on the NAS; an active Immich backup schedule, a successful run and a passing
  restore drill; and a sweep confirming no container log exceeds 30 MB on any container host.
- **FR-013**: Where a cheap static check exists (lint, syntax check, rendering the service unit),
  it MUST pass before deploy. One automated guard test in the existing guardrail tests MUST check
  the configuration each fix changes, so a later edit cannot silently undo a fix. No new test
  suite is added.
- **FR-014**: The operator documentation for the Proxmox configuration backup MUST state that its
  deploy can run only from an operator machine with root access to the Proxmox host, why CI cannot
  run it, and the exact command to use (constitution principle V exception).

### Key Entities

- **Proxmox configuration archive**: an encrypted, timestamped snapshot of the Proxmox host's
  configuration, written to the NAS by the scheduled backup service.
- **Immich database archive**: a timestamped dump of Immich's database, written by the scheduled
  Immich backup and consumed by the restore drill.
- **Container host**: a service container (LXC) that runs Docker containers. The in-scope set is
  listed in FR-011.
- **Rollout record**: the per-host list in the quickstart showing which container hosts have been
  redeployed with rotation, and when.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The Proxmox configuration backup completes from its schedule, and a NAS archive newer
  than 24 hours exists and decrypts with the backup key.
- **SC-002**: The Proxmox configuration backup succeeds on 3 consecutive scheduled runs after deploy.
- **SC-003**: The Immich backup schedule is active on the Immich container after a normal pipeline
  deploy, with no manual steps on the container.
- **SC-004**: An Immich backup run succeeds and the existing restore drill passes against its
  archive.
- **SC-005**: 9 of 9 in-scope container hosts are recorded as done in the rollout record.
- **SC-006**: No container on any container host has a log larger than 30 MB in total.
- **SC-007**: Each service is interrupted only during its own deploy-and-recreate window; no two
  services are interrupted by the rollout at the same time.

## Assumptions

- The read-only lock location and the hidden decryption key (FR-002) are the known causes of the
  Proxmox backup failures. If a successful run then exposes another defect, fixing it is in scope,
  because SC-001 requires a successful run.
- The private decryption key is present on the Proxmox host at the location the existing runbooks
  use. If it is not, it must be restored from the password manager before SC-001 can pass.
- The existing Immich backup role, schedule, retention and restore drill are correct as written and
  only need to be installed. Changing backup frequency or retention is out of scope.
- Jellyfin and the reverse proxy do not run Docker and are out of scope for Fix 3. If either is found
  to run Docker, it is added to the rollout list.
- The monitoring host is a member of the shared service-host group, so the shared setting reaches
  it. If it does not, the same values are applied through the monitoring host's own variables
  (FR-009 still holds: one set of values).
- 10 MB × 3 is enough at the measured growth of about 7 MB/day for the whole estate. It also bounds
  how much log is kept on disk to cover an outage of the future log aggregation (`092`).
- Monitoring and alerting on backup freshness is out of scope; it belongs to `091`. Shipping logs
  off-host is out of scope; it belongs to `092`.

## Dependencies

- None blocking. `091` (backup coverage and staleness) builds monitoring on top of Fixes 1 and 2.
  `092` (log aggregation) collects the logs that Fix 3 rotates.
