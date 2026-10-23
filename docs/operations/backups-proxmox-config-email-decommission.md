# Runbook: Proxmox Backup Email Notification Configuration

**Feature**: 014-email-decommission
**Status**: Active
**Last Updated**: 2026-03-01

## Overview

This runbook details the procedure for managing Proxmox host backup email notifications. Backup monitoring is handled by Prometheus/Alertmanager: `BackupStale{backup="proxmox"}` fires 36 hours after the last verified run, or if none was ever recorded. Email notifications are an optional additional channel.

## State Machine

The notification mode follows a strict state machine to ensure safety and reversibility.

| State | Description | Configuration (`proxmox_backup_email_mode`) |
|-------|-------------|---------------------------------------------|
| **Enabled** | Postfix running, email notifications active. | `enabled` |
| **Disabled** | **Current State**. No email notifications. Monitoring via Prometheus/Alertmanager. | `disabled` |
| **Removed** | Postfix packages uninstalled. Irreversible without manual reinstall. | `removed` |

### State Transitions

1.  **Enabled → Disabled**:
    -   Stop and disable `postfix` service.
    -   Remove SMTP credentials from backup config.
    -   *Rollback*: Set mode to `enabled` to restart Postfix and restore credentials.

2.  **Disabled → Removed**:
    -   **Requires Confirmation**: `proxmox_backup_uninstall_confirmed: true`.
    -   Purge `postfix` and `mailutils` packages.
    -   Remove `/etc/postfix` configuration.
    -   *Rollback*: Manual re-installation of packages required.

## Discovery Phase

Before disabling email, the playbook runs a discovery phase to ensure Postfix is not being used by other services.

**Checks Performed**:
1.  **Service Status**: Is Postfix running?
2.  **Package Status**: Are `postfix` or `mailutils` installed?
3.  **Activity Log**: Has Postfix processed mail in the last 7 days? (`journalctl`)
4.  **Usage Scan**: Do other scripts reference `sendmail` or `mail`?

**Conflict Resolution**:
- If active usage is detected (outside of the backup script), the playbook will **abort**.
- To override this safety check, set `proxmox_backup_force_remove_email: true`.

## Procedures

### 1. Verify Prometheus Monitoring (Current State)

Ensure that Prometheus/Alertmanager is monitoring backup infrastructure:

1.  Open Prometheus at `http://192.168.1.214:9090/targets`.
2.  Verify the `node-exporter` job shows the Proxmox host target as `UP`.
3.  Check Alertmanager at `http://192.168.1.214:9093` — no active `BackupStale` alerts.

### 2. Enable Email (Optional)

To activate SMTP email notifications in addition to Prometheus monitoring:

1.  Edit `ansible/group_vars/proxmox_hosts/vars.yml`:
    ```yaml
    proxmox_backup_email_mode: "enabled"
    ```
2.  Configure SMTP credentials in the vault:
    ```yaml
    proxmox_backup_smtp_host: "smtp.gmail.com"
    proxmox_backup_email_from: "alerts@example.com"
    proxmox_backup_email_to: "admin@example.com"
    ```
3.  Run playbook:
    ```bash
    ansible-playbook playbooks/site.yml --tags proxmox_backup
    ```

### 3. Disable Email (Return to Prometheus-Only)

1.  Edit `ansible/group_vars/proxmox_hosts/vars.yml`:
    ```yaml
    proxmox_backup_email_mode: "disabled"
    ```
2.  Run playbook:
    ```bash
    ansible-playbook playbooks/site.yml --tags proxmox_backup
    ```
3.  Verify Postfix is stopped on host:
    ```bash
    ssh root@proxmox "systemctl status postfix"
    # Should show: Active: inactive (dead)
    ```

### 4. Remove Packages (Final Cleanup)

**Warning**: This step removes software. Only proceed after running in "Disabled" mode for 1-2 weeks.

1.  Edit `ansible/group_vars/proxmox_hosts/vars.yml`:
    ```yaml
    proxmox_backup_email_mode: "removed"
    proxmox_backup_uninstall_confirmed: true
    ```
2.  Run playbook:
    ```bash
    ansible-playbook playbooks/site.yml --tags proxmox_backup
    ```
3.  Verify packages are gone:
    ```bash
    ssh root@proxmox "dpkg -l | grep postfix"
    # Should return no output
    ```

## Troubleshooting

### "Conflict detected: Postfix appears to be in use"
- **Cause**: The discovery phase found logs indicating email activity or scripts referencing mail commands.
- **Solution**: Investigate the logs shown in the error message. If the activity is non-critical or legacy, set `proxmox_backup_force_remove_email: true` to bypass.

### Backup Script Fails
- **Cause**: Check `/var/log/syslog` or `journalctl -u proxmox-backup.service` on the Proxmox host.
- **Solution**: Verify NAS connectivity and age encryption key configuration in `/etc/proxmox-backup.conf`.
