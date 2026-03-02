# Research: Pushover Alerting Integration

**Feature**: 043-alerting-pushover
**Date**: 2026-03-02

## Research Area 1: Alertmanager Native Pushover Support

**Question**: Does Alertmanager v0.30.0 natively support Pushover as a receiver type?

**Decision**: Yes — confirmed. Alertmanager has built-in `pushover_configs` support.

**Rationale**: The [official Alertmanager configuration reference](https://prometheus.io/docs/alerting/latest/configuration/#pushover_config) documents `<pushover_config>` as a first-class receiver integration. No plugins, sidecars, or webhook bridges are needed.

**Key fields** (from official docs):

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `send_resolved` | boolean | `true` | Send notification when alert resolves |
| `user_key` | secret | (required) | Pushover user key |
| `token` | secret | (required) | Pushover application API token |
| `title` | tmpl_string | pushover.default.title | Go template for notification title |
| `message` | tmpl_string | pushover.default.message | Go template for notification body |
| `url` | tmpl_string | pushover.default.url | Supplementary URL shown alongside message |
| `priority` | tmpl_string | `{{ if eq .Status "firing" }}2{{ else }}0{{ end }}` | Pushover priority level |
| `retry` | duration | `1m` | Retry interval for emergency priority (min 30s) |
| `expire` | duration | `1h` | Expiry for emergency priority retries |
| `html` | boolean | `false` | Enable HTML formatting in message |

**Alternatives considered**:
- Webhook bridge to Pushover API: Rejected — unnecessary complexity when native support exists.
- ntfy/Gotify self-hosted: Out of scope per spec (only Pushover is supported).

## Research Area 2: Pushover Priority Levels

**Question**: How do Pushover priority levels map to the spec's severity-based routing?

**Decision**: `critical` → priority 2 (emergency), `warning` → priority 0 (normal).

**Rationale**: The [Pushover API priority documentation](https://pushover.net/api#priority) defines:

| Priority | Name | Behavior |
|----------|------|----------|
| -2 | Lowest | No notification, no sound |
| -1 | Low | No sound or vibration |
| 0 | Normal | Standard notification, respects quiet hours |
| 1 | High | Bypasses quiet hours, red text |
| 2 | Emergency | Bypasses quiet hours, repeats until acknowledged |

Emergency priority (2) requires `retry` (min 30s) and `expire` parameters. Other priorities ignore these fields.

The spec's requirements map directly:
- FR-003: Emergency repeats every 60s → `retry: 1m`, `expire: 1h`
- FR-004: Normal respects quiet hours → `priority: 0` (built-in Pushover behavior)
- FR-016: Future info level → `priority: -1` (low, no sound/vibration)

**Alternatives considered**:
- Priority 1 (high) for critical: Rejected — doesn't require acknowledgment, violates FR-003.
- Priority 1 (high) for warning: Rejected — bypasses quiet hours, violates FR-004.

## Research Area 3: Alertmanager Routing for Dual-Channel Delivery

**Question**: How to ensure all alerts reach both Pushover AND email receivers?

**Decision**: Use child routes with `continue: true` and a catch-all email route as the last child.

**Rationale**: Alertmanager's routing tree evaluates child routes sequentially. When `continue: true` is set on a matching child, the alert proceeds to evaluate the next sibling. A catch-all child route (no matchers) at the end ensures every alert — regardless of whether it matched a Pushover route — reaches the email receiver.

**Route structure**:
```yaml
route:
  receiver: 'email-default'          # Fallback for alerts matching NO children
  group_by: ['alertname', 'severity']
  routes:                             # Only present when pushover_enabled=true
    - receiver: 'pushover-critical'
      matchers: [severity = "critical"]
      continue: true                  # Continue to next sibling
    - receiver: 'pushover-warning'
      matchers: [severity = "warning"]
      continue: true                  # Continue to next sibling
    - receiver: 'email-default'       # Catch-all: no matchers = matches all
```

**Routing behavior per alert type**:

| Alert severity | pushover-critical | pushover-warning | email-default | Correct? |
|---------------|-------------------|------------------|---------------|----------|
| critical | ✅ match, continue | ❌ no match | ✅ catch-all | ✅ FR-007, FR-008 |
| warning | ❌ no match | ✅ match, continue | ✅ catch-all | ✅ FR-007, FR-008 |
| (none) | ❌ no match | ❌ no match | ✅ catch-all | ✅ FR-010 |

**Alternatives considered**:
- Alertmanager multi-receiver (fan-out): Not a native feature — would require custom tooling. Rejected.
- Duplicate receiver with both email + pushover configs: Would change email grouping behavior. Rejected per FR-009.
- Root receiver fallback only (no catch-all child): Incorrect — root receiver only fires when NO child matches. Alerts matched by Pushover routes (even with `continue: true`) would NOT reach the root receiver. Verified against [Alertmanager routing docs](https://prometheus.io/docs/alerting/latest/configuration/#route).

## Research Area 4: Jinja2 and Go Template Escaping

**Question**: How to embed Go template expressions in an Ansible Jinja2 template?

**Decision**: Use the established `{{"{{ ... }}"}}` double-escaping pattern already used in the existing `alertmanager.yml.j2`.

**Rationale**: The existing template already uses this pattern for the email receiver:
```yaml
Subject: '[Homelab Alert] {{"{{ .GroupLabels.alertname }}"}}'
```

Jinja2 evaluates `{{"{{ .GroupLabels.alertname }}"}}` as a string expression, outputting `{{ .GroupLabels.alertname }}` literally. Alertmanager then processes this as a Go template.

For Go template conditionals that contain string literals (double quotes), the pattern extends to:
```yaml
{{"{{ if eq .Status \"firing\" }}"}}[CRITICAL]{{"{{ else }}"}}[RESOLVED]{{"{{ end }}"}}
```

Each Go template expression is wrapped in its own `{{"..."}}` Jinja2 block. The `\"` inside the Jinja2 string produces a literal `"` in the output (standard Python string escaping).

**Verified output chain**:
1. YAML parser → literal string
2. Jinja2 renders `{{"..."}}` → Go template expressions
3. Alertmanager Go template engine → final notification text

## Research Area 5: Credential Validation Pattern

**Question**: How should the playbook validate Pushover credentials when the feature is enabled?

**Decision**: Use `ansible.builtin.assert` in the role's `tasks/main.yml` before `compose_stack.yml`, gated by `pushover_enabled`.

**Rationale**: The assert module provides:
- Clear, structured error messages identifying missing variables
- Conditional execution via `when:` clause
- `no_log: true` to prevent credential values from appearing in output
- Immediate playbook failure (fail-fast) before deploying broken config

**Pattern**:
```yaml
- name: Validate Pushover credentials when enabled
  ansible.builtin.assert:
    that:
      - pushover_user_key is defined
      - pushover_user_key | length > 0
      - pushover_api_token is defined
      - pushover_api_token | length > 0
    fail_msg: >-
      Pushover is enabled (pushover_enabled=true) but credentials are missing.
      Add 'pushover_user_key' and 'pushover_api_token' to
      ansible/group_vars/monitoring/vault.yml.
  when: pushover_enabled | default(false) | bool
  no_log: true
```

**Alternatives considered**:
- Separate validation task file: YAGNI — a single assert task doesn't warrant a new file.
- Jinja2 conditional in template that raises error: Would fail at template render time, not at task level. Less clear error message. Rejected.
- Pre-task in playbook: Would duplicate logic between playbook and role. Rejected — role should self-validate.

## Research Area 6: Feature Flag and Default Values

**Question**: What variables need to be added and where?

**Decision**: Add feature flag and tuning parameters to role `defaults/main.yml`. Credentials are vault-only.

**Variable registry**:

| Variable | Location | Default | Source |
|----------|----------|---------|--------|
| `pushover_enabled` | defaults/main.yml | `false` | FR-011, FR-014 |
| `pushover_retry_interval` | defaults/main.yml | `"1m"` | FR-003, FR-014 |
| `pushover_expire_duration` | defaults/main.yml | `"1h"` | FR-003, FR-014 |
| `pushover_user_key` | vault.yml (operator-managed) | (none) | FR-013 |
| `pushover_api_token` | vault.yml (operator-managed) | (none) | FR-013 |

**Rationale**: FR-014 requires tuning parameters as role defaults with override capability. The feature flag defaults to `false` (FR-011). Credentials are vault-only (FR-013, Constitution II). The retry and expire values match Alertmanager defaults but are made explicit per FR-014.

**Alternatives considered**:
- Defining defaults in group_vars/monitoring/vars.yml: Would bypass the Ansible variable precedence chain. Role defaults allow overriding at any level. Rejected.
- Single receiver with dynamic priority: Would require complex Go template logic for priority selection. Two receivers (one per severity) is simpler and more explicit. Rejected per Constitution IV.
