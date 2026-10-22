# Monitoring Stack Upgrade Procedure

**Feature**: 017-synology-metrics
**Purpose**: Safely upgrade Prometheus, Grafana, Alertmanager, Telegraf, blackbox_exporter or node_exporter
**Requirement**: FR-028 (Version upgrade procedure)

## When to Use This Runbook

- Prometheus security patch available
- Grafana feature update desired
- Telegraf or blackbox_exporter bug fix released
- The weekly version-currency check (ntfy topic `versions`) reports a pin behind
- Routine quarterly version updates

## Upgrade Strategy

**Philosophy**: Non-production testing first, then production rollout with backup safety net.

1. **Backup First**: Always backup before upgrading
2. **Version Pinning**: Update the pins in `group_vars` (step 2), never role defaults or docker-compose.yml
3. **Idempotent Ansible**: Re-run playbook to apply upgrades
4. **Verify Before Proceed**: Check logs and health endpoints after each service upgrade

## Prerequisites

- [ ] Recent backup exists (verify in `{{ backup_path }}/`)
- [ ] Read upstream release notes for breaking changes
- [ ] Ansible vault password available
- [ ] SSH access to monitoring LXC (192.168.1.214)

## Upgrade Procedure

### 1. Create Pre-Upgrade Backup

The rollback point is a Proxmox LXC snapshot, taken as root on `pve`:

```bash
# Find the monitoring LXC VMID
pct list

# Take the snapshot
pct snapshot <vmid> pre-<change> --description "<change>: before upgrade"
pct listsnapshot <vmid>
```

The in-guest `backup-monitoring.sh` is not relied on for the rollback point: the monitoring
backup was broken until spec 091. The snapshot covers the LXC root disk, including the Docker
volumes `prometheus_data`, `grafana_data` and `alertmanager_data`.

### 2. Update Version Pins

Each version is set in exactly one place (spec 090; a guard test enforces it):

| Component | File |
|---|---|
| Prometheus, Grafana, Telegraf, Alertmanager, blackbox_exporter | `ansible/group_vars/monitoring/vars.yml` (the `# Service versions` block at the top) |
| node_exporter (every LXC) | `ansible/group_vars/all/vars.yml` |

**Never** edit role defaults: they no longer hold versions, and the playbook's `include_vars`
of the group_vars file would override them anyway.

Check upstream release notes for each component:
- [Prometheus Releases](https://github.com/prometheus/prometheus/releases)
- [Grafana Releases](https://github.com/grafana/grafana/releases)
- [Alertmanager Releases](https://github.com/prometheus/alertmanager/releases)
- [Telegraf Releases](https://github.com/influxdata/telegraf/releases)
- [blackbox_exporter Releases](https://github.com/prometheus/blackbox_exporter/releases)
- [node_exporter Releases](https://github.com/prometheus/node_exporter/releases)

### 3. Rehearse

The lab path cannot be used for monitoring (lab and prod share an address space, spec 072).
Rehearse on the monitoring LXC instead: pull the target images, and for a Grafana upgrade start
a temporary container of the new version on a copy of `grafana_data`. See
`specs/090-monitoring-version-currency/quickstart.md` §1–3 for the commands.

### 4. Apply the Upgrade through the Prod Pipeline

Deploy from the branch; no merge to `main` is needed. Do not run `ansible-playbook` against the
host directly.

```bash
gh workflow run lxc-promote-prod.yml --ref <branch> -f service=monitoring -f allow_override_failed_lab_gate=true
# after it passes and is approved:
gh workflow run lxc-apply-prod.yml --ref <branch> -f service=monitoring -f allow_override_failed_lab_gate=true
```

The role runs `promtool check config`, `promtool check rules` and `amtool check-config` with the
target images **before** `docker compose up -d`. If one fails, the old stack is still running:
fix the config on the branch and re-run.

For node_exporter, deploy each LXC the same way with `-f service=<host>`, one at a time.

### 5. Verify Upgrade

```bash
# Check container versions
ssh root@192.168.1.214 'cd /opt/monitoring && docker compose ps'

# Verify Prometheus
curl http://192.168.1.214:9090/-/healthy
curl http://192.168.1.214:9090/api/v1/status/buildinfo | jq '.data.version'

# Verify Grafana
curl http://192.168.1.214:3000/api/health | jq
curl http://192.168.1.214:3000/api/health | jq '.version'

# Verify Telegraf (SNMP collection) and blackbox_exporter
curl -s http://192.168.1.214:9273/metrics | head -3
curl http://192.168.1.214:9115/-/healthy

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

### Option 1: Revert Version Pins (only for components without migrating state)

Prometheus, Alertmanager, Telegraf, blackbox_exporter and node_exporter can be downgraded by
reverting their pins on the branch and redeploying through the prod pipeline (step 4).

**Grafana is the exception.** Grafana 12.4 and later migrate dashboard storage one way on first
start, so an older Grafana pointed at the migrated `grafana_data` is not a rollback. After a
Grafana upgrade, use Option 2.

### Option 2: Revert the LXC Snapshot

Revert the snapshot taken in step 1, then revert the pins on the branch so the next deploy does
not redo the upgrade:

```bash
# On pve, as root
pct rollback <vmid> pre-<change>
pct start <vmid>
```

This restores the whole LXC root disk, including all Docker volumes. Anything written after the
snapshot (metrics, alert state, dashboard edits) is lost.

### Clean Up

Once the upgrade is verified, delete the snapshot so it does not hold thin-pool space:

```bash
pct delsnapshot <vmid> pre-<change>
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

### Telegraf or blackbox_exporter Minor Version Upgrade

**Risk**: Low (usually backward compatible)

1. Check the release notes for removed or renamed plugin options (Telegraf) or probe modules
   (blackbox_exporter)
2. Confirm the Synology SNMP and HTTP probe targets are still up afterwards

### Alertmanager Minor Version Upgrade (e.g., v0.26 → v0.27)

**Risk**: Low (stable config format)

1. Verify SMTP routing still works post-upgrade
2. Test alert delivery

## Validation Checklist

Post-upgrade verification:

- [ ] All monitoring containers running (`docker compose ps`)
- [ ] Prometheus scraping Synology NAS (targets UP)
- [ ] Grafana dashboard loads with live metrics
- [ ] Alert rules loaded in Prometheus
- [ ] Alertmanager SMTP config active
- [ ] No error logs in `docker compose logs`
- [ ] Backup cron job still active (`crontab -l | grep backup`)

## Troubleshooting

### Container Won't Start After Upgrade

```bash
# Check logs
docker compose logs <service_name>

# Common issues:
# - Config format changed (check upstream migration guide)
# - Volume permissions issue (chown data directories)
# - Port conflicts (check if old container still running)
```

### Metrics Not Collecting After Upgrade

```bash
# Verify Prometheus scrape config
docker exec prometheus cat /etc/prometheus/prometheus.yml

# Check Telegraf's SNMP output
curl -s http://localhost:9273/metrics | grep -c '^snmp'
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
