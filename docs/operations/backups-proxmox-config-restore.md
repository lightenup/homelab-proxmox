# Proxmox Configuration Backup - Restore Runbook

**Feature**: 013-proxmox-config-backup
**Purpose**: Step-by-step procedures for recovering from Proxmox host failure
**Audience**: Operators performing disaster recovery

---

## Overview

This runbook guides you through restoring a Proxmox VE host from encrypted configuration backups stored on NAS. The restore process handles:

1. **Proxmox VE Configuration** - LXC container definitions, storage configuration
2. **System Configuration** - Network interfaces, fstab mounts
3. **IaC Artifacts** (optional) - Terraform state, Ansible inventory

**Prerequisites**:
- Fresh Proxmox VE installation (same version or compatible)
- Access to NAS backup location (`/volume1/homelab_backups/proxmox/`)
- Age encryption private key (from Bitwarden or paper backup)
- Network connectivity to NAS (192.168.1.109)

**Timeline**: Complete restore in under 2 hours

---

## Before You Begin

### Rebuild Guardrails (Orchestrator)

If you are using the rebuild orchestrator (task rebuild:plan / task rebuild:apply):

- Lab is the default environment.
- Prod runs require an explicit confirmation string.
- Apply runs require an explicit confirmation string even in lab.
- Network and fstab restores require opt-in flags (`--apply-network`, `--apply-fstab`).

See [rebuild-orchestrator.md](rebuild-orchestrator.md) for usage details.

### 1. Verify Backup Availability

```bash
# Mount NAS backup location
mount -t nfs 192.168.1.109:/volume1/homelab_backups/proxmox /mnt/nas-backup

# List available backups (sorted by date)
ls -lht /mnt/nas-backup/proxmox-backup-*.tar.zst.age | head -10
```

**Select Latest Backup**:
```bash
BACKUP_FILE=$(ls -t /mnt/nas-backup/proxmox-backup-*.tar.zst.age | head -1)
echo "Using backup: $BACKUP_FILE"
```

### 2. Retrieve Encryption Key

**Option A: From Bitwarden** (recommended):
- Log into Bitwarden
- Search for "Proxmox Backup Age Key"
- Copy private key (starts with `AGE-SECRET-KEY-`)

**Option B: From Paper Backup**:
- Retrieve physical key from secure storage
- Verify fingerprint matches recorded value

**Store Key Temporarily**:
```bash
# Create secure key file (600 permissions)
cat > /root/.age/proxmox-backup.key << 'EOF'
AGE-SECRET-KEY-1... (paste private key here)
EOF
chmod 600 /root/.age/proxmox-backup.key
```

---

## Restore Procedure

### Step 1: Decrypt and Extract Backup

```bash
# Set working directory
cd /root
mkdir -p restore-$(date +%Y%m%d)
cd restore-$(date +%Y%m%d)

# Decrypt backup
age --decrypt -i /root/.age/proxmox-backup.key "$BACKUP_FILE" > backup.tar.zst

# Verify decryption succeeded
if [[ ! -s backup.tar.zst ]]; then
  echo "ERROR: Decryption failed - check key and backup file"
  exit 1
fi
echo "✓ Decryption successful"

# Extract archive
tar --use-compress-program=zstd -xvf backup.tar.zst

# Verify extraction
ls -lh
echo "✓ Extraction complete"
```

**Expected Directory Structure**:
```
restore-20251223/
├── manifest.txt           # File checksums
├── proxmox/              # Proxmox configs
│   ├── 100.conf
│   ├── 101.conf
│   ├── storage.cfg
│   └── ...
├── network/              # Network configs
│   └── interfaces
├── system/               # System configs
│   └── fstab
├── iac/                  # IaC artifacts (if enabled)
│   ├── terraform/
│   └── ansible/
└── docs/                 # Documentation snapshots
```

### Step 2: Verify Backup Integrity

```bash
# Check manifest exists
if [[ ! -f manifest.txt ]]; then
  echo "WARNING: No manifest found - checksums unavailable"
else
  echo "✓ Manifest found - verifying checksums..."

  # Verify checksums
  cd $(dirname manifest.txt)
  sha256sum -c manifest.txt

  if [[ $? -eq 0 ]]; then
    echo "✓ All checksums verified"
  else
    echo "ERROR: Checksum mismatch detected"
    echo "Review failed files before proceeding"
  fi
fi
```

### Step 3: Restore LXC Container Configurations

**Prerequisites**:
- Proxmox VE cluster initialized
- Storage backend configured (use storage.cfg as reference)

```bash
# Review container configs
ls -lh proxmox/*.conf

# Restore LXC configs
cp proxmox/*.conf /etc/pve/lxc/

# Verify copy succeeded
ls -l /etc/pve/lxc/
```

**Validation**:
```bash
# List containers in Proxmox UI or CLI
pct list

# Expected: Containers visible but in "stopped" state
# IDs should match restored config files (100, 101, etc.)
```

**Post-Restore Actions**:
1. Verify storage paths match (check `/etc/pve/lxc/*.conf` mount points)
2. Update IP addresses if network changed
3. Start containers: `pct start <CTID>`
4. Verify services running: `pct exec <CTID> -- systemctl status`

### Step 4: Restore Storage Configuration

```bash
# Review storage config
cat proxmox/storage.cfg

# Backup current config (if it exists)
cp /etc/pve/storage.cfg /etc/pve/storage.cfg.bak

# Restore storage config
cp proxmox/storage.cfg /etc/pve/storage.cfg

# Reload Proxmox storage
systemctl restart pvedaemon pveproxy
```

**Validation**:
```bash
# Verify storage backends visible
pvesm status

# Expected: NFS shares, local storage visible
# Check mount points exist and are accessible
```

**Common Issues**:
- NFS shares not mounted → Check network connectivity, verify NAS accessible
- Permission errors → Verify Proxmox host can access NFS exports
- Storage paths changed → Update storage.cfg paths manually

### Step 5: Restore Network Configuration

```bash
# Review network config
cat network/interfaces

# Backup current config
cp /etc/network/interfaces /etc/network/interfaces.bak

# Restore network config
cp network/interfaces /etc/network/interfaces

# Review changes before applying
diff /etc/network/interfaces.bak /etc/network/interfaces
```

**⚠️ CRITICAL: Test before reboot**

```bash
# Test configuration syntax
ifup --no-act -a

# If test passes, apply changes
systemctl restart networking

# Verify connectivity
ping -c 3 192.168.1.1
```

**Rollback if needed**:
```bash
cp /etc/network/interfaces.bak /etc/network/interfaces
systemctl restart networking
```

### Step 6: Restore System Configuration

```bash
# Review fstab
cat system/fstab

# Backup current fstab
cp /etc/fstab /etc/fstab.bak

# Restore fstab
cp system/fstab /etc/fstab

# Verify syntax
mount -a --fake

# Mount all filesystems
mount -a

# Verify mounts
df -h
mount | grep nfs
```

**Common Mounts**:
- NAS backup location: `/mnt/nas-backup`
- NAS storage for LXC: `/mnt/nas-storage`

### Step 7: Restore IaC State Files

**⚠️ IMPORTANT**: As of spec 033-idempotent-rebuild, Terraform state and Ansible inventory are stored on NAS (`/mnt/nas/homelab_ci/infra_state/`) instead of the PVE filesystem.

#### Prerequisites

- NAS mounted on restored PVE host: `/mnt/nas/homelab_ci`
- Backup archive extracted: `/root/restore-YYYYMMDD/`
- Verify state directories exist: `ls /mnt/nas/homelab_ci/infra_state/{lab,static}/`

#### Restore Terraform State

**Lab Environment**:
```bash
# Verify source data in backup
ls /root/restore-*/iac-artifacts/nas-state/lab/*/terraform.tfstate

# Sync all lab service state files
rsync -av --checksum \
  /root/restore-*/iac-artifacts/nas-state/lab/ \
  /mnt/nas/homelab_ci/infra_state/lab/

# Verify restoration
ls -lh /mnt/nas/homelab_ci/infra_state/lab/*/terraform.tfstate
```

**Production Environment**:
```bash
# Verify source data in backup
ls /root/restore-*/iac-artifacts/nas-state/static/*/terraform.tfstate

# Sync static state separately
rsync -av --checksum \
  /root/restore-*/iac-artifacts/nas-state/static/ \
  /mnt/nas/homelab_ci/infra_state/prod/

# Verify restoration
ls -lh /mnt/nas/homelab_ci/infra_state/prod/*/terraform.tfstate
```

#### Restore Ansible Inventory

```bash
# Lab inventory
mkdir -p /mnt/nas/homelab_ci/infra_state/lab/ansible/inventories/generated
cp -v /root/restore-*/iac-artifacts/nas-state/lab/ansible/inventories/generated/hosts.yml \
  /mnt/nas/homelab_ci/infra_state/lab/ansible/inventories/generated/hosts.yml

# Static inventory
mkdir -p /mnt/nas/homelab_ci/infra_state/prod/ansible/inventories/generated
cp -v /root/restore-*/iac-artifacts/nas-state/static/ansible/inventories/generated/hosts.yml \
  /mnt/nas/homelab_ci/infra_state/prod/ansible/inventories/generated/hosts.yml
```

#### Validation

Verify state files are accessible and valid:
```bash
# Check file ownership and permissions
find /mnt/nas/homelab_ci/infra_state/ -type f -ls

# Validate Terraform state format (example for immich)
for env in lab static; do
  for service_dir in /mnt/nas/homelab_ci/infra_state/$env/*/; do
    [[ -f "${service_dir}terraform.tfstate" ]] || continue
    service=$(basename "$service_dir")
    if terraform show -json "${service_dir}terraform.tfstate" > /dev/null 2>&1; then
      echo "✓ $env/$service: OK"
    else
      echo "✗ $env/$service: INVALID STATE"
    fi
  done
done
```

**Expected Output**:
```
✓ lab/immich: OK
✓ lab/monitoring: OK
✓ lab/jellyfin: OK
✓ static/immich: OK
```

#### Legacy State (Deprecated Path)

If your backup includes legacy state at `iac-artifacts/legacy/terraform/terraform.tfstate`:

```bash
# This is the old location - should be migrated to NAS paths above
# Only restore legacy state if NAS state is unavailable

# Restore to old location (deprecated)
mkdir -p /var/lib/homelab-proxmox/terraform
cp /root/restore-*/iac-artifacts/legacy/terraform/terraform.tfstate \
  /var/lib/homelab-proxmox/terraform/

# Then migrate to NAS:
# DRY_RUN=false ENVIRONMENT=lab bash scripts/lab/migrate-state-to-nas.sh
```

```bash
# Navigate to inventory directory
cd /root/homelab-proxmox/ansible/inventories/generated

# Backup current inventory
cp hosts.yml hosts.yml.bak 2>/dev/null || true

# Restore inventory
cp /root/restore-*/iac/ansible/inventories/generated/hosts.yml .

# Verify syntax
ansible-inventory -i hosts.yml --list > /dev/null

# Validate against reality
ansible -i hosts.yml all -m ping

# Expected: All hosts respond (or fail with known reason)
```

**Validation: Zero Drift Check**

```bash
# Terraform validation
cd /root/homelab-proxmox/terraform
terraform plan -detailed-exitcode

# Exit code 0 = no changes (✓ success)
# Exit code 2 = drift detected (review changes)

# Ansible validation
cd /root/homelab-proxmox/ansible
ansible-playbook -i inventories/generated/hosts.yml playbooks/site.yml --check --diff

# Expected: "changed=0" across all plays
# Any changes indicate drift from backup state
```

---

## Verification

### Post-Restore Checklist

```bash
# 1. LXC containers visible
pct list

# 2. Storage backends accessible
pvesm status

# 3. Network connectivity
ping -c 3 192.168.1.1
ip addr show

# 4. NFS mounts active
mount | grep nfs
df -h /mnt/nas-backup

# 5. Proxmox services running
systemctl status pvedaemon pveproxy pve-cluster

# 6. Web UI accessible
curl -k https://localhost:8006

# 7. IaC state matches (if applicable)
cd /root/homelab-proxmox/terraform && terraform plan
cd /root/homelab-proxmox/ansible && ansible -i inventories/generated/hosts.yml all -m ping
```

### Start Services

```bash
# Start LXC containers in dependency order
pct start 100  # First container
sleep 10
pct start 101  # Dependent services
# etc...

# Verify services
pct exec 100 -- systemctl status
```

---

## Troubleshooting

### Decryption Fails

**Symptom**: `age: error: no identity matched any of the recipients`

**Solution**:
1. Verify you're using the correct private key
2. Check key fingerprint matches: `age-keygen -y /root/.age/proxmox-backup.key`
3. Try alternative key source (paper backup vs. Bitwarden)
4. Verify backup file not corrupted: `ls -lh $BACKUP_FILE`

### Container Won't Start

**Symptom**: `pct start <CTID>` fails

**Common Causes**:
1. **Storage not accessible**: Check `/etc/pve/lxc/<CTID>.conf` rootfs path
2. **Network mismatch**: Verify bridge `vmbr0` exists
3. **Resource conflict**: Check memory/CPU limits in config

**Debug**:
```bash
# Check container status
pct status <CTID>

# View container logs
journalctl -u pve-container@<CTID>

# Manual start with debug
pct start <CTID> --debug
```

### Network Configuration Broke Connectivity

**Symptom**: Lost SSH access after network restore

**Solution**:
1. **Physical/KVM access required**
2. Restore backup config:
   ```bash
   cp /etc/network/interfaces.bak /etc/network/interfaces
   systemctl restart networking
   ```
3. Review interfaces file for IP conflicts, bridge mismatches
4. Consider using DHCP temporarily for recovery

### Terraform Shows Drift

**Symptom**: `terraform plan` shows many changes

**Analysis**:
- **Expected**: Minor provider version differences
- **Unexpected**: Resource deletions, major configuration changes

**Resolution**:
```bash
# Review changes carefully
terraform plan -out=drift-review.tfplan
terraform show drift-review.tfplan

# If changes are cosmetic (formatting, provider updates):
terraform apply drift-review.tfplan

# If changes are destructive:
# DO NOT APPLY - investigate backup vs. current state mismatch
```

### Checksum Verification Fails

**Symptom**: `sha256sum -c manifest.txt` reports mismatches

**Analysis**:
- **Partial backup**: Backup may have failed mid-creation
- **Corrupted transfer**: NAS/network issues during backup
- **Tampering**: Integrity compromise (unlikely)

**Action**:
1. Try next-older backup
2. Review backup logs: `ssh root@192.168.1.112 journalctl -u proxmox-backup.service`
3. Proceed with caution - manually verify critical files

---

## Recovery Time Objectives

| Restore Phase | Time | Notes |
|---------------|------|-------|
| Decrypt & Extract | 5 min | Depends on backup size (~1-10 MB) |
| LXC Configs | 10 min | Copy + validation |
| Storage Config | 5 min | May require NFS remount |
| Network Config | 15 min | **CAUTION**: Can break connectivity |
| System Config | 10 min | fstab + mounts |
| IaC Artifacts | 30 min | Terraform/Ansible validation |
| Container Startup | 30 min | Depends on container count |
| **Total** | **~2 hours** | Including validation steps |

---

## Post-Recovery Actions

### 1. Re-enable Backup Automation

```bash
# Verify backup script exists
ls -l /usr/local/sbin/proxmox-config-backup

# If missing, redeploy via Ansible:
cd /root/homelab-proxmox/ansible
ansible-playbook -i inventories/prod/hosts.yml playbooks/backup_proxmox.yml \
  --vault-password-file ~/.ansible_vault_pass \
  -e PROXMOX_BACKUP_AGE_PUBLIC_KEY="age1..."

# Verify timer enabled
systemctl status proxmox-backup.timer

# Test manual backup
/usr/local/sbin/proxmox-config-backup
```

### 2. Update Documentation

- [ ] Note recovery date in ops log
- [ ] Document any deviations from runbook
- [ ] Update IP addresses if changed
- [ ] Record RTO (actual recovery time)

### 3. Quarterly Drill

**Schedule**: Every 3 months

**Drill Scope**:
1. Decrypt latest backup (no extraction)
2. Verify manifest checksums
3. Review restore runbook for accuracy
4. Update paper backup location documentation

---

## Key Rotation After Recovery

If you used the paper backup key (break-glass scenario):

```bash
# 1. Generate new keypair
age-keygen -o /root/.age/new-proxmox-backup.key

# 2. Extract public key
NEW_PUBLIC_KEY=$(age-keygen -y /root/.age/new-proxmox-backup.key)
echo "New public key: $NEW_PUBLIC_KEY"

# 3. Update Bitwarden with new private key
# Store in "Proxmox Backup Age Key" item

# 4. Update Ansible configuration
# The public key is deployed via environment variable (not in vars file)
# Ensure PROXMOX_BACKUP_AGE_PUBLIC_KEY is set when running playbook

# 5. Redeploy backup configuration
export PROXMOX_BACKUP_AGE_PUBLIC_KEY="$NEW_PUBLIC_KEY"
ansible-playbook -i inventories/prod/hosts.yml playbooks/backup_proxmox.yml \
  --vault-password-file ~/.ansible_vault_pass

# 6. Test new key with backup
/usr/local/sbin/proxmox-config-backup

# 7. Verify decryption with new key
age --decrypt -i /root/.age/new-proxmox-backup.key \
  /mnt/nas-backup/$(ls -t /mnt/nas-backup/*.age | head -1) | \
  tar --use-compress-program=zstd -t | head

# 8. Securely destroy old paper backup
# Generate new paper backup with new private key
```

---

## Emergency Contacts

| Issue | Contact | Notes |
|-------|---------|-------|
| NAS Access | Synology Admin | IP: 192.168.1.109 |
| Key Retrieval | Bitwarden Admin | Search: "Proxmox Backup Age Key" |
| Network Issues | Network Admin | Check router/switch config |

---

## Appendix: Quick Reference

### Essential Commands

```bash
# Mount NAS
mount -t nfs 192.168.1.109:/volume1/homelab_backups/proxmox /mnt/nas-backup

# Decrypt backup
age --decrypt -i /root/.age/proxmox-backup.key backup.tar.zst.age > backup.tar.zst

# Extract backup
tar --use-compress-program=zstd -xvf backup.tar.zst

# List containers
pct list

# Start container
pct start <CTID>

# Check storage
pvesm status

# Test Terraform drift
terraform plan -detailed-exitcode

# Test Ansible drift
ansible-playbook site.yml --check --diff
```

### File Locations

| Item | Path |
|------|------|
| Backup Archives | `/volume1/homelab_backups/proxmox/` (NAS) |
| Backup Script | `/usr/local/sbin/proxmox-config-backup` |
| Backup Config | `/etc/proxmox-backup.conf` |
| Age Private Key | `/root/.age/proxmox-backup.key` |
| LXC Configs | `/etc/pve/lxc/*.conf` |
| Storage Config | `/etc/pve/storage.cfg` |
| Network Config | `/etc/network/interfaces` |
| Mount Config | `/etc/fstab` |

---

**Last Updated**: December 23, 2025
**Document Owner**: Infrastructure Team
**Review Frequency**: Quarterly (with drill)
