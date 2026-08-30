# Quickstart — LLM Router

**Feature**: `064-llm-router` | **Date**: 2026-08-29

Deploy, verify, and run the drills that make the acceptance criteria real rather than assumed.

## 0. Prerequisites

- **On the Mac**: Ollama running headless and keeping models resident (FR-016) —
  `OLLAMA_HOST=0.0.0.0 OLLAMA_KEEP_ALIVE=-1`, with the `hermes-fast` and `hermes-balanced` models
  pulled. Tailscale up; note the MagicDNS name.
- **In `ansible/group_vars/services/vault.yml`** (`ansible-vault edit`): `openrouter_api_key`,
  `anthropic_api_key`, `litellm_master_key`, `litellm_db_password`, `tailscale_authkey` (ephemeral +
  tagged), and one key per client consumer.
- **PVE headroom**: ~4 GB RAM, ~16 GB disk.
- **Stack shape**: three containers — `litellm`, `postgres`, `tailscale` (userspace sidecar). No Redis
  (FR-014 requires it only above one worker).

## 1. Deploy

Identical from CI and laptop (Constitution V):

```bash
# laptop
scripts/lab/pve-service-deploy plan  --service llm-router --env prod
scripts/lab/pve-service-deploy apply --service llm-router --env prod
```

or the `lxc-deploy-lab` → `lxc-promote-lab` → `lxc-promote-prod` workflow chain with
`service: llm-router`.

Expect: LXC created at `192.168.1.220`, `litellm`/`postgres`/`tailscale` containers `Up (healthy)`,
post-apply healthcheck green with evidence.

## 2. Verify the deploy (US-2 / SC-004)

```bash
curl -s http://192.168.1.220:4000/health/readiness          # {"status":"healthy","db":"connected"}
scripts/healthcheck/llm-router.sh --profile lan
scripts/lab/pve-service-deploy apply --service llm-router --env prod   # re-run: idempotent, pin unchanged
```

## 3. Confirm the metric surface (research D-105 — resolved, but confirm the live path)

The licensing question is resolved: the metrics are free-tier, confirmed by running the exact pinned
image locally during implementation. `/metrics` is also open (no bearer token) by design — see
D-105 for why. This step just confirms the real deploy behaves the same as the local test:

```bash
curl -s http://192.168.1.220:4000/metrics/ \
  | grep -E 'litellm_spend_metric_total|litellm_deployment_state'
```

Non-empty output is the expected, already-verified outcome. Empty output here would mean something
about the LAB deploy differs from the tested config — check that `litellm_settings.callbacks:
[prometheus]` rendered into `config.yaml` (T017/T044 in tasks.md).

## 4. Happy path (US-1 / SC-002)

```bash
for alias in hermes-fast hermes-balanced hermes-deep; do
  curl -s http://192.168.1.220:4000/v1/chat/completions \
    -H "Authorization: Bearer $CLIENT_KEY" -H 'Content-Type: application/json' \
    -d "{\"model\":\"$alias\",\"messages\":[{\"role\":\"user\",\"content\":\"say hi\"}]}"
done
```

Then confirm in metrics that `hermes-fast` was served by the **local** deployment id — SC-002 is
about attribution, not just about getting an answer.

## 5. The downed-backend drill (SC-008) — the acceptance that matters

Do not skip this and do not infer it from config review. It is the drill that exercises the reported
LiteLLM routing-pool defect against the exact pinned version.

```bash
# on the Mac
pkill ollama

# from a client — expect a valid completion, no error, no long hang
time curl -s http://192.168.1.220:4000/v1/chat/completions \
  -H "Authorization: Bearer $CLIENT_KEY" -H 'Content-Type: application/json' \
  -d '{"model":"hermes-fast","messages":[{"role":"user","content":"say hi"}]}'
```

Pass criteria:
- A valid completion returns, served by the standby (check the deployment id in metrics).
- Latency shows **no** full timeout on the dead deployment — it was skipped, not attempted (AS-1.3).
- `LlmRouterLocalTierDown` fires as **info**, not critical.

Repeat for `hermes-balanced` and `hermes-deep` — SC-001 covers every alias, not just the first.

Then restart Ollama, wait one health interval (≤60 s), repeat: served locally again, **no operator
action**.

### 5b. Power the Mac off (SC-001) — a different failure mode

Stopping the daemon and removing the machine are not the same test. A stopped daemon refuses the
connection immediately; a Mac that has left the tailnet has no peer to refuse, so the request can hang
until the timeout — the false-fallback risk research D-102 raises. Power the Mac off (or `tailscale
down`) and repeat all three aliases. Pass criteria: every alias answers, and none exceeds the request
timeout.

## 6. Context escalation (SC-009)

Send an input longer than `hermes-fast`'s context window. Expect an answer from a larger tier — not a
400 context-length error.

## 7. Budgets (SC-010, SC-012)

```bash
# drive one client past its own cap
# expect: that client refused with a clear error; OTHER clients still served
```

Confirm the per-client refusal is distinguishable from a gateway-cap refusal, and that the breach is
attributed to the right key in monitoring.

## 7b. Total-failure detection (SC-013)

The trap the spec names first: the gateway is alive, the database is fine, and every backend is dead.
`/health/readiness` still returns 200, and the failure-rate alert stays silent because nobody is
calling.

```bash
# break every backend (revoke keys or block egress), send NO client traffic, then wait
# expect: LlmRouterCanaryFailing fires within one canary interval
```

Pass criteria: an alert fires with no client traffic flowing. A green dashboard here is the failure.

## 8. Blast radius (SC-006, SC-007)

```bash
git grep -nE 'sk-|OPENROUTER_API_KEY=|ANTHROPIC_API_KEY=' -- ':!specs' ':!docs'   # expect no hits
curl --max-time 5 http://192.168.1.220:4000/health/readiness   # from off-LAN/off-tailnet: fails
                                                               # from a LAN host: SUCCEEDS, by design
```

Confirm no Caddy route exists, no public DNS name, no landing-page tile, and that the rendered
`config.yaml` on the LXC contains only `os.environ/...` indirection — no literal keys. Confirm no
Anthropic subscription or OAuth credential is present anywhere (FR-007).

**LAN reachability is expected**, not a finding — FR-008 requires no *public* reachability, and any
LAN host can reach the gateway. Access is gated by per-client keys, not by network position (research
D-108).

## 9. Retier drill (SC-003)

Change one `deployments` entry in `ansible/group_vars/services/vars.yml`, redeploy, confirm the new
deployment serves the alias — and confirm **no client changed**. This is the rehearsal for the Mac's
32 GB → 128 GB upgrade; if it needs a template edit, [contracts/alias-mapping.md](./contracts/alias-mapping.md)
has been violated.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Every client gets an auth failure | Postgres down or unmigrated — `/health/readiness` should be 503 (D-103) |
| `hermes-fast` silently metered while the Mac is up | Cold-load timeout, or the tailnet proxy path is broken (D-102). Check `OLLAMA_KEEP_ALIVE` first, then `HTTP_PROXY` reachability from the litellm container |
| Mac unreachable from the LXC | Tailscale sidecar not authenticated, or `NO_PROXY` misconfigured so proxy traffic loops |
| Scrape 401s | `/metrics` bearer token — see the scrape-config caveat in [contracts/monitoring.md](./contracts/monitoring.md) |
| Contract present but no Grafana data | Host missing from `ansible/inventories/prod/hosts.yml` (D-107) |
