# Tasks: Decommission Host Email Notifications

**Feature**: 014-email-decommission | **Branch**: `014-email-decommission`  
**Input**: Design documents from `/specs/014-email-decommission/`  
**Prerequisites**: plan.md ✅, spec.md ✅

**Tests**: No formal tests requested - manual validation per user story acceptance criteria

**Organization**: Tasks grouped by user story to enable independent implementation and testing of each story.

## Format: `- [ ] [ID] [P?] [Story] Description with file path`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- File paths are relative to repository root

## Path Conventions

- **Ansible roles**: `ansible/roles/proxmox_backup/`
- **Documentation**: `docs/operations/`
- **Group vars**: `ansible/group_vars/proxmox_hosts/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Prepare role structure and state machine foundations

- [ ] T001 Update ansible/roles/proxmox_backup/defaults/main.yml with state machine defaults (proxmox_backup_email_mode, proxmox_backup_kuma_push_url)
- [ ] T002 Update ansible/roles/proxmox_backup/defaults/main.yml with override flags (proxmox_backup_force_remove_email, proxmox_backup_uninstall_confirmed)
- [ ] T003 Create ansible/roles/proxmox_backup/tasks/discovery.yml stub (empty file with header comment)
- [ ] T004 Create ansible/roles/proxmox_backup/tasks/configure_kuma.yml stub (empty file with header comment)
- [ ] T005 Create ansible/roles/proxmox_backup/tasks/disable_email.yml stub (empty file with header comment)
- [ ] T006 Create ansible/roles/proxmox_backup/tasks/enable_email.yml stub (empty file with header comment)
- [ ] T007 Create ansible/roles/proxmox_backup/tasks/remove_packages.yml stub (empty file with header comment)
- [ ] T008 Update ansible/roles/proxmox_backup/tasks/main.yml to add conditional includes based on proxmox_backup_email_mode state
- [ ] T009 Add proxmox_backup_kuma_push_url (initially commented out) to ansible/group_vars/proxmox_hosts/vars.yml
- [ ] T010 Verify Ansible syntax with ansible-playbook --syntax-check ansible/playbooks/services.yml

**Checkpoint**: Role structure prepared, no functional changes, syntax valid

---

## Phase 2: User Story 1 - Migrate to Centralized Monitoring (Priority: P1) 🎯 MVP

**Goal**: Backup notifications work through Uptime Kuma push monitoring

**Independent Test**: Configure Kuma URL, run backup, verify Kuma shows "Up", break NAS, verify Kuma shows "Down"

### Implementation for User Story 1

- [ ] T011 [P] [US1] Add KUMA_PUSH_URL variable to ansible/roles/proxmox_backup/templates/proxmox-backup.conf.j2 template
- [ ] T012 [P] [US1] Add send_kuma_push() function to ansible/roles/proxmox_backup/templates/proxmox-config-backup.sh.j2 (curl POST with 5s timeout)
- [ ] T013 [US1] Add exit code capture in ansible/roles/proxmox_backup/templates/proxmox-config-backup.sh.j2 (detect backup failure via $?)
- [ ] T014 [US1] Add Kuma push calls in ansible/roles/proxmox_backup/templates/proxmox-config-backup.sh.j2 (success: status=up, failure: status=down)
- [ ] T015 [US1] Add graceful fallback in send_kuma_push() for empty KUMA_PUSH_URL (silent skip, no error)
- [ ] T016 [US1] Add journald logging in send_kuma_push() for all push attempts (logger -t proxmox-backup)
- [ ] T017 [US1] Implement ansible/roles/proxmox_backup/tasks/configure_kuma.yml to deploy config with Kuma URL from vars
- [ ] T018 [US1] Test: Configure proxmox_backup_kuma_push_url in ansible/group_vars/proxmox_hosts/vars.yml with actual Kuma push URL
- [ ] T019 [US1] Test: Run ansible-playbook ansible/playbooks/services.yml --tags proxmox_backup
- [ ] T020 [US1] Test: Run backup manually (ssh to PVE, run proxmox-config-backup), verify Kuma dashboard shows "Up"
- [ ] T021 [US1] Test: Break NAS mount (umount /mnt/proxmox-backup), run backup, verify Kuma shows "Down"
- [ ] T022 [US1] Test: Comment out KUMA_PUSH_URL in vars, run backup, verify no crash (graceful fallback)

**Checkpoint**: US1 complete - Kuma monitoring fully functional, email still works (default mode=kuma_only)

---

## Phase 3: User Story 2 - Safely Disable Host Email (Priority: P2)

**Goal**: Reversible Postfix disable with discovery phase, rollback capability

**Independent Test**: Set mode=disabled, verify Postfix stopped, backup works with Kuma, test rollback to mode=enabled

### Implementation for User Story 2

- [ ] T023 [P] [US2] Implement discovery checks in ansible/roles/proxmox_backup/tasks/discovery.yml (dpkg -l packages check)
- [ ] T024 [P] [US2] Add service check to ansible/roles/proxmox_backup/tasks/discovery.yml (systemctl list-unit-files grep postfix)
- [ ] T025 [P] [US2] Add journald activity check to ansible/roles/proxmox_backup/tasks/discovery.yml (journalctl -u postfix --since 7 days ago)
- [ ] T026 [P] [US2] Add usage scan to ansible/roles/proxmox_backup/tasks/discovery.yml (grep sendmail|mail in /etc/systemd /usr/local/sbin /opt)
- [ ] T027 [US2] Add discovery results reporting in ansible/roles/proxmox_backup/tasks/discovery.yml (debug msg with findings)
- [ ] T028 [US2] Add conflict detection logic in ansible/roles/proxmox_backup/tasks/discovery.yml (abort if non-backup usage unless force flag)
- [ ] T029 [P] [US2] Implement ansible/roles/proxmox_backup/tasks/disable_email.yml to stop and disable Postfix service
- [ ] T030 [P] [US2] Add SMTP variable removal logic in ansible/roles/proxmox_backup/tasks/disable_email.yml (remove from proxmox-backup.conf)
- [ ] T031 [P] [US2] Add state transition comment in ansible/roles/proxmox_backup/tasks/disable_email.yml (add "Kuma owns notifications" comment to config)
- [ ] T032 [P] [US2] Implement ansible/roles/proxmox_backup/tasks/enable_email.yml for rollback (start/enable Postfix)
- [ ] T033 [P] [US2] Add SMTP variable restoration logic in ansible/roles/proxmox_backup/tasks/enable_email.yml (restore from vault to proxmox-backup.conf)
- [ ] T034 [US2] Update ansible/roles/proxmox_backup/templates/proxmox-config-backup.sh.j2 to gate send_email_notification() behind state check
- [ ] T035 [US2] Update ansible/roles/proxmox_backup/tasks/main.yml to include discovery.yml before disable_email.yml
- [ ] T036 [US2] Update ansible/roles/proxmox_backup/tasks/main.yml to conditionally include disable_email.yml when mode=disabled
- [ ] T037 [US2] Update ansible/roles/proxmox_backup/tasks/main.yml to conditionally include enable_email.yml when mode=enabled
- [ ] T038 [US2] Test: Run discovery phase with ansible-playbook --check mode, verify findings reported
- [ ] T039 [US2] Test: Set proxmox_backup_email_mode: disabled in ansible/group_vars/proxmox_hosts/vars.yml
- [ ] T040 [US2] Test: Run ansible-playbook ansible/playbooks/services.yml --tags proxmox_backup, verify Postfix stopped
- [ ] T041 [US2] Test: Run backup manually, verify success with Kuma push only (no email attempt in logs)
- [ ] T042 [US2] Test: Verify Postfix disabled (systemctl is-enabled postfix returns disabled)
- [ ] T043 [US2] Test rollback: Set proxmox_backup_email_mode: enabled, run playbook
- [ ] T044 [US2] Test rollback: Verify Postfix running (systemctl is-active postfix returns active)
- [ ] T045 [US2] Test rollback: Run backup, verify email sent (check logs for email notification)

**Checkpoint**: US2 complete - Email safely disabled, Postfix stopped, backup works with Kuma, rollback tested and functional

---

## Phase 4: User Story 3 - Clean Package Removal (Priority: P3)

**Goal**: Optional package cleanup with confirmation requirement

**Independent Test**: Set mode=removed + confirmation, verify packages removed, binaries gone, backup still works

### Implementation for User Story 3

- [ ] T046 [P] [US3] Implement confirmation check in ansible/roles/proxmox_backup/tasks/remove_packages.yml (fail if proxmox_backup_uninstall_confirmed not true)
- [ ] T047 [P] [US3] Add package existence check in ansible/roles/proxmox_backup/tasks/remove_packages.yml (dpkg -l postfix/mailutils)
- [ ] T048 [P] [US3] Implement package removal in ansible/roles/proxmox_backup/tasks/remove_packages.yml (apt-get remove --purge postfix mailutils)
- [ ] T049 [P] [US3] Add autoremove in ansible/roles/proxmox_backup/tasks/remove_packages.yml (apt-get autoremove --purge)
- [ ] T050 [P] [US3] Add /etc/postfix cleanup in ansible/roles/proxmox_backup/tasks/remove_packages.yml (remove directory if exists)
- [ ] T051 [P] [US3] Add /etc/msmtprc cleanup in ansible/roles/proxmox_backup/tasks/remove_packages.yml (remove file if exists)
- [ ] T052 [P] [US3] Add binary verification in ansible/roles/proxmox_backup/tasks/remove_packages.yml (check which mail returns empty)
- [ ] T053 [US3] Update ansible/roles/proxmox_backup/tasks/main.yml to include remove_packages.yml when mode=removed
- [ ] T054 [US3] Ensure discovery.yml runs before remove_packages.yml (abort if conflicts detected)
- [ ] T055 [US3] Test without confirmation: Set proxmox_backup_email_mode: removed (no confirmation flag), run playbook
- [ ] T056 [US3] Test without confirmation: Verify playbook fails with clear error message requiring confirmation
- [ ] T057 [US3] Test with confirmation: Set proxmox_backup_uninstall_confirmed: true in vars
- [ ] T058 [US3] Test with confirmation: Run ansible-playbook ansible/playbooks/services.yml --tags proxmox_backup
- [ ] T059 [US3] Test with confirmation: Verify packages removed (dpkg -l | grep postfix returns empty)
- [ ] T060 [US3] Test with confirmation: Verify binaries removed (which mail returns empty or command not found)
- [ ] T061 [US3] Test with confirmation: Verify /etc/postfix directory removed
- [ ] T062 [US3] Test with confirmation: Run backup manually, verify success with Kuma push
- [ ] T063 [US3] Test with confirmation: Check Kuma dashboard shows "Up" status
- [ ] T064 [US3] Test idempotency: Re-run playbook with same settings, verify no errors (already removed)

**Checkpoint**: US3 complete - Packages optionally removed with confirmation, backup still functional, idempotency verified

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, final validation, cross-story integration

- [ ] T065 [P] Create docs/operations/backups-proxmox-config-email-decommission.md runbook
- [ ] T066 [P] Document state machine transitions in docs/operations/backups-proxmox-config-email-decommission.md
- [ ] T067 [P] Document discovery phase procedures in docs/operations/backups-proxmox-config-email-decommission.md
- [ ] T068 [P] Document rollback procedures (enabled mode) in docs/operations/backups-proxmox-config-email-decommission.md
- [ ] T069 [P] Document package removal procedures (removed mode) in docs/operations/backups-proxmox-config-email-decommission.md
- [ ] T070 [P] Add troubleshooting section to docs/operations/backups-proxmox-config-email-decommission.md
- [ ] T071 [P] Document override flag usage (force_remove_email) in docs/operations/backups-proxmox-config-email-decommission.md
- [ ] T072 Update docs/operations/backups-proxmox-config.md to add migration section (link to decommission runbook)
- [ ] T073 Update docs/operations/backups-proxmox-config.md to document Kuma push URL configuration
- [ ] T074 Add state machine diagram to docs/operations/backups-proxmox-config-email-decommission.md (enabled → kuma_only → disabled → removed)
- [ ] T075 Test full state progression: enabled → kuma_only → disabled → removed (all transitions)
- [ ] T076 Test idempotency: Run playbook 3x in each state, verify no unexpected changes
- [ ] T077 Verify all FR requirements met (32 functional requirements from spec.md)
- [ ] T078 Final validation: Check all acceptance scenarios from user stories (11 scenarios total)
- [ ] T079 Code review: Verify all tasks use idempotent patterns (state checks before actions)
- [ ] T080 Final commit and prepare pull request for merge to main

**Final Checkpoint**: All user stories complete, documentation finished, ready for production deployment

---

## Summary

**Total Tasks**: 80  
**MVP Scope** (Phase 2 - US1): Tasks T001-T022 (22 tasks)  
**Full Feature** (All Phases): Tasks T001-T080 (80 tasks)

### Task Breakdown by Phase

| Phase | Task Range | Count | Purpose |
|-------|------------|-------|---------|
| Phase 1: Setup | T001-T010 | 10 | Infrastructure preparation |
| Phase 2: US1 (MVP) | T011-T022 | 12 | Kuma push integration |
| Phase 3: US2 | T023-T045 | 23 | Safe email disable with rollback |
| Phase 4: US3 | T046-T064 | 19 | Optional package removal |
| Phase 5: Polish | T065-T080 | 16 | Documentation and final validation |

### User Story Mapping

- **User Story 1 (P1)**: T011-T022 (12 tasks) - Kuma push monitoring
- **User Story 2 (P2)**: T023-T045 (23 tasks) - Safe disable with discovery
- **User Story 3 (P3)**: T046-T064 (19 tasks) - Package removal

### Parallel Opportunities

**Phase 2 (US1)**: Tasks T011-T012 can run in parallel (template modifications, different files)

**Phase 3 (US2)**: Tasks T023-T026 can run in parallel (discovery checks, separate aspects), Tasks T029-T033 can run in parallel (disable/enable implementations, different files)

**Phase 4 (US3)**: Tasks T046-T052 can run in parallel (remove_packages.yml implementation, different logical sections)

**Phase 5 (Polish)**: Tasks T065-T071 can run in parallel (documentation sections, different files)

### Dependencies

**Critical Path**:
1. Phase 1 (Setup) → All other phases depend on this
2. Within each user story: Implementation tasks must complete before testing tasks
3. Phase 3 (US2) depends on Phase 2 (US1) being complete (needs Kuma functional for testing)
4. Phase 4 (US3) depends on Phase 3 (US2) being complete (needs email disabled before removal)
5. Phase 5 (Polish) depends on all user stories complete (documents final state)

### Independent Testing

Each user story can be tested independently:
- **US1**: Test Kuma push without disabling email
- **US2**: Test disable/enable with Kuma already working
- **US3**: Test package removal after email disabled for 1-2 weeks

### Deployment Strategy

**Recommended MVP**: Phase 1 + Phase 2 (T001-T022)
- Delivers core value: Kuma monitoring functional
- No breaking changes: Email still works
- Low risk: Additive change only
- Can be deployed and tested in production before proceeding

**Incremental Rollout**:
1. Deploy US1 (Kuma push) → Test 1-2 weeks
2. Deploy US2 (disable email) → Test 1-2 weeks
3. Deploy US3 (remove packages) → Long-term cleanup (optional)

---

## Implementation Notes

### State Machine Transitions

Valid transitions:
- `enabled` → `kuma_only` (add Kuma, keep email)
- `kuma_only` → `disabled` (stop Postfix, Kuma only)
- `disabled` → `removed` (remove packages with confirmation)
- `disabled` → `enabled` (rollback: restart Postfix)
- `removed` → N/A (permanent: manual reinstall required)

### Override Flags

- `proxmox_backup_force_remove_email: true` - Override discovery conflicts (opt-in)
- `proxmox_backup_uninstall_confirmed: true` - Confirm package removal (opt-in)

### Validation Checklist

Before marking complete, verify:
- ✅ All 32 functional requirements from spec.md implemented
- ✅ All 11 acceptance scenarios tested
- ✅ State machine transitions work (enabled → kuma_only → disabled → removed)
- ✅ Rollback works (disabled → enabled)
- ✅ Discovery phase detects conflicts
- ✅ Idempotency verified (multiple runs safe)
- ✅ Kuma push doesn't fail backups
- ✅ Documentation complete with runbook
