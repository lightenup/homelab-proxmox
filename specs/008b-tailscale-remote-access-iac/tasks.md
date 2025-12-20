# Tasks: Tailscale Remote Access IaC

**Input**: Specification from `specs/008b-tailscale-remote-access-iac/spec.md`
**Plan**: Implementation approach in `specs/008b-tailscale-remote-access-iac/plan.md`
**Feature**: Make the Tailscale subnet-router + ACL setup fully reproducible from the repo
**Context**: Working Tailscale setup exists on pve; codifying it as Infrastructure as Code

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4, US5)
- All tasks include exact file paths

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create role structure, initial playbook scaffolding, and ensure constitution compliance (secrets protection)

- [ ] T001 Create Ansible role directory structure at ansible/roles/tailscale_router/ with subdirectories: tasks/, handlers/, defaults/, templates/, meta/
- [ ] T002 Create role metadata file ansible/roles/tailscale_router/meta/main.yml with role dependencies (none)
- [ ] T003 [P] Create main playbook ansible/playbooks/tailscale.yml targeting proxmox_hosts group
- [ ] T004 [P] Create role defaults file ansible/roles/tailscale_router/defaults/main.yml with default variables (tailscale_subnet_route: "192.168.1.0/24", tailscale_auth_key: omitted)
- [ ] T005 [P] **[CONSTITUTION COMPLIANCE]** Verify .gitignore contains patterns blocking all common secret files: **/vault.yml, **/*secret*.yml, **/*_secrets.yml, **/tailscale_auth_key*, **/*.key, **/*.pem (add patterns if missing, fail with error if .gitignore doesn't exist) - MUST execute before Phase 2 auth handling per Constitution Principle II

---

## Phase 2: User Story 1 - Rebuild Proxmox from Scratch (Priority: P1) 🎯 MVP

**Goal**: Single playbook run restores full Tailscale subnet router functionality on fresh Proxmox install

**Independent Test**: Run `ansible-playbook playbooks/tailscale.yml` against pve; verify IP forwarding persisted, subnet routes advertised, remote LAN access works from mobile

### Implementation for User Story 1

- [ ] T006 [P] [US1] Create task file ansible/roles/tailscale_router/tasks/install.yml to install Tailscale package (apt: name=tailscale state=present) with check for existing installation
- [ ] T007 [P] [US1] Create task file ansible/roles/tailscale_router/tasks/service.yml to ensure tailscaled service is enabled and running (systemd: name=tailscaled enabled=yes state=started)
- [ ] T008 [P] [US1] Create task file ansible/roles/tailscale_router/tasks/check_auth.yml to detect Tailscale authentication status (command: tailscale status) and register result
- [ ] T009 [US1] Create task file ansible/roles/tailscale_router/tasks/authenticate.yml to handle authentication logic: skip if already authenticated (check_auth result indicates connected), use tailscale_auth_key variable if provided (via ansible-vault or --extra-vars), otherwise fail with message: "ERROR: Tailscale not authenticated. Either: (1) Run 'tailscale up' manually on pve, or (2) Provide tailscale_auth_key variable via ansible-vault or --extra-vars. Generate auth key at https://login.tailscale.com/admin/settings/keys"
- [ ] T010 [P] [US1] Create template ansible/roles/tailscale_router/templates/99-tailscale-subnet-router.conf.j2 for sysctl configuration with IPv4 and IPv6 forwarding
- [ ] T011 [US1] Create task file ansible/roles/tailscale_router/tasks/ip_forwarding.yml to manage IP forwarding: deploy template to /etc/sysctl.d/99-tailscale-subnet-router.conf, use ansible.builtin.template module (automatically handles idempotency - only changes if content differs), notify sysctl reload handler on changes
- [ ] T012 [US1] Create handler ansible/roles/tailscale_router/handlers/main.yml to reload sysctl (command: sysctl --system) when config file changes
- [ ] T013 [US1] Create task file ansible/roles/tailscale_router/tasks/subnet_routes.yml to configure subnet route advertisement: check current advertised routes via 'tailscale status --json | jq -r .Self.AllowedIPs[]' and register result, run 'tailscale up --advertise-routes=192.168.1.0/24' only if 192.168.1.0/24 not already advertised, use changed_when to report true idempotency
- [ ] T014 [US1] Create main task file ansible/roles/tailscale_router/tasks/main.yml that orchestrates execution order: install → service → check_auth → authenticate → ip_forwarding → subnet_routes
- [ ] T015 [US1] Update playbook ansible/playbooks/tailscale.yml to include tailscale_router role with proper host targeting and any necessary variables

**Checkpoint**: User Story 1 complete - playbook can configure full Tailscale subnet router on pve

---

## Phase 3: User Story 3 - Verify Tailscale Configuration (Priority: P2)

**Goal**: Diagnostic tasks provide structured Ansible output showing configuration state with pass/fail per check

**Independent Test**: Run diagnostic tasks; verify output shows Tailscale status, IP, advertised routes, IP forwarding (IPv4/IPv6) with clear ok/failed status per check

### Implementation for User Story 3

- [ ] T016 [P] [US3] Create task file ansible/roles/tailscale_router/tasks/verify_tailscale_status.yml to check Tailscale connection status (command: tailscale status), use ansible.builtin.assert with condition that output contains 'logged in' or similar connection indicator, with fail_msg showing current status
- [ ] T017 [P] [US3] Create task file ansible/roles/tailscale_router/tasks/verify_tailscale_ip.yml to get Tailscale IP address (command: tailscale ip -4) and display it
- [ ] T018 [P] [US3] Create task file ansible/roles/tailscale_router/tasks/verify_routes.yml to verify advertised routes include 192.168.1.0/24: check via 'tailscale status --json | jq -r .Self.AllowedIPs[]', use ansible.builtin.assert that 192.168.1.0/24 appears in output, with fail_msg showing current advertised routes vs expected
- [ ] T019 [P] [US3] Create task file ansible/roles/tailscale_router/tasks/verify_ipv4_forwarding.yml to check IPv4 forwarding (command: sysctl -n net.ipv4.ip_forward), use ansible.builtin.assert that value equals '1', with fail_msg: "IPv4 forwarding disabled: current={{ result.stdout }}, expected=1"
- [ ] T020 [P] [US3] Create task file ansible/roles/tailscale_router/tasks/verify_ipv6_forwarding.yml to check IPv6 forwarding (command: sysctl -n net.ipv6.conf.all.forwarding), use ansible.builtin.assert that value equals '1', with fail_msg: "IPv6 forwarding disabled: current={{ result.stdout }}, expected=1"
- [ ] T021 [P] [US3] Create task file ansible/roles/tailscale_router/tasks/verify_persistence.yml to verify /etc/sysctl.d/99-tailscale-subnet-router.conf exists and contains correct IPv4/IPv6 forwarding values, use ansible.builtin.stat and ansible.builtin.slurp modules, assert file exists and content matches expected configuration, with fail_msg showing missing or incorrect values
- [ ] T022 [US3] Create verification playbook ansible/playbooks/verify_tailscale.yml that runs all verify_* tasks from tailscale_router role with tags for selective execution
- [ ] T023 [US3] Update ansible/roles/tailscale_router/tasks/main.yml to support tags: install, configure, verify (allowing selective execution via --tags)

**Checkpoint**: User Story 3 complete - diagnostic playbook provides structured verification output

---

## Phase 4: User Story 2 - Understand ACL Identity Configuration (Priority: P1)

**Goal**: Clear documentation prevents hours of troubleshooting GitHub identity format mistakes

**Independent Test**: Review docs/runbooks/tailscale-setup.md; verify it has 3+ warnings about GitHub identity format, example ACL showing xxx@github format, troubleshooting section addressing identity mismatch

### Implementation for User Story 2

- [ ] T024 [US2] Create runbook docs/runbooks/tailscale-setup.md with overview section explaining Tailscale subnet router purpose and architecture
- [ ] T025 [US2] Add "Prerequisites" section to docs/runbooks/tailscale-setup.md: Tailscale account, GitHub auth configured, admin console access, pve SSH access
- [ ] T026 [US2] Add "Quick Start" section to docs/runbooks/tailscale-setup.md: how to run ansible-playbook playbooks/tailscale.yml with example commands
- [ ] T027 [US2] Add "Configuration" section to docs/runbooks/tailscale-setup.md documenting role variables: tailscale_subnet_route, tailscale_auth_key (optional), how to set via group_vars or command line
- [ ] T028 [US2] Add "⚠️ CRITICAL: GitHub Identity Format" section to docs/runbooks/tailscale-setup.md with prominent warnings, examples showing xxx@github vs email, symptoms of misconfiguration (denied access despite routes working)
- [ ] T029 [US2] Add "Finding Your GitHub Identity" section to docs/runbooks/tailscale-setup.md with step-by-step instructions: navigate to Tailscale admin → Settings → Users, identify correct format
- [ ] T030 [US2] Review existing docs/tailscale-acl.example.json and add inline comments: (1) header comment marking file as EXAMPLE/TEMPLATE with placeholder identities, (2) above "groups" object explaining GitHub identity format requirement (xxx@github not email), (3) inline after first group member showing correct format, (4) note that real ACL with actual identities applied manually
- [ ] T031 [US2] Add "Troubleshooting" section to docs/runbooks/tailscale-setup.md with "Access Denied" subsection listing identity mismatch as first diagnostic step
- [ ] T032 [US2] Add "Verification" section to docs/runbooks/tailscale-setup.md explaining how to run verify_tailscale.yml playbook and interpret results

**Checkpoint**: User Story 2 complete - documentation explains identity pitfall comprehensively

---

## Phase 5: User Story 4 - Apply ACL Changes Manually (Priority: P2)

**Goal**: Step-by-step runbook for safely applying ACL changes from repo to Tailscale admin console

**Independent Test**: Follow documented procedure: edit docs/tailscale-acl.example.json, commit, apply via admin console, verify access still works

### Implementation for User Story 4

- [ ] T033 [US4] Add "ACL Management" section to docs/runbooks/tailscale-setup.md with overview of ACL structure (groups, acls, tagOwners)
- [ ] T034 [US4] Add "Editing ACLs" subsection to docs/runbooks/tailscale-setup.md: how to edit docs/tailscale-acl.example.json, validate JSON syntax, common patterns (adding services, modifying permissions)
- [ ] T035 [US4] Add "Applying ACL Changes" subsection to docs/runbooks/tailscale-setup.md with step-by-step procedure: 1) commit changes to repo, 2) navigate to Tailscale admin console, 3) copy JSON content, 4) paste into ACL editor, 5) validate, 6) save
- [ ] T036 [US4] Add "⚠️ Safety Warning" callout to ACL application section: test access before closing admin console, how to rollback if locked out, keep admin console open until verified
- [ ] T037 [US4] Add "ACL Testing Checklist" to docs/runbooks/tailscale-setup.md: verify Proxmox access, verify LAN service access, check Tailscale admin for warnings
- [ ] T038 [US4] Update docs/tailscale-acl.example.json comments to include examples: adding new service destinations, modifying user groups, common ACL patterns

**Checkpoint**: User Story 4 complete - ACL management runbook provides safe manual procedure

---

## Phase 6: User Story 5 - Verify Remote Access from Mobile Device (Priority: P3)

**Goal**: Verification checklist confirms end-to-end remote access from cellular device

**Independent Test**: Follow checklist from mobile on cellular: connect Tailscale, access pve at 100.67.156.70:8006, access LAN service at 192.168.1.x, verify admin console shows active routes

### Implementation for User Story 5

- [ ] T039 [US5] Add "Remote Access Verification" section to docs/runbooks/tailscale-setup.md with prerequisites (mobile device, cellular data, Tailscale app installed)
- [ ] T040 [US5] Add "Mobile Device Checklist" to docs/runbooks/tailscale-setup.md with minimum 4 validation steps: 1) disable WiFi / enable cellular, 2) connect Tailscale VPN, 3) access Proxmox web UI at https://100.67.156.70:8006, 4) access LAN service at http://192.168.1.213:2283 (Immich example)
- [ ] T041 [US5] Add "Admin Console Verification" subsection to docs/runbooks/tailscale-setup.md: navigate to Machines → pve, verify subnet route 192.168.1.0/24 shows as advertised and active, check for IP forwarding warnings (should be none)
- [ ] T042 [US5] Add "Common Issues" subsection for mobile access: Tailscale not connected, subnet routes not approved in admin, IP forwarding warnings, ACL blocking traffic
- [ ] T043 [US5] Add "Expected Behavior" section describing what successful remote access looks like: Proxmox UI loads normally, LAN services accessible via private IPs, no latency spikes (routing through Tailscale is efficient)

**Checkpoint**: User Story 5 complete - comprehensive mobile remote access verification checklist

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Documentation completeness, README updates, final validation

- [ ] T044 [P] Add "Architecture" section to docs/runbooks/tailscale-setup.md with ASCII diagram showing pve as subnet router between Tailscale mesh (100.x network) and LAN (192.168.1.0/24)
- [ ] T045 [P] Add "Security Considerations" section to docs/runbooks/tailscale-setup.md: auth key handling (never commit), ACL principle of least privilege, subnet router as single point of failure
- [ ] T046 [P] Add "Disaster Recovery" section to docs/runbooks/tailscale-setup.md explaining how this feature enables pve rebuild scenario
- [ ] T047 Update main README.md to reference new tailscale.yml playbook in "Available Playbooks" section
- [ ] T048 Update main README.md to add docs/runbooks/tailscale-setup.md to "Documentation" section
- [ ] T049 Review all tasks against FR-001 through FR-019 to ensure functional requirements coverage (validation checklist)
- [ ] T050 Final idempotency test: run ansible-playbook playbooks/tailscale.yml --tags install,configure against already-configured pve (exclude verification tasks which always execute commands), verify changed=0 for all configuration tasks

---

## Dependencies & Parallel Execution

### User Story Completion Order

```
Phase 1 (Setup)
    ↓
Phase 2 (US1) ← Must complete first (core functionality)
    ↓
Phase 3 (US3) ← Depends on US1 (verifies what US1 creates)
    ↓
Phase 4 (US2) ← Can start after US1 (documents what US1 implements)
    ↓
Phase 5 (US4) ← Independent of others (ACL is manual)
    ↓
Phase 6 (US5) ← Requires US1+US2+US4 (end-to-end validation)
    ↓
Phase 7 (Polish)
```

### Parallel Execution Opportunities

**Within Phase 1**: T002, T003, T004, T005 can run in parallel (different files)

**Within Phase 2 (US1)**: 
- T006, T007, T008, T010 can run in parallel (independent files)
- T011, T012, T013, T014 must run sequentially (dependencies)

**Within Phase 3 (US3)**:
- T016, T017, T018, T019, T020, T021 can run in parallel (independent verification tasks)
- T022, T023 must run after verification tasks

**Within Phase 4 (US2)**: All documentation tasks T024-T032 can run in any order (same file being edited)

**Within Phase 5 (US4)**: All documentation tasks T033-T038 can run in any order (same file being edited)

**Within Phase 6 (US5)**: All documentation tasks T039-T043 can run in any order (same file being edited)

**Within Phase 7**: T044, T045, T046 can run in parallel (different sections/files)

---

## Implementation Strategy

### MVP Delivery (Phase 1 + Phase 2 = User Story 1)

**First Deliverable**: Phases 1-2 (T001-T015, total 15 tasks including constitution compliance) provide fully functional Tailscale subnet router automation
- Runnable playbook that configures pve
- Idempotent execution
- Handles fresh installs and existing setups
- **Value**: Disaster recovery capability, reproducible setup

**Testing after MVP**: Run against existing pve setup (should be idempotent with changed=0)

### Incremental Delivery

**Second Increment**: Add Phase 3 (T016-T023) for diagnostics
- Verification playbook
- Structured output
- **Value**: Troubleshooting capability, confidence in configuration

**Third Increment**: Add Phase 4 (T023-T031) for documentation
- GitHub identity warnings
- How-to guide
- **Value**: Knowledge capture, prevents common mistakes

**Fourth Increment**: Add Phase 5 (T032-T037) for ACL management
- Manual application procedure
- Safety warnings
- **Value**: Safe ACL updates, operational procedures

**Fifth Increment**: Add Phase 6 (T038-T042) for mobile verification
- End-to-end testing checklist
- **Value**: User-facing validation

**Final Polish**: Phase 7 (T043-T050)

---

## Success Criteria Mapping

- **SC-001**: ✅ T011 ensures /etc/sysctl.d/99-tailscale-subnet-router.conf exists with correct values
- **SC-002**: ✅ T019, T020 verify sysctl values return 1 for IPv4 and IPv6 forwarding
- **SC-003**: ✅ T018 verifies tailscale debug prefs includes 192.168.1.0/24 in AdvertiseRoutes
- **SC-004**: ✅ T040 includes Proxmox web UI access at 100.67.156.70:8006 in mobile checklist
- **SC-005**: ✅ T040 includes LAN service access at 192.168.1.213:2283 in mobile checklist
- **SC-006**: ✅ T041 verifies Tailscale admin console shows subnet route as advertised and active with no warnings
- **SC-007**: ✅ T050 performs final idempotency test verifying changed=0 on rerun
- **SC-008**: ✅ T028, T029, T031 provide at least 3 explicit warnings about GitHub identity format
- **SC-009**: ✅ T030 adds comments to ACL JSON ensuring GitHub identity format (xxx@github)
- **SC-010**: ✅ T016-T021 provide structured Ansible output with pass/fail status per check

---

## Task Count Summary

- **Phase 1 (Setup + Constitution Compliance)**: 5 tasks
- **Phase 2 (US1 - Rebuild Proxmox)**: 10 tasks  
- **Phase 3 (US3 - Verify Configuration)**: 8 tasks
- **Phase 4 (US2 - Identity Documentation)**: 9 tasks
- **Phase 5 (US4 - ACL Management)**: 6 tasks
- **Phase 6 (US5 - Mobile Verification)**: 5 tasks
- **Phase 7 (Polish)**: 7 tasks

**Total**: 50 tasks

**Parallel Opportunities**: 18 tasks marked [P] (36% of total can run in parallel within phases)

**MVP Scope**: 15 tasks (Phase 1 + Phase 2 = T001-T015, includes CRITICAL constitution compliance)
