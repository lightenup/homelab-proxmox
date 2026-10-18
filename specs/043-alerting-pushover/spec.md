# Feature Specification: Pushover Alerting Integration

**Feature Branch**: `043-alerting-pushover`
**Created**: 2026-03-02
**Status**: Draft
**Input**: User description: "Alerting"

## Overview

The homelab monitoring stack (established in Features 040–042) delivers all alert notifications exclusively via email. Email is unreliable for time-critical alerts — messages may be delayed, filtered to spam, or simply not checked for hours. This feature adds push notifications to the operator's phone via Pushover, with severity-based priority routing: critical alerts (NAS down, endpoint unreachable, disk full) bypass quiet hours and repeat until acknowledged, while warning alerts arrive at normal priority respecting quiet hours. Email delivery continues unchanged for all alerts, providing a persistent record and fallback channel.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Critical Alert Push Notifications (Priority: P1)

As a homelab administrator, I want critical alerts pushed to my phone immediately with emergency priority that repeats until I acknowledge them, so that I can respond to service-threatening issues (NAS down, endpoint unreachable, disk critically full, TLS certificate expiring imminently, fail2ban monitoring offline) within minutes — regardless of whether I am actively checking email.

**Why this priority**: Critical alerts represent active service outages or imminent failures. The current email-only delivery means the operator may not see a "SynologyNASDown" or "DiskSpaceCritical" alert for hours if they are away from their inbox. Push notifications with emergency priority and forced acknowledgment ensure human awareness and confirm receipt, which is the core problem this feature solves.

**Independent Test**: Trigger a test critical alert via the alerting system. Confirm a push notification arrives on the phone within 2 minutes, repeats every 60 seconds, and stops repeating after acknowledgment.

**Acceptance Scenarios**:

1. **Given** push notifications are enabled and credentials are configured, **When** a critical-severity alert fires (e.g., SynologyNASDown, EndpointDown, DiskSpaceCritical, TLSCertExpiryCritical, Fail2banDown), **Then** the operator receives a push notification on their phone within 2 minutes of the alert firing, with a title clearly indicating "[CRITICAL]" and the alert name.
2. **Given** a critical push notification has been delivered, **When** the operator has not acknowledged it, **Then** the notification repeats every 60 seconds for up to 1 hour.
3. **Given** a critical push notification is repeating, **When** the operator acknowledges it via the push notification app, **Then** the repeating stops immediately.
4. **Given** a critical push notification has been repeating for 1 hour without acknowledgment, **When** the 1-hour expiry window passes, **Then** the notification stops repeating (does not nag indefinitely).
5. **Given** a critical alert fires, **When** the push notification is delivered, **Then** the notification message includes the alert summary text (from the alert's `annotations.summary` field), providing enough context to understand the issue without opening a dashboard.
6. **Given** multiple critical alerts fire simultaneously (e.g., NAS down causes both SynologyNASDown and DiskSpaceCritical), **When** push notifications are sent, **Then** each distinct alert group produces a separate push notification — the operator receives one notification per alert group, not one per individual alert instance.

---

### User Story 2 — Warning Alert Push Notifications (Priority: P1)

As a homelab administrator, I want warning-level alerts pushed to my phone at normal priority that respects quiet hours, so that I am aware of developing issues (high CPU, TLS certificate approaching expiry, elevated ban rate, high error rate) during waking hours without being woken at 3 AM for non-urgent matters.

**Why this priority**: Warning alerts indicate degradation that may escalate to critical if unaddressed (e.g., disk at 87% will eventually hit 95%). Email-only delivery means warnings may be missed for the same reasons as critical alerts. However, warnings are not emergencies — they should not bypass quiet hours or require acknowledgment. Normal-priority push notifications strike the right balance: visible during the day, silent at night.

**Independent Test**: Trigger a test warning alert. Confirm a push notification arrives on the phone at normal priority. Set quiet hours in the push notification app, trigger another warning, and confirm no sound/vibration is produced during quiet hours.

**Acceptance Scenarios**:

1. **Given** push notifications are enabled, **When** a warning-severity alert fires (e.g., HighCPUUsage, DiskSpaceWarning, TLSCertExpiringSoon, Fail2banHighBanRate, CaddyHighErrorRate), **Then** the operator receives a push notification at normal priority with a title clearly indicating "[WARNING]" and the alert name.
2. **Given** the operator has configured quiet hours in the push notification app (e.g., 11 PM to 7 AM), **When** a warning alert fires during quiet hours, **Then** the notification is delivered silently (no sound or vibration) — the operator sees it when they next check their phone.
3. **Given** a warning push notification has been delivered, **When** the operator views the notification, **Then** it does NOT require acknowledgment and does NOT repeat — it behaves as a standard one-time push notification.
4. **Given** a warning alert fires, **When** the push notification is delivered, **Then** the notification message includes the alert summary text, providing context about the warning condition.

---

### User Story 3 — Alert Resolution Notifications (Priority: P2)

As a homelab administrator, I want to receive a "resolved" push notification when a previously firing alert clears, so that I know the issue has been fixed without needing to manually check the monitoring dashboard or email.

**Why this priority**: Without resolution notifications, the operator must actively check whether a previously reported issue is still ongoing. A "resolved" notification closes the loop: "DiskSpaceCritical fired → I acknowledged it → I expanded the disk → Resolved notification confirms the fix worked." This is particularly valuable after critical alerts where the operator has taken remediation action and wants confirmation.

**Independent Test**: Trigger a test alert (critical or warning). Confirm the alert notification arrives. Then clear the test alert. Confirm a "resolved" notification arrives on both push and email channels.

**Acceptance Scenarios**:

1. **Given** a critical alert has previously fired and a push notification was sent, **When** the alert condition clears (metric returns to healthy), **Then** the operator receives a "resolved" push notification identifying which alert cleared.
2. **Given** a warning alert has previously fired, **When** the alert condition clears, **Then** the operator receives a "resolved" push notification.
3. **Given** a critical or warning alert fires and resolves, **When** the operator checks their email, **Then** a "resolved" email was also sent — confirming both channels receive resolution notifications.

---

### User Story 4 — Push Notification Opt-In with Safe Defaults (Priority: P2)

As a homelab administrator, I want push notifications to be an opt-in feature that does not break the monitoring stack when not configured, so that the alerting system works correctly during CI testing, lab environments, or before I have signed up for the push notification service.

**Why this priority**: The monitoring stack is deployed via CI/CD and must function without push notification credentials. A mandatory dependency on an external push service would break CI pipelines and prevent lab testing. The feature-flag pattern ensures backward compatibility and allows incremental adoption: deploy the monitoring stack first, add push notification credentials later.

**Independent Test**: Deploy the monitoring stack with push notifications disabled (default). Trigger a test alert. Confirm the email notification arrives normally and no errors appear in the alerting system logs related to missing push notification credentials.

**Acceptance Scenarios**:

1. **Given** push notifications are disabled (the default configuration), **When** an alert fires, **Then** the alert is delivered via email only — no errors, no warnings about missing push credentials in the alerting system logs.
2. **Given** push notifications are disabled, **When** the monitoring playbook is run, **Then** no push notification receiver configuration is generated in the alerting system — the configuration is identical to the pre-feature state.
3. **Given** push notifications are enabled but credentials are missing from the vault, **When** the monitoring playbook runs, **Then** the playbook fails with a clear error message identifying which credentials are missing — rather than deploying a broken configuration that silently fails at notification time.
4. **Given** push notifications are enabled and valid credentials are configured, **When** the monitoring playbook runs, **Then** the push notification receivers are added to the alerting configuration alongside the existing email receiver — the email receiver remains unchanged.

---

### User Story 5 — Email Continuity for All Alerts (Priority: P2)

As a homelab administrator, I want all alerts to continue being delivered via email regardless of whether push notifications are enabled, so that I have a persistent, searchable record of all alert history and a fallback channel if my phone is unavailable.

**Why this priority**: Push notifications are transient — once dismissed, there is no searchable archive. Email provides a persistent audit trail of all alerts and their resolution times. Additionally, if the operator's phone is dead, in airplane mode, or the push notification service experiences an outage, email ensures no alerts are silently lost.

**Independent Test**: Enable push notifications. Trigger a critical and a warning alert. Confirm both push notifications AND emails arrive for each alert. Disable push notifications. Trigger another alert. Confirm email still arrives.

**Acceptance Scenarios**:

1. **Given** push notifications are enabled, **When** a critical alert fires, **Then** BOTH a push notification AND an email notification are delivered — push does not replace email.
2. **Given** push notifications are enabled, **When** a warning alert fires, **Then** BOTH a push notification AND an email notification are delivered.
3. **Given** push notifications are disabled, **When** any alert fires, **Then** email notifications are delivered exactly as they were before this feature — no changes to email routing, grouping, or timing.
4. **Given** push notifications are enabled, **When** the alerting system's existing group-by, group-wait, group-interval, and repeat-interval timings are checked, **Then** they remain unchanged from the pre-feature configuration — push notification routing does not alter the existing email behavior.

---

### Edge Cases

- **What happens if the push notification service is unreachable when a critical alert fires?** The alerting system logs the delivery failure and retries on the next evaluation cycle. The email notification is unaffected and still delivered because routing to push and email are independent channels with `continue: true`. The operator receives the email even if push fails.
- **What happens if the operator does not acknowledge a critical push notification and the 1-hour expiry passes?** The push notification service stops retrying. The alert remains active in the alerting system. On the next repeat interval (default 4 hours), the alerting system sends a new notification batch — which triggers a fresh emergency push notification, restarting the 1-hour acknowledgment cycle.
- **What happens if push notification credentials are rotated (API token regenerated)?** The old token stops working immediately. Push notifications fail silently until the vault is updated with the new token and the monitoring playbook is re-run. Email notifications continue unaffected. The alerting system logs push delivery failures.
- **What happens during a monitoring stack redeployment?** Brief interruption (1–2 minutes) during which no notifications of either type are sent. Alerts that fire during redeployment are queued and processed once the alerting system restarts. No notifications are lost.
- **What happens if the same alert fires and resolves repeatedly in quick succession (flapping)?** The alerting system's existing grouping and repeat-interval settings govern notification frequency. Push notifications follow the same grouping rules as email. The operator receives grouped notifications, not individual push notifications for each flap cycle.
- **What happens when the operator has multiple devices registered with the push notification service?** All registered devices receive the notification. Device targeting is managed in the push notification app's settings, not in the alerting configuration. This feature sends to the user key, which delivers to all devices by default.
- **What happens if a critical alert fires during the push notification app's quiet hours?** Emergency-priority notifications bypass quiet hours by design — the phone sounds/vibrates regardless. This is the intended behavior for critical alerts that require immediate attention.
- **What happens to alerts that have no severity label?** They fall through to the default email-only route. Only alerts explicitly labeled `severity: critical` or `severity: warning` are routed to push notification channels. All 18 existing alert rules have severity labels assigned.

## Requirements *(mandatory)*

### Functional Requirements

#### Push Notification Channel

- **FR-001**: The alerting system MUST support a push notification channel alongside the existing email channel, delivering notifications to the operator's mobile device via a push notification service. *(traces to US-1, US-2)*
- **FR-002**: The push notification channel MUST support severity-based priority routing: critical alerts at emergency priority (repeats until acknowledged) and warning alerts at normal priority (respects quiet hours). *(traces to US-1, US-2)*
- **FR-003**: Emergency-priority push notifications for critical alerts MUST repeat every 60 seconds until acknowledged by the operator, with a maximum retry duration of 1 hour. *(traces to US-1, AC-1.2, AC-1.3, AC-1.4)*
- **FR-004**: Normal-priority push notifications for warning alerts MUST respect the operator's quiet hours configuration in the push notification app — delivering silently during quiet hours. *(traces to US-2, AC-2.2)*
- **FR-005**: All push notifications MUST include the alert name in the title (prefixed with severity level) and the alert summary annotation in the message body. *(traces to US-1 AC-1.5, US-2 AC-2.4)*
- **FR-006**: The alerting system MUST send "resolved" notifications via the push notification channel when a previously firing alert clears, for both critical and warning severities. *(traces to US-3)*

#### Routing and Email Continuity

- **FR-007**: All alerts MUST continue to be delivered via email regardless of push notification configuration — push notifications are an additional channel, not a replacement. *(traces to US-5)*
- **FR-008**: The routing configuration MUST use `continue: true` on push notification routes so that alerts fall through to the email receiver after being sent to push. *(traces to US-5, AC-5.1, AC-5.2)*
- **FR-009**: The existing alerting system group-by settings (`alertname`, `severity`), timing settings (group_wait, group_interval, repeat_interval), and email receiver configuration MUST remain unchanged. *(traces to US-5, AC-5.4)*
- **FR-010**: Alerts without a `severity` label MUST route to the default email-only receiver — they MUST NOT be sent to the push notification channel. *(traces to edge case: alerts without severity label)*

#### Feature Flag and Credential Management

- **FR-011**: Push notifications MUST be disabled by default via a feature flag (defaulting to off). When disabled, the alerting configuration MUST NOT include push notification receivers or routes. *(traces to US-4, AC-4.1, AC-4.2)*
- **FR-012**: When push notifications are enabled, the deployment MUST validate that push notification credentials (user key and API token) are defined in the vault before generating the alerting configuration. Missing credentials MUST cause the playbook to fail with a clear error message. *(traces to US-4, AC-4.3)*
- **FR-013**: Push notification credentials (user key and API token) MUST be stored exclusively in Ansible vault — never in plaintext in the repository. *(traces to constitution secrets policy)*
- **FR-014**: The feature flag and tuning parameters (retry interval, expiry duration) MUST be defined as role defaults with sensible values that can be overridden in group_vars. *(traces to US-4)*

#### Severity-to-Priority Mapping

- **FR-015**: The alerting system MUST map severity levels to push notification priorities as follows: `critical` → emergency priority (bypasses quiet hours, requires acknowledgment), `warning` → normal priority (respects quiet hours, no acknowledgment required). *(traces to US-1, US-2)*
- **FR-016**: A future `info` severity level (not currently used by any alert rule) SHOULD map to low priority (no sound or vibration). This is not required for initial delivery but the routing structure SHOULD accommodate it without rework. *(traces to future extensibility)*

#### Alert Coverage

- **FR-017**: All 18 existing alert rules across all alert rule files (7 critical, 11 warning) MUST be routed to the appropriate push notification channel based on their severity label. No alert rule changes are required — the routing is based on the existing `severity` label. *(traces to US-1, US-2)*

### Key Entities

- **Push Notification Receiver**: A named alerting system receiver configuration that sends notifications to the operator's mobile device via a push notification service API. Contains: service credentials (user key, API token), priority level, retry/expiry settings for emergency priority, message title template, and message body template. Two receivers exist: one for critical (emergency priority) and one for warning (normal priority).
- **Severity-Based Route**: An alerting system routing rule that matches alerts by their `severity` label and directs them to a specific receiver. Routes use `continue: true` to ensure alerts are also processed by downstream receivers (email).
- **Feature Flag**: A boolean configuration variable (`pushover_enabled`) that gates the entire push notification integration. When false, no push notification receivers or routes are included in the generated alerting configuration.
- **Push Notification Credentials**: A pair of secrets (user key identifying the recipient, API token identifying the sending application) stored in Ansible vault, required only when the feature flag is enabled.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Operator receives a push notification on their phone within 2 minutes when any critical alert fires — verified by triggering a test critical alert and confirming delivery.
- **SC-002**: Critical push notifications repeat until acknowledged — verified by triggering a critical alert, waiting 2 minutes, and confirming a second notification is received.
- **SC-003**: Operator receives a push notification on their phone when any warning alert fires, at normal priority that does not bypass quiet hours — verified by triggering a test warning alert.
- **SC-004**: Operator receives both a push notification and an email for the same alert — verified by triggering a test alert and confirming delivery on both channels.
- **SC-005**: Operator receives a "resolved" push notification when a previously firing alert clears — verified by triggering and then clearing a test alert.
- **SC-006**: With push notifications disabled (default), the monitoring stack deploys successfully and email alerts function identically to the pre-feature state — verified by deploying without push credentials and triggering a test alert.
- **SC-007**: With push notifications enabled but credentials missing, the deployment fails with a clear error message — verified by enabling the flag without adding vault credentials.
- **SC-008**: Existing alerting behavior (grouping, timing, email delivery, inhibition rules) remains unchanged after enabling push notifications — verified by comparing the alerting configuration's route/receiver structure and confirming email-only paths are unmodified.
- **SC-009**: Re-running the monitoring playbook after enabling push notifications produces an idempotent result — no unexpected changes on the second run.
- **SC-010**: All 18 existing alert rules are routed correctly: 7 critical alerts to the emergency push channel, 11 warning alerts to the normal push channel, and all 18 to email — verified by inspecting the generated alerting configuration and confirming route matching.

## Assumptions

- **A-001**: Features 040 (Monitoring Overhaul), 041 (Monitoring Tier B), and 042 (Monitoring Tier C) are fully merged and operational. The alerting system (Alertmanager v0.30.0), all 18 alert rules, 8 inhibition rules, and email notification channel are deployed and functional.
- **A-002**: The operator will sign up for a Pushover account ($5 one-time per platform), create an application, and manually add the user key and API token to the Ansible vault before enabling the feature flag. This is a one-time manual prerequisite.
- **A-003**: The alerting system (Alertmanager v0.30.0) natively supports Pushover as a receiver type — no additional software or plugins are required.
- **A-004**: All 18 existing alert rules have a `severity` label assigned (either `critical` or `warning`). No alert rules lack a severity label.
- **A-005**: The existing alerting system routing and receiver configuration is defined in a Jinja2 template (`alertmanager.yml.j2`) that can be extended with conditional blocks gated by the feature flag.
- **A-006**: The Pushover service is externally hosted (pushover.net) and the monitoring LXC (192.168.1.214) has outbound internet access on HTTPS (port 443) to reach the Pushover API.
- **A-007**: Alert volume is low (homelab context) — typically 0–3 alerts per day. Push notification rate limits imposed by Pushover (7,500 messages per month per application) will not be exceeded.
- **A-008**: Quiet hours behavior is managed entirely by the Pushover mobile app — no time-based muting configuration is needed in the alerting system. Emergency-priority notifications bypass quiet hours by Pushover's design.

## Non-Functional Requirements

- **NFR-001**: Push notification delivery latency MUST be less than 2 minutes from alert firing to notification appearing on the operator's phone — accounting for alerting system evaluation, push API call, and Pushover's delivery pipeline.
- **NFR-002**: The push notification integration MUST NOT increase the alerting system container's resource consumption by more than negligible overhead (no new processes or containers — it is a configuration change to the existing alerting system).
- **NFR-003**: The feature flag MUST allow toggling push notifications on or off by changing a single variable and re-running the monitoring playbook — no manual configuration on the monitoring host required.

## Out of Scope

- **New alert rules** — This feature adds a notification channel only. No new alert rules are created and no existing alert thresholds or conditions are modified.
- **Alert rule severity reclassification** — The existing severity labels (7 critical, 11 warning) are taken as-is. Reclassifying any alert's severity is a separate concern.
- **Multi-user push notifications** — Only a single operator (one Pushover user key) is supported. Sending to multiple family members or device groups is deferred.
- **Pushover device targeting** — Sending to specific devices within the operator's Pushover account is not configured. All registered devices receive all notifications.
- **Time-based muting in the alerting system** — Quiet hours are handled by the Pushover app, not by Alertmanager time-based routes. Adding Alertmanager mute_time_intervals is deferred.
- **Alternative push notification services** — Only Pushover is supported. Slack, Discord, Telegram, ntfy, Gotify, and other alternatives are not evaluated or integrated.
- **Per-alert-rule push notification routing** — All critical alerts go to the same push channel and all warning alerts go to the same push channel. Per-rule routing (e.g., "only push NAS alerts but not CPU alerts") is not supported.
- **Dashboard or Grafana integration** — No link to Grafana dashboard is included in the push notification body. A static URL to the Grafana instance may be included as a convenience, but deep-linking to specific alert dashboards is out of scope.
- **Push notification history or audit trail** — Pushover's message history is managed by the Pushover app. No additional logging or archiving of push notifications is implemented in the homelab infrastructure.
- **Inhibition rule changes** — The existing 8 inhibition rules from Features 040–042 are unchanged. No new inhibition rules are needed for the push notification channel because inhibition operates at the alert level (before routing to receivers), not at the receiver level.

## Constraints

- **C-001**: Must follow existing IaC patterns — Ansible roles and playbooks for all configuration, secrets in Ansible vault, idempotent deployments. Per constitution Section I (Spec-Driven Workflow) and Section II (Secrets Policy).
- **C-002**: Must not alter existing alerting behavior — email receiver configuration, routing group-by/timing, and inhibition rules remain unchanged. Push notification routes are additive only.
- **C-003**: Must not require any new containers, processes, or infrastructure components — this is a configuration change to the existing Alertmanager deployment.
- **C-004**: Must comply with the constitution's dual-provisioning parity (Section V) — deployable from both CI/CD (GitHub Actions) and developer laptop.
- **C-005**: Must comply with the constitution's code economy principle (Section IV) — no unnecessary abstraction. The feature flag and credential validation are the minimal additions needed.
- **C-006**: The Pushover credentials are external to the repository — the operator must manually add them to the vault. The deployment must not assume credentials exist unless the feature flag is explicitly enabled.

## Dependencies

- **D-001**: Feature 040 (Monitoring Overhaul) — the unified alerting framework, Alertmanager configuration template, email receiver, and all infrastructure alert rules. Must be merged.
- **D-002**: Feature 041 (Monitoring Tier B) — external exporter alerts (Caddy, Nextcloud) and vault preflight assertion pattern. Must be merged.
- **D-003**: Feature 042 (Monitoring Tier C) — security alerts (EndpointDown, TLSCert*, Fail2ban*), which complete the full set of 18 alert rules that will be routed to push. Must be merged.
- **D-004**: Pushover account and application — operator must have signed up for Pushover, installed the mobile app, created an application, and obtained the user key and API token. This is a manual prerequisite performed outside the IaC workflow.
- **D-005**: Outbound internet access from the monitoring LXC (192.168.1.214) to `api.pushover.net` over HTTPS (port 443).

## Decision Log

| # | Ambiguity | Decision | Rationale |
|---|-----------|----------|-----------|
| DL-01 | Should warning-level alerts be sent to Pushover, or only critical? | Yes — warnings are sent at normal priority. | The homelab has low alert volume (18 rules total, typically 0–3 alerts per day). Normal-priority notifications respect quiet hours, so there is no risk of 3 AM noise for warnings. The operator benefits from being aware of developing issues (TLS cert approaching expiry, disk filling up) before they escalate to critical. Excluding warnings would mean the operator only learns of problems after they become emergencies. |
| DL-02 | What retry interval and expiry duration for emergency push notifications? | Retry every 60 seconds, expire after 1 hour (3600 seconds). | 60-second retry is aggressive enough for a homelab where the operator is typically within arm's reach of their phone. 1-hour expiry prevents infinite nagging if the operator is genuinely unavailable (e.g., at work, sleeping). After expiry, the alerting system's repeat_interval (4 hours) will re-trigger, starting a fresh emergency cycle — so the alert is not silently lost. |
| DL-03 | Should quiet hours be managed in Alertmanager or the Pushover app? | Pushover app handles quiet hours natively. No Alertmanager changes. | Pushover's priority system handles this by design: emergency (priority 2) bypasses quiet hours, normal (priority 0) respects them. Adding Alertmanager `mute_time_intervals` would duplicate this logic, introduce configuration complexity, and risk desynchronization between two quiet-hours systems. The Pushover app gives the operator direct control over their own quiet hours schedule. |
| DL-04 | Should resolved notifications be sent via push? | Yes — `send_resolved: true` on all push receivers. | Resolution notifications close the feedback loop for the operator. After receiving "DiskSpaceCritical" and taking action, a "Resolved: DiskSpaceCritical" push notification confirms the fix worked without requiring the operator to open Grafana or check email. The marginal cost (one extra push per alert lifecycle) is negligible given the low alert volume. |
| DL-05 | Should the Grafana URL be included in push notifications? | Yes — as a static convenience link to the Grafana instance root. | Including `https://grafana.hus-sky.no` in the push notification gives the operator a one-tap path to investigate. Deep-linking to specific alert dashboards is out of scope (would require per-alert URL templates), but the root Grafana URL is simple and useful. |
| DL-06 | How should the feature flag default? | Disabled (`pushover_enabled: false`). | The monitoring stack must function without Pushover credentials during CI, lab testing, and initial deployment. Defaulting to disabled ensures backward compatibility and prevents deployment failures when credentials are not yet configured. The operator explicitly opts in by setting `pushover_enabled: true` and adding vault credentials. |
| DL-07 | Should per-alert push notification routing be supported (e.g., push NAS alerts but not CPU alerts)? | No — all alerts of a given severity go to the same push channel. | Per-alert routing adds configuration complexity that is not justified for an 18-rule homelab. The severity-based split (critical = emergency, warning = normal) provides sufficient differentiation. If specific alerts are too noisy, the correct fix is to adjust the alert's threshold or severity, not to add per-alert routing exceptions. |
| DL-08 | What happens to the `info` severity level (not currently used)? | Reserve low priority mapping for future use. The routing structure should accommodate it without rework, but no `info` route is deployed now. | No existing alert rules use `info` severity, so deploying an info route would violate YAGNI (constitution Section IV). However, the routing structure (match on severity label → route to receiver) naturally extends to a third severity level without structural changes. Documenting the intended mapping (info → low priority) ensures consistency when info-level alerts are eventually introduced. |

## Open Questions

None — all ambiguities resolved in Decision Log above.

## Self-Critique

### Strengths
- Comprehensive user stories with well-structured Given/When/Then acceptance scenarios covering both happy paths and failure modes.
- Edge cases section is thorough — covers service outages, flapping, credential rotation, redeployment windows, multi-device delivery, and quiet-hours interaction.
- Decision Log is detailed with clear rationale for each ambiguity resolved. No TBD items remain.
- Clear separation of concerns: the spec describes *what* behavior is required without prescribing Jinja2 templates, Ansible task structure, or API call sequences.
- Feature flag pattern (FR-011, FR-012) ensures backward compatibility and aligns with constitution's CI/CD expectations and dual-provisioning parity.
- Constitution cross-references are explicit (secrets policy, code economy, dual-provisioning parity, separation of concerns).

### Issues Found
- **[severity: medium]** Alert count was incorrect: spec originally stated "17 alert rules (7 critical, 10 warning)" but the actual codebase contains 18 alert rules (7 critical, 11 warning). ImmichJobBacklogHigh (warning) was uncounted. **Fixed**: All 10 occurrences of "17" updated to "18" and "10 warning" updated to "11 warning" throughout the spec.
- **[severity: low]** DL-05 referenced `http://grafana.hus-sky.no` but `group_vars/monitoring/vars.yml` shows `grafana_protocol: "https"` — the Grafana instance uses HTTPS (established in Feature 039). **Fixed**: Updated to `https://grafana.hus-sky.no`.
- **[severity: low]** FR-016 mentions a future `info` severity level and uses SHOULD language, which is borderline YAGNI per constitution Section IV. However, it explicitly states "not required for initial delivery" and only asks the routing structure to "accommodate it without rework" — which it naturally does via severity-label matching. The requirement is appropriately scoped and does not mandate any extra code. Acceptable as-is.

### Verdict
ACCEPT — after applying the alert count and Grafana URL corrections above. The specification is complete, testable, and aligned with the constitution. All quality gate criteria are met.
