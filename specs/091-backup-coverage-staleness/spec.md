# Feature Specification: Backup Coverage and Staleness

**Feature Branch**: `091-backup-coverage-staleness`

**Created**: 2026-10-23

**Status**: Draft

**Input**: User description: "docs/backlog/091-backup-coverage-and-staleness.md Prompt me" — source
backlog item [`docs/backlog/091-backup-coverage-and-staleness.md`](../../docs/backlog/091-backup-coverage-and-staleness.md),
which absorbs [`073`](../../docs/backlog/073-consolidate-backup-roles.md) (consolidate the backup roles).

## Context

The estate deliberately has no Proxmox guest backups: an LXC is rebuilt from Terraform and Ansible,
and only state that cannot be rebuilt is backed up, per service, to the Synology NAS. The owner
confirmed this on 2026-10-21, but it is not written down, and measuring it against the live estate
(2026-10-21, re-measured 2026-10-23 after `089` and `090` landed) found:

1. **Failures are silent.** Only hermes publishes a backup metric, and its alert cannot fire for a
   backup that never succeeded. Monitoring's backup has failed every night since at least
   2026-07-09; the Proxmox configuration backup failed from 2026-01-19 until `089` fixed it. Nobody
   noticed either. The Proxmox host is not scraped at all.
2. **The four service backup roles are copies** of each other (prune logic, handlers, schedule
   units). Any fix or new capability means four edits.
3. **Coverage gaps and defects**: Jellyfin's database (users, watch history) has no backup; the
   Proxmox backup timer fires twice a day; Immich's archive contains its secrets file; Nextcloud's
   backup does not check its destination and writes to local disk if the NAS is missing; hermes'
   NAS mount is not monitored like the others.

The measured per-host state and the owner's decisions of 2026-10-23 are in the backlog item and are
the baseline for this spec.

## Clarifications

### Session 2026-10-23

- Q: Existing Immich archives on the NAS contain the app's secrets file, readable on the share.
  New archives stop carrying it (FR-008). What happens to the existing ones? → A: Let them age out
  through normal retention (up to about 6 months). No rewrite of old archives and no rotation of
  the secrets in them; the exposure on the share is accepted until then.
- Q: Every backup must fail when its destination is not the NAS (FR-004). The lab has no NAS. How
  does the lab behave? → A: Backups are production-only. Lab deploys do not install them, and the
  set of backups expected by the staleness alert follows the same switch.
- Q: Jellyfin runs natively, not in a container. How is a consistent copy of its database taken?
  → A: An online database backup while Jellyfin keeps running. No downtime.
- Q: Jellyfin backup schedule and retention? → A: Daily at 05:00 (the next free slot after hermes
  at 04:45), with the same 7 daily / 4 weekly / 6 monthly retention as the other service backups.

### Session 2026-10-23 (analysis)

- The file-list comparison against "the previous night's archive" would fail for hermes, whose data
  directories gain files every day. The baseline is now a run of the old backup taken by hand just
  before each service's deploy (FR-006, SC-003). That leaves one extra archive that day, which the
  normal retention handles.
- The edge case "the alert should not fire before a new backup's first run" had no mechanism behind
  it. Resolved by order, not by a grace rule (constitution IV): a new backup's first run is
  triggered at its host's deploy, before monitoring is deployed with it in the expected set.

## User Scenarios & Testing *(mandatory)*

The actor throughout is the homelab operator: the person who owns the estate, deploys through the
gated pipeline, receives alerts on their phone, and would have to restore from backup after a
failure.

### User Story 1 - A failed or missing backup raises an alert (Priority: P1)

The operator wants to learn within a day and a half that any backup has stopped succeeding, or has
never succeeded, instead of finding out months later when they need it. After this change every
backup, the Proxmox configuration backup included, reports its last success to monitoring, and one
alert fires for any backup whose last success is too old or missing.

**Why this priority**: Silent failure is the root problem. Two backups failed for months unnoticed.
Every other story is only trustworthy once failures are visible.

**Independent Test**: With the alert deployed, stop one backup from succeeding (or remove its success
record) and confirm the alert fires for that backup only; restore it and confirm the alert clears.

**Acceptance Scenarios**:

1. **Given** every backup succeeded within the last 36 hours, **When** the operator checks
   alerts, **Then** no backup-staleness alert is active.
2. **Given** one backup's last success is older than 36 hours, **When** monitoring evaluates the
   rule, **Then** a warning-level alert fires naming that backup, and no other backup.
3. **Given** a backup that is expected for a host but has never recorded a success, **When**
   monitoring evaluates the rule, **Then** the same alert fires for it.
4. **Given** the Proxmox host, **When** the operator looks at monitoring's scrape targets, **Then**
   the Proxmox host is a target and its configuration backup's last success is visible.
5. **Given** the change is deployed, **When** the operator lists alert rules, **Then** there is one
   backup-staleness rule, and the hermes-only rule it replaces is gone.
6. **Given** hermes' NAS backup mount, **When** the operator queries filesystem metrics, **Then** it
   appears the same way every other host's NAS mount does.

---

### User Story 2 - One maintained backup mechanism that refuses a wrong destination (Priority: P1)

The operator wants a single service-backup mechanism, so a fix or capability is made once and
applies to every service, and wants every service backup to refuse to run when its destination is
not the NAS, so no backup quietly fills a local disk instead. The four existing service backups are
moved onto it one at a time, without breaking any of them or their existing archives.

**Why this priority**: Equal to Story 1. The success record of Story 1 is added once here rather
than four times, and the destination check closes Nextcloud's write-to-local path, which is a
backup that looks successful but is not on the NAS.

**Independent Test**: Move one service onto the shared mechanism, run its backup, and compare the
archive's file list with a run of the old backup taken just before the switch; point it at a
destination that is not the NAS mount and confirm the run fails without writing anything.

**Acceptance Scenarios**:

1. **Given** a service moved onto the shared mechanism, **When** its backup runs, **Then** the
   archive has the same name pattern, location and file list as a run of the old backup taken
   just before the switch (Immich without its secrets file), and runs at the same time.
2. **Given** existing archives from before the switch, **When** retention runs after the switch,
   **Then** they are pruned by the same 7 daily / 4 weekly / 6 monthly rules as before, and none is
   lost early or kept forever.
3. **Given** any service backup whose NAS destination is not mounted, **When** it runs, **Then** it
   fails, writes nothing, and records no success, so Story 1's alert eventually fires.
4. **Given** all four services are moved, **When** the operator looks in the repo, **Then** the four
   old backup roles no longer exist, not even as wrappers.
5. **Given** a service on the shared mechanism, **When** the operator reads its configuration,
   **Then** it supplies only how to take its snapshot and what to archive; the schedule units,
   destination check, retention and success record come from the shared mechanism.
6. **Given** a restore is needed, **When** the operator follows the restore path for each service,
   **Then** it works against an archive produced by the shared mechanism.

---

### User Story 3 - Every host whose state cannot be rebuilt is backed up, once a day (Priority: P2)

The operator wants the set of backups to match the policy exactly: Jellyfin's user and
watch-history data is backed up, the monitoring backup that can never work is removed, and the
Proxmox configuration backup runs once a day instead of twice.

**Why this priority**: Jellyfin is the one real coverage gap; the other two are clean-ups that stop
a permanently failing job and a duplicate run. Less urgent than making failures visible.

**Independent Test**: Deploy Jellyfin, run its backup, confirm an archive on the NAS containing the
database and configuration, restore it once; confirm monitoring has no backup job and the Proxmox
timer has one daily trigger.

**Acceptance Scenarios**:

1. **Given** Jellyfin is deployed, **When** its 05:00 backup runs, **Then** an archive with a
   consistent copy of its database and its configuration directory is on the NAS, Jellyfin kept
   serving during the run, and a success is recorded.
2. **Given** a Jellyfin archive, **When** the operator restores it, **Then** users and watch
   history are back. Metadata and trickplay images regenerate and are not in the archive.
3. **Given** the monitoring host after deploy, **When** the operator lists its scheduled jobs,
   **Then** the old monitoring backup script and its schedule are gone.
4. **Given** the Proxmox host after deploy, **When** the operator inspects the backup timer,
   **Then** it has exactly one daily trigger, at the configured backup time.

---

### User Story 4 - No secrets in service archives (Priority: P2)

The operator wants backup archives on the NAS to hold data, not credentials. Immich's archive stops
including the app's secrets file; a restore re-creates it from configuration.

**Why this priority**: A real exposure on a shared drive, but limited to the NAS and contained by
the decision to let old archives age out.

**Independent Test**: Run Immich's backup, list the archive, confirm no secrets file; run the
existing Immich restore drill and confirm it passes.

**Acceptance Scenarios**:

1. **Given** Immich's backup has run after the change, **When** the operator lists the archive,
   **Then** it does not contain the app's secrets file.
2. **Given** that archive, **When** the operator runs the Immich restore drill, **Then** it passes,
   with the secrets file re-created from configuration.
3. **Given** any other service archive, **When** the operator lists it, **Then** it contains no
   credentials file that it did not contain before this change.

---

### User Story 5 - The backup policy is written down and correct (Priority: P3)

The operator, or someone helping after a failure, wants one place that says which hosts are backed
up, which are rebuilt from configuration, and which are disposable, and why. Documentation that
claims monitoring coverage that does not exist is corrected.

**Why this priority**: Documentation does not stop data loss, but without it the deliberate "no
guest backups" decision looks like an oversight, and the wrong claims mislead whoever reads them.

**Independent Test**: Read the architecture document and check every host in the inventory is
listed with a class and reason; search the operations docs for the false alert claim.

**Acceptance Scenarios**:

1. **Given** the architecture document, **When** the operator reads its backup section, **Then** it
   states the policy and lists every inventory host as backed up, rebuilt from configuration, or
   disposable, each with a reason.
2. **Given** the architecture and Proxmox backup operations documents, **When** the operator reads
   them, **Then** none claims that a host-down alert covers the Proxmox backup; they point to the
   backup-staleness alert instead.
3. **Given** the monitoring quickstart, **When** the operator reads its NAS-mount section, **Then**
   it no longer describes an in-guest NAS mount for the monitoring host.

---

### Edge Cases

- **Backup never ran since deploy**: a newly added backup (Jellyfin) has no success record until
  its first run. The alert fires for it as soon as monitoring expects it. So a new backup's first
  run is triggered by hand when its host is deployed, and only then is monitoring deployed with the
  backup in its expected set. There is no separate grace period.
- **Host removed from the inventory**: its backup leaves the expected set in the same change, so the
  alert does not fire forever for a host that no longer exists.
- **Lab environment**: backups are not installed and are not expected, so the lab raises no
  staleness alerts and no lab backup writes to local disk.
- **Monitoring itself is down**: the alert cannot fire while monitoring is down. This is covered by
  the existing monitoring-health alerting and is not new scope.
- **Partial or interrupted run**: a run that fails midway records no success and leaves no
  half-written success record; a success is recorded only after the archive is complete on the NAS.
- **Two backups on the same host**: each records its own success and is judged separately.
- **Switch-over night**: the first run on the shared mechanism may land the same night as the last
  run of the old role. Archive names stay the same, so retention treats them as one series; the
  old schedule is removed in the same deploy so the backup does not run twice.
- **Jellyfin busy during backup**: the online database backup must produce a consistent copy while
  Jellyfin writes to it.
- **NAS mount missing at deploy time**: deploying a service whose NAS destination is not mounted
  in production must fail, rather than install a backup that can only fail.
- **Old Immich archives with secrets**: they remain on the NAS until retention removes them (owner
  decision). No step rewrites or deletes them early.
- **Bare-metal Proxmox host**: host metrics collection there must not carry over container-specific
  restrictions that hide real host data, nor expose collectors that are unsafe or noisy on the host.

## Requirements *(mandatory)*

### Functional Requirements

**Policy and documentation**

- **FR-001**: The architecture document's backup section MUST state the policy ("rebuild from
  configuration; back up only what cannot be rebuilt") and list every host in the inventory as
  backed up, rebuilt from configuration, or disposable, each with its reason.
- **FR-002**: The false claim that a host-down alert covers the Proxmox backup MUST be corrected in
  the architecture document and in both Proxmox backup operations documents. The monitoring
  quickstart's in-guest NAS-mount section MUST be corrected or removed.

**One service-backup mechanism**

- **FR-003**: A single shared service-backup role, applied once per service, MUST replace the four
  existing service backup roles (financial-scenario, hermes, immich, nextcloud). It owns the
  schedule units, handlers, destination check, retention pruning and success record; each service
  supplies only its snapshot step and the paths to archive. The four old roles MUST be deleted, not
  kept as wrappers. The Proxmox configuration backup stays a separate role and reuses only the
  success-record writer.
- **FR-004**: Every service backup MUST refuse to run, and fail, when its destination is not the NAS
  mount. In production, a deploy MUST fail if the destination is not mounted.
- **FR-005**: Schedules, retention (7 daily / 4 weekly / 6 monthly), destinations and archive names
  of the four migrated backups MUST stay as they are today, so existing archives keep pruning
  correctly.
- **FR-006**: Each service MUST be switched to the shared role and checked one at a time. The first
  run after each switch MUST be compared (file list) against a run of the old backup taken by hand
  just before that service's deploy, and the old schedule MUST not remain active beside the new one.
- **FR-007**: Service backups MUST be installed in production only. Lab deploys MUST NOT install
  them, and the expected-backup set (FR-012) MUST follow the same switch.

**Coverage**

- **FR-008**: Immich's archive MUST no longer contain the app's secrets file; a restore re-creates
  it from configuration. No other archive may gain a credentials file. Existing archives are left
  to age out (Clarifications).
- **FR-009**: Jellyfin MUST get a backup through the shared role: a consistent online copy of its
  database plus its configuration directory, daily at 05:00, with the shared retention, written to
  the NAS through the same host-mount-plus-bind-mount pattern as the other services (never an
  in-guest NAS mount). Metadata and trickplay images are excluded.
- **FR-010**: The monitoring host's backup script and its schedule MUST be removed. Monitoring is
  rebuilt from configuration; recent metrics, non-provisioned dashboard state and silences are
  accepted losses.
- **FR-011**: The Proxmox configuration backup timer MUST fire once a day, at the configured backup
  time.

**Staleness detection**

- **FR-012**: Every backup, the Proxmox configuration backup included, MUST record the time of its
  last success as a metric named per backup, written atomically on success only, through each
  host's existing host-metrics exporter. The Proxmox host MUST run that exporter and be a monitoring
  scrape target.
- **FR-013**: One backup-staleness rule MUST raise a warning when any backup's last success is older
  than 36 hours. It MUST replace the hermes-only rule.
- **FR-014**: A backup that is expected but has no success record MUST alert the same way. The
  expected set MUST come from the same inventory data that configures the backups, not a second
  hand-kept list.
- **FR-015**: Hermes' NAS backup mount MUST appear in filesystem metrics like every other host's
  NAS mount. The cause of its absence today MUST be found and fixed.

**Delivery and verification**

- **FR-016**: Changes on the Proxmox host (exporter, timer, success record) MUST be applied from an
  operator machine under the constitution principle V exception recorded by `089`, and the
  operator documentation MUST give the exact command.
- **FR-017**: Where cheap static checks exist (lint, syntax check, rule validation, rendering units),
  they MUST pass before deploy. Automated guard tests MUST cover the shared role's contract: each
  service supplies a snapshot step and archive paths, destination check present, success record
  written only on success, and the expected set derived from inventory data.
- **FR-018**: The feature's quickstart MUST record, per service, the switch date, the archive
  comparison and the restore exercised (SC-003), plus the deliberate-break test of the alert
  (SC-002).

### Key Entities

- **Backup**: a scheduled job that copies one host's non-rebuildable state to the NAS. Has a name,
  a host, a schedule, a snapshot step, the paths it archives and a retention policy.
- **Success record**: per backup, the time of the last successful run, visible to monitoring.
- **Expected-backup set**: the backups that should exist in production, derived from the inventory
  data that configures them. Drives "never succeeded" detection.
- **Backup class**: per inventory host, one of backed up, rebuilt from configuration, or disposable,
  with a reason. Recorded in the architecture document.
- **Archive**: a timestamped file on the NAS produced by one backup run, pruned by retention.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For every host classed "backed up" (Proxmox host, immich, nextcloud,
  financial-scenario, hermes, jellyfin), a backup newer than 36 hours exists on the NAS and the
  backup-staleness alert is quiet.
- **SC-002**: Breaking one backup on purpose raises the alert for that backup only, within its
  36-hour window. Removing its success record raises it too.
- **SC-003**: After the switch to the shared role, each of the five service backups (four migrated
  plus Jellyfin) produces an archive whose file list matches that of a run of the old backup taken
  just before the switch (Immich without its secrets file; Jellyfin has no earlier backup), and one
  restore of each is
  exercised and recorded: the existing drills for Immich and hermes, a recorded manual restore for
  Nextcloud, financial-scenario and Jellyfin.
- **SC-004**: The Proxmox configuration backup runs once per day, its success time is in
  monitoring, and its archive passes the existing Proxmox backup verification script.
- **SC-005**: The architecture document lists 100% of inventory hosts with a backup class.
- **SC-006**: The four old service backup role directories, the monitoring backup script and the
  hermes-only staleness rule no longer exist in the repo.

## Assumptions

- The per-host measurements and owner decisions in the backlog item (2026-10-23) are current. If a
  host's state has changed by implementation time, the classification is updated in the same
  change.
- llm-router and the reverse proxy are rebuilt from configuration (reasons in the backlog item);
  ntfy, market-model and eurooffice are already documented as needing no backup; the empty Home
  Assistant LXC is not in the inventory and is out of scope.
- Warning-level alerts already reach the operator's phone through the existing alert routing; no
  routing change is needed.
- Jellyfin's LXC can get the NAS host mount and bind mount the other services use; adding it is in
  scope.
- The existing restore drills for Immich and hermes keep working with archives from the shared role,
  with only the changes needed to re-create Immich's secrets file.
- The 36-hour threshold suits every backup, since all run daily.
- Proxmox guest backups (vzdump) remain out of scope by the policy this feature records.
- Shipping logs off-host is out of scope; it belongs to `092`.

## Dependencies

- **Absorbs** `073` (consolidate backup roles).
- **After** `089` (backup and log-rotation quick fixes) and `090` (monitoring stack version
  currency), both delivered.
- **Before** `092` (log aggregation), whose agent on the Proxmox host builds on the exporter and
  scrape target added here.
- **Closes** "Backup job monitoring" and the host-exporter part of "Proxmox host/guest + storage
  health" in `improvement-candidates.md`.
