# Implementation Report: Service Health Automation & Drift Detection

**Feature Branch**: `018b-health-auto-drift`
**Date**: 2025-12-29
**Status**: Implemented & Validated

## 1. Overview

This feature implements automated service health monitoring, drift detection, and email notifications. It transitions the healthcheck system from a manual CLI tool to a background service running on the `monitoring` node, managed by Systemd and deployed via Ansible.

## 2. Implementation Details

### 2.1 Python Runner Enhancements
The core logic in `scripts/healthcheck/healthcheck.py` was expanded to include:
-   **SMTP Notifications**: Uses `smtplib` to send emails when a service regresses from `PASS` to `FAIL`.
-   **Drift Detection**: Scans the inventory for hosts in the `services` group that lack a `healthcheck_path` definition, flagging them as "Coverage Gaps".
-   **Static Inventory Support**: Added `--inventory` argument to load host data from a JSON file, decoupling execution from the Ansible runtime environment.
-   **History Management**: Loads `artifacts/healthcheck/history/latest.json` to compare current state with previous runs.

### 2.2 Ansible Automation
A new role `healthcheck_automation` was created to handle deployment.
-   **Installation Pattern**: Instead of running scripts directly from the git repository, the role "installs" the application to `/opt/healthcheck`.
    -   Generates a static `inventory.json` from the Ansible controller.
    -   Copies `healthcheck.py`, `run.sh`, and `inventory.json` to the target host.
    -   Creates a `.env` file containing SMTP secrets (from Ansible Vault).
-   **Systemd Integration**:
    -   `healthcheck.service`: Executes the wrapper script.
    -   `healthcheck.timer`: Triggers the service hourly.

### 2.3 Wrapper Script
`scripts/healthcheck/run.sh` was updated to:
-   Source environment variables from `.env`.
-   Manage artifact rotation (keeping the last 50 reports).
-   Pass arguments correctly to the Python script.

## 3. Modified Files

| File Path | Description |
|-----------|-------------|
| `scripts/healthcheck/healthcheck.py` | Added SMTP, drift detection, and inventory loading logic. |
| `scripts/healthcheck/run.sh` | Added env sourcing and history rotation. |
| `ansible/roles/healthcheck_automation/` | New role for deployment. |
| `ansible/playbooks/healthcheck_automation.yml` | Playbook to apply the role. |
| `docs/operations/healthchecks-automation.md` | Operational documentation. |

## 4. Validation Results

### 4.1 Deployment
The playbook `ansible/playbooks/healthcheck_automation.yml` successfully deployed the service to the `monitoring` host (192.168.1.214).

### 4.2 Execution
The service was manually triggered and verified:
-   **Timer Status**: Active (`systemctl status healthcheck.timer`).
-   **Service Status**: Ran successfully (exit code 1 due to detected failures, which is expected behavior).
-   **Logs**: Verified via `journalctl -u healthcheck.service`.

### 4.3 Observed Behavior
The healthcheck correctly identified the status of all services:
```text
HOSTNAME             STATUS     DETAILS
--------------------------------------------------------------------------------
homeassistant        FAIL       Connection error: [Errno 111] Connection refused
immich               PASS
monitoring           PASS
proxmox              PASS
reverse_proxy        PASS
```
*Note: The failure for HomeAssistant is a valid finding (port closed) and confirm the detection logic is working.*

## 5. Architectural Refactor
During implementation, we shifted from a "run-in-place" model (executing scripts from the git repo) to an "install" model.
-   **Reason**: Running `ansible-inventory` inside the remote host proved unreliable due to environment differences and interactive shell limitations ("Duplicate become password prompt").
-   **Solution**: The Ansible role now pre-calculates the inventory and ships a self-contained package to `/opt/healthcheck`. This ensures the service is robust and independent of the git repository state on the monitoring node.

## 6. Next Steps
-   Investigate and resolve the "Connection refused" error for HomeAssistant.
-   Monitor the service over 24 hours to ensure email notifications are sent correctly on state changes.
