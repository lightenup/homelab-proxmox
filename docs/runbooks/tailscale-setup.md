# Tailscale Subnet Router Setup

**Purpose**: Configure Proxmox host (pve) as a Tailscale subnet router to enable secure remote access to LAN services  
**Feature**: 008b-tailscale-remote-access-iac  
**Last Updated**: December 20, 2025

## Overview

This runbook documents how to configure the Proxmox host as a Tailscale subnet router, enabling remote access to all LAN services (192.168.1.0/24) through the Tailscale VPN mesh network. The setup is fully automated via Ansible and designed for disaster recovery scenarios where the Proxmox host needs to be rebuilt from scratch.

**Architecture**: Proxmox host (pve) acts as a gateway between the Tailscale mesh network (100.x.x.x addresses) and the local LAN (192.168.1.0/24), with IP forwarding enabled to route traffic between networks.

**Key Benefits**:
- Remote access to all LAN services from anywhere
- Disaster recovery: rebuild pve with a single playbook run
- Reproducible configuration (no manual setup required)
- Secure: leverages Tailscale's WireGuard-based mesh VPN

---

## Prerequisites

Before running the Tailscale setup playbook, ensure the following:

1. **Tailscale Account**: Active Tailscale account with admin access to the tailnet
2. **GitHub Authentication**: Tailscale tailnet configured with GitHub as identity provider
3. **Admin Console Access**: Ability to log in to https://login.tailscale.com/admin
4. **Proxmox SSH Access**: SSH access to pve host with root or sudo privileges
5. **Ansible Control Node**: Ansible installed on the machine running the playbook
6. **Network Connectivity**: pve has internet access to reach Tailscale coordination servers

---

## Quick Start

### Running the Playbook

```bash
# From the homelab-proxmox repository root:
cd /path/to/homelab-proxmox

# Run the full Tailscale setup (install, configure, verify)
ansible-playbook ansible/playbooks/tailscale.yml

# Run only configuration tasks (skip install)
ansible-playbook ansible/playbooks/tailscale.yml --tags configure

# Run verification checks only
ansible-playbook ansible/playbooks/verify_tailscale.yml
```

### First-Time Setup

If Tailscale is not yet authenticated on pve, you have two options:

**Option 1: Manual Authentication (Recommended for first run)**
```bash
# SSH to pve and run:
ssh root@pve
tailscale up --advertise-routes=192.168.1.0/24

# Follow the authentication link in your browser
# Then rerun the Ansible playbook
```

**Option 2: Automated Authentication with Auth Key**
```bash
# Generate an auth key at https://login.tailscale.com/admin/settings/keys
# Recommended settings: Reusable, Tagged with "Devices", No expiration

# Provide auth key via command line:
ansible-playbook ansible/playbooks/tailscale.yml \
  --extra-vars "tailscale_auth_key=tskey-auth-xxxxx"

# OR via ansible-vault (more secure for repeated use):
# Store in ansible/group_vars/proxmox_hosts/vault.yml:
# tailscale_auth_key: tskey-auth-xxxxx
```

---

## Configuration

### Role Variables

The `tailscale_router` role supports the following variables:

**`tailscale_subnet_route`** (required)
- Default: `"192.168.1.0/24"`
- Description: CIDR notation for the LAN subnet to advertise through Tailscale
- Location: `ansible/roles/tailscale_router/defaults/main.yml`
- Override: Set in `ansible/group_vars/proxmox_hosts.yml` or `--extra-vars`

**`tailscale_auth_key`** (optional)
- Default: undefined
- Description: Tailscale authentication key for non-interactive setup
- **⚠️ NEVER commit this to the repository!**
- Provide via:
  - `--extra-vars` on command line
  - `ansible-vault` encrypted file at `ansible/group_vars/proxmox_hosts/vault.yml`

### Customizing the Subnet

To advertise a different subnet (e.g., 10.0.0.0/8):

```yaml
# In ansible/group_vars/proxmox_hosts.yml:
tailscale_subnet_route: "10.0.0.0/8"
```

Or via command line:
```bash
ansible-playbook ansible/playbooks/tailscale.yml \
  --extra-vars "tailscale_subnet_route=10.0.0.0/8"
```

---

## ⚠️ CRITICAL: GitHub Identity Format

**THIS IS THE #1 CAUSE OF ACCESS DENIED ERRORS**

When using GitHub authentication with Tailscale, ACL group identities **MUST** use the format `xxx@github` (GitHub username with `@github` suffix), **NOT** email addresses.

### Symptoms of Incorrect Identity Format

- Subnet routes show as "advertised" and "active" in Tailscale admin ✓
- IP forwarding is enabled and working ✓
- But all traffic is **DENIED** when trying to access pve or LAN services ✗
- No clear error message - just connection timeout or "unreachable"

### Why This Happens

Tailscale ACLs match traffic against user/group identities. If your ACL uses `user@example.com` but Tailscale knows you as `user@github`, **no rules match** and all traffic is denied by default.

### Correct vs Incorrect Examples

❌ **WRONG** (email address):
```json
{
  "groups": {
    "group:admins": ["andreas.jacobsen@example.com"]
  }
}
```

✅ **CORRECT** (GitHub identity):
```json
{
  "groups": {
    "group:admins": ["ajacobsen@github"]
  }
}
```

**Note**: The identity is your **GitHub username** + `@github`, not your GitHub email.

---

## Finding Your GitHub Identity

To find the correct identity format for yourself or other users:

1. Log in to Tailscale admin console: https://login.tailscale.com/admin
2. Navigate to **Settings** → **Users**
3. Locate your user in the list
4. The identity format shown is what must be used in ACLs
   - For GitHub auth: `username@github`
   - For Google auth: `email@gmail.com` (different provider)
   - For other SSO: varies by provider

**Example**: If your GitHub username is `ajacobsen`, your Tailscale identity is `ajacobsen@github` regardless of what email address is associated with your GitHub account.

---

## Verification

### Running Verification Checks

After running the setup playbook, verify the configuration:

```bash
# Run all verification checks
ansible-playbook ansible/playbooks/verify_tailscale.yml

# Run specific checks
ansible-playbook ansible/playbooks/verify_tailscale.yml --tags verify-status
ansible-playbook ansible/playbooks/verify_tailscale.yml --tags verify-routes
ansible-playbook ansible/playbooks/verify_tailscale.yml --tags verify-ipv4
```

### Expected Output

All verification tasks should show `ok` status with success messages:

```
TASK [Verify Tailscale is logged in] *****
ok: [pve] => {
    "msg": "✓ Tailscale is connected and logged in"
}

TASK [Verify subnet route is advertised] *****
ok: [pve] => {
    "msg": "✓ Subnet route 192.168.1.0/24 is advertised"
}

TASK [Verify IPv4 forwarding is enabled] *****
ok: [pve] => {
    "msg": "✓ IPv4 forwarding is enabled (value: 1)"
}
```

### Manual Verification

You can also verify the configuration manually on pve:

```bash
# Check Tailscale status
tailscale status

# Check Tailscale IP
tailscale ip -4

# Check advertised routes
tailscale status --json | jq '.Self.AllowedIPs'

# Check IP forwarding
sysctl net.ipv4.ip_forward
sysctl net.ipv6.conf.all.forwarding

# Check persistence file
cat /etc/sysctl.d/99-tailscale-subnet-router.conf
```

---

## Troubleshooting

### Access Denied Despite Routes Working

**Symptom**: Subnet routes show as active in Tailscale admin, but cannot access pve or LAN services.

**Most Common Cause**: ACL identity mismatch (GitHub format issue - see "⚠️ CRITICAL: GitHub Identity Format" section above)

**Steps to diagnose**:
1. Verify your identity in Tailscale admin → Settings → Users
2. Check your ACL at https://login.tailscale.com/admin/acls
3. Ensure ACL group memberships use `username@github`, not email addresses
4. Test access immediately after updating ACL (changes apply instantly)

### Tailscale Not Authenticated

**Symptom**: Playbook fails with "ERROR: Tailscale not authenticated"

**Solution**:
```bash
# Option 1: Authenticate manually on pve
ssh root@pve
tailscale up --advertise-routes=192.168.1.0/24

# Option 2: Provide auth key to playbook
ansible-playbook ansible/playbooks/tailscale.yml \
  --extra-vars "tailscale_auth_key=tskey-auth-xxxxx"
```

### IP Forwarding Not Persisting

**Symptom**: IP forwarding works after playbook run but is disabled after reboot

**Diagnosis**:
```bash
# Check if persistence file exists
ls -l /etc/sysctl.d/99-tailscale-subnet-router.conf

# Verify content
cat /etc/sysctl.d/99-tailscale-subnet-router.conf
```

**Solution**: Rerun the playbook to deploy the sysctl configuration file.

### Subnet Routes Not Approved

**Symptom**: Routes show as "advertised" but not "active" in Tailscale admin

**Cause**: Subnet routes require admin approval in the Tailscale admin console.

**Solution**:
1. Go to https://login.tailscale.com/admin/machines
2. Click on the pve device
3. Under "Subnet routes", click **Approve** for 192.168.1.0/24

---

## ACL Management

### Understanding ACL Structure

Tailscale Access Control Lists (ACLs) define who can access what resources in your tailnet. The ACL is structured as JSON with the following main sections:

- **`groups`**: Define collections of users (e.g., admins, family, guests)
- **`tagOwners`**: Specify who can apply tags to devices (e.g., tag:proxmox)
- **`acls`**: Traffic rules matching source users/groups to destination devices/networks
- **`ssh`**: SSH-specific access rules for Tailscale SSH feature

**Example ACL structure** (see `docs/tailscale-acl.example.json` in repository):
```json
{
  "groups": {
    "group:admin": ["username@github"]
  },
  "acls": [
    {
      "action": "accept",
      "src": ["group:admin"],
      "dst": ["192.168.1.0/24:*"]
    }
  ]
}
```

---

### Editing ACLs

#### Where to Edit

The ACL template file is located at `docs/tailscale-acl.example.json` in this repository. This file serves as:
- Reference documentation for the ACL structure
- Template for manual application to Tailscale admin console
- Version control for ACL changes

**⚠️ Important**: This file is NOT automatically applied. Changes must be manually copied to the Tailscale admin console (see "Applying ACL Changes" below).

#### Common ACL Patterns

**Adding a new service/port**:
```json
{
  "action": "accept",
  "src": ["group:admin"],
  "dst": ["192.168.1.213:2283"]  // Immich photo service
}
```

**Adding a new user to a group**:
```json
{
  "groups": {
    "group:admin": [
      "user1@github",
      "user2@github"  // ← Add new user
    ]
  }
}
```

**Creating a new group with limited access**:
```json
{
  "groups": {
    "group:family": ["user3@github", "user4@github"]
  },
  "acls": [
    {
      "action": "accept",
      "src": ["group:family"],
      "dst": ["192.168.1.213:2283"]  // Only allow Immich access
    }
  ]
}
```

#### JSON Syntax Validation

Before applying ACL changes, validate JSON syntax:

```bash
# Using jq (recommended)
jq . docs/tailscale-acl.example.json

# Using python
python3 -m json.tool docs/tailscale-acl.example.json

# Using online validator
# Copy content to https://jsonlint.com/
```

---

### Applying ACL Changes

**⚠️ SAFETY WARNING**: Incorrect ACL changes can lock you out of your tailnet. Follow this procedure carefully.

#### Step-by-Step Procedure

1. **Edit the ACL template file**:
   ```bash
   # Edit the template in your repository
   vim docs/tailscale-acl.example.json
   
   # Validate JSON syntax
   jq . docs/tailscale-acl.example.json
   ```

2. **Commit changes to repository** (for version control):
   ```bash
   git add docs/tailscale-acl.example.json
   git commit -m "acl: Add new service access for group:family"
   git push
   ```

3. **Navigate to Tailscale admin console**:
   - Go to https://login.tailscale.com/admin/acls
   - **⚠️ KEEP THIS BROWSER TAB OPEN** until you verify access works

4. **Copy and paste ACL JSON**:
   - Copy entire content of `docs/tailscale-acl.example.json`
   - Paste into the ACL editor in Tailscale admin
   - Replace placeholder identities (e.g., `lightenup@github`) with real identities

5. **Validate in Tailscale UI**:
   - Click "Validate" button in Tailscale ACL editor
   - Fix any syntax errors or validation warnings
   - Review the "Policy Diff" showing what changed

6. **Save ACL**:
   - Click "Save" button
   - ACL changes apply immediately (no restart required)

7. **⚠️ Test access BEFORE closing admin console**:
   - Test access to pve: `ssh root@100.67.156.70`
   - Test access to LAN service: `curl http://192.168.1.213:2283`
   - If locked out, revert ACL in admin console (still open)

8. **Verify in Tailscale admin** (optional):
   - Go to https://login.tailscale.com/admin/machines
   - Check that subnet routes still show as "active"
   - Check for any warnings on the pve device

---

### ⚠️ Safety Warning: ACL Rollback

**If you lock yourself out**:

1. **Admin console still open**: Click "Revert" or use browser back button to restore previous ACL
2. **Admin console closed**: Contact another admin with access to revert the ACL
3. **No other admin**: You may need to contact Tailscale support

**Prevention tips**:
- Always test access immediately after ACL changes
- Keep admin console tab open during testing
- Have a second admin account as backup
- Make small incremental changes (easier to identify problems)
- Commit ACL changes to repository with descriptive messages

---

### ACL Testing Checklist

After applying ACL changes, verify the following:

- [ ] **Proxmox web UI accessible**: https://100.67.156.70:8006
- [ ] **Proxmox SSH accessible**: `ssh root@100.67.156.70`
- [ ] **LAN service accessible**: Test one service (e.g., Immich at http://192.168.1.213:2283)
- [ ] **Subnet routes active**: Check Tailscale admin → Machines → pve
- [ ] **No warnings in Tailscale admin**: Verify pve device shows green/healthy
- [ ] **Mobile access works**: Test from phone on cellular (if applicable)

---



