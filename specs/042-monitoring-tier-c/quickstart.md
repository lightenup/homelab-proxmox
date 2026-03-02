# Quickstart: Monitoring Tier C — Security & Availability Probing

**Feature Branch**: `042-monitoring-tier-c`
**Date**: 2026-03-02

## Prerequisites

- Features 040 (Monitoring Overhaul) and 041 (Monitoring Tier B) fully merged and operational
- Ansible vault password available (`.vault-pass.txt` or environment variable)
- DNS: `*.hus-sky.no` resolves to 192.168.1.211 from monitoring LXC (192.168.1.214)
- Network connectivity from monitoring LXC to all fail2ban hosts on port 9191

## Deployment Order

### Step 1: Deploy fail2ban + exporters on 3 hosts

```bash
cd ansible
# Deploy to all 3 fail2ban hosts
ansible-playbook -i inventories/prod/hosts.yml playbooks/fail2ban.yml \
  --vault-password-file .vault-pass.txt
```

This deploys fail2ban, custom filters, jail configs, and the Prometheus exporter on:
- reverse_proxy (192.168.1.211)
- nextcloud (192.168.1.216)
- jellyfin (192.168.1.215)

### Step 2: Deploy monitoring stack update

```bash
cd ansible
ansible-playbook -i inventories/prod/hosts.yml playbooks/monitoring.yml \
  --vault-password-file .vault-pass.txt
```

This adds:
- Blackbox exporter container to Docker Compose
- Blackbox scrape config + fail2ban exporter scrape configs to Prometheus
- Security alert rules (6 rules)
- Updated inhibition rules (4 new rules)
- Security Overview dashboard to Grafana

### Step 3: Verify

1. Open Grafana at https://grafana.hus-sky.no → Security Overview dashboard
2. Check all 5 endpoint status indicators are green
3. Check TLS certificate days-remaining shows >14 days for all domains
4. Check fail2ban sections show jail status for 3 hosts
5. Check Prometheus targets page: blackbox-https and fail2ban-exporter-* are UP

## Verification Commands

```bash
# Check fail2ban status on each host
ssh root@192.168.1.211 "fail2ban-client status"
ssh root@192.168.1.216 "fail2ban-client status"
ssh root@192.168.1.215 "fail2ban-client status"

# Check fail2ban exporter is responding
curl -s http://192.168.1.211:9191/metrics | head -5
curl -s http://192.168.1.216:9191/metrics | head -5
curl -s http://192.168.1.215:9191/metrics | head -5

# Check blackbox exporter probe targets
curl -s "http://192.168.1.214:9115/probe?target=https://grafana.hus-sky.no&module=https_2xx" | grep probe_success

# Check Prometheus has the targets
curl -s http://192.168.1.214:9090/api/v1/targets | python3 -m json.tool | grep blackbox
```

## Rollback

If issues arise:
1. Revert monitoring stack: re-run `monitoring.yml` from the previous commit (removes blackbox container, alert rules, dashboard)
2. Revert fail2ban: `ansible-playbook playbooks/fail2ban.yml --tags uninstall` (or manually `apt remove fail2ban` on affected hosts)
