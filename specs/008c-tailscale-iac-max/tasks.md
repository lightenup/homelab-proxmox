# Tasks: Tailscale IaC Max + API Audit

**Input**: Specification from `specs/008c-tailscale-iac-max/spec.md`
**Plan**: Implementation approach in `specs/008c-tailscale-iac-max/plan.md`
**Feature**: 008c-tailscale-iac-max

## Phase 1: Setup & Discovery

- [x] T001 [P] Create `ansible/roles/tailscale_router/` directory structure (tasks, defaults, handlers, templates, meta).
- [x] T002 [P] Create `ansible/roles/tailscale_audit/` directory structure (tasks, defaults, meta).
- [x] T003 [P] Create `ansible/roles/tailscale_acl/` directory structure (tasks, defaults, meta) for US4.
- [x] T004 [P] **[CONSTITUTION COMPLIANCE]** Verify `.gitignore` contains patterns blocking all common secret files: `**/vault.yml`, `**/*secret*.yml`, `**/*_secrets.yml`, `**/tailscale_auth_key*`, `**/*.key`, `**/*.pem`. Fail if `.gitignore` doesn't exist or is missing patterns.
- [x] T005 Configure Ansible Variables:
    - Add non-secret defaults (e.g., `tailscale_tailnet_name`) to `ansible/group_vars/all/vars.yml`.
    - Add secrets (`tailscale_oauth_client_id`, `tailscale_oauth_client_secret`, optional `tailscale_auth_key`) to `ansible/group_vars/all/vault.yml` (encrypted).
- [x] T006 Create `scripts/tailscale/test_api_access.sh` to verify OAuth token generation and API connectivity (list devices) using `curl` and the Vault credentials.

## Phase 2: Host-Side IaC (US1 - Rebuild Proxmox)

- [x] T007 [P] [US1] Create `ansible/roles/tailscale_router/defaults/main.yml` with `tailscale_subnet_routes: "192.168.1.0/24"` and `tailscale_tags: []` (empty by default for safety).
- [x] T008 [P] [US1] Create `ansible/roles/tailscale_router/tasks/install.yml` to install `tailscale` package (apt).
- [x] T009 [P] [US1] Create `ansible/roles/tailscale_router/tasks/sysctl.yml` to deploy `/etc/sysctl.d/99-tailscale-subnet-router.conf` (IPv4/IPv6 forwarding) and reload sysctl.
- [x] T010 [US1] Create `ansible/roles/tailscale_router/tasks/auth.yml`:
    - Check `tailscale status`.
    - If not logged in:
        - Check if `tailscale_auth_key` is defined.
        - If defined: Run `tailscale up --auth-key={{ tailscale_auth_key }} --advertise-routes={{ tailscale_subnet_routes }} {{ '--advertise-tags=' + tailscale_tags | join(',') if tailscale_tags else '' }}`.
        - If NOT defined: Fail with message "Tailscale not authenticated. Run 'tailscale up' manually or provide 'tailscale_auth_key' in vault."
- [x] T011 [US1] Create `ansible/roles/tailscale_router/tasks/verify.yml` to assert IP forwarding is active and routes are advertised locally.
- [x] T012 [US1] Create `ansible/playbooks/tailscale.yml` targeting `proxmox_hosts` and including `tailscale_router`.

## Phase 3: Tailnet "Drift Audit" (US3)

- [x] T013 [P] [US3] Create `ansible/roles/tailscale_audit/tasks/main.yml`:
    - Authenticate to API using OAuth credentials (fetch access token).
    - Fetch device details for `pve` (filter by hostname) and register to variable `tailscale_device_info`.
    - Debug/Print `tailscale_device_info` for inspection.
- [x] T014 [US3] Add assertions to `ansible/roles/tailscale_audit/tasks/main.yml`:
    - Assert `node.status == "online"` (verify field name from debug output).
    - Assert `node.lastSeen` is within last 24h.
    - Assert `node.advertisedRoutes` contains `192.168.1.0/24`.
    - Assert `node.enabledRoutes` contains `192.168.1.0/24` (if API exposes it; otherwise skip with warning).
    - Assert `node.tags` contains `tag:proxmox` (if `tailscale_tags` is set).
- [x] T015 [US3] Update `ansible/playbooks/tailscale.yml` to include `tailscale_audit` role (tagged `audit`).

## Phase 4: ACL Source of Truth (US2)

- [x] T016 [P] [US2] Create `docs/tailscale/policy.hujson` (HuJSON format) by exporting current working ACLs.
- [x] T017 [US2] Add comments to `docs/tailscale/policy.hujson` explaining GitHub identity format (`xxx@github`) and using placeholders for sensitive identities where possible.
- [x] T018 [US2] Create `docs/runbooks/tailscale-acl.md` documenting:
    - The `policy.hujson` format.
    - GitHub identity pitfalls.
    - Manual "Edit -> Copy -> Paste in Admin Console" workflow as the primary/fallback method.

## Phase 5: Safe Automated Configuration (US4)

- [x] T019 [P] [US4] Create `ansible/roles/tailscale_acl/tasks/main.yml`:
    - **Guard**: `when: tailscale_safe_mode | default(false) | bool`.
    - Step 1: Fetch current ACL from API and save to local file `backup_acl.json`.
    - Step 2: Validate `docs/tailscale/policy.hujson` using Tailscale API `/validate` endpoint (if available) or dry-run.
    - Step 3: Push `docs/tailscale/policy.hujson` to API.
    - Step 4: Rescue block: If Push fails, attempt to push `backup_acl.json` to restore state.
- [x] T020 [US4] (Optional) Implement route auto-approval logic in `tailscale_acl` if API permits safe approval, also guarded by `tailscale_safe_mode`.

## Phase 6: Verification & Polish (US5)

- [x] T021 [US5] Create `docs/runbooks/tailscale-setup.md` with "Disaster Recovery" steps (how to run the playbook on a fresh host).
- [x] T022 [US5] Add "Mobile Verification Checklist" to runbook (Cellular -> Tailscale -> Proxmox IP).
- [x] T023 [US5] Run full idempotency test: Execute playbook twice, verify `changed=0` on second run.
