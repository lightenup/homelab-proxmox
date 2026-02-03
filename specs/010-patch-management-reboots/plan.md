# Implementation Plan: Patch Management + Reboots

**Feature Branch**: `010-patch-management-reboots`
**Created**: December 19, 2025
**Status**: Draft

## Overview

This plan implements monthly patch management for the homelab infrastructure with orchestrated reboot handling and verification. The approach follows the speckit constitution: Ansible handles configuration management, verification runs post-update, and documentation provides operational guidance.

**Key Design Decisions**:
- Use Ansible `apt` module for package updates (not shell scripts)
- Implement reboot detection via `/var/run/reboot-required` check
- Gate Proxmox host reboots with explicit `allow_host_reboot` variable
- Serial execution to avoid simultaneous reboots overwhelming services
- Two-tier verification: Infrastructure checks (SSH, mounts) are critical; HTTP service checks are warning-only

## Architecture

### Components

```
ansible/
├── playbooks/
│   ├── update_monthly.yml          # Main orchestration playbook
│   └── tailscale_diagnostics.yml   # Optional diagnostics
├── roles/
│   └── patch_management/
│       ├── defaults/
│       │   └── main.yml            # Timeouts, reboot flags
│       ├── tasks/
│       │   ├── main.yml            # Entry point
│       │   ├── update.yml          # apt update + upgrade
│       │   ├── reboot.yml          # Reboot handling
│       │   └── verify.yml          # Post-update checks
│       └── handlers/
│           └── main.yml            # Reboot handler
docs/
└── runbooks/
    ├── monthly-patching.md         # Operational runbook
    └── tailscale-mobile.md         # Mobile access guide
```

### Data Flow

1. **Orchestration**: `update_monthly.yml` → Play 1 (services) → Play 2 (proxmox_hosts)
2. **Per-Host**: apt update → apt upgrade → check reboot required → conditional reboot → wait for SSH → verify
3. **Reporting**: Gather facts → generate summary → display to operator
4. **Verification**: Infrastructure (SSH, mounts) - critical | Services (HTTP) - warning-only

### Ansible Inventory Integration

Uses existing inventory structure:

```yaml
# ansible/inventories/generated/hosts.yml
all:
  children:
    proxmox_hosts:
      hosts:
        pve:
          ansible_host: 192.168.1.112
    services:
      hosts:
        adguard:
          ansible_host: 192.168.1.210
        proxy:
          ansible_host: 192.168.1.211
        homeassistant:
          ansible_host: 192.168.1.212
        immich:
          ansible_host: 192.168.1.213
```

No inventory changes required.

## Implementation Phases

### Phase 1: Spec & Wiring (US1, US2, US3 foundation)

**Goal**: Create specification, playbook structure, and role skeleton

**Tasks**:
1. Write spec.md with user stories and requirements ✅
2. Write plan.md (this document) ✅
3. Create tasks.md with detailed implementation checklist
4. Create playbook skeleton: `playbooks/update_monthly.yml`
5. Create role skeleton: `roles/patch_management/`
6. Create defaults: timeouts, flags, verification targets
7. Test playbook runs without errors (no-op state)

**Verification**:
- `ansible-playbook playbooks/update_monthly.yml --syntax-check` passes
- `ansible-playbook playbooks/update_monthly.yml --check` completes without failures
- Role defaults define all required variables

**Deliverables**:
- Playbook orchestrates services → proxmox_hosts order
- Role structure follows Ansible best practices
- No functionality implemented yet (scaffolding only)

---

### Phase 2: Patching Role Implementation (US1, US2)

**Goal**: Implement apt update, upgrade, and reboot logic

**Tasks**:
1. Implement `tasks/update.yml`: apt cache update + upgrade tasks
2. Implement `tasks/reboot.yml`: check `/var/run/reboot-required` + conditional reboot
3. Add reboot gating logic: respect `allow_host_reboot` variable for proxmox_hosts
4. Implement wait-for-connection after reboot (600s reboot timeout / 300s SSH wait)
5. Add package change detection using `register` + `changed_when`
6. Test idempotency: run twice, verify second run shows minimal changes

**Verification**:
- Run against services group, verify LXCs update and reboot if needed
- Run against pve without flag, verify no reboot occurs
- Run against pve with `-e allow_host_reboot=true`, verify reboot completes
- Re-run playbook, confirm idempotent (changed=0 except cache)

**Deliverables**:
- LXC containers update and reboot automatically (US1)
- Proxmox host updates but requires explicit reboot flag (US2)
- Package upgrade uses safe mode (no removals)

---

### Phase 3: Orchestration with Ordering (US3)

**Goal**: Implement proper execution order and serial batching

**Tasks**:
1. Configure Play 1 (services): `serial: 1` to avoid simultaneous reboots
2. Configure Play 2 (proxmox_hosts): always runs after services complete
3. Add pre-flight checks: verify Ansible control node connectivity
4. Implement package count tracking (approximate via apt output)
5. Add timestamp tracking for total execution time
6. Test full workflow: services first, then host

**Verification**:
- Run playbook, verify services patched before proxmox_hosts
- Verify only one LXC reboots at a time
- Verify total execution order matches expected sequence
- Confirm timing data collected for summary

**Deliverables**:
- Single playbook orchestrates entire monthly update (US3)
- Execution order prevents cascading failures
- Performance data available for reporting

---

### Phase 4: Verification + Reporting (US3, US4)

**Goal**: Implement post-update verification and summary report

**Tasks**:
1. Implement `tasks/verify.yml`:
   - SSH connectivity check to all hosts (CRITICAL - fails playbook)
   - NFS mount check on pve: `/mnt/nas/homelab_immich` (CRITICAL - fails playbook)
   - Bind mount check on immich: `/mnt/immich` (CRITICAL - fails playbook)
   - HTTP checks (WARNING-ONLY - logs to summary): immich, homeassistant, proxy
2. Add verification failure detection and reporting (two-tier strategy)
3. Implement summary generation:
   - Hosts updated (package count)
   - Hosts rebooted (list)
   - Infrastructure verification status (pass/fail)
   - Service HTTP check warnings
   - Total execution time + per-host breakdown
4. Use `debug` tasks to display summary at end
5. Test verification failure paths (simulate missing mount for critical check, stopped service for warning)

**Verification**:
- Infrastructure checks (SSH, mounts) fail playbook when missing
- HTTP service checks log warnings but playbook continues
- Summary report shows both critical failures and HTTP warnings
- Operator can patch even with services intentionally down

**Deliverables**:
- Post-update verification catches infrastructure issues and fails playbook (US4)
- Service HTTP warnings don't block security patching (operational flexibility)
- Summary report provides complete audit trail (US3)
- Operator has clear success/failure/warning visibility

---

### Phase 5: Tailscale Mobile Runbook (US5)

**Goal**: Document Tailscale mobile access and create diagnostics

**Tasks**:
1. Create `docs/runbooks/tailscale-mobile.md`:
   - Phone app installation steps
   - Verifying tailnet membership
   - Checking subnet route approval
   - Address format explanation (IP vs MagicDNS vs .local)
   - Why mDNS doesn't work over Tailscale
   - Troubleshooting checklist
2. Create `playbooks/tailscale_diagnostics.yml`:
   - Run `tailscale status` on pve
   - Output `tailscale ip -4`
   - Show advertised routes
   - Display route approval status
3. Test runbook: follow steps from phone, verify connectivity
4. Test diagnostics playbook: run and verify output is useful

**Verification**:
- Follow runbook from phone, successfully access pve via Tailscale IP
- Follow runbook, successfully access immich via MagicDNS
- Run diagnostics playbook, output shows current Tailscale state
- Runbook explains why `.local` names don't work from phone

**Deliverables**:
- Operator can access homelab from phone during maintenance (US5)
- Diagnostics playbook provides troubleshooting data
- Documentation prevents common mDNS confusion

---

## Testing Strategy

### Unit Testing (Per-Phase)

Each phase includes verification steps that test components in isolation:
- Phase 1: Syntax check, --check mode validation
- Phase 2: Test patching on single LXC, verify reboot
- Phase 3: Test orchestration order with serial execution
- Phase 4: Test verification with simulated failures
- Phase 5: Test runbook and diagnostics in real environment

### Integration Testing

After all phases complete:
1. Run full `update_monthly.yml` against all hosts
2. Verify execution order: services → proxmox_hosts
3. Verify LXCs reboot automatically when needed
4. Verify pve requires explicit flag for reboot
5. Verify all verification checks pass
6. Verify summary report shows accurate data
7. Verify Tailscale mobile access works from phone

### Idempotency Testing

1. Run playbook twice in succession
2. Verify second run shows `changed=0` except apt cache updates
3. Verify no unnecessary reboots on second run
4. Verify verification checks remain green

### Rollback Testing

Not automated. Manual recovery procedures documented in runbook:
- If apt upgrade fails: manually investigate package issues
- If reboot fails: IPMI/physical access to boot previous kernel
- If mount missing: manual NFS troubleshooting steps

## Risk Mitigation Implementation

### Host Reboot Failure (Risk 1)

**Implementation**:
- Set `async: 600` with `poll: 0` for reboot task
- Use `wait_for_connection` with 10-minute timeout
- Document IPMI access in runbook
- Keep previous kernel in GRUB menu

### NFS Mount Missing (Risk 2)

**Implementation**:
- Explicit mount verification in verify.yml
- Fail playbook if critical mounts missing
- Document manual mount recovery in runbook
- Consider adding mount retry logic (future enhancement)

### Container Auto-Start Failure (Risk 3)

**Implementation**:
- HTTP health checks detect missing services
- Document manual `pct start <VMID>` procedure
- Verify `onboot: 1` setting in Terraform (separate task)

### Kernel Incompatibility (Risk 4)

**Implementation**:
- Test in maintenance window
- Document kernel rollback procedure via GRUB
- Keep physical/IPMI access available

### Tailscale Access Issues (Risk 5)

**Implementation**:
- Comprehensive troubleshooting checklist in runbook
- Diagnostics playbook validates current config
- Screenshots for ACL and route approval

## Technical Decisions

### Why `apt` Module vs Shell Commands?

**Decision**: Use Ansible `apt` module
**Rationale**: Idempotent, cross-distro compatible, better error handling
**Alternatives Considered**: Shell `apt-get` commands (less idempotent)

### Why `/var/run/reboot-required` vs Other Methods?

**Decision**: Check file existence for reboot detection
**Rationale**: Standard Debian/Ubuntu convention, reliable
**Alternatives Considered**: Parse apt output (fragile), check running kernel vs installed (complex)

### Why Explicit Reboot Flag for Host?

**Decision**: Require `-e allow_host_reboot=true` for pve
**Rationale**: Safety gate prevents accidental downtime, operator must consciously approve
**Alternatives Considered**: Always reboot (unsafe), prompt interactively (not automatable)

### Why Serial Execution?

**Decision**: `serial: 1` for services group
**Rationale**: Prevents all services going down simultaneously, easier troubleshooting
**Alternatives Considered**: Parallel execution (faster but riskier)

### Why Two-Tier Verification (Critical vs Warning)?

**Decision**: Infrastructure checks (SSH, mounts) are critical and fail playbook. Service HTTP checks log warnings only.
**Rationale**:
- Infrastructure failures indicate broken systems that need immediate attention
- Services may be intentionally stopped for maintenance or troubleshooting
- Security patching shouldn't be blocked by application-layer issues
- Separates infrastructure health from service availability
**Alternatives Considered**:
- All checks critical (too strict - blocks patching when services down)
- All checks warning (too loose - misses infrastructure failures)
- Conditional checks based on previous state (too complex)

## Success Criteria Mapping

| Criterion | Implementation | Verification Method |
|-----------|----------------|---------------------|
| SC-001 | Playbook orchestrates services → host | Run playbook, check execution order |
| SC-002 | Idempotent tasks with conditional changes | Run twice, verify changed=0 |
| SC-003 | Reboot + wait_for_connection with 5min timeout | Test with kernel update requiring reboot |
| SC-004 | `when: allow_host_reboot is defined` condition | Run without flag, verify no reboot |
| SC-005 | Verification tasks with mount checks | Simulate missing mount, verify detection |
| SC-006 | HTTP checks with `failed_when: false` log warnings | Stop service, verify playbook continues with warning |
| SC-007 | Debug tasks with summary dictionary | Run playbook, review terminal output |
| SC-008 | Tailscale runbook with step-by-step guide | Follow from phone, verify access |
| SC-009 | Diagnostics playbook with no root required | Run playbook, verify output shown |
| SC-010 | Optimized execution with serial batching | Run playbook, verify duration < 30min |

## Timeline Estimate

- **Phase 1**: 1-2 hours (spec, plan, scaffolding)
- **Phase 2**: 2-3 hours (patching logic, reboot handling)
- **Phase 3**: 1-2 hours (orchestration, serial execution)
- **Phase 4**: 2-3 hours (verification, summary reporting)
- **Phase 5**: 1-2 hours (runbook, diagnostics)

**Total**: 7-12 hours implementation + 2-3 hours testing = **10-15 hours**

## Future Enhancements (Post-v1)

- Automated scheduling via systemd timers or cron
- Integration with monitoring platform (Prometheus/Grafana)
- Package hold management for pinned versions
- Email/Slack notifications on completion
- Pre-patch automated backup trigger
- Rollback automation for failed upgrades
- Support for dist-upgrade with major version changes
- Integration with external change management system

## References

- Ansible apt module: https://docs.ansible.com/ansible/latest/collections/ansible/builtin/apt_module.html
- Ansible reboot module: https://docs.ansible.com/ansible/latest/collections/ansible/builtin/reboot_module.html
- Debian reboot-required: https://wiki.debian.org/UnattendedUpgrades
- Tailscale subnet routers: https://tailscale.com/kb/1019/subnets/
- Speckit constitution: `constitution.md`
