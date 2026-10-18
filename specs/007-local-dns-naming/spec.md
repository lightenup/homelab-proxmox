# Feature Specification: Local DNS & Naming

**Feature Branch**: `007-local-dns-naming`
**Created**: 2025-12-16
**Status**: Draft

## Clarifications

### Session 2025-12-16
- Q: Should the Proxmox host be included in mDNS configuration? → A: Yes, include the Proxmox host (`pve`) to ensure consistent `.local` access.
- Q: Should firewall rules for mDNS (UDP 5353) be configured? → A: No, assume host firewalls are permissive or disabled; do not modify firewall settings.

## User Scenarios & Testing

### User Story 1 - Admin Access via Hostname (Priority: P1)

As an administrator, I want to access my homelab services using human-readable hostnames (e.g., `proxy.local`, `immich.local`) from my laptop, so that I don't have to memorize IP addresses or edit my local hosts file manually.

**Why this priority**: This is the primary goal of the feature—improving usability for the admin without infrastructure changes.

**Independent Test**: Can be tested by running `ping proxy.local` from the admin workstation after the playbook runs.

**Acceptance Scenarios**:

1. **Given** the Ansible playbook has run successfully on all LXCs, **When** I ping `proxy.local` from my laptop, **Then** it resolves to `192.168.1.211`.
2. **Given** the reverse proxy is running, **When** I visit `http://proxy.local` in a browser, **Then** the Nginx welcome page (or configured default) loads.
3. **Given** the Immich service is running, **When** I visit `http://immich.local` (or via proxy if configured), **Then** it resolves and connects.

---

### User Story 2 - Inter-Service Resolution (Priority: P2)

As a service running in an LXC (e.g., Home Assistant), I want to be able to resolve other services by their `.local` hostname, so that my configuration can use names instead of hardcoded IPs.

**Why this priority**: Enables portable configuration and internal service discovery.

**Independent Test**: Can be tested by SSHing into one LXC and pinging another by name.

**Acceptance Scenarios**:

1. **Given** I am logged into the `homeassistant` LXC, **When** I run `ping immich.local`, **Then** it resolves to `192.168.1.213`.
2. **Given** I am logged into the `proxy` LXC, **When** I run `getent hosts immich.local`, **Then** it returns the correct IP `192.168.1.213`.

---

### User Story 3 - Automated Configuration (Priority: P3)

As an administrator, I want the mDNS configuration to be applied automatically via Ansible, so that any new container I provision immediately becomes resolvable.

**Why this priority**: Ensures maintainability and consistency.

**Independent Test**: Can be tested by re-running the playbook and verifying no changes occur (idempotency).

**Acceptance Scenarios**:

1. **Given** the playbook has already run, **When** I run it again, **Then** it reports "changed=0" for the mDNS tasks.
2. **Given** a new LXC is added to the inventory, **When** I run the playbook, **Then** `avahi-daemon` is installed and configured automatically.

---

## Functional Requirements

- **FR-001**: All managed hosts (Proxmox host `pve` and LXCs `proxy`, `immich`, `homeassistant`) MUST broadcast their hostname via mDNS (`.local` domain).
- **FR-002**: The solution MUST NOT require any changes to the central router or DHCP server.
- **FR-003**: The configuration MUST be managed via a reusable Ansible role (`mdns_base`).
- **FR-004**: The solution MUST support standard mDNS clients (Bonjour on macOS/Windows, Avahi on Linux).
- **FR-005**: Documentation MUST be provided detailing client support limitations (e.g., Android) and the future migration path to `home.arpa`.

## Success Criteria

- **Measurable**:
    - `ping <hostname>.local` succeeds for 100% of managed LXCs from the admin laptop.
    - `avahi-resolve -n <hostname>.local` returns the correct IP on all Linux hosts.
- **Qualitative**:
    - Admin can navigate to services in the browser using `.local` names.
    - No manual editing of `/etc/hosts` is required on the admin laptop.

## Technical Constraints & Assumptions

- **Constraint**: We cannot modify the router's DNS or DHCP settings at this stage.
- **Constraint**: We are using a flat LAN (`192.168.1.0/24`), so multicast traffic is assumed to flow freely between devices.
- **Assumption**: The admin laptop is on the same subnet as the Proxmox host and LXCs.
- **Assumption**: The admin laptop has an mDNS resolver enabled (default on macOS/Windows 10+).
- **Assumption**: Host-level firewalls (UFW/iptables) are disabled or permissive for local traffic (UDP 5353).

## Out of Scope

- Configuring a central DNS server to resolve these names for the whole network (requires router change).
- Configuring public domain names or SSL certificates (Feature 005/Future).
- Android client support (Android does not natively support `.local` mDNS resolution without specific apps).

## Stop Points & Decisions

- **Decision**: Enable mDNS on **ALL** LXCs (not just proxy/immich) to ensure consistent addressability.
- **Decision**: Use `.local` for mDNS now. Reserve `home.arpa` for the future DNS-based setup.
- **Decision**: Include optional per-device DNS override guidance in the documentation for clients that struggle with mDNS.
