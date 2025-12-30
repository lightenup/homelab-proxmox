# Feature Specification: Service Regression Remediation (AdGuard + Home Assistant)

**Feature Branch**: `018c-service-remediation`
**Created**: 2025-12-29
**Status**: Draft
**Input**: User description: "Service Regression Remediation (AdGuard + Home Assistant)"

## Clarifications

### Session 2025-12-29
- Q: How should GAP alerts (missing healthcheck metadata) be configured? → A: Add a CLI argument (`--alert-on-gap`) to `healthcheck.py` and expose it as a variable in the Ansible role defaults.

## User Scenarios & Testing

### User Story 1 - Home Assistant Healthcheck Remediation (Priority: P1)

As an operator, I need Home Assistant to either be reachable on the expected endpoint and return a stable health response, or be marked as intentionally disabled (SKIP) with a documented reason. This ensures healthchecks reflect reality and don't generate noise.

**Why this priority**: Critical to eliminate false positives in the monitoring system.

**Independent Test**: Can be tested by running the healthcheck script against the Home Assistant host and verifying the status is either PASS or SKIP.

**Acceptance Scenarios**:

1. **Given** Home Assistant is intended to be running, **When** the healthcheck runs, **Then** it reports `homeassistant PASS` consistently.
2. **Given** Home Assistant is intentionally disabled, **When** the healthcheck runs, **Then** it reports `homeassistant SKIP (disabled: reason)` and does not count as a failure.

---

### User Story 2 - AdGuard Healthcheck Remediation (Priority: P1)

As an operator, I need AdGuard to either be reachable on the expected endpoint and return a stable health response, or be marked as intentionally disabled (SKIP) with a documented reason.

**Why this priority**: Critical to eliminate false positives in the monitoring system.

**Independent Test**: Can be tested by running the healthcheck script against the AdGuard host and verifying the status is either PASS or SKIP.

**Acceptance Scenarios**:

1. **Given** AdGuard is intended to be running, **When** the healthcheck runs, **Then** it reports `adguard PASS` consistently.
2. **Given** AdGuard is intentionally disabled, **When** the healthcheck runs, **Then** it reports `adguard SKIP (disabled: reason)` and does not count as a failure.

---

### User Story 3 - Inventory Metadata for Service Intent (Priority: P1)

As an operator, I want to express service intent in inventory metadata (host_vars/group_vars) so the healthcheck system can distinguish between failures, intentional skips, and coverage gaps.

**Why this priority**: Foundation for US1 and US2, enabling the system to understand operator intent.

**Independent Test**: Can be tested by modifying host variables and verifying `healthcheck.py` output reflects the changes (PASS/FAIL/SKIP/GAP).

**Acceptance Scenarios**:

1. **Given** a host with `healthcheck_enabled: false`, **When** the healthcheck runs, **Then** it reports status `SKIP` with the provided reason.
2. **Given** a host with `healthcheck_enabled: true` (default), **When** the healthcheck runs, **Then** it performs the check and reports `PASS` or `FAIL`.
3. **Given** a host in the services group with no healthcheck metadata, **When** the healthcheck runs, **Then** it reports `GAP`.

---

### User Story 4 - Refined Email Notifications (Priority: P2)

As an operator, I want email alerts only when a service transitions from PASS to FAIL (true regression), ignoring SKIP states and configurable GAP alerts.

**Why this priority**: Reduces alert fatigue and ensures alerts are actionable.

**Independent Test**: Can be tested by simulating state transitions and verifying email delivery.

**Acceptance Scenarios**:

1. **Given** a service transitions from PASS to FAIL, **When** the healthcheck runs, **Then** an email alert is sent.
2. **Given** a service is in SKIP state, **When** the healthcheck runs, **Then** no email alert is sent.
3. **Given** a service is in GAP state, **When** the healthcheck runs, **Then** no email alert is sent (unless explicitly configured).

---

## Functional Requirements

- **FR-001**: Healthcheck runner must support `SKIP` state via inventory metadata (e.g., `healthcheck_enabled: false` + `healthcheck_reason`).
- **FR-002**: For enabled services, healthcheck must validate endpoint with configurable scheme, host, port, path, expected status code, and optional body match.
- **FR-003**: For AdGuard and Home Assistant, remediation must be implemented by either enabling the service deployment or explicitly disabling monitoring (SKIP).
- **FR-004**: Drift detection must continue to find "coverage gaps" for services group members lacking healthcheck metadata.
- **FR-005**: Email notifications must ignore SKIP states and must not alert on GAP unless configured via `--alert-on-gap` CLI argument (default: off).

## Success Criteria

- **Measurable**: `healthcheck.service` produces 0 false positive alerts over a 24-hour period.
- **Measurable**: All hosts in the `services` group have a status of PASS, SKIP, or GAP (with GAP being 0 for fully covered inventory).
- **User-focused**: Operator receives email alerts only for genuine service regressions.
- **Verifiable**: `ansible-playbook playbooks/site.yml` runs with `changed=0` on subsequent runs (idempotency).

## Key Entities & Data

- **Inventory Metadata**: `healthcheck_enabled` (boolean), `healthcheck_reason` (string).
- **Healthcheck Status**: Enum [PASS, FAIL, SKIP, GAP].
- **Artifacts**: JSON reports containing status and reasons for all hosts.

## Assumptions

- The network environment (flat LAN) remains unchanged for this iteration.
- Secrets are managed via existing Ansible Vault mechanisms.
- AdGuard and Home Assistant installation issues (if any) can be resolved via standard Ansible tasks or Docker Compose adjustments.
- **[Entity 2]**: [What it represents, relationships to other entities]

## Success Criteria *(mandatory)*

<!--
  ACTION REQUIRED: Define measurable success criteria.
  These must be technology-agnostic and measurable.
-->

### Measurable Outcomes

- **SC-001**: [Measurable metric, e.g., "Users can complete account creation in under 2 minutes"]
- **SC-002**: [Measurable metric, e.g., "System handles 1000 concurrent users without degradation"]
- **SC-003**: [User satisfaction metric, e.g., "90% of users successfully complete primary task on first attempt"]
- **SC-004**: [Business metric, e.g., "Reduce support tickets related to [X] by 50%"]
