# Tasks: Proxmox Config Backup Automation

**Feature**: 013-proxmox-config-backup  
**Input**: [spec.md](./spec.md)  
**Created**: December 22, 2025  
**Architecture**: Choice 3, Option A - Local script runtime (systemd → bash script)

## Format: `- [ ] [ID] [P?] [Story?] Description with file path`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: User story label (US1, US2, etc.) - only for user story phases
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization, NAS setup, and encryption key preparation

- [X] T001 Create Ansible role structure: ansible/roles/proxmox_backup/{tasks,handlers,defaults,templates}/main.yml
- [X] T002 Document NAS share creation in docs/operations/backups-proxmox-config.md (manual prerequisite: /volume1/homelab_backups/proxmox/)
- [X] T003 Document NFS export configuration in docs/operations/backups-proxmox-config.md (manual prerequisite: export to 192.168.1.112)
- [X] T004 Document age key generation procedure in docs/operations/backups-proxmox-config.md (manual prerequisite: age-keygen + Bitwarden storage)
- [X] T005 Create backup playbook wrapper: ansible/playbooks/backup_proxmox.yml
- [X] T006 Add backup variables to ansible/group_vars/proxmox_hosts.yml (backup schedule, staging paths, NAS mount point)
- [X] T007 Create script for manual backup execution: scripts/backup/run_proxmox_backup.sh

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story implementation

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T008 Install age encryption tool on Proxmox host via Ansible task in ansible/roles/proxmox_backup/tasks/prerequisites.yml
- [X] T009 Install zstd compression tool on Proxmox host via Ansible task in ansible/roles/proxmox_backup/tasks/prerequisites.yml
- [X] T010 Verify NFS mount prerequisites in ansible/roles/proxmox_backup/tasks/prerequisites.yml (nfs-common package)
- [X] T011 Create staging directory /var/backups/proxmox-staging/ with correct permissions in ansible/roles/proxmox_backup/tasks/setup.yml
- [X] T012 Deploy backup script template to /usr/local/sbin/proxmox-config-backup (mode 0750) in ansible/roles/proxmox_backup/tasks/deploy_script.yml (script uses flock for locking, strict mode, retry logic for /etc/pve)
- [X] T013 Deploy backup configuration file to /etc/proxmox-backup.conf in ansible/roles/proxmox_backup/tasks/deploy_script.yml (contains vars: NAS mount, age key path, retention policy, repo path)

**Checkpoint**: Foundation ready - script deployed, configuration ready for US1 implementation

---

## Phase 3: User Story 1 - Recover from Complete Host Failure (Priority: P1) 🎯 MVP

**Tasks**: T014-T027 (14 tasks)

**Goal**: Create basic backup functionality for Proxmox host configuration files

**Independent Test**: Run script manually (/usr/local/sbin/proxmox-config-backup), verify encrypted archive on NAS with Proxmox configs

**Acceptance**: Script collects all critical Proxmox config files, compresses, encrypts, and transfers to NAS

**Status**: ✅ **COMPLETE** - All functions implemented and tested successfully (Dec 23, 2025)

### Implementation for User Story 1

- [X] T014 [P] [US1] Implement collection functions in script: collect_proxmox_configs() copies /etc/pve/lxc/*.conf to staging with retry/backoff
- [X] T015 [P] [US1] Add script function: collect /etc/pve/storage.cfg
- [X] T016 [P] [US1] Add script function: collect /etc/network/interfaces and /etc/network/interfaces.d/*
- [X] T017 [P] [US1] Add script function: collect /etc/fstab
- [X] T018 [P] [US1] Add script function: collect Tailscale config (only if INCLUDE_TAILSCALE=true in /etc/proxmox-backup.conf)
- [X] T019 [P] [US1] Add script function: collect rclone config (only if INCLUDE_RCLONE=true in /etc/proxmox-backup.conf)
- [X] T020 [US1] Add script function: generate_manifest() creates manifest.txt with sha256sum
- [X] T021 [US1] Add script function: compress_staging() creates tar.zst with timestamp
- [X] T022 [US1] Add script function: encrypt_archive() uses age with public key
- [X] T023 [US1] Add script function: mount_nas() mounts NFS or verifies mounted
- [X] T024 [US1] Add script function: transfer_to_nas() copies encrypted archive
- [X] T025 [US1] Add script function: set_permissions() chmod 640 root:root on NAS
- [X] T026 [US1] Add script function: cleanup_staging() removes timestamped staging dir
- [X] T027 [US1] Complete script: main() with flock, trap handlers, journald logging, exit codes

**Checkpoint**: **MVP COMPLETE** - User Story 1 fully functional, manual backup creates encrypted archive on NAS

**Test Results** (Dec 23, 2025):
- ✅ Backup ran successfully: `/usr/local/sbin/proxmox-config-backup`
- ✅ Archive created: `proxmox-backup-20251223-092833.tar.zst.age` (1.3 KB)
- ✅ Stored on NAS: `/volume1/homelab_backups/proxmox/`
- ✅ Decryption verified: All files extracted successfully
- ✅ Contents verified: LXC configs (100-104.conf), storage.cfg, interfaces, fstab
- ✅ Cleanup verified: Staging directory removed
- ✅ Timer scheduled: Next run Wed 2025-12-24 00:04:32 CET

---

## Phase 4: User Story 2 - Deterministic Infrastructure Rebuild (Priority: P1)

**Tasks**: T029-T038 (10 tasks)

**Goal**: Add IaC artifact backup (Terraform state, Ansible inventory) to enable infrastructure rebuild

**Independent Test**: Run backup, decrypt archive, verify terraform.tfstate and ansible inventory files present with correct content

**Acceptance**: Restored Terraform state shows zero plan diff, restored Ansible inventory shows zero check-mode changes

### Implementation for User Story 2

- [ ] T028 [US2] Add prerequisite check to script: verify REPO_PATH defined in /etc/proxmox-backup.conf or skip US2
- [ ] T029 [P] [US2] Add script function: collect_terraform() copies terraform/terraform.tfstate* from $REPO_PATH
- [ ] T030 [P] [US2] Add script function: collect_ansible_inventory() copies ansible/inventories/generated/ from $REPO_PATH
- [ ] T031 [P] [US2] Add script function: collect_ansible_group_vars() copies ansible/group_vars/* (excludes secrets.yml)
- [ ] T032 [P] [US2] Add script function: collect_ansible_host_vars() if present
- [ ] T033 [P] [US2] Add script function: collect_ansible_playbooks() copies ansible/playbooks/*.yml
- [ ] T034 [P] [US2] Add script function: collect_ansible_role_tasks() copies ansible/roles/*/tasks/
- [ ] T035 [P] [US2] Add script function: collect_docs() copies README.md, docs/operations/, docs/runbooks/
- [ ] T036 [US2] Add exclusion filters to script: skip .git/, .terraform/, node_modules/, __pycache__/
- [ ] T037 [US2] Add verification to script: check terraform.tfstate size > 0, inventory YAML valid
- [ ] T038 [US2] Update manifest function to include IaC artifacts

**Checkpoint**: User Story 2 complete - backup includes IaC artifacts, infrastructure can be rebuilt deterministically

---

## Phase 5: User Story 3 - Scheduled Automated Backups (Priority: P1)

**Tasks**: T039-T048 (10 tasks)

**Goal**: Automate backup execution via systemd timer running daily at 2 AM

**Independent Test**: Enable timer, wait 48 hours, verify two dated backup archives exist on NAS with different timestamps

**Acceptance**: Backups run automatically daily, timer survives reboot, rotation maintains 30 daily + 12 monthly backups

### Implementation for User Story 3

- [ ] T039 [P] [US3] Create systemd service unit in ansible/roles/proxmox_backup/templates/proxmox-backup.service.j2 (ExecStart=/usr/local/sbin/proxmox-config-backup, Type=oneshot, User=root)
- [ ] T040 [P] [US3] Create systemd timer unit in ansible/roles/proxmox_backup/templates/proxmox-backup.timer.j2 (OnCalendar=daily 02:00, Persistent=true)
- [ ] T041 [US3] Implement systemd unit deployment in ansible/roles/proxmox_backup/tasks/systemd.yml (copy units to /etc/systemd/system/, daemon-reload)
- [ ] T042 [US3] Enable and start systemd timer in ansible/roles/proxmox_backup/tasks/systemd.yml (systemctl enable --now proxmox-backup.timer)
- [ ] T043 [US3] Add rotation function to script: rotate_old_backups() deletes files older than 30 days on NAS
- [ ] T044 [US3] Add to rotation function: preserve first backup of each month (12 monthly retention)
- [ ] T045 [US3] Call rotation function BEFORE backup creation in main() (fail-safe if disk full)
- [ ] T046 [US3] Add safety check to rotation: preserve at least 1 backup even if policy would delete all
- [ ] T047 [US3] Log rotation actions via journald: deleted files, reason, timestamp
- [ ] T048 [US3] Verify idempotency: script can run multiple times (new backup created, rotation reapplied)

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

- [ ] T057 [P] [US5] Add send_email_notification() function to script template (compose subject, body with error/success details, use mail/sendmail command)
- [ ] T058 [P] [US5] Add SMTP configuration to /etc/proxmox-backup.conf (SMTP_HOST, SMTP_PORT, EMAIL_FROM, EMAIL_TO, NOTIFY_ON_SUCCESS variables)
- [ ] T059 [US5] Add failure notification to trap handler in main() (on ERR trap, call send_email_notification with exit code and error context)
- [ ] T060 [US5] Include backup metrics in notification in send_email_notification() (archive size, duration, file count, checksum from manifest)
- [ ] T061 [US5] Add optional success notification in main() (after successful transfer, if NOTIFY_ON_SUCCESS=true, call send_email_notification with success metrics)
- [ ] T062 [US5] Implement notification for specific failure types in send_email_notification() (detect failure type from exit code and last journald entries: NFS mount failure, encryption failure, disk full, verification failure)
- [ ] T063 [US5] Add notification configuration to ansible/group_vars/proxmox_hosts.yml and deploy via config template (SMTP host, port, from/to addresses, enable/disable flags)
- [ ] T064 [US5] Document notification setup in docs/operations/backups-proxmox-config.md (SMTP config in /etc/proxmox-backup.conf, testing with script, troubleshooting mail delivery)

**Checkpoint**: User Story 5 complete - operators receive email alerts on backup failures, can optionally enable success notifications

---

## Phase 8: Polish & Cross-Cutting Concerns

**Tasks**: T065-T080 (16 tasks)

**Purpose**: Documentation, edge case handling, security hardening, and final integration

- [ ] T065 [P] Write comprehensive restore runbook in docs/operations/backups-proxmox-config-restore.md (prerequisites, step-by-step for each file type, verification)
- [ ] T066 [P] Document break-glass encryption key recovery in docs/operations/backups-proxmox-config.md (paper backup procedure, quarterly drill)
- [ ] T067 [P] Document manual backup execution in docs/operations/backups-proxmox-config.md (run /usr/local/sbin/proxmox-config-backup manually, verification steps with --verify flag)
- [ ] T068 [P] Create quickstart guide in docs/operations/backups-proxmox-config.md (one-time setup, Ansible deployment, systemd timer configuration, first backup test)
- [ ] T069 Verify retry logic with exponential backoff for /etc/pve access in collect_proxmox_configs() (already specified in FR-032e: max 3 attempts, log warnings via journald)
- [ ] T070 Add mount validation to mount_nas() function in script template (check mount exists and writable before proceeding with transfer)
- [ ] T071 Add disk space check to prerequisites section in main() (verify staging has 1GB free, NAS mount has 200MB free, fail early if insufficient)
- [ ] T072 Implement graceful failure handling in main() trap handlers (preserve previous backup on failure, clean up partial staging dirs, no partial archives on NAS)
- [ ] T073 Add encryption key fingerprint to backup metadata in encrypt_archive() (store age public key fingerprint in separate .meta file alongside archive)
- [ ] T074 Implement secret exclusion verification in collect_ansible_*() functions (scan collected files for API keys, tokens, passwords in plaintext using regex, fail if found)
- [ ] T075 Add backup size monitoring in main() (log warning via journald if archive >200MB, error if >500MB, investigate large artifacts before transfer)
- [ ] T076 Document key rotation procedure in docs/operations/backups-proxmox-config.md (generate new age keypair, test decrypt old backup with old key, update Bitwarden, update /etc/proxmox-backup.conf, label backup archive versions)
- [ ] T077 Add integration test playbook in ansible/playbooks/test_backup.yml (deploy script + config, run /usr/local/sbin/proxmox-config-backup manually, verify archive exists on NAS, run --verify, validate contents)
- [ ] T078 Create backup monitoring check for Uptime Kuma in docs/operations/backups-proxmox-config.md (check latest backup timestamp on NAS, alert if >36 hours old, integrate with existing monitoring)
- [ ] T079 Update main README.md with backup feature summary (Feature 013 summary, schedule, NAS location, restore pointer to runbook)
- [ ] T080 Add backup role to ansible/playbooks/site.yml (include proxmox_backup role for proxmox_hosts group, ensure deploys script + config + systemd units)

**Checkpoint**: Feature complete - all user stories implemented, documented, integrated, ready for production use

---

## Dependencies

### Story Completion Order

```
Phase 1 (Setup: T001-T007) ← Role structure + manual setup documentation
            ↓
Phase 2 (Foundational: T008-T013) ← Packages, script deployment, config (blocking)
            ↓
Phase 3 (US1: T014-T027) ← Basic Backup → MVP COMPLETE HERE  
            ↓
Phase 4 (US2: T028-T038) ← IaC Artifacts (builds on US1 script functions)
            ↓
Phase 5 (US3: T039-T048) ← Automation (systemd runs script, rotation in script)
            ↓
Phase 6 (US4: T049-T056) ← Verification (--verify flag enhances reliability)
            ↓
Phase 7 (US5: T057-T064) ← Notifications (script-native email on failure)
            ↓
Phase 8 (Polish: T065-T080) ← Completes all stories, production-ready
```

**Note**: Manual prerequisites (NAS setup, age keypair generation) documented in Phase 1 must be completed by operator before script deployment. Script is independent from Ansible at runtime (Choice 3, Option A).

### User Story Dependencies

- **US1 (Recover from Host Failure)**: No dependencies - can implement script functions immediately after Phase 2 deploys script template
- **US2 (IaC Rebuild)**: Depends on US1 (extends script with additional collection functions, uses same compress/encrypt/transfer pipeline)
- **US3 (Automation)**: Depends on US1+US2 (systemd timer runs complete backup script)
- **US4 (Verification)**: Depends on US1+US2 (adds --verify flag to script for post-backup validation)
- **US5 (Notifications)**: Depends on US1-US4 (adds email notification to script trap handlers for any failure mode)

### Parallel Execution Opportunities

**Phase 2 (Foundational)**: T008-T010 can run in parallel (different package installations)

**Phase 3 (US1 Implementation)**: Script functions can be developed/tested in parallel (collect_*, compress_*, encrypt_*, transfer_* are independent until main() orchestration)

**Phase 4 (US2 Implementation)**: IaC collection functions can be developed in parallel (collect_terraform(), collect_ansible_*(), collect_docs() are independent)

**Phase 5 (US3 Implementation)**: T039-T040 can run in parallel (systemd service and timer templates are independent)

**Phase 6 (US4 Implementation)**: verify_backup() function can be developed in parallel with main backup flow (independent code path triggered by --verify flag)

**Phase 7 (US5 Implementation)**: send_email_notification() function and SMTP config can be developed in parallel (independent from backup flow until trap integration)

**Phase 8 (Polish)**: T065-T068 can run in parallel (documentation tasks), T069-T075 can run in parallel (different script function enhancements)

---

## Implementation Strategy

### MVP Scope (Recommended First Deliverable)

**Goal**: Complete User Story 1 only - prove basic backup works end-to-end

**Deliverables**:
- Phases 1-3 complete (Setup → Foundational → US1 Basic Backup)
- Manual prerequisites completed (NAS share, age keypair generation, NFS test)
- Ansible role structure established
- Backup script deployed to /usr/local/sbin/proxmox-config-backup
- Configuration file deployed to /etc/proxmox-backup.conf
- Manual script execution functional (/usr/local/sbin/proxmox-config-backup)
- Encrypted archive on NAS with Proxmox configs
- Basic restore documentation

**Timeline**: 1 week (Phase 1: 1 day, Phase 2: 1 day, Phase 3: 2-3 days, plus 1 day for manual setup and testing)

**Validation**: Run /usr/local/sbin/proxmox-config-backup manually, decrypt archive, verify LXC configs present

### Incremental Delivery

1. **Week 1**: MVP (Phases 1-3: Setup + Foundation + US1) - Basic backup script functional
2. **Week 2**: Phases 4-5 (US2 IaC artifacts + US3 automation) - Complete script + systemd scheduling
3. **Week 3**: Phases 6-7 (US4 verification + US5 notifications) - Verification flag + email alerts
4. **Week 4**: Phase 8 (Polish) - Documentation + edge case handling + integration testing

### Testing Checkpoints

- **After Phase 1 (T007)**: Setup documentation complete, manual prerequisites documented
- **After Phase 2 (T013)**: Foundation ready - script deployed, config deployed, packages installed
- **After Phase 3 (T027)**: Test manual script execution → encrypted archive on NAS with Proxmox configs (MVP COMPLETE)
- **After Phase 4 (T038)**: Test IaC artifact backup → archive contains Terraform state, Ansible inventory
- **After Phase 5 (T048)**: Wait 48 hours → verify systemd timer triggered two backups, rotation works
- **After Phase 6 (T056)**: Run /usr/local/sbin/proxmox-config-backup --verify <path> → exit 0 for valid archive
- **After Phase 7 (T064)**: Simulate failure (unmount NAS) → email received within 5 minutes with error details
- **After Phase 8 (T080)**: Full integration test → script deployed via site.yml, systemd timer running, all features working

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
- ✅ Terraform state in archive (if repo path defined)
- ✅ Ansible inventory in archive (if repo path defined)
- ✅ `terraform plan` shows zero diff after restore
- ✅ `ansible-playbook --check` shows no changes after restore

**US3 (Scheduled Automated Backups)**:
- ✅ Systemd timer enabled and running
- ✅ Backup runs daily at 2 AM
- ✅ 30 daily backups retained
- ✅ 12 monthly backups retained
- ✅ Timer survives reboot

**US4 (Verify Backup Integrity)**:
- ✅ /usr/local/sbin/proxmox-config-backup --verify decrypts archive
- ✅ Verification lists all files from manifest
- ✅ Verification validates SHA256 checksums
- ✅ Verification completes in <60 seconds
- ✅ Corrupted archive detected with specific exit code

**US5 (Email Notification on Failure)**:
- ✅ Email sent on NFS mount failure
- ✅ Email sent on encryption failure
- ✅ Email contains specific error details
- ✅ Email received within 5 minutes
- ✅ Optional success email works (if NOTIFY_ON_SUCCESS=true)

### Success Criteria Validation

- **SC-002**: Backup completes in <10 minutes → measure with `time /usr/local/sbin/proxmox-config-backup`
- **SC-003**: Archive size <100 MB → check with `du -h` on NAS
- **SC-004**: 100% verifiable backups → run `proxmox-config-backup --verify` on all backups in 30-day period
- **SC-005**: Verification <60 seconds → measure with `time /usr/local/sbin/proxmox-config-backup --verify <path>`
- **SC-007**: Zero Terraform diff → `terraform plan` after restore shows "No changes"
- **SC-008**: Zero Ansible drift → `ansible-playbook site.yml --check` shows ok=N changed=0
- **SC-009**: Stable NAS storage → 42 backups * ~100 MB = ~4 GB (monitor over 60 days)
- **SC-010**: Zero plaintext secrets → script's collect_ansible_*() functions exclude secrets.yml and scan for plaintext credentials

---

## Task Summary

**Total Tasks**: 80 (across 8 phases)

**Phase Breakdown**:
- Phase 1 (Setup): 7 tasks (T001-T007) - role structure, documentation, manual setup docs
- Phase 2 (Foundational): 6 tasks (T008-T013) - packages, script deployment, config deployment
- Phase 3 (US1 - Basic Backup): 14 tasks (T014-T027) 🎯 MVP (script functions for Proxmox configs)
- Phase 4 (US2 - IaC Artifacts): 11 tasks (T028-T038) (includes prereq check + IaC collection functions)
- Phase 5 (US3 - Automation): 10 tasks (T039-T048) (systemd runs script, rotation in script)
- Phase 6 (US4 - Verification): 8 tasks (T049-T056) (--verify flag and function)
- Phase 7 (US5 - Notifications): 8 tasks (T057-T064) (script-native email)
- Phase 8 (Polish): 16 tasks (T065-T080) (docs, edge cases, integration)

**Parallel Opportunities**: Script functions can be developed/tested in parallel (collection, compression, encryption, transfer functions are independent until main() orchestration)

**MVP Scope**: 27 tasks (Phases 1-3: T001-T027) = 1 week of work (script template development + testing)

**Note**: Phase 1 includes documentation for manual prerequisites (NAS setup, age keypair generation, NFS test) that operators must complete before script deployment. Architecture uses local bash script runtime (Choice 3, Option A) - systemd runs script, Ansible deploys/configures only.

**Full Feature**: 80 tasks = 3-4 weeks of focused work

**Independent Testing**: Each user story has clear validation criteria and can be tested independently
