# Implementation Plan: Synology Metrics & Alerting

**Branch**: `017-synology-metrics` | **Date**: 2025-12-28 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/017-synology-metrics/spec.md`

## Summary

Deploy observability stack (Prometheus, Grafana, SNMP Exporter, Alertmanager) on dedicated monitoring LXC to provide real-time visibility into Synology NAS health (storage capacity, disk health, CPU/RAM, network) with proactive email alerting for critical conditions (volume >85% full, NAS down, disk SMART issues). Fully automated deployment via Terraform + Ansible with zero manual UI configuration, secrets in Ansible Vault, and daily automated backups of TSDB to NAS.

## Technical Context

**Language/Version**: Docker Compose (stack orchestration), Bash 5.x (backup scripts), Ansible 2.14+
**Primary Dependencies**: Prometheus 2.48+, Grafana 10.2+, SNMP Exporter 0.25+, Alertmanager 0.26+, Docker 24+
**Storage**: Prometheus TSDB (Docker volume, 15-day retention), Grafana config (Docker volume), NAS backups via NFS
**Testing**: Smoke test playbook (validate endpoints), manual alert testing, backup/restore validation
**Target Platform**: Debian 12 LXC on Proxmox VE 9.x, LAN-only access (no internet exposure)
**Project Type**: Infrastructure automation (Terraform LXC + Ansible compose deployment)
**Performance Goals**: <5s scrape latency, <3s dashboard load, <2min alert delivery, <10min initial deployment
**Constraints**: ≤2 vCPU / 4GB RAM, 32GB disk, SNMPv3-only (no Docker on NAS), email-only alerting, secrets in vault
**Scale/Scope**: 1 Synology NAS (192.168.1.109), 1 monitoring LXC (192.168.1.214), 4-6 dashboard panels, 3 alert rules

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

✅ **No constitution violations** - Feature follows established patterns:
- Terraform provisions LXC infrastructure (separation of concerns upheld)
- Ansible deploys and configures services (consistent with existing roles)
- Static IP assignment (192.168.1.214) follows network conventions
- Secrets stored in Ansible Vault (secrets policy compliant)
- One LXC per logical service (services model compliant)
- Docker compose used (consistent with existing service deployments)

## Project Structure

### Documentation (this feature)

```text
specs/017-synology-metrics/
├── spec.md              # Feature specification with clarifications (complete)
├── plan.md              # This file - implementation architecture
├── research.md          # Phase 0: Technology decisions and best practices
├── data-model.md        # Phase 1: Metrics schema and alert rule definitions
├── quickstart.md        # Phase 1: Quick deployment guide for operators
├── contracts/           # Phase 1: Prometheus scrape configs, alert rule YAML
│   ├── prometheus.yml   # Scrape targets and evaluation rules
│   ├── alertmanager.yml # Routing and SMTP configuration
│   └── alerts.yml       # Alert rule definitions (volume usage, NAS down, SMART)
└── tasks.md             # Phase 2: Task breakdown by user story (created by /speckit.tasks)
```

### Source Code (repository root)

```text
terraform/
├── main.tf                          # Modify: Add monitoring LXC module call
├── modules/
│   └── lxc_service/                 # Existing: Reuse for monitoring LXC
│       └── main.tf                  # No changes needed (generic LXC module)
└── prod.tfvars                      # Existing: Add monitoring LXC variables

ansible/
├── group_vars/
│   └── monitoring/
│       ├── vars.yml                 # Create: Monitoring stack config (Prometheus, Grafana, SNMP targets)
│       └── vault.yml                # Create: Secrets (Grafana admin pass, SMTP creds, SNMP community string)
├── host_vars/
│   └── monitoring/
│       └── vars.yml                 # Create: Host-specific overrides (if needed)
├── inventories/
│   └── generated/
│       └── hosts.yml                # Modify: Add monitoring LXC after Terraform apply
├── playbooks/
│   ├── site.yml                     # Modify: Import monitoring.yml playbook
│   └── monitoring.yml               # Create: Orchestrate monitoring stack deployment
└── roles/
    ├── monitoring_stack/            # Create: Deploy Docker compose observability stack
    │   ├── defaults/
    │   │   └── main.yml             # Defaults: versions, ports, retention periods
    │   ├── tasks/
    │   │   ├── main.yml             # Orchestrate: Docker install → compose deploy → backup config
    │   │   ├── docker.yml           # Install Docker (delegate to geerlingguy.docker)
    │   │   ├── compose_stack.yml    # Deploy Prometheus/Grafana/SNMP/Alertmanager compose
    │   │   ├── grafana_provision.yml # Copy dashboard JSON and datasource YAML
    │   │   └── backup_cron.yml      # Configure daily backup cron job
    │   ├── templates/
    │   │   ├── docker-compose.yml.j2 # Compose stack with pinned versions
    │   │   ├── prometheus.yml.j2     # Prometheus config (scrape targets, alert rules)
    │   │   ├── snmp.yml.j2           # SNMP Exporter auth config (SNMPv3 credentials from vault)
    │   │   ├── alertmanager.yml.j2   # Alertmanager config (SMTP settings from vault)
    │   │   └── backup-monitoring.sh.j2 # Backup script for TSDB and Grafana volumes
    │   ├── files/
    │   │   ├── grafana/
    │   │   │   ├── provisioning/
    │   │   │   │   ├── datasources/
    │   │   │   │   │   └── prometheus.yml # Auto-provision Prometheus datasource
    │   │   │   │   └── dashboards/
    │   │   │   │       └── default.yml    # Dashboard provider config
    │   │   │   └── dashboards/
    │   │   │       └── synology-nas.json # Core dashboard (4-6 panels)
    │   │   └── prometheus/
    │   │       └── alerts.yml        # Alert rule definitions (volume, NAS down, SMART)
    │   └── handlers/
    │       └── main.yml              # Handlers: restart compose stack
    └── geerlingguy.docker/          # Existing: Install Docker CE (reuse from prior features)

docs/
└── operations/
    └── monitoring/
        ├── synology-snmp-setup.md    # Create: Manual prerequisite (enable SNMP in DSM UI)
        ├── runbook-alert-testing.md  # Create: Test alert procedure (manual trigger)
        └── runbook-upgrades.md       # Create: Upgrade procedure (version pins, rollback)

scripts/
└── monitoring/
    └── smoke-test.sh                 # Create: Validate Prometheus/Grafana/Alertmanager endpoints
```

**Structure Decision**: Create dedicated `monitoring_stack` role for compose deployment. Reuse existing `lxc_service` Terraform module for LXC provisioning. Grafana provisioning via files (no manual import). Alert rules as YAML contracts in `specs/017-synology-metrics/contracts/`. Backup automation via cron job configured by Ansible.

## Architecture Decisions

### 1. Monitoring Stack Deployment: Docker Compose on LXC

**Decision**: Single docker-compose.yml with 4 services: Prometheus, Grafana, SNMP Exporter, Alertmanager

**Compose Stack Structure**:
```yaml
version: '3.8'
services:
  prometheus:
    image: prom/prometheus:v2.48.0
    volumes:
      - prometheus_data:/prometheus
      - ./prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - ./alerts.yml:/etc/prometheus/alerts.yml:ro
    command: --config.file=/etc/prometheus/prometheus.yml --storage.tsdb.retention.time=15d
    ports: ["9090:9090"]
    restart: unless-stopped

  grafana:
    image: grafana/grafana:10.2.3
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/provisioning:/etc/grafana/provisioning:ro
      - ./grafana/dashboards:/var/lib/grafana/dashboards:ro
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_ADMIN_PASSWORD}
    ports: ["3000:3000"]
    restart: unless-stopped

  snmp-exporter:
    image: prom/snmp-exporter:v0.25.0
    ports: ["9116:9116"]
    restart: unless-stopped

  alertmanager:
    image: prom/alertmanager:v0.26.0
    volumes:
      - ./alertmanager.yml:/etc/alertmanager/alertmanager.yml:ro
    ports: ["9093:9093"]
    restart: unless-stopped

volumes:
  prometheus_data:
  grafana_data:
```

**Rationale**:
- Single compose file simplifies deployment and lifecycle management
- Docker volumes persist data across container restarts (FR-012, FR-013)
- `unless-stopped` ensures auto-restart after LXC reboot (FR-014)
- Pinned versions prevent unintentional upgrades (FR-028)
- Read-only config mounts prevent container tampering
- No network exposure beyond LXC (all ports on 127.0.0.1 or bridged via LXC IP)

**Alternative Considered**: Separate LXCs per service - Rejected due to resource overhead (4 LXCs × 1GB RAM = 4GB vs 1 LXC × 2.5GB actual usage)

### 2. SNMP Integration: SNMPv3 with Authentication and Privacy

**Decision**: Primary implementation uses SNMPv3 with authPriv security level (MD5 authentication + AES encryption)

**SNMP Configuration** (Prometheus scrape):
```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'synology-snmp'
    static_configs:
      - targets: ['192.168.1.109']
    metrics_path: /snmp
    params:
      module: [synology]
      auth: [synology_v3]  # References snmp.yml auth config
    relabel_configs:
      - source_labels: [__address__]
        target_label: __param_target
      - source_labels: [__param_target]
        target_label: instance
      - target_label: __address__
        replacement: snmp-exporter:9116
```

**SNMP Exporter Auth** (via snmp.yml config file):
```yaml
# snmp.yml (deployed to /opt/monitoring/snmp-exporter/snmp.yml)
synology_v3:
  version: 3
  security_level: authPriv
  username: ${SNMP_V3_USERNAME}
  auth_protocol: MD5
  auth_password: ${SNMP_V3_AUTH_PASSWORD}
  priv_protocol: AES
  priv_password: ${SNMP_V3_PRIV_PASSWORD}

# docker-compose.yml snmp-exporter service
volumes:
  - ./snmp.yml:/etc/snmp_exporter/snmp.yml:ro
environment:
  - SNMP_V3_USERNAME=${SNMP_V3_USERNAME}
  - SNMP_V3_AUTH_PASSWORD=${SNMP_V3_AUTH_PASSWORD}
  - SNMP_V3_PRIV_PASSWORD=${SNMP_V3_PRIV_PASSWORD}
```

**Rationale**:
- SNMPv3 natively supported by Synology DSM 7.x (verified by operator NAS screenshot)
- Addresses Synology security warning about SNMPv1/v2c insecurity
- authPriv provides authentication (MD5) + encryption (AES-128) for SNMP traffic (FR-029)
- Credentials stored in Ansible Vault (FR-010, FR-034)
- SNMP Exporter supports SNMPv3 natively via auth config
- No plaintext community strings on network

**Security Benefits over v2c**:
- Encrypted SNMP traffic prevents credential sniffing on LAN
- Per-user authentication (vs shared community string)
- Replay attack protection via timestamps
- Integrity verification via HMAC-MD5
- Synology DSM UI recommends SNMPv3 as best practice

### 3. Grafana Dashboard Provisioning: Zero-Clickops

**Decision**: Dashboard JSON pre-deployed via Grafana provisioning directories

**Provisioning Flow**:
1. Ansible copies `synology-nas.json` to LXC at `/opt/monitoring/grafana/dashboards/`
2. Docker compose mounts to `/var/lib/grafana/dashboards/synology-nas.json:ro`
3. Grafana provisioning config (`/etc/grafana/provisioning/dashboards/default.yml`) watches directory
4. Dashboard appears in Grafana UI immediately after startup

**Dashboard Panels** (4-6 core metrics per clarifications):
```json
{
  "title": "Synology NAS",
  "panels": [
    {"title": "Storage Capacity", "type": "gauge", "targets": ["volume_used_percent"]},
    {"title": "Disk Health", "type": "table", "targets": ["disk_status", "disk_temp"]},
    {"title": "CPU Usage", "type": "graph", "targets": ["cpu_usage_percent"]},
    {"title": "Memory Usage", "type": "graph", "targets": ["memory_usage_percent"]},
    {"title": "Network Throughput", "type": "graph", "targets": ["network_rx_bytes", "network_tx_bytes"]},
    {"title": "Disk Temperature", "type": "graph", "targets": ["disk_temp_celsius"]}
  ]
}
```

**Rationale**:
- No manual import (FR-005, US3 acceptance criteria)
- Dashboard versioned in git alongside code
- Reproducible: destroy/rebuild includes dashboard automatically
- Operator can iterate dashboard in Grafana UI, export JSON, commit to repo

**Alternative Considered**: Grafana API provisioning - Rejected due to added complexity and race conditions during bootstrap

### 4. Alerting: Per-Volume Thresholds with Email Delivery

**Decision**: Prometheus alert rules evaluate per-volume usage, Alertmanager routes to email

**Alert Rules** (`prometheus/alerts.yml`):
```yaml
groups:
  - name: synology_nas
    interval: 30s
    rules:
      - alert: SynologyVolumeHighUsage
        expr: volume_used_percent > 85
        for: 5m
        labels:
          severity: warning
          component: storage
        annotations:
          summary: "NAS volume {{ $labels.volume }} usage critical"
          description: "Volume {{ $labels.volume }} is {{ $value }}% full (threshold: 85%)"

      - alert: SynologyNASDown
        expr: up{job="synology-snmp"} == 0
        for: 2m
        labels:
          severity: critical
          component: availability
        annotations:
          summary: "Synology NAS unreachable"
          description: "SNMP scrape failed for 3 consecutive attempts"

      - alert: SynologyDiskSMARTWarning
        expr: disk_smart_status != 1  # Assuming 1=healthy, 0=warning
        for: 5m
        labels:
          severity: warning
          component: disk
        annotations:
          summary: "Disk {{ $labels.disk }} SMART warning"
          description: "Disk health status abnormal (check DSM UI)"
```

**Alertmanager Configuration** (SMTP routing):
```yaml
# alertmanager.yml
global:
  smtp_smarthost: '{{ monitoring_smtp_host }}:587'
  smtp_from: '{{ monitoring_smtp_from }}'
  smtp_auth_username: '{{ monitoring_smtp_username }}'
  smtp_auth_password: '{{ monitoring_smtp_password }}'
  smtp_require_tls: true

route:
  receiver: 'email-alerts'
  group_by: ['alertname', 'volume', 'disk']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h

receivers:
  - name: 'email-alerts'
    email_configs:
      - to: '{{ monitoring_alert_email }}'
        headers:
          Subject: '[Homelab] {{ .GroupLabels.alertname }}'
```

**Rationale**:
- Per-volume alerting prevents missed issues on multi-volume NAS (clarification decision)
- 5-minute `for` clause reduces alert flapping (edge case mitigation)
- Group interval prevents email spam (FR-023, NFR-004)
- SMTP credentials from Ansible Vault (FR-010)
- Test alert via `amtool` documented in runbook (FR-031)

### 5. Backup Automation: Daily Cron with NFS Mount

**Decision**: Automated daily backup via cron job, TSDB and Grafana volumes to NAS

**Backup Script** (`backup-monitoring.sh`):
```bash
#!/bin/bash
set -euo pipefail

BACKUP_DIR="/mnt/nas-backup"
DATE=$(date +%Y%m%d-%H%M%S)
BACKUP_FILE="monitoring-backup-${DATE}.tar.gz"

# Mount NAS (assumes NFS export from Feature 013)
mount -t nfs 192.168.1.109:/volume1/homelab_backups/monitoring ${BACKUP_DIR}

# Backup Docker volumes
docker run --rm \
  -v prometheus_data:/prometheus:ro \
  -v grafana_data:/grafana:ro \
  -v ${BACKUP_DIR}:/backup \
  alpine tar czf /backup/${BACKUP_FILE} /prometheus /grafana

# Cleanup old backups (keep 30 days)
find ${BACKUP_DIR} -name "monitoring-backup-*.tar.gz" -mtime +30 -delete

umount ${BACKUP_DIR}
echo "Backup completed: ${BACKUP_FILE}"
```

**Cron Configuration**:
```bash
# Deployed by Ansible to /etc/cron.d/monitoring-backup
0 3 * * * root /usr/local/sbin/backup-monitoring.sh >> /var/log/monitoring-backup.log 2>&1
```

**Rationale**:
- Daily 3 AM backup avoids peak usage (clarification: fully automated)
- NFS mount reuses existing NAS share from Feature 013 (A-009)
- 30-day retention balances disk usage vs recovery window
- Logs to file for troubleshooting (FR-024)
- Volume mounts as read-only prevent accidental modification

**Alternative Considered**: Manual backup only - Rejected per clarification session (operator chose Option A: fully automated)

### 6. Secrets Management: Ansible Vault for All Credentials

**Decision**: All secrets stored in `ansible/group_vars/monitoring/vault.yml`, encrypted with ansible-vault

**Vault Contents**:
```yaml
# ansible/group_vars/monitoring/vault.yml (encrypted)
monitoring_grafana_admin_password: "{{ vault_grafana_admin_password }}"
monitoring_smtp_host: "smtp.gmail.com"
monitoring_smtp_username: "{{ vault_smtp_username }}"
monitoring_smtp_password: "{{ vault_smtp_app_password }}"
monitoring_smtp_from: "homelab-alerts@example.com"
monitoring_alert_email: "operator@example.com"
monitoring_snmp_v3_username: "{{ vault_snmp_v3_username }}"
monitoring_snmp_v3_auth_password: "{{ vault_snmp_v3_auth_password }}"
monitoring_snmp_v3_priv_password: "{{ vault_snmp_v3_priv_password }}"
```

**Deployment Flow**:
1. Operator runs: `ansible-vault edit group_vars/monitoring/vault.yml`
2. Ansible prompts for vault password during playbook run
3. Templates inject secrets into compose env file or config files
4. Git commit includes encrypted vault (safe to push)

**Rationale**:
- Proven pattern from Feature 013 (Proxmox backup age keys)
- No plaintext secrets in repo (FR-034, US5 acceptance)
- Vault password stored in operator's password manager (not in git)
- Future GitHub Actions runner can use vault password from secrets

### 7. Deployment Phases with Stop Points

**Phase 1: Core Infrastructure** - STOP POINT 1
- Terraform provisions monitoring LXC (192.168.1.214)
- Ansible installs Docker via geerlingguy.docker role
- LXC accessible, Docker running
- **Test**: `ssh root@monitoring.local 'docker ps'` succeeds

**Phase 2: Observability Stack** - STOP POINT 2
- Ansible deploys compose stack
- Prometheus, Grafana, SNMP Exporter, Alertmanager running
- Services accessible via LXC IP
- **Test**: `curl http://192.168.1.214:9090/-/healthy` returns 200

**Phase 3: SNMP Metrics Collection** - STOP POINT 3
- Prometheus scrape config for Synology target
- SNMP Exporter configured with community string
- Grafana dashboard provisioned
- **Test**: Prometheus target UP, dashboard shows live NAS metrics

**Phase 4: Email Alerting** - STOP POINT 4
- Alertmanager SMTP config deployed
- Prometheus alert rules loaded
- Test alert procedure validated
- **Test**: Manual trigger delivers email within 2 minutes

**Phase 5: Operational Tooling** - STOP POINT 5
- Backup cron configured
- Smoke test script deployed
- Documentation complete
- **Test**: Backup completes successfully, smoke test passes

## Dependencies

**External Prerequisites** (manual operator steps):
1. Synology SNMPv3 enabled (5 min) - DSM UI → Terminal & SNMP → Enable SNMPv3 service, create user with authPriv
2. SMTP credentials available - Gmail app password or Mailgun account
3. NAS backup share accessible - `/volume1/homelab_backups/` from Feature 013

**Terraform Module Dependencies**:
- Existing `modules/lxc_service` (no changes needed)

**Ansible Role Dependencies**:
- `geerlingguy.docker` (already in requirements.yml from prior features)

**Docker Image Dependencies** (pulled during deployment):
- `prom/prometheus:v2.48.0` (~200MB)
- `grafana/grafana:10.2.3` (~350MB)
- `prom/snmp-exporter:v0.25.0` (~50MB)
- `prom/alertmanager:v0.26.0` (~60MB)
- Total: ~660MB (fits within 32GB LXC disk)

## Risk Mitigation

### R-001: SNMP OID Compatibility
**Risk**: Dashboard breaks if Synology DSM version uses different SNMP OIDs
**Mitigation**: Test against DSM 7.x (confirmed SNMPv3 support from operator NAS), document tested versions in prerequisite guide, provide OID troubleshooting section in runbook

### R-002: Prometheus TSDB Disk Growth
**Risk**: Unbounded metrics storage fills 32GB LXC disk
**Mitigation**: 15-day retention configured (FR-022), estimated 10GB usage per NFR-007, self-monitoring alert if disk >80% full

### R-003: Alert Delivery Failures
**Risk**: SMTP auth fails silently, operator unaware of critical NAS issues
**Mitigation**: Alertmanager UI shows failed notifications (FR-017), test alert procedure in runbook (FR-031), separate Uptime Kuma monitor for monitoring stack health

### R-004: mDNS Resolution Failures
**Risk**: `monitoring.local` hostname unresolvable, operator cannot access Grafana
**Mitigation**: Documentation includes both mDNS and direct IP access methods, fallback to `192.168.1.214:3000`

### R-005: Monitoring Stack Downtime
**Risk**: LXC reboot causes metrics gap, alerts not fired
**Mitigation**: Docker compose `restart: unless-stopped` policy (FR-014), systemd service for compose (future enhancement), separate Uptime Kuma monitor detects monitoring stack down

## Next Steps

1. **Phase 0: Research** (`/speckit.plan` auto-generates research.md)
   - Document tested Synology SNMP OIDs for DSM 7.x with SNMPv3
   - Validate SNMP Exporter SNMPv3 auth configuration format
   - Identify Grafana dashboard JSON structure for 4-6 panels
   - Validate Alertmanager SMTP configuration with Gmail/Mailgun
   - Research SNMP Exporter generator.yml for custom Synology MIB

2. **Phase 1: Design** (`/speckit.plan` auto-generates data-model.md, contracts/)
   - Define Prometheus scrape intervals and retention
   - Create alert rule definitions (volume, NAS down, SMART)
   - Design Grafana dashboard JSON (storage gauge, disk table, CPU/RAM/network graphs)
   - Define backup script structure and cron schedule

3. **Phase 2: Tasks** (`/speckit.tasks` generates tasks.md)
   - Break down implementation into Terraform changes, Ansible role creation, testing validation
   - Assign task IDs, priorities, parallelization opportunities
   - Define acceptance criteria per user story

4. **Implementation**: Execute tasks.md sequentially with stop point validation
