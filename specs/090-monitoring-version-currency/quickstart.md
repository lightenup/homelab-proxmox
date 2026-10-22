# Quickstart: Monitoring Stack Version Currency

This is the validation and rollout record for `090`. Run the sections in order. Record the results
inline: dates, counts and versions, as the 089 quickstart does. The data shapes are in
[data-model.md](./data-model.md), and the check's interface is in
[contracts/currency-check.md](./contracts/currency-check.md).

Conventions: `MON=192.168.1.214` (VMID 103). Run the `ssh root@…` commands from an operator machine
on the LAN; the Mac works (root SSH to the LXC, Docker Hub reachable). The Mac cannot reach the
tailnet (Zscaler); see `AGENTS.md`. The monitoring LXC has no `jq` or `bc`: keep raw JSON on the
host and normalise it with `jq` on the operator machine rather than installing packages.

## 0. Static checks (PR CI, before any deploy)

```bash
bash scripts/ci/python-tests.sh            # includes guardrails/test_version_pins.py and version_currency unit tests
cd ansible && ansible-playbook playbooks/monitoring.yml --syntax-check
ansible-lint roles/monitoring_stack roles/node_exporter
act -l && act -n -W .github/workflows/version-currency.yml workflow_dispatch
rg -n '^(prometheus|grafana|telegraf|alertmanager|blackbox_exporter|node_exporter)_version:' ansible/
```

Expected: tests pass, and the syntax check and lint are clean. `rg` shows exactly six lines: five in
`group_vars/monitoring/vars.yml` and one in `group_vars/all/vars.yml` (SC-004).

### Baseline (T001, 2026-10-22)

- `ansible-playbook playbooks/monitoring.yml --syntax-check`: PASS
- `.venv/bin/python -m pytest -c python/pytest.ini --no-cov python/tests/guardrails`: 12 passed
- `.venv/bin/python -c 'import yaml'`: ok

### Upstream re-check (T002, 2026-10-22)

All R-01 targets confirmed as latest patch on their line:

| Component | Target | Latest on line | Status |
|---|---|---|---|
| Grafana | 13.2.4 | 13.2.4 | current |
| Prometheus | v3.13.5 | 3.13.5 (LTS) | current |
| Alertmanager | v0.34.1 | 0.34.1 | current |
| blackbox_exporter | v0.29.1 | 0.29.1 | current |
| Telegraf | 1.40.2 | 1.40.2 | current |
| node_exporter | 1.12.1 | 1.12.1 | current |

Prometheus 3.13 is still the newest LTS line (3.15 is non-LTS, eol 2026-11-06).

### US4 static checks (T029–T031, 2026-10-22)

- `bash scripts/ci/python-tests.sh`: 199 passed; total coverage 93%, `version_currency.py` 96%.
- Mutation score of `version_currency.py` alone: 320 killed / 85 survived = **79.0%** (floor 41%).
  Measured locally with mutmut 2.5.1 on Python 3.14 (2.5.1 does not run on 3.15), on a scratch copy
  of the repo, runner limited to `python/tests/version_currency`. The PR mutation gate on `42cd558`
  (whole package, on `pve`) passed at 42.07%.
- Guard file `python/tests/guardrails/test_version_pins.py`: 5 passed, no `xfail` markers.
- `actionlint .github/workflows/version-currency.yml`: clean. `act -l`: lists job `check`
  (schedule, workflow_dispatch). `act -n`: not run, the Docker daemon (Colima) was not running
  on the Mac.
- Local dry run from the Mac: exit 1. Every source failed with `CERTIFICATE_VERIFY_FAILED` (CA
  cert does not include key usage extension), which is the Zscaler TLS interception, so no
  findings could be computed locally. The five `unchecked` pins were listed. The findings check
  moves to the `pi-ci` dry run (§9 row 1).

## 1. Confirm target tags exist (from `pve` or the monitoring LXC)

```bash
ssh root@$MON 'for i in grafana/grafana:13.2.4 prom/prometheus:v3.13.5 prom/alertmanager:v0.34.1 \
  prom/blackbox-exporter:v0.29.1 telegraf:1.40.2 alpine:latest; do docker pull -q "$i" >/dev/null && echo "ok $i" || echo "MISSING $i"; done'
```

Expected: no `MISSING`. If a newer patch of the same line exists, use it and update research R-01.
Pre-pulling also shortens the outage during deploy. `alpine` is for the §3 data copy, so live
Grafana is not paused while an image downloads.

**Result (T009, 2026-10-22):** all five target images pulled, no `MISSING`.

## 2. Before snapshot (FR-006)

The Grafana password is read from the live container's environment **on the LXC** and never
printed, so it does not pass through the operator's shell or history. Raw JSON stays on the host;
it is normalised on the operator machine (the LXC has no `jq`).

```bash
ssh root@$MON 'mkdir -p /root/090 && cd /root/090 &&
  curl -s localhost:9090/api/v1/targets > targets.before.raw.json &&
  curl -s localhost:9090/api/v1/rules   > rules.before.raw.json &&
  GF_PW="$(docker exec grafana printenv GF_SECURITY_ADMIN_PASSWORD)" &&
  echo "grafana auth: $(curl -s -o /dev/null -w "%{http_code}" -u admin:"$GF_PW" localhost:3000/api/user)" &&
  curl -s -u admin:"$GF_PW" "localhost:3000/api/search?type=dash-db" > dashboards.before.raw.json'
for f in targets rules dashboards; do scp -q root@$MON:/root/090/$f.before.raw.json .; done
jq -S '[.data.activeTargets[] | {job:.labels.job, instance:.labels.instance, health}] | sort_by(.job,.instance)' targets.before.raw.json > targets.before.json
jq -S '[.data.groups[] | .name as $g | .rules[] | $g + "/" + .name] | sort' rules.before.raw.json > rules.before.json
jq -S '[.[] | {uid, title}] | sort_by(.uid)' dashboards.before.raw.json > dashboards.before.json
echo "targets up/total: $(jq '[.[]|select(.health=="up")]|length' targets.before.json) / $(jq length targets.before.json)"
jq length rules.before.json dashboards.before.json
scp -q targets.before.json rules.before.json dashboards.before.json root@$MON:/root/090/
```

`grafana auth` must be `200`. A `401` means the admin password was changed in the UI after the
database was created (`GF_SECURITY_ADMIN_PASSWORD` only applies at first start); stop and resolve.
If more than about a day passes before §5, re-run this section just before §4.

| Item | Count before | Recorded |
|---|---|---|
| Targets (up / total) | 41 / 41 | 2026-10-22 14:57 local, T010 |
| Alert rules | 33 | |
| Dashboards | 8 | `caddy-proxy`, `immich-photos`, `infra-overview`, `jellyfin`, `llm-router`, `nextcloud`, `security-overview`, `synology-nas-health` |

## 3. Side-by-side rehearsal on the monitoring LXC (research R-06)

The running stack is not restarted. Volume `monitoring_grafana_data`, network `monitoring_default`
(compose project `monitoring`; confirm with `docker volume ls` / `docker network ls`).

```bash
# validators: target images against the live rendered config (check config also checks the rule files)
ssh root@$MON 'cd /opt/monitoring &&
  docker run --rm --entrypoint promtool -v $PWD/prometheus:/etc/prometheus:ro prom/prometheus:v3.13.5 check config /etc/prometheus/prometheus.yml &&
  docker run --rm --entrypoint amtool  -v $PWD/alertmanager:/etc/alertmanager:ro prom/alertmanager:v0.34.1 check-config /etc/alertmanager/alertmanager.yml'

# Grafana 13.2 against a consistent copy of its data. `docker pause` freezes (does not restart)
# live Grafana so the SQLite copy is consistent; alpine must already be pulled (§1).
ssh root@$MON 'docker volume create grafana_rehearsal &&
  docker pause grafana &&
  docker run --rm -v monitoring_grafana_data:/from:ro -v grafana_rehearsal:/to alpine sh -c "cp -a /from/. /to/";
  docker unpause grafana &&
  docker run -d --name grafana-rehearsal -p 127.0.0.1:3999:3000 \
    -v grafana_rehearsal:/var/lib/grafana \
    -v /opt/monitoring/grafana/provisioning:/etc/grafana/provisioning:ro \
    -v /opt/monitoring/grafana/dashboards:/var/lib/grafana/dashboards:ro \
    -e GF_SERVER_ROOT_URL=http://localhost:3999/ \
    -e GF_UNIFIED_ALERTING_EXECUTE_ALERTS=false \
    -e GF_USERS_ALLOW_SIGN_UP=false -e TZ=Europe/Copenhagen \
    --network monitoring_default grafana/grafana:13.2.4'
```

- `GF_SERVER_ROOT_URL` makes login redirects work through the tunnel below;
  `GF_UNIFIED_ALERTING_EXECUTE_ALERTS=false` stops the copy from evaluating any Grafana-managed
  alert rules and notifying a second time.
- `docker logs grafana-rehearsal` shows "Unified storage migrations completed successfully" and a
  `Count validation` line for dashboards with `legacy_count` = `unified_count`; no
  `database is locked`, `malformed` or migration errors. Two `level=error` lines about missing
  `provisioning/plugins` and `provisioning/alerting` directories are pre-existing (live 12.3.1
  logs them too) and harmless.
- The dashboard list from `localhost:3999/api/search?type=dash-db` equals `dashboards.before.json`.
- Open each dashboard through a tunnel: `ssh -N -L 3999:localhost:3999 root@$MON`, then
  `http://localhost:3999/d/<uid>`, and confirm there are no panel errors.

Clean up: `ssh root@$MON 'docker rm -f grafana-rehearsal && docker volume rm grafana_rehearsal'`.

| Check | Result (T011, 2026-10-22) |
|---|---|
| `promtool check config` (3.13.5), incl. 4 rule files | PASS |
| `amtool check-config` (0.34.1) | PASS (8 inhibit rules, 3 receivers) |
| Grafana 13.2.4 migration clean | PASS: dashboards 8 → 8, database `ok`, 0 restarts, data source healthy; 0 Grafana-managed alert rules |
| Dashboards listed / opened without errors | 8 / 8 (API list identical; owner opened all 8, no panel errors) |

Rehearsal container and volume removed; live stack untouched (all five containers up throughout).
Note: on this run `alpine` was not pre-pulled, so live Grafana stayed paused for a few seconds
while it downloaded; §1 now pulls it.

If Grafana fails and the cause cannot be fixed in this feature, fall back to 12.4.13 (spec
FR-001), record why here, and repeat this section with `grafana/grafana:12.4.13`.

## 4. Rollback point (FR-011)

On `pve`, as root:

```bash
VMID=$(pct list | awk '$NF=="monitoring"{print $1}')
pct snapshot "$VMID" pre-090 --description "090: before monitoring upgrade"
pct listsnapshot "$VMID"
```

| VMID | Snapshot | Taken (UTC) | Deleted (UTC) |
|---|---|---|---|
| | `pre-090` | | |

Previous pins: Grafana `12.3.1`, Prometheus `v3.8.1`, Alertmanager `v0.30.0`, blackbox `v0.28.0`,
Telegraf `1.37.0`, node_exporter `1.10.2`.

## 5. Production deploy: monitoring host

Use the prod path only. The lab half refuses `monitoring` by design (the 072 guard).

```bash
gh workflow run lxc-promote-prod.yml --ref <branch> -f service=monitoring -f allow_override_failed_lab_gate=true
# after it passes:
gh workflow run lxc-apply-prod.yml --ref <branch> -f service=monitoring -f allow_override_failed_lab_gate=true
```

Expected: the play validates the configs with the new images **before** `docker compose up -d`
(research R-05), then `verify.yml` passes.

Record the time the stack restarted. Use the Prometheus container start time:
`ssh root@$MON 'date -d "$(docker inspect -f {{.State.StartedAt}} prometheus)" +%s'`. §6 uses it.

| Deploy run | `DEPLOY_EPOCH` (Prometheus restart, Unix s) |
|---|---|
| | |

## 6. After snapshot and comparison (FR-007 to FR-010, SC-001 to SC-003)

Repeat §2 with `.after.json`, then:

```bash
ssh root@$MON 'cd /root/090 && for f in targets rules dashboards; do diff <(jq -S . $f.before.json) <(jq -S . $f.after.json) && echo "$f: identical"; done'
ssh root@$MON 'curl -s localhost:9090/api/v1/status/buildinfo | jq -r .data.version; curl -s localhost:3000/api/health | jq -r .version;
  docker exec alertmanager amtool --version | head -1; docker exec telegraf telegraf --version; docker exec blackbox-exporter blackbox_exporter --version 2>&1 | head -1'
# FR-010: the hour ending 5 min before the restart, pinned with @ so the result does not depend
# on when this runs (valid within the 15-day retention)
curl -s "http://$MON:9090/api/v1/query" --data-urlencode "query=count(count_over_time(up[1h] @ $((DEPLOY_EPOCH - 300))))" | jq '.data.result[0].value[1]'
```

Targets that were `down` before (for example `llm-queue` when the Mac sleeps) may differ in
`health` only. Every other diff blocks completion.

Then open the eight dashboards at `https://grafana.hus-sky.no` and confirm there are no panel
errors. Fire a test alert, as in 082 quickstart §3:

```bash
ssh root@$MON 'docker exec alertmanager amtool --alertmanager.url=http://localhost:9093 alert add Test090 severity=warning \
  --annotation=summary="090 upgrade test" --end=$(date -u -d "+2 min" +%Y-%m-%dT%H:%M:%SZ)'
```

| Check | Result |
|---|---|
| Versions running (SC-001) | |
| Targets / rules / dashboards identical (SC-002) | |
| Dashboards open without panel errors | / 8 |
| History before the upgrade is queryable (FR-010) | |
| Test alert on Pushover / ntfy within 5 min (SC-003) | / |

**Rollback** (any blocking failure): `pct rollback "$VMID" pre-090` on `pve`, then revert the pins
on the branch. Changing the Grafana pin back alone is **not** a rollback (research R-02).

After everything passes: `pct delsnapshot "$VMID" pre-090` (FR-012). Record the time in §4.

## 7. node_exporter rollout (SC-007)

Each LXC gets the new binary through its own normal prod deploy (`lxc_base` → `node_exporter`),
one host at a time. Check each one:

```bash
ssh root@<host> '/usr/local/bin/node_exporter --version | head -1'
curl -s "http://$MON:9090/api/v1/query" --data-urlencode 'query=count by (version) (node_exporter_build_info)'
```

| Host | Deployed (date) | Version |
|---|---|---|
| reverse_proxy | | |
| immich | | |
| monitoring | (done in §5) | |
| jellyfin | | |
| nextcloud | | |
| financial-scenario | | |
| market-model | | |
| eurooffice | | |
| llm-router | | |
| hermes | | |
| ntfy | | |

Done when the `count by (version)` query returns only `1.12.1`.

## 8. ntfy publisher (082 contract)

1. Add the `version_check` account to the vault and to `ntfy_users`, then deploy ntfy through the
   prod path.
2. Extend the 082 access matrix and run it:
   `NTFY_VERSION_CHECK_TOKEN=… scripts/healthcheck/ntfy-acl-check.sh`. Expected: every cell
   matches, and `version_check` can write only `versions`.
3. Subscribe to `versions` in the app.

## 9. Currency check (SC-005, SC-006)

```bash
# local parity, no publish
PYTHONPATH=python/src python -m homelab_proxmox_orchestrator.version_currency --dry-run
# SC-005: on a throwaway branch, lower grafana_version to 13.2.3 and run the workflow on it
gh workflow run version-currency.yml --ref test/090-lowered-pin -f dry_run=false
```

Expected:

- The dry run lists the service pins that are behind today (research R-10) and **no**
  monitoring pin. It exits 0.
- The test-branch run posts to `versions` with a `grafana_version 13.2.3 -> 13.2.4` line
  (SC-005).
- With the network to endoflife.date blocked, or a bad token, the run fails red and does not
  pass silently (FR-013a).

Delete the test branch afterwards.

| Check | Result |
|---|---|
| Dry run: no monitoring findings | 2026-10-22, `8612d8b`, from a temp clone on `pve` (the workflow can't be dispatched until it is on `main`): exit 0, **no monitoring pin** in the findings. Six service pins behind: `nextcloud_exporter_version` 0.9.0→0.9.2, `immich_version` v3.0.2→v3.3.5, `eurooffice_version` v9.3.2→v9.3.5, `llm_router_version` v1.83.3-stable→v1.106.2, `hermes_version` 0.11.3→0.12.3, `hermes_agent_version` v0.21.6→v0.22.4. Five pins `unchecked`. Without `GITHUB_TOKEN` every GitHub call returned HTTP 403 (anonymous rate limit on the shared IP) while endoflife.date worked; the workflow passes its token. |
| Lowered pin reported (SC-005) | |
| Error case fails the run | |
| First scheduled Monday run (date, outcome) | |
| 4 weeks without a report for a current pin (SC-006) | |
