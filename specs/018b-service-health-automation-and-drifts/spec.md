# Feature Specification: Service Health Automation & Drift Detection

**Feature Branch**: `018b-health-auto-drift`
**Created**: 2025-12-29
**Status**: Draft
**Input**: User description: "Automate service health checks, add email notifications, and implement drift detection"

## User Scenarios & Testing

### User Story 1 - Scheduled Execution (Priority: P1)

As an operator, I want healthchecks to run automatically on a schedule (e.g., every hour) with artifacts retained, so regressions are detected without me remembering to run commands.

**Why this priority**: Automation ensures consistent monitoring and historical data for debugging.

**Independent Test**:
1. Deploy the systemd timer.
2. Verify `systemctl list-timers` shows the job.
3. Wait for the next run or force it.
4. Check `artifacts/healthcheck/history/` for a new timestamped JSON file.

**Acceptance Scenarios**:
1. **Given** the playbook is applied, **When** the timer triggers, **Then** `run.sh` executes successfully.
2. **Given** a run completes, **When** I check the artifacts folder, **Then** `latest.json` is updated and a new history file exists.
3. **Given** the server reboots, **When** it comes back up, **Then** the timer is still active.

### User Story 2 - Notification on Failure (Priority: P1)

As an operator, I want an email when required checks fail, with a short summary and a linkable artifact path, so I notice regressions quickly.

**Why this priority**: Passive monitoring is useless if failures are ignored.

**Independent Test**:
1. Configure a dummy email recipient.
2. Intentionally break a service (e.g., stop a container).
3. Run the healthcheck.
4. Verify an email is received with the correct failure details.

**Acceptance Scenarios**:
1. **Given** all checks pass, **When** the job runs, **Then** NO email is sent (default config).
2. **Given** a check fails, **When** the job runs, **Then** an email is sent containing the failing host, URL, and error reason.
3. **Given** the email configuration is invalid, **When** the job runs, **Then** the script logs the error but does not crash the entire run.

### User Story 3 - Drift & Coverage Enforcement (Priority: P1)

As an operator, I want the system to detect when a new host/service exists in inventory but has no healthcheck coverage, so adding/removing services doesn’t silently reduce test coverage.

**Why this priority**: Prevents "silent failures" where a service is deployed but never monitored.

**Independent Test**:
1. Add a new host to the `services` group in Ansible inventory.
2. Do NOT add `healthcheck_*` variables.
3. Run the healthcheck in "coverage mode".
4. Verify it fails and reports the missing host.

**Acceptance Scenarios**:
1. **Given** a host in the `services` group without `healthcheck_path`, **When** coverage check runs, **Then** it exits with non-zero code and lists the host.
2. **Given** all hosts in `services` have `healthcheck_path`, **When** coverage check runs, **Then** it passes.

### User Story 4 - Centralized Metadata (Priority: P2)

As an operator, I want to define common healthcheck patterns in `group_vars` rather than repeating them in every `host_vars` file, to minimize duplication.

**Why this priority**: Reduces maintenance overhead and copy-paste errors.

**Independent Test**:
1. Move `healthcheck_port: 80` to `group_vars/services.yml`.
2. Remove it from individual host vars.
3. Run the healthcheck.
4. Verify it still resolves the correct port for all hosts.

**Acceptance Scenarios**:
1. **Given** a variable defined in `group_vars`, **When** the runner resolves host vars, **Then** it sees the group-level value.
2. **Given** a variable defined in both `group_vars` and `host_vars`, **When** the runner resolves host vars, **Then** the `host_vars` value takes precedence (standard Ansible behavior).

### User Story 5 - Optional Integration Hooks (Priority: P2)

As an operator, I want the system designed to allow future integrations (e.g., Uptime Kuma, Prometheus) without rewriting the core logic.

**Why this priority**: Future-proofing.

**Acceptance Scenarios**:
1. **Given** the spec, **When** reviewed, **Then** it identifies where hooks would be placed (e.g., `notify_success`, `notify_failure` functions).

## Requirements

### Functional Requirements

#### Automation
- **FR-001**: The system MUST provide Ansible templates for `healthcheck.service` and `healthcheck.timer`.
- **FR-002**: The timer MUST execute `scripts/healthcheck/run.sh` with a configurable profile (default: LAN).
- **FR-003**: The system MUST create and manage an `artifacts/healthcheck/history` directory.

#### Notifications
- **FR-004**: The system MUST support sending emails via a local MTA (e.g., `sendmail` binary) or Python `smtplib`.
- **FR-005**: Secrets (SMTP password) MUST be stored in Ansible Vault and passed via environment variables or a secured config file, NOT committed to git.
- **FR-006**: The system MUST send emails on state transitions (Success -> Failure) by default to prevent alert fatigue. A configuration option SHOULD allow "always on failure" or "on recovery" (Failure -> Success).

## Clarifications

### Session 2025-12-29
- Q: When should email notifications be triggered?
  - A: **State change only (Success -> Failure)**. This prevents alert fatigue from repeated failures.
- Q: How are monitored groups defined for coverage?
  - A: **Ansible Variable**. Defined in inventory/vars (e.g., `healthcheck_enforced_groups`) to maintain SSOT.
- Q: How frequently should coverage checks run?
  - A: **Every run (Hourly)**. Coverage checks execute alongside standard healthchecks to ensure immediate feedback on drift.
- Q: Should coverage gaps trigger an email alert?
  - A: **Yes, treat as a failure**. Coverage gaps are critical risks and must be alerted with the same urgency as service outages.

#### Drift & Coverage
- **FR-007**: The system MUST implement a "coverage mode" that scans the inventory for hosts in groups defined by the Ansible variable `healthcheck_enforced_groups` (default: `['services']`) that lack `healthcheck_path`. This check MUST run during every scheduled execution, and any gaps MUST be treated as a failure condition triggering notifications.
- **FR-008**: The system MUST generate a `baseline.json` artifact representing the expected state of the inventory (hosts and URLs) to facilitate drift detection.

#### Documentation
- **FR-009**: The system MUST include a runbook `docs/operations/healthchecks-automation.md` detailing schedule configuration, artifact locations, and troubleshooting.
- **FR-010**: The documentation MUST explain the "Group Vars First" approach for adding new services.

### Key Entities

- **Coverage Report**: A list of inventory hosts that *should* be monitored but aren't.
- **History Artifact**: A timestamped JSON file containing the results of a run.
- **Baseline Snapshot**: A JSON file listing all discovered targets, used to detect changes over time.

## Design Constraints

- **SSOT**: The Ansible inventory remains the single source of truth. No separate "targets.json" or database.
- **No Duplication**: Healthcheck metadata (paths, ports) should be defined in `group_vars` whenever possible.
- **Minimal Deps**: Email notification should use standard Python libraries or existing system binaries to avoid new pip dependencies if possible.
