# Monitoring Stack Quickstart Guide

**Feature**: 017-synology-metrics
**Purpose**: End-to-end deployment guide from prerequisites to verification
**Audience**: Homelab operators deploying Synology monitoring for the first time

## TL;DR - Fully Automated Deployment 🚀

**New!** Use the automated init script for zero-manual-step deployment:

```bash
cd /path/to/homelab-proxmox

# One command to rule them all
./scripts/monitoring/init-monitoring.sh
```

**What it automates:**
- ✅ Prerequisites validation (Terraform, Ansible, SSH connectivity)
- ✅ SNMPv3 connectivity verification
- ✅ Interactive secrets collection (vault passwords, SMTP config)
- ✅ Ansible vault creation and encryption
- ✅ Terraform LXC provisioning
- ✅ Ansible inventory update
- ✅ Full stack deployment (Prometheus, Grafana, Alertmanager, SNMP Exporter)
- ✅ NFS backup mount configuration
- ✅ Smoke test verification

**Time:** ~15-20 minutes (mostly waiting for Docker image pulls)

**Still manual:** Synology SNMPv3 configuration (DSM UI - see Step 1 below)

---

## Manual Deployment (Step-by-Step)

For operators who prefer manual control or need to troubleshoot individual steps:

## Overview

This guide walks you through deploying a complete monitoring stack (Prometheus, Grafana, SNMP Exporter, Alertmanager) to monitor your Synology NAS. The entire process takes approximately 20-30 minutes.

**What You'll Get:**
- Real-time Synology NAS metrics (storage, CPU, RAM, network, disk health)
- Grafana dashboard at http://monitoring.local:3000
- Email alerts for critical conditions (volume >85%, NAS down, disk issues)
- Daily automated backups to NAS
- Fully automated deployment (zero manual UI clicks)

## Prerequisites

### Required

- [ ] Proxmox VE 8.x host (192.168.1.112)
- [ ] Synology NAS with DSM 7.x (192.168.1.109)
- [ ] Ansible control machine (laptop/workstation with Ansible 2.14+)
- [ ] Git repository cloned: `homelab-proxmox`
- [ ] SSH access to Proxmox host
- [ ] Administrator access to Synology DSM
- [ ] Email account for alerts (Gmail, Office 365, or SMTP server)
- [ ] Ansible vault password (for encrypting secrets)

### Optional

- [ ] NFS share on Synology for backups (e.g., `/volume1/backups`)
- [ ] mDNS/Avahi configured for `monitoring.local` hostname

## Step 1: Configure Synology SNMPv3

**Time**: ~5 minutes
**Documentation**: [Synology SNMP Setup Guide](synology-snmp-setup.md)

1. Log into Synology DSM as administrator
2. Navigate to: **Control Panel** → **Terminal & SNMP** → **SNMP**
3. Enable SNMP service
4. Configure SNMPv3 user:
   - **Username**: `monitoring`
   - **Auth Protocol**: SHA
   - **Auth Password**: `YourStrongAuthPassword` (min 8 characters)
   - **Priv Protocol**: AES
   - **Priv Password**: `YourStrongPrivPassword` (min 8 characters)
5. (Optional) Restrict SNMP access to monitoring LXC IP: `192.168.1.214`

**Verification:**

```bash
# Manual test:
snmpwalk -v3 -l authPriv -u monitoring -a MD5 -A "YourAuthPassword" -x AES -X "YourPrivPassword" 192.168.1.109 1.3.6.1.2.1.1.5

# Expected: Returns NAS hostname
```

Note: The full monitoring init script performs SNMP connectivity checks as part of its preflight.

## Step 2: Configure Ansible Vault Secrets

**Time**: ~5 minutes

**Automated Option:**
```bash
# The init script handles this automatically
./scripts/monitoring/init-monitoring.sh
# Skip to verification step
```

**Manual Option:**

### Create Ansible Vault File

```bash
cd /path/to/homelab-proxmox

# Edit the vault template
vim ansible/group_vars/monitoring/vault.yml

# Update the following variables:
# - grafana_admin_password: Strong password for Grafana UI
# - smtp_server: Your SMTP server (e.g., smtp.gmail.com)
# - smtp_port: Usually 587 for TLS
# - smtp_from_address: Sender email address
# - smtp_username: SMTP authentication username
# - smtp_password: SMTP authentication password (use App Password for Gmail)
# - alert_email_recipient: Where to send alert emails
# - snmp_username: "monitoring" (must match Synology config)
# - snmp_auth_password: Must match Synology SNMPv3 auth password
# - snmp_priv_password: Must match Synology SNMPv3 priv password
```

### Encrypt Vault File

```bash
# Encrypt the vault file
ansible-vault encrypt ansible/group_vars/monitoring/vault.yml

# Enter vault password when prompted (save this password securely!)

# Verify encryption succeeded
cat ansible/group_vars/monitoring/vault.yml
# Should show "$ANSIBLE_VAULT;1.1;AES256" header
```

**Gmail Users**: Generate an App Password at https://myaccount.google.com/apppasswords

## Step 3: Provision Monitoring LXC with Terraform

**Time**: ~3 minutes

```bash
cd terraform

# Review planned changes
terraform plan -var-file=environments/prod.tfvars

# Expected output:
# - module.monitoring_lxc will be created
# - 2 vCPU, 4096 MB RAM, 32 GB disk
# - IP: 192.168.1.214

# Apply changes
terraform apply -var-file=environments/prod.tfvars

# Type 'yes' when prompted

# Wait for LXC creation (~2 minutes)
```

**Verification:**

```bash
# Check LXC is running
ssh root@192.168.1.112 'pct list | grep monitoring'

# Expected: 1xx monitoring running

# SSH to LXC should work
ssh root@192.168.1.214
# Should connect successfully
```

## Step 4: Update Ansible Inventory

**Time**: ~2 minutes

```bash
cd ../ansible

# Check if monitoring LXC is in inventory
grep -A5 "\[monitoring\]" inventories/generated/hosts.yml

# If missing, add manually:
vim inventories/generated/hosts.yml

# Add:
# [monitoring]
# monitoring ansible_host=192.168.1.214 ansible_user=root

# Or regenerate inventory from Terraform outputs:
cd /path/to/homelab-proxmox
task inventory:update
```

## Step 5: Deploy Monitoring Stack with Ansible

**Time**: ~10 minutes (includes Docker installation, image pulls, config deployment)

```bash
cd ansible

# Verify connectivity
ansible monitoring -m ping

# Expected: monitoring | SUCCESS => {"changed": false, "ping": "pong"}

# Deploy monitoring stack
ansible-playbook playbooks/monitoring.yml --ask-vault-pass

# Enter your Ansible vault password when prompted

# Watch deployment progress (takes ~8-10 minutes)
# Tasks performed:
# 1. Configure LXC base (hostname, timezone, packages)
# 2. Configure mDNS (monitoring.local hostname)
# 3. Install Docker via geerlingguy.docker role
# 4. Create monitoring directories
# 5. Deploy docker-compose.yml (Prometheus, Grafana, SNMP Exporter, Alertmanager)
# 6. Deploy Prometheus scrape config and alert rules
# 7. Deploy SNMP Exporter SNMPv3 config
# 8. Deploy Alertmanager SMTP config
# 9. Provision Grafana datasource and dashboards
# 10. Configure backup cron job
# 11. Start all services via docker-compose
# 12. Verify health endpoints
```

**Expected Output:**

```
PLAY RECAP *********************************************************************
monitoring : ok=45   changed=32   unreachable=0    failed=0    skipped=3
```

## Step 6: Verify Deployment

**Time**: ~5 minutes

### 6.1: Check Service Health

```bash
# SSH to monitoring LXC
ssh root@192.168.1.214

# Check Docker containers
docker ps

# Expected: 4 containers running
# - prometheus
# - grafana
# - snmp-exporter
# - alertmanager

# Check container logs (should show no errors)
docker logs prometheus --tail 20
docker logs grafana --tail 20
docker logs snmp-exporter --tail 20
docker logs alertmanager --tail 20
```

### 6.2: Run Smoke Test

```bash
# From Ansible control machine
cd /path/to/homelab-proxmox
./scripts/monitoring/smoke-test.sh

# Expected: All tests pass (green checkmarks)
```

### 6.3: Verify Prometheus Targets

Open in browser: http://192.168.1.214:9090/targets

**Expected:**
- `prometheus` (localhost:9090): UP
- `synology-snmp` (192.168.1.109): UP

If `synology-snmp` is DOWN:
- Verify Synology SNMPv3 is enabled
- Verify SNMPv3 credentials match vault.yml
- Check SNMP Exporter logs: `docker logs snmp-exporter`

### 6.4: Verify Grafana Dashboard

Open in browser: http://192.168.1.214:3000

**Login:**
- Username: `admin`
- Password: `[From vault.yml: grafana_admin_password]`

**Navigate to:**
1. Click **Dashboards** (left sidebar)
2. Open **Synology NAS Health** dashboard

**Expected:**
- 4 panels showing live data:
  - Storage Capacity gauge (% usage per volume)
  - Disk Health Status table (disk names, temperatures)
  - CPU & Memory Usage graph (line chart over time)
  - Network Throughput graph (bytes in/out)

If no data:
- Check Prometheus datasource: **Configuration** → **Data Sources** → **Prometheus**
- Verify URL is `http://prometheus:9090`
- Test connection (should return green checkmark)

### 6.5: Verify Alert Rules

Open in browser: http://192.168.1.214:9090/alerts

**Expected:**
- `SynologyVolumeHighUsage` (inactive)
- `SynologyNASDown` (inactive)
- `SynologyDiskSMARTWarning` (inactive or N/A if SMART OIDs unavailable)

### 6.6: Verify Alertmanager

Open in browser: http://192.168.1.214:9093

**Expected:**
- Status page loads
- **Config** tab shows SMTP configuration (smarthost, from address)
**Automated:** NFS mount is now configured automatically by Ansible if `monitoring_nfs_enabled: true` in [vars.yml](../../ansible/group_vars/monitoring/vars.yml)

**Manual Configuration (if needed):**


### 6.7: Test Alert Delivery (Optional but Recommended)

Follow [Alert Testing Procedure](runbook-alert-testing.md) to trigger a test alert and verify email delivery.

## Step 7: Backups

The monitoring host is rebuilt from configuration and is not backed up (see
[architecture](../../architecture.md)). Prometheus keeps 15 days, and dashboards and rules are provisioned.

## Troubleshooting

### Common Issues

#### Issue: Synology SNMP target shows DOWN

**Cause**: SNMPv3 credentials mismatch or SNMP service disabled

**Fix:**
1. Verify Synology SNMP is enabled: DSM → Terminal & SNMP → SNMP
2. Test SNMPv3 manually from monitoring LXC:
   ```bash
   ssh root@192.168.1.214
   apt-get install snmp
   snmpwalk -v3 -l authPriv -u monitoring -a MD5 -A "YourAuthPassword" -x AES -X "YourPrivPassword" 192.168.1.109 1.3.6.1.2.1.1.5
   ```
3. Check SNMP Exporter config: `docker exec snmp-exporter cat /etc/snmp_exporter/snmp.yml`

#### Issue: Grafana shows "No data"

**Cause**: Prometheus datasource not configured or unreachable

**Fix:**
1. Grafana → Configuration → Data Sources → Prometheus
2. Verify URL is `http://prometheus:9090` (internal Docker network)
3. Click **Save & Test** (should show green checkmark)
4. Check Prometheus is scraping: http://192.168.1.214:9090/targets

#### Issue: Alert emails not received

**Cause**: SMTP config incorrect or Gmail blocking login

**Fix:**
1. Check Alertmanager logs: `docker logs alertmanager --tail 50`
2. For Gmail: Generate App Password (not account password)
3. Test SMTP manually:
   ```bash
   ssh root@192.168.1.214
   apt-get install swaks
   swaks --to recipient@example.com --from homelab@example.com --server smtp.gmail.com:587 --auth-user your-email@gmail.com --auth-password YOUR_APP_PASSWORD --tls
   ```

#### Issue: mDNS `monitoring.local` not resolving

**Cause**: Avahi not configured or firewall blocking

**Fix:**
1. VeReview automated backup schedule (daily 3 AM, 30-day retention)
5. → Schedule restore drill (quarterly recommended)
6. → Review upgrade procedure for version updates

## Automation Scripts Reference

**New automation tools in this feature:**

- **`scripts/monitoring/init-monitoring.sh`**: Full automated deployment
  - Validates prerequisites
  - Collects and encrypts secrets
  - Provisions infrastructure
  - Deploys monitoring stack
  - Configures NFS backups
  - Runs verification tests

- **`scripts/monitoring/smoke-test.sh`**: Service health validation
  - Tests all 4 services (Prometheus, Grafana, Alertmanager, SNMP Exporter)
  - Validates Synology target scraping
  - Color-coded pass/fail output

  - Idempotent and fully automated
## Next Steps

1. ✅ **Monitoring deployed and verified**
2. → Bookmark Grafana dashboard: http://monitoring.local:3000
3. → Trigger test alert to verify email delivery
4. → Set up NFS backup mount (if not done)
5. → Schedule restore drill (quarterly recommended)
6. → Review upgrade procedure for version updates

## Quick Reference

**Service URLs:**
- Grafana: http://192.168.1.214:3000 (admin / vault password)
- Prometheus: http://192.168.1.214:9090
- Alertmanager: http://192.168.1.214:9093
- SNMP Exporter: http://192.168.1.214:9116/metrics

**SSH Access:**
- Monitoring LXC: `ssh root@192.168.1.214`
- Proxmox host: `ssh root@192.168.1.112`

**Configuration Files:**
- Terraform: `terraform/main.tf`, `terraform/environments/prod.tfvars`
- Ansible playbook: `ansible/playbooks/monitoring.yml`
- Ansible vault: `ansible/group_vars/monitoring/vault.yml`
- Docker compose: `/opt/monitoring/docker-compose.yml` (on LXC)

**Useful Commands:**
```bash
# Re-run Ansible (after config changes)
ansible-playbook playbooks/monitoring.yml --ask-vault-pass

# Restart monitoring stack
ssh root@192.168.1.214 'cd /opt/monitoring && docker-compose restart'

# View logs
ssh root@192.168.1.214 'cd /opt/monitoring && docker-compose logs -f'

# Run smoke test
./scripts/monitoring/smoke-test.sh
```

## See Also

- [Synology SNMP Setup Guide](synology-snmp-setup.md)
- [Alert Testing Procedure](runbook-alert-testing.md)
- [Restore Procedure](runbook-restore.md)
- [Upgrade Procedure](runbook-upgrades.md)
- [Feature Specification](../../../specs/017-synology-metrics/spec.md)
- [Implementation Plan](../../../specs/017-synology-metrics/plan.md)
