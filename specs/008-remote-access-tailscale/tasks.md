# Tasks: Tailscale IaC Max + API Audit

**Feature**: 008c-tailscale-iac-max
**Status**: In Progress

## Phase 1: Setup & Discovery
- [x] T001 Create directory structure for roles (`tailscale_router`, `tailscale_audit`, `tailscale_acl`)
- [x] T002 Configure `group_vars` (split `vars.yml` and `vault.yml`)
- [x] T003 Create `scripts/tailscale/test_api_access.sh` for API verification

## Phase 2: Host-Side IaC
- [x] T004 Implement `tailscale_router` role (install, sysctl, auth, verify)
- [x] T005 Implement `tailscale_router` tasks for manual auth fallback

## Phase 3: Tailnet Drift Audit
- [x] T006 Implement `tailscale_audit` role (API-based drift detection)

## Phase 4: ACL Source of Truth
- [x] T007 Create `docs/tailscale/policy.hujson`
- [x] T008 Create `docs/runbooks/tailscale-acl.md`

## Phase 5: Safe Automated Configuration
- [x] T009 Implement `tailscale_acl` role (Commit-Confirm logic)
- [x] T010 Create `ansible/playbooks/tailscale.yml`

## Phase 6: Verification & Polish
- [x] T011 Update `docs/runbooks/tailscale-setup.md`
- [x] T012 Add "Mobile Verification Checklist" to runbook
- [x] T013 Run full idempotency test (Syntax Check)
- [x] T014 Final commit and push
