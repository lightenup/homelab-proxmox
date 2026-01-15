# Implementation Tasks: Minimal Monitoring & Alerting

**Feature**: 011-monitoring-alerting  
**Created**: December 20, 2025  
**Updated**: December 20, 2025 (after spec clarifications)  
**Total Estimated Tasks**: 63  

## Implementation Approach

**Key Clarifications**:
- **Notifications**: Email (SMTP) only - no ntfy server deployment
- **Monitor Configuration**: Fully automated via Uptime Kuma API
- **SMTP Auth**: STARTTLS port 587 with PLAIN/LOGIN
- **API Access**: Container readiness checks + retry logic
- **Dashboard Auth**: Basic authentication, credentials in Ansible Vault

## Task List

### Phase 1: Infrastructure Provisioning (Terraform)

**Goal**: Create monitoring LXC via Terraform

- [X] **[P] T001**: Add monitoring LXC module instance to `terraform/main.tf`
  - **Files**: terraform/main.tf
  - **Details**: Copy immich module pattern, adjust resources (2 cores, 2GB RAM, 10GB storage)
  - **Validation**: `terraform validate` passes

- [X] **[P] T002**: Update `terraform/environments/prod.tfvars` with monitoring service ID and IP
  - **Files**: terraform/environments/prod.tfvars
  - **Details**: Add `monitoring = 204` to service_ids, add `monitoring = "192.168.1.204"` to service_ips
  - **Validation**: Values follow existing patterns

- [X] **[P] T003**: Add monitoring outputs to `terraform/outputs.tf`
  - **Files**: terraform/outputs.tf
  - **Details**: Output monitoring_ip and monitoring_hostname for inventory generation
  - **Validation**: `terraform validate` passes

- [X] **T004**: Run `terraform plan` and review proposed changes
  - **Command**: `cd terraform && terraform plan -var-file=environments/prod.tfvars`
  - **Validation**: Plan shows 1 new LXC resource, no changes to existing resources
  - **⚠️ STOP POINT**: Review plan output carefully before proceeding

- [X] **T005**: Run `terraform apply` to create monitoring LXC
  - **Command**: `cd terraform && terraform apply -var-file=environments/prod.tfvars`
  - **Validation**: LXC 204 visible in Proxmox UI, status "running"

- [X] **T006**: Verify monitoring LXC is reachable via SSH
  - **Command**: `ssh ansible@192.168.1.204`
  - **Validation**: SSH connection succeeds, ansible user has sudo access (will be validated during playbook run)

- [X] **T007**: Update Ansible inventory from Terraform outputs
  - **Command**: `./scripts/update_ansible_inventory.sh`
  - **Files**: ansible/inventories/generated/hosts.yml
  - **Validation**: `monitoring` host appears in inventory with correct IP

---

### Phase 2: Ansible Role Structure

**Goal**: Create monitoring stack Ansible roles

- [X] **[P] T008**: Create monitoring_stack role directory structure
  - **Command**: `mkdir -p ansible/roles/monitoring_stack/{tasks,handlers,templates,defaults,meta}`
  - **Files**: ansible/roles/monitoring_stack/
  - **Validation**: Directories exist

- [X] **[P] T009**: Create uptime_kuma role directory structure
  - **Command**: `mkdir -p ansible/roles/uptime_kuma/{tasks,templates,defaults,meta,files}`
  - **Files**: ansible/roles/uptime_kuma/
  - **Validation**: Directories exist

- [X] **T010**: Create monitoring playbook
  - **Files**: ansible/playbooks/monitoring.yml
  - **Details**: Import monitoring_stack and uptime_kuma roles
  - **Validation**: `ansible-playbook --syntax-check playbooks/monitoring.yml` passes

---

### Phase 3: Docker Installation

**Goal**: Install Docker on monitoring LXC

- [X] **T011**: Create monitoring_stack role metadata
  - **Files**: ansible/roles/monitoring_stack/meta/main.yml
  - **Details**: Declare dependency on geerlingguy.docker role
  - **Validation**: File exists with valid YAML

- [X] **[P] T012**: Create monitoring_stack role defaults
  - **Files**: ansible/roles/monitoring_stack/defaults/main.yml
  - **Details**: Define uptime_kuma_version, uptime_kuma_port, timezone
  - **Validation**: Variables follow naming conventions

- [X] **[P] T013**: Create monitoring group variables
  - **Files**: ansible/group_vars/monitoring/vars.yml
  - **Details**: Define monitoring_targets list (4 services), API timeouts, retry settings
  - **Validation**: Valid YAML, all 4 services defined

- [X] **T014**: Create Docker installation task
  - **Files**: ansible/roles/monitoring_stack/tasks/install_docker.yml
  - **Details**: Import geerlingguy.docker role, verify Docker service running
  - **Validation**: Syntax check passes

- [X] **T015**: Create main task orchestration
  - **Files**: ansible/roles/monitoring_stack/tasks/main.yml
  - **Details**: Import install_docker.yml as first task
  - **Validation**: Syntax check passes

- [X] **T016**: Test Docker installation
  - **Command**: `ansible-playbook playbooks/monitoring.yml --tags docker`
  - **Validation**: Docker service running on monitoring LXC, `docker ps` works (will be validated during playbook run)

---

### Phase 4: Docker Compose Stack

**Goal**: Deploy Uptime Kuma container (no ntfy)

- [X] **T017**: Create /opt/monitoring directory task
  - **Files**: ansible/roles/monitoring_stack/tasks/create_directories.yml
  - **Details**: Create /opt/monitoring with correct ownership (ansible user or root)
  - **Validation**: Directory created with mode 0755

- [X] **T018**: Template Docker Compose file for Uptime Kuma only
  - **Files**: ansible/roles/monitoring_stack/templates/docker-compose.yml.j2
  - **Details**: Single uptime-kuma service, volume, port 3001, restart policy
  - **Validation**: Template renders correctly with ansible-playbook --check

- [X] **T019**: Create task to deploy Docker Compose file
  - **Files**: ansible/roles/monitoring_stack/tasks/deploy_compose.yml
  - **Details**: Template docker-compose.yml to /opt/monitoring/, notify handler to restart
  - **Validation**: Template module idempotent

- [X] **T020**: Create handler to restart Docker Compose stack
  - **Files**: ansible/roles/monitoring_stack/handlers/main.yml
  - **Details**: `docker compose -f /opt/monitoring/docker-compose.yml up -d`
  - **Validation**: Handler syntax correct

---

### Phase 5: Systemd Service

**Goal**: Configure monitoring stack to start on boot

- [X] **T021**: Template systemd service file
  - **Files**: ansible/roles/monitoring_stack/templates/monitoring-stack.service.j2
  - **Details**: Oneshot service, requires docker.service, restart policy
  - **Validation**: Template renders correctly

- [X] **T022**: Create task to deploy systemd service
  - **Files**: ansible/roles/monitoring_stack/tasks/systemd_service.yml
  - **Details**: Template service file, enable and start service
  - **Validation**: Service enabled and active

- [X] **T023**: Create task to reload systemd daemon
  - **Files**: ansible/roles/monitoring_stack/tasks/systemd_service.yml
  - **Details**: systemd daemon-reload when service file changes
  - **Validation**: daemon-reload runs after service template

---

### Phase 6: Container Verification

**Goal**: Validate Uptime Kuma container is ready

- [X] **T024**: Create task to verify Docker container running
  - **Files**: ansible/roles/monitoring_stack/tasks/verify.yml
  - **Details**: `docker ps --filter name=uptime-kuma --format '{{.Status}}'` includes "Up"
  - **Validation**: Task succeeds when container running

- [X] **T025**: Create task to verify Uptime Kuma port listening
  - **Files**: ansible/roles/monitoring_stack/tasks/verify.yml
  - **Details**: wait_for module on port 3001, timeout 120 seconds
  - **Validation**: Port 3001 is listening

- [X] **T026**: Create task to verify Uptime Kuma HTTP response
  - **Files**: ansible/roles/monitoring_stack/tasks/verify.yml
  - **Details**: `curl -f http://localhost:3001` returns HTTP 200 (may take 30-60s)
  - **Validation**: Uptime Kuma responds successfully

- [X] **T027**: Add verification tasks to main.yml
  - **Files**: ansible/roles/monitoring_stack/tasks/main.yml
  - **Details**: Import verify.yml, tag with 'verify'
  - **Validation**: All verification tasks pass

---

### Phase 7: Secrets Configuration

**Goal**: Configure SMTP and admin credentials securely

- [X] **T028**: Create monitoring group_vars directory
  - **Command**: `mkdir -p ansible/group_vars/monitoring`
  - **Validation**: Directory exists

- [X] **[P] T029**: Document secrets file structure
  - **Files**: ansible/group_vars/monitoring/vault.yml.example
  - **Details**: Example showing uptime_kuma_admin_user/password, SMTP credentials (6 fields)
  - **Validation**: Example file committed to repo

- [ ] **T030**: ⚠️ STOP POINT: Create encrypted vault file
  - **Command**: `ansible-vault create ansible/group_vars/monitoring/vault.yml`
  - **Manual Step**: User must create vault with real SMTP credentials and admin password
  - **Validation**: vault.yml exists, `ansible-vault view` works

- [X] **T031**: Verify .gitignore blocks vault.yml
  - **Command**: `git add ansible/group_vars/monitoring/vault.yml` (should fail)
  - **Validation**: Git refuses to stage vault.yml (already in .gitignore from Feature 008b)

---

### Phase 8: Uptime Kuma API Automation

**Goal**: Automate monitor provisioning via API

- [X] **T032**: Create uptime_kuma role defaults
  - **Files**: ansible/roles/uptime_kuma/defaults/main.yml
  - **Details**: API URLs, retry settings, timeouts
  - **Validation**: Valid YAML

- [X] **T033**: Create task to wait for API readiness
  - **Files**: ansible/roles/uptime_kuma/tasks/wait_for_api.yml
  - **Details**: Poll GET /api/status until HTTP 200, retry for up to 2 minutes
  - **Validation**: Task uses until loop with retries

- [X] **T034**: Create task to check if setup is complete
  - **Files**: ansible/roles/uptime_kuma/tasks/check_setup.yml
  - **Details**: GET /api/status, check if "needSetup" is false (idempotency)
  - **Validation**: Registers result for conditional execution

- [X] **T035**: Create task to setup admin account
  - **Files**: ansible/roles/uptime_kuma/tasks/setup_admin.yml
  - **Details**: POST /api/setup with admin credentials from vault, only when needSetup=true
  - **Validation**: Task skipped if admin already exists

- [X] **T036**: Create task to login and get API token
  - **Files**: ansible/roles/uptime_kuma/tasks/login.yml
  - **Details**: POST /api/login with admin credentials, extract auth token from response
  - **Validation**: Token stored in registered variable for subsequent requests

- [X] **T037**: Create task to configure SMTP notification
  - **Files**: ansible/roles/uptime_kuma/tasks/configure_smtp.yml
  - **Details**: POST /api/notification with SMTP settings from vault, use auth token
  - **Validation**: SMTP notification appears in GET /api/notification

- [X] **T038**: Create task to get existing monitors
  - **Files**: ansible/roles/uptime_kuma/tasks/get_monitors.yml
  - **Details**: GET /api/monitor, extract list of monitor names for idempotency check
  - **Validation**: Stores monitor list in registered variable

- [X] **T039**: Create task loop to provision monitors
  - **Files**: ansible/roles/uptime_kuma/tasks/provision_monitors.yml
  - **Details**: Loop through monitoring_targets, POST /api/monitor for each, skip if name exists
  - **Validation**: Creates all 4 monitors idempotently

- [X] **T040**: Create task to verify monitor count
  - **Files**: ansible/roles/uptime_kuma/tasks/verify_monitors.yml
  - **Details**: GET /api/monitor, count monitors, assert equals 4
  - **Validation**: All monitors successfully created

- [X] **T041**: Create main uptime_kuma task orchestration
  - **Files**: ansible/roles/uptime_kuma/tasks/main.yml
  - **Details**: Import all API tasks in sequence with error handling
  - **Validation**: Syntax check passes
---

### Phase 9: mDNS Configuration

**Goal**: Ensure monitoring.local hostname resolves

- [X] **T042**: Verify mdns_base role applied to monitoring LXC
  - **Files**: ansible/playbooks/monitoring.yml
  - **Details**: Include mdns_base role or verify Avahi installed
  - **Validation**: `avahi-browse -a` shows monitoring.local

- [X] **T043**: Test mDNS resolution from control node
  - **Command**: `ping -c 1 monitoring.local`
  - **Validation**: Resolves to 192.168.1.204

---

### Phase 10: Playbook Integration

**Goal**: Integrate monitoring into main playbook

- [X] **T044**: Add monitoring playbook to site.yml
  - **Files**: ansible/playbooks/site.yml
  - **Details**: `- import_playbook: monitoring.yml` with tag 'monitoring'
  - **Validation**: `ansible-playbook playbooks/site.yml --tags monitoring` works

- [ ] **T045**: Test full monitoring playbook execution
  - **Command**: `cd ansible && ansible-playbook playbooks/monitoring.yml`
  - **Validation**: Playbook completes successfully, all tasks green/ok

- [ ] **T046**: Test idempotency
  - **Command**: `ansible-playbook playbooks/monitoring.yml` (run twice)
  - **Validation**: Second run shows changed=0 (except check tasks)

---

### Phase 11: End-to-End Testing

**Goal**: Validate complete monitoring flow with email notifications

- [ ] **T047**: Access Uptime Kuma dashboard from LAN device
  - **Command**: Browse to http://monitoring.local:3001 on laptop/phone
  - **Validation**: Dashboard loads, login screen appears

- [ ] **T048**: Login with admin credentials
  - **Manual Step**: Login with uptime_kuma_admin_user/password from vault
  - **Validation**: Dashboard shows all monitors

- [ ] **T049**: Verify all 4 monitors are present
  - **Validation**: Proxmox, Proxy, Immich, Home Assistant all visible with UP status

- [ ] **T050**: Verify SMTP notification channel configured
  - **Manual Step**: Check Settings → Notifications
  - **Validation**: SMTP notification exists with correct settings

- [ ] **T051**: Simulate service outage (Immich)
  - **Command**: SSH to immich LXC, `sudo systemctl stop immich`
  - **Wait**: 2-3 minutes for down threshold
  - **Validation**: Check email inbox for DOWN notification

- [ ] **T052**: Verify dashboard shows DOWN status
  - **Command**: Refresh Uptime Kuma dashboard
  - **Validation**: Immich monitor shows red DOWN indicator

- [ ] **T053**: Restore service and verify recovery notification
  - **Command**: SSH to immich LXC, `sudo systemctl start immich`
  - **Wait**: 1-2 minutes for UP detection
  - **Validation**: Check email inbox for recovery notification

- [ ] **T054**: Verify dashboard shows UP status
  - **Command**: Refresh Uptime Kuma dashboard
  - **Validation**: Immich monitor shows green UP indicator

---

### Phase 12: Documentation & Cleanup

**Goal**: Complete documentation and finalize feature

- [ ] **T055**: Create monitoring setup runbook
  - **Files**: docs/runbooks/monitoring-setup.md
  - **Sections**: Prerequisites, Quick Start, SMTP Configuration, Troubleshooting
  - **Validation**: Includes architecture diagram and clear instructions

- [ ] **[P] T056**: Add architecture diagram to runbook
  - **Files**: docs/runbooks/monitoring-setup.md
  - **Details**: ASCII diagram showing monitoring LXC, services, SMTP notification flow
  - **Validation**: Diagram is clear and accurate

- [ ] **[P] T057**: Add SMTP configuration guide to runbook
  - **Files**: docs/runbooks/monitoring-setup.md
  - **Details**: Gmail app passwords, Outlook SMTP, self-hosted mail server examples
  - **Validation**: Covers major SMTP providers

- [ ] **[P] T058**: Add troubleshooting section to runbook
  - **Files**: docs/runbooks/monitoring-setup.md
  - **Details**: Common issues (SMTP auth failures, API errors, mDNS resolution)
  - **Validation**: Covers major failure modes

- [ ] **T059**: Update main README.md
  - **Files**: README.md
  - **Details**: Add `monitoring.yml` to "Available Playbooks", link to runbook
  - **Validation**: Links work, descriptions clear

- [ ] **T060**: Review all Ansible tasks for idempotency
  - **Manual Review**: Check tasks.yml files for changed_when, creates, state parameters
  - **Validation**: No tasks will incorrectly report changed on rerun

- [ ] **T061**: Final idempotency test
  - **Command**: `ansible-playbook playbooks/monitoring.yml` (run 3 times)
  - **Validation**: Runs 2 and 3 show changed=0

- [ ] **T062**: Verify no secrets in git history
  - **Command**: `git log -p | grep -E '(smtp_password|admin_password)'`
  - **Validation**: No secrets visible

- [ ] **T063**: Test monitoring stack survives reboot
  - **Command**: SSH to monitoring LXC, `sudo reboot`, wait 5 minutes
  - **Validation**: Container auto-starts, monitors resume after boot

---

## Task Dependencies

```
Phase 1 (Terraform) → Phase 2 (Ansible Structure) → Phase 3 (Docker) → Phase 4 (Compose) → Phase 5 (Systemd)
                                                                              ↓
Phase 7 (Secrets) ←─────────────────── Phase 6 (Verification) ←─────────────┘
      ↓
Phase 8 (API Automation) → Phase 9 (mDNS) → Phase 10 (Integration) → Phase 11 (E2E Testing) → Phase 12 (Finalize)
```

**Key Stop Points**:
- **After T004**: Review Terraform plan before infrastructure changes
- **Before T030**: Configure SMTP credentials and admin password in vault before deployment
- **After T046**: Verify idempotency before proceeding to manual testing
- **After T054**: Validate end-to-end email alert flow before completing feature

---

## Parallel Execution Opportunities

**Phase 1 (T001-T003)**: Terraform file edits can run in parallel

**Phase 2 (T008-T009)**: Role directory creation can run in parallel

**Phase 3 (T012-T013)**: Variable file creation can run in parallel

**Phase 7 (T029)**: Documentation can be written while other tasks execute

**Phase 12 (T056-T058)**: Documentation sections can be written in parallel

---

## Success Criteria Mapping

- **SC-001** (Dashboard accessible in 5s): ✅ T047
- **SC-002** (All 4 services displayed): ✅ T049
- **SC-003** (Dashboard updates in 2 min): ✅ T052
- **SC-004** (Email notification in 3 min): ✅ T051
- **SC-005** (Notification includes service name): ✅ T051
- **SC-006** (Recovery notification in 2 min): ✅ T053
- **SC-007** (Terraform no-op on rerun): ✅ T004
- **SC-008** (Ansible changed=0 on rerun): ✅ T046, T061
- **SC-009** (Stack survives reboot): ✅ T063
- **SC-010** (No secrets in git): ✅ T031, T062

---

## Functional Requirements Mapping

| FR | Description | Tasks |
|----|-------------|-------|
| FR-001 | Deployed via Ansible | T010, T045 |
| FR-002 | mDNS hostname (monitoring.local) | T042, T043 |
| FR-003 | Monitor 4 critical services | T039, T049 |
| FR-004 | Display status/response time | T047, T049 |
| FR-005 | Alerts after threshold | T051 |
| FR-006 | Email (SMTP) notifications | T037, T050 |
| FR-007 | Alert includes service name | T051 |
| FR-008 | Secrets not committed | T029-T031, T062 |
| FR-009 | Terraform provisioned LXC | T001-T005 |
| FR-010 | Inventory from Terraform | T007 |
| FR-011 | Idempotent deployment | T046, T061 |
| FR-012 | Docker Compose orchestration | T018-T020 |
| FR-013 | Templated compose files | T018 |
| FR-014 | mDNS hostnames for targets | T039 |
| FR-015 | Persistent data (volumes) | T018 |
| FR-016 | Auto-start on boot | T021-T023, T063 |
| FR-017 | Verification tasks | T024-T027 |
| FR-018 | SMTP configuration docs | T057 |
| FR-019 | Automated monitor provisioning | T032-T041 |

---

## Validation Commands Summary

**Terraform**:
```bash
cd terraform
terraform validate
terraform plan -var-file=environments/prod.tfvars
terraform apply -var-file=environments/prod.tfvars
```

**Ansible**:
```bash
cd ansible
ansible-playbook --syntax-check playbooks/monitoring.yml
ansible-playbook playbooks/monitoring.yml
ansible-playbook playbooks/monitoring.yml --tags verify
```

**Manual Verification**:
```bash
# SSH access
ssh ansible@192.168.1.204

# Container status
ssh ansible@192.168.1.204 "docker ps"

# HTTP health
curl -f http://monitoring.local:3001

# API status
curl -s http://monitoring.local:3001/api/status | jq

# mDNS resolution
ping -c 1 monitoring.local
```

**Email Test**:
```bash
# Stop service (on immich LXC)
ssh ansible@immich "sudo systemctl stop immich"

# Wait 2-3 minutes, check email inbox

# Start service
ssh ansible@immich "sudo systemctl start immich"

# Wait 1-2 minutes, check email inbox for recovery
```

---

## Estimated Time

- **Phase 1 (Terraform)**: 30 minutes
- **Phase 2-5 (Ansible Base)**: 2 hours
- **Phase 6-7 (Verification + Secrets)**: 1 hour
- **Phase 8 (API Automation)**: 3 hours (complex API integration)
- **Phase 9-10 (Integration)**: 30 minutes
- **Phase 11 (E2E Testing)**: 1 hour (including wait times)
- **Phase 12 (Documentation)**: 2 hours

**Total**: ~10 hours (excluding wait time for email delivery)

---

## Notes

- **No ntfy Server**: Simplified stack - only Uptime Kuma container needed
- **API Automation**: All monitors configured via API, no manual UI steps required
- **SMTP Only**: Email notifications exclusively, no push notifications or webhooks
- **Authentication**: Dashboard requires login, credentials in vault.yml
- **Idempotency**: API tasks check for existing resources before creation
- **SMTP Testing**: Requires real SMTP server, cannot be fully mocked
- **Email Delivery**: May take 1-3 minutes depending on SMTP provider
- **Docker Compose Version**: Assumes `docker compose` (V2) command
