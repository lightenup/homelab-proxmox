# Log Aggregation Runbook

**Feature**: [092-log-aggregation](../../../specs/092-log-aggregation/spec.md)
**Purpose**: operate the log pipeline — where things are, how to purge a leaked credential,
what to do during a store or relay outage, and how to tune and enable a per-service error rule.

## 1. Data flow

```
collectors (Alloy, every production host + pve)
  -> redact on the host (8 credential patterns)
  -> :3101 relay (monitoring host's own Alloy, push-only)
  -> host-local Loki (127.0.0.1:3100 only)
  -> Grafana (search) and the local ruler (-> Alertmanager -> Pushover/ntfy)
```

- Every host ships its journal, Docker container output (where applicable) and any declared
  files, labelled `env`, `host`, `service`, `source` and (per source) `ident`/`unit`,
  `container`, or `filename`. Only pve's kernel OOM lines carry structured metadata (`lxc`).
- Collectors retry pushing forever (`max_backoff_retries = 0`); nothing is dropped unless an
  outage outlasts the host's own on-disk buffer (section 4) or Loki's 7-day backfill limit.
- Retention is 720 h (30 days). The `loki_data` volume is **not backed up** (FR-014).

## 2. Where things are

| What | Where |
|---|---|
| Store config | `/opt/monitoring/loki/loki.yaml` (`loki.yaml.j2`), port `127.0.0.1:3100` |
| Store rules (Loki ruler) | `/opt/monitoring/loki/rules/fake/log_alerts.yaml` (`log_alerts.yaml.j2`) |
| Pipeline self-monitoring (Prometheus) | `prometheus/alerts/log_pipeline_alerts.yml` (`log_pipeline_alerts.yml.j2`) |
| Collector config | `/etc/alloy/config.alloy` on every production host (`config.alloy.j2`) |
| Collector memory limits | `/etc/systemd/system/alloy.service.d/override.conf` |
| Redaction patterns | `ansible/roles/alloy/defaults/main.yml` → `alloy_redaction_patterns` |
| Login allow-list | `ansible/group_vars/monitoring/vars.yml` → `ssh_login_allowlist`, `ssh_sudo_expected` |
| Per-service error rules | `ansible/host_vars/<service>.yml` → `monitoring_contract.log_alert_rules` |
| Grafana data source | `Loki`, uid `loki`, `http://loki:3100` |
| `lokitool` (deploy-time validator) | `/usr/local/bin/lokitool` on the monitoring host |

Ports: store `3100` (loopback only), relay `3101` (LAN push-only), collector HTTP/metrics
`12345` (`alloy_http_port`, scraped by Prometheus' `alloy` job).

## 3. Leaked-credential procedure (FR-016, SC-008)

If a secret reaches the store (a new format the 8 patterns miss, or a pattern that fails to
match), quickstart §7 is the drill; this is the same procedure for a real incident:

1. **Rotate** the credential at its issuer first. Do this before anything else.
2. **Delete** the lines, from the monitoring host:

   ```bash
   curl -s -X POST -G http://127.0.0.1:3100/loki/api/v1/delete \
     --data-urlencode 'query={env="prod"} |= "<the leaked substring>"' \
     --data-urlencode start=<unix seconds before first occurrence>
   curl -s http://127.0.0.1:3100/loki/api/v1/delete | jq '.[-1].status'
   ```

   Matching lines disappear from query results as soon as the request is **received**.
   Physical removal happens after `delete_request_cancel_period` (10 minutes) and the next
   compaction (research R2).
3. **Extend** the redaction patterns: add an entry to `alloy_redaction_patterns`
   (`ansible/roles/alloy/defaults/main.yml`) and a corresponding positive line to
   `python/tests/guardrails/fixtures/redaction_corpus.txt`. Run
   `bash scripts/ci/python-tests.sh` and deploy the collector role so the new pattern is live
   before the same credential format can leak again.

## 4. Store or relay outage

Both the store and the relay run on the monitoring host's own Alloy and Loki, so an outage of
one looks like an outage of both from every other collector's point of view (research R4).

- Every collector keeps its read position (journal cursor, file offset, Docker since-time) and
  retries without limit (`max_backoff_retries = 0`). Lines queue on the **source host's own
  disk** — Docker's json-file logs and the systemd journal — not in Alloy's memory.
- The binding limit is Loki's `reject_old_samples_max_age` of 168 h (7 days): an outage longer
  than that loses the oldest lines once the store comes back, because it refuses to accept
  samples older than its own cutoff.
- `LogCollectorDown` (10m) flags one collector being unreachable. `ServiceDown{job="loki"}`
  (the existing critical rule) flags the store itself. `LogHostSilent` (2h) flags a collector
  that is up but has shipped nothing — most often a missing group membership (research R5).
- No action is needed to "flush" anything: once the store or relay is back, backlogged lines
  arrive with their original timestamps (verify with the quickstart §10 drill).

## 5. Tuning and enabling a per-service error rule (SC-004)

The five per-service rules (`llm-router`, `hermes`, `nextcloud`, `immich`, `ntfy`) ship
`enabled: false` until a 7-day baseline passes (quickstart §6):

1. Run the rule's count expression (without the trailing comparison) over the last 7 days at
   `step=15m` against the store, and take the maximum 15-minute count.
2. Set the rule's threshold to `max(5, 3 × max_15m)` in its `expr`.
3. Set `enabled: true` and add `baseline: {from, to, max_15m}` to the rule in
   `ansible/host_vars/<service>.yml`, removing `disabled_reason`.
4. Redeploy monitoring. Confirm `LogRulesNotLoaded` stays quiet (its expected count rises with
   the newly-enabled rule).
5. Inject an error burst into that service only and confirm only its alert fires.

A service whose errors are too noisy at the computed threshold stays `enabled: false`, with
`disabled_reason` updated to record the actual finding.

## 6. Never `lokitool rules lint`

`lokitool rules lint` (without `--dry-run`) rewrites the rule file in place and adds a
top-level `namespace:` key that the local ruler rejects outright — stopping **every** log rule,
not just the one being edited (research R10). Only `lokitool rules check <file>` is used, both
locally (quickstart §1) and at deploy (`validate_alerts.yml`, before anything restarts).

## 7. Replays: `LogReplayRejected`

Alloy's Docker source can lose a container's read position and re-send that container's
whole log. Loki then rejects every line more than an hour behind as `too_far_behind`. Those
lines are duplicates of lines Loki already stores; nothing is lost. RCA 2026-10-27 found two
triggers:

| Trigger | Status |
|---|---|
| The container came back on another bridge IP (e.g. a compose stack restarted in place), so the position key changed | Fixed: `discovery.relabel "docker"` drops the address, network and port labels from the key (`config.alloy.j2`, `test_alloy_position_key.py`) |
| The container was stopped across a 15 s discovery refresh (LXC reboot, Docker restart, `docker stop` + `start`), so the position was deleted | Upstream [grafana/alloy#7036](https://github.com/grafana/alloy/issues/7036), open. Bump `alloy_version` when it ships |

A replay raises `LogReplayRejected` (info, silent). It does not raise `LogLinesDiscarded`, and
`LogCollectorDropping` ignores drops in the same 15 minutes. If `too_far_behind` goes on for an
hour, `LogLinesDiscardedSustained` fires: that is not a replay but something like a host clock
running behind.

## 8. Accepted risks

- **Docker socket access**: the collector reads container logs over `/var/run/docker.sock` on
  every Docker host, which makes it root-equivalent there. Its only inbound surface is the
  read-mostly config UI on `:12345`, and the rendered config holds no secrets (FR-010).
- **Unauthenticated push on `:3101`**: any LAN device can push lines to the relay, which could
  inject a fake log line or consume ingestion limits. It cannot read, query or delete anything.
  Bounded by Loki's ingestion limits and `LogCollectorDropping`/`LogLinesDiscarded` (research
  R4, MR-004).
- **Password SSH on pve**: pve keeps `PasswordAuthentication yes` (owner decision, research
  R3/R13); every password login there raises `SshLoginNotAllowed` with `method=password`. Every
  LXC has password authentication disabled (FR-015).
