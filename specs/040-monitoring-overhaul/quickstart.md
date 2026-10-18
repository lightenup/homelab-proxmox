# Quickstart: Monitoring & Observability Overhaul

**Branch**: `040-monitoring-overhaul` | **Date**: 2026-03-01

## Prerequisites

- Ansible installed locally with access to the homelab inventory
- Vault password available (for encrypted secrets)
- All service LXCs reachable from the deployment machine

## Deployment Order

The feature touches multiple roles and playbooks. Deploy in this order:

### 1. Deploy node_exporter to all service LXCs

Run each service playbook to deploy node_exporter via the updated `lxc_base` role:

```bash
# From ansible/ directory
ansible-playbook playbooks/reverse_proxy.yml --tags base
ansible-playbook playbooks/immich.yml --tags base
ansible-playbook playbooks/jellyfin.yml --tags base
ansible-playbook playbooks/nextcloud.yml --tags base
# Note: the homeassistant playbook also needs running if that LXC exists
```

**Verify**: `curl http://192.168.1.211:9100/metrics` should return Prometheus metrics from each LXC.

### 2. Enable Caddy metrics on the reverse proxy

```bash
ansible-playbook playbooks/reverse_proxy.yml
```

**Verify**: `curl http://192.168.1.211:2019/metrics` should return Caddy metrics.

### 3. Enable Immich telemetry

```bash
ansible-playbook playbooks/immich.yml
```

**Verify**: `curl http://192.168.1.213:8081/metrics` should return Immich API metrics.

### 4. Deploy the updated monitoring stack

```bash
ansible-playbook playbooks/monitoring.yml
```

This single playbook:
- Removes Uptime Kuma container (cleanup)
- Deploys updated Prometheus config with all scrape targets
- Deploys new alert rules (infrastructure + service-specific)
- Deploys updated Alertmanager config with inhibition rules
- Provisions new Grafana dashboards (infrastructure, Caddy, Immich)
- Aligns version pins in defaults

**Verify**:
- Open Grafana at `https://grafana.hus-sky.no` → Infrastructure Overview dashboard shows all 7 containers
- Open Prometheus at `http://192.168.1.214:9090/targets` → All targets show "UP"
- Open Alertmanager at `http://192.168.1.214:9093` → Zero active alerts

### 5. Run the proxmox_backup playbook (Kuma cleanup)

```bash
ansible-playbook playbooks/backup_proxmox.yml
```

**Verify**: No Kuma references in backup config files on the Proxmox host.

## Adding Monitoring for a New Service

To add monitoring for a future service, add a `monitoring_contract` to the service role's `defaults/main.yml`:

```yaml
# Example: roles/my_new_service/defaults/main.yml
monitoring_contract:
  enabled: true
  scrape_targets:
    - job_name: "my-new-service"
      port: 9100
      path: "/metrics"
  alert_rules: []
  dashboard_file: null
```

Then re-run the monitoring playbook:
```bash
ansible-playbook playbooks/monitoring.yml
```

The new service will automatically appear in Prometheus scrape targets. No changes to the monitoring role required (FR-007, SC-005).

## Verification Checklist

- [ ] All 7 LXCs show in infrastructure dashboard (SC-001)
- [ ] Stop a service → receive email alert within 5 min (SC-002)
- [ ] Caddy dashboard shows request rates after generating traffic (SC-003)
- [ ] Immich dashboard shows job queues after uploading photos (SC-004)
- [ ] `grep -r "caddy\|immich" ansible/roles/monitoring_stack/` returns zero hits (SC-005)
- [ ] `docker ps` on monitoring LXC shows no Uptime Kuma container (SC-006)
- [ ] Defaults file versions match group_vars (SC-007)
- [ ] Synology dashboard still renders correctly (SC-008)
- [ ] Re-run monitoring playbook → no changes (SC-009)
