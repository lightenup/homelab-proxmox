# Service Health Automation & Drift Detection

## Overview
This feature automates the execution of service healthchecks, provides email notifications on failure, and detects "drift" (services in inventory but missing healthcheck definitions).

## Configuration

### Schedule
The healthchecks run automatically via a Systemd timer.
Default schedule: Hourly (`*-*-* *:00:00`).
To change the schedule, update `healthcheck_schedule` in `ansible/roles/healthcheck_automation/defaults/main.yml` and re-run the playbook.

### Notifications
Email notifications are sent using `smtplib`.
Configuration is managed via Ansible Vault and stored in `scripts/healthcheck/.env`.
Variables:
- `smtp_host`
- `smtp_port`
- `smtp_user`
- `smtp_pass`
- `smtp_from`
- `smtp_to`

Notifications are sent **only** when:
1.  A service changes state from `PASS` to `FAIL`.
2.  A coverage gap is detected (missing `healthcheck_path`).

### Coverage & Drift
The system enforces that all hosts in specific groups (default: `services`) have a `healthcheck_path` defined.
To modify the enforced groups, update `healthcheck_enforced_groups` in `ansible/roles/healthcheck_automation/defaults/main.yml`.

## Operations

### View Logs
```bash
journalctl -u healthcheck.service
```

### Force Immediate Run
```bash
sudo systemctl start healthcheck.service
```

### Check Timer Status
```bash
systemctl list-timers healthcheck.timer
```

### View History
Artifacts are stored in `artifacts/healthcheck/history/`.
The latest result is linked at `artifacts/healthcheck/history/latest.json`.

### Troubleshooting
- **Email not sending**: Check `journalctl -u healthcheck.service` for SMTP errors. Verify `.env` file exists and has correct permissions.
- **Coverage failures**: Add `healthcheck_path` to the missing host's variables or remove the host from the enforced group.
