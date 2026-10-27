# Alerting heartbeat runbook

The alerting path is Prometheus / Loki ruler → Alertmanager (monitoring LXC) → Pushover and
ntfy. If any link in it dies, the alerts about that failure can't be delivered either. The
heartbeat watches the path from outside it. Added after the RCA of 2026-10-27, which found
Alertmanager unscraped, no rule on delivery failures and nothing outside the monitoring LXC.

## How it works

| Piece | Where | What it does |
|---|---|---|
| `Watchdog` alert | `monitoring_stack/files/prometheus/alerts/alerting_path_alerts.yml` | `vector(1)`: always firing, so it is in Alertmanager whenever Prometheus evaluates rules and reaches Alertmanager |
| `null` route | `monitoring_stack/templates/alertmanager.yml.j2` | First route; sends `Watchdog` to a receiver with no integrations, so it never pages |
| `alerting-heartbeat.timer` | pve, role `alerting_heartbeat` | Every 5 min asks `http://192.168.1.214:9093/api/v2/alerts` for an active, unsilenced, uninhibited `Watchdog` |
| Page | Pushover API, directly | After 3 failed checks in a row (~15 min): "Homelab alerting path DOWN" (priority 1). Repeats every 6 h while down; "recovered" once when it is back |

The two delivery hops also have their own alerts, which reach you through the other channel
when one fails: `AlertmanagerNotificationsFailing` (per integration: `pushover`, `webhook` =
ntfy) and `PrometheusNotificationsFailing`. The Loki ruler's hop is `LogRuleNotificationsFailing`.

## You got "Homelab alerting path DOWN"

1. Is the monitoring LXC up? `ssh root@192.168.1.214 'docker ps --format "{{.Names}} {{.Status}}"'`
2. Is Alertmanager up? `curl -s http://192.168.1.214:9093/-/ready`
3. Is Prometheus evaluating rules? `curl -s 'http://192.168.1.214:9090/api/v1/query?query=ALERTS{alertname="Watchdog"}'`
4. Was `Watchdog` silenced? `curl -s http://192.168.1.214:9093/api/v2/silences`. Expire any silence matching it; a silenced Watchdog reads as a dead path, by design.
5. On pve: `journalctl -u alerting-heartbeat -n 20` shows each check's reason.

Until it recovers, no alert reaches you: check the services you care about by hand.

## Operating it

```bash
# deploy or update (operator path; pve has no pipeline)
cd ansible && ansible-playbook -i inventories/prod/hosts.yml playbooks/host_proxmox.yml \
  --tags alerting_heartbeat --vault-password-file .vault-pass.txt

# on pve
systemctl list-timers alerting-heartbeat.timer
systemctl start alerting-heartbeat.service && journalctl -u alerting-heartbeat -n 5
cat /var/lib/alerting-heartbeat/state     # "<consecutive failures> <time of last DOWN page>"
```

A monitoring deploy restarts Prometheus and Alertmanager; `Watchdog` is back within about a
minute, well inside the 15-minute threshold, so deploys do not page.

The Pushover credentials are Alertmanager's (`group_vars/monitoring/vault.yml`). The role
loads that file itself because `monitoring` is a host, not a group, so Ansible never applies
`group_vars/monitoring/` on its own. They are written to `/etc/default/alerting-heartbeat`
(0600) and reach `curl` on stdin, never on its command line.

## Limits

- pve is the watcher. If pve itself is down, the monitoring LXC is too (it runs on pve) and
  nothing pages. Covering that needs a check from off-site.
- It proves alerts reach Alertmanager. Alertmanager → Pushover/ntfy is covered by
  `AlertmanagerNotificationsFailing`, which can only reach you through the channel still working.
