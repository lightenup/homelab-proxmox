# Feature Specification: Tailscale IaC Max + API Audit

**Feature Branch**: `008c-tailscale-iac-max`
**Status**: Draft
**Goal**: Make the Tailscale subnet-router setup fully reproducible ("IaC-first") and implement safe API-based auditing to detect drift between the desired state (repo) and actual state (Tailnet).

## Context
We currently have a working Tailscale setup on the Proxmox host (`pve`) acting as a subnet router for the LAN (`192.168.1.0/24`). However, the setup was likely manual or partially automated. We want to codify this into Ansible to ensure a fresh Proxmox host can be restored to this state automatically. Additionally, we want to leverage the Tailscale API to audit the state of the Tailnet (devices, routes, ACLs) against our expectations.

## Clarifications

### Session 2025-12-28

- Q: Authentication strategy for rebuilding Proxmox host? → A: Option B - OAuth Client (Dynamic Keys). Use OAuth client credentials stored in Vault to dynamically generate auth keys at runtime.
- Q: Implementation method for Tailnet "Drift Audit" (US3)? → A: Option A - Ansible Role. Implement the audit logic as a dedicated Ansible role using `uri` module or local scripts invoked by Ansible, ensuring integration with the existing inventory and vault.
- Q: ACL Application Strategy (US4)? → A: Option B - Automated Application (Safe Mode). Implement a "commit-confirm" workflow: validate syntax locally, push ACL via API, immediately verify connectivity (e.g., can we still reach the API?), and auto-revert if verification fails.

## User Stories

### US1: Rebuild Proxmox Host (P1)
As a homelab admin, I can run a single Ansible playbook to restore the Proxmox host to a working Tailscale subnet-router state from scratch.
- **Acceptance Criteria**:
  - Installs Tailscale if missing.
  - Ensures `tailscaled` service is running.
  - Enables and persists IPv4/IPv6 forwarding in `/etc/sysctl.d/`.
  - Advertises the configured subnet route (default `192.168.1.0/24`).
  - Handles authentication: detects if already authenticated; if not, uses OAuth client credentials from Vault to generate a dynamic auth key.
  - Idempotent: Re-running the playbook on a configured host results in `changed=0`.

### US2: ACL Source of Truth (P1)
As a homelab admin, I want the ACL JSON in the repo to be the source of truth for my Tailnet access policies.
- **Acceptance Criteria**:
  - A canonical ACL file exists at `docs/tailscale/acl.json`.
  - Documentation clearly explains the GitHub identity format (`xxx@github`).
  - Automated application is implemented (see US4).

### US3: Tailnet "Drift Audit" (P2)
As a homelab admin, I can run a read-only audit tool that verifies the state of my Tailnet via the Tailscale API.
- **Acceptance Criteria**:
  - Verifies `pve` device exists and is online/last-seen recently.
  - Verifies advertised routes are present and enabled (if API permits).
  - Verifies tags match expectations (e.g., `tag:proxmox`).
  - Runs without interactive login (uses API key from Vault).
  - Outputs a concise PASS/FAIL summary.

### US4: Safe Automated Configuration (P3)
As a homelab admin, I want to automatically apply ACLs and route approvals from the repo, but with a safety mechanism to prevent lockout.
- **Acceptance Criteria**:
  - **ACL Automation**: Ansible task pushes `acl.json` to Tailscale API.
  - **Safety Check**: "Commit-Confirm" logic. After pushing, the playbook must verify it can still reach the Tailscale API or a specific node. If not, it attempts to revert to the previous ACL (saved before push).
  - **Route Approval**: Automatically approve advertised routes for `pve` if they match the expected subnet.
  - **Gating**: This dangerous capability must be gated behind a specific tag or variable (e.g., `tailscale_apply_changes=true`).

### US5: End-to-End Verification (P3)
As a homelab admin, I have a checklist to verify remote access works as expected from a client device.
- **Acceptance Criteria**:
  - Verify Proxmox UI access via Tailscale IP.
  - Verify LAN service access via subnet router (192.168.1.x).
  - Verify Admin Console reflects the correct state.

## Functional Requirements
1. **Idempotency**: All Ansible tasks must be idempotent.
2. **Configurability**: Subnet routes must be defined in variables (default `192.168.1.0/24`).
3. **Persistence**: IP forwarding must persist across reboots via `/etc/sysctl.d/99-tailscale-subnet-router.conf`.
4. **Verification**: Playbooks must include `assert` tasks to verify local state (IP, routes, sysctl).
5. **Secret Management**: All secrets (auth keys, API keys) must be stored in Ansible Vault and excluded from git via `.gitignore`.
6. **ACL Management**: Repo must contain the canonical ACL JSON file.

## Non-Functional Requirements
1. **Safety**: Audit tools must be read-only by default.
2. **Documentation**: Clear runbooks for setup, disaster recovery, and ACL management.
3. **Security**: No secrets in plaintext. Least privilege for API keys if possible.

## Out of Scope
- LAN firewall segmentation (unless required for Tailscale).
- Full monitoring integration (Prometheus/Grafana) - focus is on configuration and audit.
- Replacement of the main LAN router.
