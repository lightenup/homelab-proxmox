# Feature Specification: Minimal Monitoring & Alerting

**Feature Branch**: `011-monitoring-alerting`
**Created**: December 20, 2025
**Status**: Draft
**Input**: "Deliver a minimal, self-hosted monitoring + alerting baseline that gives a simple dashboard for 'is it up?' and sends alerts to a phone-friendly channel when key services are down"

## Clarifications

### Session 2025-12-20

- Q: Which notification channel(s) should be implemented (ntfy, Discord, email)? → A: Email (SMTP) only, because: zero inbound exposure, works everywhere, easy to integrate with basically all monitoring stacks
- Q: Should monitors be configured via Ansible automation or manual UI? → A: Fully automated via Ansible (use Uptime Kuma API/config files to provision monitors)
- Q: Which SMTP authentication method should be supported? → A: STARTTLS 587 with SMTP AUTH (PLAIN/login). Minimal smtp_host/port/user/password/from/to schema, single provider
- Q: How should Ansible interact with Uptime Kuma to provision monitors? → A: Wait for container ready, then API calls with retry logic (most robust for automation)
- Q: Should the Uptime Kuma dashboard require authentication? → A: Basic authentication enabled (admin account created on first setup, Ansible manages credentials)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Service Health Dashboard (Priority: P1)

As a homelab administrator, when I want to check if my services are running, I need a simple web dashboard that shows the current status of all critical services at a glance, so I can quickly identify issues without checking each service individually.

**Why this priority**: This is the core monitoring capability. Without a dashboard, there's no visibility into service health, making troubleshooting reactive and time-consuming. This delivers immediate value by consolidating health checks in one place.

**Independent Test**: Can be fully tested by (1) accessing the monitoring dashboard URL from a LAN device, (2) verifying all configured monitors are visible, (3) checking that status indicators (UP/DOWN) update correctly, and (4) confirming response times are displayed.

**Acceptance Scenarios**:

1. **Given** the monitoring feature is deployed, **When** I browse to the monitoring URL (monitoring.local) from my LAN, **Then** I see a dashboard showing all configured service monitors with their current status
2. **Given** all services are running normally, **When** I view the dashboard, **Then** all monitors show "UP" status with green indicators and recent response times
3. **Given** a service becomes unavailable, **When** I refresh the dashboard after the check interval, **Then** the affected monitor shows "DOWN" status with a red indicator

---

### User Story 2 - Mobile Alert Notifications (Priority: P1)

As a homelab administrator, when a critical service goes down, I need to receive immediate notifications on my mobile phone, so I can respond to outages even when I'm not at my computer.

**Why this priority**: Monitoring without alerting provides no value when away from the dashboard. Mobile notifications are essential for timely response to outages. This is the primary reason for implementing monitoring - proactive awareness of problems.

**Independent Test**: Can be tested by (1) configuring alert channel on mobile device, (2) manually stopping a monitored service, (3) waiting for alert threshold to be exceeded, and (4) verifying notification is received on phone with service name and status.

**Acceptance Scenarios**:

1. **Given** alerting is configured with a notification channel, **When** a monitored service has been down for longer than the alert threshold (e.g., 2 minutes), **Then** I receive a notification on my phone identifying which service is down
2. **Given** a service has recovered after being down, **When** the monitor detects the service is back up, **Then** I receive a recovery notification on my phone
3. **Given** multiple services are down simultaneously, **When** alerts are triggered, **Then** I receive separate notifications for each affected service (no notification batching that hides failures)

---

### User Story 3 - Infrastructure as Code Deployment (Priority: P1)

As a homelab administrator, when I need to rebuild or replicate my monitoring stack, I need the entire deployment to be reproducible via Terraform and Ansible, so I can recover from disasters or migrate to new infrastructure without manual configuration.

**Why this priority**: Consistency with existing homelab patterns. All infrastructure is IaC-managed, and monitoring should be no exception. This ensures the monitoring stack itself can be recovered using the same disaster recovery processes as other services.

**Independent Test**: Can be tested by (1) running Terraform to provision monitoring LXC, (2) running Ansible playbook to deploy monitoring stack, (3) verifying dashboard is accessible, (4) destroying the LXC and reprovisioning, and (5) confirming the stack functions identically after recreation.

**Acceptance Scenarios**:

1. **Given** the monitoring infrastructure code is in the repository, **When** I run `terraform apply` with the monitoring module, **Then** a monitoring LXC is created with correct network configuration and static IP
2. **Given** the monitoring LXC exists, **When** I run the monitoring Ansible playbook, **Then** all monitoring components (Docker, Uptime Kuma) are installed and configured idempotently with automated monitor provisioning
3. **Given** the monitoring stack is deployed, **When** I re-run the Ansible playbook without changes, **Then** the playbook reports zero changes (changed=0, except for check tasks like "Get container status")

---

### Edge Cases

- What happens when the monitoring service itself goes down? (Self-monitoring is out of scope for minimal MVP, but the dashboard should be accessible after a monitoring LXC reboot without manual intervention)
- How does the system handle transient network issues? (Monitors should have configurable retry intervals and down thresholds to avoid false alarms from brief network hiccups)
- What happens when notification secrets are missing or invalid? (Ansible deployment should fail with clear error message if secrets are not configured, preventing deployment of non-functional alerting)
- How are monitor targets discovered? (Manual configuration in this minimal version; future enhancement could auto-discover from Terraform inventory)
- What happens when mDNS resolution fails? (Monitors should have fallback to IP addresses from inventory; document limitation that mDNS requires functional LAN networking)
- How do we prevent alert storms? (Configure alert cooldown periods in Uptime Kuma to rate-limit repeat notifications)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Monitoring stack MUST be deployed via Ansible roles and playbooks (no manual configuration allowed)
- **FR-002**: Monitoring endpoint MUST be reachable on LAN via mDNS hostname (monitoring.local or similar) for easy discovery
- **FR-003**: Dashboard MUST display status for at least these critical endpoints:
  - pve.local:8006 (HTTPS, Proxmox web UI)
  - proxy.local:80 (HTTP, Caddy reverse proxy)
  - immich.local:2283 (HTTP, Immich photo service)
  - homeassistant.local:8123 (HTTP, Home Assistant)
- **FR-004**: Dashboard MUST display current status (UP/DOWN), response time, and uptime percentage for each monitored service
- **FR-005**: Alert notifications MUST trigger when a monitored service is down for longer than a configurable threshold (default: 2 minutes)
- **FR-006**: Alert notifications MUST be delivered via email (SMTP) to administrator's email address
- **FR-007**: Alert notifications MUST include service name, current status, and timestamp
- **FR-008**: All secrets (SMTP credentials: smtp_host, smtp_port, smtp_user, smtp_password, smtp_from, smtp_to; Uptime Kuma admin credentials: uptime_kuma_admin_user, uptime_kuma_admin_password) MUST NOT be committed to git (use Ansible Vault)
- **FR-009**: Monitoring LXC MUST be provisioned via Terraform with static IP address from service_ips variable
- **FR-010**: LXC inventory MUST be generated from Terraform outputs (no manual IP duplication in Ansible inventory)
- **FR-011**: Ansible deployment MUST be idempotent (rerunning playbook produces changed=0 except for check tasks)
- **FR-012**: Monitoring stack MUST use Docker Compose for container orchestration (consistent with homelab pattern)
- **FR-013**: Docker Compose configuration files MUST be templated via Ansible (no hardcoded values from repository)
- **FR-014**: Monitor targets MUST use mDNS hostnames (.local) where possible; fallback to inventory IPs if mDNS unavailable
- **FR-015**: Uptime Kuma data MUST persist across container restarts (Docker volumes or bind mounts)
- **FR-016**: Monitoring stack MUST start automatically on LXC boot (systemd service for Docker Compose)
- **FR-017**: Ansible role MUST include verification tasks to confirm containers are running and dashboard is accessible
- **FR-018**: Documentation MUST include instructions for configuring SMTP notification channel (server details, authentication, testing)
- **FR-019**: All 4 core monitors MUST be provisioned automatically via Ansible using Uptime Kuma API (new monitors added by updating monitoring_targets variable and rerunning playbook)

### Success Criteria *(mandatory)*

Success criteria must be measurable, technology-agnostic, and verifiable without implementation details:

- **SC-001**: Administrator can view service health dashboard by navigating to monitoring.local from any LAN device within 5 seconds
- **SC-002**: Dashboard displays current status (UP/DOWN) for all 4 critical services (pve, proxy, immich, homeassistant)
- **SC-003**: Dashboard updates within 2 minutes when a service transitions from UP to DOWN
- **SC-004**: Administrator receives mobile notification within 3 minutes of a service going down
- **SC-005**: Notification includes service name and DOWN status (human-readable message)
- **SC-006**: Recovery notification is sent within 2 minutes of service becoming available again
- **SC-007**: Running `terraform apply` with no changes reports no infrastructure modifications needed
- **SC-008**: Running Ansible monitoring playbook twice (no changes between runs) reports changed=0 on second run
- **SC-009**: Monitoring stack survives LXC reboot and resumes monitoring within 5 minutes of boot completion
- **SC-010**: No notification secrets are visible in git repository history (`git log -p` shows no auth tokens/passwords)

### Key Entities *(include if feature involves data)*

- **Monitoring LXC**: Debian-based container hosting monitoring stack
  - Attributes: Static IP (from service_ips), mDNS hostname (monitoring.local), 2GB RAM, 10GB storage
  - Role: Hosts Docker engine, Uptime Kuma container, monitoring data volumes

- **Uptime Kuma Instance**: Web-based uptime monitoring dashboard
  - Attributes: Port 3001 (default), SQLite database for history, web UI for configuration, basic authentication enabled
  - Authentication: Admin account created during initial setup, credentials managed via Ansible Vault
  - Monitors: HTTP(S) checks, ICMP ping checks, configurable intervals (default 60s)
  - Notifications: Supports 90+ notification types (email via SMTP for this implementation)

- **Monitor Configuration**: Individual service health check
  - Attributes: Name, type (HTTP/HTTPS/ping), URL/hostname, check interval, retry count, down threshold
  - Example: {"name": "Proxmox Web UI", "type": "https", "url": "https://pve.local:8006", "interval": 60, "retries": 3}

- **Notification Channel**: Email delivery mechanism for alerts
  - Attributes: smtp_host (server FQDN), smtp_port (587 for STARTTLS), smtp_user (authentication username), smtp_password (authentication password), smtp_from (sender email address), smtp_to (recipient email address)
  - Protocol: SMTP AUTH (PLAIN/LOGIN) over STARTTLS
  - Security: All SMTP credentials stored in Ansible Vault

- **Docker Compose Stack**: Container orchestration configuration
  - Attributes: Services (uptime-kuma only), volumes (data persistence), networks (bridge default)
  - Management: Started/stopped via systemd service for reliability

### Assumptions *(include if making informed guesses)*

- **Network configuration**: All services use mDNS (.local) names; LAN DNS is assumed to support mDNS resolution (Avahi/Bonjour). If mDNS fails, monitors will fall back to static IPs from inventory.
- **LXC networking**: Monitoring LXC can reach all service LXCs on the same LAN subnet (192.168.1.0/24). No firewall rules currently block inter-LXC communication.
- **Docker availability**: Docker Engine can be installed via Ansible on Debian-based LXC (consistent with existing service deployments like Immich).
- **Mobile device access**: User has email client configured on mobile device for receiving alert notifications.
- **SMTP availability**: User has access to SMTP server (personal email provider, Gmail, or self-hosted) with credentials for sending alerts.
- **Dashboard authentication**: Basic authentication is enabled for security best practices. Admin credentials are managed via Ansible Vault and used for API access.
- **Check intervals**: Default 60-second check interval is acceptable balance between responsiveness and resource usage. Critical services don't require sub-minute monitoring.
- **Alert thresholds**: 2-minute down threshold (2 consecutive failed checks at 60s interval) reduces false positives from transient issues.
- **Persistent storage**: Docker volumes are sufficient for monitoring data persistence; no separate backup strategy required for minimal MVP (monitoring history is not critical data).
- **Single monitoring instance**: One monitoring LXC is sufficient for homelab scale (4-10 services). High availability monitoring is not required.
- **Monitor provisioning**: All monitors are provisioned automatically via Ansible using Uptime Kuma API with container readiness checks and retry logic for reliability.

---

## Out of Scope *(optional)*

Explicitly excluded from this feature to maintain minimal scope:

- **Public internet access**: No reverse proxy configuration, no external domain exposure. Monitoring is LAN-only (Tailscale access is possible via existing subnet router but not configured here).
- **Full observability stack**: No Prometheus, Grafana, Loki, or metric collection. Only uptime/availability monitoring (binary UP/DOWN checks).
- **Log aggregation**: No centralized logging, no log parsing, no log-based alerts.
- **Application performance monitoring**: No response time alerts, no latency tracking beyond basic "is it responding" checks.
- **Backup automation**: No automated backups of monitoring configuration or historical data. Manual export of Uptime Kuma config is acceptable.
- **LAN segmentation/firewalling**: No VLAN configuration, no firewall rules. Assumes flat LAN with all services mutually reachable.
- **Advanced alerting**: No escalation policies, no on-call rotation, no alert grouping. Single notification channel for all alerts.
- **Self-monitoring**: Monitoring stack does not monitor itself (no "who watches the watchers"). Acceptable risk for minimal MVP.
- **Historical data retention**: Default Uptime Kuma retention policy (30 days) is acceptable. No custom retention configuration.
- **Custom dashboards**: Single default Uptime Kuma dashboard. No custom views, no per-user dashboards.

---

## Constraints *(optional)*

Technical and organizational limitations:

- **LAN-only access**: Dashboard and notification configuration must work without public internet exposure (mDNS + LAN IPs only).
- **Terraform/Ansible patterns**: Must follow existing homelab IaC patterns (Terraform for infra provisioning, Ansible for configuration, dynamic inventory generation).
- **No new dependencies**: Cannot require router/DNS changes, cannot require new infrastructure beyond one LXC.
- **Minimal resource usage**: Monitoring LXC should use minimal resources (2GB RAM, 10GB storage sufficient).
- **Mobile-first alerting**: Notification channel must work reliably on mobile devices without requiring laptop/desktop access.
- **Secrets management**: Must use existing secrets patterns (Ansible Vault + ~/.ansible_vault_pass or gitignored secrets files).
- **Repository boundaries**: Terraform owns LXC provisioning, Ansible owns service configuration. No Terraform configuration inside Ansible roles.
- **Idempotency requirement**: All Ansible tasks must be idempotent (can be run repeatedly without side effects).

---

## Dependencies *(optional)*

Prerequisites and integration points:

- **Existing infrastructure**: Proxmox host (pve) with Terraform provider configured
- **Existing services**: Core LXC services (immich, homeassistant, proxy) reachable via mDNS
- **Existing tooling**:
  - Terraform >= 1.5.7
  - Ansible >= 2.10
  - Dynamic inventory script: scripts/update_ansible_inventory.sh
  - Ansible user with passwordless sudo on all LXCs
- **Network configuration**: mDNS resolution functional on LAN (Avahi installed on LXCs)
- **Docker role**: Existing Ansible role for Docker installation (geerlingguy.docker or custom)
- **Secrets management**: Ansible Vault password file at ~/.ansible_vault_pass

---

## Future Enhancements *(optional)*

Features intentionally deferred to future iterations:

- **Monitor auto-discovery**: Parse Terraform outputs to automatically generate monitor list
- **Advanced metrics**: Prometheus exporter integration for detailed metrics (CPU, memory, disk usage)
- **Custom dashboards**: Grafana integration for customizable visualizations
- **Multi-channel alerting**: Support for multiple notification channels (Discord/Slack webhooks as secondary channels alongside email)
- **Alert escalation**: Tiered notifications (send to primary channel, escalate to secondary if not acknowledged)
- **Public access**: Tailscale-only access to monitoring dashboard (requires Tailscale ACL updates)
- **Backup automation**: Scheduled backups of Uptime Kuma configuration to NFS or S3
- **Self-monitoring**: Monitor the monitoring stack itself (external health check service or dead man's switch)
- **Historical reporting**: Weekly/monthly uptime reports sent via email
- **Integration testing**: Automated tests that simulate service outages and verify alerts are received
- **Geographic redundancy**: Secondary monitoring instance in different location (cloud VM or friend's homelab)
