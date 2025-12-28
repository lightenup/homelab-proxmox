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

### 2. verify-snmpv3.sh - SNMPv3 Connectivity Verification

**Location:** `scripts/monitoring/verify-snmpv3.sh`

**Purpose:** Verify Synology SNMPv3 configuration before deploying monitoring stack.

**What It Tests:**
- Ping connectivity to NAS
- SNMPv3 basic authentication (sysName OID)
- Storage metrics accessibility (hrStorageTable)
- CPU and memory metrics
- Network interface metrics
- Synology-specific disk health OIDs

**Usage:**
```bash
# With default NAS IP (192.168.1.109)
./scripts/monitoring/verify-snmpv3.sh

# With custom NAS IP
./scripts/monitoring/verify-snmpv3.sh 192.168.1.105

# With environment variables (non-interactive)
export SNMP_USERNAME="monitoring"
export SNMP_AUTH_PROTOCOL="MD5"
export SNMP_AUTH_PASSWORD="YourAuthPassword"
export SNMP_PRIV_PROTOCOL="AES"
export SNMP_PRIV_PASSWORD="YourPrivPassword"
./scripts/monitoring/verify-snmpv3.sh
```

**Prerequisites:**
- `snmpwalk` tool installed (`brew install net-snmp` or `apt-get install snmp`)
- Synology SNMPv3 configured and enabled

**Output:**
```
✓ Basic connectivity: PASS
✓ Storage metrics: PASS
✓ CPU/Memory metrics: OK
✓ Network metrics: PASS
• Synology disk OIDs: AVAILABLE (or N/A)
```

**Troubleshooting:**
- If FAIL: Check username/password match DSM configuration
- If timeout: Verify SNMP service is enabled in DSM
- If N/A on disk OIDs: Normal for some NAS models

---

### 3. smoke-test.sh - Service Health Validation

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

### nfs_mount Role

**Location:** `ansible/roles/nfs_mount/`

**Purpose:** Automate NFS client setup and mount configuration.

**What It Automates:**
- Install `nfs-common` package
- Create mount point directory
- Verify NFS export is available (`showmount -e`)
- Configure `/etc/fstab` entry
- Mount NFS share
- Validate mount is active
- Test write permissions
- Create backup subdirectory

**Usage:**
```yaml
# In playbook or role
- name: Configure NFS backup mount
  ansible.builtin.include_role:
    name: nfs_mount
  when: monitoring_nfs_enabled | default(true)
```

**Configuration (group_vars/monitoring/vars.yml):**
```yaml
monitoring_nfs_enabled: true
nfs_server: "192.168.1.109"
nfs_export_path: "/volume1/backups"
nfs_mount_point: "/mnt/nas/backups"
nfs_mount_options: "defaults,_netdev,rw,hard,intr,timeo=600,retrans=2"
backup_subdir: "monitoring"
```

**Idempotency:**
- Re-running is safe - only applies changes if needed
- Uses `ansible.posix.mount` module for /etc/fstab management

**Verification:**
- Tests mount with `mountpoint -q`
- Tests write with temporary file creation
- Fails if export doesn't exist or mount fails

---

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

**Verification:** Use `verify-snmpv3.sh` to confirm configuration is correct

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
   - Run `verify-snmpv3.sh` separately
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

### verify-snmpv3.sh Fails

**Common Issues:**

1. **snmpwalk not found**
   - Install: `brew install net-snmp` (macOS)
   - Install: `apt-get install snmp` (Linux)

2. **Authentication failure**
   - Verify username in DSM matches script
   - Verify auth protocol (MD5 vs SHA)
   - Verify passwords match exactly

3. **Timeout errors**
   - Check SNMP service is enabled in DSM
   - Verify network connectivity
   - Check firewall rules

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
