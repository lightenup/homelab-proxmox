# Monitoring Stack Upgrade Procedure

**Feature**: 017-synology-metrics  
**Purpose**: Safely upgrade Prometheus, Grafana, SNMP Exporter, or Alertmanager versions  
**Requirement**: FR-028 (Version upgrade procedure)

## When to Use This Runbook

- Prometheus security patch available
- Grafana feature update desired
- SNMP Exporter bug fix released
- Routine quarterly version updates

## Upgrade Strategy

**Philosophy**: Non-production testing first, then production rollout with backup safety net.

1. **Backup First**: Always backup before upgrading
2. **Version Pinning**: Update `defaults/main.yml`, not docker-compose.yml directly
3. **Idempotent Ansible**: Re-run playbook to apply upgrades
4. **Verify Before Proceed**: Check logs and health endpoints after each service upgrade

## Prerequisites

- [ ] Recent backup exists (verify in `{{ backup_path }}/`)
- [ ] Read upstream release notes for breaking changes
- [ ] Ansible vault password available
- [ ] SSH access to monitoring LXC (192.168.1.214)

## Upgrade Procedure

### 1. Create Pre-Upgrade Backup

```bash
# SSH to monitoring LXC
ssh root@192.168.1.214

# Manually trigger backup (don't wait for 3 AM cron)
/usr/local/sbin/backup-monitoring.sh

# Verify backup succeeded
ls -lh /mnt/nas/backups/monitoring/ | tail -3
```

### 2. Update Version Pins

On Ansible control machine (laptop/workstation):

```bash
cd /path/to/homelab-proxmox

# Edit role defaults
vim ansible/roles/monitoring_stack/defaults/main.yml

# Update desired version pins:
# prometheus_version: "v2.48.0" → "v2.50.0"
# grafana_version: "10.2.0" → "10.3.0"
# snmp_exporter_version: "v0.25.0" → "v0.26.0"
# alertmanager_version: "v0.26.0" → "v0.27.0"
```

**Important**: Check upstream release notes for each service:
- [Prometheus Releases](https://github.com/prometheus/prometheus/releases)
- [Grafana Releases](https://github.com/grafana/grafana/releases)
- [SNMP Exporter Releases](https://github.com/prometheus/snmp_exporter/releases)
- [Alertmanager Releases](https://github.com/prometheus/alertmanager/releases)

### 3. Test in Non-Production (Optional but Recommended)

If you have a test LXC:

```bash
ansible-playbook playbooks/monitoring.yml --limit monitoring-test --ask-vault-pass
```

Verify services start and metrics flow correctly before proceeding to production.

### 4. Apply Upgrade via Ansible

```bash
# Re-run monitoring playbook (idempotent - only changes version pins)
ansible-playbook playbooks/monitoring.yml --ask-vault-pass

# Monitor deployment
ssh root@192.168.1.214 'cd /opt/monitoring && docker-compose logs -f'
```

### 5. Verify Upgrade

```bash
# Check container versions
ssh root@192.168.1.214 'docker-compose ps'

# Verify Prometheus
curl http://192.168.1.214:9090/-/healthy
curl http://192.168.1.214:9090/api/v1/status/buildinfo | jq '.data.version'

# Verify Grafana
curl http://192.168.1.214:3000/api/health | jq
curl http://192.168.1.214:3000/api/health | jq '.version'

# Verify SNMP Exporter
curl http://192.168.1.214:9116/health

# Verify Alertmanager
curl http://192.168.1.214:9093/-/healthy
```

### 6. Verify Metrics and Alerts

```bash
# Check Prometheus targets
curl -s "http://192.168.1.214:9090/api/v1/targets" | jq '.data.activeTargets[] | {job: .labels.job, state: .health}'

# Expected: {"job": "synology-snmp", "state": "up"}

# Check alert rules loaded
curl -s "http://192.168.1.214:9090/api/v1/rules" | jq '.data.groups[].rules[].name'

# Expected: ["SynologyVolumeHighUsage", "SynologyNASDown", "SynologyDiskSMARTWarning"]

# Verify Grafana dashboard
echo "Open http://192.168.1.214:3000 and check Synology NAS dashboard renders correctly"
```

## Rollback Procedure (If Upgrade Fails)

### Option 1: Revert Version Pins (Preferred)

```bash
# Edit defaults/main.yml and restore previous versions
vim ansible/roles/monitoring_stack/defaults/main.yml

# Re-run Ansible to downgrade
ansible-playbook playbooks/monitoring.yml --ask-vault-pass
```

### Option 2: Restore from Backup (Nuclear Option)

If upgrade causes data corruption or service fails to start:

```bash
# Follow restore procedure
# See: runbook-restore.md
```

## Common Upgrade Scenarios

### Prometheus Major Version Upgrade (e.g., v2.x → v3.x)

**Risk**: High (potential TSDB format changes, breaking API changes)

1. Read migration guide thoroughly
2. Test in non-production FIRST
3. Expect possible downtime (TSDB conversion may take minutes)
4. Backup is critical (may not be reversible)

### Grafana Major Version Upgrade (e.g., 10.x → 11.x)

**Risk**: Medium (UI changes, plugin compatibility)

1. Check dashboard provisioning still works
2. Verify Prometheus datasource plugin compatible
3. Test dashboard JSON rendering

### SNMP Exporter Minor Version Upgrade (e.g., v0.25 → v0.26)

**Risk**: Low (usually backward compatible)

1. No special considerations
2. Config format rarely changes

### Alertmanager Minor Version Upgrade (e.g., v0.26 → v0.27)

**Risk**: Low (stable config format)

1. Verify SMTP routing still works post-upgrade
2. Test alert delivery

## Validation Checklist

Post-upgrade verification:

- [ ] All 4 containers running (`docker-compose ps`)
- [ ] Prometheus scraping Synology NAS (targets UP)
- [ ] Grafana dashboard loads with live metrics
- [ ] Alert rules loaded in Prometheus
- [ ] Alertmanager SMTP config active
- [ ] No error logs in `docker-compose logs`
- [ ] Backup cron job still active (`crontab -l | grep backup`)

## Troubleshooting

### Container Won't Start After Upgrade

```bash
# Check logs
docker-compose logs <service_name>

# Common issues:
# - Config format changed (check upstream migration guide)
# - Volume permissions issue (chown data directories)
# - Port conflicts (check if old container still running)
```

### Metrics Not Collecting After Upgrade

```bash
# Verify Prometheus scrape config
docker exec prometheus cat /etc/prometheus/prometheus.yml

# Test SNMP manually
docker exec snmp-exporter wget -qO- http://localhost:9116/health
```

### Grafana Dashboard Broken

```bash
# Re-provision dashboards
ansible-playbook playbooks/monitoring.yml --tags grafana --ask-vault-pass
```

## Maintenance Schedule

**Recommended**: Quarterly upgrades for patch releases, annual for major versions.

- **Quarterly** (Q1, Q2, Q3, Q4): Minor/patch version upgrades
- **Annually** (Q1): Review major version upgrades
- **As-Needed**: Critical security patches (apply within 7 days)

## See Also

- [Restore Procedure](runbook-restore.md)
- [Backup Script](../../../ansible/roles/monitoring_stack/templates/backup-monitoring.sh.j2)
- [Synology SNMP Setup](synology-snmp-setup.md)
