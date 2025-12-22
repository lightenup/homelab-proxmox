# Tasks: Proxmox Config Backup Automation

**Feature**: 013-proxmox-config-backup  
**Input**: [spec.md](./spec.md)  
**Created**: December 22, 2025

## Format: `- [ ] [ID] [P?] [Story?] Description with file path`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: User story label (US1, US2, etc.) - only for user story phases
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization, NAS setup, and encryption key preparation

- [ ] T001 Create Ansible role structure: ansible/roles/proxmox_backup/{tasks,handlers,defaults,templates}/main.yml
- [ ] T002 Document NAS share creation in docs/operations/backups-proxmox-config.md (manual prerequisite: /volume1/homelab_backups/proxmox/)
- [ ] T003 Document NFS export configuration in docs/operations/backups-proxmox-config.md (manual prerequisite: export to 192.168.1.112)
- [ ] T004 Document age key generation procedure in docs/operations/backups-proxmox-config.md (manual prerequisite: age-keygen + Bitwarden storage)
- [ ] T005 Create backup playbook wrapper: ansible/playbooks/backup_proxmox.yml
- [ ] T006 Add backup variables to ansible/group_vars/proxmox_hosts.yml (backup schedule, staging paths, NAS mount point)
- [ ] T007 Create script for manual backup execution: scripts/backup/run_proxmox_backup.sh

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story implementation

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T008 Install age encryption tool on Proxmox host via Ansible task in ansible/roles/proxmox_backup/tasks/prerequisites.yml
- [ ] T009 Install zstd compression tool on Proxmox host via Ansible task in ansible/roles/proxmox_backup/tasks/prerequisites.yml
- [ ] T010 Verify NFS mount prerequisites in ansible/roles/proxmox_backup/tasks/prerequisites.yml (nfs-common package)
- [ ] T011 Create staging directory /var/backups/proxmox-staging/ with correct permissions in ansible/roles/proxmox_backup/tasks/setup.yml
- [ ] T012 Implement lock file mechanism in ansible/roles/proxmox_backup/tasks/lock.yml (create /var/run/proxmox-backup.lock, fail if exists)
- [ ] T013 Implement logging setup in ansible/roles/proxmox_backup/tasks/logging.yml (configure /var/log/proxmox-backup.log with rotation)
- [ ] T014 Create systemd journal logging helper in ansible/roles/proxmox_backup/templates/backup_logger.sh.j2

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Recover from Complete Host Failure (Priority: P1) 🎯 MVP

**Tasks**: T015-T028 (14 tasks)

**Goal**: Create basic backup functionality for Proxmox host configuration files

**Independent Test**: Run backup manually, verify /etc/pve/lxc/*.conf, /etc/network/interfaces, and /etc/fstab exist in staging directory before compression

**Acceptance**: Backup collects all critical Proxmox config files to staging directory

### Implementation for User Story 1

- [ ] T015 [P] [US1] Implement Proxmox config collection task in ansible/roles/proxmox_backup/tasks/collect_proxmox.yml (copy /etc/pve/lxc/*.conf to staging)
- [ ] T016 [P] [US1] Collect Proxmox storage configuration in ansible/roles/proxmox_backup/tasks/collect_proxmox.yml (copy /etc/pve/storage.cfg to staging)
- [ ] T017 [P] [US1] Collect network configuration in ansible/roles/proxmox_backup/tasks/collect_network.yml (copy /etc/network/interfaces and /etc/network/interfaces.d/* to staging)
- [ ] T018 [P] [US1] Collect system fstab in ansible/roles/proxmox_backup/tasks/collect_system.yml (copy /etc/fstab to staging)
- [ ] T019 [P] [US1] Collect Tailscale configuration in ansible/roles/proxmox_backup/tasks/collect_tailscale.yml (copy /var/lib/tailscale/* and /etc/default/tailscaled to staging)
- [ ] T020 [P] [US1] Collect rclone configuration if present in ansible/roles/proxmox_backup/tasks/collect_optional.yml (copy /root/.config/rclone/rclone.conf or /etc/rclone/rclone.conf)
- [ ] T021 [US1] Create backup manifest generator in ansible/roles/proxmox_backup/tasks/manifest.yml (generate manifest.txt with file paths, sizes, SHA256 hashes)
- [ ] T022 [US1] Implement tar.zst compression in ansible/roles/proxmox_backup/tasks/compress.yml (create proxmox-backup-YYYYMMDD-HHMMSS.tar.zst from staging)
- [ ] T023 [US1] Implement age encryption in ansible/roles/proxmox_backup/tasks/encrypt.yml (encrypt tar.zst with age, output .tar.zst.age)
- [ ] T024 [US1] Implement NFS mount task in ansible/roles/proxmox_backup/tasks/mount_nas.yml (mount /volume1/homelab_backups/proxmox/ to /mnt/backup-nas/)
- [ ] T025 [US1] Implement backup transfer in ansible/roles/proxmox_backup/tasks/transfer.yml (copy encrypted archive to NFS mount)
- [ ] T026 [US1] Set backup file permissions in ansible/roles/proxmox_backup/tasks/transfer.yml (chmod 640, chown root:root on NAS)
- [ ] T027 [US1] Implement staging cleanup in ansible/roles/proxmox_backup/tasks/cleanup.yml (remove staging directory contents after successful transfer)
- [ ] T028 [US1] Create main backup orchestration task in ansible/roles/proxmox_backup/tasks/main.yml (call all tasks in sequence with error handling)

**Checkpoint**: **MVP COMPLETE** - User Story 1 fully functional, manual backup creates encrypted archive on NAS

---

## Phase 4: User Story 2 - Deterministic Infrastructure Rebuild (Priority: P1)

**Tasks**: T029-T038 (10 tasks)

**Goal**: Add IaC artifact backup (Terraform state, Ansible inventory) to enable infrastructure rebuild

**Independent Test**: Run backup, decrypt archive, verify terraform.tfstate and ansible inventory files present with correct content

**Acceptance**: Restored Terraform state shows zero plan diff, restored Ansible inventory shows zero check-mode changes

### Implementation for User Story 2

- [ ] T029 [P] [US2] Implement Terraform state collection in ansible/roles/proxmox_backup/tasks/collect_terraform.yml (copy terraform/terraform.tfstate and terraform.tfstate.backup from repo location)
- [ ] T030 [P] [US2] Implement Ansible inventory collection in ansible/roles/proxmox_backup/tasks/collect_ansible.yml (copy ansible/inventories/generated/hosts.yml to staging)
- [ ] T031 [P] [US2] Collect Ansible group_vars in ansible/roles/proxmox_backup/tasks/collect_ansible.yml (copy ansible/group_vars/* to staging, excluding secrets.yml if plaintext)
- [ ] T032 [P] [US2] Collect Ansible host_vars if present in ansible/roles/proxmox_backup/tasks/collect_ansible.yml (copy ansible/host_vars/* to staging)
- [ ] T033 [P] [US2] Collect Ansible playbooks in ansible/roles/proxmox_backup/tasks/collect_ansible.yml (copy ansible/playbooks/*.yml to staging)
- [ ] T034 [P] [US2] Collect key Ansible role tasks in ansible/roles/proxmox_backup/tasks/collect_ansible.yml (copy ansible/roles/*/tasks/*.yml to staging)
- [ ] T035 [P] [US2] Collect documentation files in ansible/roles/proxmox_backup/tasks/collect_docs.yml (copy README.md, docs/operations/*.md, docs/runbooks/*.md)
- [ ] T036 [US2] Implement exclusion filters in ansible/roles/proxmox_backup/tasks/collect_ansible.yml (skip .git/, .terraform/, node_modules/, __pycache__/)
- [ ] T037 [US2] Add verification step for deterministic state in ansible/roles/proxmox_backup/tasks/verify_iac.yml (check Terraform state file size > 0, Ansible inventory valid YAML)
- [ ] T038 [US2] Update manifest generation to include IaC artifacts in ansible/roles/proxmox_backup/tasks/manifest.yml

**Checkpoint**: User Story 2 complete - backup includes IaC artifacts, infrastructure can be rebuilt deterministically

---

## Phase 5: User Story 3 - Scheduled Automated Backups (Priority: P1)

**Tasks**: T039-T048 (10 tasks)

**Goal**: Automate backup execution via systemd timer running daily at 2 AM

**Independent Test**: Enable timer, wait 48 hours, verify two dated backup archives exist on NAS with different timestamps

**Acceptance**: Backups run automatically daily, timer survives reboot, rotation maintains 30 daily + 12 monthly backups

### Implementation for User Story 3

- [ ] T039 [P] [US3] Create systemd service unit in ansible/roles/proxmox_backup/templates/proxmox-backup.service.j2 (execute backup playbook as root)
- [ ] T040 [P] [US3] Create systemd timer unit in ansible/roles/proxmox_backup/templates/proxmox-backup.timer.j2 (OnCalendar=daily at 02:00)
- [ ] T041 [US3] Implement systemd unit deployment in ansible/roles/proxmox_backup/tasks/systemd.yml (copy units to /etc/systemd/system/, systemctl daemon-reload)
- [ ] T042 [US3] Enable and start systemd timer in ansible/roles/proxmox_backup/tasks/systemd.yml (systemctl enable --now proxmox-backup.timer)
- [ ] T043 [US3] Implement rotation policy in ansible/roles/proxmox_backup/tasks/rotate.yml (keep 30 daily backups: delete files older than 30 days)
- [ ] T044 [US3] Implement monthly backup preservation in ansible/roles/proxmox_backup/tasks/rotate.yml (keep 12 monthly: preserve first backup of each month)
- [ ] T045 [US3] Implement pre-backup rotation in ansible/roles/proxmox_backup/tasks/main.yml (call rotate task BEFORE backup creation)
- [ ] T046 [US3] Add safety check to rotation in ansible/roles/proxmox_backup/tasks/rotate.yml (preserve at least 1 backup even if policy would delete)
- [ ] T047 [US3] Log rotation actions in ansible/roles/proxmox_backup/tasks/rotate.yml (log deleted filenames, reason, timestamp to /var/log/proxmox-backup.log)
- [ ] T048 [US3] Add idempotency verification in ansible/roles/proxmox_backup/tasks/main.yml (running twice creates new backup with new timestamp only)

**Checkpoint**: User Story 3 complete - backups run automatically, rotation policy enforced, timer persists across reboots

---

## Phase 6: User Story 4 - Verify Backup Integrity Without Restore (Priority: P2)

**Tasks**: T049-T056 (8 tasks)

**Goal**: Provide verification command to decrypt and validate backup archives without full extraction

**Independent Test**: Run verification against latest backup, should decrypt, list contents, verify checksums, complete in <60 seconds

**Acceptance**: Verification detects corrupted backups, validates checksums, reports success/failure clearly

### Implementation for User Story 4

- [ ] T049 [P] [US4] Create verification script in scripts/backup/verify_proxmox_backup.sh (decrypt with age, list tar contents, verify checksums)
- [ ] T050 [P] [US4] Implement post-backup verification in ansible/roles/proxmox_backup/tasks/verify.yml (run verification immediately after backup creation)
- [ ] T051 [US4] Add checksum generation to manifest in ansible/roles/proxmox_backup/tasks/manifest.yml (SHA256 for each file)
- [ ] T052 [US4] Implement checksum validation in scripts/backup/verify_proxmox_backup.sh (compare manifest checksums against archive contents)
- [ ] T053 [US4] Add verification to backup workflow in ansible/roles/proxmox_backup/tasks/main.yml (fail backup if post-verification fails)
- [ ] T054 [US4] Log verification results in ansible/roles/proxmox_backup/tasks/verify.yml (log success/failure, files verified, duration to /var/log/proxmox-backup.log)
- [ ] T055 [US4] Add exit code handling in scripts/backup/verify_proxmox_backup.sh (0=success, 1=decryption failure, 2=checksum mismatch, 3=missing files)
- [ ] T056 [US4] Document verification procedure in docs/operations/backups-proxmox-config.md (command usage, exit codes, troubleshooting)

**Checkpoint**: User Story 4 complete - operators can verify backup integrity independently, post-backup validation ensures archive quality

---

## Phase 7: User Story 5 - Email Notification on Failure (Priority: P3)

**Tasks**: T057-T064 (8 tasks)

**Goal**: Send email notifications when backups fail for early warning

**Independent Test**: Simulate NFS mount failure, trigger backup, verify email received within 5 minutes with error details

**Acceptance**: Failure emails sent with specific error context, optional success emails include metrics

### Implementation for User Story 5

- [ ] T057 [P] [US5] Create email notification template in ansible/roles/proxmox_backup/templates/backup_notification.j2 (subject, body with error/success details)
- [ ] T058 [P] [US5] Implement email sender task in ansible/roles/proxmox_backup/tasks/notify.yml (use existing SMTP credentials from Bitwarden/Kuma setup)
- [ ] T059 [US5] Add failure notification to error handler in ansible/roles/proxmox_backup/tasks/main.yml (catch failures, call notify task with error context)
- [ ] T060 [US5] Include backup metrics in notification in ansible/roles/proxmox_backup/tasks/notify.yml (size, duration, file count, checksum)
- [ ] T061 [US5] Add optional success notification in ansible/roles/proxmox_backup/tasks/notify.yml (configurable via backup_notify_on_success variable, default: false)
- [ ] T062 [US5] Implement notification for specific failure types in ansible/roles/proxmox_backup/tasks/notify.yml (NFS mount failure, encryption failure, disk full, verification failure)
- [ ] T063 [US5] Add notification configuration to ansible/group_vars/proxmox_hosts.yml (SMTP host, port, from/to addresses, enable/disable flags)
- [ ] T064 [US5] Document notification setup in docs/operations/backups-proxmox-config.md (SMTP config, testing procedure, troubleshooting)

**Checkpoint**: User Story 5 complete - operators receive email alerts on backup failures, can optionally enable success notifications

---

## Phase 8: Polish & Cross-Cutting Concerns

**Tasks**: T065-T080 (16 tasks)

**Purpose**: Documentation, edge case handling, security hardening, and final integration

- [ ] T065 [P] Write comprehensive restore runbook in docs/operations/backups-proxmox-config-restore.md (prerequisites, step-by-step for each file type, verification)
- [ ] T066 [P] Document break-glass encryption key recovery in docs/operations/backups-proxmox-config.md (paper backup procedure, quarterly drill)
- [ ] T067 [P] Document manual backup execution in docs/operations/backups-proxmox-config.md (ansible-playbook command, verification steps)
- [ ] T068 [P] Create quickstart guide in docs/operations/backups-proxmox-config.md (one-time setup, schedule configuration, first backup)
- [ ] T069 Add retry logic with exponential backoff for /etc/pve access in ansible/roles/proxmox_backup/tasks/collect_proxmox.yml (max 3 attempts, log warnings)
- [ ] T070 Add NFS mount validation before backup in ansible/roles/proxmox_backup/tasks/mount_nas.yml (check mount exists and writable)
- [ ] T071 Add disk space check before backup in ansible/roles/proxmox_backup/tasks/prerequisites.yml (verify staging has 1GB free, NAS has 200MB free)
- [ ] T072 Implement graceful failure handling in ansible/roles/proxmox_backup/tasks/main.yml (preserve previous backup on failure, no partial archives)
- [ ] T073 Add encryption key fingerprint to backup metadata in ansible/roles/proxmox_backup/tasks/encrypt.yml (store in separate .meta file alongside archive)
- [ ] T074 Implement secret exclusion verification in ansible/roles/proxmox_backup/tasks/collect_ansible.yml (scan for API keys, tokens, passwords in plaintext, fail if found)
- [ ] T075 Add backup size monitoring in ansible/roles/proxmox_backup/tasks/verify.yml (log warning if >200MB, error if >500MB, investigate large artifacts)
- [ ] T076 Document key rotation procedure in docs/operations/backups-proxmox-config.md (generate new key, test decrypt old backup, update Bitwarden, label backup versions)
- [ ] T077 Add integration test playbook in ansible/playbooks/test_backup.yml (run backup, verify archive exists, decrypt, validate contents)
- [ ] T078 Create backup monitoring check for Uptime Kuma in docs/operations/backups-proxmox-config.md (check latest backup timestamp, alert if >36 hours old)
- [ ] T079 Update main README.md with backup feature summary (location, schedule, restore pointer)
- [ ] T080 Add backup role to ansible/playbooks/site.yml (include proxmox_backup role for proxmox_hosts group)

**Checkpoint**: Feature complete - all user stories implemented, documented, integrated, ready for production use

---

## Dependencies

### Story Completion Order

```
Phase 1 (Setup: T001-T007) ← Role structure + manual setup documentation
            ↓
Phase 2 (Foundational: T008-T014) ← Packages, staging, logging (blocking)
            ↓
Phase 3 (US1: T015-T028) ← Basic Backup → MVP COMPLETE HERE  
            ↓
Phase 4 (US2: T029-T038) ← IaC Artifacts (builds on US1 pipeline)
            ↓
Phase 5 (US3: T039-T048) ← Automation (builds on US1+US2 complete backup)
            ↓
Phase 6 (US4: T049-T056) ← Verification (enhances US1-US3 reliability)
            ↓
Phase 7 (US5: T057-T064) ← Notifications (enhances US1-US4 monitoring)
            ↓
Phase 8 (Polish: T065-T080) ← Completes all stories, production-ready
```

**Note**: Manual prerequisites (NAS setup, key generation) documented in Phase 1 must be completed by operator before automated tasks can run.

### User Story Dependencies

- **US1 (Recover from Host Failure)**: No dependencies - can start immediately after Phase 2
- **US2 (IaC Rebuild)**: Depends on US1 (uses same compression/encryption pipeline)
- **US3 (Automation)**: Depends on US1+US2 (automates complete backup)
- **US4 (Verification)**: Depends on US1+US2 (verifies complete backup structure)
- **US5 (Notifications)**: Depends on US1-US4 (notifies on any failure mode)

### Parallel Execution Opportunities

**Phase 2 (Foundational)**: T008-T010 can run in parallel (different package installations)

**Phase 3 (US1 Implementation)**: T015-T020 can run in parallel (collect different config types to staging)

**Phase 4 (US2 Implementation)**: T029-T035 can run in parallel (collect different IaC artifacts)

**Phase 5 (US3 Implementation)**: T039-T040 can run in parallel (systemd service and timer are independent)

**Phase 6 (US4 Implementation)**: T049-T050 can run in parallel (verification script and Ansible task independent)

**Phase 7 (US5 Implementation)**: T057-T058 can run in parallel (template and sender task independent)

**Phase 8 (Polish)**: T065-T068 can run in parallel (documentation tasks), T069-T075 can run in parallel (different edge case handlers)

---

## Implementation Strategy

### MVP Scope (Recommended First Deliverable)

**Goal**: Complete User Story 1 only - prove basic backup works end-to-end

**Deliverables**:
- Phases 1-3 complete (Setup → Foundational → US1 Basic Backup)
- Manual prerequisites completed (NAS share, key generation, NFS test)
- Ansible role structure established
- Manual backup execution functional
- Encrypted archive on NAS with Proxmox configs
- Basic restore documentation

**Timeline**: 1 week (Phase 1: 1 day, Phase 2: 1 day, Phase 3: 2-3 days, plus 1 day for manual setup)

**Validation**: Run backup manually, decrypt archive, verify LXC configs present

### Incremental Delivery

1. **Week 1**: MVP (Phases 1-3: Setup + Foundation + US1) - Basic backup functionality
2. **Week 2**: Phases 4-5 (US2 IaC artifacts + US3 automation) - Complete backup + scheduling
3. **Week 3**: Phases 6-7 (US4 verification + US5 notifications) - Reliability + monitoring
4. **Week 4**: Phase 8 (Polish) - Documentation + edge cases

### Testing Checkpoints

- **After Phase 1 (T007)**: Setup documentation complete
- **After Phase 2 (T014)**: Foundation ready - packages installed, staging created, logging configured
- **After Phase 3 (T028)**: Test manual backup execution → encrypted archive on NAS (MVP COMPLETE)
- **After Phase 4 (T038)**: Test IaC artifact restore → Terraform plan shows zero diff
- **After Phase 5 (T048)**: Wait 48 hours → verify two backups exist, rotation works
- **After Phase 6 (T056)**: Run verification → detects corrupted archive (test with truncated file)
- **After Phase 7 (T064)**: Simulate failure → email received within 5 minutes
- **After Phase 8 (T080)**: Full integration test → backup runs via site.yml, all features working

---

## Validation Criteria

### Per-Story Validation

**US1 (Recover from Host Failure)**:
- ✅ LXC configs (/etc/pve/lxc/*.conf) in archive
- ✅ Network config (/etc/network/interfaces) in archive
- ✅ fstab in archive
- ✅ Archive encrypted with age
- ✅ Archive on NAS with correct permissions

**US2 (Deterministic Infrastructure Rebuild)**:
- ✅ Terraform state in archive
- ✅ Ansible inventory in archive
- ✅ `terraform plan` shows zero diff after restore
- ✅ `ansible-playbook --check` shows no changes after restore

**US3 (Scheduled Automated Backups)**:
- ✅ Systemd timer enabled and running
- ✅ Backup runs daily at 2 AM
- ✅ 30 daily backups retained
- ✅ 12 monthly backups retained
- ✅ Timer survives reboot

**US4 (Verify Backup Integrity)**:
- ✅ Verification script decrypts archive
- ✅ Verification lists all files
- ✅ Verification validates checksums
- ✅ Verification completes in <60 seconds
- ✅ Corrupted archive detected

**US5 (Email Notification on Failure)**:
- ✅ Email sent on NFS mount failure
- ✅ Email sent on encryption failure
- ✅ Email contains specific error details
- ✅ Email received within 5 minutes
- ✅ Optional success email works

### Success Criteria Validation

- **SC-002**: Backup completes in <10 minutes → measure with `time ansible-playbook backup_proxmox.yml`
- **SC-003**: Archive size <100 MB → check with `du -h` on NAS
- **SC-004**: 100% verifiable backups → run verification on all backups in 30-day period
- **SC-005**: Verification <60 seconds → measure with `time ./verify_proxmox_backup.sh`
- **SC-007**: Zero Terraform diff → `terraform plan` after restore shows "No changes"
- **SC-008**: Zero Ansible drift → `ansible-playbook site.yml --check` shows ok=N changed=0
- **SC-009**: Stable NAS storage → 42 backups * ~100 MB = ~4 GB (monitor over 60 days)
- **SC-010**: Zero plaintext secrets → `grep -r 'password\|api_key\|token' staging/` returns nothing

---

## Task Summary

**Total Tasks**: 80 (across 8 phases)

**Phase Breakdown**:
- Phase 1 (Setup): 7 tasks (T001-T007) - role structure, documentation, manual setup docs
- Phase 2 (Foundational): 7 tasks (T008-T014) - packages, staging, logging
- Phase 3 (US1 - Basic Backup): 14 tasks (T015-T028) 🎯 MVP
- Phase 4 (US2 - IaC Artifacts): 10 tasks (T029-T038)
- Phase 5 (US3 - Automation): 10 tasks (T039-T048)
- Phase 6 (US4 - Verification): 8 tasks (T049-T056)
- Phase 7 (US5 - Notifications): 8 tasks (T057-T064)
- Phase 8 (Polish): 16 tasks (T065-T080)

**Parallel Opportunities**: 28 tasks marked [P] can run in parallel (35% of tasks)

**MVP Scope**: 28 tasks (Phases 1-3) = 1 week of work

**Note**: Phase 1 includes documentation for manual prerequisites (NAS setup, key generation, NFS test) that operators must complete before running automated tasks

**Full Feature**: 80 tasks = 3-4 weeks of focused work

**Independent Testing**: Each user story has clear validation criteria and can be tested independently
