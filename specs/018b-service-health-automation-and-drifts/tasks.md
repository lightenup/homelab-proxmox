# Tasks - Service Health Automation & Drift Detection

**Feature Branch**: `018b-health-auto-drift`
**Status**: Complete

## 1. Python Runner Enhancements

- [x] **1.1 Implement SMTP Notification** <!-- id: 1.1 -->
    - Modify `scripts/healthcheck/healthcheck.py`.
    - Add `send_email` function using `smtplib`.
    - Read config from env vars (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM`, `SMTP_TO`).
    - **Logic**: Load `artifacts/healthcheck/history/latest.json`. Compare current status with previous.
    - **Trigger**: Send email ONLY if state transitions from Success -> Failure (or if coverage gaps exist).
    - **Hooks**: Add placeholder comments/functions for `notify_success` and `notify_failure` to support future integrations (US5).
- [x] **1.2 Implement Coverage Mode** <!-- id: 1.2 -->
    - Modify `scripts/healthcheck/healthcheck.py`.
    - Add `--check-coverage` argument (or run by default).
    - Logic: Iterate inventory, check for `healthcheck_path` on hosts in groups defined by `healthcheck_enforced_groups` (default: `['services']`).
    - **Artifact**: Generate `artifacts/healthcheck/baseline.json` listing all discovered targets (FR-008).
    - **Behavior**: If gaps found, add to failure list and return exit code 1.
- [x] **1.3 Update Wrapper Script** <!-- id: 1.3 -->
    - Modify `scripts/healthcheck/run.sh`.
    - Add history rotation (keep last N files).
    - Source `.env` file if present (for SMTP secrets).
    - Ensure `healthcheck.py` is called with coverage checks enabled.

## 2. Ansible Automation

- [x] **2.1 Create Role Structure** <!-- id: 2.1 -->
    - `mkdir -p ansible/roles/healthcheck_automation/{tasks,templates,defaults,handlers}`.
    - Define `healthcheck_enforced_groups: ['services']` in `defaults/main.yml`.
- [x] **2.2 Create Systemd Templates** <!-- id: 2.2 -->
    - Create `ansible/roles/healthcheck_automation/templates/healthcheck.service.j2`.
    - Create `ansible/roles/healthcheck_automation/templates/healthcheck.timer.j2`.
- [x] **2.3 Implement Role Tasks** <!-- id: 2.3 -->
    - `ansible/roles/healthcheck_automation/tasks/main.yml`.
    - Task: Install systemd units.
    - Task: Create `.env` file from Vault secrets at `scripts/healthcheck/.env`.
    - Task: Enable timer.
- [x] **2.4 Add to Playbook** <!-- id: 2.4 -->
    - Add role to `ansible/site.yml` (targeting `localhost` or monitoring node).

## 3. Documentation & Verification

- [x] **3.1 Create Operations Doc** <!-- id: 3.1 -->
    - `docs/operations/healthchecks-automation.md`.
- [x] **3.2 Verify Implementation** <!-- id: 3.2 -->
    - Run coverage check.
    - Test email notification.
    - Verify systemd timer.
