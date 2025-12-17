# Implementation Plan - Remote Access Baseline (Tailscale)

## Phase 1: Documentation & Configuration Design
- [ ] Create `docs/tailscale-acl.example.json` to document the intended Access Control List policy.
- [ ] Define required Ansible variables (auth key, routes) in `ansible/group_vars/proxmox_hosts.yml` (using placeholders/comments for secrets).

## Phase 2: Ansible Role Development (`tailscale_host`)
- [ ] Initialize new role `ansible/roles/tailscale_host`.
- [ ] Implement task: Add Tailscale repository and install package.
- [ ] Implement task: Enable and start `tailscaled` service.
- [ ] Implement task: Run `tailscale up` with:
    - `--authkey={{ tailscale_auth_key }}`
    - `--advertise-routes=192.168.1.0/24`
    - `--ssh=false` (per spec decision)
    - Check if already up to avoid re-running.

## Phase 3: Integration & Deployment
- [ ] Add `tailscale_host` role to `ansible/playbooks/host_proxmox.yml`.
- [ ] Update `ansible/group_vars/proxmox_hosts.yml` to include the role variables.
- [ ] Run playbook against `pve` host.

## Phase 4: Validation & Handover
- [ ] Manual Step: Approve subnet routes in Tailscale Admin Console.
- [ ] Manual Step: Apply ACLs in Tailscale Admin Console.
- [ ] Verify remote access to Proxmox UI (`:8006`) via LTE/External network.
- [ ] Verify remote access to LXC services (e.g., Immich) via LTE/External network.
