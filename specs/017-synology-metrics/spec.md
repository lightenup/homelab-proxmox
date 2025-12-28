# Feature Specification: Synology Metrics & Alerting

**Feature Branch**: `017-synology-metrics`  
**Created**: 2025-12-28  
**Status**: Draft  
**Input**: Build observability stack (Prometheus/Grafana/Alertmanager) on dedicated LXC to monitor Synology NAS health via SNMP with email alerting

## Clarifications

### Session 2025-12-28

- Q: Grafana dashboard scope - comprehensive (15+ panels) vs core metrics only (4-6 panels) vs minimal (2 panels)? → A: Core metrics only: storage capacity gauge, disk health table, CPU/RAM utilization, network throughput (4-6 panels total)
- Q: Backup automation - fully automated (daily cron) vs scheduled with manual override vs manual only? → A: Fully automated only: daily cron job backs up TSDB/Grafana volumes to NAS, no manual script provided
- Q: Alert threshold for disk usage - per-volume vs aggregate capacity vs both? → A: Per-volume alerting: separate alert for each Synology volume (volume1, volume2, etc.) when it exceeds 85%

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Synology Health Monitoring (Priority: P1) 🎯 MVP

Operator can view real-time and historical metrics for Synology NAS (storage capacity, disk health, CPU/RAM usage, network throughput) through a web dashboard accessible on the local network.

**Why this priority**: Core value proposition - provides immediate visibility into NAS health, which is critical for homelab data storage and backup operations. Without monitoring, disk failures or capacity issues go unnoticed until service disruption.

**Independent Test**: Access Grafana at `http://monitoring.local:3000`, authenticate, view Synology dashboard showing live metrics from `192.168.1.109`. Metrics refresh every 30 seconds and show data for last 24 hours minimum.

**Acceptance Scenarios**:

1. **Given** SNMP enabled on Synology and monitoring stack deployed, **When** operator opens Grafana Synology dashboard, **Then** dashboard displays core metrics in 4-6 panels: storage capacity gauge, disk health status table, CPU/RAM utilization graphs, and network throughput chart
2. **Given** dashboard is displaying metrics, **When** operator adds a 1GB file to NAS, **Then** storage capacity gauge reflects increased usage within 60 seconds
3. **Given** monitoring LXC reboots, **When** LXC comes back online, **Then** metrics collection resumes automatically without manual intervention
4. **Given** NAS is offline, **When** operator checks Grafana, **Then** dashboard shows "No Data" state for NAS metrics with clear indicator that target is down

---

### User Story 2 - Proactive Alerting via Email (Priority: P1) 🎯 MVP

Operator receives email alerts when critical NAS conditions occur (high disk usage, disk health issues, NAS unreachable) so issues can be addressed before data loss or service disruption.

**Why this priority**: Alerting is essential for homelab scenarios where the operator may not actively monitor dashboards. Email delivery works even when not connected to Tailscale, meeting the requirement for "LAN operation + outbound email alerts."

**Independent Test**: Configure alert for NAS volume >85% full, trigger by adding test data to specific volume, verify email received within 2 minutes. Verify alert resolves (recovery email sent) after test data removed.

**Acceptance Scenarios**:

1. **Given** alert rules configured and SMTP settings deployed, **When** any individual NAS volume (e.g., volume1) exceeds 85% capacity, **Then** operator receives email alert within 2 minutes identifying the specific volume name and current usage percentage
2. **Given** NAS becomes unreachable (network cable disconnected), **When** Prometheus scrape fails for 3 consecutive attempts, **Then** operator receives "NAS Down" email alert with last successful scrape timestamp
3. **Given** alert condition triggered and email sent, **When** condition resolves (usage drops below threshold), **Then** operator receives "Resolved" email notification
4. **Given** SMTP credentials rotated, **When** Ansible playbook re-run with new credentials in vault, **Then** test alert successfully delivers to configured recipient

---

### User Story 3 - Infrastructure Provisioning via IaC (Priority: P1) 🎯 MVP

Operator deploys entire monitoring stack using Terraform + Ansible commands from laptop, with zero clickops in Grafana/Prometheus UIs after bootstrap.

**Why this priority**: IaC approach ensures reproducibility, disaster recovery capability, and aligns with homelab automation principles. Manual configuration creates undocumented dependencies and makes rebuilds painful.

**Independent Test**: Destroy monitoring LXC, re-run Terraform + Ansible, verify Grafana auto-provisions datasources/dashboards and Alertmanager routes configured without any manual UI steps.

**Acceptance Scenarios**:

1. **Given** fresh Proxmox host and repo cloned, **When** operator runs `terraform apply -var-file=prod.tfvars`, **Then** monitoring LXC created with 2 vCPU / 4GB RAM / 32GB disk at `192.168.1.214`
2. **Given** LXC provisioned, **When** operator runs `ansible-playbook playbooks/monitoring.yml`, **Then** Docker installed, compose stack deployed, and all services healthy within 5 minutes
3. **Given** stack deployed, **When** operator accesses `http://monitoring.local:3000`, **Then** Grafana loads with "Synology NAS" dashboard already visible in dashboards list (no import required)
4. **Given** stack deployed, **When** operator checks Prometheus targets at `http://monitoring.local:9090/targets`, **Then** Synology SNMP exporter target shows "UP" state with last scrape timestamp

---

### User Story 4 - Optional: Proxmox Host & LXC Metrics (Priority: P2)

Operator can view CPU, memory, disk, and network metrics for Proxmox host (`pve`) and individual LXCs through Grafana dashboards.

**Why this priority**: Nice-to-have for complete observability, but NAS monitoring is more critical. Can be added incrementally after core functionality proven.

**Independent Test**: Deploy node_exporter on `pve` host, view "Proxmox Host" dashboard showing host-level metrics. Optionally deploy node_exporter to LXCs for per-container visibility.

**Acceptance Scenarios**:

1. **Given** node_exporter installed on `pve`, **When** operator views Proxmox dashboard in Grafana, **Then** dashboard shows host CPU usage, memory, disk I/O, and network throughput
2. **Given** high CPU load generated on `pve`, **When** operator refreshes dashboard, **Then** CPU metrics reflect increased load within 30 seconds
3. **Given** node_exporter deployed to `immich` LXC, **When** operator views LXC dashboard, **Then** dashboard shows container-specific resource usage separate from host

---

### User Story 5 - Operations & Security (Priority: P1) 🎯 MVP

Operator can safely backup/restore monitoring stack, perform controlled upgrades, and ensure secrets never leak to git repository.

**Why this priority**: Operational maturity required for production use. Data loss risk (TSDB) and security risk (SMTP passwords in git) must be mitigated from day one.

**Independent Test**: Run `git status` and verify no secrets tracked. Wait for automated daily backup to complete, destroy monitoring LXC, restore from backup, verify historical data intact.

**Acceptance Scenarios**:

1. **Given** monitoring stack running, **When** operator runs `ansible-playbook playbooks/monitoring.yml` again, **Then** playbook completes with "ok" or "changed" states only (no errors), stack remains functional
2. **Given** SMTP password defined in `ansible/group_vars/monitoring/vault.yml`, **When** operator runs `git status`, **Then** vault file NOT shown as untracked/modified (encrypted or gitignored)
3. **Given** Prometheus collected 7 days of metrics and daily backup cron configured, **When** automated backup runs at scheduled time (e.g., 3 AM), **Then** TSDB and Grafana volumes backed up to `/volume1/homelab_backups/monitoring/` on NAS with date-stamped tarball
4. **Given** monitoring LXC destroyed and recreated, **When** operator restores from backup tarball, **Then** Grafana shows historical data from previous 7 days (no data loss)
5. **Given** new Grafana version released, **When** operator updates version in `docker-compose.yml` and re-runs Ansible, **Then** Grafana upgrades without data loss and release notes reviewed beforehand

---

### Edge Cases

- **What happens when Synology SNMP service crashes?** Prometheus scrapes fail, target marked DOWN, alert fired. Dashboard shows "No Data" state. Operator investigates NAS, restarts SNMP service via DSM UI.
- **What happens when monitoring LXC runs out of disk space?** Prometheus TSDB fills disk, new metrics rejected, container may crash-loop. Alert fired for "Monitoring LXC Disk Full". Operator increases LXC disk size via Proxmox UI or reduces TSDB retention period.
- **What happens when SMTP server is unreachable?** Alertmanager cannot deliver emails, logs errors. No silent failure - Alertmanager UI (`http://monitoring.local:9093`) shows failed notifications. Operator troubleshoots network/SMTP config.
- **What happens when mDNS resolution fails (`monitoring.local` not reachable)?** Operator uses direct IP `192.168.1.214:3000` as fallback. Documentation includes both DNS and IP access methods.
- **What happens when operator forgets to enable SNMP on Synology?** Prometheus scrape fails with "connection refused", target DOWN. Operator follows documented prerequisite steps to enable SNMP in DSM.
- **What happens during Synology DSM upgrade?** SNMP service may restart, brief scrape failures expected. No persistent alert fired unless downtime exceeds 5 minutes. Metrics resume automatically after upgrade completes.
- **What happens when alert fires repeatedly (flapping)?** Alertmanager groups repeated alerts, sends digest email instead of spam. Configured with `group_wait: 30s`, `group_interval: 5m` to prevent alert fatigue.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provision a dedicated LXC named `monitoring` at static IP `192.168.1.214` with 2 vCPU, 4GB RAM, 32GB disk via Terraform
- **FR-002**: System MUST install Docker and deploy Prometheus, Grafana, SNMP Exporter, and Alertmanager via docker-compose with pinned versions
- **FR-003**: System MUST scrape Synology NAS metrics via SNMP from `192.168.1.109` every 30 seconds using SNMP Exporter
- **FR-004**: System MUST provide one Grafana dashboard for Synology with 4-6 core metric panels: storage capacity gauge (%), disk health status table, CPU/RAM utilization line graphs, and network throughput chart (bytes in/out)
- **FR-005**: System MUST auto-provision Grafana datasources (Prometheus) and dashboards via provisioning files (no manual import)
- **FR-006**: System MUST alert via email when any individual NAS volume (e.g., volume1, volume2) usage exceeds 85% threshold, with alert identifying specific volume name
- **FR-007**: System MUST alert via email when NAS becomes unreachable (3 consecutive failed scrapes)
- **FR-008**: System SHOULD alert via email when disk SMART status indicates issues (best-effort: dependent on Synology model exposing SMART OIDs via SNMP)
- **FR-009**: System MUST send "resolved" notification emails when alert conditions clear
- **FR-010**: System MUST store SMTP credentials (username/password) in Ansible Vault file, never in plaintext
- **FR-011**: System MUST configure Alertmanager with SMTP settings (host, port 587, STARTTLS) deployed from Ansible variables
- **FR-012**: System MUST persist Prometheus TSDB data in Docker volume surviving container restarts
- **FR-013**: System MUST persist Grafana configuration (dashboards, datasources, users) in Docker volume surviving container restarts
- **FR-014**: System MUST restart all monitoring services automatically after LXC reboot (docker-compose with restart: unless-stopped)
- **FR-015**: System MUST expose Prometheus UI at `http://monitoring.local:9090` for operator troubleshooting
- **FR-016**: System MUST expose Grafana UI at `http://monitoring.local:3000` with authentication required
- **FR-017**: System MUST expose Alertmanager UI at `http://monitoring.local:9093` for alert status inspection
- **FR-018**: System MUST configure Grafana with strong admin password deployed from Ansible vault (not default `admin/admin`)
- **FR-019**: System MUST enable Docker nesting in monitoring LXC via Terraform configuration (`features: { nesting: 1 }`)
- **FR-020**: System MUST document Synology SNMP setup as manual prerequisite with DSM UI screenshots/steps
- **FR-021**: System MUST provide smoke test playbook/script that validates Prometheus targets UP, Grafana accessible, Alertmanager config valid
- **FR-022**: System MUST configure Prometheus retention period (15 days) to prevent unbounded disk growth (validated: 30s scrape interval × 15d × estimated metric cardinality = ~10GB per NFR-007 constraint)
- **FR-023**: System MUST configure Alertmanager to group repeated alerts by NAS hostname to prevent email spam
- **FR-024**: System MUST log all alert notifications (sent/failed) in Alertmanager for audit trail
- **FR-025**: System MUST support Ansible playbook idempotency (re-running playbook safe and produces no unexpected changes)
- **FR-026**: System MUST automatically backup Prometheus TSDB and Grafana volumes to NAS location `/volume1/homelab_backups/monitoring/` daily via cron job with date-stamped tarballs
- **FR-027**: System MUST document restore procedure including TSDB import and volume restoration steps
- **FR-028**: System MUST document upgrade procedure including version pinning strategy and rollback steps
- **FR-029**: System SHOULD restrict SNMP access on Synology to monitoring LXC IP `192.168.1.214` via DSM firewall/ACL (optional, documented in operations guide)
- **FR-030**: System MUST configure SNMPv3 with authPriv security level (MD5 authentication + AES encryption) for SNMP communication with Synology NAS
- **FR-031**: System MUST provide test alert procedure in documentation (manual trigger + expected email delivery)
- **FR-032**: System MUST expose Grafana via mDNS hostname `monitoring.local` resolvable on LAN without Tailscale connection
- **FR-033**: System MUST NOT require inbound internet connectivity for any monitoring functionality
- **FR-034**: System MUST NOT commit any secrets (SMTP passwords, Grafana admin password, SNMP community strings) to git repository

### Non-Functional Requirements

- **NFR-001**: Monitoring LXC MUST consume ≤ 2 vCPU / 4 GB RAM under normal operation (target: 1.5 vCPU / 2.5 GB actual usage)
- **NFR-002**: Prometheus scrape latency MUST be < 5 seconds for SNMP Exporter target under normal network conditions
- **NFR-003**: Grafana dashboard load time MUST be < 3 seconds for Synology dashboard with 24-hour time range
- **NFR-004**: Alert delivery latency MUST be < 2 minutes from condition trigger to email received in inbox
- **NFR-005**: Monitoring stack MUST survive LXC reboot and resume operation within 2 minutes without operator intervention
- **NFR-006**: Ansible playbook runtime MUST complete initial deployment in < 10 minutes on standard Proxmox host
- **NFR-007**: Prometheus TSDB disk usage MUST NOT exceed 20GB with 15-day retention and 30-second scrape intervals
- **NFR-008**: System MUST remain functional during Synology DSM upgrades (brief metrics gaps acceptable, no persistent failures)
- **NFR-009**: Documentation MUST include all manual prerequisites in numbered step-by-step format with DSM version compatibility notes

### Key Entities

- **monitoring LXC**: Container running observability stack at `192.168.1.214`, managed by Terraform/Ansible, runs Docker
- **Prometheus**: Time-series database scraping SNMP Exporter every 30 seconds, storing metrics with 15-day retention, evaluating alert rules
- **SNMP Exporter**: Translates SNMP OIDs from Synology NAS into Prometheus metrics format, listens on `:9116/snmp`
- **Grafana**: Visualization UI with auto-provisioned datasources/dashboards, authenticated access, persisted configuration
- **Alertmanager**: Routes alerts from Prometheus to email via SMTP, groups/deduplicates alerts, tracks notification state
- **Alert Rule**: Prometheus evaluation expression (e.g., `volume_usage > 85`) with severity/labels, triggers Alertmanager notification
- **Grafana Dashboard**: JSON definition provisioned from Ansible, displays Synology metrics in panels (gauge, graph, table)
- **SNMP Target**: Synology NAS IP `192.168.1.109` polled by Prometheus via SNMP Exporter with configured community string/credentials
- **SMTP Configuration**: Alertmanager settings (server, port, auth) deployed from Ansible vault variables, used for email delivery
- **Docker Volume**: Persistent storage for Prometheus TSDB (`prometheus_data`) and Grafana config (`grafana_data`), backed up to NAS

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Operator can view Synology NAS storage capacity in Grafana dashboard within 5 minutes of completing deployment
- **SC-002**: System delivers email alert within 2 minutes when NAS volume usage exceeds 85% in test scenario
- **SC-003**: Monitoring stack survives LXC reboot and resumes metrics collection within 2 minutes without manual intervention
- **SC-004**: Ansible playbook re-runs complete with idempotent result (no unexpected changes) in 100% of test iterations
- **SC-005**: Zero secrets (SMTP passwords, Grafana admin password) detected in git repository via `git grep -i password` or `git status`
- **SC-006**: Prometheus TSDB restored from backup retains 100% of historical data from backup timestamp
- **SC-007**: Grafana dashboard loads in < 3 seconds when displaying 24 hours of NAS metrics
- **SC-008**: Alert flapping prevented - repeated alert conditions generate max 1 email per 5-minute group interval
- **SC-009**: Terraform deployment completes successfully in < 5 minutes creating monitoring LXC with correct resource allocation
- **SC-010**: SNMP Exporter scrape success rate > 99% over 24-hour period under normal network conditions
- **SC-011**: Monitoring stack documentation reviewed and validated by executing each step on fresh Proxmox host (walkthrough test)
- **SC-012**: Resource utilization remains under NFR-001 limits (≤2 vCPU / 4GB RAM) during 7-day continuous operation test

## Assumptions *(mandatory)*

- **A-001**: Synology NAS (DSM 6.x or 7.x) supports SNMP v2c or v3 (operator verifies model compatibility before deployment)
- **A-002**: Operator has admin access to Synology DSM UI to enable SNMP service and configure community string/credentials
- **A-003**: LAN subnet `192.168.1.0/24` allows unrestricted communication between monitoring LXC and NAS (no firewall rules blocking SNMP port 161)
- **A-004**: mDNS / Avahi service running on Proxmox host for `.local` hostname resolution (already working per context)
- **A-005**: Operator has valid SMTP server credentials (Gmail, Mailgun, or other provider) for Alertmanager email delivery
- **A-006**: SMTP server allows outbound connections on port 587 (STARTTLS) from homelab network (not blocked by ISP)
- **A-007**: Existing reverse proxy LXC (`proxy` @ `192.168.1.211`) available if operator chooses to expose Grafana via proxy instead of direct access
- **A-008**: Proxmox host has internet connectivity during initial deployment for Docker image pulls (prometheus, grafana, snmp-exporter)
- **A-009**: NAS backup share `/volume1/homelab_backups/` exists and accessible via NFS from monitoring LXC (created in prior feature 013)
- **A-010**: Operator has basic understanding of Prometheus/Grafana concepts (metrics, queries, dashboards) or willing to learn from provided documentation

## Constraints

- **C-001**: Must use open-source monitoring tools only (Prometheus/Grafana ecosystem) - no proprietary or cloud-based solutions
- **C-002**: Must work without Tailscale connection - all monitoring functionality accessible on LAN (email alerts work from anywhere)
- **C-003**: Must not require Docker running on Synology NAS - all monitoring infrastructure on Proxmox LXC only
- **C-004**: Must not expose monitoring services to public internet - LAN access only (no port forwarding)
- **C-005**: Must use email-only alerting - no Slack, Discord, PagerDuty, or push notification integrations required
- **C-006**: Must fit within monitoring LXC resource limits (2 vCPU / 4GB RAM) - cannot scale beyond single LXC deployment
- **C-007**: Must support disaster recovery - monitoring stack rebuildable from Terraform/Ansible + backup tarball (no undocumented manual config)
- **C-008**: Must comply with homelab IaC standards - secrets in Ansible Vault, pinned versions, idempotent playbooks

## Out of Scope

- **OOS-001**: Advanced Grafana features (alerting UI, RBAC, LDAP integration) - basic auth only
- **OOS-002**: High availability / clustering - single monitoring LXC acceptable for homelab
- **OOS-003**: Log aggregation (Loki) - metrics-only scope, logs may be future feature
- **OOS-004**: Application performance monitoring (APM) for Immich/HomeAssistant - infrastructure metrics only
- **OOS-005**: Custom metric exporters beyond SNMP and node_exporter - no specialized app monitoring
- **OOS-006**: Grafana plugin ecosystem - use built-in panels only, no third-party plugins
- **OOS-007**: Multi-tenant Grafana (multiple organizations) - single operator use case
- **OOS-008**: Prometheus federation / remote write - single Prometheus instance sufficient
- **OOS-009**: Automated alert tuning / ML-based anomaly detection - static threshold alerts only
- **OOS-010**: Mobile app for Grafana - web UI access sufficient

## Risks & Mitigations

- **R-001**: **Risk**: SNMP polling overhead impacts NAS performance  
  **Mitigation**: Use 30-second scrape intervals (not aggressive), monitor NAS CPU via dashboard, adjust interval if needed. SNMP is lightweight protocol designed for network device monitoring.

- **R-002**: **Risk**: Prometheus TSDB grows unbounded, fills LXC disk  
  **Mitigation**: Configure 15-day retention, 32GB LXC disk sufficient for metrics volume. Monitor Prometheus disk usage via self-scrape, alert if >80% full.

- **R-003**: **Risk**: Email alerts not delivered due to SMTP auth failures  
  **Mitigation**: Test alert procedure in documentation, validate SMTP config during deployment. Alertmanager UI shows notification failures for troubleshooting.

- **R-004**: **Risk**: Synology SNMP OIDs differ between DSM versions, dashboard breaks  
  **Mitigation**: Document tested DSM versions, use standard OIDs from Synology MIB files. Provide troubleshooting steps to identify missing OIDs.

- **R-005**: **Risk**: Operator forgets Grafana admin password, locks self out  
  **Mitigation**: Store password in Ansible vault with retrieval instructions. Document Grafana password reset procedure via docker exec.

- **R-006**: **Risk**: Monitoring stack fails during LXC reboot, metrics gap unnoticed  
  **Mitigation**: Docker compose restart policy (unless-stopped), systemd service for compose stack. Monitor stack health via Uptime Kuma (separate monitoring).

- **R-007**: **Risk**: SNMPv2 community string leaked, unauthorized access to NAS SNMP  
  **Mitigation**: Use strong non-default community string in vault, restrict SNMP access to monitoring LXC IP via Synology firewall. Consider SNMPv3 for auth/encryption.

- **R-008**: **Risk**: Grafana dashboard import fails, operator gets blank UI  
  **Mitigation**: Use Grafana provisioning (not manual import), test dashboard JSON validity during deployment, provide sample dashboard in repo.

## Implementation Strategy

### Architecture Decision: Dedicated LXC with Docker Compose

**Chosen Approach**: Single LXC running Docker with multi-container compose stack

**Rationale**:
- **Isolation**: Monitoring infrastructure separated from monitored services, survives service LXC rebuilds
- **Resource Control**: LXC resource limits prevent monitoring from impacting host performance
- **Portability**: Docker compose simplifies version management and upgrades
- **IaC Alignment**: Terraform provisions LXC, Ansible deploys compose - familiar pattern from prior features

**Alternatives Considered**:
1. **Native packages** (apt install prometheus grafana) - Rejected: harder to version-pin, messier upgrades
2. **Separate LXCs per service** (prometheus-lxc, grafana-lxc) - Rejected: resource waste, complex networking
3. **Kubernetes (k3s)** - Rejected: overkill for homelab, complexity not justified for 4 containers

### Secret Management: Ansible Vault

**Chosen Approach**: Secrets stored in `ansible/group_vars/monitoring/vault.yml` encrypted with ansible-vault

**Rationale**:
- **Proven Pattern**: Already used for Proxmox backup age keys (Feature 013)
- **Built-in Tool**: No additional dependencies, works with existing Ansible workflow
- **Git Safe**: Encrypted vault file safe to commit, no .gitignore risks
- **Audit Trail**: Vault changes tracked in git history (encrypted)

**Variables in Vault**:
```yaml
# ansible/group_vars/monitoring/vault.yml (encrypted)
monitoring_grafana_admin_password: "StrongPassword123!"
monitoring_smtp_username: "alerts@example.com"
monitoring_smtp_password: "smtp-app-password"
monitoring_snmp_community_string: "MyS3cretCommunity"  # SNMPv2c
monitoring_snmpv3_user: "monitoring"  # SNMPv3
monitoring_snmpv3_auth_pass: "auth-password"
monitoring_snmpv3_priv_pass: "priv-password"
```

**Alternative Considered**:
- **Git-ignored secrets file** - Rejected: higher risk of accidental commit, no backup in repo history, harder to share with future GitHub Actions runner

### Grafana Dashboard Provisioning: Embedded JSON

**Chosen Approach**: Grafana dashboard JSON files deployed via Ansible to provisioning directory

**Rationale**:
- **No Clickops**: Dashboard available immediately after stack deployment
- **Version Control**: Dashboard changes tracked in git
- **Reproducibility**: Destroy/rebuild includes dashboards automatically

**Implementation**:
```
ansible/roles/monitoring_stack/files/grafana/dashboards/
  synology-nas.json
  proxmox-host.json (optional US4)
```

Ansible copies to `/var/lib/docker/volumes/grafana_data/_data/provisioning/dashboards/`

### Deployment Phases

**Phase 1: Core Infrastructure (US3)** - STOP POINT 1
- Terraform provisions monitoring LXC
- Ansible deploys Docker + compose stack
- Services running, accessible via IP
- **Test**: `curl http://192.168.1.214:9090/-/healthy` returns 200

**Phase 2: Synology Metrics (US1)** - STOP POINT 2
- SNMP exporter configured for Synology target
- Prometheus scrape config added
- Grafana dashboard provisioned
- **Test**: Dashboard shows live NAS metrics

**Phase 3: Email Alerting (US2)** - STOP POINT 3
- Alertmanager config with SMTP settings
- Prometheus alert rules for NAS conditions
- Test alert procedure validated
- **Test**: Manual trigger delivers email within 2 minutes

**Phase 4: Operations (US5)** - STOP POINT 4
- Backup script for TSDB volumes
- Upgrade procedure documented
- Smoke test playbook created
- **Test**: Backup/restore cycle preserves data

**Phase 5: Optional Expansion (US4)** - STOP POINT 5
- Node exporter on Proxmox host
- Additional dashboards for host/LXC metrics
- **Test**: Host dashboard populated with live data

### Manual Prerequisites (Minimal)

**Synology DSM Configuration** (5 minutes):
1. Log into DSM at `http://192.168.1.109:5000`
2. Navigate to **Control Panel → Terminal & SNMP** (DSM 7) or **Control Panel → SNMP** (DSM 6)
3. Enable SNMP service
4. Configure SNMPv3 (preferred) or SNMPv2c community string
5. (Optional) Add firewall rule restricting SNMP port 161 to `192.168.1.214`

**SMTP Provider Setup** (if not already done):
- Gmail: Create app-specific password
- Mailgun: Note SMTP credentials from dashboard
- Other: Ensure port 587 STARTTLS supported

All other configuration deployed via Ansible - no manual Grafana/Prometheus UI steps required.
