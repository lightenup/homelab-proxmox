# Quickstart / validation: Hermes Agent behind Hermes (083)

Every Ansible run goes through the pipeline. The dev box has no SSH to the LXCs (082), so a
deploy runs `lxc-deploy-lab` → `lxc-promote-*` → `lxc-apply-prod`. Commands below that run *on the
Hermes LXC* are run from the PVE host (`pct exec <vmid> -- …`) or in a pipeline step.

A laptop run must pass `-e deploy_environment=lab|prod`. It defaults to `prod`, and a forgotten
flag on a LAB run is indistinguishable from PROD (research R-011). The pipeline always passes it.
Per backlog 067 the LAB stage deploys the real Hermes LXC, so LAB checks run on the production
machine, without the ntfy token.

Contracts: [agent-runtime.md](./contracts/agent-runtime.md),
[egress-allowlist.md](./contracts/egress-allowlist.md). Entities: [data-model.md](./data-model.md).

## Order of deploys

1. **llm-router** (new `hermes_agent` client, which mints the key) on LAB, then PROD.
2. **hermes** on LAB, then the checks Q-L1…Q-L7.
3. **hermes** on PROD, then the checks Q-P1…Q-P6.
4. **monitoring** on PROD only (`allow_override_failed_lab_gate=true`, backlog 072), for
   `HermesAgentCronStale`.

## Results so far

| Check | Date | Result |
|---|---|---|
| Q-L1 | 2026-10-17 | PASS — `v0.21.6`, Python 3.14.7, git 2.47.3 (pinned image run locally; the deploy does not exec these) |
| Q-L2 | 2026-10-17 | PASS — read-only config starts cleanly once `_config_version` is stamped; approvals `manual/deny/deny/300` loaded; the LAB deploy's health wait passed (run 39042576752) |
| Q-L6 | 2026-10-17 | PASS — LAB deploy run 39041787329: searxng, llm-router, MCP and reverse-proxy connected; Proxmox :8006, NAS :5000, router :80 and the LXC's :9100 refused |
| Q-L10 | 2026-10-17 | PASS — peak LXC used memory 2130 MB of 6144 MB (34.7 %) under concurrent agent turn + Whisper + SpeechT5; no resize. See research "Observed in the pinned image" |
| Q-L7 | 2026-10-17 | PASS — no token: subscribe 403 with 60 s steady-state retry (14 lines / 10 min); `--deliver ntfy` job ran but was refused (`ntfy HTTP 403`); nothing sent. LAB reached `ntfy.hus-sky.no`, so it was exercised, not skipped. Also found and disabled the gateway's restart notices (research R-006) |
| Q-P1 | 2026-10-17 | PASS — `hermes` PROD apply 39047151905 (promote 39046881454, `7369da3`): exposure gate, confinement assertion, health wait and all 8 egress probes green, `failed=0`. `llm-router` PROD apply 39046516486 first. |
| Q-P2 | 2026-10-17 | PASS — `NTFY_TOKEN` set and heartbeat mount present after the apply; subscribe refused with 403 on the 2/5/10/30/60 s backoff (6 lines in 2 min), no restart notice; `hermes send --to ntfy "083 path test"` returned `success: true`, ntfy message id `KtARnzvjTLVZ`. Phone receipt: confirmed by owner. `hermes cron list` is empty until US4 creates `heartbeat` (T038) |
| Q-P3 | 2026-10-17 | PASS — run 1 (16:03Z, 1m39s): `ok`, no delivery error, report of 5 promising MLX models (3305 bytes, under the 4096 truncation limit), clone at `d7f6a4a`, state in `$HERMES_HOME/state/model_scout.json`; run 2 (16:05Z): `silent (empty output)`, no delivery attempt. Phone: one report, nothing from run 2 (owner confirmed) |
| Q-P4 | PASS | 2026-10-17 16:16Z, Mac asleep (TCP 4443 closed on 3 tries; ICMP still answered). `hermes cron run model-scout` → "Ran now: succeeded", last run `ok`, output `silent (empty output)` — no model call needed (SC-002). Side observation (Q-L9): an agent chat in the same state fails after retries with HTTP 429 `No deployments available … cooldown_list=['balanced-local']` — the router has no fallback, so agent chat is unavailable while the Mac sleeps; scheduled script jobs are unaffected |
| Q-L8 | PASS | LAB deploy 39049924155 at `2994170`: no `heartbeat` job, no `/heartbeat` mount. Manual write to `/var/lib/hermes-agent-heartbeat/hermes_agent.prom` with a symlink in the textfile directory → `hermes_agent_heartbeat_timestamp_seconds` on `:9100/metrics`, `node_textfile_scrape_error 0` (node_exporter follows the symlink; no second directory needed). Files removed afterwards. Same deploy rendered `timezone: "Europe/Oslo"`. Side effect (backlog 067): the LAB stage also stripped `NTFY_TOKEN` and the heartbeat mount from the production machine until the next PROD apply |
| Q-P5 | 2026-10-17 | PASS — scheduler-driven (not manual) run of `fail.sh` (`exit 3`, `every 2m` instead of 15m, same scheduler path) at 16:08:05Z: `error: Script exited with code 3`, no "not delivered" warning; job removed at 16:08:23Z. Phone: one failure message naming `fail`, no repeats; report rendered as markdown (owner confirmed) |
| Note | | LAB deploys the production LXC (backlog 067), so these ran on the real machine, without the ntfy token |

## LAB checks (deploy gate, no phone traffic)

| # | Check | Expected | Covers |
|---|---|---|---|
| Q-L1 | Deploy passes; `docker exec -u hermes hermes_agent hermes --version`; `python3 --version`; `git --version` | pin matches; Python ≥ 3.11; git present | FR-001, FR-019 |
| Q-L2 | `config.yaml` is mounted read-only and the agent starts cleanly; `hermes config show` shows approvals `manual/deny/deny/300` | starts; values as rendered. If startup needs a writable config, switch to the R-004 fallback | FR-007 |
| Q-L3 | In Open WebUI pick `hermes-agent`: "show disk usage", "search the web for X", one MCP question | terminal, SearXNG and MCP all used; `hermes-balanced` answers exactly as before | US-2 #1–2, SC-005 |
| Q-L4 | In Open WebUI ask `hermes-agent` to run a flagged command (e.g. `rm -rf /opt/data/workspace/x`) | refused with a readable message in < 5 s | FR-007, SC-008 |
| Q-L5 | Create a throwaway agent job with a bad model alias, `--deliver local`; `hermes cron run`; inspect the CLI's `Ran now: …` line and `$HERMES_HOME/cron/output/<job-id>/` | failure recorded; learn whether agent-job failures go to `deliver` or need a separate target, and record it in research R-006 | FR-013 |
| Q-L6 | Egress probes from inside `hermes_agent` (the deploy runs them too) | gateway, MCP, Caddy:443 and SearXNG connect; Proxmox :8006, NAS, router, LXC :9100 fail | FR-008, SC-009 |
| Q-L7 | ntfy adapter with no token: `docker logs hermes_agent` after 10 min; one script job `--deliver ntfy` printing "lab" | refused subscription logged without a tight loop; publish refused (401/403); **nothing on the phone**. If LAB cannot reach `ntfy.hus-sky.no`, record "not exercised" and rely on Q-P2 | FR-012, FR-014 |
| Q-L8 | Heartbeat **not** present on LAB (`hermes cron list`); node_exporter symlink mechanism tested with a manual write | no `heartbeat` job; metric appears on `:9100/metrics` | FR-014, R-007 |
| Q-L9 | Inference host away: chat `hermes-agent` | readable error within seconds | US-2 #3 |
| Q-L10 | Memory: `docker stats` during a multi-tool agent turn plus a voice request in Open WebUI | LXC peak < 80 %; otherwise a Terraform memory bump before PROD | SC-011 |

## PROD checks

| # | Check | Expected | Covers |
|---|---|---|---|
| Q-P1 | Deploy passes, including the DNS exposure assertion and egress probes | green | FR-017, SC-009 |
| Q-P2 | `docker logs hermes_agent`; `hermes cron list` shows `heartbeat`; `docker exec -u hermes hermes_agent hermes send --to ntfy "083 path test"` | subscription refused (403) without a loop; **the phone shows the message**, which proves Hermes LXC → Caddy → ntfy | FR-012, 082 T026 gap |
| Q-P3 | Install the scout as owner content (below); `hermes cron run model-scout`; run again | first run: report on the phone; second: nothing | US-1, FR-019 |
| Q-P4 | Mac asleep, `hermes cron run model-scout` | runs and delivers (or silent if no news) | SC-002 |
| Q-P5 | Failing job: `echo 'exit 3' > scripts/fail.sh`, schedule `every 15m`, wait one tick, then remove it | phone shows a failure naming `fail` | SC-003 |
| Q-P6 | Manual router check: no port forward to `reverse_proxy_ip` (or any) on 80/443. Record: date, router, screenshot reference | recorded here | FR-017 |
| Q-P7 | `docker stop hermes_agent`, wait | `HermesAgentCronStale` within 1 h + 5 m, via Alertmanager | US-4, SC-004 |
| Q-P8 | Backup, then `hermes-restore-drill.yml` | `agent-manifest.sha256` verifies; `heartbeat` and `model-scout` are listed; one run succeeds; no phone message | US-5, SC-007 |
| Q-P9 | Open WebUI: Automations not offered; the gateway connection is still the default | as stated | FR-015, FR-006 |
| Q-P10 | After 2 weeks: gateway metrics for client `hermes` show no 429s caused by `hermes_agent`; no LAB-origin or duplicate scout messages | as stated | SC-006, SC-010 |

### Installing the model scout (owner content, not Ansible)

Source: `github.com/lightenup/local-llm` (≥ `d7f6a4a`), runbook `docs/SCOUT.md`.

```sh
docker exec -it -u hermes hermes_agent bash
cd /tmp && git clone https://github.com/lightenup/local-llm && \
  cp local-llm/scout/hermes-cron.sh "$HERMES_HOME/scripts/model-scout.sh"
hermes cron create "30 7 * * *" --no-agent --script model-scout.sh --deliver ntfy --name model-scout
hermes cron run model-scout
```

Installed on PROD 2026-10-17 from `local-llm` commit `d7f6a4a0822009c944e21921d822e6c58dc21dc4`
(script sha256 `c72f93c8…f6729`, fetched at that commit rather than `main`): job `model-scout`
(`2f76dd46f0cd`), `30 7 * * *`, `--no-agent --deliver ntfy`, no repository change. The agent's clock is
UTC unless `timezone` is set (research "Observed in the pinned image"), so this job's first schedule fired
at 07:30 UTC until the `timezone: Europe/Oslo` config deploys; re-save the schedule afterwards
(`hermes cron edit model-scout --schedule "30 7 * * *"`) so `next_run_at` is recomputed.

### Adding a second job (SC-001)

Repeat the block above with a different script and name. No repository change is needed.
