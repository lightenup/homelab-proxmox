# Feature Specification: Monitoring & Observability Overhaul

**Feature Branch**: `040-monitoring-overhaul`
**Created**: 2026-03-01
**Revised**: 2026-03-01 (Self-critique pass — see revision notes at end)
**Status**: Draft
**Input**: User description: "Monitoring observability overhaul"

## Overview

The homelab monitoring stack currently has minimal coverage: Prometheus scrapes only itself and a Telegraf SNMP bridge, Grafana has a single Synology NAS dashboard, and three Synology-focused alert rules exist. A separate Uptime Kuma instance monitors four services via HTTP checks (though it is not included in the monitoring playbook and the Kuma role is unused), and an independent Python healthcheck script watches seven services. Monitoring stack component versions have already been updated to current stable releases (Prometheus v3.8.1, Grafana 12.3.1, Telegraf 1.37.0, Alertmanager v0.30.0) in the group_vars layer.

This feature overhauls the monitoring foundation to provide infrastructure-level metrics from every service container, application-level metrics from services that natively expose them, a unified alerting framework that replaces Uptime Kuma, and an extensible pattern that makes onboarding future services automatic.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Infrastructure Health Baseline (Priority: P1)

As a homelab administrator, I want to see CPU, memory, disk, and network metrics for every service container in my homelab, so that I can identify resource exhaustion before it causes outages and make informed capacity decisions.

**Why this priority**: Without per-container infrastructure metrics, the only visibility into resource usage is SSH-ing into each container individually. This is the foundational observability layer that all other monitoring builds on, and it covers every service in the homelab regardless of what application it runs.

**Independent Test**: Deploy the infrastructure metrics agent to all service containers, verify that a monitoring dashboard shows live CPU/memory/disk/network graphs for each container independently of any application-specific metrics.

**Acceptance Scenarios**:

1. **Given** the infrastructure metrics agent is deployed to all service containers (AdGuard, Reverse Proxy, Home Assistant, Immich, Monitoring, Jellyfin, Nextcloud), **When** the operator opens the infrastructure dashboard, **Then** each container appears as a separate row/panel showing CPU usage, memory usage, disk usage, and network throughput with data no older than 60 seconds.
2. **Given** a container is under high CPU load, **When** the operator views the infrastructure dashboard, **Then** the CPU metric for that specific container reflects the elevated usage within 60 seconds.
3. **Given** a container's root filesystem is 86% full, **When** the alert evaluation runs, **Then** the operator receives an email alert identifying the specific container and current disk usage percentage within 5 minutes.
4. **Given** a container's memory usage exceeds 85% for 5 consecutive minutes, **When** the alert evaluation runs, **Then** the operator receives a warning email identifying the specific container and current memory usage percentage.
5. **Given** the Proxmox host reboots and containers restart, **When** the infrastructure metrics agents come back online, **Then** metrics collection resumes automatically without manual intervention, and the dashboard shows data within 2 minutes of container startup.

---

### User Story 2 — Unified Service Availability Alerting (Priority: P1)

As a homelab administrator, I want a single alerting mechanism that automatically monitors every scraped service and notifies me when any service becomes unreachable, so that I have one source of truth for availability instead of maintaining Uptime Kuma and the monitoring stack separately.

**Why this priority**: Currently, Uptime Kuma monitors 4 services via HTTP and the healthcheck script monitors 7 services, both independently from Prometheus. Having three separate monitoring systems creates confusion about which one is authoritative and triples the maintenance effort. A unified approach where every service scraped by the metrics collector automatically gets availability monitoring eliminates this duplication.

**Independent Test**: Stop a monitored service, verify an alert email is received within 5 minutes. Restart the service, verify a recovery email is received. Confirm no Uptime Kuma configuration exists on the monitoring container.

**Acceptance Scenarios**:

1. **Given** the monitoring stack is deployed with the unified alerting framework, **When** any monitored service (including infrastructure metrics agents, application metrics endpoints, and existing Synology SNMP) becomes unreachable for 2 minutes, **Then** the operator receives an email alert identifying the service name, the affected endpoint, and a "down for 2+ minutes" message.
2. **Given** an alert has fired for a downed service, **When** the service recovers and the next scrape succeeds, **Then** the operator receives a recovery email within 2 minutes.
3. **Given** the monitoring stack is deployed, **When** the operator checks the monitoring container, **Then** no Uptime Kuma process, container, configuration, or data directory exists.
4. **Given** the Uptime Kuma role directory existed in the Ansible codebase, **When** this feature is complete, **Then** the role directory, its variables in host_vars, and its secrets in vault are fully removed from the repository.
5. **Given** all services are healthy, **When** the operator views the alert status interface, **Then** zero active alerts are shown and all scrape targets report "UP" status.

---

### User Story 3 — Application-Level Service Metrics (Priority: P1)

As a homelab administrator, I want to see application-specific metrics for services that natively expose them — specifically request rates, error rates, and response times for the reverse proxy, and API throughput and background job queue sizes for the photo service — so that I can diagnose performance issues and track usage patterns beyond simple up/down status.

**Why this priority**: Infrastructure metrics (CPU/memory) tell you a container is struggling but not why. Application metrics reveal the root cause — high error rates, growing job backlogs, slow responses. Caddy and Immich both support native metrics with minimal configuration, making this a high-value, low-effort addition.

**Independent Test**: Generate HTTP traffic through the reverse proxy, verify that the Caddy dashboard shows request rates and error breakdowns. Upload photos to Immich, verify the Immich dashboard shows API request counts and job queue sizes.

**Acceptance Scenarios**:

1. **Given** Caddy metrics are enabled on the reverse proxy container, **When** the operator opens the reverse proxy dashboard, **Then** the dashboard displays HTTP request rate, response time distribution, error rate (4xx/5xx breakdown), and upstream health status with data refreshing every 30 seconds.
2. **Given** Caddy is experiencing a high rate of 5xx errors (above 5% of total responses for 5 minutes), **When** the alert evaluation runs, **Then** the operator receives a warning email about elevated error rates.
3. **Given** Immich telemetry is enabled, **When** the operator opens the photo service dashboard, **Then** the dashboard displays API request rate, background job queue sizes (e.g., thumbnail generation backlog), and processing throughput.
4. **Given** the Immich thumbnail generation backlog grows beyond 500 items for 10 minutes, **When** the alert evaluation runs, **Then** the operator receives a warning email about the growing job backlog.
5. **Given** the reverse proxy or photo service metrics endpoint becomes unreachable, **When** the general service-down alert fires, **Then** the alert correctly identifies the application metrics endpoint (not just the infrastructure agent) as the failed target.

---

### User Story 4 — Extensible Monitoring Onboarding (Priority: P2)

As a homelab administrator, I want adding monitoring for a new service to require only a declaration in that service's own configuration — without editing the central monitoring infrastructure — so that monitoring scales naturally as I add services and no central bottleneck exists.

**Why this priority**: The current Prometheus config has only 2 hardcoded scrape targets. Every new service would require manually editing the monitoring stack's configuration files, creating tight coupling. An extensible pattern where each service declares its own monitoring contract makes the monitoring system maintainable long-term and prevents the monitoring role from becoming a monolith that knows about every service.

**Independent Test**: Add a mock monitoring declaration to a service role's configuration. Re-deploy the monitoring stack. Verify the new target appears in the scrape configuration, its alert rules are loaded, and its dashboard is provisioned — all without any edits to the monitoring role itself.

**Acceptance Scenarios**:

1. **Given** a service role declares a monitoring contract (metrics endpoints, alert rules, dashboard reference), **When** the monitoring stack is deployed, **Then** the monitoring system automatically generates scrape configuration for each declared endpoint, loads the declared alert rules, and provisions the declared dashboard — without any modification to the monitoring role's code.
2. **Given** two services each declare their own monitoring contracts, **When** the monitoring stack is deployed, **Then** both services' metrics, alerts, and dashboards are independently present and functional.
3. **Given** a service's monitoring contract is disabled (set to inactive), **When** the monitoring stack is redeployed, **Then** that service's scrape targets, alert rules, and dashboard are removed from the active configuration while all other services remain unaffected.
4. **Given** a new service is added to the homelab with a monitoring contract, **When** the monitoring stack playbook runs, **Then** the new service's targets appear in the scrape target list and its dashboard is accessible — confirming zero-touch onboarding from the monitoring side.

---

### User Story 5 — Monitoring Stack Version Alignment (Priority: P2)

As a homelab administrator, I want the monitoring stack's pinned defaults file to match the already-deployed current stable versions and for the new configuration templates introduced by this feature to be validated against those versions, so that the codebase is internally consistent and the overhaul does not inadvertently downgrade components.

**Why this priority**: The monitoring stack group_vars already specify current stable versions (Prometheus v3.8.1, Grafana 12.3.1, Telegraf 1.37.0, Alertmanager v0.30.0), but the role defaults file still pins late-2023 versions (Prometheus v2.48.0, Grafana 10.2.0, Telegraf 1.28, Alertmanager v0.26.0). This discrepancy risks confusion during implementation. The real work here is ensuring the new self-registration templates, alert rules, and dashboard JSON are compatible with the already-running v3.x/12.x stack — not performing the version upgrade itself.

**Independent Test**: Verify that `ansible/roles/monitoring_stack/defaults/main.yml` version pins match `ansible/group_vars/monitoring/vars.yml`. Verify the Synology dashboard, Synology alerts, and email alerting continue to function with the new configuration templates.

**Acceptance Scenarios**:

1. **Given** the monitoring stack role defaults previously pinned outdated versions, **When** this feature is complete, **Then** the defaults file version pins match the group_vars values (Prometheus v3.8.1, Grafana 12.3.1, Telegraf 1.37.0, Alertmanager v0.30.0) — eliminating the defaults/group_vars version mismatch.
2. **Given** new Prometheus configuration templates are introduced (self-registration scrape configs, additional alert rule files), **When** the monitoring stack starts, **Then** no configuration compatibility errors appear in the logs and all scrape targets report successful scrapes — confirming compatibility with Prometheus 3.x syntax.
3. **Given** new Grafana dashboard JSON files are introduced (infrastructure overview, reverse proxy, photo service), **When** the operator accesses the dashboards, **Then** they render correctly on Grafana 12.x — confirming no deprecated panel types or query syntax are used.

---

### User Story 6 — Uptime Kuma Decommission (Priority: P2)

As a homelab administrator, I want Uptime Kuma fully removed from the codebase, the monitoring container, and all cross-role references, so that I no longer maintain a redundant monitoring tool alongside the unified alerting system and no dead code paths remain.

**Why this priority**: Once unified alerting (US-2) is in place, Uptime Kuma provides no additional value. Keeping it running wastes container resources and creates confusion about which system is authoritative. However, removal depends on the replacement being functional first. Additionally, the `proxmox_backup` role has a `kuma_only` email mode with code that references Uptime Kuma push monitors — this dead code path must be cleaned up.

**Independent Test**: After removal, verify no Uptime Kuma processes run, no Kuma-related files exist in the codebase (including cross-role references), and both the monitoring playbook and the proxmox backup playbook still succeed.

**Acceptance Scenarios**:

1. **Given** the Uptime Kuma Ansible role directory previously existed, **When** this feature is complete, **Then** the directory `ansible/roles/uptime_kuma/` no longer exists in the repository.
2. **Given** Uptime Kuma variables were defined in monitoring host vars and vault, **When** this feature is complete, **Then** all Uptime Kuma-related variables (`monitoring_targets`, `uptime_kuma_api_url`, `uptime_kuma_api_wait_timeout`, `uptime_kuma_api_retry_delay`, `uptime_kuma_api_max_retries`, `uptime_kuma_admin_user`, `uptime_kuma_admin_password`) are removed.
3. **Given** the monitoring playbook is run after Uptime Kuma removal, **When** the playbook completes, **Then** no errors reference missing Uptime Kuma roles or variables, and the monitoring stack functions correctly.
4. **Given** the `proxmox_backup` role had a `kuma_only` email mode with `configure_kuma.yml` that referenced Uptime Kuma push monitors, **When** this feature is complete, **Then** the `kuma_only` mode code, `configure_kuma.yml` task file, and KUMA_URL template variable are removed from the `proxmox_backup` role, and the `proxmox_backup_email_mode` options no longer include `kuma_only`.
5. **Given** operational documentation in `docs/operations.md` referenced "Kuma Migration" and "Current Mode: kuma_only", **When** this feature is complete, **Then** those references are updated to reflect the current state (Uptime Kuma decommissioned, email mode disabled/enabled only).

---

### Edge Cases

- **What happens if an infrastructure metrics agent fails on a single container?** The service-down alert fires for that specific container's agent. Other containers' metrics continue unaffected. The operator investigates and restarts the agent.
- **What happens during a monitoring stack redeployment?** Brief metrics gaps (1–2 minutes) are expected. No false alerts should fire because alert thresholds require sustained failure (2+ minutes). Historical data is preserved across redeployment.
- **What happens if a service exposes metrics on a port that's unreachable from the monitoring container?** The scrape target shows as DOWN, and the service-down alert fires. The operator must ensure network connectivity between the monitoring container and service containers on metrics ports.
- **What happens if two services declare conflicting monitoring contracts (same scrape job name)?** The monitoring stack should fail deployment with a clear error rather than silently overwriting one service's configuration. Each service's monitoring contract must use a unique job name.
- **What happens when a major Prometheus version upgrade changes configuration syntax?** The deployment should fail fast with a clear configuration error. The operator reviews the migration guide and updates templates before retrying.
- **What happens if the email notification system is down when an alert fires?** The alert management system logs the failed delivery. The alert remains active and delivery is retried on the next evaluation cycle. The operator can view pending alerts in the alert status interface.
- **What happens if a service's monitoring contract declares an alert rule with invalid syntax?** The monitoring stack should fail deployment with a validation error identifying the specific service and rule, rather than deploying a broken configuration.
- **What happens to existing Synology metrics and alerts during the overhaul?** The existing Synology SNMP integration (Telegraf), three Synology alert rules, and the Synology NAS dashboard must be preserved unchanged. They continue to function alongside the new capabilities.
- **What happens when the generic ServiceDown alert fires alongside the existing SynologyNASDown alert?** Both would fire if the Telegraf SNMP target goes down — the generic `up == 0` rule and the Synology-specific `SynologyNASDown` rule. The alerting system must use inhibition rules so that the more specific `SynologyNASDown` alert takes precedence and the generic `ServiceDown` alert is suppressed for Synology targets, avoiding duplicate notifications.
- **What happens when an infrastructure metrics agent is unreachable but the service container itself is healthy?** Both the agent-down alert and any threshold alerts for that container become invalid. The alerting system should use inhibition rules to suppress infrastructure threshold alerts (CPU, memory, disk) for a container when that container's agent is unreachable, since the threshold data is stale.
- **What happens to historical Uptime Kuma data when it is decommissioned?** Historical uptime data stored in Uptime Kuma's SQLite database on the monitoring container is discarded. No export or migration is performed because the Prometheus-based unified alerting system provides equivalent availability tracking via the `up` metric going forward. The operator accepts loss of pre-decommission uptime history from the Kuma tool.

## Requirements *(mandatory)*

### Functional Requirements

#### Infrastructure Metrics

- **FR-001**: System MUST deploy an infrastructure metrics agent to every service container in the homelab (AdGuard at 192.168.1.210, Reverse Proxy at 192.168.1.211, Home Assistant at 192.168.1.212, Immich at 192.168.1.213, Monitoring at 192.168.1.214, Jellyfin at 192.168.1.215, Nextcloud at 192.168.1.216). *(traces to US-1)*
- **FR-002**: Each infrastructure metrics agent MUST expose CPU, disk, filesystem, memory, network, and system uptime metrics. *(traces to US-1)*
- **FR-003**: The monitoring system MUST automatically scrape infrastructure metrics from all service containers without hardcoding individual targets in the monitoring configuration. *(traces to US-1, US-4)*

#### Application-Level Metrics

- **FR-004**: The reverse proxy (Caddy) MUST expose a metrics endpoint accessible from the monitoring container, providing HTTP request counts, response time histograms, and error code breakdowns. *(traces to US-3)*
- **FR-005**: The photo service (Immich) MUST expose metrics endpoints accessible from the monitoring container, providing API request metrics and background job queue statistics. *(traces to US-3)*
- **FR-006**: Application metrics endpoints MUST be accessible only within the LAN (not exposed via the public-facing reverse proxy or HTTPS domains). *(traces to US-3)*

#### Self-Registration Pattern

- **FR-007**: Each service role MUST be able to declare its own monitoring contract — specifying metrics endpoints (host, port, path, scrape interval), alert rules (condition, threshold, severity, notification text), and dashboard reference — as part of its own configuration, not in the central monitoring role. *(traces to US-4)*
- **FR-008**: The monitoring system MUST dynamically generate its scrape configuration by aggregating monitoring contracts from all service roles in the inventory. *(traces to US-4)*
- **FR-009**: The monitoring system MUST dynamically generate alert rules by aggregating alert definitions from all service monitoring contracts, alongside infrastructure-wide alert rules. *(traces to US-4)*
- **FR-010**: The monitoring system MUST provision dashboards by collecting dashboard definitions from service roles that declare them. *(traces to US-4)*
- **FR-011**: Disabling a service's monitoring contract (setting enabled to false) MUST remove that service's scrape targets, alert rules, and dashboard from the active monitoring configuration on the next deployment. *(traces to US-4)*

#### Alerting

- **FR-012**: System MUST include a generic service-down alert rule that fires when any scrape target is unreachable for 2 minutes. This single rule replaces all per-service HTTP checks previously handled by Uptime Kuma. *(traces to US-2)*
- **FR-013**: System MUST include infrastructure alert rules for: high CPU usage (above 85% for 10 minutes), high memory usage (above 85% for 5 minutes), disk space warning (above 85% for 5 minutes), and disk space critical (above 95% for 2 minutes) — applied across all containers with infrastructure metrics. *(traces to US-1)*
- **FR-014**: All alerts MUST be delivered via the existing email (SMTP) notification channel configured in the monitoring stack. *(traces to US-1, US-2, US-3)*
- **FR-015**: Each service's monitoring contract MAY declare service-specific alert rules (e.g., Caddy high error rate, Immich job backlog) that are loaded alongside infrastructure-wide rules. *(traces to US-3, US-4)*

#### Dashboards

- **FR-016**: System MUST provide a new infrastructure overview dashboard showing CPU, memory, disk, and network metrics across all service containers on a single view. *(traces to US-1)*
- **FR-017**: System MUST provide a new reverse proxy dashboard showing HTTP request rate, response time distribution, error rate breakdown, and upstream health. *(traces to US-3)*
- **FR-018**: System MUST provide a new photo service dashboard showing API request rates, background job queue sizes, and processing throughput. *(traces to US-3)*
- **FR-019**: The existing Synology NAS dashboard and its three alert rules MUST be preserved without modification. *(traces to US-5)*

#### Uptime Kuma Removal

- **FR-020**: The Uptime Kuma Ansible role (`ansible/roles/uptime_kuma/`) MUST be removed from the repository. *(traces to US-6)*
- **FR-021**: All Uptime Kuma-related variables MUST be removed from `ansible/host_vars/monitoring/vars.yml` (monitoring_targets, uptime_kuma_api_url, uptime_kuma_api_wait_timeout, uptime_kuma_api_retry_delay, uptime_kuma_api_max_retries). *(traces to US-6)*
- **FR-022**: All Uptime Kuma-related secrets MUST be removed from `ansible/group_vars/monitoring/vault.yml` (uptime_kuma_admin_user, uptime_kuma_admin_password). *(traces to US-6)*
- **FR-023**: The Uptime Kuma container on the monitoring LXC MUST be stopped and removed as part of deployment. *(traces to US-6)*
- **FR-024**: The `proxmox_backup` role's Uptime Kuma integration MUST be removed: the `configure_kuma.yml` task file, the `kuma_only` option from `proxmox_backup_email_mode`, and the `KUMA_URL` template variable in `proxmox-backup.conf.j2`. *(traces to US-6)*
- **FR-025**: Operational documentation (`docs/operations.md`) MUST be updated to remove references to Uptime Kuma migration and the `kuma_only` email mode. *(traces to US-6)*

#### Version Alignment

- **FR-026**: The monitoring stack role defaults (`ansible/roles/monitoring_stack/defaults/main.yml`) MUST be updated to match the already-deployed versions in group_vars (Prometheus v3.8.1, Grafana 12.3.1, Telegraf 1.37.0, Alertmanager v0.30.0), eliminating the defaults/group_vars version mismatch. *(traces to US-5)*
- **FR-027**: All new configuration templates (scrape configs, alert rules, dashboard JSON) MUST be compatible with the currently running Prometheus 3.x and Grafana 12.x — no deprecated syntax or features. *(traces to US-5)*

#### Alerting Hygiene

- **FR-028**: The alerting configuration MUST include inhibition rules to prevent the generic ServiceDown alert from firing alongside the more specific SynologyNASDown alert for the same target, avoiding duplicate notifications. *(traces to US-2)*
- **FR-029**: The alerting configuration MUST include inhibition rules to suppress infrastructure threshold alerts (CPU, memory, disk) for a specific container when that container's infrastructure metrics agent is unreachable, since threshold data is stale. *(traces to US-1, US-2)*
- **FR-030**: The monitoring stack deployment MUST validate alert rule syntax before activating new configuration. If any service's monitoring contract contains an invalid alert rule, deployment MUST fail with an error identifying the specific service and rule. *(traces to US-4)*

#### IaC & Operations

- **FR-031**: All changes MUST be deployed via Ansible roles and playbooks (no manual configuration of the monitoring stack). *(traces to all stories)*
- **FR-032**: The monitoring playbook MUST be idempotent — re-running it without changes produces no unexpected modifications. *(traces to all stories)*
- **FR-033**: No secrets (SMTP credentials, Grafana admin password, SNMP credentials) MUST be committed to the git repository in plaintext. *(traces to all stories)*

### Key Entities

- **Monitoring Contract**: A per-service declaration that defines how a service participates in monitoring. Contains: enabled flag, list of metrics endpoints (each with host, port, path, scrape interval), list of alert rules (each with name, condition expression, duration, severity, summary text), and an optional dashboard reference. Declared in each service role's configuration. Aggregated by the monitoring stack.
- **Infrastructure Metrics Agent**: A lightweight process running on each service container that exposes system-level metrics (CPU, memory, disk, network). One instance per container.
- **Scrape Target**: A network endpoint (host:port/path) that the monitoring system periodically queries to collect metrics. Each monitoring contract declares one or more scrape targets.
- **Alert Rule**: A condition with a threshold, evaluation duration, severity level, and notification text. When the condition is sustained for the specified duration, the alert fires and notification is sent. Rules come from two sources: infrastructure-wide (always present) and per-service (declared in monitoring contracts).
- **Dashboard**: A visual display of metrics for a specific service or infrastructure overview. JSON definition files stored alongside the service role that owns them. Provisioned automatically by the monitoring stack.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Operator can view live CPU, memory, disk, and network metrics for all 7 service containers on a single infrastructure dashboard within 5 minutes of deployment completion.
- **SC-002**: Operator receives an email alert within 5 minutes when any monitored service becomes unreachable (replaces Uptime Kuma's HTTP checks with zero additional configuration per service).
- **SC-003**: Operator can view Caddy request rates and error breakdowns on a dedicated reverse proxy dashboard, with data refreshing within 30 seconds of actual traffic.
- **SC-004**: Operator can view Immich API throughput and job queue sizes on a dedicated photo service dashboard, with data refreshing within 30 seconds.
- **SC-005**: Adding monitoring for a future service requires changes only to that service's role — verified by confirming that zero lines in the monitoring role's code reference Caddy or Immich by name.
- **SC-006**: No Uptime Kuma process, role directory, variable, secret, or cross-role reference (including `proxmox_backup` role's `kuma_only` code path and `docs/operations.md` Kuma references) exists in the codebase or on the monitoring container after deployment.
- **SC-007**: The monitoring stack role defaults file version pins match the group_vars values (Prometheus v3.8.1, Grafana 12.3.1, Telegraf 1.37.0, Alertmanager v0.30.0) — no version mismatch between the two layers.
- **SC-008**: Existing Synology NAS dashboard displays data correctly and all three Synology alert rules evaluate without errors after the overhaul.
- **SC-009**: Re-running the monitoring Ansible playbook without changes produces an idempotent result (no unexpected changes).
- **SC-010**: Infrastructure alert rules fire correctly: disk warning at >85%, disk critical at >95%, memory warning at >85%, CPU warning at >85% sustained — verified by test scenarios or threshold inspection.
- **SC-011**: When the Telegraf SNMP target goes down, only the SynologyNASDown alert fires — the generic ServiceDown alert is suppressed for that target via inhibition rules (no duplicate alerts).
- **SC-012**: The monitoring LXC's total resource consumption (all monitoring stack components combined) does not exceed 4 GB RAM and 2 vCPU under normal operation with all 7 infrastructure agents + 2 application metrics endpoints scraped.

## Assumptions

- **A-001**: All service containers (192.168.1.210–216) are reachable from the monitoring container (192.168.1.214) on the 192.168.1.0/24 subnet without firewall restrictions on metrics ports.
- **A-002**: The existing SMTP email notification channel (configured in Alertmanager) continues to function for all new alert rules. No new notification channels are needed.
- **A-003**: Caddy supports native Prometheus-format metrics via a configuration directive. No external exporter is needed.
- **A-004**: Immich supports native Prometheus-format metrics via environment variable configuration. No external exporter is needed.
- **A-005**: The infrastructure metrics agent can run as a standalone binary on containers that do not have Docker installed (e.g., Jellyfin, Reverse Proxy).
- **A-006**: Home Assistant is not yet deployed (placeholder role only — `ansible/roles/homeassistant/tasks/main.yml` is a debug placeholder) and is excluded from application-level monitoring in this iteration. The infrastructure metrics agent is still deployed to its container if the container exists.
- **A-007**: The existing Telegraf SNMP bridge for Synology NAS continues to function unchanged alongside the new components.
- **A-008**: The monitoring stack is already running Prometheus v3.8.1 (confirmed in `ansible/group_vars/monitoring/vars.yml`). The Prometheus v2 → v3 migration has already occurred. New configuration templates must target Prometheus 3.x syntax from the start.
- **A-009**: The monitoring stack is already running Grafana 12.3.1 (confirmed in `ansible/group_vars/monitoring/vars.yml`). The role defaults file (`ansible/roles/monitoring_stack/defaults/main.yml`) still pins Grafana 10.2.0, but group_vars override defaults. The defaults file needs alignment, not a version upgrade operation.
- **A-010**: The monitoring playbook does not currently include the Uptime Kuma role (confirmed by inspection of `ansible/playbooks/monitoring.yml` — roles are `lxc_base`, `mdns_base`, `monitoring_stack`), so removing the Uptime Kuma role directory will not break the playbook.
- **A-011**: The `proxmox_backup` role's `proxmox_backup_email_mode` is currently set to `"disabled"` in `ansible/group_vars/proxmox_hosts/vars.yml` (not `kuma_only`), meaning the Kuma push integration is already inactive in practice. Removing the `kuma_only` code path will not break the currently running backup system.
- **A-012**: The `docs/operations.md` documentation claiming "Current Mode: kuma_only (Email disabled, Kuma active)" is stale and does not match the actual group_vars setting of `"disabled"`. This documentation drift is corrected as part of the Uptime Kuma decommission.

## Non-Functional Requirements

- **NFR-001**: Each infrastructure metrics agent instance MUST consume no more than 50 MB RAM and negligible CPU on the service container it runs on — verified by inspection of agent resource usage on at least one container after deployment.
- **NFR-002**: The monitoring LXC's total resource consumption (all stack components: Prometheus, Grafana, Telegraf, Alertmanager) MUST remain within 4 GB RAM and 2 vCPU under normal operation with all targets scraped. *(aligns with feature 017 resource allocation)*
- **NFR-003**: The infrastructure overview dashboard MUST load within 5 seconds when displaying a 24-hour time range.
- **NFR-004**: Alert delivery latency MUST be less than 5 minutes from condition trigger to email receipt — accounting for scrape interval (30s), evaluation interval (30s), alert threshold duration (2+ minutes), and SMTP delivery.
- **NFR-005**: Adding 7 infrastructure agent targets + 2 application metrics endpoints to Prometheus MUST NOT cause TSDB disk usage to exceed 25 GB with 15-day retention (building on the existing ~10 GB estimate from feature 017).

## Out of Scope

- **External exporters** for services without native metrics (Nextcloud, Jellyfin, AdGuard, Proxmox VE) — deferred to a future iteration after this foundation is established.
- **Healthcheck script removal** — the existing Python healthcheck script on systemd timer is retained as-is. It is independent, harmless, and provides a safety net during the transition. Removal deferred to a future iteration.
- **Security monitoring** — fail2ban, Blackbox Exporter, certificate lifecycle monitoring, DNS anomaly detection, authentication failure correlation — all deferred to a future iteration.
- **Log aggregation** (e.g., centralized log collection and search) — entirely out of scope for the monitoring overhaul.
- **Home Assistant metrics** — HA is a placeholder role, not yet deployed. No monitoring contract is created for it.
- **Proxmox host metrics** — metrics from the Proxmox hypervisor itself (as opposed to its LXC guests) require a dedicated exporter, deferred to a future iteration.
- **High availability** — a single monitoring stack instance is sufficient for the homelab. No redundancy or failover.
- **Public internet exposure** — monitoring dashboards and metrics endpoints remain LAN-only.
- **New notification channels** — no Slack, Discord, PagerDuty, or push notification integrations. Email-only per existing setup.
- **Recording rules or complex aggregations** — deferred to the security monitoring iteration where they are needed for anomaly detection.
- **Push-based heartbeat monitoring replacement** — the `proxmox_backup` role previously had an Uptime Kuma push monitor for backup success heartbeats. This push-based pattern (where the backup script pushes "I'm alive" to a monitor) is fundamentally different from Prometheus's pull-based model. Implementing a push-gateway or dead-man's-switch replacement is deferred. The backup script's success/failure is already logged, and the operator can verify backup health via the existing systemd timer status.

## Constraints

- **C-001**: Must follow existing IaC patterns — Ansible roles and playbooks for all configuration, secrets in Ansible Vault, idempotent deployments.
- **C-002**: Must not break the existing Synology SNMP monitoring chain (Telegraf → Prometheus → Grafana dashboard + 3 alert rules).
- **C-003**: Must not expose metrics endpoints via the public HTTPS reverse proxy — metrics are internal LAN-only traffic.
- **C-004**: Infrastructure metrics agents must work on containers without Docker (Jellyfin and Reverse Proxy run services natively, not in Docker).
- **C-005**: Must comply with the constitution's separation of concerns: Terraform owns container existence, Ansible owns configuration inside containers.
- **C-006**: Must comply with the constitution's secrets policy: no plaintext secrets in the repository.
- **C-007**: Must comply with the constitution's dual-provisioning parity: deployable from both CI/CD and developer laptop.

## Dependencies

- **D-001**: Feature 017 (Synology Metrics) — the existing monitoring stack, Prometheus, Grafana, Telegraf, and Alertmanager are already deployed and functional. This feature builds on that foundation.
- **D-002**: Feature 039 (HTTPS Services) — Caddy is configured with HTTPS for all services. Metrics exposure must not interfere with the existing Caddyfile structure.
- **D-003**: Existing Ansible roles for each service (reverse_proxy, immich, jellyfin, nextcloud, adguard, homeassistant, lxc_base) — monitoring contracts will be added to these roles' defaults.
- **D-004**: Existing Ansible Vault for the monitoring group — secrets for Uptime Kuma removal and any new credentials.
- **D-005**: Network connectivity between monitoring LXC (192.168.1.214) and all service LXCs on metrics-specific ports.
- **D-006**: Feature 013 (Proxmox Config Backup) — the `proxmox_backup` role has Uptime Kuma references (`configure_kuma.yml`, `kuma_only` mode) that must be cleaned up as part of the Uptime Kuma decommission.

## Decision Log

| # | Ambiguity | Decision | Rationale |
|---|-----------|----------|-----------|
| DL-01 | How many iterations should this spec cover? | Iteration A only (foundation). Iterations B (external exporters, healthcheck removal) and C (security monitoring) are explicitly out of scope. | Iteration A establishes the extensible pattern that B and C build on. Shipping A first delivers immediate value and validates the self-registration approach before committing to the full roadmap. |
| DL-02 | Should the healthcheck script be removed? | No. Retain the existing Python healthcheck script as-is. | It is independent of the monitoring stack, adds no maintenance burden in this iteration, and provides a safety net during the transition. Removal is deferred to a future iteration when all services have full metrics coverage. |
| DL-03 | Which services get native application metrics? | Only Caddy (reverse proxy) and Immich (photo service). | These are the only two services in the homelab that expose Prometheus-format metrics natively with minimal configuration changes. All others (Nextcloud, Jellyfin, AdGuard, Proxmox VE) require external exporters, which are deferred. |
| DL-04 | Should Home Assistant get a monitoring contract? | No. Excluded from this iteration. | The HA Ansible role is a placeholder — the service is not yet deployed. Cannot monitor what does not exist. The infrastructure metrics agent will be deployed to the container if it exists, but no HA-specific monitoring contract is created. |
| DL-05 | What alert thresholds to use for infrastructure alerts? | 85% warning, 95% critical for disk. 85% warning for memory and CPU. 2 minutes for service-down. | Industry-standard thresholds that balance early warning with noise reduction. Aligned with the existing Synology volume alert threshold (85%). The 2-minute service-down threshold matches the existing Uptime Kuma `alert_down_threshold` of 2 minutes. |
| DL-06 | Should Uptime Kuma be removed in this iteration or deferred? | Remove in this iteration. | Once the Prometheus `up` metric + generic ServiceDown alert rule is in place, Uptime Kuma provides zero additional value. Keeping it running wastes resources and creates confusion about which system is authoritative. The monitoring playbook already does not include the Uptime Kuma role, making removal low-risk. |
| DL-07 | Should version bumps be included or done separately? | Version bumps are already done — only defaults-file alignment is needed. | Inspection of `ansible/group_vars/monitoring/vars.yml` confirms Prometheus v3.8.1, Grafana 12.3.1, Telegraf 1.37.0, Alertmanager v0.30.0 are already deployed. The role defaults file still pins late-2023 versions, creating a mismatch. This feature aligns the defaults to match group_vars (housekeeping) and ensures new templates target the v3.x/12.x APIs. No upgrade operation is needed. |
| DL-08 | What Grafana version is actually running? | Grafana 12.3.1, confirmed in `ansible/group_vars/monitoring/vars.yml` with `grafana_domain: "grafana.hus-sky.no"` and `grafana_protocol: "https"`. The defaults file pins 10.2.0 but group_vars override it. | Resolved by inspecting `ansible/group_vars/monitoring/vars.yml`. The HTTPS services feature (039) updated the Grafana domain and protocol. The version bump was applied to group_vars at some prior point. |
| DL-09 | Should the infrastructure metrics agent run as a standalone binary or Docker container? | Standalone binary. | Some LXCs (Jellyfin, Reverse Proxy) run services natively without Docker. A standalone binary works everywhere regardless of whether Docker is installed. |
| DL-10 | Should the metrics agent be deployed via `lxc_base` or individually per service? | Deploy as a shared base role included in every service's playbook. | This ensures every container gets infrastructure metrics automatically as new services are added, without requiring per-service configuration. Aligns with the extensible pattern philosophy. |

| DL-11 | How to handle ServiceDown/SynologyNASDown alert overlap? | Use Alertmanager inhibition rules so that the more specific `SynologyNASDown` alert suppresses the generic `ServiceDown` alert for Synology targets. | The existing alertmanager config already uses inhibition (inhibit disk alerts when NAS is down). Extending this pattern to suppress the generic ServiceDown for Synology targets avoids duplicate emails while preserving both rules for their distinct use cases. |
| DL-12 | Should infrastructure threshold alerts be inhibited when agent is unreachable? | Yes. Add inhibition rules that suppress CPU/memory/disk threshold alerts when the agent's `up` metric is 0. | Stale threshold data should not trigger false alerts. Inhibiting threshold alerts when the agent is down is standard practice and reduces noise. |
| DL-13 | What happens to Uptime Kuma historical data? | Discarded. No export or migration. | The Prometheus `up` metric provides equivalent availability tracking going forward. The Kuma SQLite database is on the monitoring LXC (Docker volume) and contains only 4 monitor targets with limited history. The value of preserving this data does not justify the complexity. |
| DL-14 | What about the proxmox_backup role's Kuma integration? | Remove the `kuma_only` code path entirely. | The `proxmox_backup_email_mode` is already set to `"disabled"` in group_vars (not `kuma_only`), so the Kuma code path is dead. The default in the role's `defaults/main.yml` is `kuma_only`, but the group_vars override makes it inactive. Removing the dead code prevents future confusion and eliminates a dangling dependency on the deleted Uptime Kuma role. |
| DL-15 | Should the proxmox backup heartbeat monitoring be replaced? | No — deferred to a future iteration. | The push-based heartbeat pattern (backup script pushes "I'm alive") is fundamentally different from Prometheus's pull-based model. Implementing a push-gateway or dead-man's-switch is non-trivial and orthogonal to the monitoring overhaul's core goals. The backup script logs success/failure to systemd journal, which is sufficient for now. |

## Open Questions

None — all ambiguities resolved in Decision Log above.

---

## Self-Critique

### Strengths
- Comprehensive user stories with well-structured Given/When/Then acceptance scenarios
- Clear separation of P1 vs P2 priorities with justified rationale
- Extensive edge case coverage (8 original + 3 added in revision)
- Decision log resolves all ambiguities with documented rationale
- Constitution cross-check is thorough (secrets policy, separation of concerns, dual-provisioning parity)

### Issues Found (revision pass)
- **[severity: high] Factual inaccuracy — version update story (US-5)**: The original spec claimed the stack "runs versions from late 2023" but `ansible/group_vars/monitoring/vars.yml` already has Prometheus v3.8.1, Grafana 12.3.1, Telegraf 1.37.0, Alertmanager v0.30.0. US-5 was framed as a version upgrade when the actual work is defaults-file alignment and template compatibility. **Fixed**: Rewrote US-5 as "Version Alignment", corrected narrative, updated acceptance scenarios and DL-07/DL-08.
- **[severity: high] Missing cross-role Uptime Kuma dependencies**: The `proxmox_backup` role has `configure_kuma.yml`, a `kuma_only` email mode, and KUMA_URL template variable — all referencing Uptime Kuma. `docs/operations.md` also references Kuma. None of these were covered by FR-020 through FR-023. **Fixed**: Added FR-024, FR-025, US-6 acceptance scenarios 4–5, dependency D-006, assumptions A-011/A-012, and decision DL-14.
- **[severity: high] ServiceDown/SynologyNASDown alert duplication**: FR-012's generic `up == 0` alert would fire simultaneously with the existing `SynologyNASDown` alert for the same target, causing duplicate emails. **Fixed**: Added FR-028 (inhibition rules), edge case, SC-011, and decision DL-11.
- **[severity: medium] No non-functional requirements**: Feature 017 had detailed NFRs. Feature 040 adds 7 agents + 2 app metrics endpoints + 3 dashboards with zero NFRs. **Fixed**: Added NFR-001 through NFR-005.
- **[severity: medium] Missing alert inhibition for stale threshold data**: No requirement to suppress CPU/memory/disk alerts when the agent itself is down. **Fixed**: Added FR-029 and decision DL-12.
- **[severity: medium] Uptime Kuma data disposition not specified**: Spec said "remove" but didn't address historical data. **Fixed**: Added edge case and decision DL-13.
- **[severity: medium] Missing alert rule validation requirement**: Edge case mentioned it but no FR covered it. **Fixed**: Added FR-030.
- **[severity: low] Assumption A-009 hedged when fact was known**: Group_vars clearly show Grafana 12.3.1. **Fixed**: Stated the confirmed version.
- **[severity: low] Push-based heartbeat monitoring gap not acknowledged**: Removing Kuma eliminates the proxmox backup push monitor pattern with no replacement. **Fixed**: Added to Out of Scope with decision DL-15.

### Verdict
ACCEPT (after revisions applied above)
