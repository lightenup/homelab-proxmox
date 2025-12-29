# Tailscale Subnet Router Setup

## Overview
This runbook describes how to deploy and verify the Tailscale subnet router on the Proxmox host (`pve`).
This setup allows remote access to the LAN (`192.168.1.0/24`) via Tailscale.

## Prerequisites
- Ansible installed on controller.
- `ansible/group_vars/all/vault.yml` populated with:
  - `tailscale_oauth_client_id`
  - `tailscale_oauth_client_secret`
  - `tailscale_auth_key` (Optional, for initial bootstrap)

## Deployment
Run the playbook:
```bash
ansible-playbook playbooks/tailscale.yml
```

## Disaster Recovery (Rebuild from Scratch)
1. Install Proxmox VE.
2. Configure SSH access for Ansible.
3. Ensure `tailscale_auth_key` is set in vault (or run `tailscale up` manually once).
4. Run the playbook.
5. Verify the device appears in Tailscale Admin Console.
6. Verify subnet routes are advertised.

## Verification Checklist

### 1. Mobile Access (Cellular)
- [x] Disable WiFi on mobile device.
- [x] Enable Tailscale VPN.
- [x] Access Proxmox UI: `https://100.x.y.z:8006` (Tailscale IP).
- [x] Access LAN Service: `http://192.168.1.x:port` (e.g., Immich).
- [x] Verify latency is reasonable (direct connection vs DERP).

### 2. Admin Console
- [ ] Go to [Tailscale Machines](https://login.tailscale.com/admin/machines).
- [ ] Find `pve`.
- [ ] Verify "Subnets" shows `192.168.1.0/24` as **Advertised** and **Enabled**.
- [ ] Verify no "IP Forwarding" warnings.

### 3. Audit Playbook
Run the audit role to verify state via API:
```bash
ansible-playbook playbooks/tailscale.yml --tags audit
```
Expected output: All assertions pass.

## ACL Management
See [Tailscale ACL Management](tailscale-acl.md).
gitm