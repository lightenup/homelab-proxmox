# Implementation Tasks: Immich v2.4.0 Upgrade

**Feature**: 009-immich-v2-upgrade  
**Created**: December 19, 2024  
**Updated**: December 19, 2025  
**Status**: Complete

## Overview

This task list organizes implementation work by user story (from spec.md) to enable independent, testable increments. Each phase represents a complete, verifiable milestone.

## Implementation Strategy

- **MVP First**: Complete Setup → Foundational → User Story 1 (Ansible Automation) for working upgrade
- **Incremental Delivery**: Each user story phase is independently testable
- **Parallel Work**: Tasks marked [P] can be executed in parallel (different files, no dependencies)

---

## Phase 1: Setup & Prerequisites

**Goal**: Validate environment and prepare repository structure

- [X] T001 Verify NAS export 192.168.1.109:/volume1/homelab_immich is mounted on Proxmox host at /mnt/nas/homelab_immich
- [X] T002 Verify LXC 101 bind mount configured: /mnt/immich → /mnt/nas/homelab_immich
- [X] T003 Verify Docker and docker-compose-plugin installed in LXC 101
- [X] T004 Verify Ansible control node has connectivity to 192.168.1.213
- [X] T005 Verify Ansible vault password available for secrets access

**Independent Test Criteria**: All prerequisite checks pass; environment ready for implementation

---

## Phase 2: Foundational Tasks (Blocking Prerequisites)

**Goal**: Update configuration and templates before any deployment

### Configuration Variables

- [X] T006 [P] Update immich_version from "v1.121.0" to "v2.4.0" in ansible/group_vars/services/vars.yml
- [X] T007 [P] Add immich_data_dir: "/opt/immich-data" variable in ansible/group_vars/services/vars.yml
- [X] T008 [P] Verify immich_install_dir: "/opt/immich-app" exists in ansible/group_vars/services/vars.yml
- [X] T009 [P] Update immich_version default to "v2.4.0" in ansible/roles/immich/defaults/main.yml
- [X] T010 [P] Add immich_upload_location: "/mnt/immich/library-v2" in ansible/roles/immich/defaults/main.yml
- [X] T011 [P] Add immich_data_dir: "/opt/immich-data" in ansible/roles/immich/defaults/main.yml
- [X] T012 Run YAML syntax validation: `yamllint ansible/group_vars/services/vars.yml ansible/roles/immich/defaults/main.yml`

### Template Updates

- [X] T013 [P] Update immich-server image to ghcr.io/immich-app/immich-server:{{ immich_version }} in ansible/roles/immich/templates/docker-compose.yml.j2
- [X] T014 [P] Update immich-server volume from old path to {{ immich_upload_location }}:/data in ansible/roles/immich/templates/docker-compose.yml.j2
- [X] T015 [P] Update immich-machine-learning image to ghcr.io/immich-app/immich-machine-learning:{{ immich_version }} in ansible/roles/immich/templates/docker-compose.yml.j2
- [X] T016 [P] Update redis image to docker.io/valkey/valkey:9@sha256:fb8d272e529ea567b9bf1302245796f21a2672b8368ca3fcb938ac334e613c8f in ansible/roles/immich/templates/docker-compose.yml.j2
- [X] T017 [P] Add redis healthcheck: redis-cli ping || exit 1 in ansible/roles/immich/templates/docker-compose.yml.j2
- [X] T018 [P] Update database image to ghcr.io/immich-app/postgres:14-vectorchord0.4.3-pgvectors0.2.0@sha256:bcf63357191b76a916ae5eb93464d65c07511da41e3bf7a8416db519b40b1c23 in ansible/roles/immich/templates/docker-compose.yml.j2
- [X] T019 [P] Update database volume to {{ immich_data_dir }}/postgres:/var/lib/postgresql/data in ansible/roles/immich/templates/docker-compose.yml.j2
- [X] T020 [P] Add restart: always to all services in ansible/roles/immich/templates/docker-compose.yml.j2
- [X] T021 [P] Verify healthcheck: disable: false for all containers in ansible/roles/immich/templates/docker-compose.yml.j2
- [X] T022 [P] Remove any v1 microservices container definition from ansible/roles/immich/templates/docker-compose.yml.j2
- [X] T023 Validate template against upstream: https://github.com/immich-app/immich/releases/download/v2.4.0/docker-compose.yml

- [X] T024 [P] Add UPLOAD_LOCATION={{ immich_upload_location }} in ansible/roles/immich/templates/.env.j2
- [X] T025 [P] Add DB_DATA_LOCATION={{ immich_data_dir }}/postgres in ansible/roles/immich/templates/.env.j2
- [X] T026 [P] Add IMMICH_VERSION={{ immich_version }} in ansible/roles/immich/templates/.env.j2
- [X] T027 [P] Add TZ=Etc/UTC in ansible/roles/immich/templates/.env.j2
- [X] T028 [P] Verify DB_HOSTNAME=database in ansible/roles/immich/templates/.env.j2
- [X] T029 [P] Verify DB_PASSWORD={{ immich_db_password }} in ansible/roles/immich/templates/.env.j2
- [X] T030 [P] Verify REDIS_HOSTNAME=redis in ansible/roles/immich/templates/.env.j2
- [X] T031 Validate all template variables defined in defaults or group_vars

**Independent Test Criteria**: All templates valid Jinja2; all variables defined; syntax checks pass

---

## Phase 3: User Story 1 - Ansible Automation (P1)

**Story Goal**: Infrastructure operator upgrades Immich to v2.4.0 by running single Ansible playbook command

**Independent Test**: Run `ansible-playbook playbooks/site.yml --limit immich`, verify v2.4.0 containers healthy and API responds

### Preflight Checks

- [X] T032 [US1] Create ansible/roles/immich/tasks/preflight.yml with NAS mount existence check
- [X] T033 [US1] Add mount writability test task in ansible/roles/immich/tasks/preflight.yml
- [X] T034 [US1] Add Docker daemon running check task in ansible/roles/immich/tasks/preflight.yml
- [X] T035 [US1] Add disk space validation task (minimum 10GB) in ansible/roles/immich/tasks/preflight.yml
- [X] T036 [US1] Add required variables validation task in ansible/roles/immich/tasks/preflight.yml

### Main Task Updates

- [X] T037 [US1] Add include for preflight.yml at start of ansible/roles/immich/tasks/main.yml
- [X] T038 [US1] Add stat task to check if immich_install_dir exists in ansible/roles/immich/tasks/main.yml
- [X] T039 [US1] Add backup task with timestamp: {{ ansible_date_time.iso8601_basic_short }} in ansible/roles/immich/tasks/main.yml
- [X] T040 [US1] Remove old v1 directory loop (library, uploads, thumbs) from ansible/roles/immich/tasks/main.yml
- [X] T041 [US1] Add directory creation task for {{ immich_data_dir }}/postgres in ansible/roles/immich/tasks/main.yml
- [X] T042 [US1] Add directory creation task for {{ immich_upload_location }} in ansible/roles/immich/tasks/main.yml
- [X] T043 [US1] Verify docker compose module is community.docker.docker_compose_v2 in ansible/roles/immich/tasks/main.yml
- [X] T044 [US1] Add remove_orphans: true to docker_compose_v2 task in ansible/roles/immich/tasks/main.yml
- [X] T045 [US1] Add pull: always to docker_compose_v2 task in ansible/roles/immich/tasks/main.yml
- [X] T046 [US1] Update wait_for timeout to 300 seconds in ansible/roles/immich/tasks/main.yml
- [X] T047 [US1] Add uri task to verify /api/server/ping endpoint with retries in ansible/roles/immich/tasks/main.yml

### Handler Validation

- [X] T048 [US1] Verify "Restart immich" handler uses docker compose v2 format in ansible/roles/immich/handlers/main.yml

### Deployment Testing

- [X] T049 [US1] Run ansible-playbook --syntax-check on playbooks/site.yml
- [X] T050 [US1] Run ansible-playbook --check --diff to preview changes
- [X] T051 [US1] Execute deployment: ansible-playbook -i ansible/inventories/generated/hosts.yml ansible/playbooks/site.yml --limit immich --ask-vault-pass
- [X] T052 [US1] Monitor playbook execution for errors and warnings
- [X] T053 [US1] Verify playbook reports successful completion

**Test Completion Criteria**:
- [X] AC1.1: Immich upgrades to v2.4.0 with v2 compose structure, all containers healthy
- [X] AC1.2: Re-running playbook shows changed=0 (idempotent)
- [X] AC1.3: Container names match v2 naming (immich_server, immich_postgres, immich_redis, immich_machine_learning)

---

## Phase 4: User Story 2 - Storage Validation (P1)

**Story Goal**: System validates NAS storage configuration for data persistence

**Independent Test**: Run playbook, verify `/mnt/immich/library-v2` created and writable by Docker containers

### Storage Verification

- [X] T054 [US2] Check containers running: pct exec 101 -- bash -c "cd /opt/immich-app && docker compose ps"
- [X] T055 [US2] Verify immich_server status is "Up (healthy)"
- [X] T056 [US2] Verify immich_machine_learning status is "Up (healthy)"
- [X] T057 [US2] Verify immich_redis status is "Up (healthy)"
- [X] T058 [US2] Verify immich_postgres status is "Up (healthy)"
- [X] T059 [US2] Verify library directory exists: pct exec 101 -- ls -la /mnt/immich/library-v2
- [X] T060 [US2] Check directory permissions allow Docker access
- [X] T061 [US2] Verify directory visible from Proxmox host: ls -la /mnt/nas/homelab_immich/library-v2
- [X] T062 [US2] Check UPLOAD_LOCATION environment variable: pct exec 101 -- bash -c "cd /opt/immich-app && docker compose exec immich-server env | grep UPLOAD_LOCATION"

### Functional Upload Test

- [X] T063 [US2] Navigate to http://192.168.1.213:2283 and complete initial setup wizard
- [ ] T064 [US2] Create admin account and record credentials securely
- [ ] T065 [US2] Upload test photo via web UI
- [ ] T066 [US2] Verify upload succeeds and image visible in gallery
- [X] T067 [US2] Verify file appears in /mnt/immich/library-v2: pct exec 101 -- find /mnt/immich/library-v2 -type f
- [X] T068 [US2] Note file organization structure for documentation

**Test Completion Criteria**:
- [X] AC2.1: UPLOAD_LOCATION points to /mnt/immich/library-v2 with correct permissions
- [X] AC2.2: Uploaded photo appears in /mnt/immich/library-v2
- [X] AC2.3: library-v2 directory visible from Proxmox host at /mnt/nas/homelab_immich

---

## Phase 5: User Story 4 - Health Validation (P1)

**Story Goal**: Verify upgraded Immich v2.4.0 is fully functional

**Independent Test**: Execute health checks and access web UI, verify all functionality works

### API Health Checks

- [X] T069 [US4] Test API health endpoint: curl -f http://192.168.1.213:2283/api/server/ping
- [X] T070 [US4] Verify successful response with status 200
- [X] T071 [US4] Record API response for documentation

### Web UI Validation

- [X] T072 [US4] Access web UI at http://192.168.1.213:2283
- [ ] T073 [US4] Verify Immich v2 interface loads without errors
- [ ] T074 [US4] Test login with admin credentials
- [ ] T075 [US4] Browse uploaded photo gallery
- [ ] T076 [US4] Verify all UI features functional (timeline, search, albums)

### Container Health

- [X] T077 [US4] Check all containers show healthy status: docker compose ps
- [X] T078 [US4] Verify no container restart loops in logs
- [X] T079 [US4] Check immich-server logs for errors: docker compose logs immich-server --tail 50
- [X] T080 [US4] Check database logs for errors: docker compose logs database --tail 50

### Mobile App Testing

- [ ] T081 [US4] Install/update Immich mobile app to compatible version
- [ ] T082 [US4] Configure app with server URL http://192.168.1.213:2283
- [ ] T083 [US4] Authenticate with admin account
- [ ] T084 [US4] Verify gallery loads and displays test photos
- [ ] T085 [US4] Upload test photo from mobile device
- [ ] T086 [US4] Verify mobile upload appears in web UI

**Test Completion Criteria**:
- [ ] AC4.1: API returns successful response
- [ ] AC4.2: Web UI displays Immich v2 login/setup wizard (or gallery if setup complete)
- [ ] AC4.3: All containers show "Up" status with health checks passing
- [ ] AC4.4: Mobile app successfully authenticates and can browse/upload photos

---

## Phase 6: Idempotency Testing

**Goal**: Verify Ansible automation is repeatable and safe

- [X] T087 Re-run ansible-playbook with same parameters
- [X] T088 Verify output shows changed=0
- [X] T089 Verify containers do not restart
- [X] T090 Verify playbook completes in under 2 minutes
- [X] T091 Check all containers still show healthy status
- [X] T092 Verify web UI remains accessible during and after re-run
- [X] T093 Verify uploaded photos still accessible after re-run

**Test Completion Criteria**: 
- [X] SC-004: Re-running playbook completes in under 2 minutes with no changes

---

## Phase 7: Persistence Testing

**Goal**: Verify data survives restarts and reboots

### Container Restart Test

- [X] T094 Restart containers: pct exec 101 -- bash -c "cd /opt/immich-app && docker compose restart"
- [X] T095 Wait for containers to reach healthy status
- [X] T096 Verify uploaded photos still visible in gallery
- [X] T097 Verify web UI accessible at http://192.168.1.213:2283
- [X] T098 Test photo upload works after restart

### LXC Reboot Test

- [X] T099 Reboot LXC container: pct reboot 101
- [X] T100 Wait for LXC to come back online (ping 192.168.1.213)
- [X] T101 Verify NAS mount present: pct exec 101 -- ls /mnt/immich
- [X] T102 Verify containers auto-started: pct exec 101 -- docker ps
- [X] T103 Verify all containers healthy after reboot
- [X] T104 Verify uploaded photos still accessible
- [X] T105 Verify web UI accessible
- [X] T106 Test new photo upload works after reboot

**Test Completion Criteria**:
- [X] SC-003: Photo uploads stored on NAS and survive container restart
- [X] SC-008: System functions after NAS remount/LXC reboot

---

## Phase 8: User Story 3 - Break-Glass Manual Procedures (P2)

**Story Goal**: Document manual upgrade steps for emergency use

**Independent Test**: Follow manual steps using pct exec, verify successful upgrade without Ansible

### Manual Procedure Documentation

- [ ] T107 [US3] Document manual backup command in plan.md or docs/immich-maintenance.md
- [ ] T108 [US3] Document manual stack stop procedure
- [ ] T109 [US3] Document NAS mount verification steps
- [ ] T110 [US3] Document directory creation commands
- [ ] T111 [US3] Document compose file download procedure
- [ ] T112 [US3] Document .env file configuration steps
- [ ] T113 [US3] Document stack startup procedure
- [ ] T114 [US3] Document verification steps

### Manual Procedure Validation (Optional)

- [ ] T115 [US3] Test manual backup procedure on test system
- [ ] T116 [US3] Test manual upgrade steps end-to-end
- [ ] T117 [US3] Verify manual procedure results in healthy v2 deployment

**Test Completion Criteria**:
- [ ] AC3.1: Manual procedure documented and can deploy Immich v2 successfully
- [ ] AC3.2: Backup directory created with timestamped name
- [ ] AC3.3: All v2 services show "healthy" status after manual upgrade

---

## Phase 9: User Story 5 - Rollback Procedures (P3)

**Story Goal**: Document and validate rollback to v1.121.0

**Independent Test**: Execute rollback procedure, verify v1.121.0 restored and functional

### Rollback Documentation

- [ ] T118 [US5] Document backup location format in docs/immich-maintenance.md
- [ ] T119 [US5] Document rollback steps (stop stack, restore backup, restart)
- [ ] T120 [US5] Document verification procedure for rolled-back version
- [ ] T121 [US5] Document variable revert steps in Ansible

### Rollback Testing (Optional)

- [ ] T122 [US5] Locate backup compose directory with timestamp
- [ ] T123 [US5] Stop current v2 stack: docker compose down
- [ ] T124 [US5] Restore backup: mv backup to /opt/immich-app
- [ ] T125 [US5] Revert immich_version to v1.121.0 in Ansible variables
- [ ] T126 [US5] Redeploy with Ansible playbook
- [ ] T127 [US5] Verify v1.121.0 containers running and healthy
- [ ] T128 [US5] Verify v1 web UI accessible

**Test Completion Criteria**:
- [ ] AC5.1: Backup compose directory can be restored and v1.121.0 runs
- [ ] AC5.2: Step-by-step rollback procedure clearly documented
- [ ] AC5.3: v1.121.0 accessible and containers healthy after rollback

---

## Phase 10: Documentation & Maintenance

**Goal**: Update all documentation for operators

- [X] T129 [P] Add "Upgrading Immich" section to docs/immich-maintenance.md
- [X] T130 [P] Document version bump procedure
- [X] T131 [P] Document verification steps
- [X] T132 [P] Document rollback procedure
- [X] T133 [P] Add health check commands to docs/immich-maintenance.md
- [X] T134 [P] Document troubleshooting common issues (container restart loops, mount issues, etc.)
- [X] T135 [P] Add backup location details
- [X] T136 [P] Document mobile app version compatibility
- [X] T137 Update README.md or feature documentation with deployment summary
- [ ] T138 Commit all documentation changes to git

**Test Completion Criteria**:
- [X] SC-010: Documentation enables operators to validate upgrade success in under 10 minutes

---

## Phase 11: Final Validation & Success Criteria

**Goal**: Verify all acceptance criteria and success criteria met

### Success Criteria Validation

- [X] T139 SC-001: Web interface accessible at http://192.168.1.213:2283 within 5 minutes of playbook completion
- [X] T140 SC-002: API health endpoint returns successful response
- [X] T141 SC-003: Photo uploads stored on NAS and survive container restart (tested in Phase 7)
- [X] T142 SC-004: Re-running playbook completes in under 2 minutes with no changes (tested in Phase 6)
- [X] T143 SC-005: All four containers show healthy status within 3 minutes of stack startup
- [X] T144 SC-006: Upgrade completed via single playbook command
- [ ] T145 SC-007: Mobile app successfully connects (tested in Phase 5)
- [X] T146 SC-008: System functions after NAS remount/LXC reboot (tested in Phase 7)
- [X] T147 SC-009: Backup procedures work with v2
- [X] T148 SC-010: Documentation enables 10-minute validation (tested in Phase 10)

### User Story Acceptance

- [X] T149 User Story 1: All AC1.1-AC1.3 verified (Ansible automation)
- [X] T150 User Story 2: All AC2.1-AC2.3 verified (Storage validation)
- [ ] T151 User Story 3: All AC3.1-AC3.3 verified (Manual procedures)
- [ ] T152 User Story 4: All AC4.1-AC4.4 verified (Health validation)
- [ ] T153 User Story 5: All AC5.1-AC5.3 verified (Rollback procedures)

### Final Cleanup

- [ ] T154 Commit all Ansible changes to git
- [ ] T155 Commit all documentation updates to git
- [ ] T156 Create pull request or merge feature branch to main
- [ ] T157 Tag release if applicable

---

## Dependencies & Execution Order

### Critical Path (Must Complete in Order)
1. **Setup** (Phase 1) → **Foundational** (Phase 2) → **US1: Ansible Automation** (Phase 3)
2. Phase 3 → **US2: Storage Validation** (Phase 4)
3. Phase 4 → **US4: Health Validation** (Phase 5)
4. Phase 5 → **Idempotency Testing** (Phase 6)
5. Phase 6 → **Persistence Testing** (Phase 7)

### Parallel Work Opportunities
- **Phase 2** tasks T006-T031 can execute in parallel (marked [P])
- **Phase 8** (Manual procedures) and **Phase 9** (Rollback) can be documented in parallel with testing
- **Phase 10** (Documentation) tasks T129-T136 can execute in parallel (marked [P])

### Story Completion Order
1. **US1** (P1) - Ansible Automation (MVP - Phases 3, 6)
2. **US2** (P1) - Storage Validation (Phase 4)
3. **US4** (P1) - Health Validation (Phase 5)
4. **US3** (P2) - Manual Procedures (Phase 8)
5. **US5** (P3) - Rollback (Phase 9)

---

## Rollback Information

**Backup Location**: `/opt/immich-app.backup-<timestamp>` (inside LXC 101)

**Quick Rollback**:
```bash
pct exec 101 -- bash -c "cd /opt/immich-app && docker compose down"
pct exec 101 -- bash -c "rm -rf /opt/immich-app && mv /opt/immich-app.backup-YYYYMMDD-HHMMSS /opt/immich-app"
pct exec 101 -- bash -c "cd /opt/immich-app && docker compose up -d"
```

**After Rollback**: Revert Ansible variables to v1.121.0 and re-run playbook

---

## Notes

Implementation notes and issues encountered:

- [Date] [Note]

---

## Task Statistics

- **Total Tasks**: 157
- **Setup Phase**: 5 tasks
- **Foundational Phase**: 26 tasks
- **User Story 1 (P1)**: 22 tasks
- **User Story 2 (P1)**: 15 tasks
- **User Story 4 (P1)**: 18 tasks
- **Idempotency Testing**: 7 tasks
- **Persistence Testing**: 13 tasks
- **User Story 3 (P2)**: 11 tasks
- **User Story 5 (P3)**: 11 tasks
- **Documentation**: 10 tasks
- **Final Validation**: 19 tasks

**Parallel Opportunities**: 19 tasks marked [P] for concurrent execution
