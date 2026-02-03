# Feature Specification: Tailscale Remote Access IaC

**Feature Branch**: `008b-tailscale-remote-access-iac`
**Created**: December 20, 2025
**Status**: Draft
**Input**: User description: "Make the Tailscale subnet-router + ACL setup fully reproducible from the repo"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Rebuild Proxmox from Scratch (Priority: P1)

As a homelab administrator, when I rebuild my Proxmox host from scratch, I need to restore full Tailscale subnet router functionality by running a single Ansible playbook, so I can regain secure remote access to my LAN services without manually reconfiguring networking settings.

**Why this priority**: This is the core disaster recovery scenario. Without this, rebuilding the Proxmox host requires manual reconfiguration of IP forwarding, subnet routes, and Tailscale settings - error-prone and not documented. This delivers immediate value by making the entire setup reproducible.

**Independent Test**: Can be fully tested by (1) running the Ansible playbook against a fresh Proxmox install, (2) verifying IP forwarding is enabled and persisted, (3) confirming subnet routes are advertised to Tailscale, and (4) accessing LAN services remotely via Tailscale from a mobile device.

**Acceptance Scenarios**:

1. **Given** a fresh Proxmox installation without Tailscale, **When** I run the tailscale_router Ansible role, **Then** Tailscale is installed, authenticated, IP forwarding is enabled and persisted, and subnet route 192.168.1.0/24 is advertised
2. **Given** Tailscale is already configured, **When** I rerun the Ansible role, **Then** no changes are made (idempotent) and all settings remain correct (existing persistence file verified and preserved)
3. **Given** IP forwarding persistence file exists with correct values, **When** I run the Ansible role, **Then** the file is verified and preserved unchanged

---

### User Story 2 - Understand ACL Identity Configuration (Priority: P1)

As a homelab administrator using GitHub authentication with Tailscale, I need clear documentation explaining that ACL group identities must use the format `xxx@github` (not email addresses), so I can avoid the common pitfall where all traffic gets denied due to identity mismatch.

**Why this priority**: This is the root cause of the most confusing failure mode. Without this knowledge, users will configure ACLs with email addresses, see subnet routes advertised correctly, but have all access denied with no clear error message. This documentation prevents hours of troubleshooting.

**Independent Test**: Can be tested by reviewing documentation and verifying it includes: (1) explicit warning about GitHub auth identity format, (2) example ACL showing correct `xxx@github` format, (3) explanation of symptoms when identity is wrong (denied access despite routes working), and (4) how to find the correct identity in Tailscale admin console.

**Acceptance Scenarios**:

1. **Given** documentation is available, **When** I read the Tailscale setup section, **Then** I see a prominent warning about GitHub auth identity format with concrete examples
2. **Given** the ACL file in the repo, **When** I review it, **Then** I see correctly formatted GitHub identities (not emails) and inline comments explaining the format requirement
3. **Given** I'm troubleshooting access denial, **When** I consult the documentation, **Then** I find a troubleshooting section that explains identity mismatch as the first thing to check

---

### User Story 3 - Verify Tailscale Configuration (Priority: P2)

As a homelab administrator, I need a simple way to verify that Tailscale subnet routing is properly configured on the Proxmox host, so I can quickly diagnose issues without manually checking multiple system settings.

**Why this priority**: After running the automation or during troubleshooting, operators need quick visibility into the actual configuration state. This reduces debugging time and provides confidence that the setup is correct.

**Independent Test**: Can be tested by running diagnostic commands/playbook and verifying the output includes: (1) Tailscale status showing connection state, (2) Tailscale IP address, (3) advertised routes including 192.168.1.0/24, (4) IP forwarding status for both IPv4 and IPv6, and (5) clear pass/fail indicators for each check.

**Acceptance Scenarios**:

1. **Given** Tailscale is properly configured, **When** I run the diagnostic task, **Then** I see structured Ansible output with all checks showing ok/success status
2. **Given** IP forwarding is disabled, **When** I run the diagnostic task, **Then** I see a failed task with clear message showing current value (0) vs expected value (1) for IP forwarding check
3. **Given** subnet routes are not advertised, **When** I run the diagnostic task, **Then** I see a failed task indicating advertised routes do not include 192.168.1.0/24

---

### User Story 4 - Apply ACL Changes Manually (Priority: P2)

As a homelab administrator, when I need to update Tailscale ACL policies (e.g., add new services, modify permissions), I need clear documentation on how to manually apply the ACL JSON from the repo to the Tailscale admin console, so I can safely update access control without automation risks.

**Why this priority**: ACL changes are infrequent but critical. Automating ACL application via API is risky (could lock out all users if misconfigured). Manual application with good documentation provides safety while the setup matures.

**Independent Test**: Can be tested by following the documented procedure to: (1) edit the ACL JSON file in the repo, (2) commit changes, (3) navigate to Tailscale admin console, (4) paste the ACL JSON, (5) validate and save, and (6) verify changes take effect without breaking access.

**Acceptance Scenarios**:

1. **Given** ACL documentation exists, **When** I need to add a new service to allowed destinations, **Then** I find step-by-step instructions for editing the ACL file and applying it
2. **Given** I apply an ACL change in the Tailscale admin console, **When** I save the change, **Then** the documentation warns me to test access before closing the admin console (in case I locked myself out)
3. **Given** the ACL file in the repo, **When** I review it, **Then** I see inline comments explaining the structure and how to add new rules safely

---

### User Story 5 - Verify Remote Access from Mobile Device (Priority: P3)

As a homelab user away from home, I need a verification checklist to confirm that remote access is working correctly via Tailscale, so I can access both the Proxmox host directly and LAN services through the subnet router.

**Why this priority**: This is the end-to-end validation that everything works from the user's perspective. While lower priority for initial setup, it's essential for confirming the entire system functions as intended.

**Independent Test**: Can be tested independently by following a checklist from a mobile device on cellular (not home WiFi): (1) connect to Tailscale VPN, (2) access Proxmox web UI at https://100.67.156.70:8006, (3) access a LAN service like Immich at http://192.168.1.213:2283, and (4) verify in Tailscale admin that subnet routes show as active and warnings are cleared.

**Acceptance Scenarios**:

1. **Given** I'm on cellular data with Tailscale connected, **When** I navigate to the Proxmox Tailscale IP, **Then** I can access the Proxmox web UI without errors
2. **Given** I'm on cellular data with Tailscale connected, **When** I navigate to a LAN IP address like 192.168.1.213, **Then** I can access the LAN service (e.g., Immich) through the subnet router
3. **Given** I check the Tailscale admin console, **When** I view the pve device, **Then** I see subnet route 192.168.1.0/24 marked as advertised and active with no warnings about IP forwarding

---

### Edge Cases

- What happens when Tailscale authentication is not yet completed? (Role should check `tailscale status` first; if not authenticated and no auth key available, provide clear instructions for running `tailscale up` manually)
- How does the system handle rerunning the role when Tailscale is already configured? (Must be idempotent with no unnecessary changes; detects existing auth and preserves it)
- What happens if the user has multiple subnet routes already advertised? (Should preserve existing routes and add/update as needed)
- How does the system behave if IP forwarding is enabled but not persisted? (Should add persistence config without disrupting current state)
- What happens when the operator forgets to update ACL after changing the setup? (Documentation should include a reminder/checklist)
- How does verification handle temporary network issues? (Diagnostics should distinguish between configuration errors and transient network problems)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Ansible role MUST install Tailscale package if not already present on the Proxmox host
- **FR-002**: Ansible role MUST ensure tailscaled service is enabled and running
- **FR-003**: Ansible role MUST enable IPv4 IP forwarding (net.ipv4.ip_forward = 1)
- **FR-004**: Ansible role MUST enable IPv6 forwarding (net.ipv6.conf.all.forwarding = 1)
- **FR-005**: Ansible role MUST ensure IP forwarding configuration is persisted in /etc/sysctl.d/99-tailscale-subnet-router.conf (verify existing file or create if missing with correct IPv4 and IPv6 forwarding values)
- **FR-006**: Ansible role MUST run `sysctl --system` when the sysctl configuration file changes
- **FR-007**: Ansible role MUST configure Tailscale to advertise subnet route 192.168.1.0/24 using `tailscale up --advertise-routes=192.168.1.0/24` (no additional flags required; minimal configuration matching working setup)
- **FR-008**: Ansible role MUST support authentication key via optional secret variable `tailscale_auth_key` for non-interactive fresh installs, provided either through ansible-vault encrypted file (e.g., ansible/group_vars/proxmox_hosts/vault.yml) OR command line --extra-vars (role detects existing authentication and skips if present; auth key only used when Tailscale not yet authenticated; variable never committed to repo)
- **FR-009**: Ansible role MUST detect existing Tailscale authentication and preserve it (no re-authentication or key rotation if already connected)
- **FR-010**: Ansible role MUST provide structured diagnostic output with clear pass/fail indicators for each check using ansible.builtin.assert module with descriptive fail_msg and success_msg: Tailscale connection status, Tailscale IP address, advertised routes (including 192.168.1.0/24), IPv4 forwarding status (current vs expected value), IPv6 forwarding status (current vs expected value)
- **FR-011**: Repository MUST contain ACL JSON template file at docs/tailscale-acl.example.json using correct GitHub identity format (`xxx@github` not email) with placeholder identities (e.g., user1@github, admin@github); real ACL with actual identities applied manually per FR-014
- **FR-012**: Repository MUST NOT commit any secrets (no auth keys, no API tokens, no real user identities in ACL); .gitignore MUST block all common secret file patterns unconditionally
- **FR-013**: Documentation at docs/runbooks/tailscale-setup.md MUST explain the identity format requirement for GitHub-authenticated tailnets
- **FR-014**: Documentation at docs/runbooks/tailscale-setup.md MUST provide step-by-step instructions for manually applying ACL changes from docs/tailscale-acl.example.json to Tailscale admin console
- **FR-015**: Documentation at docs/runbooks/tailscale-setup.md MUST include verification checklist for testing remote access from mobile device
- **FR-016**: Ansible role MUST be idempotent (rerunning produces no changes if already configured); tasks MUST check current state before making changes and use changed_when conditions to report true idempotency (e.g., check existing sysctl file content, check current advertised routes before running tailscale up)
- **FR-017**: Ansible role MUST detect authentication state before attempting configuration (check `tailscale status`); if not authenticated and no auth key provided, fail with clear instructions for manual authentication
- **FR-018**: Documentation at docs/runbooks/tailscale-setup.md MUST reference the ACL JSON file location at docs/tailscale-acl.example.json
- **FR-019**: Playbook MUST provide tags or separate playbook for running only Tailscale configuration (e.g., `ansible-playbook playbooks/tailscale.yml` or `--tags tailscale`)

### Key Entities *(include if feature involves data)*

- **Proxmox Host (pve)**: Physical server running Proxmox VE that acts as the Tailscale subnet router
  - Attributes: LAN IP (192.168.1.112), Tailscale IP (100.67.156.70), subnet routes advertised (192.168.1.0/24)
  - Role: Gateway between Tailscale mesh network and local LAN

- **ACL Policy**: JSON configuration defining access control rules in Tailscale
  - Attributes: groups (admin users), acls (traffic rules), tagOwners (device tags)
  - Location: Committed to repo at documented path
  - Critical field: group membership using GitHub identity format (`xxx@github`)

- **Subnet Route**: Network route advertised by pve to Tailscale mesh
  - Attributes: CIDR (192.168.1.0/24), status (advertised/active), device (pve)
  - Enables: Remote access to all LAN services through Tailscale VPN

- **IP Forwarding Configuration**: System-level kernel parameters
  - Attributes: IPv4 forwarding (net.ipv4.ip_forward), IPv6 forwarding (net.ipv6.conf.all.forwarding)
  - Persistence: /etc/sysctl.d/99-tailscale-subnet-router.conf
  - Required for: Routing traffic between Tailscale interface and LAN interface

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After running the Ansible role against pve, `/etc/sysctl.d/99-tailscale-subnet-router.conf` exists with correct IPv4 and IPv6 forwarding values (verifiable via file check)
- **SC-002**: After running the Ansible role, `sysctl -n net.ipv4.ip_forward` returns `1` and `sysctl -n net.ipv6.conf.all.forwarding` returns `1` (verifiable via command execution)
- **SC-003**: After running the Ansible role, `tailscale debug prefs` output includes AdvertiseRoutes containing 192.168.1.0/24 (verifiable via command grep)
- **SC-004**: From a mobile device on cellular with Tailscale connected, Proxmox web UI at https://100.67.156.70:8006 is accessible (verifiable via manual test)
- **SC-005**: From a mobile device on cellular with Tailscale connected, LAN service at http://192.168.1.213:2283 is accessible through subnet router (verifiable via manual test)
- **SC-006**: In Tailscale admin console, pve device shows subnet route 192.168.1.0/24 as advertised and active with no IP forwarding warnings (verifiable via admin UI check)
- **SC-007**: Rerunning the Ansible role against already-configured pve with configuration tasks only (--tags install,configure, excluding verification tasks) results in 0 changes and ok status for all tasks (verifiable via Ansible output showing "changed=0")
- **SC-008**: Documentation at docs/runbooks/tailscale-setup.md includes at least 3 explicit warnings or explanations about GitHub identity format requirements (verifiable via documentation review)
- **SC-009**: ACL JSON template file in repo at docs/tailscale-acl.example.json uses GitHub identity format (`xxx@github`) with placeholder identities for all user references, clearly marked as EXAMPLE/TEMPLATE (verifiable via file review)
- **SC-010**: Running diagnostic tasks outputs structured Ansible results with all required checks (Tailscale status, IPs, routes, forwarding status) showing pass/fail status per check (verifiable via playbook execution showing ok/failed for each task)

## Scope & Boundaries

### In Scope

- Ansible role for configuring Tailscale subnet router on pve
- IP forwarding configuration and persistence
- Subnet route advertisement for 192.168.1.0/24
- Diagnostic tasks for operator verification
- ACL JSON template file at docs/tailscale-acl.example.json (already exists with placeholder identities, maintained as example)
- Operational runbook at docs/runbooks/tailscale-setup.md explaining identity format requirements, manual ACL application, and verification procedures
- Verification checklist for remote access testing
- Secret handling for Tailscale auth keys (via git-ignored file or ansible-vault)

### Out of Scope

- Automatic ACL application via Tailscale API (optional future enhancement)
- Tailscale installation on other devices (focus is pve only)
- Firewall rule configuration (assumes existing firewall allows necessary traffic)
- VPN client setup on mobile devices (user handles manually via Tailscale app)
- Monitoring/alerting for Tailscale connectivity issues
- Exit node configuration (only subnet routing, not exit node)
- MagicDNS configuration (using IPs directly)
- Key management for rotating Tailscale auth keys

## Assumptions

- Proxmox host (pve) has internet connectivity for Tailscale authentication
- User has admin access to Tailscale admin console for ACL management
- User has already created a Tailscale account and tailnet
- GitHub authentication is already configured for the Tailscale tailnet
- User knows their GitHub identity (xxx@github format) or can find it in Tailscale admin
- Tailscale package repository is accessible from pve (or package is already cached)
- Ansible control node has SSH access to pve
- LAN subnet 192.168.1.0/24 is stable and won't change
- No conflicting VPN or routing software is installed on pve
- User has mobile device with Tailscale app installed for testing

## Dependencies

- **Proxmox VE** (already installed on pve)
- **Tailscale service**: Available package from Tailscale repository or Debian repos
- **Ansible**: Control node with ansible installed (already in use for this homelab)
- **SSH access**: Ansible must be able to connect to pve as root or with sudo
- **Internet connectivity**: Required for Tailscale authentication and coordination server communication
- **GitHub account**: Required if using GitHub auth for Tailscale (already in use)
- **Tailscale admin console access**: Required for verifying subnet routes and applying ACL changes

## Risks & Mitigations

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Tailscale auth fails during automated run | High - blocks entire setup | Medium | Provide clear error message with instructions. Support auth key via secret variable for non-interactive runs. |
| ACL misconfiguration locks out all users | High - loss of remote access | Low | Manual ACL application only (no automation). Documentation includes validation steps. Keep Tailscale admin console open until access verified. |
| IP forwarding changes break existing network setup | Medium - connectivity issues | Low | Configuration is additive only (enables forwarding). Changes are reversible via sysctl. |
| Rerunning role breaks existing Tailscale setup | Medium - service disruption | Low | Role is idempotent. Uses `tailscale up` which is safe to rerun with same parameters. |
| Secrets accidentally committed to repo | High - security breach | Low | Use .gitignore for secret files. Document secret handling clearly. Code review before commits. |
| GitHub identity format misunderstood | High - access denied despite correct setup | High (common) | Prominent documentation warning. Example ACL with correct format. Troubleshooting section addresses this first. |

## Clarifications

### Session 2024-12-20

- Q: Since you have a working Tailscale setup on pve, how is it currently authenticated? → A: Manual authentication already done - role should detect and skip auth if already authenticated, only use auth key for fresh installs
- Q: How should the diagnostic verification task present its output? → A: Structured Ansible output with clear pass/fail per check
- Q: Your working setup has IP forwarding enabled. How was it configured - temporarily via sysctl command, or already persisted in a config file? → A: Already persisted in /etc/sysctl.d/99-tailscale-subnet-router.conf (initially configured temporarily, then persisted)
- Q: When you ran `tailscale up` to configure subnet routing, did you use any additional flags beyond `--advertise-routes=192.168.1.0/24`? → A: Only --advertise-routes flag used
- Q: Where should the Tailscale setup and ACL management documentation be placed? → A: New file docs/runbooks/tailscale-setup.md

## Open Questions

None - all requirements clarified in user input.

## References

- Tailscale subnet router documentation: https://tailscale.com/kb/1019/subnets/
- Tailscale ACL documentation: https://tailscale.com/kb/1018/acls/
- Existing Proxmox setup: specs/001-bootstrap-proxmox-iac/
- Current ACL template file: docs/tailscale-acl.example.json (example with placeholder GitHub identities, not production ACL)
