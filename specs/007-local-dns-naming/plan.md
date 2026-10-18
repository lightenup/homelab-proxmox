# Implementation Plan - Local DNS & Naming

This plan outlines the steps to implement mDNS-based local naming across the homelab infrastructure without modifying the central router.

## Proposed Architecture

- **Mechanism**: mDNS (Multicast DNS) via `avahi-daemon`.
- **Domain**: `.local`.
- **Scope**: Proxmox host (`pve`) and all Ansible-managed LXCs (`proxy`, `immich`, `homeassistant`).
- **Management**: New Ansible role `mdns_base`.

## Phased Approach

### Phase 1: Ansible Role Development
Create a reusable Ansible role that installs and configures `avahi-daemon`. This role will ensure the hostname is correctly set and the service is active.

### Phase 2: Deployment
Apply the role to the existing inventory. This involves updating the `site.yml` or creating a specific `naming.yml` playbook to target the `services` group.

### Phase 3: Verification & Documentation
Verify resolution from the admin laptop and between LXCs. Document the setup and known limitations (e.g., Android).

## Risks & Mitigations

- **Risk**: Hostname conflicts if multiple devices have the same name.
  - **Mitigation**: Ansible inventory ensures unique hostnames.
- **Risk**: mDNS flooding (low risk on small network).
  - **Mitigation**: Standard Avahi configuration is lightweight.
- **Risk**: Client incompatibility (Android).
  - **Mitigation**: Document this limitation clearly; no workaround planned for v1.
