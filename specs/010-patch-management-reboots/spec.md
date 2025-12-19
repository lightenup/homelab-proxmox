# Feature Specification: Patch Management + Reboots (Monthly Cadence)

**Feature Branch**: `010-patch-management-reboots`  
**Created**: December 19, 2025  
**Status**: Draft  
**Priority**: P1 (Security & Stability)

## Overview

### Goal

Implement a safe, orchestrated monthly patching process for all homelab infrastructure (Proxmox host + LXC containers) with controlled reboot handling and post-update verification. Include documentation for Tailscale mobile access to support remote administration during maintenance windows.

### Current State

- **Infrastructure**: 1 Proxmox host (pve: 192.168.1.112), 4 LXC containers running services
- **OS**: Debian Bookworm on LXCs, Proxmox VE on host
- **Patching**: Manual, ad-hoc updates with no orchestration
- **Reboot handling**: No systematic approach to detecting when reboots are required
- **Verification**: No post-update validation checks
- **Tailscale**: Installed on pve host, subnet routing configured, but no mobile access documentation

**Risk**: Without systematic patching, security vulnerabilities accumulate. Uncoordinated reboots could cause service disruptions or require manual recovery.

### Scope

**In Scope**:
- Monthly patching automation via Ansible for all managed hosts
- Reboot detection and orchestration (LXCs first, host last)
- Explicit gating for Proxmox host reboot (safety stop point)
- Post-update verification (SSH, mounts, HTTP endpoints)
- Human-readable summary report of changes and reboots
- Tailscale mobile access documentation and diagnostics

**Out of Scope**:
- Automated scheduling (manual monthly execution acceptable for v1)
- Full monitoring platform or alerting
- Major version upgrades (dist-upgrade)
- VLAN reconfiguration or router DNS changes
- Creating new secrets or secret management changes

### Non-Goals

- Implementing CI/CD automation for patching
- Building custom monitoring dashboards
- Managing package holds or pinning
- Handling catastrophic failure recovery (separate DR plan)

## Clarifications

### Session 2025-12-19

- Q: In User Story 1, "containers auto-start correctly" after LXC reboot - does this refer to Docker containers inside the LXC or the LXC container itself being started by Proxmox? → A: Both - Docker containers have `restart: always` in compose files (already configured), AND LXCs have `onboot: 1` in Proxmox config
- Q: When verification checks fail after patching (e.g., NFS mount missing), should the playbook fail or continue with warnings? → A: Fail playbook - Stop execution and exit with error on any verification failure (prevents declaring maintenance complete when infrastructure is broken)
- Q: For "safe upgrade mode that doesn't remove packages", which Ansible apt module parameter should be used? → A: `upgrade: safe` - Explicit safe mode (functionally identical to "yes" but clearer intent)
- Q: Should reboot timeout and SSH wait timeout use the same value (300s mentioned in spec)? → A: Split timing - 600s reboot timeout (allows fsck/slow hardware), 300s SSH wait (separates reboot completion from SSH availability)
- Q: Should summary report show only total playbook execution time or include per-host timing? → A: Both - Total playbook wall-clock time + per-host breakdown (helps identify slow hosts for optimization)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Patch All LXCs Safely (Priority: P1)

As a homelab operator, I need to patch all LXC containers monthly with automatic reboot when required, so that security vulnerabilities are addressed without manual intervention per container.

**Why this priority**: Security patches are critical. Multiple containers require efficient batch processing.

**Independent Test**: Run monthly patch playbook against services group, verify all containers update, reboot if needed, and remain accessible.

**Acceptance Scenarios**:

1. **Given** the Ansible inventory is current, **When** I run `ansible-playbook playbooks/update_monthly.yml`, **Then** each LXC in the `services` group performs `apt update && apt upgrade`, reboots only if `/var/run/reboot-required` exists, and SSH remains accessible post-reboot
2. **Given** no updates are available, **When** I re-run the playbook, **Then** it completes with `changed=0` except for "apt cache updated" tasks (idempotent)
3. **Given** a kernel update requires reboot, **When** patching completes, **Then** the LXC automatically reboots (Proxmox `onboot: 1` setting) and Docker containers auto-start via `restart: always` policy in compose files

---

### User Story 2 - Patch Proxmox Host with Safety Gate (Priority: P1)

As a homelab operator, I need to patch the Proxmox host after LXCs with an explicit approval before host reboot, so that I control when the hypervisor goes down.

**Why this priority**: Host reboot affects all services. Operator must control timing and be present to monitor.

**Independent Test**: Patch pve host, verify it doesn't reboot without explicit flag.

**Acceptance Scenarios**:

1. **Given** LXCs are patched, **When** I run patching against pve without reboot flag, **Then** packages update but host does not reboot even if `/var/run/reboot-required` exists
2. **Given** pve requires reboot, **When** I run with `-e allow_host_reboot=true`, **Then** host reboots and comes back with SSH accessible and Proxmox services healthy
3. **Given** no reboot is required, **When** I run with reboot flag, **Then** no reboot occurs and playbook reports "reboot not needed"

---

### User Story 3 - Orchestrated Patching with Summary (Priority: P2)

As a homelab operator, I need a single command that patches services then host with a summary report, so that I understand what changed and what rebooted.

**Why this priority**: Operational efficiency. Single workflow reduces errors and provides audit trail.

**Independent Test**: Run full monthly update, verify order and summary output.

**Acceptance Scenarios**:

1. **Given** I run `update_monthly.yml`, **When** it completes, **Then** services group patched first, proxmox_hosts group patched second, with explicit ordering
2. **Given** updates were applied, **When** playbook finishes, **Then** summary includes: which hosts changed, which rebooted, approximate package counts, total duration, and per-host timing breakdown
3. **Given** some hosts had no updates, **When** reviewing summary, **Then** report clearly indicates "no changes" vs "updates applied" per host

---

### User Story 4 - Post-Update Verification (Priority: P2)

As a homelab operator, I need automated verification after patching that critical mounts and services are functional, so that I catch issues before declaring maintenance complete.

**Why this priority**: Prevents blind assumption that everything works. Early detection of mount or service failures.

**Independent Test**: Run verification tasks, confirm mount and HTTP checks pass.

**Acceptance Scenarios**:

1. **Given** patching completed, **When** verification runs, **Then** it checks SSH connectivity to pve + all LXCs and reports success/failure
2. **Given** Immich depends on NFS, **When** verification runs, **Then** it confirms `/mnt/nas/homelab_immich` exists on pve and bind mount exists in immich LXC
3. **Given** services are deployed, **When** HTTP checks run, **Then** it validates HTTP 200 on immich:2283, homeassistant:8123, proxy:80 and fails playbook if any service is unreachable
4. **Given** AdGuard is not yet deployed, **When** verification runs for services that exist, **Then** all deployed services must pass health checks or playbook fails

---

### User Story 5 - Tailscale Mobile Access Runbook (Priority: P2)

As a homelab operator, I need documentation explaining how to access homelab services from my phone via Tailscale, so that I can monitor or intervene during maintenance windows remotely.

**Why this priority**: Enables remote administration. Common pain point that needs clear docs.

**Independent Test**: Follow runbook, confirm phone can reach pve and services via Tailscale.

**Acceptance Scenarios**:

1. **Given** Tailscale is installed on pve and phone, **When** I follow the runbook, **Then** it explains how to confirm phone is connected to tailnet and subnet routes are approved
2. **Given** I try to use `.local` mDNS names from phone, **When** I check docs, **Then** runbook explains why this doesn't work over Tailscale and recommends Tailscale IP, MagicDNS name, or tailnet FQDN instead
3. **Given** I need to troubleshoot connectivity, **When** I follow checklist, **Then** runbook provides commands for: checking tailscale status, verifying routes, checking ACL tags, and viewing advertised routes
4. **Given** I want to validate Tailscale config, **When** I run optional diagnostics playbook, **Then** it outputs: `tailscale status`, `tailscale ip -4`, advertised routes, and approval status

---

### Edge Cases

- **What happens when apt update fails due to repository issues?** Playbook should fail fast on that host but continue with others if using `serial` batching
- **What happens when a reboot fails to complete (host doesn't come back)?** Playbook should timeout waiting for SSH and report failure; operator intervention required
- **What happens when NFS mount is missing post-reboot?** Verification tasks detect and report failure; operator can investigate before marking maintenance complete
- **What happens when multiple kernel updates accumulate?** Only one reboot needed; `/var/run/reboot-required` is sufficient signal
- **What happens when a container fails to start after reboot?** Verification checks will detect missing HTTP endpoints; operator can check container logs

## Functional Requirements *(mandatory)*

### Patching & Updates

**FR-001**: Provide Ansible playbook `ansible/playbooks/update_monthly.yml` that orchestrates monthly patching in explicit order:
- Play 1: Patch `services` group (all LXCs)
- Play 2: Patch `proxmox_hosts` group (pve only)

**FR-002**: Implement `apt update` + `apt upgrade` using Ansible apt module with `upgrade: safe` parameter (never removes packages, explicit safe mode)

**FR-003**: Support reboot detection using Debian/Ubuntu convention: check for `/var/run/reboot-required` file existence

**FR-004**: Automatically reboot LXC containers when reboot is required without operator confirmation

**FR-005**: Gate Proxmox host reboot behind explicit variable: `-e allow_host_reboot=true`. Default behavior: no host reboot even if required.

### Orchestration

**FR-006**: Execute plays with `serial: 1` or small batches to avoid overwhelming services with simultaneous reboots

**FR-007**: Configure reboot handling with split timeouts: reboot timeout 600 seconds (allows fsck and slow hardware), SSH reconnection wait 300 seconds (validates SSH availability post-boot)

**FR-008**: Implement idempotency: re-running playbook should show minimal changes if packages already updated

### Verification

**FR-009**: Post-update verification must check (all are critical - playbook fails if any check fails):
- SSH connectivity to pve host
- SSH connectivity to all LXCs in services group
- NFS mount existence on pve: `/mnt/nas/homelab_immich`
- Immich bind mount existence: `/mnt/immich` accessible in LXC 101

**FR-010**: Implement HTTP health checks (all are critical - playbook fails if service unreachable):
- Immich: http://192.168.1.213:2283/api/server/ping
- Home Assistant: http://192.168.1.212:8123
- Reverse Proxy: http://192.168.1.211:80

**FR-011**: All verification checks are mandatory and will cause playbook failure if unsuccessful (ensures operator does not declare maintenance complete when infrastructure is broken)

### Reporting

**FR-012**: Generate human-readable summary at end of playbook including:
- List of hosts that had package updates
- List of hosts that rebooted
- Approximate count of packages upgraded per host
- Total playbook wall-clock execution time
- Per-host timing breakdown (helps identify slow hosts)
- Any verification failures

**FR-013**: Use Ansible `debug` tasks or custom callback plugin for summary output

### Tailscale Mobile Access

**FR-014**: Create runbook `docs/runbooks/tailscale-mobile.md` covering:
- Installing Tailscale app on phone
- Confirming phone is in tailnet
- Checking subnet route approval in admin console
- Which address format to use from phone (Tailscale IP / MagicDNS / FQDN)
- Why `.local` mDNS doesn't work over Tailscale
- Troubleshooting checklist

**FR-015**: Create optional diagnostics playbook `ansible/playbooks/tailscale_diagnostics.yml` that outputs:
- `tailscale status`
- `tailscale ip -4`
- Advertised subnet routes
- Route approval status

### Security & Secrets

**FR-016**: Do not introduce new secrets for patching; use existing ansible_user and SSH keys

**FR-017**: Do not commit any secrets to git repository

## Success Criteria *(mandatory)*

**SC-001**: Running `update_monthly.yml` successfully patches all LXCs and pve host with summary showing what changed

**SC-002**: Re-running playbook immediately shows idempotent behavior (changed=0 except cache updates)

**SC-003**: LXC containers automatically reboot when required and return to healthy state within 5 minutes

**SC-004**: Proxmox host does not reboot without explicit `-e allow_host_reboot=true` flag

**SC-005**: Post-update verification detects missing NFS mount or bind mount and fails playbook

**SC-006**: HTTP health checks fail playbook when critical services are unreachable (preventing false declaration of maintenance success)

**SC-007**: Summary report clearly shows which hosts updated, which rebooted, and verification status

**SC-008**: Tailscale mobile runbook enables phone access to homelab services via Tailscale IP or MagicDNS

**SC-009**: Tailscale diagnostics playbook runs and outputs status without requiring root on phone

**SC-010**: Monthly patching workflow completes in under 30 minutes for all hosts (excluding large download times)

## Risks & Mitigations *(mandatory)*

### Risk 1: Proxmox Host Fails to Reboot

**Impact**: High - All services unavailable  
**Likelihood**: Low  
**Mitigation**:
- Test reboot procedure in low-traffic window
- Document IPMI/iLO access for remote recovery
- Keep previous kernel in boot menu as fallback
- Set conservative reboot timeout (10 minutes)

### Risk 2: NFS Mount Not Present After Reboot

**Impact**: High - Immich cannot access photo library  
**Likelihood**: Medium  
**Mitigation**:
- Verification tasks explicitly check mount before declaring success
- Document manual mount recovery procedure
- Consider implementing automatic mount retry in Ansible

### Risk 3: Container Fails to Auto-Start After Reboot

**Impact**: Medium - Specific service unavailable  
**Likelihood**: Low  
**Mitigation**:
- Verification checks detect missing HTTP endpoints
- Document manual recovery: LXC start via `pct start <VMID>`, Docker container start via `docker compose up -d`
- Verify two-layer auto-start: LXC `onboot: 1` in Proxmox config + Docker `restart: always` in compose files

### Risk 4: Kernel Update Causes Hardware Incompatibility

**Impact**: Critical - Host unbootable  
**Likelihood**: Very Low  
**Mitigation**:
- Proxmox uses stable kernel releases
- GRUB keeps previous kernels for rollback
- Test in maintenance window with physical access available

### Risk 5: Tailscale Mobile Access Doesn't Work

**Impact**: Low - Cannot monitor remotely, but homelab still functional  
**Likelihood**: Medium  
**Mitigation**:
- Comprehensive runbook with troubleshooting steps
- ACL configuration documented and tested
- Subnet route approval documented with screenshots

## Assumptions *(mandatory)*

1. All hosts have reliable network connectivity during patching
2. Ansible control node (laptop) remains powered during execution
3. NFS server (Synology NAS) is accessible during patching
4. Operator is available to monitor playbook execution
5. Physical or IPMI access available if Proxmox host fails to reboot
6. Tailscale control plane (tailscale.com) is accessible for authentication
7. Sufficient disk space exists on all hosts for package downloads (~500MB buffer)
8. SSH keys are properly configured for ansible_user on all hosts
9. Proxmox backup retention is configured (VZDump) for pre-patch recovery option
10. All production LXCs have `onboot: 1` configured in Proxmox
11. All Docker services use `restart: always` policy in compose files

## Dependencies *(mandatory)*

**Upstream Dependencies**:
- Debian/Proxmox package repositories must be accessible
- Tailscale control plane for mobile authentication
- NFS server must remain online during patching

**Internal Dependencies**:
- Ansible inventory must be current and accurate
- SSH connectivity must work to all hosts
- Existing ansible_user accounts with sudo privileges
- Vault password file must be accessible for secrets

**Technical Dependencies**:
- Ansible version 2.9+ (for reboot module features)
- Python 3 on all managed hosts
- systemd for service management
- apt package manager (Debian-based systems)

## Out of Scope (Explicit Non-Requirements)

- Automated cron-based scheduling of monthly updates
- Custom monitoring platform or Grafana dashboards
- Package pinning or hold management
- Major version upgrades (e.g., Debian 11 → 12)
- Router configuration or VLAN changes
- DNS server reconfiguration
- Creating new authentication secrets
- Windows or non-Debian system patching
- Database backup automation (covered separately)
- Rollback automation (manual recovery procedures only)

## References

- Debian Security Updates: https://www.debian.org/security/
- Proxmox Updates: https://pve.proxmox.com/wiki/Package_Repositories
- Ansible Reboot Module: https://docs.ansible.com/ansible/latest/collections/ansible/builtin/reboot_module.html
- Tailscale Subnet Routers: https://tailscale.com/kb/1019/subnets/
- Tailscale Mobile App: https://tailscale.com/kb/1017/install/
