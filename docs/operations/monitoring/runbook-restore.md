# Monitoring Stack Restore Procedure

**Feature**: 017-synology-metrics
**Purpose**: Restore Prometheus TSDB and Grafana dashboards from backup
**Requirement**: FR-027 (Disaster recovery procedure)

## When to Use This Runbook

- Monitoring LXC destroyed or corrupted
- Prometheus TSDB data loss
- Grafana dashboards/datasources lost
- Testing disaster recovery (restore drill)

## Prerequisites

- Backup tarball exists in `{{ backup_path }}/monitoring_backup_YYYYMMDD_HHMMSS.tar.gz`
- Monitoring LXC provisioned via Terraform (192.168.1.214)
- Docker installed on monitoring LXC
- Ansible playbook has been run at least once (Docker volumes created)

## Restore Procedure

### 1. Stop Monitoring Stack

SSH to monitoring LXC:

```bash
ssh root@192.168.1.214
cd /opt/monitoring
docker-compose down
```

### 2. Extract Backup Tarball

```bash
# List available backups
ls -lh /mnt/nas/backups/monitoring/

# Choose most recent backup (or specific restore point)
BACKUP_FILE="/mnt/nas/backups/monitoring/monitoring_backup_20250128_030000.tar.gz"

# Extract to temporary directory
mkdir -p /tmp/restore
tar xzf "${BACKUP_FILE}" -C /tmp/restore

# Verify extracted files
ls -lh /tmp/restore/
# Expected: prometheus_data.tar.gz, grafana_data.tar.gz, alertmanager_data.tar.gz
```

### 3. Restore Prometheus TSDB

```bash
# Get Prometheus volume name
PROMETHEUS_VOLUME=$(docker volume ls --format '{{.Name}}' | grep prometheus_data)

# Restore Prometheus data
docker run --rm \
    -v ${PROMETHEUS_VOLUME}:/target \
    -v /tmp/restore:/backup:ro \
    debian:bookworm-slim \
    bash -c "rm -rf /target/* && tar xzf /backup/prometheus_data.tar.gz -C /target"

echo "Prometheus TSDB restored"
```

### 4. Restore Grafana Data

```bash
# Get Grafana volume name
GRAFANA_VOLUME=$(docker volume ls --format '{{.Name}}' | grep grafana_data)

# Restore Grafana data
docker run --rm \
    -v ${GRAFANA_VOLUME}:/target \
    -v /tmp/restore:/backup:ro \
    debian:bookworm-slim \
    bash -c "rm -rf /target/* && tar xzf /backup/grafana_data.tar.gz -C /target"

echo "Grafana dashboards/datasources restored"
```

### 5. Restore Alertmanager State

```bash
# Get Alertmanager volume name
ALERTMANAGER_VOLUME=$(docker volume ls --format '{{.Name}}' | grep alertmanager_data)

# Restore Alertmanager data
docker run --rm \
    -v ${ALERTMANAGER_VOLUME}:/target \
    -v /tmp/restore:/backup:ro \
    debian:bookworm-slim \
    bash -c "rm -rf /target/* && tar xzf /backup/alertmanager_data.tar.gz -C /target"

echo "Alertmanager state restored"
```

### 6. Start Monitoring Stack

```bash
cd /opt/monitoring
docker-compose up -d

# Verify all services started
docker-compose ps
```

### 7. Verify Restoration

```bash
# Check Prometheus has historical data
curl -s "http://localhost:9090/api/v1/query?query=up" | jq

# Check Grafana loads (may take 30s to start)
curl -s http://localhost:3000/api/health | jq

# Access Grafana UI
echo "Open http://192.168.1.214:3000 and verify Synology dashboard shows historical data"
```

### 8. Cleanup

```bash
rm -rf /tmp/restore
```

## Validation Checklist

- [ ] Prometheus UI loads at http://192.168.1.214:9090
- [ ] Prometheus targets show synology-snmp as UP
- [ ] Prometheus has historical metrics (check Graph tab)
- [ ] Grafana UI loads at http://192.168.1.214:3000
- [ ] Grafana Prometheus datasource configured (not manual import)
- [ ] Synology NAS dashboard exists (not manual import)
- [ ] Grafana shows historical data (not just current time)
- [ ] Alertmanager UI loads at http://192.168.1.214:9093

## Troubleshooting

### Grafana Shows No Data

- Check Prometheus datasource: Grafana → Configuration → Data Sources → Prometheus
- Verify URL is `http://prometheus:9090`
- Test connection should return green checkmark

### Prometheus Has No Historical Data

- Check TSDB path: `docker exec prometheus ls -lh /prometheus`
- Verify backup tarball was not empty: `tar tzf /backup/prometheus_data.tar.gz | head`

### Permission Errors on Volume Restore

- Add `--user root` to docker run commands
- Verify Docker socket is accessible: `ls -l /var/run/docker.sock`

## Notes

- Restore procedure requires downtime (services stopped during restore)
- Historical metrics older than 15 days are not retained (per FR-022)
- Grafana admin password from vault.yml is NOT in backup (stored in environment variable)
- SMTP credentials from vault.yml are NOT in backup (stored in config file on host)

## See Also

- [Backup Script](../../../ansible/roles/monitoring_stack/templates/backup-monitoring.sh.j2)
- [Upgrade Procedure](runbook-upgrades.md)
- [Synology SNMP Setup](synology-snmp-setup.md)
