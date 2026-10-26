# Feature Specification: Monitoring Tier C — Security & Availability Probing

**Feature Branch**: `042-monitoring-tier-c`
**Created**: 2026-03-02
**Status**: Draft
**Input**: User description: "Monitoring Tier C: Security monitoring"

## Overview

The homelab currently has zero security monitoring. Features 040 (Monitoring Overhaul) and 041 (Monitoring Tier B) built the monitoring foundation — infrastructure metrics on every container, application metrics for Caddy/Immich/Nextcloud/Jellyfin, unified alerting, and the self-registration pattern. Both tiers explicitly deferred security monitoring to Tier C. This feature introduces HTTPS endpoint probing with TLS certificate lifecycle monitoring, brute-force detection and blocking via fail2ban, a consolidated security overview dashboard, and corresponding alert rules with inhibition hygiene — closing the security observability gap.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — HTTPS Endpoint Probing & Availability Alerting (Priority: P1)

As a homelab administrator, I want all my public-facing HTTPS services continuously probed from inside the network so that I am notified within minutes when any service becomes unreachable through the reverse proxy path — detecting DNS, TLS, reverse proxy, or backend failures before users report them.

**Why this priority**: The homelab serves 5 active public-facing services through a single Caddy reverse proxy. Currently, there is no synthetic probing — the operator only discovers outages when a family member complains or when manually checking. HTTPS probing tests the full request path (DNS resolution → Caddy TLS termination → backend health) and provides the highest immediate value because it covers all 5 services with a single component.

**Independent Test**: Deploy the HTTPS probe service. Stop one of the backend services (e.g., Jellyfin). Verify that the probe detects the failure and an alert email arrives within 5 minutes. Restart the service and verify recovery notification.

**Acceptance Scenarios**:

1. **Given** the HTTPS probe service is deployed on the monitoring host, **When** the operator checks the monitoring target list, **Then** 4 probe targets appear (one per public HTTPS endpoint: `grafana.hus-sky.no`, `immich.hus-sky.no`, `nextcloud.hus-sky.no`, `jellyfin.hus-sky.no`) and each shows a successful probe result.
2. **Given** all HTTPS probes are running, **When** a backend service (e.g., Jellyfin) is stopped and the endpoint becomes unreachable for 2 minutes, **Then** the operator receives an email alert (EndpointDown, critical severity) identifying the specific endpoint URL within 5 minutes.
3. **Given** an EndpointDown alert has fired, **When** the backend service is restored and the next probe succeeds, **Then** the operator receives a recovery email within 3 minutes.
4. **Given** one endpoint is experiencing slow responses (response time above 5 seconds sustained for 5 minutes), **When** the alert evaluation runs, **Then** the operator receives a warning email (HighProbeLatency) identifying the slow endpoint and its response time.
5. **Given** the monitoring host reboots, **When** the probe service restarts automatically, **Then** probing resumes within 2 minutes of host startup without manual intervention.
6. **Given** an endpoint returns an HTTP redirect (302) — as Nextcloud is expected to do, **When** the probe follows the redirect, **Then** the probe reports success (not failure), and the response latency includes the redirect follow time.

---

### User Story 2 — TLS Certificate Expiry Monitoring (Priority: P1)

As a homelab administrator, I want advance warning when any TLS certificate is approaching expiry so that I can investigate failed ACME renewals before the certificate expires and users see browser security warnings.

**Why this priority**: Caddy manages all TLS certificates via DNS-01 ACME with the Domeneshop DNS plugin. Automated renewal usually works, but if it silently fails (DNS API outage, rate limits, plugin misconfiguration), the operator has no visibility until the certificate actually expires and browsers show scary warnings. A 14-day early warning gives ample time to investigate and manually intervene, while a 7-day critical alert escalates urgency. This is paired with US-1 because the certificate expiry metric comes from the same HTTPS probe infrastructure.

**Independent Test**: Check the certificate expiry metric for each probed endpoint. Verify that all certificates show more than 14 days remaining (expected for fresh Let's Encrypt certs). Optionally, simulate a near-expiry scenario by lowering the alert threshold temporarily and verifying that the alert fires.

**Acceptance Scenarios**:

1. **Given** HTTPS probes are running for all 5 endpoints, **When** the operator queries the certificate expiry metric, **Then** each endpoint shows the number of days until its TLS certificate expires, with accuracy to the nearest day.
2. **Given** a TLS certificate has fewer than 14 days until expiry (sustained for 15 minutes to avoid transient measurement noise), **When** the alert evaluation runs, **Then** the operator receives a warning email (TLSCertExpiringSoon) identifying the specific domain and the number of days remaining.
3. **Given** a TLS certificate has fewer than 7 days until expiry (sustained for 15 minutes), **When** the alert evaluation runs, **Then** the operator receives a critical email (TLSCertExpiryCritical) identifying the specific domain and the number of days remaining.
4. **Given** an HTTPS endpoint is completely unreachable (EndpointDown alert has fired), **When** the certificate expiry check cannot obtain certificate data from the unreachable endpoint, **Then** the TLSCertExpiringSoon and TLSCertExpiryCritical alerts do NOT fire for that endpoint — because certificate status is unknown when the endpoint is down. (Inhibition rule: EndpointDown suppresses cert alerts for the same instance.)
5. **Given** Caddy successfully renews a certificate via ACME, **When** the next probe detects the new certificate, **Then** the certificate expiry metric jumps from a low value (e.g., 5 days) to a high value (e.g., 89 days), and any previously firing cert expiry alerts resolve automatically.

---

### User Story 3 — Brute-Force Detection and Blocking (Priority: P2)

As a homelab administrator, I want repeated authentication failures automatically detected and the offending IP addresses blocked, and I want visibility into ban activity so that I can assess the threat level and ensure the blocking mechanism is functioning correctly.

**Why this priority**: The homelab exposes SSH on the reverse proxy, Nextcloud login, and Jellyfin login to the internet. Without intrusion detection, brute-force login attempts go unnoticed and unblocked. fail2ban is the industry-standard solution for this and is well-supported in the Debian ecosystem. While this is lower priority than endpoint probing (US-1 covers availability), it is the foundational security layer — detecting and blocking attacks rather than just detecting outages.

**Independent Test**: Deploy fail2ban to the reverse proxy host. Generate deliberate SSH auth failures from a test IP. Verify the IP is banned after the configured failure threshold. Check that the ban appears in the monitoring metrics within 60 seconds.

**Acceptance Scenarios**:

1. **Given** fail2ban is deployed on the reverse proxy host (192.168.1.211), **When** an IP address generates 5 failed SSH login attempts within 10 minutes, **Then** that IP is banned from SSH access for the configured ban duration and the ban is logged.
2. **Given** fail2ban is deployed on the Nextcloud host (192.168.1.216), **When** an IP address generates repeated Nextcloud login failures matching the Nextcloud auth failure log pattern, **Then** that IP is banned and the ban event is captured in fail2ban metrics.
3. **Given** fail2ban is deployed on the Jellyfin host (192.168.1.215) with at minimum an SSH jail, **When** the operator checks the fail2ban service status, **Then** fail2ban is running with the sshd jail active.
4. **Given** fail2ban metrics are exposed on each fail2ban-enabled host, **When** the monitoring system scrapes the metrics endpoint, **Then** the scrape target shows "UP" and metrics include current ban count, total bans, total failures, and jail status per jail.
5. **Given** a sustained brute-force attack triggers more than 10 bans within one hour on any host, **When** the alert evaluation runs, **Then** the operator receives a warning email (Fail2banHighBanRate) identifying the host and indicating an active brute-force attempt.
6. **Given** the fail2ban metrics exporter becomes unreachable on a host for 2 minutes, **When** the alert evaluation runs, **Then** the operator receives a critical alert (Fail2banDown) identifying the host — and the Fail2banHighBanRate alert is suppressed for that host since ban data is unavailable.

---

### User Story 4 — Security Overview Dashboard (Priority: P2)

As a homelab administrator, I want a single "Security Overview" dashboard that consolidates all security and availability metrics — endpoint health, TLS certificate lifecycle, fail2ban activity — so that I can assess the security posture of my homelab at a glance without navigating multiple dashboards or running manual checks.

**Why this priority**: Individual metrics are valuable, but the operator needs a consolidated view to quickly answer "is everything secure and available?" This dashboard is the primary interface for security observability and ties together US-1, US-2, and US-3 into a coherent operational view. It is P2 rather than P1 because the alerts (US-1, US-2) provide immediate notification of problems even without a dashboard.

**Independent Test**: Deploy the security dashboard. Verify that all panels display live data. Introduce a test failure (stop a service, trigger a ban) and confirm the dashboard reflects the event in real time.

**Acceptance Scenarios**:

1. **Given** the Security Overview dashboard is provisioned, **When** the operator opens it in the dashboard UI, **Then** it loads within 5 seconds and displays panels organized into three logical sections: Endpoint Health, TLS Certificates, and fail2ban Activity.
2. **Given** all HTTPS endpoints are healthy, **When** the operator views the Endpoint Health section, **Then** a status grid shows each domain with a green "Up" indicator, and a response latency chart shows historical probe times per endpoint.
3. **Given** one endpoint is down, **When** the operator views the Endpoint Health section, **Then** the status grid shows that specific domain with a red "Down" indicator while all other domains remain green.
4. **Given** all TLS certificates are valid with more than 30 days remaining, **When** the operator views the TLS Certificates section, **Then** a bar gauge shows days remaining per domain with green coloring (green ≥ 30 days, yellow 14–30 days, red < 14 days), and a timeline chart shows certificate expiry over time.
5. **Given** fail2ban is active on 3 hosts, **When** the operator views the fail2ban section, **Then** the dashboard shows: active bans per host and jail (stat grid), ban rate over time (hourly trend chart), failed authentication attempts over time (hourly trend chart), and a jail status table showing each jail's enabled/active state.
6. **Given** the Security Overview dashboard is deployed via the monitoring stack's dashboard provisioning system, **When** the monitoring playbook is re-run, **Then** the dashboard is re-provisioned idempotently — no manual import is required and no duplicates are created.

---

### User Story 5 — Security Alert Noise Reduction (Priority: P3)

As a homelab administrator, I want security alerts to follow the same inhibition cascade pattern established in Tier A so that when a root-cause alert fires (e.g., endpoint down), downstream symptom alerts (e.g., certificate expiry check failing) are suppressed — ensuring I receive only actionable notifications, not a flood of redundant emails.

**Why this priority**: Without inhibition rules, a single endpoint outage would generate three emails: EndpointDown, TLSCertExpiringSoon (probe can't check cert), and HighProbeLatency (timeout). Similarly, a fail2ban exporter crash would generate both Fail2banDown and Fail2banHighBanRate (stale data). The inhibition cascade from Tier A proved effective for infrastructure alerts, and applying the same pattern to security alerts maintains consistent alerting hygiene. This is P3 because the alerts themselves (P1, P2) are more important than noise reduction — noisy alerts are better than no alerts.

**Independent Test**: Stop a probed endpoint. Verify that only the EndpointDown alert fires — not TLSCertExpiringSoon or HighProbeLatency. Stop the fail2ban exporter on a host. Verify that only Fail2banDown fires — not Fail2banHighBanRate.

**Acceptance Scenarios**:

1. **Given** EndpointDown has fired for `nextcloud.hus-sky.no`, **When** the TLS certificate check also fails (because the endpoint is unreachable), **Then** the TLSCertExpiringSoon and TLSCertExpiryCritical alerts are suppressed for `nextcloud.hus-sky.no` — only the EndpointDown email is delivered.
2. **Given** EndpointDown has fired for an endpoint, **When** the HighProbeLatency alert would also fire (probe timeout reads as >5s), **Then** the HighProbeLatency alert is suppressed for that endpoint — only EndpointDown is delivered.
3. **Given** Fail2banDown has fired for the reverse proxy host, **When** the Fail2banHighBanRate alert evaluation runs for the same host, **Then** it is suppressed — only Fail2banDown is delivered.
4. **Given** Fail2banDown has fired for a host's fail2ban exporter, **When** the generic ServiceDown alert (from Feature 040) also triggers for the same fail2ban exporter scrape target, **Then** ServiceDown is suppressed for that target — only Fail2banDown is delivered, following the same pattern as SynologyNASDown suppressing ServiceDown for Synology targets.
5. **Given** endpoint probing and fail2ban monitoring are both active, **When** the operator reviews the alerting configuration, **Then** the inhibition rules follow the same structural pattern used by infrastructure alert inhibitions from Feature 040 (consistent source/target matching on the `instance` label).

---

### Edge Cases

- **What happens if DNS does not resolve `*.hus-sky.no` from the monitoring LXC to the Caddy reverse proxy IP?** The HTTPS probes fail for all endpoints. EndpointDown alerts fire for every domain. The operator investigates DNS resolution on the monitoring host. This is a prerequisite that must be verified before or during deployment — if split-horizon or public DNS is not configured, all probes will fail.
- **What happens if Caddy is down but the backend services are healthy?** All probes fail simultaneously because they go through Caddy. EndpointDown fires for every endpoint. The operator sees a correlated failure pattern (all endpoints down at once) which indicates a reverse proxy issue rather than individual service failures.
- **What happens if the HTTPS probe service itself crashes?** All probe metrics stop updating. The monitoring system's generic ServiceDown alert (from Feature 040) fires for the probe service's scrape target. Certificate expiry and response latency data go stale. Whether EndpointDown alerts also fire for individual endpoints depends on how the monitoring system handles stale probe data — the implementation should ensure that a probe service outage produces only the ServiceDown alert, not a cascade of 5 EndpointDown alerts for every probed endpoint. The operator receives a single alert about the probe service being down.
- **What happens if fail2ban bans a legitimate user?** The user is locked out for the configured ban duration. The operator can see the ban in the fail2ban dashboard panel (active bans by host and jail) and manually unban the IP. This is standard fail2ban operational procedure. The monitoring feature does not provide automated unbanning.
- **What happens if a fail2ban jail configuration references a log file that doesn't exist?** fail2ban logs an error and the jail fails to start. The other jails on that host continue functioning. The fail2ban metrics exporter still runs (reporting the failed jail status). The operator sees the jail as inactive in the dashboard's jail status table.
- **What happens during a monitoring stack redeployment?** Brief probe gaps (1–2 minutes) are expected. EndpointDown alerts should NOT fire because the `for: 2m` threshold accounts for brief gaps. Historical probe data is preserved across redeployment (stored in the monitoring system's time-series database).
- **What happens if a brute-force attack generates thousands of bans per hour?** fail2ban continues banning IPs. The Fail2banHighBanRate alert fires (>10 bans/hour threshold). The operator receives a warning email. fail2ban's performance under extreme load is outside the scope of this monitoring feature — the monitoring system reports what fail2ban does, it doesn't control fail2ban's capacity.
- **What happens when the Nextcloud container runs Nextcloud inside Docker and auth failure logs are inside the Docker container, not on the host filesystem?** The fail2ban jail must be configured to read logs from the correct path. If the log path is not accessible to fail2ban on the LXC host, the Nextcloud authentication jail cannot function and is excluded — the sshd jail still operates. This path mapping is an implementation detail to be resolved during planning.

## Requirements *(mandatory)*

### Functional Requirements

#### HTTPS Endpoint Probing

- **FR-001**: System MUST deploy an HTTPS probe service on the monitoring host (192.168.1.214) that performs synthetic HTTPS requests against target URLs and exposes the results as metrics. *(traces to US-1)*
- **FR-002**: The HTTPS probe service MUST be deployed as a container in the existing monitoring Docker Compose stack, following the same pattern as the existing Telegraf container. *(traces to US-1)*
- **FR-003**: System MUST probe 5 active public HTTPS endpoints: `https://grafana.hus-sky.no`, `https://immich.hus-sky.no`, `https://nextcloud.hus-sky.no`, `https://jellyfin.hus-sky.no`. *(traces to US-1)*
- **FR-004**: For each probed endpoint, the system MUST collect: probe success/failure (boolean), HTTP response status code, TLS certificate expiry timestamp, total probe response duration, and DNS resolution time. *(traces to US-1, US-2)*
- **FR-005**: The HTTPS probe MUST follow HTTP redirects (302/301) and report success if the final response is successful — because Nextcloud and Grafana redirect unauthenticated users to login pages. *(traces to US-1, AC-1.6)*
- **FR-006**: The HTTPS probe configuration MUST be defined as static scrape configuration in the central monitoring configuration (not via the monitoring contract self-registration pattern) because the probe targets are external URLs — not per-service exporter endpoints. *(traces to US-1)*

#### TLS Certificate Monitoring

- **FR-007**: System MUST expose a metric representing the number of days until each probed endpoint's TLS certificate expires, derived from the probe's certificate expiry timestamp. *(traces to US-2)*
- **FR-008**: System MUST alert at the 14-day warning threshold (TLSCertExpiringSoon) and 7-day critical threshold (TLSCertExpiryCritical) for certificate expiry, with a sustained evaluation period of 15 minutes to avoid transient measurement noise. *(traces to US-2)*

#### fail2ban Deployment

- **FR-009**: System MUST deploy fail2ban on 3 LXCs that accept external traffic: reverse_proxy (192.168.1.211), nextcloud (192.168.1.216), and jellyfin (192.168.1.215). *(traces to US-3)*
- **FR-010**: System MUST configure an `sshd` fail2ban jail on all 3 fail2ban-enabled hosts, banning IPs after repeated SSH authentication failures. *(traces to US-3)*
- **FR-011**: System MUST configure a `nextcloud` fail2ban jail on the Nextcloud host (192.168.1.216) to detect and ban IPs generating repeated Nextcloud login failures — contingent on auth failure logs being accessible to fail2ban on the LXC host. *(traces to US-3)*
- **FR-012**: System SHOULD configure a `jellyfin` fail2ban jail on the Jellyfin host (192.168.1.215) to detect and ban IPs generating repeated Jellyfin login failures — contingent on Jellyfin writing auth failure logs in a format parseable by fail2ban. If the log format is not parseable, this requirement is waived and the sshd jail alone is sufficient. *(traces to US-3)*
- **FR-013**: fail2ban deployment MUST be managed via Ansible — installed as a system package with systemd service management. Manual configuration is not acceptable. *(traces to US-3)*

#### fail2ban Metrics

- **FR-014**: System MUST deploy a fail2ban metrics exporter on each fail2ban-enabled host, exposing: current active ban count per jail, total cumulative bans per jail, total authentication failures per jail, and jail enabled/active status. *(traces to US-3)*
- **FR-015**: Each fail2ban metrics exporter MUST be integrated into the monitoring system via the monitoring contract pattern (self-registration in the service's host_vars), following the established pattern from Features 040 and 041 for per-service exporters. *(traces to US-3, US-4)*
- **FR-016**: The fail2ban metrics exporter MUST be accessible from the monitoring host (192.168.1.214) on a dedicated port. *(traces to US-3)*

#### Security Alert Rules

- **FR-017**: System MUST deploy a dedicated security alert rules file alongside existing alert rule files (infrastructure alerts, Synology alerts), following the same file-based alert rules pattern where the monitoring system auto-loads all alert files from a designated directory. *(traces to US-1, US-2, US-3)*
- **FR-018**: The security alert rules file MUST include the following 6 alert rules:

  | Alert Name | Condition | Sustained Duration | Severity | Description |
  |---|---|---|---|---|
  | EndpointDown | HTTPS probe failure for any endpoint | 2 minutes | Critical | Public endpoint is unreachable |
  | TLSCertExpiringSoon | Certificate expiry < 14 days | 15 minutes | Warning | Certificate approaching expiry |
  | TLSCertExpiryCritical | Certificate expiry < 7 days | 15 minutes | Critical | Certificate critically close to expiry |
  | HighProbeLatency | Probe response time > 5 seconds | 5 minutes | Warning | Endpoint responding slowly |
  | Fail2banHighBanRate | More than 10 bans within 1 hour | 5 minutes | Warning | Active brute-force attack detected |
  | Fail2banDown | fail2ban exporter unreachable | 2 minutes | Critical | fail2ban monitoring is offline |

  *(traces to US-1, US-2, US-3, US-5)*

- **FR-019**: All security alerts MUST be delivered via the existing email (SMTP) notification channel — no new notification channels. *(traces to US-1, US-2, US-3)*

#### Alertmanager Inhibition Rules

- **FR-020**: The alerting configuration MUST include an inhibition rule where EndpointDown suppresses TLSCertExpiringSoon, TLSCertExpiryCritical, and HighProbeLatency for the same instance (endpoint). *(traces to US-5)*
- **FR-021**: The alerting configuration MUST include inhibition rules where: (a) Fail2banDown suppresses Fail2banHighBanRate for the same instance (host), and (b) Fail2banDown suppresses the generic ServiceDown alert for the same fail2ban exporter instance — preventing duplicate notifications when the exporter is unreachable, following the same pattern as SynologyNASDown → ServiceDown from Feature 040. *(traces to US-5)*
- **FR-022**: New inhibition rules MUST follow the same structural pattern (source alert, target alert, matching labels) used by existing inhibition rules from Feature 040. *(traces to US-5)*

#### Security Overview Dashboard

- **FR-023**: System MUST provide a "Security Overview" built-in dashboard, provisioned automatically by the monitoring stack's dashboard provisioning system — not requiring manual import. *(traces to US-4)*
- **FR-024**: The Security Overview dashboard MUST include the following panels:

  | Section | Panel | Display Type | Data Shown |
  |---|---|---|---|
  | Endpoint Health | HTTPS Endpoint Status | Status grid | Up/Down per domain (green/red) |
  | Endpoint Health | Probe Response Time | Time series | Response duration per endpoint over time |
  | Endpoint Health | Probe Success Rate (24h) | Gauge | Average availability percentage per endpoint |
  | TLS Certificates | Certificate Expiry (days) | Bar gauge | Days remaining per domain (red <7d, yellow <14d, green ≥30d) |
  | TLS Certificates | Certificate Expiry Timeline | Time series | Expiry metric over time (shows renewal jumps) |
  | fail2ban | Active Bans by Host | Status grid | Current ban count per host and jail |
  | fail2ban | Ban Rate (hourly) | Time series | Bans per hour per host and jail |
  | fail2ban | Failed Auth Attempts | Time series | Auth failures per hour per host and jail |
  | fail2ban | Jail Status | Table | Jail enabled/active state per host |

  *(traces to US-4)*

- **FR-025**: The Security Overview dashboard MUST be compatible with the currently running dashboard UI version and MUST NOT use deprecated panel types or query syntax. *(traces to US-4)*

#### IaC & Operations

- **FR-026**: All changes (probe service, fail2ban, exporters, alert rules, dashboard, inhibition rules) MUST be deployed via Ansible roles and playbooks — no manual configuration on any host. *(traces to all stories)*
- **FR-027**: The monitoring playbook MUST remain idempotent after all changes — re-running without changes produces no unexpected modifications. *(traces to all stories)*
- **FR-028**: No secrets MUST be committed to the git repository in plaintext. If any component requires credentials (e.g., fail2ban exporter API keys), they MUST be stored in Ansible vault. *(traces to all stories)*
- **FR-029**: All changes MUST be deployable from both CI/CD (GitHub Actions on the self-hosted runner) and a developer laptop — per the constitution's dual-provisioning parity requirement. *(traces to all stories)*

### Key Entities

- **HTTPS Probe Target**: A public-facing URL that the probe service tests periodically. Each target yields metrics for probe success, response time, TLS certificate expiry, and DNS resolution time. Defined statically in the monitoring configuration (not via monitoring contracts). The initial list includes 5 active domains served by the Caddy reverse proxy.
- **TLS Certificate Expiry Metric**: A per-endpoint metric representing the time remaining until the endpoint's TLS certificate expires, expressed in days. Derived from the HTTPS probe's certificate inspection. Used to trigger warning (14-day) and critical (7-day) alerts.
- **fail2ban Jail**: A fail2ban configuration unit that monitors a specific log source for authentication failure patterns and bans offending IPs. Each jail has: a name (e.g., `sshd`, `nextcloud`), a log path, a failure pattern, a failure threshold, and a ban duration. Multiple jails can run on a single host.
- **fail2ban Metrics Exporter**: A process on each fail2ban-enabled host that reads fail2ban state (bans, failures, jail status) and exposes it as metrics for the monitoring system to scrape. Integrated via the monitoring contract self-registration pattern.
- **Security Alert Rule**: A condition/threshold pair that, when sustained for a specified duration, triggers a notification. Security alert rules are grouped in a dedicated file alongside existing alert rule files. Each rule has: a name, a condition expression, a sustained duration, a severity level (warning or critical), and a description.
- **Inhibition Rule**: A relationship between two alert rules where firing of a "source" alert suppresses a "target" alert for the same instance. Prevents redundant notifications when a root cause (e.g., endpoint down) would also trigger symptom alerts (e.g., certificate check failed).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Operator can view live up/down status for all 5 public HTTPS endpoints on the Security Overview dashboard within 5 minutes of deployment completion.
- **SC-002**: Operator receives an email alert within 5 minutes when any HTTPS endpoint becomes unreachable (EndpointDown alert fires after 2 minutes of sustained failure, plus notification delivery).
- **SC-003**: Operator can view TLS certificate days-remaining for all 5 endpoints on the Security Overview dashboard, with per-domain thresholds visually distinguishing healthy (≥30 days), warning (14–30 days), and critical (<14 days) states.
- **SC-004**: Operator receives an email alert when any TLS certificate has fewer than 14 days until expiry (warning) or fewer than 7 days (critical).
- **SC-005**: fail2ban is running and actively banning offending IPs on 3 hosts (reverse_proxy, nextcloud, jellyfin) — verified by checking fail2ban service status and jail list on each host.
- **SC-006**: Operator can view fail2ban activity (active bans, ban rate trend, failed auth attempts, jail status) across all 3 fail2ban-enabled hosts on the Security Overview dashboard.
- **SC-007**: When an HTTPS endpoint goes down, only the EndpointDown alert fires — TLSCertExpiringSoon, TLSCertExpiryCritical, and HighProbeLatency are suppressed for that endpoint (verified by stopping a backend service and confirming only one email is received).
- **SC-008**: When the fail2ban exporter goes down on a host, only the Fail2banDown alert fires — both Fail2banHighBanRate and the generic ServiceDown alert are suppressed for that host (verified by stopping the fail2ban exporter and confirming only one email is received).
- **SC-009**: Existing monitoring from Features 040 and 041 continues to function: infrastructure metrics, Caddy/Immich application metrics, external exporters (Nextcloud/Jellyfin), Synology SNMP metrics, and the unified alerting framework remain operational after this feature is deployed.
- **SC-010**: Re-running the monitoring Ansible playbook after all changes produces an idempotent result (no unexpected changes on the second run).
- **SC-011**: The Security Overview dashboard loads within 5 seconds when displaying a 24-hour time range.
- **SC-012**: No component introduced by this feature (probe service, fail2ban, exporters) requires manual configuration on any host — everything is deployed and configured by Ansible.

## Assumptions

- **A-001**: Features 040 (Monitoring Overhaul) and 041 (Monitoring Tier B) are fully merged and operational. The monitoring stack (Prometheus, Grafana, Alertmanager), self-registration pattern, monitoring contracts, infrastructure metrics agents, and application exporters are all deployed.
- **A-002**: DNS resolution of `*.hus-sky.no` domains from the monitoring LXC (192.168.1.214) resolves to the Caddy reverse proxy IP (192.168.1.211). This is likely already configured via public or split-horizon DNS for LAN access. If this is not the case, the HTTPS probes will all fail and the issue must be resolved before this feature delivers value.
- **A-003**: The Caddy reverse proxy (192.168.1.211) is serving all 5 public HTTPS endpoints with valid TLS certificates managed via DNS-01 ACME (Domeneshop DNS plugin). Certificates are automatically renewed by Caddy.
- **A-004**: The existing monitoring Docker Compose stack supports adding new containers alongside the current services (Prometheus, Grafana, Alertmanager, Telegraf, and any exporter containers from Tier B).
- **A-005**: The monitoring system's alert rules auto-loading mechanism (glob pattern for alert files) supports adding new alert rule files without modifying the main configuration file.
- **A-006**: The existing email SMTP notification channel is functional and will be used for all new security alerts. No new notification channels are needed.
- **A-007**: Network connectivity exists between the monitoring LXC (192.168.1.214) and all fail2ban-enabled LXCs on the fail2ban exporter port.
- **A-008**: The reverse proxy LXC (192.168.1.211), Nextcloud LXC (192.168.1.216), and Jellyfin LXC (192.168.1.215) all run Debian stable and can install fail2ban via `apt`. These are not Docker-only containers.
- **A-009**: SSH is exposed to the internet on the reverse proxy LXC, making the `sshd` fail2ban jail immediately valuable. SSH on Nextcloud and Jellyfin is accessible within the LAN (and possibly from the internet).
- **A-010**: Nextcloud writes authentication failure logs in a known, parseable format that fail2ban can match — based on the reference document stating "Nextcloud has a well-defined auth failure log format." The specific log path may require investigation during implementation (container vs. host filesystem).
- **A-011**: Home Assistant is not deployed (`ha.hus-sky.no` is not probed in this feature). It will be added to the probe list when HA is deployed in a future feature. This is consistent with Feature 040's decision (DL-04).
- **A-012**: The fail2ban metrics exporter does not require secrets (no API keys or credentials). fail2ban state is read from the local fail2ban socket or textfile. If a specific exporter implementation requires credentials, they will be stored in Ansible vault.
- **A-013**: The monitoring LXC's resource allocation (4 GB RAM, 2 vCPU as established in Feature 040) is sufficient to accommodate the additional HTTPS probe service container.

## Non-Functional Requirements

- **NFR-001**: The HTTPS probe service container MUST consume no more than 50 MB RAM and negligible CPU on the monitoring host — consistent with the per-component resource limits from Feature 040.
- **NFR-002**: Each fail2ban installation MUST consume no more than 50 MB RAM per host. fail2ban is a lightweight daemon and this threshold accounts for all configured jails.
- **NFR-003**: Each fail2ban metrics exporter instance MUST consume no more than 50 MB RAM per host — consistent with the exporter resource limits from Feature 040.
- **NFR-004**: The Security Overview dashboard MUST load within 5 seconds when displaying a 24-hour time range — consistent with the dashboard performance target from Feature 040.
- **NFR-005**: Alert delivery latency for security alerts MUST be less than 5 minutes from condition trigger to email receipt — accounting for scrape interval, evaluation interval, sustained duration threshold, and SMTP delivery. (Consistent with Feature 040's NFR-004.)
- **NFR-006**: HTTPS probe interval SHOULD be 30 seconds or less to ensure timely detection of endpoint failures (the 2-minute EndpointDown threshold assumes multiple failed probes, not just one).

## Out of Scope

- **Log aggregation / centralized logging** — Loki, Promtail, or similar. Entirely separate architecture concern. Out of scope for all monitoring tiers. Delivered separately by spec 092.
- **Network intrusion detection** — Suricata, Zeek, or similar. Requires dedicated hardware/resources beyond the homelab scope.
- **Proxmox VE host metrics** — Deferred since Tier A. The hypervisor itself (as opposed to its LXC guests) requires a different collection approach. Separate feature.
- **Vulnerability scanning** — Trivy, Grype, or similar. Not a monitoring concern.
- **WAF / rate limiting** — Application-level security at the reverse proxy. Caddy configuration concern, not monitoring.
- **Custom recording rules for anomaly detection** — The initial deployment collects raw metrics; recording rules can be added in a follow-up once baseline patterns are observed.
- **SSH key rotation monitoring** — Low value in a homelab context.
- **Audit logging** — Requires log aggregation infrastructure that is out of scope.
- **Home Assistant endpoint probing** — HA is not yet deployed. `ha.hus-sky.no` is excluded from the probe list. Will be added when HA is deployed.
- **Authentication failure correlation across hosts** — Correlating failed login attempts from the same IP across multiple hosts (e.g., attacker scanning SSH on reverse_proxy then trying Nextcloud) requires recording rules or cross-host aggregation. Deferred until recording rules are in scope.
- **Automated incident response** — Automatically restarting failed services or escalating alerts beyond email. Out of scope.
- **Public internet probing** — Probing from outside the LAN (testing DNS/firewall path from the internet) would require external infrastructure. All probing is from the monitoring LXC inside the LAN.

## Constraints

- **C-001**: Must follow existing IaC patterns — Ansible roles and playbooks for all configuration, secrets in Ansible vault, idempotent deployments.
- **C-002**: Must not break any monitoring established by Features 040 or 041 — infrastructure metrics, application metrics (Caddy, Immich, Nextcloud, Jellyfin), Synology SNMP metrics, unified alerting, and self-registration pattern must continue to function.
- **C-003**: Must not expose the HTTPS probe service, fail2ban exporters, or any metrics endpoints via the public HTTPS reverse proxy — all metrics traffic is internal LAN-only.
- **C-004**: Must comply with the constitution's separation of concerns: Terraform owns container existence, Ansible owns configuration inside containers. All fail2ban and exporter deployment is Ansible-managed.
- **C-005**: Must comply with the constitution's secrets policy: no plaintext secrets in the repository.
- **C-006**: Must comply with the constitution's dual-provisioning parity: deployable from both CI/CD and developer laptop.
- **C-007**: The HTTPS probe service configuration is a special case — it uses static scrape configuration (not monitoring contracts) because it probes external URLs. This is an intentional deviation from the self-registration pattern and must not set a precedent for other services to bypass monitoring contracts.
- **C-008**: fail2ban metrics exporters MUST use the monitoring contract pattern (self-registration in host_vars), consistent with how all other per-service exporters are integrated.

## Dependencies

- **D-001**: Feature 040 (Monitoring Overhaul) — the monitoring stack, self-registration pattern, monitoring contracts, infrastructure metrics, unified alerting, and alert inhibition framework. Must be merged.
- **D-002**: Feature 041 (Monitoring Tier B) — external exporters (Nextcloud, Jellyfin), Synology SNMP fix, Prometheus hot-reload via `--web.enable-lifecycle`, vault preflight assertions pattern. Must be merged.
- **D-003**: Caddy reverse proxy (Feature 039) — HTTPS endpoints served by Caddy with valid TLS certificates. Required for HTTPS probing to function.
- **D-004**: Network connectivity — monitoring LXC must reach all `*.hus-sky.no` domains via HTTPS (port 443) and all fail2ban-enabled LXCs on the exporter port.
- **D-005**: DNS resolution — `*.hus-sky.no` must resolve to the Caddy reverse proxy IP (192.168.1.211) from the monitoring LXC (192.168.1.214).
- **D-006**: Existing Ansible roles for reverse_proxy, nextcloud, and jellyfin — fail2ban and its exporter will be added to these roles' configurations or as a shared role included by each.

## Decision Log

| # | Ambiguity | Decision | Rationale |
|---|-----------|----------|-----------|
| DL-01 | Should `ha.hus-sky.no` (Home Assistant) be included in the HTTPS probe list? | No — excluded until HA is deployed. | Home Assistant is not yet deployed (confirmed in Feature 040 DL-04). Probing a non-existent endpoint would generate a permanent EndpointDown alert, creating noise. The probe list will be updated when HA is deployed in a future feature. |
| DL-02 | Should HTTPS probes run from inside the LAN or from an external location? | Inside the LAN (from the monitoring LXC). | LAN probing tests the full request path through Caddy (DNS → TLS → backend) without requiring external infrastructure. The homelab has no external monitoring endpoint. LAN probing is simpler, avoids firewall/NAT complexity, and still validates the critical path. External probing would additionally test DNS propagation and firewall rules, but this is lower value for a homelab and requires infrastructure that does not exist. |
| DL-03 | Which fail2ban metrics exporter implementation should be used (dedicated Go binary, Python-based, or textfile collector via node_exporter)? | Not prescribed — this is an implementation decision for the planning phase. | The specification requires fail2ban metrics to be exposed (FR-014) and integrated via monitoring contracts (FR-015). The choice between a dedicated exporter binary, a Python script, or a cron-based textfile collector is an implementation detail with trade-offs (real-time vs. simplicity, extra process vs. reuse of existing node_exporter). The planning phase should evaluate options based on the existing node_exporter deployment and operational simplicity. |
| DL-04 | Does DNS resolve `*.hus-sky.no` to the Caddy IP from the monitoring LXC? | Assumed yes (A-002), but verification is required during deployment. | Public or split-horizon DNS likely handles this for LAN access. The spec includes this as an assumption (A-002) and the edge cases section documents the failure mode if it does not resolve correctly. Verification during implementation is a prerequisite step, not a specification question. |
| DL-05 | Can fail2ban parse Nextcloud authentication failure logs from the containerized deployment? | Assumed yes (A-010), based on Nextcloud's well-defined auth failure log format. The Nextcloud jail is a MUST requirement (FR-011) with a contingency clause. | The reference document states Nextcloud has a "well-defined auth failure log format." The containerized deployment may require log path mapping (Docker volume or host-accessible log file). The requirement includes a contingency: if auth logs are not accessible, the jail requirement is waived. The sshd jail still provides SSH protection. |
| DL-06 | Can fail2ban parse Jellyfin authentication failure logs? | Uncertain — the Jellyfin jail is a SHOULD (conditional) requirement (FR-012). | The reference document notes "Jellyfin auth logs may not be in standard fail2ban format — investigate during implementation." Rather than blocking the feature on this uncertainty, the Jellyfin-specific auth jail is a conditional requirement. The sshd jail (MUST) provides SSH protection regardless. If Jellyfin auth logs are parseable, the jail is added; if not, it is documented as a known limitation and descoped. |
| DL-07 | What threshold for Fail2banHighBanRate (bans per hour)? | 10 bans per hour. | This is a conservative starting threshold from the reference document. In a homelab with limited external exposure, 10 bans in an hour indicates a targeted brute-force attack rather than random internet noise. The threshold can be tuned after baseline data is collected. |
| DL-08 | What response time threshold for HighProbeLatency? | 5 seconds, sustained for 5 minutes. | The reference document specifies >5s for 5m. In a homelab where all services are on the same LAN segment, response times should be well under 1 second. A 5-second threshold is generous and only fires for genuine degradation, not momentary spikes. The 5-minute sustained duration prevents false alerts from brief network hiccups. |
| DL-09 | Should the Security Overview dashboard be owned by a specific service or be a built-in dashboard? | Built-in dashboard — not owned by any single service. | The dashboard spans multiple services (endpoint probing covers all domains, fail2ban covers 3 hosts). It follows the same pattern as the Infrastructure Overview and Synology NAS dashboards from Feature 040, which are also built-in dashboards deployed directly by the monitoring stack's dashboard provisioning. |
| DL-10 | Should fail2ban ban duration and failure thresholds be specified in the spec? | No — these are operational tuning parameters, not monitoring requirements. | The spec requires fail2ban to be deployed and configured with specific jails (FR-009 through FR-012). The exact ban duration (e.g., 10 minutes, 1 hour) and failure count before ban (e.g., 5 attempts) are operational decisions that the planning phase should determine based on security best practices. The monitoring feature's job is to report what fail2ban does, not to define fail2ban's security policy in detail. |
| DL-11 | Should the probe service check internal (LAN) URLs as well, or only public HTTPS endpoints? | Only public HTTPS endpoints through the reverse proxy. | Internal health checks (direct IP:port) are already handled by the infrastructure metrics agents and the generic ServiceDown alert from Feature 040. The HTTPS probes specifically test the public-facing path through Caddy's TLS termination. Adding internal probe targets would duplicate existing monitoring and create confusion about which alert to act on. |
| DL-12 | Should Fail2banDown suppress the generic ServiceDown alert for the same fail2ban exporter target? | Yes — following the SynologyNASDown → ServiceDown precedent from Feature 040. | The `Fail2banDown` alert condition ("fail2ban exporter unreachable") overlaps with Feature 040's generic `ServiceDown` rule (`up == 0`). Without an inhibition rule, both would fire simultaneously when a fail2ban exporter goes down, producing duplicate emails. Feature 040 established the precedent: `SynologyNASDown` suppresses `ServiceDown` for Synology targets (inhibition rule #1 in alertmanager.yml.j2). The same pattern applies here — the more specific `Fail2banDown` suppresses the generic `ServiceDown` for fail2ban exporter targets. |

## Open Questions

None — all ambiguities resolved in Decision Log above.
