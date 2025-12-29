# Tasks: Service Health Regression Checks

**Feature**: 018a-service-health-regression-checks
**Status**: Draft

## Phase 1: Configuration & Structure
- [x] T001 [P] Create directory structure: `scripts/healthcheck/`, `artifacts/healthcheck/`.
- [x] T002 [P] Update `.gitignore` to exclude `artifacts/healthcheck/`.
- [x] T003 [P] Add `healthcheck_*` variables to Ansible group_vars/host_vars for key services (Immich, Proxmox, Proxy).

## Phase 2: Core Runner Implementation
- [x] T004 [P] Create `scripts/healthcheck/healthcheck.py` skeleton.
  - Implement `ansible-inventory --list` execution and JSON parsing.
  - Implement logic to filter hosts by `healthcheck_path`.
- [x] T005 [P] Implement Target Resolution Logic.
  - Resolve `ansible_host` (LAN).
  - Resolve `tailscale_ip` (Tailscale) - handle missing IPs gracefully.
- [x] T006 [P] Implement HTTP Check Logic.
  - Use `requests` library.
  - Validate status code (default 200).
  - Validate JSON body (if `healthcheck_expect_json` is set).
  - Handle timeouts and connection errors.

## Phase 3: CLI & Reporting
- [x] T007 [P] Implement CLI arguments: `--profile` (lan/tailscale), `--json`, `--filter`.
- [x] T008 [P] Implement Console Output (Table format using `tabulate` or manual formatting).
- [x] T009 [P] Implement JSON Output to `artifacts/healthcheck/latest.json`.
- [x] T010 [P] Create shell wrapper `scripts/healthcheck/run.sh` to set up environment (if needed).

## Phase 4: Integration
- [x] T011 [P] Create Ansible playbook `ansible/playbooks/healthcheck.yml`.
- [x] T012 [P] Create documentation `docs/operations/healthchecks.md`.

## Phase 5: Verification
- [x] T013 [P] Verify LAN profile against live environment.
- [x] T014 [P] Verify Tailscale profile (if applicable).
- [x] T015 [P] Verify failure handling (stop a service and run check).
