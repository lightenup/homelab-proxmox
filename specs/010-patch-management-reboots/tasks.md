# Implementation Tasks: Patch Management + Reboots

**Feature Branch**: `010-patch-management-reboots`  
**Created**: December 19, 2025  
**Status**: Draft  
**Last Updated**: December 19, 2025 (clarifications integrated)

## Clarifications Applied (2025-12-19)

These tasks incorporate the following specification clarifications:

1. **Container auto-start**: Both LXC (`onboot: 1` in Proxmox) and Docker (`restart: always` in compose files)
2. **Verification failures**: All checks are critical - playbook fails on any verification failure
3. **Apt upgrade mode**: Use `upgrade: safe` parameter for explicit intent
4. **Reboot timeouts**: Split timing - 600s reboot timeout / 300s SSH wait timeout
5. **Summary timing**: Include both total execution time and per-host timing breakdown

## Task Conventions

- `[ ]` = Not started
- `[x]` = Completed
- `[P]` = Can be done in parallel with other [P] tasks
- `[US#]` = Maps to User Story from spec.md
- Each phase must complete before next phase begins
- Mark task complete with implementation notes after verification passes

---

## Phase 1: Spec & Wiring (Foundation)

**Goal**: Create specification and playbook scaffolding

### Specification Documents

- [x] **T001** [US1-5] Create spec.md with all user stories, requirements, and acceptance criteria
  - **Completed**: Created comprehensive spec.md with 5 user stories (US1-US5), 17 functional requirements (FR-001 to FR-017), 10 success criteria (SC-001 to SC-010), edge cases, risks, assumptions, and dependencies
- [x] **T002** [US1-5] Create plan.md with implementation phases and technical decisions
  - **Completed**: Created detailed plan.md with 5 implementation phases, architecture overview, technical decisions (apt module, reboot detection, serial execution), and success criteria mapping
- [x] **T003** [US1-5] Create tasks.md (this document) with actionable checklist
  - **Completed**: Created tasks.md with 80 tasks organized across 5 phases plus integration testing, documentation, and git workflow sections

### Playbook Scaffolding

- [ ] **T004** [US3] Create `ansible/playbooks/update_monthly.yml` with two plays:
  - Play 1: Target `services` group
  - Play 2: Target `proxmox_hosts` group
  - Include comments explaining orchestration order

- [ ] **T005** [US3] Configure Play 1 with `serial: 1` to avoid simultaneous reboots

- [ ] **T006** [US3] Add play-level variables:
  - `gather_facts: yes`
  - `become: yes`

### Role Structure

- [ ] **T007** [US1,2] Create role directory: `ansible/roles/patch_management/`

- [ ] **T008** [US1,2] Create role subdirectories:
  - `defaults/`
  - `tasks/`
  - `handlers/`

- [ ] **T009** [US1,2] Create `defaults/main.yml` with default variables:
  ```yaml
  # Reboot handling (clarified: 600s reboot / 300s SSH wait)
  patch_reboot_timeout: 600
  patch_wait_for_connection_timeout: 300
  allow_host_reboot: false
  
  # Verification targets (clarified: all checks are critical and fail playbook)
  patch_verify_ssh: true
  patch_verify_mounts: true
  patch_verify_http: true
  
  # HTTP endpoints (clarified: all are critical checks)
  patch_http_endpoints:
    - name: "Immich API"
      url: "http://192.168.1.213:2283/api/server/ping"
      host: "immich"
    - name: "Home Assistant"
      url: "http://192.168.1.212:8123"
      host: "homeassistant"
    - name: "Reverse Proxy"
      url: "http://192.168.1.211:80"
      host: "proxy"
  
  # NFS mounts to verify
  patch_nfs_mounts:
    - path: "/mnt/nas/homelab_immich"
      host: "pve"
  
  # Bind mounts to verify
  patch_bind_mounts:
    - path: "/mnt/immich"
      host: "immich"
  ```

- [ ] **T010** [US1,2] Create task file stubs:
  - `tasks/main.yml` (entry point)
  - `tasks/update.yml` (apt update + upgrade)
  - `tasks/reboot.yml` (reboot handling)
  - `tasks/verify.yml` (post-update checks)

- [ ] **T011** [US1,2] Create `tasks/main.yml` to include other task files:
  ```yaml
  ---
  - name: "Patch Management - Update packages"
    include_tasks: update.yml
  
  - name: "Patch Management - Handle reboot if needed"
    include_tasks: reboot.yml
  
  - name: "Patch Management - Verify system health"
    include_tasks: verify.yml
  ```

### Initial Testing

- [ ] **T012** [P] [US3] Validate playbook syntax:
  ```bash
  ansible-playbook ansible/playbooks/update_monthly.yml --syntax-check
  ```

- [ ] **T013** [P] [US3] Run playbook in check mode:
  ```bash
  ansible-playbook ansible/playbooks/update_monthly.yml --check
  ```

- [ ] **T014** [US3] Wire role into playbook:
  - Add `roles: [patch_management]` to both plays
  - Verify playbook runs without errors (no-op state)

**Phase 1 Verification**:
- Syntax check passes
- Check mode completes without failures
- Playbook structure follows Ansible best practices
- All task files exist and are properly included

---

## Phase 2: Patching Role Implementation

**Goal**: Implement package update and reboot logic

### Apt Update & Upgrade

- [ ] **T015** [US1] Implement `tasks/update.yml` - Update apt cache:
  ```yaml
  - name: "Update apt cache"
    apt:
      update_cache: yes
      cache_valid_time: 3600
    register: apt_cache_result
  ```

- [ ] **T016** [US1] Implement `tasks/update.yml` - Upgrade packages (clarified: use upgrade=safe):
  ```yaml
  - name: "Upgrade all packages (safe mode - never removes packages)"
    apt:
      upgrade: safe
      autoremove: no
      autoclean: yes
    register: apt_upgrade_result
  ```

- [ ] **T017** [US1] Add package count tracking:
  ```yaml
  - name: "Record package upgrade count"
    set_fact:
      packages_upgraded: "{{ apt_upgrade_result.stdout_lines | select('search', 'upgraded') | list | length }}"
    when: apt_upgrade_result.changed
  ```

### Reboot Detection & Handling

- [ ] **T018** [US1,2] Implement `tasks/reboot.yml` - Check reboot required:
  ```yaml
  - name: "Check if reboot is required"
    stat:
      path: /var/run/reboot-required
    register: reboot_required_file
  ```

- [ ] **T019** [US2] Add Proxmox host reboot gate:
  ```yaml
  - name: "Set reboot decision for LXCs"
    set_fact:
      should_reboot: "{{ reboot_required_file.stat.exists }}"
    when: "'services' in group_names"
  
  - name: "Set reboot decision for Proxmox host (gated)"
    set_fact:
      should_reboot: "{{ reboot_required_file.stat.exists and allow_host_reboot | default(false) | bool }}"
    when: "'proxmox_hosts' in group_names"
  ```

- [ ] **T020** [US1,2] Implement conditional reboot:
  ```yaml
  - name: "Reboot system if required"
    reboot:
      reboot_timeout: "{{ patch_reboot_timeout }}"
      msg: "Rebooting for kernel/library updates"
    when: should_reboot | default(false) | bool
    register: reboot_result
  ```

- [ ] **T021** [US1,2] Add wait for SSH after reboot:
  ```yaml
  - name: "Wait for system to become reachable"
    wait_for_connection:
      timeout: "{{ patch_wait_for_connection_timeout }}"
    when: reboot_result.changed
  ```

- [ ] **T022** [US1,2] Verify system is operational after reboot:
  ```yaml
  - name: "Gather facts after reboot"
    setup:
    when: reboot_result.changed
  ```

### Initial Testing

- [ ] **T023** [US1] Test patching on single LXC (adguard):
  ```bash
  ansible-playbook ansible/playbooks/update_monthly.yml --limit adguard
  ```
  - Verify apt update runs
  - Verify packages upgrade if available
  - Verify no reboot occurs if not required

- [ ] **T024** [US1] Simulate reboot-required condition and verify auto-start (clarified):
  - Manually create `/var/run/reboot-required` on test LXC
  - Run playbook against that LXC
  - Verify reboot occurs
  - Verify SSH returns after reboot
  - Verify LXC auto-started (Proxmox `onboot: 1` setting)
  - Verify Docker containers auto-started (`restart: always` in compose files)

- [ ] **T025** [US2] Test Proxmox host without reboot flag:
  ```bash
  ansible-playbook ansible/playbooks/update_monthly.yml --limit pve
  ```
  - If `/var/run/reboot-required` exists, verify NO reboot occurs

- [ ] **T026** [US2] Test Proxmox host WITH reboot flag:
  ```bash
  ansible-playbook ansible/playbooks/update_monthly.yml --limit pve -e allow_host_reboot=true
  ```
  - If reboot required, verify reboot occurs
  - Verify pve returns and SSH accessible

- [ ] **T027** [US1,2] Test idempotency:
  - Run playbook twice against same host
  - Verify second run shows `changed=0` except apt cache update
  - Verify no unnecessary reboots

- [ ] **T027a** [US1] Verify LXC auto-start configuration (clarified requirement):
  - Check all production LXCs have `onboot: 1` in Proxmox config
  - Command: `pct config <VMID> | grep onboot`
  - Verify for: adguard (210), proxy (211), homeassistant (212), immich (213)
  - If not set, update via Terraform or `pct set <VMID> -onboot 1`

**Phase 2 Verification**:
- LXC containers update and reboot automatically when needed (US1)
- Proxmox host updates but requires explicit flag for reboot (US2)
- Package upgrade uses safe mode (no package removals)
- Idempotency confirmed on repeated runs

---

## Phase 3: Orchestration with Ordering

**Goal**: Implement proper execution order and performance tracking

### Execution Order

- [ ] **T028** [US3] Verify Play 1 targets `services` group:
  ```yaml
  - name: "Monthly Patching - Services"
    hosts: services
    serial: 1
    roles:
      - patch_management
  ```

- [ ] **T029** [US3] Verify Play 2 targets `proxmox_hosts` group:
  ```yaml
  - name: "Monthly Patching - Proxmox Host"
    hosts: proxmox_hosts
    roles:
      - patch_management
  ```

- [ ] **T030** [US3] Add preflight connectivity check at start of playbook:
  ```yaml
  - name: "Preflight - Verify Ansible connectivity"
    hosts: all
    gather_facts: no
    tasks:
      - name: "Test SSH connectivity"
        ping:
  ```

### Performance Tracking

- [ ] **T031** [US3] Add timestamp tracking at playbook start:
  ```yaml
  - name: "Record playbook start time"
    hosts: localhost
    gather_facts: no
    tasks:
      - name: "Set start timestamp"
        set_fact:
          playbook_start_time: "{{ ansible_date_time.epoch }}"
          cacheable: yes
  ```

- [ ] **T032** [US3] Track per-host package counts:
  - Already implemented in T017 as `packages_upgraded`
  - Verify fact is properly registered for summary

- [ ] **T033** [US3] Track which hosts rebooted:
  ```yaml
  - name: "Record reboot event"
    set_fact:
      host_rebooted: true
      cacheable: yes
    when: reboot_result.changed
  ```

### Orchestration Testing

- [ ] **T034** [US3] Test full playbook execution order:
  ```bash
  ansible-playbook ansible/playbooks/update_monthly.yml
  ```
  - Verify services group runs first
  - Verify proxmox_hosts group runs second
  - Verify serial execution (one LXC at a time)

- [ ] **T035** [US3] Test with subset of hosts:
  ```bash
  ansible-playbook ansible/playbooks/update_monthly.yml --limit services
  ```
  - Verify only services group executes
  - Verify pve is skipped

- [ ] **T036** [US3] Test timing data collection:
  - Run playbook and check for start timestamp
  - Verify per-host facts are registered
  - Calculate approximate duration

**Phase 3 Verification**:
- Single playbook orchestrates entire monthly update (US3)
- Services patched before Proxmox host
- Serial execution prevents simultaneous reboots
- Performance data available for reporting

---

## Phase 4: Verification + Reporting

**Goal**: Implement post-update verification and summary report

### Verification Tasks

- [ ] **T037** [US4] Implement `tasks/verify.yml` - SSH connectivity check:
  ```yaml
  - name: "Verify SSH connectivity to all hosts"
    wait_for_connection:
      timeout: 30
    delegate_to: "{{ item }}"
    loop: "{{ groups['all'] }}"
    register: ssh_check_result
    failed_when: false
  ```

- [ ] **T038** [US4] Add NFS mount verification for pve:
  ```yaml
  - name: "Verify NFS mount on Proxmox host"
    stat:
      path: "{{ item.path }}"
    register: nfs_mount_check
    when: inventory_hostname == item.host
    loop: "{{ patch_nfs_mounts }}"
    failed_when: not nfs_mount_check.stat.exists
  ```

- [ ] **T039** [US4] Add bind mount verification for immich:
  ```yaml
  - name: "Verify bind mount in Immich LXC"
    stat:
      path: "{{ item.path }}"
    register: bind_mount_check
    when: inventory_hostname == item.host
    loop: "{{ patch_bind_mounts }}"
    failed_when: not bind_mount_check.stat.exists
  ```

- [ ] **T040** [US4] Implement HTTP health checks (clarified: all are critical checks):
  ```yaml
  - name: "HTTP health check - {{ item.name }}"
    uri:
      url: "{{ item.url }}"
      method: GET
      timeout: 10
      status_code: 200
    register: http_check_result
    when: 
      - patch_verify_http | bool
      - inventory_hostname == item.host
    loop: "{{ patch_http_endpoints }}"
  ```

- [ ] **T041** [US4] Add verification result tracking:
  ```yaml
  - name: "Record verification results"
    set_fact:
      verification_passed: "{{ ssh_check_result.failed == false and nfs_mount_check.stat.exists | default(true) }}"
      cacheable: yes
  ```

### Summary Reporting

- [ ] **T042** [US3] Create summary play at end of playbook:
  ```yaml
  - name: "Generate Summary Report"
    hosts: localhost
    gather_facts: no
    tasks:
      - name: "Collect results from all hosts"
        set_fact:
          summary_data: "{{ hostvars }}"
  ```

- [ ] **T043** [US3] Generate hosts updated list:
  ```yaml
  - name: "Identify hosts with package updates"
    set_fact:
      hosts_updated: "{{ groups['all'] | select('in', hostvars) | select('packages_upgraded', 'defined') | list }}"
  ```

- [ ] **T044** [US3] Generate hosts rebooted list:
  ```yaml
  - name: "Identify hosts that rebooted"
    set_fact:
      hosts_rebooted: "{{ groups['all'] | select('in', hostvars) | select('host_rebooted', 'defined') | list }}"
  ```

- [ ] **T045** [US3] Calculate total execution time:
  ```yaml
  - name: "Calculate playbook duration"
    set_fact:
      playbook_duration: "{{ (ansible_date_time.epoch | int) - (playbook_start_time | int) }}"
  ```

- [ ] **T046** [US3] Display summary report (clarified: include per-host timing breakdown):
  ```yaml
  - name: "Display Summary Report"
    debug:
      msg:
        - "========== MONTHLY PATCHING SUMMARY =========="
        - "Total Execution Time: {{ playbook_duration }}s"
        - ""
        - "Hosts Updated: {{ hosts_updated | length }}"
        - "  {{ hosts_updated | join(', ') }}"
        - ""
        - "Per-Host Timing:"
        - "{% for host in groups['all'] %}"
        - "  {{ host }}: {{ hostvars[host].host_duration | default('N/A') }}s"
        - "{% endfor %}"
        - ""
        - "Hosts Rebooted: {{ hosts_rebooted | length }}"
        - "  {{ hosts_rebooted | join(', ') }}"
        - ""
        - "Verification Status:"
        - "  SSH Connectivity: {{ 'PASS' if ssh_check_result.failed == false else 'FAIL' }}"
        - "  NFS Mounts: {{ 'PASS' if nfs_mount_check.stat.exists | default(false) else 'FAIL' }}"
        - "  HTTP Checks: {{ 'PASS' if http_check_result.status == 200 | default(false) else 'SKIP' }}"
        - "=============================================="
  ```

### Verification Testing

- [ ] **T047** [US4] Test SSH connectivity verification:
  ```bash
  ansible-playbook ansible/playbooks/update_monthly.yml --check
  ```
  - Verify SSH check runs for all hosts
  - Verify result recorded correctly

- [ ] **T048** [US4] Test NFS mount verification:
  - Run playbook with NFS mount present
  - Verify check passes
  - Simulate missing mount: `umount /mnt/nas/homelab_immich`
  - Verify check detects failure

- [ ] **T049** [US4] Test bind mount verification:
  - Run playbook with bind mount present
  - Verify check passes
  - Stop immich container to simulate missing mount
  - Verify check reports issue

- [ ] **T050** [US4] Test HTTP checks with service down (clarified: should fail playbook):
  - Stop homeassistant container
  - Run verification
  - Verify HTTP check fails and playbook exits with error

- [ ] **T051** [US3] Test summary report (clarified: includes per-host timing):
  - Run full playbook
  - Verify summary shows:
    - Correct host counts
    - Accurate reboot list
    - Total execution time
    - Per-host timing breakdown
    - Verification status

**Phase 4 Verification**:
- Post-update verification detects mount issues and fails playbook (US4)
- HTTP checks fail playbook when services are unreachable (clarified behavior)
- Summary report provides complete audit trail with per-host timing (US3)
- Operator has clear success/failure visibility

---

## Phase 5: Tailscale Mobile Runbook

**Goal**: Document Tailscale mobile access and create diagnostics

### Runbook Documentation

- [ ] **T052** [US5] Create `docs/runbooks/` directory if not exists

- [ ] **T053** [US5] Create `docs/runbooks/tailscale-mobile.md` with sections:
  - Overview: Why Tailscale for mobile access
  - Prerequisites: Tailscale account, subnet router configured
  - Phone app installation (iOS/Android)
  - Verifying tailnet membership
  - Checking subnet route approval in admin console
  - Address format explanation (with examples)
  - Why mDNS (.local) doesn't work over Tailscale
  - Troubleshooting checklist

- [ ] **T054** [US5] Document phone app installation:
  ```markdown
  ## Installing Tailscale on Phone
  
  ### iOS
  1. Open App Store
  2. Search "Tailscale"
  3. Install official Tailscale app
  4. Open app, tap "Sign in"
  5. Authenticate with your Tailscale account
  
  ### Android
  1. Open Google Play Store
  2. Search "Tailscale"
  3. Install official Tailscale app
  4. Open app, tap "Sign in"
  5. Authenticate with your Tailscale account
  ```

- [ ] **T055** [US5] Document tailnet verification:
  ```markdown
  ## Verifying Tailnet Membership
  
  1. Open Tailscale app on phone
  2. Check status indicator (green = connected)
  3. Note your phone's Tailscale IP (usually 100.x.x.x)
  4. Visit Tailscale admin console: https://login.tailscale.com/admin/machines
  5. Confirm your phone appears in device list
  ```

- [ ] **T056** [US5] Document subnet route approval:
  ```markdown
  ## Checking Subnet Route Approval
  
  Your Proxmox host (pve) advertises subnet routes for 192.168.1.0/24.
  
  1. Visit admin console: https://login.tailscale.com/admin/machines
  2. Find "pve" in machine list
  3. Click machine name to view details
  4. Check "Subnet routes" section
  5. Verify 192.168.1.0/24 shows "Approved" status
  6. If not approved, click "Review" and approve the route
  ```

- [ ] **T057** [US5] Document address format explanation:
  ```markdown
  ## Address Formats: What Works from Phone
  
  ### ✅ WORKS: Tailscale IP
  - Example: `http://100.64.0.5`
  - Direct Tailscale VPN address
  - Always works, most reliable
  
  ### ✅ WORKS: MagicDNS Name
  - Example: `http://pve` or `http://immich`
  - Requires MagicDNS enabled in tailnet settings
  - Resolves to Tailscale IP automatically
  
  ### ✅ WORKS: Subnet Route IP
  - Example: `http://192.168.1.213`
  - Requires subnet route approved (see above)
  - Routes through pve to reach LAN devices
  
  ### ❌ DOES NOT WORK: .local mDNS
  - Example: `http://pve.local` or `http://immich.local`
  - mDNS (Multicast DNS) requires direct network access
  - Tailscale VPN doesn't forward multicast traffic
  - Use Tailscale IP or MagicDNS instead
  ```

- [ ] **T058** [US5] Document troubleshooting checklist:
  ```markdown
  ## Troubleshooting Checklist
  
  ### Phone Cannot Connect to Homelab
  
  1. **Check Tailscale Status**
     - Open Tailscale app
     - Verify status shows "Connected"
     - Note your phone's Tailscale IP
  
  2. **Verify Subnet Routes**
     - Check admin console for route approval
     - Confirm pve is online and connected
     - Verify pve advertises 192.168.1.0/24
  
  3. **Test Connectivity**
     - Try pve Tailscale IP: `http://100.x.x.x`
     - Try MagicDNS: `http://pve`
     - Try subnet route: `http://192.168.1.112`
  
  4. **Check ACL Rules**
     - Visit: https://login.tailscale.com/admin/acls
     - Verify your phone's tag can access pve
     - Check for any deny rules blocking access
  
  5. **Restart Tailscale**
     - On phone: Force close app, reopen
     - On pve: `sudo systemctl restart tailscaled`
  ```

### Diagnostics Playbook

- [ ] **T059** [US5] Create `ansible/playbooks/tailscale_diagnostics.yml`:
  ```yaml
  ---
  - name: "Tailscale Diagnostics"
    hosts: proxmox_hosts
    gather_facts: yes
    become: yes
    
    tasks:
      - name: "Check Tailscale service status"
        systemd:
          name: tailscaled
          state: started
        check_mode: yes
        register: tailscale_service
      
      - name: "Display service status"
        debug:
          msg: "Tailscale service is {{ 'running' if tailscale_service.status.ActiveState == 'active' else 'not running' }}"
  ```

- [ ] **T060** [US5] Add Tailscale status output:
  ```yaml
  - name: "Get Tailscale status"
    command: tailscale status
    register: tailscale_status
    changed_when: false
  
  - name: "Display Tailscale status"
    debug:
      var: tailscale_status.stdout_lines
  ```

- [ ] **T061** [US5] Add Tailscale IP output:
  ```yaml
  - name: "Get Tailscale IPv4 address"
    command: tailscale ip -4
    register: tailscale_ip
    changed_when: false
  
  - name: "Display Tailscale IP"
    debug:
      msg: "Tailscale IP: {{ tailscale_ip.stdout }}"
  ```

- [ ] **T062** [US5] Add advertised routes output:
  ```yaml
  - name: "Check advertised subnet routes"
    command: tailscale status --json
    register: tailscale_status_json
    changed_when: false
  
  - name: "Parse and display routes"
    debug:
      msg: "Advertised routes: {{ (tailscale_status_json.stdout | from_json).Self.AllowedIPs }}"
  ```

### Runbook Testing

- [ ] **T063** [US5] Test runbook from phone:
  - Follow installation steps
  - Install Tailscale app
  - Authenticate and connect
  - Verify tailnet membership
  - Check subnet route approval

- [ ] **T064** [US5] Test address formats from phone:
  - Try accessing pve via Tailscale IP
  - Try accessing pve via MagicDNS (if enabled)
  - Try accessing immich via 192.168.1.213
  - Confirm `.local` names don't work (document why)

- [ ] **T065** [US5] Test diagnostics playbook:
  ```bash
  ansible-playbook ansible/playbooks/tailscale_diagnostics.yml
  ```
  - Verify output shows Tailscale status
  - Verify Tailscale IP displayed
  - Verify advertised routes shown
  - Confirm no root required on phone side

- [ ] **T066** [US5] Test troubleshooting steps:
  - Simulate connectivity issue
  - Follow checklist step-by-step
  - Verify each command works as documented
  - Refine instructions based on findings

**Phase 5 Verification**:
- Operator can access homelab from phone via Tailscale (US5)
- Runbook explains why mDNS doesn't work over Tailscale
- Diagnostics playbook provides useful troubleshooting data
- Documentation prevents common address format confusion

---

## Final Integration Testing

**Goal**: Validate complete end-to-end workflow

- [ ] **T067** Run full monthly patching workflow:
  ```bash
  ansible-playbook ansible/playbooks/update_monthly.yml
  ```
  - Verify execution order: services → proxmox_hosts
  - Verify serial execution (one service at a time)
  - Verify LXCs reboot automatically if needed
  - Verify pve does NOT reboot without flag

- [ ] **T068** Test Proxmox host reboot with flag:
  ```bash
  ansible-playbook ansible/playbooks/update_monthly.yml --limit pve -e allow_host_reboot=true
  ```
  - If reboot required, verify it occurs
  - Verify pve returns with all services healthy
  - Verify LXCs auto-start after host reboot

- [ ] **T069** Verify post-update checks:
  - All SSH connectivity passes
  - NFS mount exists on pve
  - Bind mount exists in immich
  - HTTP checks run without hard-failing playbook

- [ ] **T070** Review summary report:
  - Verify accurate host counts
  - Verify correct reboot list
  - Verify timing data reasonable
  - Verify verification status clear

- [ ] **T071** Test idempotency end-to-end:
  - Run full playbook twice
  - Verify second run shows minimal changes
  - Verify no unnecessary reboots

- [ ] **T072** Test Tailscale mobile access:
  - Connect phone to tailnet
  - Access pve via Tailscale IP
  - Access immich via subnet route
  - Confirm runbook instructions accurate

**Final Verification Checklist**:
- [ ] All user stories (US1-US5) have test coverage
- [ ] All functional requirements (FR-001 to FR-017) implemented
- [ ] All success criteria (SC-001 to SC-010) validated
- [ ] All tasks marked complete with notes
- [ ] Documentation complete (spec, plan, runbooks)

---

## Documentation Tasks

- [ ] **T073** Create operational runbook:
  - Create `docs/runbooks/monthly-patching.md`
  - Document when to run monthly patching
  - Document command to run
  - Document what to expect in output
  - Document common issues and solutions

- [ ] **T074** Update main README if needed:
  - Add reference to monthly patching workflow
  - Link to operational runbook
  - Note Tailscale mobile access documentation

- [ ] **T075** Document recovery procedures:
  - What to do if host reboot fails
  - What to do if mount missing post-reboot
  - What to do if container doesn't auto-start
  - IPMI/physical access instructions

---

## Git Workflow Tasks

- [ ] **T076** Commit spec documents:
  ```bash
  git add specs/010-patch-management-reboots/
  git commit -m "docs(patching): Add monthly patch management specification"
  ```

- [ ] **T077** Commit playbook implementation:
  ```bash
  git add ansible/playbooks/update_monthly.yml ansible/roles/patch_management/
  git commit -m "feat(patching): Implement monthly update orchestration with reboot handling"
  ```

- [ ] **T078** Commit verification implementation:
  ```bash
  git add ansible/roles/patch_management/tasks/verify.yml
  git commit -m "feat(patching): Add post-update verification checks"
  ```

- [ ] **T079** Commit Tailscale documentation:
  ```bash
  git add docs/runbooks/tailscale-mobile.md ansible/playbooks/tailscale_diagnostics.yml
  git commit -m "docs(tailscale): Add mobile access runbook and diagnostics"
  ```

- [ ] **T080** Final commit with task completion:
  ```bash
  git add specs/010-patch-management-reboots/tasks.md
  git commit -m "docs(patching): Mark implementation tasks complete"
  ```

---

## Task Summary

- **Phase 1** (Spec & Wiring): T001-T014 (14 tasks)
- **Phase 2** (Patching Implementation): T015-T027 (13 tasks)
- **Phase 3** (Orchestration): T028-T036 (9 tasks)
- **Phase 4** (Verification & Reporting): T037-T051 (15 tasks)
- **Phase 5** (Tailscale Runbook): T052-T066 (15 tasks)
- **Integration Testing**: T067-T072 (6 tasks)
- **Documentation**: T073-T075 (3 tasks)
- **Git Workflow**: T076-T080 (5 tasks)

**Total Tasks**: 80

**Estimated Completion Time**: 10-15 hours
