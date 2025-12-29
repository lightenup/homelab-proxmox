# Implementation Plan: Tailscale IaC Max + API Audit

**Feature**: 008c-tailscale-iac-max
**Goal**: Reproducible Tailscale subnet router setup and API-based drift detection.

## Phase 1: Discovery & API Exploration
**Goal**: Determine capabilities of Tailscale API and current host state.
- [ ] **Audit Local Host**: Check current `sysctl` settings, `tailscale status`, and installed packages on `pve`.
- [ ] **Explore API**: Use `curl`/`jq` with a personal access token (PAT) to:
    - List devices (find `pve`).
    - Check routes (is `192.168.1.0/24` advertised? enabled?).
    - Check ACLs (can we fetch current ACL? validate a new one?).
    - Check tags.
- [ ] **Decision Record**: Decide on Auth Key vs OAuth Client for US1, and Manual vs Automated ACL apply for US2.

## Phase 2: Host-Side IaC (US1)
**Goal**: Ansible role `tailscale_router` to configure Proxmox.
- [ ] **Role Structure**: Create `ansible/roles/tailscale_router/`.
- [ ] **Install & Service**: Ensure Tailscale is installed and running.
- [ ] **Sysctl**: Configure `/etc/sysctl.d/99-tailscale-subnet-router.conf` for IP forwarding.
- [ ] **Auth Handling**:
    - Check `tailscale status`.
    - If not logged in, use `tailscale up --auth-key={{ vault_tailscale_auth_key }}` (if provided).
    - Fail gracefully if no key and not logged in.
- [ ] **Subnet Routes**: `tailscale set --advertise-routes={{ tailscale_subnet_routes }}`.
- [ ] **Verification**: Assert tasks for IP forwarding and advertised routes.

## Phase 3: ACL Source of Truth (US2)
**Goal**: Formalize ACL management.
- [ ] **Canonical File**: Establish `docs/tailscale/acl.json`.
- [ ] **Documentation**: Add comments/warnings about GitHub identity format (`xxx@github`).
- [ ] **Process**: Document the "Edit -> Commit -> Apply" workflow.
- [ ] **Automation (Optional)**: If Phase 1 confirms safety, implement a "validate" or "diff" script using the API.

## Phase 4: API Audit (US3)
**Goal**: Read-only drift detection.
- [ ] **Role/Script**: Create `ansible/roles/tailscale_audit/` or `scripts/tailscale/audit.sh`.
- [ ] **API Integration**: Use `uri` module or `curl` with API key from Vault.
- [ ] **Checks**:
    - Device `pve` exists and is `online`.
    - Subnet routes are `advertised` AND `enabled`.
    - Tags match expectations.
- [ ] **Output**: Print clear PASS/FAIL summary.

## Phase 5: Advanced Automation (US4 - Optional)
**Goal**: Safe "write" automation if justified.
- [ ] **Route Approval**: If API allows, auto-approve subnet routes for `tag:proxmox` devices (careful!).
- [ ] **Tagging**: Auto-tag device if missing.
- [ ] **Guardrails**: Require `tailscale_auto_approve=true` variable.

## Phase 6: Verification & Polish (US5)
**Goal**: End-to-end testing and documentation.
- [ ] **Runbook**: Create `docs/runbooks/tailscale.md`.
- [ ] **Checklist**: Mobile device verification steps.
- [ ] **Idempotency Test**: Run playbook twice, verify `changed=0`.
- [ ] **Secret Check**: Verify no secrets in git.

## Repo Structure Changes
- `ansible/roles/tailscale_router/` (New)
- `ansible/roles/tailscale_audit/` (New)
- `docs/tailscale/acl.json` (New/Moved)
- `docs/runbooks/tailscale.md` (New)
- `scripts/tailscale/` (New)
