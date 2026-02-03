# Alert Testing Procedure

**Feature**: 017-synology-metrics
**Purpose**: Manually test Prometheus alert rules and Alertmanager email delivery
**Requirement**: FR-031 (Alert testing procedure)

## When to Use This Runbook

- After initial deployment (verify alerts work)
- After SMTP configuration changes
- After alert rule modifications
- Quarterly alert drill (ensure email routing functional)

## Prerequisites

- [ ] Monitoring stack deployed and running
- [ ] SMTP credentials configured in vault.yml
- [ ] Alert rules loaded in Prometheus (verify at http://192.168.1.214:9090/alerts)
- [ ] Alertmanager SMTP config active (verify at http://192.168.1.214:9093/#/status)

## Alert Rules Overview

Feature 017 includes 3 alert rules:

| Alert Name | Condition | Threshold | Purpose |
|------------|-----------|-----------|---------|
| `SynologyVolumeHighUsage` | Volume capacity | >85% for 5 minutes | Warn before storage full |
| `SynologyNASDown` | SNMP scrape fails | Down for 2 minutes | Detect NAS unreachable |
| `SynologyDiskSMARTWarning` | Disk health status | Non-normal for 5 minutes | Detect disk failure (best-effort) |

## Testing Method 1: Manual Alert Trigger (Recommended)

### Test `SynologyVolumeHighUsage` Alert

**Requirement**: Write test data to NAS volume to exceed 85% capacity

#### Step 1: Check Current Volume Usage

SSH to monitoring LXC:

```bash
ssh root@192.168.1.214

# Query current volume usage
curl -s "http://localhost:9090/api/v1/query?query=100%20*%20(1%20-%20(hrStorageAvailable%20/%20hrStorageSize))" | jq '.data.result[] | {volume: .metric.hrStorageDescr, usage: .value[1]}'
```

#### Step 2: Add Test Data to NAS

SSH to NAS or use DSM File Station:

```bash
# Example: Add large test file to a volume
ssh admin@192.168.1.109
dd if=/dev/zero of=/volume1/test-alert-data.bin bs=1M count=50000  # 50GB file
```

**Note**: Ensure you have enough free space and won't actually fill the volume to 100%.

#### Step 3: Wait for Alert to Fire

Alerts have a 5-minute threshold. Monitor Prometheus alerts page:

```bash
# Open in browser
open http://192.168.1.214:9090/alerts

# Or poll via API
watch -n 10 'curl -s "http://192.168.1.214:9090/api/v1/alerts" | jq ".data.alerts[] | select(.labels.alertname == \"SynologyVolumeHighUsage\")"'
```

#### Step 4: Verify Email Received

Check your email inbox (address in `alert_email_recipient` vault variable):

**Expected Email:**
- **Subject**: `[Homelab Alert] SynologyVolumeHighUsage`
- **Body**: Volume name and usage percentage (e.g., "volume1 is at 87% capacity")
- **Delivery Time**: Within 2 minutes of alert firing

#### Step 5: Cleanup Test Data

```bash
ssh admin@192.168.1.109
rm /volume1/test-alert-data.bin
```

Alert should auto-resolve within 5 minutes after usage drops below 85%.

---

### Test `SynologyNASDown` Alert

**Requirement**: Temporarily block SNMP traffic to simulate NAS unreachable

#### Step 1: Block SNMP Traffic

**Option A: Synology Firewall (Recommended)**

1. Log into DSM
2. Navigate to: **Control Panel** → **Security** → **Firewall**
3. Temporarily block port 161 from monitoring LXC (192.168.1.214)

**Option B: Proxmox Firewall (Alternative)**

```bash
# SSH to Proxmox host
ssh root@192.168.1.112

# Block SNMP traffic from monitoring LXC to NAS
iptables -I FORWARD -s 192.168.1.214 -d 192.168.1.109 -p udp --dport 161 -j DROP
```

#### Step 2: Wait for Alert to Fire

Alert threshold is 2 minutes. Monitor:

```bash
# Watch Prometheus targets
open http://192.168.1.214:9090/targets

# Watch for alert firing
watch -n 10 'curl -s "http://192.168.1.214:9090/api/v1/alerts" | jq ".data.alerts[] | select(.labels.alertname == \"SynologyNASDown\")"'
```

#### Step 3: Verify Email Received

**Expected Email:**
- **Subject**: `[Homelab Alert] SynologyNASDown`
- **Body**: "SNMP scrape target 192.168.1.109 has been down for more than 2 minutes"
- **Delivery Time**: Within 2 minutes of alert firing

#### Step 4: Restore SNMP Access

**Option A: Remove Synology Firewall Rule**

1. DSM → Control Panel → Security → Firewall
2. Remove or disable the block rule

**Option B: Remove Proxmox iptables Rule**

```bash
# Remove the DROP rule
iptables -D FORWARD -s 192.168.1.214 -d 192.168.1.109 -p udp --dport 161 -j DROP
```

Alert should auto-resolve within 2 minutes after SNMP scrape succeeds.

---

### Test `SynologyDiskSMARTWarning` Alert

**Note**: This alert is **best-effort** per FR-008. If your Synology model does not expose SMART OIDs via SNMP, this alert will never fire (expected behavior).

#### Step 1: Verify SMART OIDs Available

```bash
ssh root@192.168.1.214

# Check if Synology exposes disk status OIDs
curl -s "http://localhost:9090/api/v1/query?query=diskStatus" | jq '.data.result'
```

If result is empty, your NAS model does not expose SMART metrics. Skip this test.

#### Step 2: Simulate Disk Failure (Not Recommended)

**Warning**: There is no safe way to simulate a real disk SMART failure without potentially damaging hardware or data.

**Alternative**: Validate alert rule syntax without triggering:

```bash
# Check alert rule is loaded
curl -s "http://192.168.1.214:9090/api/v1/rules" | jq '.data.groups[].rules[] | select(.name == "SynologyDiskSMARTWarning")'
```

#### Step 3: Manual Email Test (If SMART Unavailable)

If SMART OIDs are not available, skip this alert test. Core monitoring (volume, CPU, RAM, network) will still function.

---

## Testing Method 2: Using `amtool` (Advanced)

Alertmanager includes a CLI tool for sending test alerts without triggering real conditions.

### Install `amtool`

```bash
# On macOS
brew install alertmanager

# On Debian/Ubuntu
apt-get install prometheus-alertmanager
```

### Send Test Alert

```bash
# Define test alert
amtool alert add \
    --alertmanager.url=http://192.168.1.214:9093 \
    --annotation=summary="Test alert from amtool" \
    --annotation=description="This is a manual test alert to verify email delivery" \
    alertname="TestAlert" \
    severity="warning"

# Check alert fired
amtool --alertmanager.url=http://192.168.1.214:9093 alert query

# Expected email within 30 seconds (no group wait for manual alerts)
```

### Clear Test Alert

```bash
# Alerts auto-expire after 5 minutes, or clear manually:
amtool silence add \
    --alertmanager.url=http://192.168.1.214:9093 \
    --duration=1h \
    alertname="TestAlert"
```

---

## Testing Method 3: Prometheus PromQL Injection (Expert)

Temporarily modify Prometheus rules to force alerts to fire.

### Step 1: Edit Alert Rule

SSH to monitoring LXC:

```bash
ssh root@192.168.1.214
cd /opt/monitoring/prometheus

# Backup original rule
cp alerts.yml alerts.yml.bak

# Edit rule to always fire (for testing)
sed -i 's/> 85/> 0/g' alerts.yml  # Fire immediately for any volume usage

# Reload Prometheus config
docker exec prometheus kill -HUP 1
```

### Step 2: Verify Alert Fires

```bash
# Should fire within 30 seconds
curl -s "http://localhost:9090/api/v1/alerts" | jq
```

### Step 3: Restore Original Rule

```bash
mv alerts.yml.bak alerts.yml
docker exec prometheus kill -HUP 1
```

---

## Validation Checklist

After testing alerts:

- [ ] Alert appears in Prometheus UI (/alerts page shows "FIRING")
- [ ] Alert visible in Alertmanager UI (http://192.168.1.214:9093/#/alerts)
- [ ] Email received at configured recipient address
- [ ] Email subject line matches expected format
- [ ] Email body contains alert annotations (summary, description)
- [ ] Alert auto-resolves after condition clears
- [ ] Resolved email received (optional, depending on Alertmanager config)

## Troubleshooting

### Alert Fires But No Email Sent

**Check Alertmanager SMTP config:**

```bash
curl -s "http://192.168.1.214:9093/api/v2/status" | jq '.config.global'

# Verify SMTP settings:
# - smtp_smarthost: correct server:port
# - smtp_from: valid sender address
# - smtp_auth_username: correct username
# - smtp_require_tls: true
```

**Check Alertmanager logs:**

```bash
docker logs alertmanager --tail 50

# Look for SMTP errors:
# - "Authentication failed"
# - "Connection refused"
# - "TLS handshake failed"
```

**Common SMTP Issues:**

- Gmail: Requires App Password (not account password)
- Office 365: May require OAuth2 (not supported by Alertmanager - use SMTP relay)
- Self-hosted: Verify firewall allows outbound port 587/465

### Alert Never Fires (Stays in "Pending")

**Check alert evaluation interval:**

```bash
# Prometheus evaluates rules every 30s (default)
curl -s "http://192.168.1.214:9090/api/v1/status/config" | jq '.data.yaml' | grep evaluation_interval
```

**Check alert rule syntax:**

```bash
# Validate PromQL query manually
curl -s "http://192.168.1.214:9090/api/v1/query?query=YOUR_ALERT_EXPRESSION" | jq
```

**Check "for" duration:**

```yaml
# Alert must be true for 5 minutes before firing
for: 5m

# For testing, reduce to 30s:
for: 30s
```

### Email Delivery Delayed

**Check Alertmanager grouping:**

```yaml
# Alertmanager waits 30s to group similar alerts
group_wait: 30s

# For immediate delivery during testing, set to 0s:
group_wait: 0s
```

## See Also

- [Prometheus Alert Rules](../../../ansible/roles/monitoring_stack/files/prometheus/alerts.yml)
- [Alertmanager Configuration](../../../ansible/roles/monitoring_stack/templates/alertmanager.yml.j2)
- [Smoke Test Script](../../../scripts/monitoring/smoke-test.sh)
- [Official Alertmanager Documentation](https://prometheus.io/docs/alerting/latest/alertmanager/)
