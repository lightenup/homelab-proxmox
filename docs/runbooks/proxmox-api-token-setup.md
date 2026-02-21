# Proxmox API Token Setup for Rebuild Orchestrator

**Purpose**: Create API token for laptop-based Terraform execution against Proxmox VE

**When Needed**: Before Phase 3 of delta implementation (D-009: Services phase refactor)

## Prerequisites

- SSH access to PVE host
- Root credentials for Proxmox web UI

## Create API Token

### Option 1: Via Web UI (Recommended)

1. **Login to Proxmox Web UI**:
   ```
   https://192.168.1.112:8006
   ```

2. **Navigate to API Tokens**:
   - Datacenter → Permissions → API Tokens
   - Click "Add"

3. **Configure Token**:
   - **User**: `root@pam`
   - **Token ID**: `rebuild` (full name will be `root@pam!rebuild`)
   - **Privilege Separation**: ✅ **UNCHECK** this box
     - This allows token to inherit root@pam permissions
     - Required for VM/LXC creation and modification
   - **Comment**: "Rebuild orchestrator - laptop Terraform execution"
   - **Expire**: Never (or set far future date)

4. **Copy Secret**:
   - ⚠️ **CRITICAL**: Copy the secret immediately - it's only shown once
   - Format: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`

5. **Store in Bitwarden**:
   ```
   Item Name: Proxmox API Token - Rebuild
   Username: root@pam!rebuild
   Password: <paste secret from step 4>
   URI: https://192.168.1.112:8006
   Notes: Used by rebuild orchestrator for laptop-based Terraform execution
   ```

### Option 2: Via CLI

```bash
ssh pve

# Create token (will output secret once)
pveum user token add root@pam rebuild \
  --privsep 0 \
  --comment "Rebuild orchestrator token"

# Example output:
# ┌──────────────┬──────────────────────────────────────┐
# │ key          │ value                                │
# ╞══════════════╪══════════════════════════════════════╡
# │ full-tokenid │ root@pam!rebuild                     │
# │ info         │ {"privsep":0}                        │
# │ value        │ xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx │
# └──────────────┴──────────────────────────────────────┘

# ⚠️ Copy the 'value' field immediately!
```

## Verify Token

Test the token works before using in rebuild:

```bash
# From laptop
export PROXMOX_API_TOKEN_ID="root@pam!rebuild"
export PROXMOX_API_TOKEN_SECRET="<secret-from-bitwarden>"

# Test API access
curl -k \
  -H "Authorization: PVEAPIToken=${PROXMOX_API_TOKEN_ID}=${PROXMOX_API_TOKEN_SECRET}" \
  https://192.168.1.112:8006/api2/json/version

# Expected: JSON response with PVE version
# {"data":{"release":"8.2","repoid":"xxxxx","version":"8.2.4"}}
```

## Usage in Rebuild

Add to your shell profile (`.zshrc` or `.bash_profile`):

```bash
# Proxmox API credentials for rebuild orchestrator
export PROXMOX_API_TOKEN_ID="root@pam!rebuild"
export PROXMOX_API_TOKEN_SECRET="<from-bitwarden>"
```

Or load from file (more secure):

```bash
# Create ~/.proxmox-rebuild-credentials (chmod 600)
export PROXMOX_API_TOKEN_ID="root@pam!rebuild"
export PROXMOX_API_TOKEN_SECRET="<secret>"

# Source in rebuild commands
source ~/.proxmox-rebuild-credentials
task rebuild:plan -- --backup-dir /path/to/backup
```

## Troubleshooting

**"permission denied" errors**:
- Verify privilege separation is **disabled** (`privsep: 0`)
- Check token exists: `ssh pve "pveum user token list root@pam"`

**"401 Unauthorized"**:
- Verify secret is correct (no extra whitespace)
- Check token not expired: `ssh pve "pveum user token list root@pam"`

**Token regeneration** (if secret lost):
```bash
ssh pve
pveum user token remove root@pam rebuild
pveum user token add root@pam rebuild --privsep 0
# Store new secret in Bitwarden
```

## Security Notes

- Token has full root privileges (privsep disabled required for LXC operations)
- Store secret in Bitwarden, never commit to git
- Consider creating separate token per operator if multiple people use rebuild
- Token does not expire by default - rotate periodically (e.g., quarterly)
- Can be revoked immediately if compromised: `pveum user token remove root@pam rebuild`

## References

- Proxmox API Token docs: https://pve.proxmox.com/wiki/User_Management#pveum_tokens
- Used by: Terraform provider `telmate/proxmox` for authentication
