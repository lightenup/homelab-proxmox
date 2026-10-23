# Automation Scripts - Feature 017

## Overview

Feature 017 includes comprehensive automation to minimize manual steps and maximize IaC principles. This document describes the automation tools and their usage.

## Scripts

### 1. init-monitoring.sh - Full Stack Deployment

**Location:** `scripts/monitoring/init-monitoring.sh`

**Purpose:** One-command deployment of the entire monitoring stack from scratch.

**What It Automates:**
- Prerequisites validation (Terraform, Ansible, SSH tools)
- Proxmox SSH connectivity check
- Interactive secrets collection (Grafana password, SMTP config, SNMPv3 credentials)
- SNMPv3 connectivity verification
- Ansible vault file creation and encryption
- Terraform LXC provisioning (with approval prompt)
- Ansible inventory update
- Full monitoring stack deployment via Ansible
- Smoke test verification

**Usage:**
```bash
cd /path/to/homelab-proxmox
./scripts/monitoring/init-monitoring.sh
```

**Prerequisites:**
- Synology SNMPv3 configured (still manual - DSM UI required)
- Terraform installed
- Ansible installed (with ansible-vault)
- SSH access to Proxmox host
- SMTP credentials ready

**Time:** ~15-20 minutes (mostly Docker image pulls)

**Interactive Prompts:**
- Grafana admin password
- SMTP server, port, credentials
- Alert recipient email
- SNMPv3 credentials (must match Synology)
- Ansible vault encryption password
- Terraform apply approval

**Output:**
- Encrypted `ansible/group_vars/monitoring/vault.yml`
- Deployed monitoring LXC at 192.168.1.214
- Running Docker stack (Prometheus, Grafana, Alertmanager, SNMP Exporter)
- NFS backup mount configured
- Service URLs and login credentials

---

### 2. smoke-test.sh - Service Health Validation

**Location:** `scripts/monitoring/smoke-test.sh`

**Purpose:** Validate all monitoring services are healthy and scraping data.

**What It Tests:**
- Prometheus health endpoint (/-/healthy)
- Prometheus targets status (synology-snmp should be UP)
- Grafana health endpoint (/api/health)
- SNMP Exporter metrics endpoint (/metrics)
- Alertmanager health endpoint (/-/healthy)

**Usage:**
```bash
./scripts/monitoring/smoke-test.sh

# Or from Ansible control machine
ssh root@192.168.1.214 '/opt/monitoring/smoke-test.sh'
```

**Output:**
```
[✓] Prometheus is healthy
[✓] Synology SNMP target is UP
[✓] Grafana is healthy
[✓] SNMP Exporter is responding
[✓] Alertmanager is healthy

=== SUMMARY ===
5/5 tests passed
```

**Exit Codes:**
- 0: All tests passed
- 1: One or more tests failed

---

## Ansible Roles

## Automation Benefits

**Before (Manual Steps):**
1. ❌ Manually edit vault.yml (copy passwords, check syntax)
2. ❌ Run ansible-vault encrypt (remember password)
3. ❌ Manually edit inventory file
4. ❌ SSH to LXC and manually configure NFS
5. ❌ Manually edit /etc/fstab
6. ❌ Manually test SNMPv3 (remember complex snmpwalk syntax)
7. ❌ Manually verify each service endpoint

**After (Automated):**
1. ✅ Run `./scripts/monitoring/init-monitoring.sh`
2. ✅ Answer interactive prompts
3. ✅ Approve Terraform plan
4. ✅ Wait ~15 minutes
5. ✅ Done!

**Time Savings:** ~40 minutes → ~20 minutes (50% reduction)
**Error Reduction:** Eliminates manual typos, syntax errors, missed steps
**Reproducibility:** Same process every time, documented in code

---

## Still Manual (DSM UI Required)

### Synology SNMPv3 Configuration

**Why Still Manual:**
- Synology DSM API requires authentication and doesn't expose SNMPv3 user management
- SSH automation would require storing DSM admin credentials (security risk)
- One-time configuration per NAS (doesn't change)

**Process:** (~5 minutes)
1. DSM → Control Panel → Terminal & SNMP → SNMP
2. Enable SNMP service
3. Create SNMPv3 user with MD5/AES

**Documentation:** [Synology SNMP Setup Guide](../../docs/operations/monitoring/synology-snmp-setup.md)

**Verification:** Use the SNMP verification steps in the quickstart, or run the full init script which includes SNMP connectivity checks.

---

## Future Automation Ideas

### Potential Enhancements:

1. **Terraform Module for Synology SNMP**
   - Use Synology DSM API (if available)
   - Requires research into API capabilities
   - Risk: Storing DSM admin credentials

2. **GitHub Actions / CI Pipeline**
   - Automated validation on PR (syntax checks, smoke tests)
   - Automated deployment to non-prod environment
   - Scheduled smoke tests (daily health checks)

3. **Ansible Callback Plugin**
   - Real-time deployment status in Slack/email
   - Progress bars for long-running tasks
   - Failure notifications with context

4. **Self-Service Web UI**
   - Web form for secret collection
   - One-click deployment button
   - Real-time deployment logs
   - Service health dashboard

---

## Troubleshooting Automation

### init-monitoring.sh Fails

**Common Issues:**

1. **Prerequisites check fails**
   - Install missing tools (Terraform, Ansible)
   - Configure SSH key for Proxmox

2. **SNMPv3 verification fails**
   - Run the manual `snmpwalk` verification from the monitoring quickstart
   - Check DSM SNMP configuration
   - Verify credentials match

3. **Terraform apply fails**
   - Check Proxmox API connectivity
   - Verify prod.tfvars values
   - Run `terraform plan` manually

4. **Ansible deployment fails**
   - Verify vault password is correct
   - Check inventory has monitoring group
   - Run playbook with `-vvv` for debug output

### NFS Mount Fails

**Common Issues:**

1. **Export not found**
   - Verify NFS service enabled in DSM
   - Check export path in DSM NFS rules
   - Run `showmount -e 192.168.1.109` manually

2. **Permission denied**
   - Check NFS rule allows monitoring LXC IP
   - Verify squash settings (map to admin)
   - Check shared folder permissions in DSM

3. **Mount point busy**
   - Unmount existing: `umount /mnt/nas/backups`
   - Kill processes using mount: `fuser -km /mnt/nas/backups`
   - Re-run Ansible playbook

---

## See Also

- [Quickstart Guide](../../docs/operations/monitoring/quickstart.md) - Full deployment guide
- [Synology SNMP Setup](../../docs/operations/monitoring/synology-snmp-setup.md) - Manual SNMPv3 configuration
- [Runbook: Restore](../../docs/operations/monitoring/runbook-restore.md) - Disaster recovery
- [Feature Spec](../../../specs/017-synology-metrics/spec.md) - Requirements and design
