# Runbook: Decommission Host Email Notifications

**Feature**: 014-email-decommission
**Status**: Active
**Last Updated**: 2025-12-28

## Overview

This runbook details the procedure for transitioning Proxmox host backup notifications from legacy Email (Postfix) to Centralized Monitoring (Uptime Kuma). This change reduces maintenance overhead and security surface area by removing the need for a local MTA on the hypervisor.

## State Machine

The transition follows a strict state machine to ensure safety and reversibility.

| State | Description | Configuration (`proxmox_backup_email_mode`) |
|-------|-------------|---------------------------------------------|
| **Enabled** | Legacy state. Postfix running, email notifications active. | `enabled` |
| **Kuma Only** | **Current State**. Postfix running but unused by backup script. Kuma push active. | `kuma_only` |
| **Disabled** | Postfix service stopped and disabled. Kuma push active. | `disabled` |
| **Removed** | Postfix packages uninstalled. Irreversible without manual reinstall. | `removed` |

### State Transitions

1.  **Enabled → Kuma Only**:
    -   Deploy Kuma push configuration.
    -   Update backup script to use Kuma.
    -   Verify Kuma notifications work.
    -   *Rollback*: None needed (additive change).

2.  **Kuma Only → Disabled**:
    -   Stop and disable `postfix` service.
    -   Remove SMTP credentials from backup config.
    -   *Rollback*: Set mode to `enabled` to restart Postfix and restore credentials.

3.  **Disabled → Removed**:
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

### 1. Verify Kuma Monitoring (Current State)

Ensure that Uptime Kuma is receiving heartbeats from the backup script.

1.  Check Uptime Kuma Dashboard.
2.  Look for "Proxmox Backup" monitor.
3.  Status should be "Up".
4.  Message should be "Backup Success".

### 2. Disable Email (Planned)

To stop the Postfix service and rely solely on Kuma:

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

### 3. Rollback to Email (If needed)

If Kuma monitoring fails or email is required again:

1.  Edit `ansible/group_vars/proxmox_hosts/vars.yml`:
    ```yaml
    proxmox_backup_email_mode: "enabled"
    ```
2.  Run playbook:
    ```bash
    ansible-playbook playbooks/site.yml --tags proxmox_backup
    ```
3.  Verify Postfix is running.

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

### "Kuma URL not defined"
- **Cause**: `proxmox_backup_kuma_url` is missing in `vars.yml`.
- **Solution**: Ensure the variable is set. It should be automatically populated from the monitoring host if the full playbook is run.

### Backup Script Fails with "curl: (7) Failed to connect"
- **Cause**: The Kuma URL is unreachable from the Proxmox host.
- **Solution**: Check network connectivity between Proxmox and the Monitoring LXC. Ensure the URL uses the correct IP (not localhost).
