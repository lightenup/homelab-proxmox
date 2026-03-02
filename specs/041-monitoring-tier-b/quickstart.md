# Quickstart: Monitoring Tier B

**Branch**: `041-monitoring-tier-b` | **Date**: 2026-03-01

## Prerequisites

1. Feature 040 (Monitoring Overhaul) merged to main
2. Monitoring stack running on LXC 192.168.1.214
3. Synology NAS reachable at 192.168.1.109 with SNMP enabled
4. Ansible vault credentials available (SNMP, exporter API keys)

## Deployment Order

All changes deploy via existing playbooks. No new playbooks required.

### Step 1: Synology SNMP Fix (monitoring playbook)

```bash
cd ansible
ansible-playbook -i inventories/prod/hosts.yml playbooks/monitoring.yml --diff
```

Deploys: Updated Telegraf config, fixed alert rules, corrected dashboard.

**Verify**: Open Grafana → Synology NAS Health dashboard → all panels show live data.

### Step 2: AdGuard Home Exporter (adguard playbook)

```bash
# First: add AdGuard API credentials to vault
ansible-vault edit group_vars/services/vault.yml
# Add: adguard_admin_user, adguard_admin_password

ansible-playbook -i inventories/prod/hosts.yml playbooks/adguard.yml --diff
```

Deploys: AdGuard exporter container on the adguard LXC.

**Verify**: `curl http://192.168.1.210:9618/metrics` returns adguard_* metrics.

### Step 3: Nextcloud Exporter (nextcloud playbook)

```bash
# First: generate and vault the serverinfo token
TOKEN=$(openssl rand -hex 32)
ansible-vault edit group_vars/services/vault.yml
# Add: nextcloud_serverinfo_token: <token>

ansible-playbook -i inventories/prod/hosts.yml playbooks/nextcloud.yml --diff
```

Deploys: Nextcloud exporter sidecar in the Nextcloud docker-compose.

**Verify**: `curl http://192.168.1.216:9205/metrics` returns nextcloud_* metrics.

### Step 4: Jellyfin Exporter (jellyfin playbook)

```bash
# First: create Jellyfin API key via admin UI and vault it
ansible-vault edit group_vars/services/vault.yml
# Add: jellyfin_api_key: <key>

ansible-playbook -i inventories/prod/hosts.yml playbooks/jellyfin.yml --diff
```

Deploys: Jellyfin exporter as systemd service on the Jellyfin LXC.

**Verify**: `curl http://192.168.1.215:9594/metrics` returns jellyfin_* metrics.

### Step 5: Monitoring Stack Redeploy (picks up new contracts)

```bash
ansible-playbook -i inventories/prod/hosts.yml playbooks/monitoring.yml --diff
```

Deploys: Updated Prometheus scrape targets, service alert rules, provisioned dashboards.

**Verify**:
- Prometheus targets page: all new scrape targets show "UP"
- Grafana dashboard list: AdGuard Home, Nextcloud, Jellyfin dashboards present
- Each dashboard shows live data

## Smoke Test Checklist

- [ ] Synology NAS dashboard: all panels show live data
- [ ] `SynologyNASDown` alert references `job="telegraf-snmp"` (check Prometheus alerts page)
- [ ] AdGuard Home dashboard: DNS query rate, blocked %, upstream response times visible
- [ ] Nextcloud dashboard: active users, storage usage, health status visible
- [ ] Jellyfin dashboard: media library stats, session count visible
- [ ] All new Prometheus targets show "UP" status
- [ ] Re-running each playbook produces no changes (idempotency)
