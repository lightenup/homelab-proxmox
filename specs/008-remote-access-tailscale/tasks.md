# Tasks: Remote Access Baseline (Tailscale + ACLs)

**Feature**: Remote Access Baseline (Tailscale + ACLs)
**Status**: Planned

## Phase 1: Setup
*Goal: Define configuration and documentation standards.*

- [x] T001 Create `docs/tailscale-acl.example.json` with Default Deny policy and `tag:proxmox` example
- [x] T002 Update `ansible/group_vars/proxmox_hosts.yml` with `tailscale_auth_key` and `tailscale_advertise_routes` variables

## Phase 2: Foundational (Ansible Role)
*Goal: Create the reusable Ansible role for Tailscale host configuration.*

- [x] T003 Create directory structure for `ansible/roles/tailscale_host/tasks`
- [x] T004 Implement package installation in `ansible/roles/tailscale_host/tasks/main.yml` (add repo, install `tailscale`)
- [x] T005 Implement service configuration in `ansible/roles/tailscale_host/tasks/main.yml` (enable/start service)
- [x] T006 Implement `tailscale up` logic in `ansible/roles/tailscale_host/tasks/main.yml` using `tailscale_auth_key`, `tailscale_advertise_routes`, `--advertise-tags=tag:proxmox`, and `--ssh=false`

## Phase 3: User Story 1 - Remote Admin Access
*Goal: Enable remote access to Proxmox host.*

- [x] T007 [US1] Add `tailscale_host` role to `ansible/playbooks/host_proxmox.yml`
- [x] T008 [US1] Verify `ansible/group_vars/proxmox_hosts.yml` is correctly configured for the `pve` host

## Phase 4: User Story 2 - Remote Service Access
*Goal: Ensure subnet routing is configured for accessing LXCs.*

- [x] T009 [US2] Verify `tailscale_advertise_routes` in `ansible/group_vars/proxmox_hosts.yml` includes `192.168.1.0/24`

## Phase 5: User Story 3 - Access Control Enforcement
*Goal: Define secure access policies.*

- [x] T010 [US3] Finalize `docs/tailscale-acl.example.json` with specific rules for `tag:proxmox` (allow port 8006, 22 from Admin)

## Phase 6: Polish
*Goal: Documentation and cleanup.*

- [x] T011 Update `docs/network-layout.md` to include Tailscale Subnet Router details
- [x] T012 Document validation procedure (smoke test) in `docs/operations.md`

## Dependencies

- **US1** depends on **Phase 2** (Role creation).
- **US2** depends on **US1** (Host must be online to route).
- **US3** depends on **US1** (Need host online to test ACLs).

## Implementation Strategy

1.  **Setup**: Define the "contract" (variables and ACLs).
2.  **Role**: Build the logic to install and configure Tailscale.
3.  **Deploy**: Apply to the host and verify connectivity.
4.  **Secure**: Apply ACLs to lock it down.
