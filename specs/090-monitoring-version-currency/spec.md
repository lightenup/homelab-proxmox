# Feature Specification: Monitoring Stack Version Currency

**Feature Branch**: `090-monitoring-version-currency`

**Created**: 2026-10-22

**Status**: Draft

**Input**: User description: "090-monitoring-stack-version-currency.md prompt me" — source backlog item
[`docs/backlog/090-monitoring-stack-version-currency.md`](../../docs/backlog/090-monitoring-stack-version-currency.md).

## Context

The monitoring stack's image pins have not moved since they were set. Three components (Grafana, Prometheus, Telegraf) are past
their vendors' support windows, and nothing in the repo notices when a pin falls behind: the only
automated dependency tool covers the Python tooling and cannot read version variables in the
deployment configuration.

State checked 2026-10-21 (re-check at plan time):

| Component | Pinned (live) | Latest | Support status |
|---|---|---|---|
| Grafana | 12.3.1 | 13.2.x | 12.3 security support ended 2026-08-19. Supported: 13.2 (to 2027-05-18), 13.1 (to 2027-03-20), 12.4 (to 2027-05-24) |
| Prometheus | v3.8.1 | v3.15.0 | 3.8 unsupported since 2026-01-09. LTS: 3.13 (to 2027-07-31) |
| Alertmanager | v0.30.0 | v0.34.1 | No published support policy; four minors behind |
| blackbox_exporter | v0.28.0 | v0.29.0 | One minor behind |
| Telegraf | 1.37.0 | 1.40.2 | 1.37 support ended 2026-06-08 (found at plan time) |
| node_exporter (every LXC) | 1.10.2 | 1.12.1 | Two minors behind |

The monitoring versions are defined twice today: in the monitoring host's variables and again in
the monitoring role's defaults. node_exporter's version lives in its own role's defaults and
reaches every container host.

## Clarifications

### Session 2026-10-22

- Q: Which Grafana line? → A: Target 13.2. Fall back to 12.4 only if the plan finds a 13.0 breaking
  change that affects the provisioned dashboards or data sources and cannot be fixed here.
- Q: Should Prometheus follow LTS lines or the six-weekly minors? → A: LTS lines (3.13 now). Expect
  about one upgrade a year.
- Q: Which currency mechanism? → A: A scheduled check that posts to ntfy, like the model scout.
  Renovate is not used.

### Session 2026-10-22 (planning)

- Finding: Telegraf 1.37 also left support, on 2026-06-08 (endoflife.date). The table above
  understated it as "three minors behind". FR-003 already covers it.
- Finding: both Grafana 12.4 and 13.x move dashboard storage one way on first start. A Grafana pin
  change is therefore never a rollback. Only the snapshot is (research R-02).
- Q: Where does the check run? → A: As a scheduled workflow on the self-hosted CI runner, which
  runs a Python module in the existing package. The same command runs locally with `--dry-run`.
- Q: Cadence and repeats? → A: Weekly, with no state. Every finding repeats until fixed. A run with
  nothing behind sends nothing.
- Q: Which service pins? → A: Every pin with a release or support source. Pins without one
  (digest-pinned, date-tagged, own images) are listed by name as "not checked".
- Q: Rollout? → A: First choice was "lab first". That is not possible, because lab and prod share an
  address space (`072`, `067`), so a lab monitoring deploy reaches production. Replaced by a
  side-by-side rehearsal on the monitoring host: the target validators run against the live
  config, and a temporary Grafana 13.2 runs on a copy of its data. Then the snapshot, then one
  prod deploy.

## User Scenarios & Testing *(mandatory)*

The actor throughout is the homelab operator: the person who owns the estate, deploys through the
gated pipeline, and relies on the monitoring stack to learn when something breaks.

### User Story 1 - Monitoring runs supported versions without losing anything (Priority: P1)

The operator wants every monitoring component on a version its vendor still supports, so security
fixes keep arriving. The upgrade must not silently drop a scrape target, an alert rule, a
dashboard or an alert channel; the `072` incident showed that a monitoring deploy can lose
configuration without anyone noticing.

**Why this priority**: Two components are already out of security support. The monitoring stack
is the estate's only alarm, so a silent loss here hides every other failure.

**Independent Test**: Record targets, rules, dashboards and alert delivery before the upgrade;
deploy the new pins through the pipeline; record the same after; compare.

**Acceptance Scenarios**:

1. **Given** the new pins are deployed, **When** the operator lists the running versions, **Then**
   each component in the table runs a version inside its vendor's support window, or the latest
   release where there is no policy.
2. **Given** a before-snapshot of scrape targets, **When** the upgrade completes, **Then** the same
   set of targets is present and up.
3. **Given** a before-snapshot of loaded alert rules (count and names), **When** the upgrade
   completes, **Then** the same rules are loaded.
4. **Given** the upgrade is complete, **When** the operator opens each provisioned dashboard,
   **Then** every dashboard loads without panel errors and its data sources resolve.
5. **Given** the upgrade is complete, **When** the operator fires a test alert, **Then** it reaches
   both Pushover and ntfy.
6. **Given** the new configuration, **When** the rule and alert-routing validators run, **Then**
   both pass.

---

### User Story 2 - Failed upgrade can be undone (Priority: P1)

The operator wants a known way back if the upgrade breaks monitoring: a captured state of the
monitoring host and a record of the previous pins.

**Why this priority**: The monitoring host's own backup does not work today (owned by `091`). An
upgrade without a rollback point risks losing dashboards and history with no recovery.

**Independent Test**: Before the upgrade, confirm a snapshot of the monitoring host exists and the
previous pins are written down. The rollback steps can be read and checked without being run.

**Acceptance Scenarios**:

1. **Given** the upgrade has not started, **When** the operator checks the hypervisor, **Then** a
   one-off snapshot of the monitoring host exists, taken before the upgrade.
2. **Given** the upgrade record, **When** the operator reads it, **Then** it lists every previous pin
   and the steps to restore them and the snapshot.
3. **Given** the upgrade has been verified, **When** the operator closes the feature, **Then** the
   one-off snapshot is removed so it does not grow unbounded.

---

### User Story 3 - Each version is defined in one place (Priority: P2)

The operator wants to change a monitoring version by editing one line, not two that can drift.

**Why this priority**: Duplicate pins make the upgrade itself error-prone and make the currency
check (Story 4) ambiguous. It is a precondition for Story 4 rather than value on its own.

**Independent Test**: Search the repository for each monitoring version variable and confirm it has
a single authoritative value.

**Acceptance Scenarios**:

1. **Given** the change is merged, **When** the operator searches for each monitoring component's
   version, **Then** exactly one place sets the value that is deployed.
2. **Given** a role still carries a default, **When** the role is used in production, **Then** the
   host variables override it, and the default is not a second copy of the same pin.

---

### User Story 4 - Pins that fall behind are reported (Priority: P2)

The operator wants to be told when a pinned monitoring image falls behind or leaves support,
instead of finding out a year later by chance.

**Why this priority**: Without it, this feature has to be repeated by hand. It matters less than
fixing the current unsupported versions, so it follows Stories 1–3.

**Independent Test**: On a test branch, lower one pin; confirm the mechanism reports it.

**Acceptance Scenarios**:

1. **Given** the mechanism is active, **When** a pinned monitoring image has a newer release,
   **Then** the operator receives a report naming the component, the pinned version and the
   available version.
2. **Given** one pin is lowered on a test branch, **When** the mechanism runs, **Then** it reports
   that pin.
3. **Given** the service images pinned in the services variables, **When** the mechanism runs,
   **Then** they are covered too, even if their upgrades stay manual.
4. **Given** nothing is behind, **When** the mechanism runs, **Then** it produces no report (no
   noise).

---

### Edge Cases

- **Grafana major-version breaking changes**: a dashboard, data source or plugin that the new line
  no longer supports must be found during verification, not after. Any provisioned item that
  fails blocks the upgrade. It is either fixed or causes the fallback to 12.4 (FR-001). It is
  never accepted as a known issue.
- **Prometheus on-disk data format**: if the new version cannot read existing time-series data,
  history would be lost. Verification confirms that data from before the upgrade is still
  queryable.
- **Grafana internal database migration**: a major-version upgrade migrates Grafana's own database
  one way. Rollback after it has run requires the snapshot, not only a pin change.
- **node_exporter reaches every container host**: its upgrade is rolled out through each host's
  normal deploy. A host that has not been redeployed yet keeps the old version; the upgrade record
  lists which hosts are done.
- **Alert rules that use removed or renamed functions** fail to load silently in some versions; the
  before/after rule comparison is what catches this.
- **Version tags that do not follow semantic versioning** or carry a `v` prefix inconsistently: the
  currency check must compare them correctly and not report false upgrades.
- **Vendor publishes a release then pulls it**: the check reports only published, non-pre-release
  versions.
- **Pin is current but its line leaves support**: for components with a published policy, being on
  the latest patch of an unsupported line still counts as "behind".

## Requirements *(mandatory)*

### Functional Requirements

**Upgrade**

- **FR-001**: Grafana MUST move to the latest 13.2 release. The plan MUST review the 13.0 breaking
  changes against the provisioned dashboards, data sources and plugins. If a breaking change
  affects them and cannot be fixed within this feature, the target falls back to the latest 12.4
  release, and the plan records why.
- **FR-002**: Prometheus MUST move to the latest patch of the current LTS line (3.13 at the time of
  writing). The estate follows LTS lines, which means about one upgrade a year.
- **FR-003**: Alertmanager, blackbox_exporter, Telegraf and node_exporter MUST move to their current
  releases at plan time.
- **FR-004**: The upgrade MUST be deployed through the existing gated pipeline, not by hand on the
  host.

**Single source**

- **FR-005**: Each monitoring component's version MUST be defined once. The duplicate values in the
  monitoring role's defaults MUST be removed, or reduced to a default that the host variables
  override, following the `consolidate-service-versions` precedent.

**No silent loss**

- **FR-006**: Before the upgrade, the operator MUST record: the set of scrape targets and their
  state, the loaded alert rules (count and names), and the list of provisioned dashboards.
- **FR-007**: After the upgrade, the same records MUST be taken and compared. Any target, rule or
  dashboard that is missing or failing blocks completion.
- **FR-008**: The rule validator and the alert-routing validator MUST pass on the new configuration
  before deploy.
- **FR-009**: A test alert MUST reach both Pushover and ntfy after the upgrade.
- **FR-010**: Time-series data recorded before the upgrade MUST still be queryable after it.

**Rollback**

- **FR-011**: Before the upgrade, a one-off snapshot of the monitoring host MUST be taken, and the
  previous pins MUST be recorded in the feature's upgrade record with the rollback steps.
- **FR-012**: After the upgrade is verified, the one-off snapshot MUST be removed.

**Currency**

- **FR-013**: A mechanism MUST report when a pinned monitoring image falls behind its latest
  release or leaves its vendor's support window. The mechanism is a scheduled check that posts to
  ntfy, like the model scout. It compares each pin with the vendor's published releases and, where
  one exists, the support window. It uses no new external tool. For Prometheus, "behind" means not
  on the latest patch of the current LTS line, or the pinned LTS line has left support. A newer
  non-LTS minor is not reported.
- **FR-013a**: The check MUST publish under the `082` publisher contract, with its own account,
  token and topic. Its run MUST be bounded in time, and a failure to reach ntfy or a release source
  MUST be visible in the run's result. It MUST NOT pass silently.
- **FR-014**: The mechanism MUST also cover the service image pins in the services variables,
  reporting only; those upgrades stay manual.
- **FR-015**: The mechanism MUST NOT report when everything is current.

**Verification**

- **FR-016**: The feature's quickstart MUST contain the before/after comparison (FR-006, FR-007),
  the test-alert check (FR-009), and the per-host node_exporter rollout record.
- **FR-017**: One automated guard test in the existing guardrail tests MUST check that each
  monitoring version is defined once, so a later edit cannot reintroduce a duplicate.

### Key Entities

- **Version pin**: the single configured version of one component. Attributes: component, pinned
  version, location.
- **Support window**: a vendor's published end-of-support date for a release line, where one
  exists.
- **Before/after snapshot**: the recorded set of targets, rules (count and names) and dashboards,
  taken before and after the upgrade.
- **Upgrade record**: the previous pins, the new pins, the rollback steps, and the per-host
  node_exporter rollout state, kept in the feature's quickstart.
- **Currency report**: a report naming a component, its pinned version and the newer or supported
  version available.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 6 of 6 components in the table run a version inside the vendor's support window, or
  the latest release where there is no policy.
- **SC-002**: The before/after comparison is recorded, with 0 targets, rules or dashboards missing
  or failing.
- **SC-003**: A test alert reaches both alert channels within 5 minutes of firing.
- **SC-004**: Each monitoring version is set in exactly 1 place.
- **SC-005**: Lowering one pin on a test branch causes the currency mechanism to report it on its
  next run.
- **SC-006**: Over the first 4 weeks after the mechanism is active, it produces 0 reports for pins
  that are already current.
- **SC-007**: Every container host is recorded as running the new node_exporter version.

## Assumptions

- The monitoring host's own backup stays broken until `091`; a one-off hypervisor snapshot is a
  sufficient rollback point for this feature.
- The version table above is a snapshot. Exact target versions are re-checked at plan time and
  the then-current releases are used.
- Grafana plugins, if any are installed, are checked for compatibility with the chosen line as part
  of FR-007; replacing an incompatible plugin is in scope.
- Upgrading the container hosts' Debian base is out of scope (tracked in `improvement-candidates.md`).
  Upgrading the service images themselves is out of scope; each service owns its upgrade. FR-014
  only reports on them.
- Version pins kept in role defaults outside the services and monitoring version blocks are out
  of scope for the check: `jellyfin_exporter_version`, `fail2ban_exporter_version`, `go_version`,
  and the vendored `docker_compose_version`. They are named in research R-10 so they are not
  skipped silently. Moving the exporter pins into the services block is an improvement candidate.
- A brief monitoring outage during the deploy is acceptable. Alerts that would fire during that
  window are not replayed.
- The node_exporter upgrade rides each container host's normal pipeline deploy, one at a time, in
  the same way as the `089` log rotation rollout.

## Dependencies

- **After `089`** (backup and log rotation quick fixes): no technical dependency; ordering only.
- **Not after `091`** (backup coverage and staleness): a one-off snapshot is enough for rollback.
- **Before `092`** (log aggregation), soft: `092` adds Loki to the same stack and should start from
  supported versions.
