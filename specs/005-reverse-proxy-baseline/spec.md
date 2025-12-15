# Feature Specification: Internal Reverse Proxy Baseline

**Feature Branch**: `005-reverse-proxy-baseline`
**Created**: 2025-12-15
**Status**: Draft
**Input**: User description: "Internal Reverse Proxy Baseline (Internal LAN, HTTP-first)"

## Clarifications

### Session 2025-12-15
- Q: Installation method? → A: Official Apt Repo (Option A)
- Q: Logging method? → A: Journald (stdout) (Option A)
- Q: Configuration structure? → A: Modular (Import Directory) (Option B)
- Q: HTTPS behavior? → A: Explicitly Disable (`auto_https off`) (Option A)

## User Scenarios & Testing

### User Story 1 - Basic Proxy Setup (Priority: P1)

As a homelab administrator, I want to access Immich via the reverse proxy IP so that I have a central ingress point for my services.

**Why this priority**: This is the core functionality of the feature. Without this, there is no reverse proxy.

**Independent Test**: Can be tested by deploying the role and curling the proxy IP.

**Acceptance Scenarios**:

1. **Given** the proxy LXC is running and configured, **When** I send an HTTP GET request to `http://192.168.1.211/`, **Then** I receive a response from the Immich server (200 OK or 302 Redirect).
2. **Given** the proxy is running, **When** I check the headers of the forwarded request on the Immich side (if possible) or verify via proxy logs, **Then** I see `Host`, `X-Forwarded-For`, and `X-Forwarded-Proto` headers are present.

---

### User Story 2 - Persistence & Idempotency (Priority: P2)

As a homelab administrator, I want the reverse proxy configuration to be persistent across reboots and managed idempotently via Ansible so that the system is reliable and easy to maintain.

**Why this priority**: Ensures reliability and consistent configuration management, which is critical for infrastructure-as-code.

**Independent Test**: Can be tested by rebooting the LXC and re-running the Ansible playbook.

**Acceptance Scenarios**:

1. **Given** the proxy LXC has been rebooted, **When** I attempt to access `http://192.168.1.211/` after a few minutes, **Then** the service is available without manual intervention.
2. **Given** the playbook has already been applied, **When** I run the playbook again, **Then** Ansible reports zero changed tasks.

---

### User Story 3 - Documentation & Maintenance (Priority: P3)

As a homelab administrator, I want clear documentation on how to update the reverse proxy configuration and package so that I can keep the system secure and up-to-date.

**Why this priority**: Essential for long-term maintenance but not blocking the initial deployment.

**Independent Test**: Can be tested by following the documentation to perform a mock update.

**Acceptance Scenarios**:

1. **Given** I need to update the Caddy version or configuration, **When** I follow the documented procedure, **Then** the changes are applied successfully and the service remains operational.

---

### Edge Cases

- **Immich Down**: If the Immich backend is down, the proxy should return a 502 Bad Gateway error (standard Caddy behavior).
- **Network Partition**: If the proxy cannot reach the Immich LXC, it should handle the timeout gracefully.

## Requirements

### Functional Requirements

- **FR-001**: The reverse proxy service MUST run on the `proxy` LXC (192.168.1.211) and listen on port 80.
- **FR-002**: The reverse proxy MUST route all traffic from `/` to the Immich service at `192.168.1.213:2283`.
- **FR-003**: The reverse proxy MUST forward standard proxy headers (`Host`, `X-Forwarded-For`, `X-Forwarded-Proto`) to the backend.
- **FR-004**: The deployment MUST be fully automated and idempotent using Ansible.
- **FR-005**: The proxy service MUST start automatically on system boot and recover from crashes (systemd).
- **FR-006**: The solution MUST provide a documented approach for updating the reverse proxy configuration and software.
- **FR-007**: Caddy MUST be installed via the official Apt repository to facilitate standard package management updates.
- **FR-008**: Caddy MUST be configured to log access and errors to stdout for management via systemd/journald.
- **FR-009**: The Caddy configuration MUST use a modular structure, importing site configurations from `/etc/caddy/conf.d/*.caddy`.
- **FR-010**: Caddy MUST have automatic HTTPS explicitly disabled (`auto_https off`) to prevent certificate provisioning attempts and ensure HTTP-only operation on port 80.

### Key Entities

- **Proxy Host**: The LXC container hosting the Caddy service.
- **Upstream Service**: The Immich application running on a separate LXC.
- **Caddyfile**: The configuration file defining the routing rules.

## Success Criteria

### Measurable Outcomes

- **SC-001**: `curl -I http://192.168.1.211/` returns a successful HTTP response (2xx or 3xx) from a client on the LAN.
- **SC-002**: Direct access to Immich API (`http://192.168.1.213:2283/api/server/ping`) continues to function.
- **SC-003**: Re-running the Ansible playbook results in 0 changed tasks.
- **SC-004**: The reverse proxy service is available within 2 minutes of an LXC reboot.
