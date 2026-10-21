# Feature Specification: log aggregation and log-based alerting

**Feature Branch**: `089-log-aggregation`
**Created**: 2026-10-21
**Status**: Draft — ready for `/speckit-specify`, raised 2026-10-21. Nothing blocks it; best after
[`091`](./091-monitoring-stack-version-currency.md). Assumptions were checked against the repo, upstream docs and the live estate on 2026-10-21 (see
[Measured state](#measured-state-2026-10-21) and [Research notes](#research-notes-for-speckit-plan)).
**Input**: Collect the logs of every host the estate manages into one store next to Prometheus,
make them searchable in Grafana, and alert on them through the existing Alertmanager → Pushover +
ntfy path. Four capabilities in the first delivery: collection and search, OOM-kill alerts,
per-service error alerts, and login anomaly alerts. **Proposed** tooling is Grafana Loki
(monolithic, filesystem storage) with Grafana Alloy as the collector. `/speckit-plan` confirms
that choice (R-001), which the research below already narrows.

---

## Why this exists

Alerting today is metrics and probes only: node_exporter on every LXC, blackbox endpoint probes,
the per-service `monitoring_contract` rules, and fail2ban counts on three hosts. A service that has
wedged but still answers its port and does not saturate CPU or disk is invisible. The only signal
of application correctness is Caddy's 5xx rate (`host_vars/reverse_proxy.yml`), which sees only
requests that go through Caddy and says nothing about which service, or why.

Two open items in [`improvement-candidates.md`](./improvement-candidates.md) need logs and
nothing else:

- **Application-level error/log alerting**, recorded there as the "highest-value gap alongside
  backup monitoring": error-rate spikes, stack traces and OOM kills per service.
- **Login anomaly alerting**: successful SSH from an unexpected source, unexpected `sudo`,
  off-hours logins.

Monitoring specs `011` and `042` both put log aggregation out of scope as "a separate
architecture concern". This is that concern.

Investigations need it too. Most backlog items since `064` were diagnosed by hand, collecting
container logs on several LXCs and lining up timestamps (`075`, `076`, `078`, `080`). Messages on
ntfy expire after 72 h (`082` FR-013); the logs of the services that published them are the only
lasting record.

## Measured state (2026-10-21)

Read-only, from the PVE host (`pct exec`), Prometheus and the repo.

| What | Finding | Consequence for this spec |
|---|---|---|
| Hosts | 11 LXCs in the PROD inventory (`services` group) plus the PVE host. `homeassistant` exists in Terraform but is **not in the inventory** and runs nothing | Scope is those 11 LXCs and the PVE host |
| Docker | Runs on 9 LXCs. **`proxy` (Caddy from apt) and `jellyfin` (apt) have no Docker** | Collection cannot assume Docker; Jellyfin logs to `/var/log/jellyfin/*.log` |
| Docker log rotation | **None anywhere.** No `daemon.json` (`docker_daemon_options: {}`), no compose `logging:`. Every container uses `json-file` with no `max-size`. Current json logs: nextcloud 245 MB, financial-scenario 149 MB, market-model 73 MB, immich 57 MB, eurooffice 57 MB | A disk-fill risk today, independent of this feature. FR-003 |
| Log volume | Journals 12–48 KB/day per LXC. Docker output ~6.3 MB/day in total (monitoring 2.8 MB, hermes 1.1 MB). **About 7 MB/day for the estate** | Storage is not the constraint: 14 days is about 100 MB before compression. Upstream sizes monolithic Loki for up to ~20 GB/day |
| Journald | Persistent (`/var/log/journal`) on every LXC and on the PVE host; 16–122 MB per LXC, 95 MB on PVE. No repo management of `journald.conf` | The journal can act as the buffer while the store is down (FR-011) |
| Kernel messages in LXCs | **Zero** kernel lines in any LXC's journal over 7 days. An unprivileged LXC cannot read the kernel ring buffer | **OOM kills are visible only in the PVE host's journal.** US-2 reads the host |
| OOM history | `node_vmstat_oom_kill` (already scraped) is 0 on every LXC over 30 days. Inside an LXC this counter is **host-wide** (LXCFS does not virtualise `/proc/vmstat`), so it cannot say which LXC | A metric backstop exists, but only the host's kernel log names the container |
| PVE host | PVE 9.2.3 on **Debian 13**. **No node_exporter, not scraped by Prometheus.** Managed by `playbooks/host_proxmox.yml` (`proxmox_host`, `tailscale_host`) | The collector would be the first agent on the hypervisor; nothing monitors it yet |
| Monitoring LXC | 2 cores, 4 GiB RAM, 32 GB rootfs (all data on rootfs), 25.9 GB free. Minimum available memory over 7 days: 90%. Prometheus TSDB 1.1 GB, 15 days | Disk needs no resize. Memory is the budget to watch (FR-004) |
| Smallest LXCs | `ntfy` 512 MiB (minimum 7-day headroom ~80%), `proxy` 1 GiB | The collector's fixed cost matters most here (FR-010) |
| Grafana | 12.3.1 live (security support ended 2026-08-19), pinned in `group_vars/monitoring/vars.yml`. One provisioned data source; each provisioning file has its own copy task | FR-006; upgrade in [`091`](./091-monitoring-stack-version-currency.md) |
| Alertmanager grouping | `group_by: ['alertname', 'severity']` | Alerts are grouped by rule, not by host |
| SSH logins (7 days) | Accepted logins on hermes 191, llm-router 38, monitoring 32, ntfy 22, proxy 7, others 0. `sudo` on hermes 2,679, llm-router 444, ntfy 249, proxy 74 | Deploys produce most logins and `sudo`. A login rule has to tell them apart by identity, not by count |
| Access paths (repo) | The pipeline runs on `pi-runner`, SSHes to `pve` as `ci`, and from `pve` into each LXC as `root` (deploy key injected via `pct exec`) or `ansible` (passwordless `sudo`). The owner logs in with a personal key. Tailscale SSH is off; tailnet traffic to LXCs is subnet-routed by `pve` and probably source-NATed to `pve`'s address | Source address alone cannot separate the pipeline from the owner on the tailnet. FR-009 uses source **and** key |
| Monitoring backup | Has never succeeded in its log (since 2026-07-09): the NAS mount is disabled | Out of scope here; raised as [`090`](./090-backup-coverage-and-staleness.md). FR-014 does not rely on it |
| Rule validation | `promtool check rules` runs only at deploy, on the monitoring host. CI does not lint rule files (pre-commit excludes `roles/*/files` and `templates`). Nothing tests `monitoring_contract` | Log rules need their own validation (FR-008) |

## Decisions recorded (2026-10-21)

| decision | choice | why |
|---|---|---|
| Tooling | **Proposed: Loki (monolithic, filesystem, TSDB index, schema v13) + Alloy.** Confirmed in `/speckit-plan` (R-001) | Loki is a native Grafana data source, and its ruler posts to the Alertmanager already deployed. Alloy is Grafana's supported collector. **Promtail reached EOL on 2026-03-02 and was removed in Loki 3.7.3**, so it is not an option. VictoriaLogs is the serious alternative (lighter, has a disk-size cap) but adds vmalert, a third-party Grafana plugin and another query language. At ~7 MB/day, Loki's weight is a memory-configuration question, not a capacity one. |
| Where the store runs | **In `monitoring_stack`**, a sixth container on the `monitoring` LXC | Constitution IV, "consolidate before adding". Disk has room (25.9 GB free for ~100 MB of logs). Memory needs explicit limits (FR-004). |
| Alert delivery | **Existing Alertmanager**, existing severity routes | Log alerts reach Pushover and ntfy exactly like metric alerts. No new receiver. |
| Hosts in scope | **The 11 inventory LXCs and the PVE host** | The PVE host is the only place OOM kills are logged (Measured state), and it is where the pipeline and the owner log in. |
| Docker log rotation | **In scope, done first** (FR-003) | Unbounded json-file logs are an existing risk, and the collector reads them. Rotation applies only to containers created afterwards, so it has to be rolled out deliberately. |
| The Mac | **Out of scope** | Managed from the `local-llm` repo, employer-managed, and its logs can contain prompt metadata. |
| Log data backup | **None** | Logs are diagnostic and bounded by retention, as `082`'s message cache is. The monitoring backup it would ride on is probably not working (Measured state). |
| First delivery | **All four capabilities** (US-1 to US-4) | Collection alone has no consumer (constitution IV). Each alert class is a consumer that justifies it. |

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Search every host's logs in one place (Priority: P1)

The owner investigates an incident from Grafana: one query across all hosts and containers,
filtered by host, service and time, instead of SSHing into each LXC.

**Independent Test**: Write a unique canary line to the journal of every in-scope host, and to
one container's stdout on every Docker host. Within 60 s each canary can be found in Grafana by
host and by service.

**Acceptance Scenarios**:
1. **Given** a line written to the systemd journal of any in-scope host, including the PVE
   host, **When** the owner queries Grafana for that host, **Then** the line is found with its
   original timestamp.
2. **Given** a line written by a Docker container on any Docker host, **When** the owner queries
   by service and container, **Then** the line is found and labelled with both.
3. **Given** a line in Jellyfin's log files, **When** the owner queries the `jellyfin` host,
   **Then** it is found.
4. **Given** a log line that contains a credential in any format listed in FR-005, **When** it
   is stored, **Then** the credential is replaced by a marker before it leaves the host, and the
   rest of the line is intact.

### User Story 2 - An OOM kill on any LXC reaches the phone, naming the LXC (Priority: P1)

**Independent Test**: On a test LXC, OOM-kill a process in a throwaway container with a small
memory limit. The phone receives one alert naming the LXC and the killed process, on both
Pushover and ntfy.

**Acceptance Scenarios**:
1. **Given** the kernel OOM-kills a process anywhere on the PVE host, whether it hit an LXC's
   memory limit, a Docker limit or system-wide memory, **When** the kernel line reaches the
   store, **Then** an alert fires within 5 minutes. It names the LXC (from the line's
   `task_memcg=/lxc/<vmid>/…` path, mapped to the LXC's name) and the process.
2. **Given** several OOM kills within the grouping window, **When** they alert, **Then** the
   phone gets one notification per alert group (Alertmanager groups by `alertname`), listing
   each LXC.
3. **Given** the log path is down, **When** an OOM kill happens, **Then** the existing
   `node_vmstat_oom_kill` counter still raises a host-wide alert without naming the LXC
   (FR-007).

### User Story 3 - A failing application is noticed even when its port still answers (Priority: P1)

**Independent Test**: Inject a burst of error lines into one service's logs. That service's error
alert fires. No other service's alert fires.

**Acceptance Scenarios**:
1. **Given** a service whose error rate rises above its declared threshold for its declared
   window, **When** the rule is evaluated, **Then** an alert names the service and includes a
   Grafana link to the matching lines.
2. **Given** a service with no log rule declared, **When** it logs errors, **Then** nothing
   alerts. Rules are opt-in per service, declared next to its existing `monitoring_contract`.
3. **Given** the normal background error noise of a service over its baseline period, **When**
   its rule is first enabled, **Then** the rule has been tuned so that baseline does not alert
   (SC-004).

### User Story 4 - An unexpected login is noticed (Priority: P1)

**Independent Test**: SSH into a test host with a key that is not on the allowed list: an alert
arrives. Run a normal pipeline deploy: nothing alerts.

**Acceptance Scenarios**:
1. **Given** a **successful** SSH login on any in-scope host whose (source, user, key
   fingerprint) is not on that host's allowed list, **When** it is logged, **Then** a `warning`
   alert names the host, user, source and key fingerprint.
2. **Given** `sudo` run by any account other than the expected one (`ansible` on LXCs, `ci` on
   the PVE host), **When** it is logged, **Then** an alert fires.
3. **Given** the deploy pipeline and the owner's normal access paths, **When** they log in,
   **Then** nothing alerts. Failed logins stay with fail2ban and its existing dashboard, not here.

### User Story 5 - The log pipeline's own failures are visible (Priority: P2)

Without this, "no log alerts" cannot be told apart from "logs stopped arriving", the silent-green
failure `064` SC-013 exists to catch. It matters more here than elsewhere: a collector missing a
group membership starts cleanly and ships nothing.

**Independent Test**: Stop the collector on one host: a warning names that host. Stop the store:
a critical alert reaches Pushover through Prometheus, not through the store.

**Acceptance Scenarios**:
1. **Given** an in-scope host that has sent no log lines for the declared window, **When**
   that is evaluated, **Then** a `warning` names the host. This includes the PVE host, which
   has no node_exporter to show it is up.
2. **Given** the store down, refusing writes, or failing to evaluate or deliver rules, **When**
   that persists for 5 minutes, **Then** Prometheus raises an alert from the store's own
   metrics. It must not depend on the store's ruler.
3. **Given** a collector that gave up and dropped entries, **When** that is evaluated, **Then**
   an alert names the host.

### Edge Cases

- **Store down**: services carry on unaffected. No container blocks on logging, and none
  restarts. Collectors retry without a limit and read on from the journal and the rotated
  json-file logs on disk when the store returns. The gap is bounded by local journal and
  rotation limits, not by collector memory (FR-011).
- **One service floods its logs**: per-stream and per-host ingestion limits stop it from using
  up the others' share. Discarded lines are counted (`loki_discarded_*{reason}`) and alerted.
- **Multi-line stack traces**: kept as one entry where the collector can tell, and redaction
  (FR-005) applies to every line of them.
- **Lines older than a week after a long outage**: Loki rejects samples older than
  `reject_old_samples_max_age` (default 1 week). Accepted as the limit of backfill.
- **LXC rebuilt**: the host keeps its labels, so queries and rules do not depend on container
  IDs. The VMID-to-name mapping for US-2 comes from the same source as the inventory.
- **LAB-path deploys** (`067`, `072`): a LAB monitoring deploy must not wipe PROD log rules or
  collector config. The `072` guards check inputs (inventory size, contracts), so they cover the
  ruler file as long as it is rendered from the same contracts.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001 — Store.** The log store MUST run in `monitoring_stack` on the `monitoring` LXC, as a
  container in its compose file. Its image is pinned in `group_vars/monitoring/vars.yml` next to
  `prometheus_version` and `grafana_version`.
- **FR-002 — Collection.** Every in-scope host MUST ship its systemd journal. The PVE host's
  journal includes kernel messages. Docker hosts also ship every container's stdout and stderr.
  `jellyfin` also ships `/var/log/jellyfin/*.log`. Every entry is labelled with environment,
  host, service and, for containers, container name. Labels MUST be low-cardinality: no request
  IDs, users or paths.
- **FR-003 — Docker log rotation.** Every Docker host MUST set `json-file` rotation
  (`max-size`, `max-file`) through `docker_daemon_options`. Rotation applies only to containers
  created afterwards, so the rollout recreates each service's containers in its normal deploy,
  and the oversized existing logs are dealt with once. This lands before collection is switched
  on.
- **FR-004 — Store limits.** Memory MUST be bounded explicitly, not left to defaults that assume
  a larger machine: the WAL replay ceiling (default 4 GB, the whole LXC), the embedded caches
  (switched on automatically at 100 MB each), and query limits. There is also a container
  memory limit. Retention MUST be enforced and recorded (proposal: 30 days). It needs the
  compactor with `retention_enabled`, `delete_request_store` and `retention_period`; without
  those, Loki keeps everything. Per-stream and global ingestion limits are set. Prometheus's
  memory and disk headroom after the change is measured and recorded (SC-007).
- **FR-005 — Redaction (constitution II).** Credentials MUST be removed **on the host, before
  shipping**, by explicit patterns. At minimum, the formats this estate uses:
  - `Authorization:` header values (`Bearer …`, `PVEAPIToken=…`);
  - ntfy tokens (`tk_` + 29 alphanumerics);
  - LiteLLM keys (`sk-…`);
  - Tailscale keys (`tskey-…`);
  - `?auth=` and `token=` query values;
  - passwords in URLs (`scheme://user:pass@`, as in LiteLLM's `DATABASE_URL`);
  - `*_TOKEN=`, `*_SECRET=`, `*_PASSWORD=` and `*_KEY=` assignments (Domeneshop, Jellyfin and
    others print config as `KEY=value`).

  The list is data, so a new format is a one-line change. A gitleaks-based filter
  (`loki.secretfilter`, GA in Alloy 1.20) MAY run as a second layer. It is not relied on, as
  upstream documents both false positives and false negatives. A drill proves every listed
  format (SC-002).
- **FR-006 — Search.** A Grafana data source for the store MUST be provisioned from a file next
  to `provisioning/datasources/prometheus.yml`, with its own copy task. Before any new dashboard
  is added, extend the existing ones where they fit (constitution IV). For example, login panels
  belong in `security-overview.json`, which already shows fail2ban.
- **FR-007 — OOM rule.** One estate-wide log rule MUST alert at `warning` on kernel OOM kills in
  the PVE host's journal. It matches the `oom-kill:constraint=` line, which is written for every
  kind of OOM (cgroup-limit OOMs are logged as "Memory cgroup out of memory", not "Out of
  memory"), and takes the LXC from `task_memcg`. A metric rule on `node_vmstat_oom_kill`
  (host-wide, already scraped) is added as the backstop when the log path is down.
- **FR-008 — Per-service error rules.** Error rules MUST be declared per service in its
  `host_vars`, next to `monitoring_contract`, so a service's metric and log alerts live in one
  place. Each rule declares the selector for an error line, the threshold, the window and the
  severity. The rules are rendered into the store's ruler directory, the same way
  `service_alerts.yml.j2` renders metric rules. They are validated at deploy (the LogQL
  counterpart of `validate_alerts.yml`'s `promtool` step), and in CI if feasible. The first
  delivery MUST cover at least `llm-router` and `hermes`, the services whose failures were
  diagnosed by hand from logs.
- **FR-009 — Login rules.** For each host, an allowed list of (source, user, key fingerprint)
  MUST be declared once:
  - LXCs: `root` and `ansible` from `pve` with the deploy key, and the owner's key.
  - PVE host: `ci` from `pi-runner`, and the owner's key.

  Successful SSH logins not on the list alert. `sudo` by an account other than `ansible` (LXCs)
  or `ci` (PVE host) alerts. Addresses come from where topology lives
  ([`081`](./081-externalise-prod-topology.md)). Key fingerprints are public values, not
  secrets, but are still kept out of the repo if `081` moves topology out.
- **FR-010 — Collector limits.** The collector MUST run under a memory limit (systemd
  `MemoryMax=` or equivalent) sized from measurement on `ntfy` (512 MiB), so it cannot push a
  small LXC's service into OOM. It needs read access to the journal (`adm` and `systemd-journal`
  groups) and, on Docker hosts, to the Docker socket, which is root-equivalent. That access is
  recorded as an accepted risk in the plan.
- **FR-011 — No back-pressure on services, bounded loss.** Collecting MUST NOT be able to block,
  slow down or restart a service. The Docker Loki logging driver is not allowed: upstream
  documents it deadlocking the Docker daemon. The collector does not give up after its default
  10 retries (about 8–9 minutes, then entries are dropped). It retries without a limit and
  relies on the journal and rotated json-file logs on disk as the buffer. Alloy's own WAL is
  experimental and is not used.
- **FR-012 — Pipeline self-monitoring.** The store MUST be scraped by Prometheus, and these
  alerts are evaluated by Prometheus, not by the store:
  - store liveness;
  - write failures and discarded lines (`loki_discarded_samples_total{reason}`);
  - ruler evaluation failures, missed iterations, and notification errors or drops to
    Alertmanager;
  - compactor retention runs;
  - collectors that dropped entries (`loki_write_dropped_entries_total`);
  - a host that stopped shipping.
- **FR-013 — Nothing leaves the estate.** Log data stays on the `monitoring` LXC. The store is
  not routed through Caddy. Grafana is the only interface, and Grafana's access stays as it is
  today.
- **FR-014 — State.** Collector and store configuration MUST be declarative, rebuilt on every
  deploy. Log data is not backed up (Decisions). A rebuilt `monitoring` LXC starts with an empty
  log store and full collection.

### Key Entities

- **Log stream**: entries sharing one label set (environment, host, service, container).
  Retention and ingestion limits apply per stream or per host.
- **Collector**: one per in-scope host. It reads the journal, Docker logs where present and
  named files where declared, then redacts, labels and ships.
- **Log rule**: an alert rule evaluated by the store, either estate-wide (OOM, login) or
  declared per service (error rate). It carries a `severity` like every other rule.
- **Allowed login**: a (source, user, key fingerprint) expected to SSH into a given host
  (FR-009).
- **Redaction pattern**: a credential format removed before shipping (FR-005).

## Monitoring Requirements

- **MR-001**: The store's liveness alert is `critical` and is evaluated by Prometheus (FR-012).
- **MR-002**: A host with no log lines for the declared window raises `warning`.
- **MR-003**: Ruler evaluation failures, and failures to deliver to Alertmanager, raise
  `warning`. A rule that cannot run is not a rule that passes.
- **MR-004**: Discarded lines (rate limits, stream limits, line too long, too old) raise `info`
  when they happen at all, and `warning` when they are sustained.
- **MR-005**: Collector drops raise `warning` naming the host.

## Success Criteria *(mandatory)*

- **SC-001**: A scripted canary check writes one line to the journal of every in-scope host, and
  one to a container on every Docker host. Every one is found in Grafana within 60 s. Results
  are recorded per host. This is also the test that each collector has the group memberships
  it needs, since a missing one fails silently.
- **SC-002**: A redaction drill logs one synthetic credential of every FR-005 format on a test
  host. A query finds none of them, and finds the marker in each line.
- **SC-003**: An OOM drill on a test LXC produces one alert on both Pushover and ntfy within
  5 minutes, naming the LXC and the process. With the store stopped, the same drill produces the
  host-wide metric alert.
- **SC-004**: Each per-service error rule is enabled only after it has been run against at least
  7 days of that service's logs with no alert. An injected error burst then fires that service's
  alert and no other.
- **SC-005**: An SSH login with a key not on the allowed list alerts. A full pipeline deploy, and
  the owner's normal access, produce no login or `sudo` alert.
- **SC-006**: Stopping the collector on one host raises MR-002 for that host only. Stopping the
  store raises MR-001 on Pushover. In both cases no service restarts and none shows added
  latency. After the store returns, the lines logged during a 30-minute outage are present.
- **SC-007**: After 14 days, the following are recorded: measured ingestion per host, disk used
  by the store, the store's and the collectors' peak memory (on `ntfy` in particular), and the
  `monitoring` LXC's remaining memory headroom. FR-004's retention and limits are then confirmed
  or changed.
- **SC-008**: After FR-003, no container on any Docker host has a json-file log larger than the
  configured `max-size` × `max-file`.

## Assumptions

- The collector can be installed from Grafana's apt repository on Debian 12 (LXCs) and Debian 13
  (PVE host) and run as a systemd service. No Proxmox-specific guidance exists; the plan records
  the choice to add a third-party repository to the hypervisor.
- Tailnet SSH to an LXC arrives source-NATed to `pve`'s address (Tailscale's subnet-router
  default; the repo sets no `--snat-subnet-routes=false`). Verify at plan time: it decides
  whether "source" in FR-009 can tell the owner from the pipeline.
- The `/lxc/<vmid>/` cgroup layout in kernel OOM lines follows PVE's standard layout. Verify with
  the OOM drill.

## Out of Scope

- The Mac and client devices on the LAN.
- The Synology NAS, unless research finds it can forward syslog with no change on the NAS beyond
  its own settings. Then it can be added as a later story.
- Failed-login alerting (fail2ban already covers it) and intrusion detection.
- Tracing and application performance monitoring.
- Shipping logs off the estate, or to any hosted service.
- Caddy **access** logs. Caddy's own runtime log reaches the journal and is collected. Access
  logging can be revisited after SC-007's measurements.
- Fixing the monitoring backup (Measured state). That is a separate item.
- A per-LXC OOM metric (cgroup `memory.events`). Neither node_exporter nor cAdvisor exposes it
  in a form that works here. The host journal is the source instead (FR-007).

## Dependencies

- **None blocking.**
- **[`091`](./091-monitoring-stack-version-currency.md)** (soft): upgrade the monitoring stack
  first, so Loki is not added to Grafana 12.3 and Prometheus 3.8, both past support. Grafana 13.x may
  also be what Logs Drilldown needs.
- **[`081`](./081-externalise-prod-topology.md)**: FR-009's allowed sources are topology. If
  `081` has landed, they come from its source; if not, from `group_vars` beside the other
  addresses, and they move with `081`.
- **[`067`](./067-lab-prod-same-address-space.md) / [`072`](./072-lab-monitoring-deploy-wipes-prod.md)**:
  the LAB path deploys to PROD addresses. Drills run on a named test LXC.
- **`082`**: log alerts reach ntfy through its existing `alerts` publisher. Nothing changes there.
- **Closes** the "Application-level error/log alerting" and "Login anomaly alerting" items in
  `improvement-candidates.md`. **Amends** `042`'s out-of-scope entry for log aggregation.
- **Related, not required**: the "`pve` node_exporter" candidate in `improvement-candidates.md`.
  This feature puts the first agent on the PVE host; installing node_exporter there through the
  same play costs little.

## Research notes (for `/speckit-plan`)

Collected 2026-10-21 against Loki v3.7.9 and Alloy v1.21.0. Re-check versions at plan time.

- **Loki 3.x**: structured metadata is on by default and needs `store: tsdb` with `schema: v13`.
  Since 3.5.8 the image has no shell, so a `wget` healthcheck fails; `loki -health` is
  available in 3.7. Monolithic mode stays supported; only Simple Scalable is being removed in
  4.0.
- **Ruler**: local rule storage, path `<dir>/fake/*.yaml` when `auth_enabled: false`.
  `alertmanager_url: http://alertmanager:9093` on the compose network. Local storage is
  read-only from the API, so rules are deployed as files, never with `lokitool rules sync`.
  `lokitool rules lint --dry-run` checks LogQL offline.
- **Alloy journal source**: reads both `/var/log/journal` and `/run/log/journal`, default
  `max_age` 7h. Without `adm` and `systemd-journal` it starts cleanly and collects nothing.
- **Alloy write path**: backoff 500 ms → 5 min, 10 retries by default, then drops (counted).
  `max_backoff_retries = 0` retries for ever. The queue is in memory (10 MiB per shard), and
  queue settings and the WAL are experimental (the WAL needs `--stability.level=experimental`
  since 1.21).
- **Alloy footprint**: upstream estimates about 120 MiB per 1 MiB/s of logs, plus a fixed cost.
  The estate's peak host produces well under 1 KiB/s, so the fixed cost dominates. Measure it.
- **Kernel OOM lines** (`mm/oom_kill.c`): `oom-kill:constraint=…,oom_memcg=…,task_memcg=…,task=…,pid=…`
  for every OOM, followed by `Memory cgroup out of memory: Killed process …` for limit OOMs or
  `Out of memory: Killed process …` for system-wide ones.
- **Logs Drilldown** in Grafana needs Loki ≥ 3.2 with the pattern ingester enabled. That is
  optional, and its exact requirement for Grafana 12.3 is unverified.
- **Alternatives considered**: VictoriaLogs v1.53 (alerting via vmalert, signed Grafana plugin,
  disk-size cap, accepts Loki push so Alloy still works). Vector 0.60 (durable disk buffers, but
  outside the Grafana ecosystem). Fluent Bit 5.1 (smallest, weaker Loki labelling).

## Open Questions (for `/speckit-plan`)

1. **R-001 — Tooling.** Confirm Loki + Alloy. The case for VictoriaLogs is memory on the 4 GiB
   LXC. Decide after measuring Loki with FR-004's limits.
2. **Docker rotation values and rollout** (FR-003): `max-size` and `max-file`, how containers are
   recreated host by host, and what happens to the existing 245 MB logs.
3. **Docker log source**: Docker API (`loki.source.docker`, needs the socket) or json-file
   tailing (still needs the socket for container-name labels). Either way the collector is
   root-equivalent on Docker hosts. Record the choice.
4. **Collector install**: which role owns it (`lxc_base` installs node_exporter on every LXC
   today) and how the PVE host gets it (`host_proxmox.yml`).
5. **Error rules**: for `llm-router` and `hermes`, what counts as an error line (many images log
   `ERROR` for normal events), and which further services join in the first delivery.
6. **Login allowed list**: confirm the access paths in Measured state with a census of 30 days
   of accepted logins and `sudo` users per host. This was not collected while drafting.
   Is "off-hours" worth a rule, or are source, user and key enough?
7. **Validation in CI**: can `lokitool rules lint` and `promtool` run in CI on rendered rules,
   given that pre-commit excludes role `files/` and `templates/`?
