# Implementation Plan - Service Regression Remediation

**Feature Branch**: `018c-service-remediation`
**Status**: Draft

## 1. Architecture & Design

### 1.1 Inventory Metadata (SSOT)
We will extend the existing Ansible inventory metadata model to support explicit service states.
*   **New Variable**: `healthcheck_enabled` (boolean, default: `true`).
*   **New Variable**: `healthcheck_reason` (string, optional).
*   **Location**: `host_vars/` or `group_vars/`.

### 1.2 Healthcheck Runner (`healthcheck.py`)
The Python script needs logic updates to handle the new states:
*   **SKIP**: If `healthcheck_enabled` is false. Log as SKIP, do not count as failure, do not alert.
*   **GAP**: If host in `services` group has no healthcheck metadata. Log as GAP.
*   **Alerting**:
    *   **SKIP**: Never alert.
    *   **GAP**: Alert only if `--alert-on-gap` flag is present.
    *   **FAIL**: Alert on regression (PASS -> FAIL).

### 1.3 Ansible Automation
The `healthcheck_automation` role needs to support the new configuration options.
*   **Configuration**: Add `healthcheck_alert_on_gap` to defaults (default: `false`).
*   **Service Definition**: Update `healthcheck.service` template to pass `--alert-on-gap` if enabled.

## 2. Implementation Steps

### Phase 1: Runner Logic Enhancements
*   Modify `scripts/healthcheck/healthcheck.py`:
    *   Add CLI argument `--alert-on-gap`.
    *   Implement logic to check `healthcheck_enabled` from host vars.
    *   Update status reporting to include `SKIP` and `GAP`.
    *   Refine `send_email_notification` to respect new alerting rules.

### Phase 2: Inventory Updates (Remediation)
*   **Home Assistant**: Update `ansible/host_vars/homeassistant.yml`. Set `healthcheck_enabled: false`, `healthcheck_reason: "Service not yet installed"`.

### Phase 3: Automation Role Updates
*   Update `ansible/roles/healthcheck_automation/defaults/main.yml` to include `healthcheck_alert_on_gap: false`.
*   Update `ansible/roles/healthcheck_automation/templates/healthcheck.service.j2` to conditionally add the `--alert-on-gap` flag.

### Phase 4: Deployment & Verification
*   Run playbook `ansible/playbooks/healthcheck_automation.yml`.
*   Manually trigger healthcheck on monitoring host.
*   Verify HA shows as `SKIP`.
*   Verify exit code is 0 (PASS) if only SKIPs/PASSes exist.

## 3. Verification Plan

### 3.1 Automated Tests
*   **Unit/Local**: Run `healthcheck.py --inventory ...` locally against modified inventory to verify SKIP output.

### 3.2 Manual Verification
*   **Deployment**: `ansible-playbook ...`
*   **Runtime**: `systemctl start healthcheck.service`
*   **Logs**: `journalctl -u healthcheck.service` should show "SKIP" for HA and no "Sending email" logs.
