# Synology SNMP Setup Guide

**Feature**: 017-synology-metrics  
**Purpose**: Enable SNMPv3 monitoring on Synology NAS for Prometheus collection  
**Requirement**: FR-020 (Manual prerequisite documentation)

## Prerequisites

- Synology DSM 7.x (recommended) or 6.x
- Administrator access to Synology DSM
- Monitoring LXC IP: 192.168.1.214

## DSM Version Compatibility

**Tested Versions:**
- ✅ DSM 7.x: Full SNMPv3 support with authPriv confirmed
- ⚠️ DSM 6.x: Not tested, SNMPv3 availability unknown

**Note**: This guide assumes DSM 7.x. For DSM 6.x, verify SNMPv3 support in your specific version before proceeding.

## Step-by-Step Configuration

### 1. Enable SNMP Service

1. Log in to Synology DSM as administrator
2. Navigate to: **Control Panel** → **Terminal & SNMP**
3. Click the **SNMP** tab
4. Check **Enable SNMP service**

### 2. Configure SNMPv3 Authentication

**Security Warning**: Do NOT use SNMPv1 or SNMPv2c - these protocols transmit community strings in plaintext. Always use SNMPv3 with authPriv for encrypted authentication and privacy.

1. Under **SNMPv3**, click **Settings**
2. Click **Create** to add a new user
3. Configure the following:

   **Username**: `monitoring`  
   **Authentication Protocol**: `MD5`  
   **Authentication Password**: `[Use password from ansible vault.yml: snmp_auth_password]`  
   **Privacy Protocol**: `AES`  
   **Privacy Password**: `[Use password from ansible vault.yml: snmp_priv_password]`

4. Click **OK** to save

### 3. Optional: Restrict SNMP Access (Recommended for Production)

**Requirement**: FR-029 (SHOULD - optional but recommended)

1. Under **SNMP**, locate **Allowed IP addresses**
2. Check **Enable IP address whitelisting**
3. Add monitoring LXC IP: `192.168.1.214`
4. Click **OK**

This restricts SNMP queries to only the monitoring LXC, improving security.

### 4. Verify SNMP Configuration

From the monitoring LXC (after deployment), test SNMP connectivity:

```bash
# Install snmpwalk tool (if not already installed)
apt-get install snmp snmp-mibs-downloader

# Test SNMPv3 connectivity
snmpwalk -v3 -l authPriv -u monitoring -a MD5 -A "YOUR_AUTH_PASSWORD" -x AES -X "YOUR_PRIV_PASSWORD" 192.168.1.109 1.3.6.1.2.1.1.5
```

**Expected Output**: System name (sysName) OID value should return your NAS hostname.

### 5. Verify Available Metrics

**Requirement**: T006b (Validate OID availability)

Test which metrics are exposed by your specific Synology model:

```bash
# Storage metrics (volumes)
snmpwalk -v3 -l authPriv -u monitoring -a MD5 -A "YOUR_AUTH_PASSWORD" -x AES -X "YOUR_PRIV_PASSWORD" 192.168.1.109 1.3.6.1.2.1.25.2.3.1

# CPU metrics
snmpwalk -v3 -l authPriv -u monitoring -a MD5 -A "YOUR_AUTH_PASSWORD" -x AES -X "YOUR_PRIV_PASSWORD" 192.168.1.109 1.3.6.1.4.1.2021.11

# Disk health (Synology-specific - may vary by model)
snmpwalk -v3 -l authPriv -u monitoring -a MD5 -A "YOUR_AUTH_PASSWORD" -x AES -X "YOUR_PRIV_PASSWORD" 192.168.1.109 1.3.6.1.4.1.6574.2.1.1
```

**Note**: SMART disk metrics (OID 1.3.6.1.4.1.6574.2.1.1) are **best-effort** per FR-008. Not all Synology models expose these OIDs. If unavailable, disk health alerts will not function, but core monitoring (storage, CPU, RAM, network) will still work.

## Troubleshooting

### SNMP Service Not Starting

- Verify DSM version supports SNMPv3 (DSM 7.x recommended)
- Check system logs: **Control Panel** → **Log Center** → **System**

### No Metrics Returned

- Verify firewall rules allow UDP port 161 from monitoring LXC
- Confirm SNMPv3 credentials match ansible vault.yml exactly
- Test with simpler OIDs first (e.g., 1.3.6.1.2.1.1.1 for sysDescr)

### Disk Health Metrics Missing

- This is **expected** for some Synology models (per FR-008 best-effort)
- Core monitoring (storage, CPU, RAM, network) will still function
- Alert rule `SynologyDiskSMARTWarning` will not trigger if OIDs unavailable

## Ansible Vault Configuration

After configuring SNMPv3 on the NAS, update the Ansible vault with the same credentials:

```bash
ansible-vault edit ansible/group_vars/monitoring/vault.yml
```

Ensure the following variables match your SNMPv3 configuration:

```yaml
snmp_username: "monitoring"
snmp_auth_password: "YOUR_AUTH_PASSWORD"
snmp_priv_password: "YOUR_PRIV_PASSWORD"
snmp_auth_protocol: "MD5"
snmp_priv_protocol: "AES"
snmp_security_level: "authPriv"
```

## Next Steps

1. ✅ SNMPv3 enabled and tested on Synology
2. → Configure SMTP credentials in vault.yml (for alerting)
3. → Run Terraform to provision monitoring LXC
4. → Run Ansible to deploy monitoring stack
5. → Verify metrics in Grafana

## References

- [Synology SNMPv3 Documentation](https://kb.synology.com/en-us/DSM/help/DSM/AdminCenter/system_snmp)
- [Prometheus SNMP Exporter](https://github.com/prometheus/snmp_exporter)
- [Feature Spec: 017-synology-metrics](../../../specs/017-synology-metrics/spec.md)
