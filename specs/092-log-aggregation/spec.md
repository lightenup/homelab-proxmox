# Feature Specification: Log Aggregation and Log-Based Alerting

**Feature Branch**: `092-log-aggregation`

**Created**: 2026-10-24

**Status**: Draft

**Input**: User description: "docs/backlog/092-log-aggregation.md Prompt me". The source is the
backlog item [`docs/backlog/092-log-aggregation.md`](../../docs/backlog/092-log-aggregation.md),
which absorbs [`079`](../../docs/backlog/079-sshd-password-auth-enabled-estate-wide.md) (SSH
password authentication left on across the estate) as FR-015.

## Context

Alerting today is metrics and probes only. A service can wedge and still answer its port without
saturating CPU or disk, and then nothing notices. The only signal of application correctness is
the reverse proxy's 5xx rate, which sees only proxied requests and does not say which service
failed or why. Two open items in `improvement-candidates.md` can only be met with logs:
application-level error alerting, recorded there as the highest-value gap, and login anomaly
alerting. Monitoring specs `011` and `042` both left log aggregation out of scope as a separate
concern. This feature is that concern.

Investigations need it as well. Most backlog items since `064` were diagnosed by collecting
container logs from several hosts by hand and lining up timestamps. ntfy messages expire after
72 hours, so the publishing services' logs are the only lasting record.

The measurements of 2026-10-21, the parts re-checked on 2026-10-24 after `089`–`091` were
delivered, and the owner's decisions are in the backlog item. They are the baseline for this
spec. The figures that shape it:

- **Scope**: the 11 production inventory LXCs and the Proxmox host. Docker runs on 9 of the
  LXCs. The reverse proxy and Jellyfin run natively, and Jellyfin logs to files.
- **Volume**: about 7 MB of logs a day across the estate. Disk is not the constraint. Memory on
  the monitoring host (4 GiB) and on the smallest LXC (`ntfy`, 512 MiB) is.
- **Kernel messages**: an unprivileged LXC cannot read the kernel log, so **OOM kills appear
  only in the Proxmox host's journal**. The existing OOM counter is host-wide and cannot name
  the LXC.
- **Logins**: deploys produce most SSH logins and `sudo` calls, and tailnet traffic reaches LXCs
  with the Proxmox host's address. A login rule has to identify logins by key, not by count or
  by source alone.
- **SSH password authentication** is offered on every host. On the LXCs nothing uses it, only
  because no account happens to have a password. On the Proxmox host it is in use (research R3).

**Tooling is decided by the owner** (2026-10-24): Grafana Loki (monolithic, filesystem storage)
as the store, inside the existing monitoring stack, with Grafana Alloy as the collector. Promtail
reached end of life on 2026-03-02. The alternatives considered are listed in the backlog item.

## Clarifications

### Session 2026-10-24

- Q: Tailnet SSH probably arrives source-NATed to the Proxmox host's address, so the source
  alone cannot tell the owner from the pipeline. Where may the owner's key log in from without
  an alert? → A: From any internal source, meaning the LAN or the Proxmox host (the tailnet
  path). The key is what identifies the owner. An owner-key login from any other source still
  alerts.
- Q: How do LAB-path deploys treat the log pipeline? → A: Production only, the same switch `091`
  used for backups. LAB deploys do not install collectors, the store or log rules, and the set
  of hosts expected to ship logs follows the same switch.
- Q: A credential in a format not on the redaction list reaches the store anyway. What is
  required? → A: Rotate the credential, delete the matching lines from the store by a documented
  procedure, and add the format to the redaction list. The procedure is exercised once during
  delivery.
- Branch: created as `092-log-aggregation` from `main`, carrying the owner's uncommitted backlog
  edits (the revisions to `079`, `092` and `backlog.md`).

### Session 2026-10-24 (plan: login census)

A census of 30 days of accepted SSH logins and `sudo` calls on every host was run during
planning ([research.md](./research.md) R3). It found LAN logins from four addresses, three of
them not named in the repo, and password logins that succeeded on the Proxmox host.

- Q: Several LAN addresses that log in are not in the repo (192.168.1.106, .116). What are
  they? → A: The owner's devices. LAN addresses come from DHCP on the router, so no rule may
  key on a specific LAN address. The allowed list is keyed on user and key. The source is only
  a class: the Proxmox host's address, or anywhere on the LAN.
- Q: Password SSH logins succeeded on the Proxmox host (root from the owner's Mac on
  2026-10-22 and 2026-10-23, `ci` on 2026-10-17). FR-015 would turn password authentication
  off there. → A: Keep password authentication on the Proxmox host. FR-015 covers the LXCs
  only. A password login has no key, so it can never match the allowed list. Every password
  login on the Proxmox host therefore raises the FR-009 alert. Using a password stays
  possible, but every use is visible.
- Plan finding: a LAB-path run can only reach the production monitoring host (`067`). If the
  store were left out of a LAB render, that run would orphan the production store. So the store
  is part of the monitoring stack definition on every path, and FR-017's production-only switch
  covers collectors, log rules and the expected-host set (FR-017 amended).

## User Scenarios & Testing *(mandatory)*

The actor throughout is the homelab operator. The operator owns the estate, deploys through the
gated pipeline, gets alerts on the phone through Pushover and ntfy, and investigates incidents.

### User Story 1 - Search every host's logs in one place (Priority: P1)

The operator investigates an incident from Grafana. One query covers every host and container
and can be filtered by host, service and time, so there is no need to SSH into each LXC. No
credential reaches the store in readable form.

**Why this priority**: Every other story reads from this store. On its own it already replaces
the manual log collection used in recent investigations.

**Independent Test**: Write a unique canary line to the journal of every in-scope host, and one
to a container's output on every Docker host. Within 60 seconds every canary can be found in
Grafana by host and by service.

**Acceptance Scenarios**:

1. **Given** a line written to the system journal of any in-scope host, including the Proxmox
   host, **When** the operator queries Grafana for that host, **Then** the line is found with its
   original timestamp.
2. **Given** a line written by a container on any Docker host, **When** the operator queries by
   service and container, **Then** the line is found and labelled with both.
3. **Given** a line in Jellyfin's log files, **When** the operator queries the `jellyfin` host,
   **Then** the line is found.
4. **Given** a log line that contains a credential in any format listed in FR-005, **When** it is
   stored, **Then** the credential has been replaced by a marker before it left the host, and the
   rest of the line is intact.
5. **Given** a log line 31 days old, **When** the operator searches for it, **Then** it is gone
   (30-day retention).

---

### User Story 2 - An OOM kill on any LXC reaches the phone and names the LXC (Priority: P1)

**Why this priority**: OOM kills are invisible today. The only metric counts them host-wide and
cannot say which LXC was hit, and none has been seen, so this has never been tested.

**Independent Test**: On a named test LXC, OOM-kill a process in a throwaway container with a
small memory limit. One alert arrives on both Pushover and ntfy, naming the LXC and the killed
process.

**Acceptance Scenarios**:

1. **Given** the kernel OOM-kills a process anywhere on the Proxmox host, whether an LXC limit, a
   container limit or system-wide memory caused it, **When** the kernel line reaches the store,
   **Then** a `warning` alert fires within 5 minutes. It names the LXC by name, not by numeric ID,
   and names the process.
2. **Given** several OOM kills inside one alert-grouping window, **When** they alert, **Then** the
   phone gets one notification for the group, listing each LXC.
3. **Given** the log path is down, **When** an OOM kill happens, **Then** the existing host-wide
   OOM counter still raises an alert, without naming the LXC.

---

### User Story 3 - A failing application is noticed even when its port still answers (Priority: P1)

**Why this priority**: This is the gap `improvement-candidates.md` ranks highest. A wedged service
that still answers its health probe is invisible today.

**Independent Test**: Inject a burst of error lines into one service's logs. That service's error
alert fires and no other service's does.

**Acceptance Scenarios**:

1. **Given** a service whose error rate rises above its declared threshold for its declared
   window, **When** the rule is evaluated, **Then** an alert names the service, and its
   summary carries the query that finds the matching lines in Grafana. The notification opens
   Grafana, which is the existing notification link.
2. **Given** a service with no declared log rule, **When** it logs errors, **Then** nothing alerts.
   Rules are opt-in per service and declared next to the service's existing monitoring contract.
3. **Given** a service's normal background error noise over its 7-day baseline, **When** its rule
   is first enabled, **Then** the rule has been tuned so that the baseline does not alert.
4. **Given** the first delivery, **When** the operator lists log rules, **Then** `llm-router`,
   `hermes`, `nextcloud`, `immich` and `ntfy` each have one. Any that has not passed its baseline
   is declared but disabled, and the reason is recorded.

---

### User Story 4 - An unexpected login is noticed (Priority: P1)

**Why this priority**: An unexpected login is a security signal, and nothing surfaces one today.
fail2ban covers failed logins only.

**Independent Test**: SSH into a test host with a key that is not on the allowed list, and an
alert arrives. Run a normal pipeline deploy and log in as the owner from the LAN and from the
tailnet, and nothing alerts.

**Acceptance Scenarios**:

1. **Given** a **successful** SSH login on any in-scope host whose combination of source, user
   and key is not on that host's allowed list, **When** it is logged, **Then** a `warning` alert
   names the host, user, source and key fingerprint.
2. **Given** one of the owner's keys, **When** it logs in from any LAN address or through the
   Proxmox host, **Then** nothing alerts. **When** it logs in from any other source, **Then**
   the alert fires.
3. **Given** `sudo` run by any account other than the expected one (`ansible` on LXCs, `ci` on
   the Proxmox host), **When** it is logged, **Then** a `warning` alert fires.
4. **Given** the deploy pipeline's normal access paths, **When** a full deploy runs, **Then** no
   login or `sudo` alert fires.
5. **Given** any in-scope LXC, **When** a client offers only password authentication, **Then**
   the LXC does not offer password as a method, whether or not the account has a password set.
6. **Given** the Proxmox host, which keeps password authentication, **When** any account logs in
   with a password, **Then** the `warning` alert fires, naming the host, user, source and the
   method `password`.

---

### User Story 5 - Failures of the log pipeline itself are visible (Priority: P2)

Without this, "no log alerts" looks the same as "logs stopped arriving". That silent-green
failure matters more here than elsewhere: a collector without the right permissions starts
cleanly and ships nothing.

**Why this priority**: The P1 stories can be demonstrated without it, but their alerts cannot be
trusted over time without it.

**Independent Test**: Stop the collector on one host, and a warning names that host. Stop the
store, and a critical alert reaches Pushover without going through the store.

**Acceptance Scenarios**:

1. **Given** an in-scope host that has sent no log lines for the declared window, **When** this is
   evaluated, **Then** a `warning` names the host. This includes the Proxmox host.
2. **Given** the store is down, refusing writes, or failing to evaluate or deliver its rules,
   **When** that lasts 5 minutes, **Then** an alert is raised by the metrics system, which does
   not depend on the store.
3. **Given** a collector that has dropped entries, **When** this is evaluated, **Then** an alert
   names the host.
4. **Given** lines discarded by the store's ingestion limits, **When** this is evaluated, **Then**
   it is visible and alerts as MR-004 describes.

---

### Edge Cases

- **Store down**: services are unaffected. No service blocks on logging, slows down or restarts.
  Collectors retry without limit and, when the store returns, catch up from the journal and the
  rotated container logs on disk. Local journal and rotation limits bound the gap, not collector
  memory.
- **One service floods its logs**: the collector throttles each host to a line-rate limit
  without dropping anything (the excess waits on the host's disk). The store's per-stream and
  global limits keep one stream from using up the others' share. Lines the store discards are
  counted and alerted (MR-004).
- **Multi-line stack traces**: in the first delivery each line is its own entry. Joining
  multi-line traces is deferred (plan follow-up). Redaction applies to every line, so it covers
  every line of a trace.
- **Long outage**: lines older than the store's backfill limit (one week by default) are refused
  on catch-up. This is accepted as the limit of backfill.
- **LXC rebuilt**: the host keeps its labels, so queries and rules do not depend on container
  IDs. The ID-to-name mapping for OOM alerts comes from the same source as the inventory.
- **Container created before `089`'s log rotation**: its logs are not rotated until it is
  recreated. Collection is not switched on for it until then (FR-003).
- **LAB-path deploys** (`067`, `072`): the LAB path can reach production addresses. A LAB deploy
  installs no collector and renders no log rule (FR-017). It also MUST NOT remove or change a
  running production store, collector or rule set.
- **Monitoring host rebuilt**: it starts with an empty store and full collection. Lines older
  than the rebuild are not recovered beyond what the hosts still hold on disk.
- **Credential slips past redaction**: handled by the rotate-purge-extend procedure (FR-016).
- **Owner's normal access**: logs in with one of the owner's keys from a LAN address, which is
  DHCP-assigned and changes, or through the Proxmox host. Neither alerts. An owner-key login
  from anywhere else does.
- **Password login on the Proxmox host**: still possible by owner decision. Every one alerts.

## Requirements *(mandatory)*

### Functional Requirements

**Store and collection**

- **FR-001 — Store.** The log store MUST run inside the existing monitoring stack on the
  `monitoring` LXC, alongside the metrics system. Its version and the collector's MUST each be
  pinned exactly once: the store's next to the other monitoring-stack pins, and the collector's
  next to the shared `node_exporter` pin, because it runs on every host. Both are covered by
  `090`'s weekly version-currency check.
- **FR-002 — Collection.** Every in-scope host MUST ship its system journal. On the Proxmox host
  that includes kernel messages. Docker hosts also ship every container's stdout and stderr.
  Services that write their application log to a file of their own also ship that file:
  Jellyfin, and Nextcloud, whose application errors reach only its own log file (research R8).
  Every entry is labelled with environment, host, service and, for containers, container name.
  Labels MUST stay low-cardinality, so request IDs, user names and paths are not labels.
- **FR-003 — Rotated logs only.** Collection MUST NOT be switched on for a container whose logs
  are not yet rotated by `089`'s settings. The collector's deploy MUST check this and fail if any
  running container lacks rotation. The rotated files are part of the outage buffer (FR-011).
- **FR-004 — Store limits.** The store's memory use MUST be bounded explicitly and MUST NOT rely
  on defaults sized for a larger machine. That covers write-ahead-log replay, caches, query
  limits and a container memory limit. Retention MUST be enforced at **30 days**. Ingestion
  limits MUST apply per stream and in total. The store MUST also support deleting lines that
  match a query, which FR-016 uses.
- **FR-005 — Redaction (constitution II).** Credentials MUST be removed **on the host, before
  shipping**, by explicit patterns. At minimum these formats, all used in this estate:
  - `Authorization:` header values (`Bearer …`, `PVEAPIToken=…`);
  - ntfy tokens (`tk_` followed by 29 alphanumerics);
  - LiteLLM keys (`sk-…`);
  - Tailscale keys (`tskey-…`);
  - `?auth=` and `token=` query values;
  - passwords in URLs (`scheme://user:pass@`);
  - `*_TOKEN=`, `*_SECRET=`, `*_PASSWORD=` and `*_KEY=` assignments.

  The list is data, so adding a format is a one-line change. A generic secret scanner MAY run as
  a second layer, but is not relied on.
- **FR-006 — Search.** The store MUST be a provisioned Grafana data source. Log panels extend
  the existing dashboards where they fit, for example login panels in the security overview next
  to fail2ban. A new dashboard is added only where no existing one fits (constitution IV).

**Alert rules**

- **FR-007 — OOM rule.** One estate-wide `warning` rule MUST alert on every kernel OOM kill in
  the Proxmox host's journal, whether an LXC limit, a container limit or system-wide memory
  caused it. It names the LXC and the process. A metric rule on the existing host-wide OOM
  counter is added as the backstop for when the log path is down.
- **FR-008 — Per-service error rules.** Error rules MUST be declared per service in the same
  place as the service's monitoring contract. Each rule declares what counts as an error line,
  the threshold, the window and the severity. Rules MUST be validated at deploy, and in CI if
  feasible, the same way metric rules are. The first delivery covers `llm-router`, `hermes`,
  `nextcloud`, `immich` and `ntfy`. A service that writes its application errors only to its own
  log file, not to the journal or its container output, MUST have that file collected (FR-002).
  Each rule is enabled only after its 7-day baseline (SC-004). A service that does not
  pass within the delivery stays declared but disabled, and the reason is recorded.
- **FR-009 — Login rules.** An allowed list of (user, key fingerprint, source class) MUST be
  declared once for the LXCs and once for the Proxmox host:
  - LXCs: `root` and `ansible` with the deploy key, from the Proxmox host; the owner's keys from
    any internal source.
  - Proxmox host: `ci` with the CI runner's key, from the LAN; the owner's keys from any
    internal source.

  The source is a class, never a single LAN address, because LAN addresses are DHCP-assigned.
  "Internal source" means any LAN address, the Proxmox host's address (through which tailnet
  traffic to the LXCs arrives), or the tailnet itself (for tailnet SSH to the Proxmox host). A successful SSH login that matches no entry alerts. A password login has no
  key, so it never matches. `sudo` by an account other than `ansible` (LXCs) or `ci` (Proxmox
  host) alerts. There is no time-of-day rule. The LAN range and the Proxmox host's address come
  from where the estate's topology lives: `081`'s source if it has landed, otherwise the
  existing group variables, moving with `081` later. Key fingerprints are public values, not
  secrets.
- **FR-010 — Collector limits.** The collector MUST run under a memory limit sized from
  measurement on `ntfy` (512 MiB), so it cannot push a small LXC's service into OOM. It needs
  read access to the journal and, on Docker hosts, to the container runtime. That access is
  root-equivalent and is recorded in the plan as an accepted risk.
- **FR-011 — No back-pressure, bounded loss.** Log collection MUST NOT be able to block, slow
  down or restart a service, so a logging driver inside the container runtime is not allowed.
  The collector MUST NOT drop entries after a fixed number of retries. It retries without limit
  and relies on the journal and the rotated logs on disk as its buffer.
- **FR-012 — Pipeline self-monitoring.** The metrics system MUST scrape the store and evaluate
  these alerts itself, not through the store: store liveness; write failures and discarded
  lines; rule evaluation failures, missed evaluations and failures to deliver to the alert
  router; retention runs; collectors that dropped entries; and hosts that stopped shipping.

**Boundaries and state**

- **FR-013 — Nothing leaves the estate.** Log data stays on the `monitoring` LXC. The store is
  not exposed through the reverse proxy. Grafana is the only interface, and its access stays as
  it is today.
- **FR-014 — State.** Collector and store configuration MUST be declarative and re-applied on
  every deploy. Log data is not backed up.
- **FR-015 — SSH password authentication off on the LXCs (from `079`).** Every in-scope LXC MUST
  turn off SSH password authentication by configuration, and the repo MUST assert this so it
  cannot regress. The console path from the Proxmox host (`pct enter`) stays the recovery route.
  The Proxmox host keeps password authentication by owner decision (Clarifications). Every
  password login there alerts through FR-009. The CI runner and the NAS are outside scope and
  are not changed.
- **FR-016 — Leaked-credential procedure.** A documented procedure MUST cover a credential found
  in the store: rotate the credential, delete the matching lines from the store, and add the
  format to the FR-005 list. The procedure is exercised once during delivery (SC-008).
- **FR-017 — Production only.** Collectors and log rules MUST be installed by production deploys
  only, using the same switch `091` uses for backups. The set of hosts expected to ship logs
  (MR-002) MUST follow the same switch. The store is part of the monitoring stack's definition
  on every path, so a LAB-path run cannot orphan it. A LAB-path deploy MUST NOT remove or change
  a running production store, collector or rule set.

### Key Entities

- **Log stream**: entries that share one label set (environment, host, service, container).
  Ingestion limits apply per stream and per host, and retention applies to all streams.
- **Collector**: one per in-scope host. It reads the journal, container logs where present and
  declared log files, then redacts, labels and ships.
- **Log rule**: an alert rule evaluated against stored logs. It is either estate-wide (OOM,
  login, `sudo`) or declared per service (error rate), and carries a severity like every other
  rule.
- **Allowed login**: a (source, user, key fingerprint) expected to SSH into a given host.
- **Redaction pattern**: a credential format removed before shipping.
- **Expected host**: an in-scope production host that is expected to ship logs. It is the basis
  for the "host stopped shipping" alert.

## Monitoring Requirements

- **MR-001**: The store's liveness alert is `critical` and is evaluated by the metrics system
  (FR-012).
- **MR-002**: An expected host with no log lines for the declared window raises `warning`.
- **MR-003**: Rule evaluation failures, and failures to deliver to the alert router, raise
  `warning`. A rule that cannot run must not look like a rule that passes.
- **MR-004**: Discarded lines raise `info` whenever they occur and `warning` when they are
  sustained. Causes include rate limits, stream limits, lines that are too long and lines that
  are too old.
- **MR-005**: Collector drops raise `warning` and name the host.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A scripted canary check writes one line to the journal of every in-scope host and
  one to a container on every Docker host. 100% of them are found in Grafana within 60 seconds,
  and the result is recorded per host.
- **SC-002**: A redaction drill logs one synthetic credential in each FR-005 format on a test
  host. A search finds none of them and finds the marker in every line.
- **SC-003**: An OOM drill on a test LXC produces one alert on both Pushover and ntfy within
  5 minutes, naming the LXC and the process. With the store stopped, the same drill produces the
  host-wide backstop alert.
- **SC-004**: Each per-service error rule is enabled only after running against at least 7 days
  of that service's logs without alerting. An injected error burst then fires that service's
  alert and no other.
- **SC-005**: A login with a key not on the allowed list alerts, and so does a password login on
  the Proxmox host. A full pipeline deploy, and owner logins from the LAN and from the tailnet,
  produce no login or `sudo` alert. On 100% of in-scope LXCs, a password-only connection attempt
  is refused and key authentication is the only method offered.
- **SC-006**: Stopping the collector on one host raises MR-002 for that host only. Stopping the
  store raises MR-001 on Pushover. In both cases no service restarts or shows added latency.
  After a 30-minute store outage, every line logged during the outage is present once the store
  is back.
- **SC-007**: After 14 days in production, the following are recorded: ingestion per host, disk
  used by the store, peak memory of the store and of the collectors (on `ntfy` in particular),
  and the `monitoring` LXC's remaining memory headroom. FR-004's limits and retention are then
  confirmed or changed.
- **SC-008**: The FR-016 procedure is exercised once on a synthetic credential that the FR-005
  list does not cover: the matching lines are no longer found, and after the format is added a
  new line is redacted.
- **SC-009**: After a LAB-path deploy, the production store, collectors, log rules and
  pipeline alert rules are unchanged, and the lab hosts raise no MR-002 alert.

## Assumptions

- The measurements and decisions in the backlog item (2026-10-21, updated 2026-10-24) are still
  current. Anything that has changed by plan time is re-measured there.
- The collector can be installed from its vendor's pinned release package (`.deb`, verified
  against the published checksums) on Debian 12 (LXCs) and Debian 13 (Proxmox host). No
  third-party package repository is added to the hypervisor (research R5).
- Tailnet SSH to an LXC arrives source-NATed to the Proxmox host's address. Verified in plan:
  the host's Tailscale preferences show `NoSNAT: false` (research R3).
- The kernel's OOM lines carry the LXC's numeric ID in a standard Proxmox cgroup path
  (`/sys/fs/cgroup/lxc/<vmid>` exists on the host, research R6). The OOM drill verifies this.
- The pipeline's access paths and the owner's keys were confirmed in plan by a census of
  30 days of accepted logins and `sudo` users per host (research R3).
- Warning and critical alerts already reach both Pushover and ntfy through the existing alert
  routing (`082`). No routing change is needed.
- Grafana's access is owner-only today (no self-sign-up). Logs that contain user activity, for
  example Nextcloud file names, are acceptable there.

## Out of Scope

- The Mac and client devices on the LAN.
- The Synology NAS, unless plan research finds it can forward its logs with no change beyond its
  own settings. If so, it becomes a later story.
- Failed-login alerting (fail2ban covers it) and intrusion detection.
- Tracing and application performance monitoring.
- Shipping logs off the estate, or to any hosted service.
- Reverse-proxy access logs. Its runtime log is collected through the journal. Access logs may be
  revisited after SC-007.
- Backing up log data or the `monitoring` LXC (`091` declared it rebuildable).
- A per-LXC OOM metric. The host journal is the source instead.
- A time-of-day login rule.
- Log pipeline components in the lab (FR-017).

## Dependencies

- **Met**: `089` (Docker log rotation), `090` (current Grafana and Prometheus plus the
  version-currency check), and `091` (Proxmox host scraped through the host playbook, which the
  collector reuses there).
- **Absorbs** `079` (SSH password authentication) as FR-015. `079` is closed as merged into
  `092`.
- **`081`** (externalise production topology, not started): FR-009's addresses move with it.
- **`067` / `072`**: the LAB path reaches production addresses. Drills run on a named test LXC,
  and FR-017 keeps LAB deploys away from the production pipeline.
- **`082`**: log alerts reach ntfy through its existing alerts publisher. Nothing changes there.
- **Closes** "Application-level error/log alerting" and "Login anomaly alerting" in
  `improvement-candidates.md`. **Amends** `042`'s out-of-scope entry for log aggregation.
- **Plan inputs**: the backlog item's Research notes and Open Questions (outage buffer depth,
  how container logs are read, which role installs the collector, error-line definitions per
  service, login census, CI validation of log rules, where the SSH setting is carried).
