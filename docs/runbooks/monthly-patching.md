# Monthly Patching Runbook

**Feature**: 010-patch-management-reboots
**Owner**: Homelab Operations
**Last Updated**: December 19, 2025

## Overview

This runbook describes the monthly **security-only** patching process for the homelab infrastructure. The playbook automatically installs security updates, reboots systems when needed, and verifies system health afterward.

**Important**: Systems are configured for security-only updates to maintain maximum stability. Feature and bugfix updates require running the manual upgrade playbook when you have time to address potential issues.

## When to Run

- **Schedule**: First weekend of each month
- **Duration**: 10-15 minutes typical (depends on reboot requirements)
- **Downtime**: Serial execution minimizes impact - only one service down at a time
- **Update Type**: Security patches only (no feature changes)

## Prerequisites

- SSH access to all hosts
- Ansible vault password configured
- Review any planned maintenance that might conflict
- Backup verification (ensure recent backups exist)
- Systems configured with security-only repositories (run `playbooks/configure_security_repos.yml` if not done)

## Standard Execution

### Run Patching (Services Only)

This updates all LXC containers but skips the Proxmox host:

```bash
cd /path/to/homelab-proxmox/ansible
ansible-playbook playbooks/update_monthly.yml
```

**What happens**:
1. Preflight connectivity check to all hosts
2. Services group (LXCs) updated serially (one at a time):
   - adguard
   - homeassistant
   - immich
   - reverse_proxy
3. Each service:
   - Updates apt cache (security repositories only)
   - Upgrades packages (safe mode - security updates only, never removes packages)
   - Reboots if kernel/library updates require it
   - Waits for SSH to return (300s timeout)
   - Verifies infrastructure (NFS/bind mounts)
   - Checks HTTP health (warnings only)
4. Summary report generated with timing and status

### Manual Full Upgrade (Feature + Bugfix Updates)

For non-security updates (features, bugfixes), use the manual upgrade playbook when you have time to troubleshoot potential issues:

```bash
# Dry run first
ansible-playbook playbooks/upgrade_manual.yml --check

# Upgrade specific host
ansible-playbook playbooks/upgrade_manual.yml --limit adguard

# Upgrade all services (skip confirmation pause with --skip-tags pause)
ansible-playbook playbooks/upgrade_manual.yml --limit services --skip-tags pause
```

**What this does**:
- Temporarily enables ALL Debian repositories
- Performs full system upgrade (apt full-upgrade)
- Handles reboots if needed
- Restores security-only repository configuration
- More risky - only run when you can monitor and fix issues

### Run Patching (Including Proxmox Host)

To also patch the Proxmox host with automatic reboot:

```bash
ansible-playbook playbooks/update_monthly.yml -e "allow_host_reboot=true"
```

**⚠️ WARNING**: This will reboot the Proxmox host if kernel updates are available, causing brief downtime for all LXC containers. LXCs will auto-start after host reboot (onboot: 1 configured).

### Run Patching (Specific Hosts)

To patch only specific hosts:

```bash
# Single host
ansible-playbook playbooks/update_monthly.yml --limit adguard

# Multiple hosts
ansible-playbook playbooks/update_monthly.yml --limit adguard,immich

# Services only
ansible-playbook playbooks/update_monthly.yml --limit services

# Host only (without reboot)
ansible-playbook playbooks/update_monthly.yml --limit pve
```

## Expected Output

### Successful Run

```
========== MONTHLY PATCHING SUMMARY ==========
Start Time: 2025-01-05T10:00:00Z
End Time: 2025-01-05T10:12:34Z
Total Execution Time: 754s (12.6m)

Hosts Updated: 4
  adguard, homeassistant, immich, reverse_proxy

Hosts Rebooted: 2
  homeassistant, immich

Verification Status: PASS
  (Infrastructure checks passed, see warnings above for HTTP check issues)
==============================================
```

### Warning Messages

HTTP health checks are **WARNING-ONLY** and won't fail the playbook. You may see:

```
WARNING: Home Assistant is unreachable - Connection timeout
```

This is expected if services are intentionally down for maintenance. Infrastructure checks (SSH, mounts) are CRITICAL and will fail the playbook if broken.

## Verification Steps

After patching completes:

1. **Review Summary Report**
   - Check hosts updated count
   - Verify expected reboots occurred
   - Review verification status

2. **Check Service Health**
   - Immich: http://192.168.1.213:2283
   - Home Assistant: http://192.168.1.212:8123
   - Reverse Proxy: http://192.168.1.211:80
   - AdGuard: http://192.168.1.210:3000

3. **Verify Docker Containers**
   ```bash
   ssh 192.168.1.213  # immich
   docker ps
   # Should see immich containers running (restart: always configured)
   ```

4. **Check Mounts**
   ```bash
   ssh root@pve.local  # or root@192.168.1.112
   mount | grep /mnt/nas/homelab_immich

   ssh 192.168.1.213  # immich or immich.local
   mount | grep /mnt/immich
   ```

## Common Issues

### Issue: Playbook fails at apt update step

**Symptoms**: "Failed to update apt cache after 5 retries"

**Possible Causes**:
- Network connectivity issue
- DNS resolution failure
- Repository mirror down or unreachable
- APT lock held by another process
- Broken sources.list configuration

**Diagnosis**:
```bash
# Run diagnostics playbook on affected host
ansible-playbook playbooks/apt_diagnostics.yml --limit immich
```

**Common Root Causes**:

1. **DNS Resolution Failure** (most common for LXCs)
   - Symptoms: Network ping works, but nslookup/dig fails
   - Error: "Temporary failure resolving 'deb.debian.org'"
   - Fix DNS configuration in LXC:
     ```bash
     # Check current DNS
     ssh 192.168.1.213  # or immich.local
     cat /etc/resolv.conf

     # Option A: Fix in LXC (temporary - lost on reboot)
     echo "nameserver 192.168.1.1" | sudo tee /etc/resolv.conf
     echo "nameserver 8.8.8.8" | sudo tee -a /etc/resolv.conf

     # Option B: Fix in Proxmox (persistent - RECOMMENDED)
     ssh root@pve.local  # or root@192.168.1.112
     pct set 101 --nameserver "192.168.1.1 8.8.8.8"
     pct stop 101 && pct start 101

     # Verify DNS works
     ssh 192.168.1.213  # or immich.local
     nslookup deb.debian.org
     ```

2. **APT Lock Held**
   - Symptoms: "APT LOCKED - Another process is using apt"
   - Cause: Another apt/dpkg process running, or stale lock from crashed process
   - Resolution:
     ```bash
     ssh 192.168.1.213  # or immich.local
     # Check what's holding the lock
     sudo lsof /var/lib/dpkg/lock-frontend

     # If no process found, remove stale locks
     sudo rm /var/lib/dpkg/lock-frontend
     sudo rm /var/lib/dpkg/lock
     sudo rm /var/cache/apt/archives/lock
     ```

3. **Network/Repository Issues**
   - If network ping fails, check LXC networking configuration
   - If repository down, wait and retry or change mirror in sources.list

**Resolution**:
1. Review diagnostics output for specific failure
2. If network/DNS issue, check host networking
3. If repository down, wait and retry or change mirror
4. If APT locked, wait for other process to finish:
   ```bash
   ssh immich
   sudo lsof /var/lib/dpkg/lock-frontend
   ```
5. If sources.list broken, review and fix configuration

### Issue: Playbook fails at reboot step

**Symptoms**: Timeout waiting for SSH reconnection

**Possible Causes**:
- System taking longer than 300s to boot
- SSH service not starting
- Network configuration issue

**Resolution**:
1. Check host status in Proxmox web UI
2. If host is up but SSH failing, use console access
3. Investigate system logs: `journalctl -b`
4. Increase timeout if needed: edit `patch_wait_for_connection_timeout` in role defaults

### Issue: NFS mount missing after reboot

**Symptoms**: Verification fails with "NFS mount not found"

**Possible Causes**:
- NFS server (Synology) not reachable
- Mount defined in /etc/fstab not auto-mounting

**Resolution**:
1. Check Synology NFS service status
2. Manually mount: `mount /mnt/nas/homelab_immich`
3. Verify /etc/fstab entry correct
4. Check network connectivity to NAS

### Issue: LXC container doesn't auto-start after host reboot

**Symptoms**: Container missing after Proxmox host reboot

**Possible Causes**:
- LXC `onboot: 1` not configured

**Resolution**:
1. Check current setting: `ssh root@pve.local` then `pct config <VMID> | grep onboot`
2. Enable auto-start: `pct set <VMID> -onboot 1`
3. Or update Terraform configuration and reapply

### Issue: Docker containers not running in immich

**Symptoms**: Immich HTTP check fails, docker ps shows no containers

**Possible Causes**:
- Docker daemon not started after reboot
- Containers missing `restart: always` policy

**Resolution**:
1. Check Docker status: `systemctl status docker`
2. Start Docker: `systemctl start docker`
3. Check compose file for `restart: always` on all services
4. Manually start: `cd /opt/immich && docker compose up -d`

## Rollback Procedures

### If patching fails mid-execution

1. **Identify failed host**: Check Ansible output for host that failed
2. **Manual investigation**: SSH to host and check system status
3. **Skip failed host**: Re-run with `--limit` excluding failed host
4. **Address issue**: Fix problem on failed host, then re-run just that host

### If service is broken after patching

1. **Immediate**: If critical service down, restore from backup
2. **Investigate**: Check logs for application errors
3. **Rollback packages** (if needed):
   ```bash
   ssh <host>
   apt list --installed | grep <package>
   apt install <package>=<previous-version>
   ```

## Recovery Access

### Physical Console Access

If SSH is unavailable:

1. **Proxmox Web UI**: https://192.168.1.112:8006
2. Navigate to LXC container or VM
3. Click "Console" to access via noVNC
4. Login with root credentials

### IPMI Access (if configured)

For hardware-level access to Proxmox host:
- Access IPMI interface (if configured)
- Use virtual console

## Related Documentation

- Feature Specification: `specs/010-patch-management-reboots/spec.md`
- Implementation Plan: `specs/010-patch-management-reboots/plan.md`
- Tailscale Setup: [docs/runbooks/tailscale-setup.md](tailscale-setup.md)
- Immich Backup/Restore: [docs/runbooks/immich-backup-restore.md](immich-backup-restore.md)

## Troubleshooting Contacts

- **Playbook Issues**: Review tasks.md in feature spec directory
- **Infrastructure Issues**: Check Proxmox logs and system journals
- **Application Issues**: Check service-specific documentation in docs/

## Change Log

- 2025-12-19: Initial runbook created for feature 010
