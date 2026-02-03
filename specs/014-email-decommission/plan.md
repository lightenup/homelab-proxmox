# Implementation Plan: Decommission Host Email Notifications

**Branch**: `014-email-decommission` | **Date**: December 23, 2025 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/014-email-decommission/spec.md`

## Summary

Migrate Proxmox backup notifications from host-based SMTP (Postfix) to centralized Uptime Kuma push monitoring. Implement safe-by-default decommissioning with discovery phase, reversible disable capability, and optional package removal. Use state machine (`proxmox_backup_email_mode`: enabled|kuma_only|disabled|removed) to control notification behavior.

## Technical Context

**Language/Version**: Bash 5.x (backup script), Ansible 2.14+ (orchestration)
**Primary Dependencies**: curl (Kuma push), Jinja2 (templates), systemctl (service management)
**Storage**: `/etc/proxmox-backup.conf` (configuration), Ansible Vault (credentials)
**Testing**: Manual validation per user story, Ansible check mode, backup dry-runs
**Target Platform**: Debian 12 (Proxmox VE hosts)
**Project Type**: Infrastructure automation (Ansible role modification)
**Performance Goals**: <5s timeout for Kuma push, backup duration unchanged
**Constraints**: Kuma push must not fail backups, reversibility required, idempotent operations
**Scale/Scope**: 2-3 PVE hosts, single proxmox_backup Ansible role, 4 user stories

## Constitution Check

*GATE: Must pass before implementation*

✅ **No constitution violations** - Feature modifies existing role without adding complexity:
- Extends existing proxmox_backup role (established pattern)
- Uses existing config file structure (/etc/proxmox-backup.conf)
- Follows established Ansible patterns (discovery tasks, state-based config)
- No new dependencies beyond curl (already standard on Debian)

## Project Structure

### Documentation (this feature)

```text
specs/014-email-decommission/
├── spec.md              # Feature specification with clarifications (complete)
├── plan.md              # This file - implementation architecture
└── tasks.md             # Task breakdown by user story (next step)
```

### Source Code (repository root)

```text
ansible/
├── group_vars/
│   ├── monitoring/
│   │   └── vars.yml                    # Modify: Add Proxmox Push monitor definition
│   └── proxmox_hosts/
│       ├── vars.yml                    # Add: proxmox_backup_email_mode (URL will be dynamic)
│       └── vault.yml                   # Existing: SMTP credentials (preserved for rollback)
├── roles/
│   ├── uptime_kuma/
│   │   ├── files/
│   │   │   └── configure_uptime_kuma.js # Modify: Support 'push' type and return URL
│   │   └── tasks/
│   │       └── main.yml                # Modify: Register output of configuration script
│   └── proxmox_backup/
│       ├── defaults/
│       │   └── main.yml                # Modify: Add state machine defaults, override flags
│       ├── tasks/
│       │   ├── main.yml                # Modify: Include new task files conditionally
│       │   ├── discovery.yml           # Create: Discovery phase (packages, services, usage detection)
│       │   ├── configure_kuma.yml      # Create: Kuma push configuration
│       │   ├── disable_email.yml       # Create: Disable Postfix, remove SMTP config
│       │   ├── enable_email.yml        # Create: Rollback - re-enable Postfix
│       │   └── remove_packages.yml     # Create: Package removal with confirmation
│       └── templates/
│           ├── proxmox-backup.conf.j2  # Modify: Add KUMA_PUSH_URL, proxmox_backup_email_mode state
│           └── proxmox-config-backup.sh.j2  # Modify: Add send_kuma_push(), gate send_email()
docs/
└── operations/
    ├── backups-proxmox-config.md       # Modify: Add Kuma migration section
    └── backups-proxmox-config-email-decommission.md  # Create: Decommission runbook
```

**Structure Decision**: Extend existing `proxmox_backup` role with conditional task files. State machine in config template controls behavior. Discovery phase in separate task file for clarity. Templates modified to support both email and Kuma modes.
**Automation Decision**: Enhance `uptime_kuma` role to handle Push monitor creation and URL retrieval. Pass this URL to `proxmox_backup` role via Ansible facts or hostvars.

## Architecture Decisions

### 1. State Machine Implementation

**Decision**: Single variable `proxmox_backup_email_mode` controls notification behavior

**States**:
- `enabled`: Email via Postfix (legacy, for rollback testing)
- `kuma_only`: Kuma push enabled, email function present but gated (transition state)
- `disabled`: Postfix stopped, SMTP vars removed, Kuma active (reversible)
- `removed`: Packages uninstalled, Kuma only (requires confirmation)

**Rationale**:
- Eliminates conflicting boolean flags
- Clear progression path matches user story priority
- Single source of truth prevents invalid states
- Ansible templates can easily switch on state value

**Implementation**:
```yaml
# defaults/main.yml
proxmox_backup_email_mode: "kuma_only"  # Safe default: Kuma + email code preserved

# group_vars/proxmox_hosts/vars.yml
proxmox_backup_email_mode: "disabled"   # Operator sets desired state
# proxmox_backup_kuma_push_url is now dynamic, retrieved from Kuma role
```

### 2. Kuma Push URL Automation

**Decision**: Use `uptime_kuma` role to create monitor and export URL

**Mechanism**:
1.  Update `configure_uptime_kuma.js` to accept `push` monitor type.
2.  Script creates/updates monitor and prints the Push URL to stdout (JSON).
3.  Ansible task registers this output.
4.  `proxmox_backup` role uses `hostvars['monitoring']['kuma_monitor_url']` (or similar) to configure the backup script.

**Rationale**:
- Avoids manual copy-paste errors.
- Keeps monitoring config centralized in `uptime_kuma` role.
- Fully automated setup.

### 2. Kuma Push Integration

**Decision**: Best-effort HTTP POST with query parameters, failure doesn't break backup

**API Format**:
```bash
curl -X POST -m 5 "${KUMA_PUSH_URL}?status=up&msg=Backup_completed_successfully" 2>&1 | logger -t proxmox-backup
# Failure detection via exit code: if backup_exit_code != 0, status=down
```

**Error Handling**:
- 5 second timeout (FR-006)
- Silent fallback if URL not configured (FR-005)
- Log all attempts to journald (FR-004)
- Never fail backup on push failure (FR-003)

**Rationale**:
- Uptime Kuma push monitor standard format (confirmed in clarifications)
- Query parameters simpler than JSON POST body
- Timeout prevents hanging backups on network issues
- Best-effort aligns with "monitoring is secondary to backup success"

**Implementation Location**: `proxmox-config-backup.sh.j2` template, new `send_kuma_push()` function

### 3. Discovery Phase

**Decision**: Pre-flight checks before disable/uninstall, abort on conflicts unless overridden

**Discovery Checks** (FR-022 through FR-025):
```yaml
# discovery.yml tasks
- Check installed packages: dpkg -l | grep -E 'postfix|mailutils'
- Check services: systemctl list-unit-files | grep postfix
- Check recent activity: journalctl -u postfix --since "7 days ago" | grep -v proxmox-backup
- Scan for usage: grep -r "sendmail\|/usr/bin/mail" /etc/systemd /usr/local/sbin /opt
```

**Override Mechanism**:
- Default: Abort if non-backup mail usage detected
- Override: `proxmox_backup_force_remove_email: true` (opt-in, FR-009)
- Report: Always display discovery findings in Ansible output

**Rationale**:
- Prevents breaking other services that depend on mail
- Opt-in override prevents accidental damage
- Idempotent: Discovery runs every time, reports cached

**Implementation Location**: New `tasks/discovery.yml` file, included conditionally from `main.yml`

### 4. Reversibility (Rollback Path)

**Decision**: Email function preserved in script, Postfix can be re-enabled via state change

**Rollback Mechanism**:
```yaml
# To rollback: Set mode back to 'enabled'
proxmox_backup_email_mode: "enabled"
# Run playbook → Postfix started, SMTP vars restored from vault
```

**What's Preserved**:
- Email function in backup script (commented/gated, not deleted)
- SMTP credentials in vault (FR-012)
- Postfix config (disabled, not purged until mode=removed)

**What's Reversed**:
- `tasks/enable_email.yml`: Start/enable Postfix
- Restore SMTP vars to `/etc/proxmox-backup.conf`
- Update email_mode state in config

**Rationale**:
- Users may need to revert if Kuma has extended outage
- Testing period (1-2 weeks) before package removal
- No permanent changes until mode=removed with confirmation

**Implementation Location**: New `tasks/enable_email.yml` for rollback logic

### 5. Package Removal (Optional)

**Decision**: Separate confirmation flag required, only after testing period

**Flags**:
```yaml
proxmox_backup_email_mode: "removed"              # State transition
proxmox_backup_uninstall_confirmed: true          # Safety confirmation (FR-015)
```

**Actions** (FR-017 through FR-021):
```bash
apt-get remove --purge postfix mailutils
apt-get autoremove --purge
rm -rf /etc/postfix   # if owned by package
rm -f /etc/msmtprc    # if exists
# DO NOT delete /etc/aliases (system file)
```

**Verification**:
- Check `which mail` returns empty (FR-031)
- Verify backup still works
- Confirm Kuma receives push

**Rationale**:
- Two-flag confirmation prevents accidental uninstall
- Permanent action requires explicit intent
- Discovery runs first to catch conflicts

**Implementation Location**: New `tasks/remove_packages.yml`, only included when mode=removed

### 6. Idempotency

**Decision**: All tasks check current state before acting (FR-027a)

**Examples**:
```yaml
# Check if Postfix already stopped before stopping
- name: Check Postfix state
  systemd:
    name: postfix
  register: postfix_state

- name: Stop Postfix
  systemd:
    name: postfix
    state: stopped
  when: postfix_state.status.ActiveState == "active"

# Check if packages already removed before removing
- name: Check if packages installed
  command: dpkg -l postfix
  register: postfix_installed
  failed_when: false

- name: Remove packages
  apt:
    name: [postfix, mailutils]
    state: absent
    purge: yes
  when: postfix_installed.rc == 0
```

**Rationale**:
- Standard Ansible best practice
- Safe to re-run after failures
- No unexpected side effects
- Operators can apply same config repeatedly

**Implementation Pattern**: All new task files follow this pattern

## Implementation Phases

### Phase 1: Setup & Infrastructure
**Goal**: Prepare role structure and defaults

- Update role defaults with state machine variables
- Create task file stubs (discovery, configure_kuma, disable_email, enable_email, remove_packages)
- Update main.yml to conditionally include new tasks based on state
- Add group_vars for Kuma URL (initially empty/commented)

**Validation**: Ansible syntax check, no functional changes yet

---

### Phase 2: User Story 1 - Kuma Push Integration (P1)
**Goal**: Backup notifications work through Kuma

**Tasks**:
- Modify `proxmox-config-backup.sh.j2`: Add `send_kuma_push()` function
- Add exit code capture and failure detection
- Template KUMA_PUSH_URL from config
- Modify `proxmox-backup.conf.j2`: Add KUMA_PUSH_URL variable
- Update defaults/main.yml: Add proxmox_backup_kuma_push_url default (empty string)
- Create `tasks/configure_kuma.yml`: Deploy config with Kuma URL

**Acceptance**:
- Configure URL in vars, run backup → Kuma shows "Up"
- Break NAS mount, run backup → Kuma shows "Down"
- Remove URL, run backup → No crash, silently skips push

**Deliverable**: Kuma monitoring fully functional, email still works (mode=kuma_only default)

---

### Phase 3: User Story 2 - Safe Email Disable (P2)
**Goal**: Reversible Postfix disable with discovery

**Tasks**:
- Create `tasks/discovery.yml`: Package check, service check, journald scan, usage scan
- Create `tasks/disable_email.yml`: Stop/disable Postfix, remove SMTP vars from config
- Create `tasks/enable_email.yml`: Rollback logic (start Postfix, restore SMTP vars)
- Modify `main.yml`: Include discovery + disable_email when mode=disabled
- Update template: Gate email function behind state check
- Add override flag handling (proxmox_backup_force_remove_email)

**Acceptance**:
- Set mode=disabled → Postfix stopped, backup works with Kuma
- Discovery detects conflict → Abort with warning
- Set mode=enabled → Postfix restarted, email works again

**Deliverable**: Safe disable with discovery, full rollback capability

---

### Phase 4: User Story 3 - Package Removal (P3)
**Goal**: Optional package cleanup with confirmation

**Tasks**:
- Create `tasks/remove_packages.yml`: apt remove --purge, autoremove, cleanup /etc/postfix
- Add confirmation flag check (fail if not set)
- Add verification: which mail, test backup, confirm Kuma
- Update main.yml: Include remove_packages when mode=removed
- Update discovery.yml: Run before removal, abort on conflicts

**Acceptance**:
- mode=removed without confirmation → Error
- mode=removed + confirmation → Packages removed, binaries gone
- Test backup after removal → Success with Kuma push

**Deliverable**: Clean package removal option for long-term cleanup

---

### Phase 5: Documentation & Polish
**Goal**: Complete runbook and operations guide

**Tasks**:
- Create `docs/operations/backups-proxmox-config-email-decommission.md`: Runbook
- Update `docs/operations/backups-proxmox-config.md`: Add migration section
- Document state machine transitions
- Document discovery override scenarios
- Document rollback procedures
- Add troubleshooting section

**Deliverable**: Complete documentation for operators

## File Modifications Summary

### Modified Files (6)
1. `ansible/roles/proxmox_backup/defaults/main.yml` - State machine defaults, Kuma URL, flags
2. `ansible/roles/proxmox_backup/tasks/main.yml` - Conditional task includes
3. `ansible/roles/proxmox_backup/templates/proxmox-backup.conf.j2` - KUMA_PUSH_URL, state var
4. `ansible/roles/proxmox_backup/templates/proxmox-config-backup.sh.j2` - Kuma push function, gated email
5. `ansible/group_vars/proxmox_hosts/vars.yml` - Kuma URL, email_mode config
6. `docs/operations/backups-proxmox-config.md` - Migration section

### New Files (6)
1. `ansible/roles/proxmox_backup/tasks/discovery.yml` - Discovery phase checks
2. `ansible/roles/proxmox_backup/tasks/configure_kuma.yml` - Kuma configuration
3. `ansible/roles/proxmox_backup/tasks/disable_email.yml` - Disable Postfix safely
4. `ansible/roles/proxmox_backup/tasks/enable_email.yml` - Rollback logic
5. `ansible/roles/proxmox_backup/tasks/remove_packages.yml` - Package removal
6. `docs/operations/backups-proxmox-config-email-decommission.md` - Decommission runbook

**Total**: 12 files (6 modified, 6 created)

## Testing Strategy

### Per User Story Testing (Independent)

**US1 - Kuma Push** (MVP):
1. Configure Kuma push URL in vars
2. Run backup manually: `proxmox-config-backup`
3. Check Kuma dashboard: Monitor shows "Up" with timestamp
4. Break NAS mount: `umount /mnt/backup`
5. Run backup (will fail)
6. Check Kuma dashboard: Monitor shows "Down"
7. Restore NAS mount, verify recovery

**US2 - Safe Disable**:
1. Run discovery: `ansible-playbook services.yml --tags proxmox_backup --check`
2. Set `proxmox_backup_email_mode: disabled`
3. Run playbook, verify Postfix stopped
4. Run backup, verify success with Kuma push only
5. Test rollback: Set mode=enabled, run playbook
6. Verify Postfix running, email function works

**US3 - Package Removal**:
1. Run with mode=removed, no confirmation → Verify failure
2. Set confirmation flag, run playbook
3. Verify packages removed: `dpkg -l | grep postfix`
4. Verify binaries gone: `which mail`
5. Run backup, verify success
6. Check Kuma shows success

### Integration Testing
- Full cycle: enabled → kuma_only → disabled → removed
- Verify idempotency: Run playbook 3x, no changes on reruns
- Verify discovery: Install sendmail, run discovery, verify abort
- Verify override: Set force flag, verify proceeds despite warning

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Kuma down during backup | Best-effort push (5s timeout), backup continues |
| Breaking other mail services | Discovery phase detects conflicts, aborts |
| Operator forgets Kuma URL | Graceful fallback, logs warning |
| Need to rollback after package removal | Document: Manual reinstall required (apt install postfix mailutils) |
| Discovery false positive | Override flag available (opt-in, requires acknowledgment) |
| Postfix used by PVE alerts | Discovery detects systemd units, warns operator |

## Dependencies

**External**:
- Uptime Kuma already deployed (Feature 011 complete)
- Kuma push monitor created by operator
- Network connectivity: PVE → Kuma (same LAN)

**Internal**:
- Feature 013 (Proxmox Configuration Backup) complete ✅
- proxmox_backup role exists and functional ✅
- Ansible vault configured with SMTP credentials ✅

## Success Criteria

✅ **US1**: Kuma monitoring works (success/failure push detected)
✅ **US2**: Email safely disabled, Postfix stopped, backup works, rollback tested
✅ **US3**: Packages optionally removed, confirmation required, backup still works
✅ **Discovery**: Detects conflicts, aborts safely
✅ **Idempotency**: Multiple runs produce same result
✅ **Documentation**: Complete runbook with troubleshooting
✅ **Rollback**: Re-enable email works (Postfix restarts, config restored)

## Next Steps

1. Run `/speckit.tasks` to break plan into concrete tasks
2. Implement Phase 2 (US1 - Kuma Push) first → Delivers MVP value
3. Test US1 independently before proceeding to US2
4. Implement Phase 3 (US2 - Safe Disable) → Test rollback
5. Wait 1-2 weeks of Kuma monitoring before US3
6. Implement Phase 4 (US3 - Package Removal) → Optional cleanup
7. Complete Phase 5 (Documentation)
8. Create PR for merge to main
