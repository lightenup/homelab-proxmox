# Operations Manual

## Remote Access (Tailscale)

### Validation (Smoke Test)

To verify that remote access is working correctly:

1.  **Disconnect from WiFi**: Ensure your client device (phone/laptop) is on an external network (e.g., LTE/5G or a coffee shop WiFi).
2.  **Enable Tailscale**: Connect to your tailnet.
3.  **Test Proxmox UI**:
    *   Navigate to `https://192.168.1.112:8006`
    *   **Expected**: Login page loads.
4.  **Test SSH**:
    *   Run `ssh root@192.168.1.112`
    *   **Expected**: Shell prompt appears.
5.  **Test Services**:
    *   Navigate to `http://192.168.1.213:2283` (Immich)
    *   **Expected**: Immich loads.
6.  **Test ACLs (Negative Test)**:
    *   If you have a non-admin device, try to SSH to `192.168.1.112`.
    *   **Expected**: Connection timed out or refused (blocked by ACL).

### Troubleshooting

*   **Host not appearing**: Check `systemctl status tailscaled` on the Proxmox host.
*   **Routes not working**: Ensure you approved the `192.168.1.0/24` route in the Tailscale Admin Console.
*   **Key Expired**: If the auth key expires, generate a new one and update `ansible/group_vars/proxmox_hosts.yml`.

## Proxmox Configuration Backup

- **Main Operations Guide**: [Proxmox Configuration Backup Operations](operations/backups-proxmox-config.md)
- **Restore Guide**: [Proxmox Configuration Restore](operations/backups-proxmox-config-restore.md)

### Email Decommissioning & Kuma Migration

We have migrated from email notifications to Uptime Kuma Push monitoring.

-   **Runbook**: [Proxmox Backup Email Decommissioning](operations/backups-proxmox-config-email-decommission.md)
-   **Current Mode**: `kuma_only` (Email disabled, Kuma active)
-   **Configuration**: `ansible/group_vars/proxmox_hosts/vars.yml`

## Evidence Governance

The lab suite produces evidence packs for every run. These packs are validated against a strict schema and catalog.

### Verification

To verify an evidence pack against the catalog and schema:

```bash
scripts/lab/pve-lab verify-evidence artifacts/019-lab/lab-YYYYMMDD-HHMMSS
```

This checks:
- **Structure**: JSON schema compliance.
- **Catalog**: All checks must be defined in `scripts/lab/checks.d/catalog.json`.
- **Integrity**: All referenced evidence files must exist.

### Comparison (Diff)

To compare two evidence packs (e.g., to check for regressions or drift):

```bash
scripts/lab/pve-lab diff-evidence artifacts/019-lab/run-A artifacts/019-lab/run-B
```

### Catalog Maintenance

The Check Catalog is the Single Source of Truth (SSOT) for all checks.
Location: `scripts/lab/checks.d/catalog.json`

To add a new check:
1.  Add the check definition to `catalog.json`.
2.  Ensure the `check_id` is unique.
3.  Run `scripts/lab/ci-verify.sh` to validate the catalog.
