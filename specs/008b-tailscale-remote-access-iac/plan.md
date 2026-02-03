# Implementation Plan: Tailscale Remote Access IaC

**Feature**: 008b-tailscale-remote-access-iac
**Goal**: Make Tailscale subnet-router + ACL setup fully reproducible from repo
**Context**: Working Tailscale configuration exists on pve (manual setup); codifying as Infrastructure as Code

## High-Level Approach

This feature codifies an existing, working Tailscale subnet router setup on the Proxmox host (pve) into Ansible automation. The implementation uses Ansible roles and playbooks to make the configuration reproducible for disaster recovery scenarios.

**Implementation Strategy**: Ansible-only (no Terraform changes)
- **Why**: Tailscale configuration is host-level setup, not infrastructure provisioning
- **Constitution Alignment**: Ansible owns configuration inside machines (Principle III)

## Architecture Overview

### Current State (Manual Configuration)
```
┌─────────────────────────────────────────────────────────────┐
│ Proxmox Host (pve)                                          │
│ - LAN IP: 192.168.1.112                                     │
│ - Tailscale IP: 100.67.156.70                               │
│ - IP forwarding: enabled (manual sysctl commands)           │
│ - Persistence: /etc/sysctl.d/99-tailscale-subnet-router.conf│
│ - Tailscale: authenticated, advertising 192.168.1.0/24      │
└─────────────────────────────────────────────────────────────┘
                        │
                        ↓ (subnet router)
        ┌───────────────────────────────┐
        │   Tailscale Mesh Network      │
        │   (100.x.x.x addresses)       │
        └───────────────────────────────┘
                        │
                        ↓ (remote access)
        ┌───────────────────────────────┐
        │ Mobile Devices / Remote Users │
        │ Access: pve + LAN services    │
        └───────────────────────────────┘

ACL Management: Manual copy/paste to Tailscale admin console
ACL File: docs/tailscale-acl.example.json (template with placeholders)
```

### Target State (Automated Configuration)
```
┌─────────────────────────────────────────────────────────────┐
│ ansible-playbook playbooks/tailscale.yml                    │
│   ↓                                                          │
│ ansible/roles/tailscale_router/                             │
│   ├── tasks/                                                 │
│   │   ├── install.yml          (apt install tailscale)      │
│   │   ├── service.yml           (enable/start tailscaled)   │
│   │   ├── check_auth.yml        (detect auth status)        │
│   │   ├── authenticate.yml      (conditional auth)          │
│   │   ├── ip_forwarding.yml     (deploy sysctl config)      │
│   │   ├── subnet_routes.yml     (advertise 192.168.1.0/24)  │
│   │   ├── verify_*.yml          (diagnostics)               │
│   │   └── main.yml              (orchestration)             │
│   ├── templates/                                             │
│   │   └── 99-tailscale-subnet-router.conf.j2                │
│   ├── handlers/main.yml         (sysctl reload)             │
│   ├── defaults/main.yml         (variables)                 │
│   └── meta/main.yml             (role metadata)             │
└─────────────────────────────────────────────────────────────┘

Documentation: docs/runbooks/tailscale-setup.md
- GitHub identity format warnings (xxx@github not email)
- Manual ACL application procedure
- Verification checklists
- Mobile remote access testing
```

## Component Breakdown

### 1. Ansible Role: `tailscale_router`

**Purpose**: Configure Proxmox host as Tailscale subnet router

**Responsibilities**:
- Install Tailscale package from Debian repos
- Enable and start tailscaled service
- Detect existing authentication (preserve if present)
- Support optional auth key for fresh installs (ansible-vault or --extra-vars)
- Deploy IP forwarding sysctl configuration (idempotent)
- Advertise subnet route 192.168.1.0/24 (idempotent)
- Provide diagnostic verification tasks

**Key Design Decisions**:
1. **Idempotency**: All tasks must be safe to rerun
   - Use ansible.builtin.template for sysctl file (automatic idempotency)
   - Check current advertised routes before running `tailscale up`
   - Use `changed_when` conditions to report accurate state changes

2. **Authentication Handling**:
   - Check `tailscale status` first to detect existing auth
   - Skip auth if already connected (preserve existing setup)
   - Use `tailscale_auth_key` variable only if provided AND not authenticated
   - Fail with clear instructions if neither condition met

3. **Verification Approach**:
   - Separate verification tasks using `ansible.builtin.assert`
   - Each check outputs clear pass/fail with current vs expected values
   - Separate playbook (verify_tailscale.yml) for diagnostics
   - Tags support: install, configure, verify

**Variables** (defaults/main.yml):
```yaml
tailscale_subnet_route: "192.168.1.0/24"
tailscale_auth_key: ""  # Optional, provided via vault or CLI
```

### 2. Main Playbook: `tailscale.yml`

**Purpose**: Entry point for Tailscale configuration

**Target**: `proxmox_hosts` group (pve)

**Structure**:
```yaml
---
- name: Configure Tailscale subnet router
  hosts: proxmox_hosts
  become: true
  roles:
    - tailscale_router
```

**Usage**:
- Full configuration: `ansible-playbook playbooks/tailscale.yml`
- Install only: `ansible-playbook playbooks/tailscale.yml --tags install`
- Verify only: `ansible-playbook playbooks/verify_tailscale.yml`
- With auth key: `ansible-playbook playbooks/tailscale.yml --extra-vars "tailscale_auth_key=tskey-..."`

### 3. Verification Playbook: `verify_tailscale.yml`

**Purpose**: Diagnostic playbook for troubleshooting

**Checks**:
- Tailscale connection status (logged in/connected)
- Tailscale IP address (display current IP)
- Advertised routes (192.168.1.0/24 present)
- IPv4 forwarding (net.ipv4.ip_forward = 1)
- IPv6 forwarding (net.ipv6.conf.all.forwarding = 1)
- Persistence file exists with correct content

**Output Format**: Ansible assert failures show current vs expected

### 4. Documentation: `docs/runbooks/tailscale-setup.md`

**Purpose**: Operational runbook for Tailscale management

**Sections**:
1. **Overview**: Architecture, purpose, disaster recovery use case
2. **Prerequisites**: Tailscale account, GitHub auth, admin access
3. **Quick Start**: How to run playbooks
4. **Configuration**: Role variables, auth key handling
5. **⚠️ CRITICAL: GitHub Identity Format**: 3+ warnings, examples, symptoms
6. **Finding Your GitHub Identity**: Step-by-step in admin console
7. **ACL Management**: Structure, editing, applying manually
8. **⚠️ Safety Warnings**: Test before closing admin console, rollback
9. **Verification**: Running diagnostics, interpreting results
10. **Remote Access Verification**: Mobile device checklist
11. **Troubleshooting**: Common issues, identity mismatch priority
12. **Architecture**: ASCII diagram showing subnet router role
13. **Security Considerations**: Auth key handling, ACL principles
14. **Disaster Recovery**: How this enables pve rebuild

### 5. ACL Template: `docs/tailscale-acl.example.json`

**Purpose**: Template ACL with placeholder identities

**Status**: Already exists, needs comments added

**Updates Required**:
- Header comment: "EXAMPLE/TEMPLATE - Use placeholders, not real identities"
- Inline comments explaining GitHub identity format (xxx@github)
- Examples of common patterns (adding services, modifying permissions)
- Note: Real ACL applied manually per runbook

## File Structure

```
ansible/
├── playbooks/
│   ├── tailscale.yml                    # NEW: Main configuration playbook
│   └── verify_tailscale.yml             # NEW: Verification playbook
└── roles/
    └── tailscale_router/                # NEW: Role directory
        ├── tasks/
        │   ├── main.yml                 # Orchestration
        │   ├── install.yml              # Package installation
        │   ├── service.yml              # Service management
        │   ├── check_auth.yml           # Authentication detection
        │   ├── authenticate.yml         # Conditional auth
        │   ├── ip_forwarding.yml        # Sysctl configuration
        │   ├── subnet_routes.yml        # Route advertisement
        │   ├── verify_tailscale_status.yml
        │   ├── verify_tailscale_ip.yml
        │   ├── verify_routes.yml
        │   ├── verify_ipv4_forwarding.yml
        │   ├── verify_ipv6_forwarding.yml
        │   └── verify_persistence.yml
        ├── templates/
        │   └── 99-tailscale-subnet-router.conf.j2  # Sysctl template
        ├── handlers/
        │   └── main.yml                 # Sysctl reload handler
        ├── defaults/
        │   └── main.yml                 # Default variables
        └── meta/
            └── main.yml                 # Role metadata

docs/
├── runbooks/
│   └── tailscale-setup.md               # NEW: Operational runbook
└── tailscale-acl.example.json           # EXISTING: Add comments

README.md                                # UPDATE: Add playbook reference
.gitignore                               # UPDATE: Add secret patterns
```

## Implementation Phases

### Phase 1: Setup (Shared Infrastructure + Constitution Compliance)
**Goal**: Create role structure, playbook scaffolding, and ensure secrets protection before any secret handling

**Deliverables**:
- Role structure (directories, meta, defaults, handlers)
- Main playbook (tailscale.yml)
- **[CRITICAL]** .gitignore verification (Constitution Principle II compliance - MUST execute before Phase 2)

**Tasks**: T001-T005 (5 tasks)

**Success Criteria**:
- Role directory structure exists
- Main playbook created
- .gitignore patterns verified/added for all secret file types

**Constitution Note**: T005 (.gitignore verification) is NON-NEGOTIABLE and must complete before Phase 2 begins

### Phase 2: US1 Implementation (MVP Core)
**Goal**: Working playbook that configures pve as Tailscale subnet router

**Deliverables**:
- Core tasks: install, service, auth detection, auth handling
- IP forwarding configuration (template + task)
- Subnet route advertisement
- Orchestration (main.yml)

**Tasks**: T006-T015 (10 tasks)

**Success Criteria**:
- Run playbook against pve → idempotent (changed=0)
- IP forwarding persisted in /etc/sysctl.d/99-tailscale-subnet-router.conf
- Subnet route 192.168.1.0/24 advertised
- Remote access works from mobile device

**Testing**: Run against existing pve setup (should be no-op)

**MVP Delivery**: Phase 1 Setup (5 tasks) + Phase 2 US1 (10 tasks) = 15 total tasks

### Phase 3: US3 Verification (Diagnostics)
**Goal**: Verification playbook for troubleshooting

**Deliverables**:
- Verification tasks (6 checks)
- Verification playbook (verify_tailscale.yml)
- Tag support in main.yml

**Tasks**: T016-T023 (8 tasks)

**Success Criteria**:
- Run verify playbook → all checks pass
- Failed checks show current vs expected values

### Phase 4: US2 Documentation (Critical - GitHub Identity Format)
**Goal**: Runbook preventing common pitfalls

**Deliverables**:
- docs/runbooks/tailscale-setup.md (comprehensive)
- Comments in docs/tailscale-acl.example.json

**Tasks**: T024-T032 (9 tasks)

**Success Criteria**:
- 3+ explicit warnings about GitHub identity format
- Step-by-step procedures for setup
- Troubleshooting section

### Phase 5: US4 ACL Management
**Goal**: Safe manual ACL application procedures

**Deliverables**:
- ACL management documentation
- Safety warnings and rollback procedures

**Tasks**: T033-T038 (6 tasks)

**Success Criteria**:
- Step-by-step ACL application procedure
- Safety warnings and testing checklist

### Phase 6: US5 Mobile Verification
**Goal**: End-to-end remote access validation

**Deliverables**:
- Mobile verification checklist (minimum 4 steps)
- Admin console verification procedures

**Tasks**: T039-T043 (5 tasks)

**Success Criteria**:
- Comprehensive mobile testing checklist
- Expected behavior documented

### Phase 7: Polish & Final Validation
**Goal**: Production-ready with complete documentation

**Deliverables**:
- Architecture diagrams
- Security considerations
- README updates
- Final validation (FR coverage, idempotency)

**Tasks**: T044-T050 (7 tasks)

**Success Criteria**:
- All documentation complete
- All 19 FRs validated
- Idempotency test passes

## Critical Implementation Notes

### Constitution Compliance

**Secrets Policy (NON-NEGOTIABLE)**:
- ❌ Never commit: auth keys, real user identities in ACL
- ✅ ACL file is TEMPLATE with placeholders (user1@github, user2@github)
- ✅ .gitignore must block: `**/vault.yml`, `**/*secret*.yml`, `**/tailscale_auth_key*`
- ✅ Real ACL applied manually via admin console (documented procedure)

**Separation of Concerns**:
- ✅ Ansible only (no Terraform changes - Tailscale is configuration, not provisioning)
- ✅ Targets existing Proxmox host (pve already provisioned by Terraform)

### Idempotency Strategy

**File-based Configuration** (sysctl):
- Use `ansible.builtin.template` module
- Module automatically detects content changes
- Only notifies handler if content differs

**Command-based Configuration** (tailscale up):
- Check current state FIRST: `tailscale status --json | jq`
- Compare desired vs current advertised routes
- Use `changed_when: desired_route not in current_routes.stdout`
- Only run `tailscale up` if route missing

**Authentication**:
- ALWAYS check `tailscale status` first
- Parse output for connection status
- Skip auth entirely if already connected

### Error Handling

**Authentication Failure**:
```
ERROR: Tailscale not authenticated. Either:
  (1) Run 'tailscale up' manually on pve, or
  (2) Provide tailscale_auth_key variable via:
      - ansible-vault: ansible/group_vars/proxmox_hosts/vault.yml
      - CLI: --extra-vars "tailscale_auth_key=tskey-..."

Generate auth key at: https://login.tailscale.com/admin/settings/keys
```

**Verification Failures**:
```
FAILED - IPv4 forwarding disabled: current=0, expected=1
FAILED - Advertised routes missing: current=[], expected=['192.168.1.0/24']
```

## Testing Strategy

### Development Testing
1. **Idempotency**: Run playbook twice, verify changed=0 on second run
2. **Fresh Install Simulation**: Temporarily stop tailscaled, verify auth handling
3. **Verification**: Run verify playbook, trigger failures by disabling settings

### Acceptance Testing
1. **Manual Rerun** (US1): Run against existing pve, verify no changes
2. **Documentation Review** (US2): Count GitHub identity warnings (must be ≥3)
3. **Diagnostics** (US3): Run verification, check structured output
4. **ACL Procedure** (US4): Follow documented steps, test rollback scenario
5. **Mobile Access** (US5): Test from cellular, access pve + LAN service

### Final Validation
- All 19 functional requirements (FR-001 to FR-019) tested
- All 10 success criteria (SC-001 to SC-010) verified
- Constitution compliance checked (.gitignore, no secrets)

## Dependencies

**External**:
- Tailscale package available from Debian repos (assume reachable)
- Existing Proxmox host (pve) with SSH access
- Ansible control node with ansible installed

**Internal**:
- No dependencies on other features
- No Terraform changes required
- No inventory changes (proxmox_hosts group already exists)

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Playbook disrupts working Tailscale setup | HIGH | Test against existing setup first, verify idempotency before fresh install testing |
| Auth key accidentally committed | HIGH | .gitignore patterns enforced, documented in runbook, code review |
| ACL template confused for production | MEDIUM | Clear header comments, "EXAMPLE" in filename, runbook explains |
| Documentation incomplete on identity format | HIGH | Validation checklist requires ≥3 warnings, peer review |
| Idempotency check for tailscale up fails | MEDIUM | Use status --json for reliable parsing, test with route already advertised |

## Success Metrics

**MVP Delivery** (Phases 1-2):
- ✅ Single playbook run configures Tailscale subnet router
- ✅ Idempotent execution (changed=0 on rerun)
- ✅ Verification playbook provides diagnostics
- ✅ Remote access functional from mobile

**Complete Feature** (All Phases):
- ✅ Comprehensive runbook with 3+ identity warnings
- ✅ ACL management documented with safety procedures
- ✅ Mobile verification checklist
- ✅ All 19 FRs implemented, all 10 SCs verified
- ✅ Constitution compliant (no secrets, Ansible-only)

## Out of Scope

Explicitly **NOT** implementing:
- Automatic ACL application via Tailscale API (too risky)
- Tailscale installation on LXCs (pve only)
- Exit node configuration (subnet routing only)
- MagicDNS configuration (using IPs directly)
- Monitoring/alerting for Tailscale status
- Auth key rotation automation

These may be future enhancements but are not part of this feature.
