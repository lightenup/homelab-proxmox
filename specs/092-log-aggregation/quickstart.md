# Quickstart: Log Aggregation and Log-Based Alerting

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Contract**: [contracts/log-pipeline.md](./contracts/log-pipeline.md)

This is the validation and rollout guide. Every step is read-only unless it says it changes
something.

- Hosts and addresses are from `ansible/inventories/prod/hosts.yml`. Monitoring is
  `192.168.1.214`, Prometheus is `http://192.168.1.214:9090`, Grafana is
  `http://192.168.1.214:3000`, and pve is `192.168.1.112`.
- Live commands run from the dev Mac as `ssh ci@pve`, then `sudo pct exec <vmid> -- …` for an
  LXC.
- Loki's API is reachable only on the monitoring host, at `127.0.0.1:3100`
  ([contracts/log-pipeline.md](./contracts/log-pipeline.md) C1).

```bash
# helper used below: run a LogQL query on the store
lq() { ssh ci@pve "sudo pct exec 103 -- curl -s -G http://127.0.0.1:3100/loki/api/v1/query_range \
  --data-urlencode 'query=$1' --data-urlencode start=$(( $(date +%s) - ${2:-600} ))000000000"; }
```

## 0. Before implementation

### 0.1 Re-run the login census (R3)

Re-run the census script from research R3 (`journalctl -t sshd -t sshd-session -g Accepted` and
`-t sudo`, on every LXC and on pve). Every (user, key) seen must be on the
`ssh_login_allowlist` in data-model §4. Any new key is either added, after the owner confirms it,
or investigated before rollout.

### 0.2 Baseline memory

Record from Prometheus:

- `node_memory_MemAvailable_bytes` for `monitoring` (192.168.1.214) and `ntfy` (192.168.1.222);
- Prometheus' own `process_resident_memory_bytes`.

SC-007 compares against these numbers.

## 1. Static checks (dev Mac, before any deploy)

```bash
bash scripts/ci/python-tests.sh                       # guard tests incl. redaction corpus (R7)
cd ansible
ansible monitoring -i inventories/prod/hosts.yml -c local -m ansible.builtin.template \
  -a "src=roles/monitoring_stack/templates/log_alerts.yaml.j2 dest=/tmp/092/log_alerts.yaml"
lokitool rules check /tmp/092/log_alerts.yaml         # lokitool from the v{{loki_version}} release
# never `lokitool rules lint` without --dry-run: it rewrites the file (R10)
ansible ntfy -i inventories/prod/hosts.yml -c local -m ansible.builtin.template \
  -a "src=roles/alloy/templates/config.alloy.j2 dest=/tmp/092/config.alloy"
docker run --rm -v /tmp/092/config.alloy:/c.alloy:ro grafana/alloy:v1.21.2 validate /c.alloy
```

Expected: tests pass, and both validators exit 0. Then deliberately break one `expr` in the
rendered rules and confirm that `lokitool rules check` exits 1.

## 2. Rollout (changes production)

Order: **services → pve → monitoring last**. Collectors installed before the relay exists retry
without limit and lose nothing (FR-011). That is the first real test of R9. Monitoring last also
means the `alloy` scrape targets only appear once every collector is there.

1. Deploy each service through the gated pipeline (`Prod 1 - LXC Promote` → `Prod 2 - LXC Apply`)
   on this branch. Use the order `market-model` (the test LXC), then the rest. After each one,
   on that LXC:

   ```bash
   systemctl is-active alloy; id alloy                # groups: adm systemd-journal [docker]
   systemctl show alloy -p MemoryMax                  # 167772160
   sshd -T | grep -E '^(passwordauthentication|kbdinteractiveauthentication)'   # both "no"
   journalctl -u alloy --since -5m | grep -c 'connection refused'   # >0 until monitoring is deployed
   ```

2. On `nextcloud` (R8): `runuser -u alloy -- head -c1 /mnt/nextcloud/data/nextcloud.log >/dev/null && echo readable`.
   If it is not readable, apply the `nogroup` fallback and record the decision.

3. pve, from an operator machine (operator-only, as `091` recorded):
   `ansible-playbook -i inventories/prod/hosts.yml playbooks/host_proxmox.yml`.
   Then check on pve that `alloy` is active, and that `sshd -T | grep passwordauthentication`
   **still says `yes`** (owner decision).

4. Monitoring, through the pipeline. Then:

   ```bash
   ssh ci@pve 'sudo pct exec 103 -- docker ps --format "{{.Names}} {{.Status}}" | grep loki'
   ssh ci@pve 'sudo pct exec 103 -- curl -s http://127.0.0.1:3100/ready'           # ready
   curl -s 'http://192.168.1.214:9090/api/v1/query?query=up{job=~"loki|alloy"}' | jq '.data.result | length'   # 13
   ```

   Within about 5 minutes, every collector's `loki_write_sent_entries_total` increases.

## 3. Exposure checks (FR-013)

```bash
curl -s -m3 http://192.168.1.214:3100/ready; echo rc=$?                     # connection refused
curl -s -m3 'http://192.168.1.214:3101/loki/api/v1/query?query={env="prod"}' -o /dev/null -w '%{http_code}\n'   # 404
```

In Grafana, Connections → Data sources → Loki → *Save & test* succeeds.

## 4. SC-001 canary and collector memory

```bash
TOKEN=canary-$(date +%s)
ssh ci@pve "sudo logger -t canary $TOKEN-proxmox; for id in \$(sudo pct list | awk 'NR>1&&\$NF!=\"homeassistant\"{print \$1}'); do \
  sudo pct exec \$id -- logger -t canary $TOKEN-\$id; \
  sudo pct exec \$id -- sh -c 'command -v docker >/dev/null && docker run --rm busybox echo $TOKEN-docker-'\$id; done"
sleep 60; lq "{env=\"prod\"} |= \"$TOKEN\"" 300 | jq -r '.data.result[] | .stream.host + " " + .stream.source'
```

Expected: one `journal` line for each of the 12 hosts, and one `docker` line for each of the 9
Docker hosts. Record the result per host. A missing journal line almost always means a missing
group membership (R5).

Collector memory: `systemctl show alloy -p MemoryCurrent` on `ntfy` and on `hermes`. Record both.
If `ntfy`'s value is above 70% of `MemoryHigh`, raise the limits before going further.

## 5. SC-002 redaction drill

On `market-model`, write each corpus line from
`python/tests/guardrails/fixtures/redaction_corpus.txt`, with a drill prefix, to the journal
(`logger -t drill`) and to a throwaway container's stdout. Then:

```bash
lq '{host="market-model"} |= "drill-"' 600 | jq -r '.data.result[].values[][1]'
```

Expected: every secret shows `<redacted>`, the control line is unchanged, and searches for each
raw secret return nothing.

## 6. SC-004 per-service baselines and enabling the error rules (after ≥ 7 days)

For each of `llm-router`, `hermes`, `nextcloud`, `immich` and `ntfy`, run the rule's
count expression over the last 7 days with `step=15m`, using `query_range`:

```bash
ssh ci@pve "sudo pct exec 103 -- curl -s -G http://127.0.0.1:3100/loki/api/v1/query_range \
  --data-urlencode 'query=<count expression without the comparison>' \
  --data-urlencode start=\$(( \$(date +%s) - 604800 ))000000000 --data-urlencode step=900" \
  | jq '[.data.result[].values[][1] | tonumber] | max'
```

Set the threshold to `max(5, 3 × max_15m)` (R8). Record `baseline: {from, to, max_15m}` and set
`enabled: true` in the service's `host_vars`, then redeploy monitoring. Next, inject an error
burst into one service (for llm-router, `docker exec` a `logger`-style JSON line repeated
threshold+1 times; for others, the equivalent line). Exactly that service's alert reaches
Pushover and ntfy. A service that does not pass stays `enabled: false` with `disabled_reason`.

## 7. FR-016 / SC-008 leaked-credential procedure (this is also the runbook)

1. Log a synthetic credential in a format **not** on the list, for example
   `drill-leak HOMELABX-<random 24 chars>`, on `market-model`. Confirm it is stored
   (`lq '{host="market-model"} |= "HOMELABX-"'`).
2. **Rotate.** For a real credential, rotate it at its issuer first. For the drill there is
   nothing to rotate.
3. **Delete**, on the monitoring host:

   ```bash
   curl -s -X POST -G http://127.0.0.1:3100/loki/api/v1/delete \
     --data-urlencode 'query={env="prod"} |= "HOMELABX-"' \
     --data-urlencode start=<unix seconds before first occurrence> -w '%{http_code}\n'   # 204
   curl -s http://127.0.0.1:3100/loki/api/v1/delete | jq '.[-1].status'
   ```

   The lines disappear from queries at once, and physical deletion follows after 10 minutes and
   the next compaction (R2).
4. **Extend.** Add a pattern to `alloy_redaction_patterns` and a corpus line to the fixture, run
   the tests, and deploy one collector (`market-model`). Log a new `HOMELABX-` line. It arrives
   as `<redacted>`.

Record the timings.

## 8. SC-003 OOM drill

On `market-model` (changes nothing persistent):

```bash
docker run --rm --memory=32m --memory-swap=32m python:3-alpine python -c "b=[]
while True: b.append(' '*10**6)"
```

Expected: within 5 minutes, one `KernelOomKill` alert on Pushover and ntfy, with
`lxc=market-model` and `task=python`.

Then stop Loki (`docker stop loki` on monitoring), repeat the drill, and expect `HostOomKill`
from Prometheus. Start Loki again.

## 9. SC-005 login drill

1. Make a throwaway key on the Mac: `ssh-keygen -t ed25519 -f /tmp/092drill -N ''`. Append it to
   `root`'s `authorized_keys` on `market-model` (through `pct exec`). Log in once with it, then
   remove the key. Expected: `SshLoginNotAllowed` names `market-model`, `root`, the source and
   the drill fingerprint.
2. On pve, a password login (by the owner) raises `SshLoginNotAllowed` with `method=password`.
3. A full pipeline deploy of one service, an owner login from the Mac on the LAN, and an owner
   login over the tailnet to an LXC and to pve raise **no** login or `sudo` alert.
4. `ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no root@192.168.1.218`
   gives `Permission denied (publickey)` on every LXC. Loop over the 11 addresses and record
   each.

## 10. SC-006 outage drill

1. `systemctl stop alloy` on `market-model`. Within 10 minutes `LogCollectorDown` fires, for
   that host only. Start it again.
2. Stop Loki for 30 minutes and run the §4 canary during the outage. `ServiceDown` for job `loki`
   reaches Pushover as critical. No service restarts, which you can confirm by checking that the
   `docker ps` uptimes are unchanged and the blackbox probes are green. After Loki restarts,
   every canary line from the outage is present with its original timestamp.

## 11. SC-009 LAB path

Run `lxc-deploy-lab.yml` for `market-model`. Afterwards, on `market-model`, the alloy config
checksum and unit are unchanged. On monitoring, `log_alerts.yaml`, `prometheus/alerts/log_pipeline_alerts.yml` and the Loki
container are unchanged (`sha256sum`, `docker inspect -f '{{.Created}}' loki`). Prometheus still
lists the same 12 `alloy` targets (FR-017, research R12).

## 12. SC-007 after 14 days

Record the following:

- ingestion per host:
  `sum by (instance) (increase(loki_write_sent_bytes_total{job="alloy"}[14d]))`;
- the size of the `loki_data` volume;
- peak `container_memory` for Loki;
- `MemoryPeak` for the collectors on `ntfy` and `hermes`;
- the monitoring LXC's minimum `MemAvailable`.

Then confirm or change FR-004's limits and the collectors' `MemoryHigh` and `MemoryMax`.

## 13. Record

| Check | Date | Result |
|---|---|---|
| §0.1 census matches allowlist | 2026-10-24 | Owner confirmed `3+Lnah…` as theirs; allow-list committed per R3 |
| §1 static checks | 2026-10-24 | 276 tests pass; lokitool check, promtool, `loki -verify-config`, `alloy validate` (6 host types) all exit 0 |
| §2 rollout (per host) | 2026-10-24/25 | All 11 LXCs + pve + monitoring live. Five defects found and fixed in rollout: `proxmox_hosts` undefined in scoped inventory, glob-path assert, missing `unzip`, Grafana not restarted on datasource change, `#` comments in Alloy config (now validated before write). nextcloud.log readable by alloy without the `nogroup` fallback |
| §3 exposure | 2026-10-25 | `:3100` refused from LAN; `:3101` query path 404; Grafana registered Loki (uid `loki`) |
| §4 SC-001 canary (12 journal / 9 docker) | 2026-10-25 | 11/11 LXC journals + pve journal (verified via live sshd lines; `ci` sudo cannot run `logger` on pve); 9/9 docker within 60 s after `refresh_interval = "15s"` (1m default missed short-lived containers) |
| §4 collector memory ntfy / hermes | 2026-10-24 | ntfy 87 MiB at first start (68% of MemoryHigh 128M), under the 70% bar; re-measure at SC-007 |
| §5 SC-002 redaction | 2026-10-25 | All 8 patterns redacted on market-model, journal and docker; controls byte-identical; 0 streams contain a raw drill secret |
| §6 SC-004 baselines (5 services) | | |
| §7 SC-008 purge | | |
| §8 SC-003 OOM + backstop | | |
| §9 SC-005 logins | | |
| §10 SC-006 outages | | |
| §11 SC-009 LAB | | |
| §12 SC-007 (14 days) | | |
