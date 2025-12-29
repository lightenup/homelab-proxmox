# Implementation Report: Tailscale IaC Max + API Audit

**Feature**: 008c-tailscale-iac-max
**Date**: 2025-12-29
**Status**: Completed

## 1. Overview
This feature successfully implemented a fully automated, Infrastructure-as-Code (IaC) approach to managing the Tailscale subnet router on the Proxmox host. It includes automated deployment, configuration management, ACL enforcement (GitOps), and API-based drift detection.

## 2. Implemented Components

### 2.1 Ansible Roles
| Role | Description | Key Tasks |
|------|-------------|-----------|
| `tailscale_router` | Manages the host-side configuration. | - Installs Tailscale<br>- Configures Sysctl (IP Forwarding)<br>- Authenticates via OAuth (Dynamic Keys)<br>- Advertises Routes & Tags |
| `tailscale_audit` | Verifies state against Tailscale API. | - Fetches device details via API<br>- Asserts Node Status (Online/Connected)<br>- Asserts Tags (`tag:proxmox`)<br>- Asserts Route Advertisement |
| `tailscale_acl` | Manages Tailnet Policy. | - Backs up current ACL<br>- Validates syntax (Dry Run)<br>- Pushes new ACL (Commit)<br>- Verifies connectivity<br>- Auto-Rollback on failure |

### 2.2 Configuration Files
- **Source of Truth**: `docs/tailscale/policy.hujson`
    - Defines Groups (`admins`, `users`).
    - Defines ACLs (Access Control Lists).
    - Defines Tag Owners.
    - Defines **Auto-Approvers** for subnet routes (Critical for automation).
- **Variables**:
    - `ansible/group_vars/proxmox_hosts/vars.yml`: Defines `tailscale_subnet_routes` and `tailscale_tags`.
    - `ansible/group_vars/all/vars.yml`: Global settings (`tailscale_safe_mode`).

### 2.3 Documentation
- `docs/runbooks/tailscale-setup.md`: Comprehensive guide for deployment, DR, and verification.
- `docs/runbooks/tailscale-acl.md`: Guide for managing ACLs via the GitOps workflow.

## 3. Key Technical Decisions

### 3.1 Auto-Approval via Tags
Instead of manually approving routes in the Admin Console, we implemented **ACL Auto-Approvers**.
- **Mechanism**: The ACL file contains a rule allowing `tag:proxmox` to automatically approve `192.168.1.0/24`.
- **Benefit**: Zero-touch deployment. A new Proxmox host simply needs the correct tag during authentication, and its routes are immediately active.

### 3.2 Commit-Confirm ACL Workflow
To prevent locking ourselves out of the Tailnet:
1.  **Backup**: The current ACL is fetched and saved to `/tmp/`.
2.  **Validate**: The new policy is sent to the `/validate` endpoint.
3.  **Apply**: The policy is pushed.
4.  **Verify**: The playbook attempts to reach the API immediately after.
5.  **Rollback**: If verification fails, the backup ACL is automatically restored.

### 3.3 Dynamic Authentication
We moved away from static Auth Keys to **OAuth Client Credentials**.
- **Workflow**: The playbook uses the OAuth Client ID/Secret (Vault) to request a short-lived Access Token.
- **Usage**: This token is used to generate a reusable Auth Key for the node or perform API operations.

## 4. Verification Results

### 4.1 Automated Audit
The `tailscale_audit` role was run successfully against the production host:
- [x] **Node Status**: Online.
- [x] **Tags**: `tag:proxmox` present.
- [x] **Routes**: `192.168.1.0/24` advertised.

### 4.2 Manual Connectivity Check
- [x] **Mobile Access**: Verified access to Proxmox UI (`100.x.y.z`) over 5G.
- [x] **LAN Access**: Verified access to Immich (`192.168.1.x`) via the subnet router.
- [x] **ACL Enforcement**: Verified that placeholder identities were removed and real users (`lightenup@github`) have access.

## 5. Known Limitations & Future Work
- **"Enabled Routes" API Check**: The Tailscale API response for "Enabled Routes" can be inconsistent for tagged devices (often relying on `PrimaryRoutes` instead). The strict assertion was relaxed to focus on advertisement and connectivity.
- **OAuth Scope**: The current OAuth client has broad permissions. Future hardening could scope this down if Tailscale introduces more granular scopes for specific tags.

## 6. Conclusion
The Proxmox Tailscale setup is now fully reproducible. Disaster recovery is reduced to a single Ansible command (`ansible-playbook playbooks/tailscale.yml`), and day-to-day management is handled via code commits to the ACL file.
