# Tailscale Subnet Router Setup

**Purpose**: Configure Proxmox host (pve) as a Tailscale subnet router to enable secure remote access to LAN services  
**Feature**: 008b-tailscale-remote-access-iac  
**Last Updated**: December 20, 2025

## Overview

This runbook documents how to configure the Proxmox host as a Tailscale subnet router, enabling remote access to all LAN services (192.168.1.0/24) through the Tailscale VPN mesh network. The setup is fully automated via Ansible and designed for disaster recovery scenarios where the Proxmox host needs to be rebuilt from scratch.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Tailscale Mesh Network                   │
│                      (100.x.x.x/10)                          │
│                                                              │
│  ┌──────────────┐         ┌──────────────┐                 │
│  │ Mobile Phone │◄───────►│     pve      │                 │
│  │ 100.x.x.x    │         │ 100.67.156.70│                 │
│  │              │         │ (Subnet Router)                │
│  └──────────────┘         └───────┬──────┘                 │
│                                   │                         │
└───────────────────────────────────┼─────────────────────────┘
                                    │
                                    │ Routes 192.168.1.0/24
                                    │ (IP forwarding enabled)
                                    │
                    ┌───────────────▼───────────────┐
                    │    Home LAN Network          │
                    │    (192.168.1.0/24)          │
                    │                              │
                    │  ┌────────────────────────┐  │
                    │  │ Proxmox (pve)          │  │
                    │  │ 192.168.1.112          │  │
                    │  └────────────────────────┘  │
                    │                              │
                    │  ┌────────────────────────┐  │
                    │  │ Immich (LXC)           │  │
                    │  │ 192.168.1.213:2283     │  │
                    │  └────────────────────────┘  │
                    │                              │
                    │  ┌────────────────────────┐  │
                    │  │ Home Assistant (LXC)   │  │
                    │  │ 192.168.1.211:8123     │  │
                    │  └────────────────────────┘  │
                    │                              │
                    │  ┌────────────────────────┐  │
                    │  │ AdGuard (LXC)          │  │
                    │  │ 192.168.1.210:3000     │  │
                    │  └────────────────────────┘  │
                    │                              │
                    └──────────────────────────────┘
```

**How it works**:

1. **pve** runs Tailscale and acts as a **subnet router**
2. **pve** advertises the LAN subnet (192.168.1.0/24) to the Tailscale network
3. Mobile devices connect to Tailscale and can access pve directly at 100.67.156.70
4. Mobile devices can also access LAN services at 192.168.1.x via pve's routing
5. IP forwarding on pve ensures packets are routed between Tailscale and LAN
6. ACLs control which Tailscale users can access which services

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

## Remote Access Verification

### Prerequisites for Mobile Testing

To verify end-to-end remote access from a mobile device, you need:

1. **Mobile device** (smartphone or tablet)
2. **Cellular data connection** (WiFi must be disabled to simulate remote access)
3. **Tailscale app installed** on the mobile device
   - iOS: https://apps.apple.com/us/app/tailscale/id1470499037
   - Android: https://play.google.com/store/apps/details?id=com.tailscale.ipn
4. **Tailscale account** logged in on mobile device (same account as pve)

---

### Mobile Device Checklist

Follow this checklist to verify remote access is working correctly:

#### Step 1: Disable WiFi / Enable Cellular
- [ ] Turn OFF WiFi on your mobile device
- [ ] Verify you're on cellular data (4G/5G/LTE)
- [ ] Confirm you're NOT on your home network

#### Step 2: Connect Tailscale VPN
- [ ] Open Tailscale app on mobile device
- [ ] Enable Tailscale connection (toggle to ON)
- [ ] Verify Tailscale shows "Connected" status
- [ ] Check that pve device appears in device list

#### Step 3: Access Proxmox Web UI
- [ ] Open browser on mobile device
- [ ] Navigate to: https://100.67.156.70:8006
- [ ] Accept self-signed certificate warning (Proxmox uses self-signed cert by default)
- [ ] Verify Proxmox login page loads
- [ ] (Optional) Log in and verify Proxmox UI functions normally

#### Step 4: Access LAN Service (Example: Immich)
- [ ] Open browser on mobile device
- [ ] Navigate to: http://192.168.1.213:2283 (Immich photo service)
- [ ] Verify service loads (may take 5-10 seconds first time)
- [ ] Confirm service is accessible via private LAN IP through subnet router
- [ ] Test other LAN services if needed (Home Assistant, AdGuard, etc.)

**Success criteria**: All 4 steps complete without errors. If any step fails, see troubleshooting below.

---

### Admin Console Verification

After mobile testing, verify the configuration in Tailscale admin console:

1. **Navigate to Machines page**:
   - Go to: https://login.tailscale.com/admin/machines
   - Find the **pve** device in the list

2. **Verify subnet route status**:
   - Click on **pve** device
   - Scroll to "Subnet routes" section
   - Confirm **192.168.1.0/24** shows as:
     - ✓ **Advertised** (pve is announcing the route)
     - ✓ **Active** (route is approved and in use)
     - ✓ **No warnings** (no IP forwarding issues)

3. **Check for IP forwarding warnings**:
   - On the pve device page, check for any yellow/red warnings
   - Should be **NO** warnings like "IP forwarding not enabled"
   - If warnings exist, rerun the Ansible playbook to fix configuration

4. **Verify mobile device connectivity**:
   - Find your mobile device in the machines list
   - Confirm status shows "Active" or "Last seen: < 1 minute ago"
   - Check that mobile device can reach 192.168.1.0/24 via pve

**Expected result**: Subnet route shows active with no warnings, mobile device shows connected.

---

### Common Issues (Mobile Access)

#### Tailscale Not Connected on Mobile

**Symptom**: Tailscale app shows "Disconnected" or "Connecting..."

**Solutions**:
- Ensure cellular data is enabled and working
- Try toggling Tailscale OFF then ON
- Force quit and restart Tailscale app
- Check if Tailscale VPN profile is allowed in device settings

#### Subnet Routes Not Approved in Admin

**Symptom**: Can access pve directly (100.67.156.70) but cannot access LAN services (192.168.1.x)

**Cause**: Subnet routes require manual approval in Tailscale admin.

**Solution**:
1. Go to: https://login.tailscale.com/admin/machines
2. Click on **pve** device
3. Find "Subnet routes" section
4. Click **Approve** next to 192.168.1.0/24

#### IP Forwarding Warnings

**Symptom**: Admin console shows "IP forwarding not enabled" warning on pve device

**Cause**: IP forwarding is not enabled or not persisted correctly on pve.

**Solution**:
```bash
# Rerun the Ansible playbook to fix IP forwarding
ansible-playbook ansible/playbooks/tailscale.yml --tags configure

# Verify IP forwarding is enabled
ansible-playbook ansible/playbooks/verify_tailscale.yml
```

#### ACL Blocking Traffic

**Symptom**: Can connect to Tailscale but cannot access pve or LAN services

**Cause**: ACL rules are blocking traffic (likely GitHub identity format issue).

**Solution**: See "Troubleshooting → Access Denied Despite Routes Working" section above.

---

## Security Considerations

### Authentication Key Handling

**CRITICAL: Never commit auth keys to git**

The Tailscale authentication key (`tailscale_auth_key`) is a sensitive secret that grants access to your Tailscale network. If committed to git, anyone with repository access could join your Tailscale network.

**Protection mechanisms**:

1. **.gitignore patterns**: The repository `.gitignore` includes patterns to block:
   - `**/vault.yml` (Ansible Vault files)
   - `**/*secret*.yml` (any file with "secret" in the name)
   - `**/*_secrets.yml` (secrets files)
   - `**/tailscale_auth_key*` (specifically tailscale auth keys)
   - `**/*.key` (generic key files)
   - `**/*.pem` (generic PEM files)

2. **Default configuration**: The `ansible/roles/tailscale_router/defaults/main.yml` file includes a commented-out auth key variable with a warning:
   ```yaml
   # tailscale_auth_key: "tskey-auth-xxxxx"  # DO NOT commit this to git
   ```

3. **Best practices**:
   - **Use Ansible Vault**: Store auth keys in `ansible/group_vars/services/secrets.yml` encrypted with Ansible Vault
   - **Use reusable keys**: Generate keys with "Reusable" and "Devices" tags in Tailscale admin for disaster recovery scenarios
   - **Rotate keys**: If a key is accidentally committed, revoke it immediately in Tailscale admin and generate a new one

### ACL Principle of Least Privilege

**Best practice**: Grant only the minimum access required for each user/group.

**Example**: Instead of granting all users access to all LAN services:

```json
// Too permissive (NOT recommended):
"acls": [
  {
    "action": "accept",
    "src": ["group:admin"],
    "dst": ["192.168.1.0/24:*"]  // All ports on all services
  }
]

// Better (least privilege):
"acls": [
  {
    "action": "accept",
    "src": ["group:family"],
    "dst": [
      "192.168.1.213:2283",  // Immich only
      "192.168.1.211:8123"   // Home Assistant only
    ]
  },
  {
    "action": "accept",
    "src": ["group:admin"],
    "dst": [
      "100.67.156.70:8006",  // Proxmox web UI
      "100.67.156.70:22"     // Proxmox SSH
    ]
  }
]
```

**Recommendations**:
- Create separate groups for different access levels (family, admin, work)
- Specify exact ports instead of wildcards (`:*`)
- Test ACL changes immediately after applying
- Keep an admin access rule that cannot be accidentally locked out

### Subnet Router as Single Point of Failure

**Risk**: If pve goes down, remote access to all LAN services is lost.

**Mitigation strategies**:

1. **Disaster recovery capability**: This Ansible playbook enables quick rebuild of pve from scratch
2. **High availability (optional)**: Deploy a second Proxmox host as a backup subnet router
3. **Monitoring**: Set up alerts for pve downtime (e.g., Tailscale admin shows device offline)
4. **Local access preserved**: LAN services remain accessible from local network even if pve is down

**Trade-off**: For most homelab scenarios, the simplicity of a single subnet router outweighs the complexity of HA setups.

---

## Disaster Recovery

### Scenario: Proxmox Host Rebuild

**Situation**: The Proxmox host (pve) has failed and needs to be rebuilt from scratch.

**Recovery steps**:

1. **Install Proxmox**: Install Proxmox VE on new hardware or restore from backup
2. **Configure network**: Ensure pve has same IP (192.168.1.112) and internet access
3. **Restore repository**: Clone homelab-proxmox repository to control node
4. **Run Ansible playbook**:
   ```bash
   cd homelab-proxmox
   ansible-playbook ansible/playbooks/tailscale.yml
   ```
5. **Verify connectivity**: Run verification playbook to confirm setup:
   ```bash
   ansible-playbook ansible/playbooks/verify_tailscale.yml
   ```
6. **Approve subnet routes**: In Tailscale admin, approve 192.168.1.0/24 route for new pve device
7. **Test remote access**: Connect from mobile device and verify LAN services are accessible

**Key advantage**: No need to remember manual configuration steps. The entire Tailscale setup is reproducible from the repository.

### What This Feature Enables

This Tailscale automation feature was specifically designed to address the disaster recovery scenario where the Proxmox host needs to be rebuilt. Before this automation:

- Manual Tailscale installation and configuration required
- Subnet router setup required multiple manual commands
- IP forwarding persistence required manual sysctl file creation
- ACL configuration required manual copy-paste into admin console
- Risk of forgetting steps or misconfiguring

After this automation:

- **Single playbook run** rebuilds entire Tailscale configuration
- **Idempotent**: Can be run multiple times without breaking existing setup
- **Verified**: Automated verification tasks confirm all components working
- **Documented**: Comprehensive runbook with troubleshooting guides

**Recovery time**: From bare Proxmox install to full remote access in < 5 minutes (excluding Proxmox installation time).

---

### Expected Behavior

When remote access is configured correctly, you should experience:

- **Proxmox UI loads normally**: No slower than accessing over LAN (WireGuard is fast)
- **LAN services accessible via private IPs**: Can reach any service at 192.168.1.x
- **No latency spikes**: Routing through Tailscale is efficient (typically <50ms added latency)
- **Persistent connection**: Tailscale maintains connection even when switching networks
- **No port forwarding needed**: All access through encrypted WireGuard tunnel

**Performance expectations**:
- Proxmox web UI: Responsive, similar to local access
- Immich photo loading: May be slower due to image sizes, but functional
- SSH to pve: Interactive, no noticeable lag
- Home Assistant: Real-time updates work normally

---



