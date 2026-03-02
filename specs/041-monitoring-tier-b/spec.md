# Feature Specification: Monitoring Tier B — Synology SNMP Fix & External Exporters

**Feature Branch**: `041-monitoring-tier-b`
**Created**: 2026-03-01
**Status**: Draft
**Input**: User description: "Monitoring Tier B: External Exporters and Synology SNMP Fix"

## Overview

The monitoring overhaul (Feature 040) established an extensible monitoring foundation: infrastructure metrics agents on every service container, application metrics for Caddy and Immich, self-registration via monitoring contracts, and unified alerting. However, the pre-existing Synology SNMP pipeline — originally delivered in Feature 017 — is broken: the Telegraf SNMP scrape target shows "UP" in Prometheus, yet zero `snmp_synology_*` metrics are produced. The Synology NAS dashboard displays no data, and the `SynologyNASDown` alert rule references a non-existent job label, preventing it from ever firing. Additionally, three services (AdGuard Home, Nextcloud, Jellyfin) currently have only container-level infrastructure metrics; they lack application-level visibility because they do not expose native Prometheus metrics and require external exporters.

This feature restores the Synology SNMP metrics pipeline to a working state (Priority 1), corrects the broken alert rules, and adds external service exporters for services that lack native metrics (Priority 2/3) — completing the deferred "external exporters" work identified in Feature 040's out-of-scope section.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Synology SNMP Metrics Restored (Priority: P1)

As a homelab administrator, I want the Synology NAS dashboard to display live storage capacity, disk health, CPU/memory usage, and network throughput metrics, so that I have visibility into NAS health and can detect capacity or hardware issues before they cause data loss.

**Why this priority**: The Synology NAS stores all critical homelab data (Immich photos, Nextcloud files, backups). The monitoring pipeline was originally delivered in Feature 017 but is currently producing zero application-level metrics despite the scrape target showing "UP." This is a regression that leaves the operator blind to NAS health — the most critical infrastructure component in the homelab.

**Independent Test**: Open the Synology NAS dashboard in Grafana. Verify that all panels (storage capacity, disk health, CPU/memory, network throughput) display live data from the NAS. Confirm that metric values update within 60 seconds of a change on the NAS (e.g., adding a file).

**Acceptance Scenarios**:

1. **Given** the monitoring stack is deployed with the Synology SNMP fix applied, **When** the operator opens the Synology NAS dashboard in Grafana, **Then** all dashboard panels display live metrics from the Synology NAS — including storage capacity per volume, disk health status, CPU usage, memory usage, and network throughput — with data no older than 60 seconds.
2. **Given** the Synology NAS is operational and SNMP is enabled, **When** the operator checks the Prometheus target list, **Then** the Telegraf SNMP scrape target shows "UP" status **and** the Prometheus metrics browser contains metrics matching the naming convention used by the Synology dashboard queries (currently zero such metrics exist).
3. **Given** the Telegraf SNMP pipeline is restored, **When** the operator adds a 1 GB file to a NAS volume, **Then** the storage capacity panel on the Synology dashboard reflects the increased usage within 90 seconds.
4. **Given** the monitoring stack is redeployed, **When** the Ansible playbook completes, **Then** the Telegraf configuration is updated and metrics collection resumes automatically — no manual intervention on the Synology NAS or monitoring container is required.

---

### User Story 2 — Synology Alert Rules Corrected (Priority: P1)

As a homelab administrator, I want all Synology-related alert rules to evaluate correctly against actual metrics, so that I receive email notifications when the NAS is unreachable, a volume is running low on space, or a disk reports health issues.

**Why this priority**: The `SynologyNASDown` alert rule currently references `job="synology-snmp"`, but the Prometheus scrape job is named `telegraf-snmp`. This label mismatch means the alert can never fire — even if the NAS goes completely offline, the operator receives no notification. The volume usage and disk health alerts also depend on metric names that do not currently exist in Prometheus, rendering all three Synology alert rules non-functional. Fixing these is essential because the NAS is the primary data store.

**Independent Test**: Simulate a NAS outage (e.g., block SNMP traffic or stop the Telegraf container). Verify that the `SynologyNASDown` alert fires within the configured threshold and an email notification is received. Restore connectivity and verify a recovery email is sent.

**Acceptance Scenarios**:

1. **Given** the Synology alert rules are corrected, **When** the Synology NAS becomes unreachable for longer than the configured threshold (2 minutes), **Then** the `SynologyNASDown` alert fires and the operator receives an email notification identifying the NAS as unreachable.
2. **Given** the Synology alert rules are corrected, **When** any individual NAS volume exceeds 85% usage for 5 minutes, **Then** the `SynologyVolumeHighUsage` alert fires and the operator receives an email identifying the specific volume and its current usage percentage.
3. **Given** the `SynologyNASDown` alert previously referenced `job="synology-snmp"`, **When** this feature is complete, **Then** the alert rule references the actual Prometheus job label used by the Telegraf SNMP scrape target (`telegraf-snmp`), ensuring the rule evaluates against real data.
4. **Given** the Synology disk health alert rule references metric names, **When** this feature is complete, **Then** all metric names in alert expressions match the metrics actually produced by the Telegraf SNMP pipeline — no alert rule references a non-existent metric.
5. **Given** the generic `ServiceDown` alert and the specific `SynologyNASDown` alert both exist, **When** the Telegraf SNMP target goes down, **Then** only the `SynologyNASDown` alert fires — the generic alert is suppressed for this target via the existing inhibition rules, confirming no regression from the alert hygiene established in Feature 040.

---

### User Story 3 — AdGuard Home Application Metrics (Priority: P2)

As a homelab administrator, I want to see DNS query volume, blocked query percentage, filter list status, and upstream DNS response times for AdGuard Home, so that I can verify my DNS filtering is working correctly and diagnose DNS resolution issues.

**Why this priority**: AdGuard Home is the DNS resolver for the entire homelab network. Currently, the only monitoring is container-level infrastructure metrics (CPU, memory, disk). Without application-level metrics, the operator cannot tell whether DNS resolution is slow, filtering is effective, or upstream servers are degrading — all of which directly impact every service in the homelab. This has a higher priority than Nextcloud/Jellyfin because DNS affects all devices.

**Independent Test**: Open the AdGuard Home dashboard in Grafana. Verify that panels display DNS query rate, blocked query percentage, and upstream response times. Generate DNS traffic and confirm the dashboard updates.

**Acceptance Scenarios**:

1. **Given** AdGuard Home application monitoring is deployed, **When** the operator opens the AdGuard Home dashboard in Grafana, **Then** the dashboard displays DNS query rate, blocked query count and percentage, top blocked domains, and upstream DNS response times with data refreshing within 60 seconds.
2. **Given** AdGuard Home application monitoring is deployed, **When** the operator generates DNS queries from a LAN device, **Then** the query rate metric increases within 60 seconds and blocked queries are counted separately from allowed queries.
3. **Given** AdGuard Home metrics are collected, **When** the AdGuard Home service becomes unreachable, **Then** the service-down alert fires within the configured threshold (per the unified alerting from Feature 040) and the operator receives an email notification.
4. **Given** the AdGuard Home monitoring contract is declared, **When** the monitoring stack is redeployed, **Then** the scrape target, alert rules, and dashboard are automatically provisioned via the self-registration pattern — without any changes to the monitoring role itself.

---

### User Story 4 — Nextcloud Application Metrics (Priority: P2)

As a homelab administrator, I want to see active user count, storage usage, and system health status for Nextcloud, so that I can monitor adoption, plan storage capacity, and detect issues before users are affected.

**Why this priority**: Nextcloud is a recently deployed service (Feature 034) that stores user files on the NAS. Currently it has only infrastructure metrics — the monitoring contract exists in host_vars but has empty scrape targets and alert rules. Application-level metrics provide visibility into file sync health, active usage, and whether Nextcloud's internal health checks are passing.

**Independent Test**: Open the Nextcloud dashboard in Grafana. Verify that panels display active user count, storage usage, and health status. Log into Nextcloud and confirm user activity is reflected in the metrics.

**Acceptance Scenarios**:

1. **Given** Nextcloud application monitoring is deployed, **When** the operator opens the Nextcloud dashboard in Grafana, **Then** the dashboard displays active user count, total storage used, free space remaining, and Nextcloud internal health status (e.g., database connectivity, cron job status) with data refreshing within 60 seconds.
2. **Given** Nextcloud application monitoring is deployed, **When** a user uploads a file via Nextcloud, **Then** the storage usage metric reflects the change within 120 seconds.
3. **Given** the Nextcloud monitoring contract is currently empty (enabled with zero scrape targets), **When** this feature is complete, **Then** the monitoring contract declares at least one scrape target, relevant alert rules for service health, and a dashboard reference.
4. **Given** the Nextcloud exporter is deployed, **When** the Nextcloud service is under heavy load, **Then** the dashboard reflects elevated response times or error counts — not just container CPU/memory — giving the operator visibility into application-level performance.

---

### User Story 5 — Jellyfin Application Metrics (Priority: P3)

As a homelab administrator, I want to see active streaming sessions, media library size, and transcoding activity for Jellyfin, so that I can understand usage patterns and identify performance bottlenecks.

**Why this priority**: Jellyfin is lower priority than AdGuard Home and Nextcloud because media streaming is not a critical infrastructure service. However, it still benefits from application-level metrics — transcoding is resource-intensive, and knowing whether the server is under heavy media load helps explain container-level CPU spikes. The monitoring contract exists in host_vars but has empty scrape targets.

**Independent Test**: Open the Jellyfin dashboard in Grafana. Verify that panels display active session count and media library statistics. Stream media and confirm session metrics update.

**Acceptance Scenarios**:

1. **Given** Jellyfin application monitoring is deployed, **When** the operator opens the Jellyfin dashboard in Grafana, **Then** the dashboard displays active streaming session count, media library item count, and transcoding activity status.
2. **Given** the Jellyfin monitoring contract is currently empty (enabled with zero scrape targets), **When** this feature is complete, **Then** the monitoring contract declares at least one scrape target and a dashboard reference.
3. **Given** a user starts streaming media from Jellyfin, **When** the operator views the Jellyfin dashboard, **Then** the active session count increases from 0 to 1 within 60 seconds.
4. **Given** no viable community exporter exists for Jellyfin at implementation time, **When** this situation is confirmed during planning, **Then** this user story is descoped (moved to out of scope) and documented as blocked — rather than building a custom solution.

---

### User Story 6 — Service-Specific Dashboards for New Exporters (Priority: P2)

As a homelab administrator, I want dedicated Grafana dashboards for each newly monitored service, so that I can view application-level metrics at a glance without constructing manual queries.

**Why this priority**: Dashboards are the primary interface for observability. Without them, metrics are collected but invisible to the operator. Each new exporter should have a corresponding dashboard that follows the same provisioning pattern as existing dashboards (Synology NAS, Infrastructure Overview, Caddy, Immich).

**Independent Test**: After deploying new exporters, verify that each service has a dedicated dashboard in Grafana's dashboard list. Open each dashboard and confirm it displays live data with no "No Data" panels.

**Acceptance Scenarios**:

1. **Given** new service exporters are deployed (AdGuard Home, Nextcloud, and optionally Jellyfin), **When** the operator navigates to the Grafana dashboard list, **Then** each new service has a dedicated dashboard that is automatically provisioned — no manual import required.
2. **Given** a service-specific dashboard is provisioned, **When** the operator opens it, **Then** all panels display live data (no "No Data" or "N/A" panels when the service is healthy and the exporter is running).
3. **Given** dashboards are provisioned via the self-registration pattern (monitoring contracts), **When** a service's monitoring contract is disabled, **Then** that service's dashboard is removed from Grafana on the next monitoring stack deployment.
4. **Given** the Synology NAS dashboard was previously showing zero data, **When** the SNMP fix (US-1) is applied, **Then** all existing Synology NAS dashboard panels display live data — no dashboard modifications should be needed if the metrics pipeline is correctly restored.

---

### Edge Cases

- **What happens if SNMPv3 credentials on the Synology NAS were rotated since the original deployment?** The Telegraf SNMP input fails authentication. Metrics remain at zero. The scrape target may still show "UP" (Telegraf is running and serving its `/metrics` endpoint) but produces no SNMP-derived metrics. Resolution requires the operator to update the SNMPv3 credentials in the Ansible vault to match the current NAS configuration.
- **What happens if the Synology NAS is on a different IP address or subnet than expected?** The Telegraf SNMP input cannot reach the NAS. The Ansible inventory lists the Synology's SSH management address as `192.168.10.30` (in the `infra` group), while the monitoring variable `synology_nas_ip` is `192.168.1.109` (used for SNMP and NFS). This dual-address setup suggests the NAS has interfaces on both subnets. If the NAS data-plane IP changed, the `synology_nas_ip` variable must be updated. The fix should include verification of actual network connectivity between the monitoring container and the NAS on SNMP port 161 at the configured IP.
- **What happens if a community exporter for a service does not exist or is unmaintained?** That service's application-level monitoring is descoped for this feature. The monitoring contract remains enabled with empty scrape targets (current state for Nextcloud and Jellyfin), and only infrastructure metrics are available. This is explicitly handled in US-5 AC-4 for Jellyfin.
- **What happens if a community exporter requires a newer version of the service than what is deployed?** The exporter for that service is descoped. The monitoring contract is left empty until the service is upgraded.
- **What happens if the AdGuard Ansible role does not exist when this feature is implemented?** AdGuard Home application monitoring (US-3) is blocked. Infrastructure metrics (node_exporter via `lxc_base`) may already be available if AdGuard is in the `services` inventory group. The application exporter work is deferred until the adguard role is created.
- **What happens if the existing Synology dashboard queries use metric names that differ from what Telegraf actually produces?** This is a confirmed issue. The dashboard queries reference `snmp_synology_*` prefixed metrics, but the Telegraf SNMP plugin with current field names would produce differently named metrics (e.g., `snmp_memTotalReal` vs. `snmp_synology_memory_total_bytes`). The fix must ensure alignment between produced metric names and consumed metric names — either by adjusting the metrics production, the dashboard queries, or both.
- **What happens if Nextcloud's internal stats endpoint requires authentication?** The exporter must be configured with Nextcloud credentials (stored in Ansible vault). If no API token mechanism exists, the metrics collection for Nextcloud may be limited to what is available without authentication.
- **What happens when the monitoring LXC is redeployed and new exporter containers start before the target services are ready?** Exporters should handle target unavailability gracefully — returning empty or error metrics rather than crashing. The service-down alert fires for the target service, not the exporter.

## Requirements *(mandatory)*

### Functional Requirements

#### Synology SNMP Pipeline Fix

- **FR-001**: The metrics produced by the Telegraf SNMP pipeline MUST match the metric names referenced by the Synology NAS Grafana dashboard queries and alert rule expressions. If a dashboard panel queries `snmp_synology_volume_available_bytes`, that metric MUST exist in Prometheus with current data when the NAS is reachable. *(traces to US-1, US-2)*
- **FR-002**: The Telegraf SNMP configuration MUST collect metrics for all data points displayed on the Synology NAS dashboard: storage capacity per volume, disk health/temperature, CPU usage, memory usage, and network throughput. The current Telegraf configuration (`telegraf.conf.j2`) includes OIDs for CPU, memory, disk status/temperature, and RAID status — but is missing storage volume capacity OIDs (total/available bytes per volume) and network interface OIDs (throughput counters). These missing OID categories MUST be added. *(traces to US-1)*
- **FR-003**: The `SynologyNASDown` alert rule MUST reference the correct Prometheus job label — the label used by the actual Telegraf SNMP scrape target (`telegraf-snmp`), not the currently incorrect `synology-snmp`. *(traces to US-2)*
- **FR-004**: All three Synology alert rules (`SynologyVolumeHighUsage`, `SynologyNASDown`, `SynologyDiskSMARTWarning`) MUST reference metric names that are actually produced by the Telegraf SNMP pipeline. No alert expression may reference a non-existent metric. *(traces to US-2)*
- **FR-005**: The Synology NAS IP address used for SNMP polling MUST be verified against the actual NAS IP on the network. If the codebase value (`192.168.1.109`) differs from the actual NAS IP, the configuration MUST be updated. *(traces to US-1)*
- **FR-006**: SNMPv3 credentials used by Telegraf MUST be verified to match the current credentials configured on the Synology NAS. If credentials have been rotated, the Ansible vault MUST be updated. *(traces to US-1)*
- **FR-007**: After the fix is applied, the Synology NAS dashboard MUST display live data on all panels — storage capacity gauge, disk health table, CPU/memory graphs, and network throughput chart — when the NAS is reachable. *(traces to US-1, US-6)*

#### External Service Exporters

- **FR-008**: An application-level metrics exporter MUST be deployed for AdGuard Home, exposing DNS query volume, blocked query count/percentage, filter list status, and upstream DNS response times. *(traces to US-3)*
- **FR-009**: An application-level metrics exporter MUST be deployed for Nextcloud, exposing active user count, storage usage, and internal health status (database connectivity, cron job execution). *(traces to US-4)*
- **FR-010**: An application-level metrics exporter SHOULD be deployed for Jellyfin, exposing active session count, media library statistics, and transcoding activity — contingent on a viable community exporter being available. If no viable exporter exists, this requirement is waived and documented as out of scope. *(traces to US-5)*
- **FR-011**: Each new exporter MUST be integrated into the service's monitoring contract (in the service's host_vars), following the self-registration pattern established in Feature 040. The monitoring role MUST NOT contain service-specific exporter configuration. *(traces to US-3, US-4, US-5, US-6)*
- **FR-012**: Each new exporter MUST have its scrape target, alert rules, and dashboard reference declared in the service's monitoring contract — enabling automatic provisioning by the monitoring stack. *(traces to US-3, US-4, US-5, US-6)*

#### Monitoring Contracts

- **FR-013**: The AdGuard Home monitoring contract MUST be created in `ansible/host_vars/adguard.yml` (matching the existing pattern of `nextcloud.yml` and `jellyfin.yml`) with scrape targets, alert rules (at minimum: exporter-down), and a dashboard reference. *(traces to US-3)*
- **FR-014**: The Nextcloud monitoring contract (currently empty in `ansible/host_vars/nextcloud.yml`) MUST be populated with scrape targets, alert rules, and a dashboard reference. *(traces to US-4)*
- **FR-015**: The Jellyfin monitoring contract (currently empty in `ansible/host_vars/jellyfin.yml`) SHOULD be populated with scrape targets and a dashboard reference — contingent on FR-010 being fulfilled. *(traces to US-5)*

#### Dashboards

- **FR-016**: A dedicated Grafana dashboard MUST be created for AdGuard Home displaying DNS query rate, blocked query percentage, top blocked domains, and upstream response times. *(traces to US-3, US-6)*
- **FR-017**: A dedicated Grafana dashboard MUST be created for Nextcloud displaying active user count, storage usage, and health status. *(traces to US-4, US-6)*
- **FR-018**: A dedicated Grafana dashboard SHOULD be created for Jellyfin displaying active sessions and media library statistics — contingent on FR-010 being fulfilled. *(traces to US-5, US-6)*
- **FR-019**: All new dashboards MUST be provisioned automatically via the monitoring contract's dashboard_file reference — no manual Grafana import. *(traces to US-6)*
- **FR-020**: The existing Synology NAS dashboard MUST display live data after the SNMP fix, without requiring structural modifications to the dashboard JSON. If the metric naming fix changes how metrics are named, the dashboard queries MUST be updated to match. *(traces to US-1, US-6)*

#### Alert Rules

- **FR-021**: Each new service exporter MUST have at minimum a service-down alert (via the generic `up == 0` rule from Feature 040) that fires when the exporter's scrape target is unreachable. *(traces to US-3, US-4, US-5)*
- **FR-022**: AdGuard Home SHOULD have an application-specific alert rule for abnormally high blocked-query percentage (suggesting a misconfigured filter list or upstream issue). *(traces to US-3)*

#### IaC & Operations

- **FR-023**: All changes MUST be deployed via Ansible roles and playbooks — no manual configuration of exporters, dashboards, or alert rules. *(traces to all stories)*
- **FR-024**: All new exporter credentials (API tokens, passwords) MUST be stored in Ansible vault — never in plaintext in the repository. *(traces to all stories)*
- **FR-025**: The monitoring playbook MUST remain idempotent after all changes — re-running without changes produces no unexpected modifications. *(traces to all stories)*
- **FR-026**: Exporter deployment MUST NOT require changes to the central monitoring role (`ansible/roles/monitoring_stack/`). Exporters are deployed by the service role that owns them; the monitoring stack discovers them via monitoring contracts. *(traces to US-3, US-4, US-5)*

#### Prometheus Config Reload

- **FR-027**: The monitoring stack MUST support hot-reloading Prometheus configuration (scrape targets, alert rules) without restarting all containers. When `prometheus.yml` or alert rule files change, the Ansible handler MUST reload Prometheus via its `/-/reload` HTTP API rather than restarting the entire Docker Compose stack. This requires enabling `--web.enable-lifecycle` on the Prometheus container. *(traces to US-1, US-2, US-3, US-4, US-5)*

#### Vault Variable Prerequisites

- **FR-028**: Each exporter deployment task MUST include a preflight assertion that verifies required vault variables are defined before attempting to deploy. If a required credential is missing, the playbook MUST fail with a clear error message naming the missing variable — not with an opaque Jinja2 undefined variable error. Required vault variables: `adguard_admin_user` and `adguard_admin_password` (AdGuard exporter), `nextcloud_serverinfo_token` (Nextcloud exporter), `jellyfin_api_key` (Jellyfin exporter). *(traces to US-3, US-4, US-5)*

### Key Entities

- **Telegraf SNMP Pipeline**: The existing metrics bridge between the Synology NAS (SNMP agent) and Prometheus (scraper). Telegraf polls the NAS via SNMPv3, transforms OID values into named metrics, and exposes them on a Prometheus-compatible endpoint. Currently broken — producing zero application-level metrics despite the endpoint being reachable.
- **External Exporter**: A lightweight process that queries a service's API or statistics endpoint and exposes the results as metrics in a format consumable by the monitoring system. Needed for services that do not natively expose monitoring-compatible metrics.
- **Monitoring Contract**: A per-service declaration (in host_vars) that specifies scrape targets, alert rules, and dashboard references. The monitoring stack aggregates these contracts to generate its configuration. Established in Feature 040. Three services (Nextcloud, Jellyfin, AdGuard) currently have empty or missing contracts that this feature populates.
- **Service Dashboard**: A Grafana JSON definition file that visualizes application-level metrics for a specific service. Stored alongside the service role and provisioned automatically by the monitoring stack via the monitoring contract's `dashboard_file` reference.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The Synology NAS dashboard displays live data on all panels (storage capacity, disk health, CPU, memory, network) — verified by visual inspection within 5 minutes of deployment. Zero "No Data" panels when the NAS is reachable.
- **SC-002**: The `SynologyNASDown` alert fires within 3 minutes when the NAS SNMP endpoint is made unreachable — verified by blocking SNMP traffic and confirming email notification receipt.
- **SC-003**: The `SynologyVolumeHighUsage` alert evaluates correctly against live volume metrics — verified by inspecting the alert rule status in the Prometheus alerts page (rule is "inactive" or "pending," not "error" or missing).
- **SC-004**: The AdGuard Home dashboard displays live DNS query metrics (query rate, blocked percentage, upstream response times) within 5 minutes of exporter deployment.
- **SC-005**: The Nextcloud dashboard displays active user count and storage usage within 5 minutes of exporter deployment.
- **SC-006**: All new exporter scrape targets show "UP" in the Prometheus target list with successful scrapes.
- **SC-007**: No service-specific exporter configuration was added to the central monitoring role (`ansible/roles/monitoring_stack/`) — verified by `git diff` on the monitoring role directory. Changes to the monitoring role are limited to Synology SNMP pipeline fixes (FR-001 through FR-007, which affect `telegraf.conf.j2` and `synology_alerts.yml` that already reside in the role). New exporter scrape targets, alert rules, and dashboards for AdGuard, Nextcloud, and Jellyfin are declared exclusively in their respective service host_vars and role directories.
- **SC-008**: Re-running the monitoring Ansible playbook after all changes produces an idempotent result (no unexpected changes on the second run).
- **SC-009**: Existing monitoring from Feature 040 continues to function: infrastructure metrics for all service containers, Caddy and Immich application metrics, and the unified alerting framework remain operational after this feature is deployed.

## Assumptions

- **A-001**: The Synology NAS (192.168.1.109) is physically operational and has SNMP enabled. The SNMP service itself is functional — the problem is in the monitoring pipeline configuration, not the NAS hardware or SNMP daemon.
- **A-002**: The monitoring stack from Feature 040 is fully deployed and operational — Prometheus, Grafana, Telegraf, Alertmanager are running on the monitoring LXC (192.168.1.214). This feature builds on that foundation.
- **A-003**: Network connectivity exists between the monitoring LXC (192.168.1.214) and the Synology NAS on SNMP port 161. If the Docker bridge network isolates Telegraf from the NAS, the deployment must ensure Telegraf has host network access or appropriate port mapping.
- **A-004**: SNMPv3 credentials configured on the Synology NAS are known to the operator and can be provided for the Ansible vault. If credentials have been rotated since Feature 017, the operator will supply the current values.
- **A-005**: The AdGuard Home LXC (192.168.1.210) exists and is running, even though the Ansible `adguard` role has not yet been created. The container was provisioned via Terraform and is accessible via SSH.
- **A-006**: Community-maintained exporters exist for AdGuard Home and Nextcloud with active maintenance and compatibility with the deployed service versions. This is a reasonable assumption given the popularity of these services, but will be verified during the planning phase.
- **A-007**: Nextcloud and Jellyfin LXCs have their application ports accessible from the monitoring LXC or can host an exporter process locally that is accessible from the monitoring LXC.
- **A-008**: The Synology NAS runs DSM 7.x, which may expose different SNMP OIDs than the DSM 6.x-era OIDs currently configured in the Telegraf template. OID compatibility must be verified during implementation.
- **A-009**: The self-registration pattern (monitoring contracts in host_vars) established in Feature 040 is working correctly for Caddy and Immich. This feature relies on the same pattern for new exporters.

## Non-Functional Requirements

- **NFR-001**: Each external exporter instance MUST consume no more than 50 MB RAM and negligible CPU on the host where it runs — consistent with the infrastructure metrics agent limit from Feature 040.
- **NFR-002**: Adding new exporter scrape targets MUST NOT cause the monitoring LXC's total resource consumption to exceed 4 GB RAM and 2 vCPU (the limit established in Feature 040 / Feature 017).
- **NFR-003**: New dashboards MUST load within 5 seconds when displaying a 24-hour time range — consistent with the dashboard performance target from Feature 040.
- **NFR-004**: Exporter scrape latency MUST be less than the configured scrape timeout (10 seconds) under normal conditions.

## Out of Scope

- **Proxmox VE host metrics** — metrics from the hypervisor itself (as opposed to its LXC guests) require a dedicated approach. Deferred to a future iteration.
- **Healthcheck script removal** — the existing Python healthcheck script is retained as-is per Feature 040's decision. Not part of this feature.
- **Security monitoring** — fail2ban metrics, Blackbox Exporter, certificate lifecycle monitoring, DNS anomaly detection. Deferred to a future iteration (Tier C).
- **Log aggregation** — centralized log collection is entirely out of scope.
- **Home Assistant metrics** — the Home Assistant Ansible role is a placeholder (not deployed). No monitoring contract is created for it.
- **Custom exporter development** — if a community exporter does not exist for a service, this feature will not build one. The service's monitoring contract is left empty until a suitable exporter becomes available.
- **AdGuard Ansible role creation** — creating the full `ansible/roles/adguard/` role is a separate feature. This feature adds monitoring for AdGuard, which may depend on the adguard role existing. If the role does not exist, AdGuard application monitoring (US-3) is blocked and documented as a dependency.
- **Exporter high availability** — single exporter instances are sufficient for the homelab. No redundancy or failover.
- **New notification channels** — email-only per existing setup. No Slack, Discord, or push notifications.
- **Recording rules or complex aggregations** — deferred to the security monitoring iteration (Tier C).
- **Telegraf replacement** — whether to continue using Telegraf as the SNMP bridge or switch to a different approach is an implementation decision for the planning phase, not a requirement of this feature. The requirement is that Synology metrics flow correctly.

## Constraints

- **C-001**: Must follow existing IaC patterns — Ansible roles and playbooks for all configuration, secrets in Ansible Vault, idempotent deployments.
- **C-002**: Must not break any monitoring established by Feature 040 — infrastructure metrics, Caddy/Immich application metrics, unified alerting, and self-registration pattern must continue to function.
- **C-003**: Must not expose exporter endpoints via the public HTTPS reverse proxy — metrics are internal LAN-only traffic.
- **C-004**: Must comply with the constitution's separation of concerns: Terraform owns container existence, Ansible owns configuration inside containers. Exporters are Ansible-managed.
- **C-005**: Must comply with the constitution's secrets policy: no plaintext secrets (exporter API tokens, SNMP credentials) in the repository.
- **C-006**: Exporter configuration must follow the self-registration pattern from Feature 040 — declared in the service's monitoring contract, not hardcoded in the central monitoring role.
- **C-007**: New dashboards must be compatible with the currently running Grafana version (12.3.1) — no deprecated panel types or query syntax.
- **C-008**: All changes must be deployable from both CI/CD (GitHub Actions on Raspberry Pi runner) and a developer laptop — per the constitution's dual-provisioning parity requirement. Since all changes are Ansible-based, this is satisfied by default, but any new scripts or automation must respect both execution contexts.

## Dependencies

- **D-001**: Feature 040 (Monitoring Overhaul) — the self-registration pattern, monitoring contracts, infrastructure metrics agents, unified alerting, and Grafana provisioning are prerequisites. Feature 040 must be fully merged before this feature is implemented.
- **D-002**: Feature 017 (Synology Metrics) — the original Synology SNMP pipeline, Telegraf configuration, dashboard JSON, and alert rules. This feature fixes issues in those artifacts.
- **D-003**: AdGuard Ansible role — the `ansible/roles/adguard/` directory does not currently exist. The AdGuard playbook (`ansible/playbooks/adguard.yml`) references this role. If the role is not created before or during this feature, AdGuard Home application monitoring (US-3) is blocked. Infrastructure monitoring (node_exporter) may still work if AdGuard is in the `services` inventory group.
- **D-004**: Nextcloud Ansible role — already exists and has a monitoring contract placeholder in `ansible/host_vars/nextcloud.yml`. The exporter can be added to this role.
- **D-005**: Jellyfin Ansible role — already exists and has a monitoring contract placeholder in `ansible/host_vars/jellyfin.yml`. The exporter can be added if a viable one is found.
- **D-006**: Network connectivity between monitoring LXC (192.168.1.214) and all service LXCs on exporter-specific ports.
- **D-007**: Synology NAS accessibility — the NAS must be reachable from the monitoring LXC on SNMP port 161 for the SNMP fix, and the operator must provide current SNMPv3 credentials if they have been rotated.

## Decision Log

| # | Ambiguity | Decision | Rationale |
|---|-----------|----------|-----------|
| DL-01 | The Ansible inventory lists the Synology SSH management address as `192.168.10.30` (infra group) but `synology_nas_ip` in monitoring vars is `192.168.1.109`. Which IP should be used for SNMP polling? | Use the monitoring variable value (`192.168.1.109`) as the SNMP target and add a verification step (FR-005) to confirm NAS SNMP reachability at that IP. | The NAS appears to have dual network interfaces — a management/SSH address on the 10.x subnet and a data-plane address on the 1.x subnet (also used for NFS mounts in the README). The monitoring variable was set in Feature 017 and is consistent with all NFS mount references. The requirement (FR-005) ensures connectivity is verified regardless. |
| DL-02 | Should the metric naming fix adjust Telegraf output to match the dashboard, or adjust the dashboard to match Telegraf output? | Not prescribed — this is an implementation decision. The requirement (FR-001) states that metric names must be aligned between producer and consumer. | Both approaches are valid and have trade-offs (changing Telegraf config affects all consumers; changing dashboard affects the visual layer). The planning/implementation phase should choose based on the least disruptive approach and future maintainability. |
| DL-03 | Should Proxmox VE host metrics be included in Tier B? | No — explicitly out of scope. | The reference document for Tier B does not mention Proxmox VE host metrics. Feature 040 already deferred this. Including it would expand the scope beyond the defined tier. |
| DL-04 | What if the Jellyfin community exporter does not exist or is unmaintained? | Jellyfin monitoring is conditional (P3, SHOULD-level requirements). If no viable exporter is found during planning, the user story is descoped and documented. | Jellyfin is a lower-priority media service. Building a custom exporter violates YAGNI. The monitoring contract remains enabled with empty targets (current state) until a suitable exporter emerges. |
| DL-05 | Should the AdGuard exporter be deployed to the AdGuard LXC or the monitoring LXC? | Not prescribed — this is an implementation decision. | Some exporters run as sidecars on the service host; others query a service API remotely from the monitoring host. The choice depends on the specific exporter's architecture and the service's API accessibility. |
| DL-06 | The AdGuard Ansible role (`ansible/roles/adguard/`) does not exist yet. Does this block the entire feature? | No — only US-3 (AdGuard Home metrics) is blocked. The Synology SNMP fix (US-1, US-2) and other exporter work (US-4, US-5) proceed independently. | The user stories are designed to be independently implementable. If the adguard role is created as a separate feature before or during this work, US-3 becomes unblocked. |
| DL-07 | Should the existing Synology dashboard be replaced with a new one, or should the current one be fixed? | Fix the current dashboard (or the metrics pipeline feeding it) so it displays data. Do not create a replacement dashboard from scratch. | The dashboard was designed and tested in Feature 017. The issue is a metrics pipeline problem, not a dashboard design problem. Creating a new dashboard would duplicate effort and potentially lose the original design intent. |
| DL-08 | What SNMP OIDs are needed for the missing Synology metrics (volumes, network)? | The implementation must identify the correct OIDs for the running DSM version. The specific OIDs are an implementation detail, not a spec requirement. | OID availability depends on the DSM version, hardware model, and firmware. The requirement (FR-002) states which data points must be collected; the planning phase determines the specific OIDs. |
| DL-09 | Should the healthcheck script be updated to include new exporters? | No — the healthcheck script is out of scope per Feature 040's decision to retain it as-is. | The healthcheck script is independent of the Prometheus monitoring stack. Modifying it introduces scope creep. It will be addressed in a future cleanup iteration. |
| DL-10 | What alert thresholds should new exporter alerts use? | Use the same patterns established in Feature 040: service-down at 2 minutes unreachable; application-specific thresholds defined based on the metric type and operational experience. | Consistency with existing alerting thresholds reduces operator confusion. Application-specific thresholds (e.g., blocked DNS percentage) should be conservative initially and can be tuned later. |
| DL-11 | Is this feature contingent on Feature 040 being merged to main? | Yes — Feature 040 must be fully merged before this feature begins implementation. | This feature depends on the self-registration pattern, monitoring contracts, infrastructure metrics, and the updated monitoring stack configuration from Feature 040. Building on an unmerged feature creates a fragile dependency chain. |

## Open Questions

None — all ambiguities resolved in Decision Log above.

---

## Self-Critique

### Strengths
- Comprehensive user stories with well-structured Given/When/Then acceptance scenarios — 6 stories, each with 3–5 ACs
- Thorough edge case analysis (8 scenarios) covering real operational failure modes
- Decision Log resolves all 11 identified ambiguities with documented rationale — no TBD items
- Conditional Jellyfin requirement (SHOULD-level) correctly applies YAGNI; doesn't commit to building a custom exporter
- Clean dependency chain: P1 (Synology fix) is independent of P2/P3 (exporters), enabling incremental delivery
- Strong alignment with Feature 040's self-registration pattern — exporters plug into existing monitoring contracts
- Out-of-scope section is explicit and well-reasoned (no scope creep into Proxmox host metrics, log aggregation, or security monitoring)

### Issues Found (Resolved in this pass)
- **[severity: medium]** SC-007 was self-contradictory — stated "no changes to the monitoring role" while acknowledging Synology SNMP fixes that live in that role. **Fixed**: reworded to clarify that service-specific exporter config must not be added, while Synology pipeline fixes to existing role files are expected.
- **[severity: medium]** FR-002 said "Any OIDs missing must be added" without specifying which OID categories are absent. The current `telegraf.conf.j2` has CPU/memory/disk-status/RAID OIDs but is entirely missing volume capacity and network throughput OIDs. **Fixed**: added explicit enumeration of present vs. absent OID categories.
- **[severity: low]** Edge case about Synology IP discrepancy cited a vague "reference document" as the source of `192.168.10.30`. **Fixed**: corrected to identify the actual source (Ansible inventory SSH management address) and explained the dual-interface setup.
- **[severity: low]** FR-013 used "or equivalent" for the AdGuard host_vars path. **Fixed**: specified the exact pattern (`ansible/host_vars/adguard.yml`) matching existing files.
- **[severity: low]** Constitution's dual-provisioning parity requirement was not explicitly addressed. **Fixed**: added C-008 confirming all changes are Ansible-based and respect both CI/CD and laptop execution contexts.
- **[severity: low]** DL-01 rationale was imprecise about why two IPs exist for the NAS. **Fixed**: clarified the management vs. data-plane interface split.

### Verdict
ACCEPT — All issues found during self-critique have been resolved. The specification passes all quality gate checks.
