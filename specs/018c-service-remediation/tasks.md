# Tasks - Service Regression Remediation

**Feature Branch**: `018c-service-remediation`
**Status**: Completed

## 1. Runner Logic Enhancements

- [x] **1.1 Update Healthcheck Script Arguments** <!-- id: 1.1 -->
    - Modify `scripts/healthcheck/healthcheck.py`.
    - Add `--alert-on-gap` boolean argument (default: False).
- [x] **1.2 Implement SKIP Logic** <!-- id: 1.2 -->
    - Modify `scripts/healthcheck/healthcheck.py`.
    - In `perform_check`, read `healthcheck_enabled` (default True) and `healthcheck_reason`.
    - If disabled, return status `SKIP` with details from reason.
    - Ensure SKIP does not count towards non-zero exit code.
- [x] **1.3 Refine Alerting Logic** <!-- id: 1.3 -->
    - Modify `scripts/healthcheck/healthcheck.py`.
    - Update `send_email_notification`:
        - Ignore `SKIP` results.
        - Ignore `GAP` results UNLESS `alert_on_gap` is True.
        - Continue to alert on `FAIL` (regression).

## 2. Inventory Remediation

- [x] **2.1 Remediate AdGuard** <!-- id: 2.1 -->
    - Modify `ansible/host_vars/adguard.yml`.
    - Add `healthcheck_enabled: false`.
    - Add `healthcheck_reason: "Service not yet installed"`.
- [x] **2.2 Remediate Home Assistant** <!-- id: 2.2 -->
    - Modify `ansible/host_vars/homeassistant.yml`.
    - Add `healthcheck_enabled: false`.
    - Add `healthcheck_reason: "Service not yet installed"`.

## 3. Automation Role Updates

- [x] **3.1 Update Role Defaults** <!-- id: 3.1 -->
    - Modify `ansible/roles/healthcheck_automation/defaults/main.yml`.
    - Add `healthcheck_alert_on_gap: false`.
- [x] **3.2 Update Service Template** <!-- id: 3.2 -->
    - Modify `ansible/roles/healthcheck_automation/templates/healthcheck.service.j2`.
    - Update `ExecStart` to include `--alert-on-gap` if `{{ healthcheck_alert_on_gap }}` is true.
- [x] **3.3 Update Wrapper Script** <!-- id: 3.3 -->
    - Modify `scripts/healthcheck/run.sh`.
    - Ensure it passes through any new arguments (already does via `"${ARGS[@]}"`, but verify).

## 4. Deployment & Verification

- [x] **4.1 Deploy Changes** <!-- id: 4.1 -->
    - Run `ansible-playbook ansible/playbooks/healthcheck_automation.yml`.
- [x] **4.2 Verify Execution** <!-- id: 4.2 -->
    - Run `ansible monitoring -m shell -a "/opt/healthcheck/run.sh --profile lan"`.
    - Verify output shows `SKIP` for AdGuard and Home Assistant.
    - Verify exit code is 0.
