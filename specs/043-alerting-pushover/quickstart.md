# Quickstart: Pushover Alerting Integration

**Feature**: 043-alerting-pushover
**Date**: 2026-03-02

## Prerequisites

1. Features 040, 041, 042 merged and deployed (monitoring stack operational)
2. Pushover account created at [pushover.net](https://pushover.net) ($5 one-time per platform)
3. Pushover mobile app installed on operator's phone
4. Pushover application created (or clone the [Prometheus app](https://pushover.net/apps/clone/prometheus))
5. User key and API token obtained from Pushover dashboard

## Enable Pushover Notifications

### Step 1: Add credentials to vault

Edit the monitoring vault file:

```bash
cd ansible
ansible-vault edit group_vars/monitoring/vault.yml
```

Add the Pushover credentials:

```yaml
# Pushover push notification credentials
pushover_user_key: "your-pushover-user-key-here"
pushover_api_token: "your-pushover-api-token-here"
```

### Step 2: Enable the feature flag

Edit `ansible/group_vars/monitoring/vars.yml` and set:

```yaml
pushover_enabled: true
```

Or override at deploy time:

```bash
ansible-playbook playbooks/monitoring.yml -e pushover_enabled=true --ask-vault-pass
```

### Step 3: Deploy

```bash
cd ansible
ansible-playbook playbooks/monitoring.yml --ask-vault-pass
```

### Step 4: Verify

Run the smoke test:

```bash
./scripts/monitoring/smoke-test.sh
```

Check Alertmanager status shows the new receivers:

```bash
curl -s http://192.168.1.214:9093/api/v2/status | jq '.config.original'
```

Verify Pushover receivers are present in the output.

## Disable Pushover Notifications

Set `pushover_enabled: false` in `ansible/group_vars/monitoring/vars.yml` (or remove the line — defaults to false), then re-run the playbook:

```bash
ansible-playbook playbooks/monitoring.yml --ask-vault-pass
```

The Alertmanager configuration reverts to email-only. No Pushover receivers or routes are generated.

## Test Alert Delivery

### Trigger a test alert via Alertmanager API

```bash
# Fire a test critical alert
curl -X POST http://192.168.1.214:9093/api/v2/alerts \
  -H "Content-Type: application/json" \
  -d '[{
    "labels": {
      "alertname": "TestCriticalAlert",
      "severity": "critical",
      "instance": "test"
    },
    "annotations": {
      "summary": "Test critical alert — please acknowledge on phone",
      "description": "This is a test alert to verify Pushover delivery."
    }
  }]'
```

Expected: Push notification arrives within 2 minutes with `[CRITICAL] TestCriticalAlert` title. Repeats every 60 seconds until acknowledged in Pushover app.

```bash
# Fire a test warning alert
curl -X POST http://192.168.1.214:9093/api/v2/alerts \
  -H "Content-Type: application/json" \
  -d '[{
    "labels": {
      "alertname": "TestWarningAlert",
      "severity": "warning",
      "instance": "test"
    },
    "annotations": {
      "summary": "Test warning alert — should arrive at normal priority",
      "description": "This is a test alert to verify Pushover warning delivery."
    }
  }]'
```

Expected: Push notification arrives at normal priority with `[WARNING] TestWarningAlert` title. Does not repeat.

### Resolve the test alert

```bash
# Send a resolved notification for the test critical alert
curl -X POST http://192.168.1.214:9093/api/v2/alerts \
  -H "Content-Type: application/json" \
  -d '[{
    "labels": {
      "alertname": "TestCriticalAlert",
      "severity": "critical",
      "instance": "test"
    },
    "annotations": {
      "summary": "Test critical alert resolved",
      "description": "This is a test resolution notification."
    },
    "endsAt": "2026-01-01T00:00:00Z"
  }]'
```

Expected: Push notification arrives with `[RESOLVED] TestCriticalAlert` title at normal priority.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Playbook fails with "credentials are missing" | `pushover_user_key` or `pushover_api_token` not in vault | Add credentials to `ansible/group_vars/monitoring/vault.yml` |
| No push notifications but email works | `pushover_enabled` not set to `true` | Set `pushover_enabled: true` in vars.yml |
| Alertmanager container fails to start | Invalid `alertmanager.yml` syntax | Check `docker logs alertmanager` on monitoring LXC |
| Push notification not received | Pushover API unreachable from monitoring LXC | Verify outbound HTTPS from 192.168.1.214 to `api.pushover.net` |
| Emergency notification doesn't repeat | Retry/expire misconfigured | Check `pushover_retry_interval` (min 30s) and `pushover_expire_duration` |
