# Proxmox Configuration Backup Operations

**Feature**: 013-proxmox-config-backup  
**Last Updated**: 2025-12-22

## Overview

Automated backup system for Proxmox host configuration and Infrastructure-as-Code artifacts. Backups are encrypted with age, stored on Synology NAS, and rotated automatically (30 daily + 12 monthly).

**Architecture**: Local bash script runtime - systemd timer runs `/usr/local/sbin/proxmox-config-backup` on PVE host. Ansible deploys script, configuration, and systemd units.

---

## Manual Prerequisites

⚠️ **CRITICAL**: Complete ALL steps below BEFORE running `./scripts/backup/run_proxmox_backup.sh`

These one-time setup tasks must be completed by operator before running automated backups.

**Required Dependencies** (must exist before deployment):
- ✅ Synology NAS accessible at 192.168.1.109
- ✅ NAS shared folder: `/volume1/homelab_backups` (created in Step 1)
- ✅ NFS export configured for PVE host 192.168.1.112 (Step 2)
- ✅ Age encryption keypair generated and in Bitwarden (Step 4)

---

### 0. Install age on Local Machine (One-Time)

**Purpose**: Install age encryption tool on your local machine for keypair generation

**Steps**:

```bash
# macOS (Homebrew)
brew install age

# Debian/Ubuntu
apt install age

# Other platforms: Download from https://github.com/FiloSottile/age/releases
```

**Verification**:
```bash
age --version
# Should output: v1.2.0 or higher
```

**Note**: age is only needed on your local machine for initial keypair generation. The PVE host will have age installed automatically by Ansible.

---

### 1. NAS Share Creation

**Purpose**: Create dedicated NFS share on Synology NAS for backup storage

**Steps**:

1. Log into Synology DSM at `http://192.168.1.109:5000`

2. Navigate to **Control Panel → Shared Folder**

3. Create new shared folder:
   - Name: `homelab_backups`
   - Location: `volume1`
   - Description: "Automated backups for homelab infrastructure"
   - Encryption: Not required (files encrypted before transfer)
   - Recycle Bin: Disabled (managed by backup rotation)

4. Set permissions:
   - User: `root` (or dedicated backup user)
   - Permission: Read/Write

5. Create proxmox subdirectory (via SSH to NAS or File Station):
   ```bash
   # Option 1: Via NAS SSH
   ssh admin@192.168.1.109
   sudo mkdir -p /volume1/homelab_backups/proxmox
   sudo chown root:root /volume1/homelab_backups/proxmox
   sudo chmod 755 /volume1/homelab_backups/proxmox
   
   # Option 2: Via DSM File Station
   # Navigate to homelab_backups → Create Folder → Name: proxmox
   ```

**Validation**:
```bash
# On Synology via SSH
ls -ld /volume1/homelab_backups/
# Should show: drwxr-xr-x with appropriate owner
```

---

### 2. NFS Export Configuration

**Purpose**: Enable NFS access from Proxmox host to backup share

**Steps**:

1. In Synology DSM, navigate to **Control Panel → File Services → NFS**

2. Enable NFS service:
   - Check "Enable NFSv3"
   - Check "Enable NFSv4" (optional, better security)
   - Check "Enable NFSv4.1" (optional)

3. Configure NFS permissions for `homelab_backups`:
   - Navigate to **Control Panel → Shared Folder**
   - Select `homelab_backups`
   - Click **Edit → NFS Permissions**
   - Click **Create**

4. Add NFS rule:
   - **Hostname or IP**: `192.168.1.112` (Proxmox host `pve`)
   - **Privilege**: Read/Write
   - **Squash**: No mapping (allow root access from client)
   - **Security**: sys (standard authentication)
   - **Enable asynchronous**: Checked (better performance)
   - **Allow connections from non-privileged ports**: Unchecked
   - **Allow users to access mounted subfolders**: Checked

**Validation**:
```bash
# On Proxmox host
showmount -e 192.168.1.109
# Should show: /volume1/homelab_backups 192.168.1.112
```

---

### 3. NFS Mount Test

**Purpose**: Verify Proxmox host can mount NAS share before automation

**Steps**:

1. SSH to Proxmox host:
   ```bash
   ssh root@192.168.1.112
   ```

2. Ensure NFS client installed:
   ```bash
   apt update
   apt install -y nfs-common
   ```

3. Create test mount point:
   ```bash
   mkdir -p /mnt/test-nas
   ```

4. Test mount:
   ```bash
   mount -t nfs 192.168.1.109:/volume1/homelab_backups /mnt/test-nas
   ```

5. Verify mount:
   ```bash
   df -h | grep homelab_backups
   mount | grep homelab_backups
   ```

6. Create proxmox subdirectory and test write permissions:
   ```bash
   mkdir -p /mnt/test-nas/proxmox
   touch /mnt/test-nas/proxmox/test-write.txt
   echo "test content" > /mnt/test-nas/proxmox/test-write.txt
   cat /mnt/test-nas/proxmox/test-write.txt
   rm /mnt/test-nas/proxmox/test-write.txt
   ```

7. Unmount test:
   ```bash
   umount /mnt/test-nas
   rmdir /mnt/test-nas
   ```

**Expected Results**:
- Mount succeeds without errors
- `df -h` shows NFS mount with available space
- Write test succeeds (file created and removed)
- Unmount succeeds

**Troubleshooting**:
- **"access denied"**: Check NFS rule allows 192.168.1.112
- **"no route to host"**: Verify NAS reachable (`ping 192.168.1.109`)
- **"permission denied"**: Check squash setting (should be "no mapping")
- **"Protocol not supported"**: Don't mount subdirectory directly. Mount parent share:
  ```bash
  # WRONG: mount -t nfs 192.168.1.109:/volume1/homelab_backups/proxmox /mnt/test-nas
  # RIGHT: mount -t nfs 192.168.1.109:/volume1/homelab_backups /mnt/test-nas
  ```
  Then access subdirectory: `/mnt/test-nas/proxmox/`
- **Mount hangs**: Check firewall allows NFS ports (2049, 111)

---

### 4. Age Encryption Key Generation

**Purpose**: Generate age keypair for backup encryption and store in Bitwarden

**Prerequisites**: age must be installed on your local machine (see section 0 above)

**Steps**:

1. Generate keypair:
   ```bash
   age-keygen -o proxmox-backup.key
   ```
   
   Output shows:
   ```
   Public key: age1xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

3. Store keys in Bitwarden:
   - Open Bitwarden
   - Create new **Secure Note**
   - Title: "Proxmox Backup Encryption Key"
   - Add custom field "Public Key": `age1xxx...` (from output)
   - Add custom field "Private Key": (paste contents of `proxmox-backup.key` file)
   - Add custom field "Homelab": "homelab-proxmox"
   - Add note: "Created: 2025-12-22 | Used for: Proxmox config backups on NAS"
   - Save

4. Test encryption/decryption:
   ```bash
   # Encrypt test file
   echo "test data" | age -r age1xxx... -o test.age
   
   # Decrypt test file
   age -d -i proxmox-backup.key test.age
   # Should output: test data
   
   # Clean up
   rm test.age proxmox-backup.key
   ```

5. Key will be deployed to PVE by Ansible (stored in `/root/.age/proxmox-backup.key`)

**Key Security**:
- ✅ Private key stored in Bitwarden (encrypted at rest)
- ✅ Private key deployed to PVE via Ansible (git-ignored variables)
- ✅ Public key can be committed to git (encryption only, safe)
- ⚠️ **CRITICAL**: Do NOT lose private key - backups unrecoverable without it
- 📋 **RECOMMENDATION**: Print paper backup of private key, store in safe

**Key Rotation**:
- Old backups remain encrypted with old key
- Both keys required after rotation (documented in key rotation procedure)
- Test decryption of old backup with old key before discarding

---

## Quickstart Guide

**Prerequisites**: All manual setup tasks above completed

### Deploy Backup System

```bash
# From repo root
cd /Users/Andreas.Jacobsen/Development/private/homelab-proxmox

# Deploy backup role to Proxmox host
ansible-playbook ansible/playbooks/backup_proxmox.yml

# Verify deployment
ssh root@192.168.1.112 "ls -lh /usr/local/sbin/proxmox-config-backup /etc/proxmox-backup.conf"
```

### Run Manual Backup

```bash
# SSH to Proxmox host
ssh root@192.168.1.112

# Run backup manually
/usr/local/sbin/proxmox-config-backup

# Check logs
journalctl -u proxmox-backup.service -f

# Verify backup on NAS
ls -lh /mnt/nas-backup/proxmox-backup-*.tar.zst.age
```

### Verify Backup Integrity

```bash
# On Proxmox host
/usr/local/sbin/proxmox-config-backup --verify /mnt/nas-backup/proxmox-backup-20251222-020000.tar.zst.age

# Should output:
# ✓ Backup verified successfully
# - Decryption: OK
# - Files: 15
# - Checksums: OK
```

### Check Systemd Timer Status

```bash
# On Proxmox host
systemctl status proxmox-backup.timer
systemctl list-timers proxmox-backup.timer

# Should show: Active, next run at 02:00 tomorrow
```

---

## CI/CD Integration

**Current Workflow** (December 2025):
- Ansible executed from local laptop
- Repo: `/Users/Andreas.Jacobsen/Development/private/homelab-proxmox`
- Deployment: Manual via `./scripts/backup/run_proxmox_backup.sh`

**Future Workflow** (Planned):
- Ansible executed from Raspberry Pi with GitHub Actions runner
- Repo cloned by GitHub Actions on Pi
- Deployment: Automated on git push to main branch

**IaC Backup Support**:
- Repo automatically deployed to PVE at `/root/homelab-proxmox`
- Ansible role ensures repo is cloned/updated before backup runs
- Works with both laptop-based and GitHub Actions workflows
- Repo updated via Ansible task (pull from GitHub on deployment)

---

## Configuration

### Backup Variables

Located in `ansible/group_vars/proxmox_hosts.yml`:

```yaml
proxmox_backup_enabled: true
proxmox_backup_schedule: "daily"
proxmox_backup_time: "02:00"

proxmox_backup_nas_host: "192.168.1.109"
proxmox_backup_nas_path: "/volume1/homelab_backups/proxmox"
proxmox_backup_age_key_path: "/root/.age/proxmox-backup.key"

# Optional: Enable IaC artifact backup (requires repo on PVE)
# proxmox_backup_repo_path: "/root/homelab-proxmox"

# Optional: Opt-in for sensitive data (default: false)
proxmox_backup_include_tailscale_state: false
proxmox_backup_include_rclone_conf: false

# Retention
proxmox_backup_retention_daily: 30
proxmox_backup_retention_monthly: 12
```

### Configuration File on PVE

Location: `/etc/proxmox-backup.conf`

Deployed by Ansible, sources variables from group_vars. Contains:
- NAS mount configuration
- Age key paths
- Retention policy
- Optional features (Tailscale, rclone, IaC repo path)
- Email notification settings (if configured)

---

## Monitoring

### Backup Success/Failure

**Check last backup status**:
```bash
# On Proxmox host
systemctl status proxmox-backup.service
journalctl -u proxmox-backup.service -n 50
```

**Check backup history**:
```bash
# On NAS
ssh root@192.168.1.109 "ls -lhtr /volume1/homelab_backups/proxmox/"
```

**Email notifications** (if configured):
- Failure: Email sent immediately with error details
- Success: Email sent only if `proxmox_backup_notify_on_success: true`

### Integration with Uptime Kuma (Future)

Monitor backup freshness:
- Check latest backup timestamp on NAS
- Alert if no backup in last 36 hours
- Integration documented in Phase 8 (T078)

---

## Troubleshooting

### Backup Fails with "NFS mount unavailable"

**Symptoms**: journalctl shows mount error

**Checks**:
1. Verify NAS reachable: `ping 192.168.1.109`
2. Verify NFS service running on NAS: `showmount -e 192.168.1.109`
3. Check NFS rule allows PVE: DSM → Shared Folder → homelab_backups → NFS Permissions
4. Test manual mount: `mount -t nfs 192.168.1.109:/volume1/homelab_backups /mnt/test`

### Backup Fails with "encryption failed"

**Symptoms**: journalctl shows age encryption error

**Checks**:
1. Verify age key exists: `ls -l /root/.age/proxmox-backup.key`
2. Verify key permissions: `stat -c %a /root/.age/proxmox-backup.key` (should be 600)
3. Test encryption: `echo "test" | age -r <public-key>`
4. Check config file: `cat /etc/proxmox-backup.conf | grep AGE_PUBLIC_KEY`

### Backup Runs but Archive Size Zero

**Symptoms**: Archive created but empty

**Checks**:
1. Check staging directory: `ls -lh /var/backups/proxmox-staging/`
2. Check disk space: `df -h /var/backups`
3. Check collection functions in journalctl
4. Verify /etc/pve accessible: `ls -lh /etc/pve/lxc/`

### "Lock already held" Error

**Symptoms**: Backup exits immediately with lock error

**Cause**: Previous backup still running or crashed leaving lock

**Solution**:
```bash
# Check for running backup process
ps aux | grep proxmox-config-backup

# If no process running, lock is stale - script uses flock so will auto-clear on reboot
# Or wait for flock timeout (usually immediate)

# Force manual cleanup (last resort)
# Script uses flock, so lock is automatically released when process exits
```

### "No such file or directory" for /root/.age/proxmox-backup.key

**Symptoms**: Manual key deployment fails with directory not found

**Cause**: /root/.age/ directory doesn't exist (Ansible would create it, but if deployment skipped)

**Solution**:
```bash
# On PVE host
mkdir -p /root/.age
echo 'AGE-SECRET-KEY-1xxx...' > /root/.age/proxmox-backup.key
chmod 600 /root/.age/proxmox-backup.key

# Verify
ls -l /root/.age/proxmox-backup.key
# Should show: -rw------- 1 root root
```

### Ansible "no hosts matched"

**Symptoms**: Deployment script runs but Ansible skips all tasks

**Cause**: Inventory doesn't have proxmox_hosts group or inventory not loaded

**Solution**:
```bash
# Check inventory exists
ls -l ansible/inventories/static/hosts.yml

# Verify proxmox_hosts group defined
grep -A 5 'proxmox_hosts:' ansible/inventories/static/hosts.yml

# If missing, add to inventory:
proxmox_hosts:
  hosts:
    pve:
      ansible_host: 192.168.1.112
      ansible_user: root

# Re-run deployment
./scripts/backup/run_proxmox_backup.sh
```

---

## What Gets Backed Up

### User Story 1 - Proxmox Configuration (Always)

- ✅ LXC container configs: `/etc/pve/lxc/*.conf`
- ✅ Storage config: `/etc/pve/storage.cfg`
- ✅ Network config: `/etc/network/interfaces`, `/etc/network/interfaces.d/*`
- ✅ System mounts: `/etc/fstab`
- ⚠️ Tailscale state: `/var/lib/tailscale/*` (opt-in, default: false)
- ⚠️ rclone config: `/root/.config/rclone/rclone.conf` (opt-in, default: false)

### User Story 2 - IaC Artifacts (If repo path defined)

- ✅ Terraform state: `terraform/terraform.tfstate`, `terraform/terraform.tfstate.backup`
- ✅ Ansible inventory: `ansible/inventories/generated/hosts.yml`
- ✅ Ansible group_vars: `ansible/group_vars/*` (excludes `secrets.yml`)
- ✅ Ansible playbooks: `ansible/playbooks/*.yml`
- ✅ Ansible role tasks: `ansible/roles/*/tasks/*.yml`
- ✅ Documentation: `README.md`, `docs/operations/*.md`, `docs/runbooks/*.md`

### What's NOT Backed Up

- ❌ LXC root filesystems (data backups handled separately)
- ❌ Git history (`.git/` directory excluded)
- ❌ Terraform providers (`.terraform/` excluded, re-downloaded on restore)
- ❌ Node modules, Python caches (`node_modules/`, `__pycache__/` excluded)
- ❌ Plaintext secrets (fails backup if detected)

---

## Restore Procedure

See [backups-proxmox-config-restore.md](./backups-proxmox-config-restore.md) for complete step-by-step restore runbook.

**Quick reference**:
1. Fresh Proxmox install
2. Retrieve encryption key from Bitwarden
3. Mount NAS, download backup archive
4. Decrypt: `age -d -i proxmox-backup.key backup.tar.zst.age | tar -xzstf -`
5. Restore files manually (LXC configs, network, fstab)
6. Verify configuration before starting containers
7. Restore IaC artifacts, run `terraform plan` (should show zero changes)

**Target**: Complete restore in under 2 hours

---

## Backup Schedule

- **Frequency**: Daily
- **Time**: 02:00 (2 AM local time)
- **Mechanism**: systemd timer (`proxmox-backup.timer`)
- **Rotation**: Before backup (fail-safe if disk full)
- **Retention**: 30 daily + 12 monthly = 42 total backups (~4 GB)

---

## Security

- 🔐 **Encryption**: age with public/private keypair
- 🔐 **Key storage**: Private key in Bitwarden + deployed to PVE (git-ignored)
- 🔐 **Archive permissions**: 640 root:root on NAS
- 🔐 **Sensitive data**: Opt-in only (Tailscale state, rclone config default: excluded)
- 🔐 **Secret scanning**: Script fails if plaintext credentials detected in IaC artifacts
- 🔐 **No plaintext secrets**: Staging cleaned after successful backup

---

## Maintenance

### Quarterly Restore Drill

**Purpose**: Validate restore procedure remains current and backups are recoverable

**Schedule**: Every 3 months

**Procedure**: See Feature 012 style quarterly drill documentation

### Monthly Backup Verification

**Purpose**: Verify recent backups are not corrupted

```bash
# On Proxmox host
for backup in $(ls -t /mnt/nas-backup/proxmox-backup-*.tar.zst.age | head -5); do
  echo "Verifying: $backup"
  /usr/local/sbin/proxmox-config-backup --verify "$backup"
done
```

### Annual Key Rotation

**Purpose**: Security hygiene (optional, not required)

**Procedure**: Documented in key rotation section (T076)

---

## CI/CD Integration

### Current Workflow (Laptop-Based)

The backup system is deployed using Ansible from your local development machine:

**Deployment Flow**:
```
Laptop (macOS) 
  → Ansible over SSH 
    → PVE Host (192.168.1.112)
      → Deploy backup script + systemd timer
      → Clone/update homelab-proxmox repo to /root/homelab-proxmox
      → systemd timer runs backup daily at 02:00
```

**Benefits**:
- Simple setup (no additional infrastructure)
- Manual control over deployments
- Fast iteration during development

**Limitations**:
- Requires laptop available for deployments
- Manual execution required

### Future Workflow (GitHub Actions on Raspberry Pi)

The system is designed to transition seamlessly to GitHub Actions:

**Planned Flow**:
```
GitHub Push 
  → GitHub Actions (self-hosted runner on Raspberry Pi) 
    → Ansible over SSH 
      → PVE Host (192.168.1.112)
        → Deploy backup script + systemd timer
        → Clone/update homelab-proxmox repo to /root/homelab-proxmox
        → systemd timer runs backup daily at 02:00
```

**Benefits**:
- Automated deployments on git push
- CI/CD best practices (testing, validation)
- No laptop dependency
- Audit trail via GitHub Actions logs

**Implementation Notes**:
- Repository sync task (`sync_repo.yml`) supports both workflows
- IaC artifacts backed up from `/root/homelab-proxmox` (works for both)
- Age key stored in GitHub Secrets for automated deployments
- Ansible inventory managed in repo

**Transition Steps** (Future):
1. Set up GitHub Actions self-hosted runner on Raspberry Pi
2. Add workflow file (`.github/workflows/deploy-proxmox-backup.yml`)
3. Store age private key in GitHub Secrets
4. Configure Ansible vault password in GitHub Secrets
5. Test deployment via GitHub Actions
6. Enable automatic deployments on push to main

---

## Backup Verification

### Manual Verification

Use the verification script to check backup integrity without full restore:

**Basic Verification**:
```bash
# On Proxmox host
/root/homelab-proxmox/scripts/backup/verify_proxmox_backup.sh \
  /mnt/nas-backup/proxmox/proxmox-backup-20251223-120000.tar.zst.age
```

**Verification Process**:
1. ✓ Decryption test (validates age key and encryption)
2. ✓ Decompression test (validates zstd integrity)
3. ✓ Required files check (storage.cfg, manifest.txt, etc.)
4. ✓ Checksum validation (verifies file integrity via SHA256)

**Exit Codes**:
- `0` - Success: backup is valid and complete
- `1` - Decryption failed (invalid key or corrupted encryption)
- `2` - Checksum mismatch (file corruption detected)
- `3` - Missing required files (incomplete backup)
- `4` - Invalid usage

**Custom Age Key**:
```bash
AGE_KEY_FILE=/path/to/key verify_proxmox_backup.sh backup.tar.zst.age
```

### Automated Post-Backup Verification

The backup script automatically verifies each backup after creation:

**Verification Steps**:
1. File size check (minimum 1KB)
2. Decryption test (first 1MB)
3. Archive structure validation (tar listing)

**Monitoring Verification**:
```bash
# Check verification status in logs
journalctl -u proxmox-backup.service -n 50 | grep -i verify

# Expected output:
# INFO: Verifying backup integrity
# INFO: Testing decryption of backup archive
# INFO: Verifying archive structure
# INFO: Backup verification passed: 4.0K
# INFO: ✓ File size valid
# INFO: ✓ Decryption successful
# INFO: ✓ Archive structure valid
```

### Quarterly Verification Drill

Run comprehensive verification on all recent backups:

```bash
# Verify last 7 daily backups
ssh root@192.168.1.112 'for backup in $(ls -t /mnt/nas-backup/proxmox/proxmox-backup-*.tar.zst.age | head -7); do
  echo "Verifying: $(basename $backup)"
  /root/homelab-proxmox/scripts/backup/verify_proxmox_backup.sh "$backup" || echo "FAILED: $backup"
done'
```

**Expected Results**:
- All backups should pass verification
- Any failures indicate corruption or key issues
- Document failures and investigate immediately

---

## Support

For issues or questions:
- Check troubleshooting section above
- Review journalctl logs: `journalctl -u proxmox-backup.service -n 100`
- Verify prerequisites completed
- Test NFS mount manually
- Validate age key in Bitwarden

**Last Updated**: 2025-12-22  
**Feature**: 013-proxmox-config-backup  
**Architecture**: Choice 3, Option A (bash script runtime)
