# Data Model: Pushover Alerting Integration

**Feature**: 043-alerting-pushover
**Date**: 2026-03-02

## Overview

This feature introduces no new persistent data entities. It extends the existing Alertmanager configuration with additional receivers and routes. The "data model" here describes the configuration entities and their relationships.

## Configuration Entities

### 1. Feature Flag

| Field | Type | Location | Default |
|-------|------|----------|---------|
| `pushover_enabled` | boolean | `ansible/roles/monitoring_stack/defaults/main.yml` | `false` |

**Behavior**: When `false`, the Alertmanager configuration is identical to the pre-feature state (no Pushover receivers or routes). When `true`, Pushover receivers and severity-based routes are injected into the generated `alertmanager.yml`.

### 2. Pushover Tuning Parameters

| Field | Type | Location | Default | Constraint |
|-------|------|----------|---------|------------|
| `pushover_retry_interval` | Alertmanager duration | `defaults/main.yml` | `"1m"` | Min 30s (Pushover API) |
| `pushover_expire_duration` | Alertmanager duration | `defaults/main.yml` | `"1h"` | Max 10800s/3h (Pushover API) |

**Behavior**: These values are only used when `pushover_enabled=true` and only apply to the `pushover-critical` receiver (emergency priority). The `pushover-warning` receiver (normal priority) ignores retry/expire.

### 3. Pushover Credentials (Vault)

| Field | Type | Location | Required When |
|-------|------|----------|---------------|
| `pushover_user_key` | secret string | `ansible/group_vars/monitoring/vault.yml` | `pushover_enabled=true` |
| `pushover_api_token` | secret string | `ansible/group_vars/monitoring/vault.yml` | `pushover_enabled=true` |

**Validation**: Asserted non-empty when `pushover_enabled=true`. Playbook fails with descriptive error if missing.

### 4. Alertmanager Receivers (Generated)

#### pushover-critical

| Config Field | Value | Source |
|-------------|-------|--------|
| `user_key` | `{{ pushover_user_key }}` | Vault |
| `token` | `{{ pushover_api_token }}` | Vault |
| `send_resolved` | `true` | FR-006 |
| `priority` | `2` (firing) / `0` (resolved) | FR-015, Go template |
| `retry` | `{{ pushover_retry_interval }}` | FR-003 |
| `expire` | `{{ pushover_expire_duration }}` | FR-003 |
| `title` | `[CRITICAL] alertname` / `[RESOLVED] alertname` | FR-005, Go template |
| `message` | Alert summaries | FR-005, Go template |
| `url` | `{{ grafana_protocol }}://{{ grafana_domain }}` | DL-05 |

**Exists when**: `pushover_enabled=true`

#### pushover-warning

| Config Field | Value | Source |
|-------------|-------|--------|
| `user_key` | `{{ pushover_user_key }}` | Vault |
| `token` | `{{ pushover_api_token }}` | Vault |
| `send_resolved` | `true` | FR-006 |
| `priority` | `0` (always normal) | FR-015 |
| `title` | `[WARNING] alertname` / `[RESOLVED] alertname` | FR-005, Go template |
| `message` | Alert summaries | FR-005, Go template |
| `url` | `{{ grafana_protocol }}://{{ grafana_domain }}` | DL-05 |

**Exists when**: `pushover_enabled=true`

### 5. Alertmanager Routes (Generated)

When `pushover_enabled=true`, child routes are added under the root route:

```
root (receiver: email-default, group_by: [alertname, severity])
├── child 1: pushover-critical (match: severity="critical", continue: true)
├── child 2: pushover-warning  (match: severity="warning",  continue: true)
└── child 3: email-default     (catch-all, no matchers)
```

When `pushover_enabled=false`, the root route has no children (identical to pre-feature state).

## Alert Severity Inventory

All 18 existing alert rules and their routing:

### Critical (7) → pushover-critical receiver

| Alert | Source File | Component |
|-------|------------|-----------|
| ServiceDown | infrastructure_alerts.yml | availability |
| DiskSpaceCritical | infrastructure_alerts.yml | infrastructure |
| SynologyNASDown | synology_alerts.yml | availability |
| EndpointDown | security_alerts.yml | availability |
| TLSCertExpiryCritical | security_alerts.yml | security |
| Fail2banDown | security_alerts.yml | availability |
| NextcloudDown | service_alerts.yml.j2 (nextcloud contract) | — |

### Warning (11) → pushover-warning receiver

| Alert | Source File | Component |
|-------|------------|-----------|
| HighCPUUsage | infrastructure_alerts.yml | infrastructure |
| HighMemoryUsage | infrastructure_alerts.yml | infrastructure |
| DiskSpaceWarning | infrastructure_alerts.yml | infrastructure |
| SynologyVolumeHighUsage | synology_alerts.yml | storage |
| SynologyDiskSMARTWarning | synology_alerts.yml | disk_health |
| TLSCertExpiringSoon | security_alerts.yml | security |
| HighProbeLatency | security_alerts.yml | performance |
| Fail2banHighBanRate | security_alerts.yml | security |
| CaddyHighErrorRate | service_alerts.yml.j2 (reverse_proxy contract) | — |
| AdGuardHighBlockedRate | service_alerts.yml.j2 (adguard contract) | — |
| ImmichJobBacklogHigh | service_alerts.yml.j2 (immich contract) | — |

## Relationship Diagram

```
pushover_enabled ──(gates)──> Jinja2 conditionals in alertmanager.yml.j2
                                    │
                                    ├── Pushover routes (child routes with continue:true)
                                    ├── Pushover receivers (pushover-critical, pushover-warning)
                                    └── Email catch-all route (ensures FR-007)

pushover_user_key ──(vault)──> pushover-critical.user_key
                          └──> pushover-warning.user_key

pushover_api_token ──(vault)──> pushover-critical.token
                           └──> pushover-warning.token

Existing alert rules ──(severity label)──> Route matching
    severity=critical ──> pushover-critical ──(continue)──> email-default
    severity=warning  ──> pushover-warning  ──(continue)──> email-default
    (no severity)     ──> (no match)        ──────────────> email-default
```

## State Transitions

This feature has no state machines. Alert lifecycle is managed by Alertmanager and Prometheus:

```
Alert Rule Fires → Alertmanager Groups → Route Match → Receiver Dispatch
                                                           ├── Pushover API POST
                                                           └── SMTP Email

Alert Condition Clears → Alertmanager sends resolved notification
                              ├── Pushover (send_resolved: true)
                              └── Email (send_resolved: true)
```
