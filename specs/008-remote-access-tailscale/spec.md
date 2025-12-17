# Feature Specification: Remote Access Baseline (Tailscale + ACLs)

**Feature Branch**: `008-remote-access-tailscale`
**Created**: 2025-12-16
**Status**: Draft

## Clarifications

### Session 2025-12-16
- Q: How should the Tailscale auth key be stored? → A: **Ansible Vault** (Encrypted file).
- Q: What Tailscale tag should be used for the Proxmox host? → A: `tag:proxmox`.
- Q: What Ansible variable name should be used for the auth key? → A: `tailscale_auth_key`.
- Q: What is the default ACL policy? → A: **Default Deny** (Block all by default). *Note: This only affects traffic over the Tailscale interface, not direct physical LAN traffic.*
- Q: What Ansible role name should be used? → A: `tailscale_host`.

## User Scenarios & Testing

### User Story 1 - Remote Admin Access (Priority: P1)

As an administrator, I want to access the Proxmox web UI and SSH into the host from a remote location (e.g., LTE, coffee shop) so that I can manage the infrastructure without being physically present.

**Why this priority**: Critical for maintaining the lab when away from home.

**Independent Test**: Connect a mobile device to LTE (disconnect WiFi), enable Tailscale, and attempt to access `https://192.168.1.112:8006`.

**Acceptance Scenarios**:

1. **Given** the Tailscale client is connected on a remote device, **When** I navigate to `https://192.168.1.112:8006`, **Then** the Proxmox login page loads.
2. **Given** the Tailscale client is connected on a remote device, **When** I run `ssh root@192.168.1.112`, **Then** I can authenticate and gain shell access.
3. **Given** the Tailscale client is disconnected, **When** I attempt to access the Proxmox IP, **Then** the connection fails (verifying no public exposure).

---

### User Story 2 - Remote Service Access (Priority: P2)

As a user, I want to access my hosted services (Immich, Home Assistant) securely from my phone while away from home, so that I can use my homelab services anywhere.

**Why this priority**: Provides the utility value of the homelab to the end user.

**Independent Test**: Connect a mobile device to LTE, enable Tailscale, and access service IPs.

**Acceptance Scenarios**:

1. **Given** Tailscale is connected remotely, **When** I access `http://192.168.1.213:2283` (Immich), **Then** the application loads.
2. **Given** Tailscale is connected remotely, **When** I access `http://192.168.1.212:8123` (Home Assistant), **Then** the dashboard loads.

---

### User Story 3 - Access Control Enforcement (Priority: P3)

As a security-conscious admin, I want to ensure that only authorized devices can access the management interfaces, so that if a non-admin device joins the tailnet, it cannot compromise the host.

**Why this priority**: Security baseline to prevent lateral movement if a client is compromised.

**Independent Test**: Review ACL file and verify rules against the Tailscale policy editor.

**Acceptance Scenarios**:

1. **Given** a valid ACL policy is applied, **When** I check the policy, **Then** it restricts access to port 8006/22 to specific admin tags/users.
2. **Given** a non-admin device (simulated or real), **When** it attempts to access port 22 on the host, **Then** the connection is blocked by Tailscale ACLs.

---

## Functional Requirements

- **FR-001**: The Proxmox host (`pve`) MUST run the Tailscale service, enabled to start on boot.
- **FR-002**: The Proxmox host MUST be configured as a Subnet Router advertising `192.168.1.0/24`.
- **FR-003**: The solution MUST NOT require any port forwarding or configuration changes on the physical router.
- **FR-004**: Access control MUST be managed via Tailscale ACLs (documented in `docs/tailscale-acl.example.json`) using a **Default Deny** policy.
- **FR-005**: The Tailscale authentication key MUST be supplied via **Ansible Vault** using the variable `tailscale_auth_key`; it MUST NOT be committed to the repo in plain text.
- **FR-006**: An Ansible role `tailscale_host` MUST be created to automate the installation and configuration, applying the tag `tag:proxmox`.
- **FR-007**: A validation procedure ("smoke test") MUST be documented.

## Success Criteria

- **Measurable**:
    - Proxmox UI (`:8006`) is reachable via Tailscale from an external network.
    - SSH (`:22`) is reachable via Tailscale from an external network.
    - Subnet routes (`192.168.1.0/24`) are advertised and accepted.
- **Qualitative**:
    - No public internet exposure of any port.
    - Router configuration remains untouched.

## Technical Constraints & Assumptions

- **Constraint**: mDNS (`.local`) names will likely not resolve over Tailscale (unless MagicDNS/Split DNS is configured later). Users must use IPs or Tailscale DNS names.
- **Constraint**: **Tailscale ACLs do not apply to local LAN traffic**. Devices on the same physical subnet (192.168.1.x) connecting directly to Proxmox (without Tailscale) will bypass these ACLs.
- **Assumption**: The user has a Tailscale account and can generate an auth key.
- **Assumption**: The user has access to the Tailscale Admin Console to approve subnet routes.

## Out of Scope

- Configuring Tailscale on individual LXCs (we are using the Subnet Router approach).
- MagicDNS configuration for `.local` domains (future enhancement).
- Tailscale SSH (we will use standard SSH over Tailscale network).

## Edge Cases

- **Client Subnet Conflict**: If the remote client is on a network that also uses `192.168.1.0/24` (very common), they may not be able to route to the homelab. *Mitigation*: Document that users may need to use a different local subnet or use Tailscale's "4via6" routing if available, or just accept this limitation for now.
- **Auth Key Expiry**: If the reusable key is revoked or expires, the node may fail to re-authenticate on restart. *Mitigation*: Use a non-expiring key or monitor key status.
- **WAN Failover**: If the host's primary WAN IP changes, Tailscale should handle NAT traversal automatically, but brief interruptions may occur.

## Stop Points & Decisions

- **Decision**: Use **Option A** (Subnet Router on Proxmox Host).
- **Decision**: Use a **reusable auth key** stored in **Ansible Vault** to allow re-provisioning.
- **Decision**: Use `tag:proxmox` for the Proxmox host to allow granular ACL rules.
- **Decision**: Disable "Tailscale SSH" feature for now; rely on standard SSH daemon protected by ACLs.
- **Decision**: Restrict admin ports (22, 8006) to Admin users in ACLs.
