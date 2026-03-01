# Feature Specification: Monitoring & Observability Overhaul

**Feature Branch**: `040-monitoring-overhaul`
**Created**: 2026-03-01
**Status**: Draft
**Input**: User description: "Monitoring observability overhaul"

## Overview

The homelab monitoring stack currently has minimal coverage: Prometheus scrapes only itself and a Telegraf SNMP bridge, Grafana has a single Synology NAS dashboard, and three Synology-focused alert rules exist. A separate Uptime Kuma instance monitors four services via HTTP checks, and an independent Python healthcheck script watches seven services. This feature overhauls the monitoring foundation to provide infrastructure-level metrics from every service container, application-level metrics from services that natively expose them, a unified alerting framework that replaces Uptime Kuma, and an extensible pattern that makes onboarding future services automatic.

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

### User Story 5 — Monitoring Stack Modernization (Priority: P2)

As a homelab administrator, I want the monitoring stack components updated to current stable versions, so that I benefit from security patches, performance improvements, and new features rather than running software that is multiple major versions behind.

**Why this priority**: The current monitoring stack runs versions from late 2023 (Prometheus v2.48.0, Grafana 10.2.0, Telegraf 1.28, Alertmanager v0.26.0). Running outdated software accumulates security risk and misses improvements. However, this is lower priority than new capabilities because the existing versions are functional.

**Independent Test**: Deploy the updated stack, verify all existing functionality (Synology dashboard, Synology alerts, email alerting) still works after the version upgrade. Confirm the running versions match the updated targets.

**Acceptance Scenarios**:

1. **Given** the monitoring stack is redeployed with updated component versions, **When** the operator checks the running versions, **Then** all components are at their latest stable major versions (Prometheus 3.x, Grafana 12.x, Telegraf 1.37.x, Alertmanager 0.28.x or newer).
2. **Given** the version upgrade is applied, **When** the operator views the existing Synology NAS dashboard, **Then** all panels display data correctly and the three existing Synology alert rules continue to evaluate without errors.
3. **Given** the version upgrade includes a major version change (Prometheus v2 → v3), **When** the monitoring stack starts, **Then** no configuration compatibility errors appear in the logs and all scrape targets report successful scrapes.

---

### User Story 6 — Uptime Kuma Decommission (Priority: P2)

As a homelab administrator, I want Uptime Kuma fully removed from the codebase and the monitoring container, so that I no longer maintain a redundant monitoring tool alongside the unified alerting system.

**Why this priority**: Once unified alerting (US-2) is in place, Uptime Kuma provides no additional value. Keeping it running wastes container resources and creates confusion about which system is authoritative. However, removal depends on the replacement being functional first.

**Independent Test**: After removal, verify no Uptime Kuma processes run, no Kuma-related files exist in the codebase, and the monitoring playbook still succeeds.

**Acceptance Scenarios**:

1. **Given** the Uptime Kuma Ansible role directory previously existed, **When** this feature is complete, **Then** the directory `ansible/roles/uptime_kuma/` no longer exists in the repository.
2. **Given** Uptime Kuma variables were defined in monitoring host vars and vault, **When** this feature is complete, **Then** all Uptime Kuma-related variables (`monitoring_targets`, `uptime_kuma_api_url`, `uptime_kuma_api_wait_timeout`, `uptime_kuma_api_retry_delay`, `uptime_kuma_api_max_retries`, `uptime_kuma_admin_user`, `uptime_kuma_admin_password`) are removed.
3. **Given** the monitoring playbook is run after Uptime Kuma removal, **When** the playbook completes, **Then** no errors reference missing Uptime Kuma roles or variables, and the monitoring stack functions correctly.

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

#### Version Updates

- **FR-024**: All monitoring stack components MUST be updated to current stable versions: Prometheus to latest 3.x, Grafana to latest 12.x, Telegraf to latest 1.37.x, Alertmanager to latest 0.28.x or newer. *(traces to US-5)*
- **FR-025**: Version updates MUST NOT break existing functionality — the Synology SNMP integration, existing alert rules, and Synology dashboard MUST continue to work after the upgrade. *(traces to US-5)*

#### IaC & Operations

- **FR-026**: All changes MUST be deployed via Ansible roles and playbooks (no manual configuration of the monitoring stack). *(traces to all stories)*
- **FR-027**: The monitoring playbook MUST be idempotent — re-running it without changes produces no unexpected modifications. *(traces to all stories)*
- **FR-028**: No secrets (SMTP credentials, Grafana admin password, SNMP credentials) MUST be committed to the git repository in plaintext. *(traces to all stories)*

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
- **SC-006**: No Uptime Kuma process, role directory, variable, or secret exists in the codebase or on the monitoring container after deployment.
- **SC-007**: All monitoring stack components run at their latest stable major versions (Prometheus 3.x, Grafana 12.x, Telegraf 1.37.x, Alertmanager 0.28.x+).
- **SC-008**: Existing Synology NAS dashboard displays data correctly and all three Synology alert rules evaluate without errors after the overhaul.
- **SC-009**: Re-running the monitoring Ansible playbook without changes produces an idempotent result (no unexpected changes).
- **SC-010**: Infrastructure alert rules fire correctly: disk warning at >85%, disk critical at >95%, memory warning at >85%, CPU warning at >85% sustained — verified by test scenarios or threshold inspection.

## Assumptions

- **A-001**: All service containers (192.168.1.210–216) are reachable from the monitoring container (192.168.1.214) on the 192.168.1.0/24 subnet without firewall restrictions on metrics ports.
- **A-002**: The existing SMTP email notification channel (configured in Alertmanager) continues to function for all new alert rules. No new notification channels are needed.
- **A-003**: Caddy supports native Prometheus-format metrics via a configuration directive. No external exporter is needed.
- **A-004**: Immich supports native Prometheus-format metrics via environment variable configuration. No external exporter is needed.
- **A-005**: The infrastructure metrics agent can run as a standalone binary on containers that do not have Docker installed (e.g., Jellyfin, Reverse Proxy).
- **A-006**: Home Assistant is not yet deployed (placeholder role only) and is excluded from monitoring in this iteration. The infrastructure metrics agent is still deployed to its container if the container exists.
- **A-007**: The existing Telegraf SNMP bridge for Synology NAS continues to function unchanged alongside the new components.
- **A-008**: Prometheus 3.x is backwards-compatible with the existing scrape configuration syntax or requires only minor, documented adjustments.
- **A-009**: The Grafana version currently running may already be newer than the version pinned in defaults (10.2.0 vs. potentially 12.x). The actual running version should be verified before applying the version bump.
- **A-010**: The monitoring playbook does not currently include the Uptime Kuma role (confirmed by inspection of `ansible/playbooks/monitoring.yml`), so removing the role directory will not break the playbook.

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

## Decision Log

| # | Ambiguity | Decision | Rationale |
|---|-----------|----------|-----------|
| DL-01 | How many iterations should this spec cover? | Iteration A only (foundation). Iterations B (external exporters, healthcheck removal) and C (security monitoring) are explicitly out of scope. | Iteration A establishes the extensible pattern that B and C build on. Shipping A first delivers immediate value and validates the self-registration approach before committing to the full roadmap. |
| DL-02 | Should the healthcheck script be removed? | No. Retain the existing Python healthcheck script as-is. | It is independent of the monitoring stack, adds no maintenance burden in this iteration, and provides a safety net during the transition. Removal is deferred to a future iteration when all services have full metrics coverage. |
| DL-03 | Which services get native application metrics? | Only Caddy (reverse proxy) and Immich (photo service). | These are the only two services in the homelab that expose Prometheus-format metrics natively with minimal configuration changes. All others (Nextcloud, Jellyfin, AdGuard, Proxmox VE) require external exporters, which are deferred. |
| DL-04 | Should Home Assistant get a monitoring contract? | No. Excluded from this iteration. | The HA Ansible role is a placeholder — the service is not yet deployed. Cannot monitor what does not exist. The infrastructure metrics agent will be deployed to the container if it exists, but no HA-specific monitoring contract is created. |
| DL-05 | What alert thresholds to use for infrastructure alerts? | 85% warning, 95% critical for disk. 85% warning for memory and CPU. 2 minutes for service-down. | Industry-standard thresholds that balance early warning with noise reduction. Aligned with the existing Synology volume alert threshold (85%). The 2-minute service-down threshold matches the existing Uptime Kuma `alert_down_threshold` of 2 minutes. |
| DL-06 | Should Uptime Kuma be removed in this iteration or deferred? | Remove in this iteration. | Once the Prometheus `up` metric + generic ServiceDown alert rule is in place, Uptime Kuma provides zero additional value. Keeping it running wastes resources and creates confusion about which system is authoritative. The monitoring playbook already does not include the Uptime Kuma role, making removal low-risk. |
| DL-07 | Should version bumps be included or done separately? | Include in this iteration. | The monitoring stack runs versions from late 2023. Updating during the overhaul is more efficient than doing a separate upgrade iteration, and avoids maintaining backwards compatibility with old versions for the new self-registration templates. |
| DL-08 | What Grafana version is actually running? | The defaults file says 10.2.0, but the running version may be newer (12.x). Actual running version must be verified before applying the bump. | The HTTPS services feature (039) added `grafana_domain` configuration, which may have updated the running Grafana version without updating the defaults file. The implementation must check the actual state to avoid a downgrade. |
| DL-09 | Should the infrastructure metrics agent run as a standalone binary or Docker container? | Standalone binary. | Some LXCs (Jellyfin, Reverse Proxy) run services natively without Docker. A standalone binary works everywhere regardless of whether Docker is installed. |
| DL-10 | Should the metrics agent be deployed via `lxc_base` or individually per service? | Deploy as a shared base role included in every service's playbook. | This ensures every container gets infrastructure metrics automatically as new services are added, without requiring per-service configuration. Aligns with the extensible pattern philosophy. |

## Open Questions

None — all ambiguities resolved in Decision Log above.
