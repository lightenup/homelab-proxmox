# Implementation Plan: Minimal Monitoring & Alerting

**Feature**: 011-monitoring-alerting  
**Created**: December 20, 2025  
**Status**: Draft  
**Updated**: December 20, 2025 (after spec clarifications)

## Overview

This plan outlines the technical approach for implementing a minimal, self-hosted monitoring and alerting system using Uptime Kuma for the dashboard and email (SMTP) for notifications. The implementation follows existing homelab patterns: Terraform provisions infrastructure, Ansible configures services (including automated monitor provisioning via API), and all secrets are managed via Ansible Vault.

---

## Technical Approach

### Architecture Decision: Uptime Kuma with Email Notifications

**Choice**: Use Uptime Kuma for monitoring dashboard with email (SMTP) notifications.

**Rationale**:
- **Uptime Kuma**: 
  - Simple, modern web UI with minimal configuration
  - Supports 90+ notification integrations including SMTP email
  - Self-hosted, no external dependencies for core functionality
  - SQLite backend (low resource usage)
  - Active development and REST API for automation
  - Built-in authentication for security
- **Email (SMTP) Notifications**:
  - Zero inbound exposure (outbound SMTP only)
  - Works everywhere (no special apps or services required)
  - Easy integration with all monitoring stacks
  - Mobile-friendly (all phones have email clients)
  - Can use existing email provider (Gmail, Outlook, etc.)
  - No additional self-hosted components needed

**Alternatives considered**:
- **ntfy self-hosted**: Rejected - requires additional container, mobile app installation, topic management complexity
- **Discord webhook**: Rejected - external service dependency, requires Discord account
- **Prometheus + Grafana**: Rejected - too complex for "minimal" requirement, overkill for binary UP/DOWN checks

**Decision**: Implement SMTP email notifications exclusively with STARTTLS authentication (port 587).

---

## Infrastructure Design

### Terraform Changes

**New LXC Module Instance**: `monitoring`

```hcl
# terraform/main.tf additions
module "monitoring" {
  source = "./modules/lxc_service"
  
  node_name    = var.proxmox_node
  lxc_id       = var.service_ids["monitoring"]
  lxc_hostname = "monitoring"
  lxc_ip       = var.service_ips["monitoring"]
  lxc_gateway  = var.lxc_gateway
  
  # Minimal resources for monitoring stack
  cores  = 2
  memory = 2048  # 2GB RAM
  
  rootfs_storage = var.lxc_storage_pool
  rootfs_size    = "10G"
  
  # Debian 12 template (consistent with other services)
  ostemplate = "local:vztmpl/debian-12-standard_12.2-1_amd64.tar.zst"
  
  # Unprivileged container (Docker compatible)
  unprivileged = true
  
  # Start on boot
  onboot = true
  
  # Network configuration
  nameserver = var.lxc_nameserver
  searchdomain = var.lxc_searchdomain
  
  # SSH key for ansible user
  ssh_public_keys = var.ssh_public_keys
}
```

**Variable Updates**:

```hcl
# terraform/environments/prod.tfvars additions
service_ids = {
  # ... existing services ...
  monitoring = 204
}

service_ips = {
  # ... existing services ...
  monitoring = "192.168.1.204"
}
```

**Output Updates**:

```hcl
# terraform/outputs.tf additions
output "monitoring_ip" {
  value = module.monitoring.lxc_ip
}

output "monitoring_hostname" {
  value = module.monitoring.lxc_hostname
}
```

### Dynamic Inventory Integration

The existing inventory script (`scripts/update_ansible_inventory.sh`) will automatically detect the new `monitoring` LXC from Terraform outputs and add it to the generated inventory. No manual inventory changes required.

**Expected inventory structure**:

```yaml
# ansible/inventories/generated/hosts.yml
all:
  children:
    services:
      hosts:
        # ... existing services ...
        monitoring:
          ansible_host: 192.168.1.204
          ansible_user: ansible
```

---

## Ansible Implementation

### Role Structure

**New Roles**:

1. **`monitoring_stack`**: Main orchestration role
   - Installs Docker (delegates to geerlingguy.docker)
   - Deploys Docker Compose configuration for Uptime Kuma
   - Configures systemd service for stack management
   - Runs verification tasks

2. **`uptime_kuma`**: Uptime Kuma specific configuration
   - Waits for container readiness
   - Creates admin user via API (on first run)
   - Provisions monitors automatically via API
   - Configures SMTP notification channel via API
   - Runs idempotency checks

### Docker Compose Templates

**Uptime Kuma Compose Template**: `ansible/roles/monitoring_stack/templates/docker-compose.yml.j2`

```yaml
version: '3.8'

services:
  uptime-kuma:
    image: louislam/uptime-kuma:{{ uptime_kuma_version | default('1') }}
    container_name: uptime-kuma
    restart: unless-stopped
    ports:
      - "{{ uptime_kuma_port | default('3001') }}:3001"
    volumes:
      - uptime-kuma-data:/app/data
    environment:
      - TZ={{ timezone | default('America/New_York') }}
    labels:
      - "com.centurylinklabs.watchtower.enable=true"

volumes:
  uptime-kuma-data:
    driver: local
```

### Systemd Service

**Template**: `ansible/roles/monitoring_stack/templates/monitoring-stack.service.j2`

```ini
[Unit]
Description=Monitoring Stack (Uptime Kuma)
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/monitoring
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

### Playbook Integration

**New Playbook**: `ansible/playbooks/monitoring.yml`

```yaml
---
# Monitoring stack deployment playbook
# Purpose: Deploy Uptime Kuma for service monitoring with email alerting
# Usage: ansible-playbook playbooks/monitoring.yml

- name: Deploy monitoring stack
  hosts: monitoring
  become: true
  
  roles:
    - geerlingguy.docker
    - monitoring_stack
    - uptime_kuma  # Includes API-based monitor provisioning

  post_tasks:
    - name: Display monitoring URLs
      ansible.builtin.debug:
        msg:
          - "Uptime Kuma dashboard: http://monitoring.local:3001"
          - "Login with credentials from vault.yml (uptime_kuma_admin_user/password)"
          - "Monitors have been configured automatically via API"
          - "Email notifications configured via SMTP"
```

**Integration into site.yml**:

```yaml
# ansible/playbooks/site.yml
- import_playbook: monitoring.yml
  tags: [monitoring]
```

### Variables

**Group Variables**: `ansible/group_vars/monitoring/vars.yml`

```yaml
---
# Monitoring stack configuration
uptime_kuma_version: "1"  # Pin to major version, auto-update minor
uptime_kuma_port: 3001

# Timezone for container logs
timezone: "America/New_York"

# API automation settings
uptime_kuma_api_wait_timeout: 120  # seconds to wait for container readiness
uptime_kuma_api_retry_delay: 5     # seconds between API call retries

# Monitor definitions (automatically provisioned via API)
monitoring_targets:
  - name: "Proxmox Web UI"
    type: "https"
    url: "https://pve.local:8006"
    interval: 60
    retries: 3
    accepted_statuscodes: ["200-299"]
    
  - name: "Reverse Proxy"
    type: "http"
    url: "http://proxy.local:80"
    interval: 60
    retries: 3
    
  - name: "Immich Photos"
    type: "http"
    url: "http://immich.local:2283"
    interval: 60
    retries: 3
    
  - name: "Home Assistant"
    type: "http"
    url: "http://homeassistant.local:8123"
    interval: 60
    retries: 3
```

**Secrets**: `ansible/group_vars/monitoring/vault.yml` (encrypted with ansible-vault)

```yaml
---
# Monitoring secrets
# Encrypt with: ansible-vault encrypt ansible/group_vars/monitoring/vault.yml

# Uptime Kuma admin credentials
uptime_kuma_admin_user: "admin"
uptime_kuma_admin_password: "change_me_to_secure_password"

# Email SMTP configuration
smtp_host: "smtp.gmail.com"
smtp_port: 587
smtp_user: "homelab-alerts@example.com"
smtp_password: "app-specific-password-here"
smtp_from: "homelab-alerts@example.com"
smtp_to: "admin@example.com"
```

### Role Tasks

**Key Tasks** (detailed in tasks.md, summary here):

1. **monitoring_stack/tasks/main.yml**:
   - Install Docker via geerlingguy.docker role
   - Create /opt/monitoring directory
   - Template docker-compose.yml
   - Template systemd service
   - Start and enable monitoring-stack.service
   - Verify container is running
   - Wait for Uptime Kuma HTTP endpoint to be ready

2. **uptime_kuma/tasks/main.yml**:
   - Wait for API to be accessible (with retry logic)
   - Check if admin user exists (idempotency)
   - Create admin user via setup API (on first run only)
   - Get API token for admin user
   - Configure SMTP notification via API
   - Loop through monitoring_targets and create/update monitors via API
   - Verify all monitors are configured correctly
   - Test notification delivery (optional manual step)

---

## Secrets Management

### Strategy

**Approach**: Use Ansible Vault for notification channel credentials, with `.gitignore` patterns to prevent accidental commits of unencrypted secrets.

**Vault File**: `ansible/group_vars/monitoring/vault.yml`

```yaml
---
$ANSIBLE_VAULT;1.1;AES256
... encrypted content ...
```

**Gitignore Patterns** (already exist from Feature 008b):

```gitignore
# Ansible secrets
**/vault.yml
**/*secret*.yml
**/*_secrets.yml
```

**Usage in Playbooks**:

```yaml
# Automatically decrypted when vault password file exists at ~/.ansible_vault_pass
- name: Configure SMTP notification via API
  ansible.builtin.uri:
    url: "http://localhost:3001/api/notification"
    method: POST
    body_format: json
    body:
      type: "smtp"
      name: "Email Alerts"
      smtp_host: "{{ smtp_host }}"
      smtp_port: "{{ smtp_port }}"
      smtp_username: "{{ smtp_user }}"
      smtp_password: "{{ smtp_password }}"
      smtp_from: "{{ smtp_from }}"
      smtp_to: "{{ smtp_to }}"
    headers:
      Authorization: "Bearer {{ uptime_kuma_api_token }}"
  no_log: true
```

### Initial Secrets Setup

**Manual Step** (documented in tasks.md STOP POINT):

```bash
# Create encrypted vault file
ansible-vault create ansible/group_vars/monitoring/vault.yml

# Edit existing vault file
ansible-vault edit ansible/group_vars/monitoring/vault.yml

# Add secrets (SMTP configuration):
---
# Uptime Kuma admin credentials
uptime_kuma_admin_user: "admin"
uptime_kuma_admin_password: "change_me_to_secure_password"

# Email SMTP configuration
smtp_host: "smtp.gmail.com"
smtp_port: 587
smtp_user: "homelab-alerts@example.com"
smtp_password: "app-specific-password-here"
smtp_from: "homelab-alerts@example.com"
smtp_to: "admin@example.com"

# Future: Discord webhook alternative (currently not implemented)
# discord_webhook_url: "https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN"
```

---

## Monitoring Configuration

### Automated Monitor Provisioning

**Approach**: Monitors are provisioned automatically via Uptime Kuma REST API during Ansible deployment. This ensures reproducibility and eliminates manual UI configuration.

**API Workflow**:

1. **Wait for container readiness**: Poll http://localhost:3001 until HTTP 200 (up to 2 minutes)
2. **Setup admin account** (first run only): POST to /api/setup with admin credentials from vault
3. **Login and get token**: POST to /api/login with admin credentials, extract auth token
4. **Configure SMTP notification**: POST to /api/notification with SMTP settings from vault
5. **Create monitors**: Loop through monitoring_targets, POST to /api/monitor for each service
6. **Verify configuration**: GET /api/monitor to confirm all monitors exist

**Idempotency**: 
- Admin setup skipped if account already exists (check /api/status)
- Monitors checked by name before creation (GET /api/monitor, compare by name)
- SMTP notification updated if already exists (PUT instead of POST)

**Manual Steps** (post-deployment):
- Access dashboard: http://monitoring.local:3001
- Login with uptime_kuma_admin_user/password from vault
- Verify monitors are running and showing correct status
- Test notification: Use "Test" button in Settings → Notifications

### Monitor Configuration Standards

**Recommended Settings**:

- **Check Interval**: 60 seconds (balance between responsiveness and resource usage)
- **Retry Count**: 3 retries (reduces false positives from transient issues)
- **Down Threshold**: 2 consecutive failed checks = DOWN (total ~2 minutes before alert)
- **Up Threshold**: 1 successful check = UP (immediate recovery notification)
- **Notification Options**:
  - Send on DOWN ✓
  - Send on UP (recovery) ✓
  - Repeat DOWN notifications: Every 30 minutes (avoid alert storms)

---

## Verification Strategy

### Automated Verification (Ansible Tasks)

1. **Docker Status**: Verify Docker service is running
2. **Container Status**: Verify uptime-kuma container is running
3. **Port Accessibility**: Verify port 3001 is listening
4. **HTTP Health Check**: Curl http://localhost:3001 returns HTTP 200
5. **API Accessibility**: GET /api/status returns valid JSON
6. **Monitor Count**: GET /api/monitor returns expected number of monitors (4)
7. **Notification Config**: GET /api/notification returns SMTP notification configured

### Manual Verification (Runbook)

1. **Dashboard Access**: Browse to http://monitoring.local:3001 from LAN device
2. **Authentication**: Login with admin credentials from vault
3. **Monitor Status**: Verify all 4 monitors show UP status (green)
4. **Notification Test**: 
   - Stop Immich service: `systemctl stop immich` (on immich LXC)
   - Wait 2 minutes for down threshold
   - Check email inbox for DOWN notification
   - Start Immich service: `systemctl start immich`
   - Check email for recovery notification

### Idempotency Verification

```bash
# Run playbook twice, verify changed=0 on second run
ansible-playbook playbooks/monitoring.yml
ansible-playbook playbooks/monitoring.yml  # Should show changed=0
```

---

## Migration and Rollback

### Deployment Risk

**Risk Level**: Low
- New infrastructure (no impact on existing services)
- Monitoring is passive (only observes, doesn't modify monitored services)
- Can be deployed and tested without affecting production

### Rollback Plan

If monitoring stack causes issues:

1. **Disable Monitoring**: 
   ```bash
   systemctl stop monitoring-stack
   systemctl disable monitoring-stack
   ```

2. **Destroy Infrastructure**:
   ```bash
   cd terraform
   terraform destroy -target=module.monitoring
   ```

3. **Clean Inventory**:
   ```bash
   ./scripts/update_ansible_inventory.sh
   ```

### Backup Considerations

**Monitoring Data**: Not critical; historical data loss is acceptable for MVP.

**Uptime Kuma Configuration**: Can be exported manually via Settings → Backup before making major changes.

**Future Enhancement**: Automated backups of Uptime Kuma SQLite database to NFS.

---

## Documentation Plan

### Deliverables

1. **Operational Runbook**: `docs/runbooks/monitoring-setup.md`
   - Initial deployment steps
   - SMTP configuration requirements
   - Manual verification procedures
   - Adding new monitors (via Ansible variables)
   - Troubleshooting common issues (API errors, SMTP auth failures)
   - Maintenance procedures

2. **Architecture Diagram**: ASCII diagram in runbook showing:
   - Monitoring LXC with Docker container
   - Monitored services (pve, proxy, immich, homeassistant)
   - Notification flow (Uptime Kuma → SMTP → email client)

3. **README Updates**: Add monitoring.yml playbook to "Available Playbooks" section

---

## Dependencies

### External Dependencies

- **Docker Images**:
  - `louislam/uptime-kuma:1` (from Docker Hub)

- **Ansible Roles**:
  - `geerlingguy.docker` (already in requirements.yml, version pinned)

- **SMTP Server**:
  - User-provided SMTP server (Gmail, Outlook, self-hosted, etc.)
  - Must support STARTTLS on port 587 with SMTP AUTH

### Internal Dependencies

- **Terraform**: Proxmox provider configured, service_ids and service_ips variables defined
- **Ansible**: Dynamic inventory generation functional, ansible user with sudo access
- **mDNS**: Avahi installed on LXCs for .local hostname resolution

---

## Testing Strategy

### Unit Testing (Role Level)

- Verify Docker Compose templates render correctly
- Verify systemd service template renders correctly
- Verify directory creation tasks are idempotent

### Integration Testing (Playbook Level)

- Run playbook against monitoring LXC
- Verify all containers start successfully
- Verify dashboard is accessible via mDNS
- Verify ports are listening

### End-to-End Testing (User Scenario)

1. Deploy monitoring stack
2. Configure monitors via UI
3. Stop a service (e.g., Immich)
4. Verify notification is received on phone
5. Start service, verify recovery notification
6. Verify dashboard shows correct status

---

## Implementation Phases

### Phase 1: Infrastructure (Terraform)

- Add monitoring LXC module
- Update variables and outputs
- Run terraform plan, review changes
- **STOP POINT**: Review Terraform plan before apply
- Run terraform apply
- Verify LXC is running and reachable

### Phase 2: Base Configuration (Ansible)

- Create monitoring_stack role skeleton
- Configure Docker installation
- Deploy Docker Compose stack
- Configure systemd service
- Verify containers are running

### Phase 3: Monitoring Setup (Ansible - Fully Automated)

- Create uptime_kuma role with API automation
- Implement container readiness wait logic
- Implement admin user creation (idempotent)
- Implement API authentication
- Implement SMTP notification configuration via API
- Implement monitor provisioning loop via API
- **STOP POINT**: Configure SMTP credentials in vault.yml before deployment
- Deploy and verify all monitors are created

### Phase 4: Notification Testing (Manual)

- Access dashboard and verify login works
- Verify all 4 monitors are present and showing UP status
- Test email delivery with manual service outage (stop/start Immich)
- Verify both DOWN and UP notifications arrive via email

### Phase 5: Validation & Documentation

- Run idempotency tests (changed=0 on second run)
- Perform end-to-end testing
- Write operational runbook with SMTP configuration guide
- Update main README
- Document process for adding new monitors

---

## Risk Assessment

### Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| mDNS resolution fails | Low | Medium | Fallback to IP addresses in monitor config |
| Docker resource usage too high | Low | Low | Monitoring LXC has 2GB RAM, plenty for lightweight containers |
| Notification delivery fails | Medium | High | Test SMTP configuration thoroughly, document multiple provider options (Gmail, Outlook, self-hosted) |
| False positive alerts | Medium | Medium | Configure retry counts and down thresholds conservatively |
| Monitoring stack down when services fail | Low | Medium | Acceptable for MVP; future enhancement: external monitoring |

### Operational Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Secrets committed to git | Low | High | Enforce .gitignore patterns, pre-commit hooks |
| Alert fatigue from too many notifications | Medium | Medium | Configure notification cooldown, adjust thresholds after testing |
| Manual monitor configuration is error-prone | Medium | Low | Document clearly, provide examples, consider API automation in future |

---

## Success Metrics

- **Deployment Time**: < 30 minutes from terraform apply to functional dashboard
- **Idempotency**: changed=0 on second playbook run (except check tasks)
- **Alert Latency**: < 3 minutes from service DOWN to phone notification
- **Resource Usage**: Monitoring LXC < 1GB RAM, < 10% CPU average
- **Reliability**: Monitoring stack survives LXC reboot, resumes within 5 minutes

---

## Future Improvements

- **Auto-discovery**: Parse Terraform outputs to automatically generate monitoring_targets list
- **Prometheus integration**: Export Uptime Kuma metrics to Prometheus for long-term storage and advanced analytics
- **Backup automation**: Scheduled backups of Uptime Kuma SQLite database to NFS
- **Self-monitoring**: External health check for monitoring stack itself (e.g., healthchecks.io cron job)
- **Multi-channel notifications**: Add Discord/Slack webhooks as secondary notification channels alongside email
- **Custom monitor types**: Add DNS, ping, TCP port checks beyond HTTP/HTTPS
- **Alert escalation**: Implement retry logic and escalation rules for repeated failures
