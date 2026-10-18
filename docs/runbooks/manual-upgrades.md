# Manual Full System Upgrade Runbook

**Feature**: 010-patch-management-reboots
**Owner**: Homelab Operations
**Last Updated**: December 19, 2025

## Overview

This runbook describes the manual full system upgrade process for non-security updates (features and bugfixes). Unlike monthly security patching which runs automatically, these upgrades require manual execution when you have time to address potential issues.

**⚠️ WARNING**: This upgrades ALL packages including feature changes that may alter behavior or introduce bugs. Only run when you have time to troubleshoot.

## When to Run

- **Schedule**: Quarterly or as needed (not automated)
- **Duration**: 15-30 minutes depending on upgrade size
- **Risk**: Higher than security-only patches - may introduce breaking changes
- **Preparation**: Ensure recent backups exist and you have time to fix issues

## Security-Only vs Full Upgrade

| Aspect | Security-Only (Monthly) | Full Upgrade (Manual) |
|--------|------------------------|----------------------|
| **Updates** | Security patches only | Security + features + bugfixes |
| **Stability** | Very stable | May introduce changes |
| **Risk** | Low | Medium |
| **Schedule** | Automated monthly | Manual as needed |
| **Playbook** | `update_monthly.yml` | `upgrade_manual.yml` |

## Prerequisites

- SSH access to all hosts
- Ansible vault password configured
- **Recent backups verified** (critical for full upgrades)
- Time to monitor and troubleshoot (2-3 hours buffer)
- Consider maintenance window for critical services

## Execution Workflow

### Step 1: Review Available Upgrades (Dry Run)

Always check what will be upgraded first:

```bash
cd /path/to/homelab-proxmox/ansible
ansible-playbook playbooks/upgrade_manual.yml --check
```

This shows available upgrades without applying them.

### Step 2: Upgrade Single Host (Recommended First)

Test on non-critical host first:

```bash
# Upgrade ntfy (test host)
ansible-playbook playbooks/upgrade_manual.yml --limit ntfy

# Verify ntfy is functioning
# Check the web UI, a test publish, logs
```

### Step 3: Upgrade Remaining Services

After validating test host:

```bash
# Upgrade all services with interactive pause
ansible-playbook playbooks/upgrade_manual.yml --limit services

# Or skip confirmation pause
ansible-playbook playbooks/upgrade_manual.yml --limit services --skip-tags pause
```

**What happens**:
1. Backs up current repository configuration
2. Temporarily enables ALL Debian repositories (main, updates, security)
3. Updates apt cache
4. Shows available upgrades
5. Pauses for review (unless --skip-tags pause)
6. Performs full upgrade (apt full-upgrade)
7. Reboots if kernel/libraries updated
8. Verifies system health
9. Restores security-only repository configuration

### Step 4: Upgrade Proxmox Host (Optional)

Only if Proxmox needs feature updates:

```bash
# Dry run first
ansible-playbook playbooks/upgrade_manual.yml --limit proxmox --check

# Real upgrade with reboot permission
ansible-playbook playbooks/upgrade_manual.yml --limit proxmox -e "allow_host_reboot=true"
```

**⚠️ WARNING**: Proxmox host reboot will briefly affect all LXC containers. They will auto-start but services will be unavailable during reboot (~2-3 minutes).

## Post-Upgrade Verification

After each upgrade, verify:

### 1. Service Health Checks

```bash
# Check HTTP endpoints
curl -I http://192.168.1.213:2283  # immich
curl -I http://192.168.1.212:8123  # homeassistant
curl -I http://192.168.1.211:80    # reverse_proxy
```

### 2. Docker Containers (immich)

```bash
ansible immich -m shell -a "docker ps" --become
# Verify all immich containers running
```

### 3. Application Logs

```bash
# Check for errors after upgrade
ansible services -m shell -a "journalctl -xe --since '10 minutes ago' | grep -i error" --become
```

### 4. Repository Configuration

Verify security-only repos restored:

```bash
# Proxmox (DEB822 format)
ssh root@pve.local "cat /etc/apt/sources.list.d/debian.sources"
# Should only show trixie-security

# LXCs (traditional format)
ansible services -m shell -a "cat /etc/apt/sources.list" --become
# Should only show bookworm-security
```

## Rollback Procedures

If upgrade causes issues:

### Option 1: Restore from Backup

Most reliable for critical issues:

```bash
# Stop affected service
pct stop <VMID>

# Restore from backup (adjust date)
# See: docs/immich-backup-restore.md

# Start service
pct start <VMID>
```

### Option 2: Downgrade Specific Package

For isolated package issues:

```bash
ssh <host>
apt list --installed | grep <package>
apt install <package>=<previous-version>
apt-mark hold <package>  # Prevent future upgrades
```

### Option 3: Restore Repository Backup

Revert to pre-upgrade repository config:

```bash
ssh <host>
ls -la /etc/apt/sources.list*.backup*
cp /etc/apt/sources.list.backup-<timestamp> /etc/apt/sources.list
apt update
```

## Common Issues

### Issue: Package conflicts during upgrade

**Symptoms**: apt reports dependency conflicts

**Resolution**:
```bash
ssh <host>
apt update
apt --fix-broken install
apt full-upgrade  # Retry after fixing
```

### Issue: Service won't start after upgrade

**Symptoms**: Systemd service fails after reboot

**Resolution**:
```bash
ssh <host>
systemctl status <service>
journalctl -u <service> -xe
# Check logs for configuration incompatibility
# May need to update service config files
```

### Issue: Repository configuration not restored

**Symptoms**: Still shows full repos after upgrade

**Resolution**:
```bash
ansible-playbook playbooks/configure_security_repos.yml --limit <host>
```

## Maintenance Calendar

Suggested upgrade schedule:

- **Monthly**: Security-only patches (automated with `update_monthly.yml`)
- **Quarterly**: Full system upgrades (manual with `upgrade_manual.yml`)
- **Major Release**: Only after testing in non-production environment

Example timeline:
- **Week 1 of month**: Security patching (automated)
- **Every 3 months**: Full upgrade (manual, scheduled maintenance window)
- **Before major release**: Review Debian/Proxmox release notes

## Related Documentation

- Security Patching: [monthly-patching.md](monthly-patching.md)
- Repository Configuration: `playbooks/configure_security_repos.yml`
- Feature Specification: `specs/010-patch-management-reboots/spec.md`
- Immich Backup: [immich-backup-restore.md](immich-backup-restore.md)

## Change Log

- 2025-12-19: Initial runbook created for manual upgrade process
