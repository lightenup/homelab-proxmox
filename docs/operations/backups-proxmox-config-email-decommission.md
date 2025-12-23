# Email Notification Decommissioning Guide

**Feature**: 013-proxmox-config-backup  
**Date**: December 23, 2025  
**Purpose**: Safely transition from host-level SMTP to Kuma push monitoring

---

## Overview

This guide documents the safe decommissioning of host-level email notifications for the Proxmox backup system in favor of centralized Kuma push monitoring.

**Why decommission host-level email?**
- **Centralized monitoring**: Kuma provides single pane of glass for all service monitoring
- **Better reliability**: Push-based monitoring detects failures faster than email-only alerts
- **Reduced complexity**: Eliminates need for SMTP relay configuration on PVE host
- **Security**: Removes stored SMTP credentials from PVE host
- **Maintainability**: One notification channel (Kuma) instead of per-service email configs

---

## Architecture Change

### Before (Phase 7 - DEPRECATED)
```
Backup Script → mail command → Postfix SMTP Relay → Gmail → Email Notification
```

### After (Recommended)
```
Backup Script → Kuma Push API → Kuma Monitoring → Email/Slack/Discord
                                  ↓
                            Centralized Notifications
```

---

## Prerequisites

✅ **Before decommissioning**, ensure:

1. **Kuma monitoring configured** for proxmox-backup
   - Push monitor created in Kuma web UI
   - Push URL added to ansible/group_vars/proxmox_hosts/vars.yml
   - Variable: `proxmox_backup_kuma_push_url`

2. **Test Kuma integration**
   ```bash
   # Run backup manually
   ssh root@192.168.1.112 /usr/local/sbin/proxmox-config-backup
   
   # Verify Kuma received push
   # Check Kuma web UI - monitor should show "up" status with recent timestamp
   ```

3. **Test failure detection**
   ```bash
   # Temporarily break NAS mount
   ssh root@192.168.1.112
   systemctl stop proxmox-backup.timer
   
   # Edit config to break NAS path
   sed -i 's/homelab_backups/BROKEN_PATH/' /etc/proxmox-backup.conf
   
   # Run backup (should fail)
   /usr/local/sbin/proxmox-config-backup
   
   # Verify:
   # - Exit code non-zero
   # - Kuma monitor shows "down" or heartbeat stale
   # - Kuma sends notification via configured channels
   
   # Restore config
   sed -i 's/BROKEN_PATH/homelab_backups/' /etc/proxmox-backup.conf
   systemctl start proxmox-backup.timer
   ```

---

## Decommissioning Procedures

### Phase 1: Disable Email (Safe, Reversible)

**Ansible approach** (recommended):

```bash
# In ansible/group_vars/proxmox_hosts/vars.yml, set:
proxmox_backup_remove_host_email: true
proxmox_backup_kuma_push_url: "https://kuma.local/api/push/xxxxx"

# Run playbook
cd ansible
ansible-playbook -i inventories/static/hosts.yml playbooks/backup_proxmox.yml \
  --vault-password-file ~/.ansible_vault_pass \
  --tags backup,decommission
```

**What this does**:
- ✓ Stops Postfix service
- ✓ Disables Postfix from starting on boot
- ✓ Removes Gmail SMTP relay configuration from /etc/postfix/main.cf
- ✓ Removes SASL password files (/etc/postfix/sasl_passwd*)
- ✓ Updates backup script to disable email by default (ENABLE_HOST_EMAIL=false)
- ✓ Logs decommissioning action to journald
- ✗ Does NOT uninstall packages (safe to keep)

**Manual approach** (if needed):

```bash
ssh root@192.168.1.112

# 1. Stop email service
systemctl stop postfix
systemctl disable postfix

# 2. Disable email in backup config
cat >> /etc/proxmox-backup.conf << 'EOF'

# Email notifications disabled - Kuma monitoring active
ENABLE_HOST_EMAIL=false
EOF

# 3. Verify backup still works
/usr/local/sbin/proxmox-config-backup

# 4. Check Kuma received push
# (Check Kuma web UI)
```

### Phase 2: Uninstall Packages (Optional, Requires Confirmation)

⚠️ **CAUTION**: Only proceed if Phase 1 testing confirms everything works

**Discovery first** (check what would be removed):

```bash
ssh root@192.168.1.112

# List mail packages
dpkg -l | egrep -i 'mailutils|postfix|libsasl'

# Check if anything else uses mail
grep -RniE 'sendmail|mailx|postfix' /etc/systemd /opt /usr/local 2>/dev/null | grep -v proxmox-backup
```

**Ansible approach** (if discovery shows only backup usage):

```bash
# In ansible/group_vars/proxmox_hosts/vars.yml, add:
proxmox_backup_remove_host_email_packages: true
proxmox_backup_uninstall_postfix: true  # If Postfix not used elsewhere

# IMPORTANT: Requires explicit confirmation flag
ansible-playbook -i inventories/static/hosts.yml playbooks/backup_proxmox.yml \
  --vault-password-file ~/.ansible_vault_pass \
  --tags backup,decommission \
  -e proxmox_backup_uninstall_confirmed=true
```

**What this does**:
- ✓ Removes mailutils package
- ✓ Removes bsd-mailx package
- ✓ Removes libsasl2-modules package
- ✓ Optionally removes Postfix (if flag set)
- ✓ Removes /etc/postfix directory (if Postfix removed)
- ✓ Runs apt autoremove to clean dependencies
- ✓ Logs package removal to journald

### Phase 3: Post-Decommissioning Verification

**Run verification checklist**:

```bash
ssh root@192.168.1.112

# 1. Verify mail binaries removed (if uninstalled)
which mail sendmail msmtp 2>/dev/null || echo "✓ No mail binaries found"

# 2. Verify Postfix not running
systemctl status postfix 2>/dev/null || echo "✓ Postfix not active"

# 3. Run backup manually
/usr/local/sbin/proxmox-config-backup

# 4. Check logs for email warnings (should be none)
journalctl -u proxmox-backup.service -n 50 | grep -i email || echo "✓ No email-related errors"

# 5. Verify backup created on NAS
ls -lh /mnt/nas-backup/proxmox-backup-*.tar.zst.age | head -1

# 6. Check Kuma monitor status
# (Open Kuma web UI - monitor should be "up" with recent timestamp)
```

**Test failure path**:

```bash
# Break NAS mount temporarily
systemctl stop proxmox-backup.timer
sed -i 's/homelab_backups/BROKEN/' /etc/proxmox-backup.conf

# Run backup (should fail)
/usr/local/sbin/proxmox-config-backup
echo "Exit code: $?"  # Should be non-zero

# Verify Kuma detected failure
# (Check Kuma web UI - monitor should show "down" or heartbeat stale)
# (Verify you received notification from Kuma via email/Slack/Discord)

# Restore config
sed -i 's/BROKEN/homelab_backups/' /etc/proxmox-backup.conf
systemctl start proxmox-backup.timer
```

---

## Rollback Procedures

If Kuma monitoring isn't working and you need to temporarily restore email:

```bash
ssh root@192.168.1.112

# 1. Re-enable email in config
cat >> /etc/proxmox-backup.conf << 'EOF'

# Temporary email re-enable for troubleshooting
ENABLE_HOST_EMAIL=true
NOTIFY_ON_SUCCESS=false
SMTP_HOST=smtp.gmail.com
EMAIL_FROM=your-email@gmail.com
EMAIL_TO=your-email@gmail.com
EOF

# 2. Restart Postfix (if not uninstalled)
systemctl start postfix
systemctl enable postfix

# 3. Test email
echo "Test" | mail -s "Proxmox backup test" your-email@gmail.com

# 4. Run backup
/usr/local/sbin/proxmox-config-backup
```

**If packages were uninstalled**, re-run Ansible with email enabled:

```bash
# In ansible/group_vars/proxmox_hosts/vars.yml:
proxmox_backup_enable_host_email: true
proxmox_backup_remove_host_email: false

# Redeploy
ansible-playbook -i inventories/static/hosts.yml playbooks/backup_proxmox.yml \
  --vault-password-file ~/.ansible_vault_pass \
  --tags backup,smtp
```

---

## Configuration Variables

### Kuma Integration (New, Recommended)

```yaml
# ansible/group_vars/proxmox_hosts/vars.yml

# Kuma push monitoring
proxmox_backup_kuma_push_url: "https://kuma.example.com/api/push/xxxxx?status=up&msg=OK"
```

### Email Decommissioning Controls

```yaml
# ansible/group_vars/proxmox_hosts/vars.yml

# Phase 1: Disable email (safe, reversible)
proxmox_backup_remove_host_email: true  # Stops services, removes config

# Phase 2: Uninstall packages (requires confirmation)
proxmox_backup_remove_host_email_packages: true  # Removes mail packages
proxmox_backup_uninstall_postfix: true  # Also remove Postfix
```

### Email Re-enable (Fallback)

```yaml
# ansible/group_vars/proxmox_hosts/vars.yml

# Only if you need to restore email temporarily
proxmox_backup_enable_host_email: true
proxmox_backup_notify_on_success: false

# SMTP credentials in vault.yml (encrypted)
# smtp_host, smtp_user, smtp_password, smtp_from, smtp_to
```

---

## Troubleshooting

### Kuma push not working

**Symptoms**: Backup succeeds but Kuma monitor stays "down" or stale

**Checks**:

```bash
# 1. Verify curl installed
which curl || apt install curl

# 2. Test push URL manually
KUMA_URL="https://kuma.example.com/api/push/xxxxx"
curl -fsS -m 10 "${KUMA_URL}?status=up&msg=test&ping=$(date +%s)"

# 3. Check network connectivity
ping -c 3 kuma.example.com

# 4. Check firewall rules (if Tailscale involved)
# Ensure PVE can reach Kuma service

# 5. Check backup logs
journalctl -u proxmox-backup.service -n 100 | grep -i kuma
```

**Solutions**:
- Verify `proxmox_backup_kuma_push_url` is correctly set in vars.yml
- Ensure Kuma push monitor is created and URL is correct
- Check Kuma service is accessible from PVE host
- Verify no proxy/firewall blocking push requests

### Email still being sent after decommissioning

**Symptoms**: Still receiving backup emails after setting `proxmox_backup_remove_host_email: true`

**Checks**:

```bash
# 1. Verify config deployed
cat /etc/proxmox-backup.conf | grep ENABLE_HOST_EMAIL

# 2. Should show:
# ENABLE_HOST_EMAIL=false (or commented out)

# 3. Check Postfix status
systemctl status postfix
# Should be: inactive (dead)
```

**Solutions**:
- Re-run Ansible playbook with decommission tag
- Manually set `ENABLE_HOST_EMAIL=false` in /etc/proxmox-backup.conf
- Stop Postfix: `systemctl stop postfix && systemctl disable postfix`

### Backup fails after email removal

**Symptoms**: Backup exits with error after decommissioning email

**This should NOT happen** - backup script has safe fallbacks

**Debug**:

```bash
# Run backup with verbose logging
bash -x /usr/local/sbin/proxmox-config-backup 2>&1 | tee /tmp/backup-debug.log

# Check for mail command errors
grep -i mail /tmp/backup-debug.log
```

**Solutions**:
- Review /tmp/backup-debug.log for actual failure cause
- Email removal should not break backup (email functions return 0 if disabled)
- Check if issue is unrelated (NAS mount, disk space, etc.)

---

## Migration Timeline

### Recommended Schedule

**Week 1: Setup and Testing**
- Day 1: Configure Kuma push monitor
- Day 2-3: Add `proxmox_backup_kuma_push_url` to vars
- Day 4-5: Deploy and test Kuma integration (with email still active)
- Day 6-7: Monitor both systems in parallel

**Week 2: Email Decommissioning**
- Day 1: Set `proxmox_backup_remove_host_email: true`
- Day 2-5: Monitor Kuma-only notifications (no email)
- Day 6-7: Verify 100% Kuma coverage

**Week 3+: Optional Package Removal**
- After 2+ weeks of stable Kuma monitoring
- Set `proxmox_backup_remove_host_email_packages: true`
- Run with `-e proxmox_backup_uninstall_confirmed=true`

---

## References

- Feature 013 Spec: [specs/013-proxmox-config-backup/spec.md](../../specs/013-proxmox-config-backup/spec.md)
- Backup Operations: [backups-proxmox-config.md](./backups-proxmox-config.md)
- Kuma Documentation: https://github.com/louislam/uptime-kuma/wiki/API

---

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2025-12-23 | Initial email decommissioning guide created | System |
| 2025-12-23 | Added Kuma push integration | System |
| 2025-12-23 | Documented safe-by-default disable approach | System |
