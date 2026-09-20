# Quickstart — LLM Router

**Feature**: `064-llm-router` | **Written**: 2026-08-29 | **Rewritten against the live deploy**: 2026-09-19

Deploy, verify, and run the drills that make the acceptance criteria real rather than assumed.

> **This file was rewritten, not annotated.** Unlike [`tasks.md`](./tasks.md), which is a ledger and
> keeps its history, this is a procedure people *run* — and it described Ollama on `:11434`, a
> tailscaled sidecar, MagicDNS names and metered fallbacks, none of which exist. A stale ledger
> misleads a reader; a stale procedure wastes an afternoon. Every command below was executed against
> the live gateway on 2026-09-19 and the outputs are the ones observed.

## 0. Prerequisites

**On the Mac** (`XMJDVVW39Y2T`, `192.168.1.177`) — four processes, all session-scoped.
The whole arrangement, and what breaks how, is [`mac-side.md`](./mac-side.md):

| | |
|---|---|
| **oMLX** | running, bound to `127.0.0.1:8000`. **Do not expose it** — only the Mac's LiteLLM talks to it (FR-016) |
| **The Mac's LiteLLM** | `docker compose` at `~/Development/private/local-llm/proxy`, bound to `127.0.0.1:4000` — loopback only; the terminator is what faces the LAN |
| **The mDNS announcer** | `launchctl list \| grep hermes-mdns` — without it the gateway cannot resolve the Mac at all ([`mac-mdns-announcer/`](./mac-mdns-announcer/)) |
| **The TLS terminator** | `launchctl list \| grep hermes-tls` — the gateway reaches the Mac over TLS on `:4443`; without it there is no path at all ([`mac-tls-terminator/`](./mac-tls-terminator/)) |

None of these auto-start. Docker Desktop is not a login item, oMLX is a GUI app, and the announcer
and terminator are LaunchAgents — so all four die with the login session. That is deliberate: when the Mac cannot
serve, the name stops resolving and the gateway fails clean rather than pointing at a dead host.

```bash
# on the Mac, after any restart
open -a Docker && open -a oMLX
./specs/064-llm-router/mac-checks/verify-omlx-residency.sh   # PASS — every aliased model is pinned
lsof -nP -iTCP:4443 -sTCP:LISTEN     # terminator, *:4443 — the only LAN listener
lsof -nP -iTCP:4000 -sTCP:LISTEN     # LiteLLM, 127.0.0.1 ONLY
lsof -nP -iTCP:8000 -sTCP:LISTEN     # oMLX,    127.0.0.1 ONLY
```

**In the vault** (`ansible-vault edit ansible/group_vars/services/vault.yml`) — five keys:
`litellm_master_key`, `llm_router_client_hermes_key`, `llm_router_canary_key`, `mac_litellm_key`,
`litellm_db_password`. The first four need an `sk-` prefix (LiteLLM rejects keys without it);
`litellm_db_password` must be **URL-safe** — generate it with `openssl rand -hex 24`, never
`base64`, which emits `/` and breaks `DATABASE_URL` parsing. Preflight asserts both.

There is no `openrouter_api_key`, `anthropic_api_key`, `omlx_api_key` or `tailscale_authkey` — the
metered tiers and the sidecar are gone.

**PVE headroom**: ~4 GB RAM, ~16 GB disk. **Stack shape**: two containers, `litellm` and `postgres`.
No Redis (FR-014 requires it only above one worker).

## 0b. Two things about the environment that will otherwise confuse you

**LAB and PROD are the same address space.** `lab.tfvars.template` and `prod.tfvars.template` are
byte-identical for this service, so `lxc-deploy-lab` builds the real LXC at `192.168.1.220` on
`pve`/`vmbr0`. "lab" is a gating stage, not an environment. The *inventories* differ completely,
which matters only for the monitoring deploy (§10).

**The Mac announces mDNS but never answers a query.** Stealth mode is MDM-enforced. A resolver that
overhears an announcement caches it and works; a cold resolver never learns the name. Hence the
announcer, and hence the role resolving the name on the LXC and passing it to the container as
`extra_hosts` — the container cannot resolve `.local` by any container-side setting, and
`network_mode: host` does not help (it shares the network namespace, not the filesystem).

## 1. Deploy

```bash
gh workflow run lxc-deploy-lab.yml --ref <branch> -f service=llm-router -f apply=false   # plan
gh workflow run lxc-deploy-lab.yml --ref <branch> -f service=llm-router -f apply=true    # apply
```

**Pass `--ref`.** Without it `gh` dispatches against the default branch and silently deploys
something other than what you are testing.

Expect: LXC at `192.168.1.220`, `litellm` and `postgres` both `Up (healthy)`, ansible
`failed=0`, post-apply healthcheck PASS, evidence pack verified.

## 2. Verify the deploy (US-2 / SC-004)

```bash
curl -s http://192.168.1.220:4000/health/readiness    # {"status":"healthy","db":"connected",...}
```

Re-run the apply to confirm idempotency. This is worth doing rather than assuming: it is what caught
the virtual-key provisioning bug, where the second apply died on duplicate key aliases because the
idempotency lookup could never work.

The `llm-router.sh` healthcheck **cannot be run ad hoc off-box** — it resolves hosts from
`inventories/generated/hosts.yml`, which only exists on `pve`. The pipeline runs it as the
post-apply gate; read its result there.

## 3. Confirm the metric surface (research D-105)

```bash
curl -s http://192.168.1.220:4000/metrics/ | grep -E 'litellm_spend_metric_total|litellm_deployment_state'
```

Free-tier and open by design — `require_auth_for_metrics_endpoint: true` **hangs indefinitely**
against this pinned version, so the endpoint is left at LiteLLM's own default. Empty output means
`litellm_settings.callbacks: [prometheus]` did not render.

## 4. Happy path (US-1 / SC-002)

```bash
for alias in hermes-fast hermes-balanced hermes-deep; do
  curl -s http://192.168.1.220:4000/v1/chat/completions \
    -H "Authorization: Bearer $CLIENT_KEY" -H 'Content-Type: application/json' \
    -d "{\"model\":\"$alias\",\"messages\":[{\"role\":\"user\",\"content\":\"say hi\"}]}"
done
```

Observed 2026-09-19: `hermes-fast` 2.0s, `hermes-balanced` 1.3s, `hermes-deep` 2.6s.

Provider model IDs must be **refused**, not served — client keys are scoped to the alias names:

```bash
curl -s ... -d '{"model":"openai/fast",...}'    # expect 401, not a completion
```

That is not hypothetical: `openai/fast` returned a real completion until the keys were scoped,
bypassing the alias and the context window and fallback behaviour it declares.

## 5. The downed-backend drill (SC-008) — the acceptance that matters

**The expectation is inverted from what this file used to say.** SC-001 is withdrawn: there is no
standby, so the pass criterion is a *clean failure*, not a completion.

```bash
# on the Mac
cd ~/Development/private/local-llm/proxy && docker compose stop litellm

# from a client — expect a prompt, legible error; NEVER a hang
time curl -s http://192.168.1.220:4000/v1/chat/completions \
  -H "Authorization: Bearer $CLIENT_KEY" -H 'Content-Type: application/json' \
  -d '{"model":"hermes-fast","messages":[{"role":"user","content":"say hi"}]}'
```

Pass criteria, all measured on 2026-09-19:

| | observed |
|---|---|
| first request after the backend dies | HTTP 500 in ~135s, naming the model group |
| every request after that, for `cooldown_time` | **HTTP 429 in ~0.03s**, "No deployments available… Try again in 60 seconds" |
| recovery once the Mac returns | **51s**, no operator action |
| a hang | **the only real failure** |

That first ~135s is the cost of discovering a blackhole and is irreducible without capping
`llm_router_request_timeout` below a legitimate generation.

**Stopping the server and powering the Mac off are the same test here**, contrary to what this file
used to claim. Stealth mode DROPs the SYN rather than refusing it, so a stopped container blackholes
exactly like an absent host — `pve` refuses in 0.001s, the Mac hangs the full window. To reproduce
without touching the Mac, blackhole the path from the LXC instead:

```bash
ssh root@192.168.1.220 'iptables -I DOCKER-USER -d 192.168.1.177 -p tcp --dport 4000 -j DROP'
# ... run the drill ...
ssh root@192.168.1.220 'iptables -D DOCKER-USER -d 192.168.1.177 -p tcp --dport 4000 -j DROP'
```

## 6. Context escalation (SC-009)

**The escalation happens one hop down**, not here: both `fallback_to` and
`context_window_fallback_to` are null on this gateway, and the Mac's own
`context_window_fallbacks` escalate `reasoner → Qwen3.8-27B-8bit:qwen-long`. The trade is
real — the fallback profile runs thinking OFF at temp 0.3, so crossing 131k buys window at
the cost of reasoning depth.

**The ~300s ceiling that used to block this is gone** (2026-09-20). The local-tier leg runs
over TLS, which holds 1500s and 1800s of complete silence; a cold 108k-token prompt that
died at 417s over plaintext now completes in ~396s. Per-deployment timeouts are 1200s, so
the operating budget is 20 minutes.

Prefill is superlinear, so plan in *time*, not tokens:

```
 24k tokens ->  41s      73k tokens -> 105s
 48k tokens ->  73s     108k tokens -> 397-690s
```

**Exercised 2026-09-20 and it works**: a 170,305-token prompt was served in 901.8s, so the
escalation to `qwen-long` fires and `hermes-deep`'s declared 262144 is honest.

**But avoid the band just above 131,072.** A 132,658-token prompt is *rejected* in under a
second — LiteLLM's pre-call token estimate undercounts against oMLX's tokenizer, still
picks `reasoner`, and oMLX refuses it. Stay clearly below 131k or clearly above ~140k until
backlog 070 is resolved.

## 7. Budgets and rate limits (SC-010)

**The spend half is inert.** Local deployments carry no per-token pricing, so `max_budget` reads 0.0
against any cap regardless of traffic and SC-012 is not verifiable. Budgets stay declared so a priced
tier re-arms them, but the runaway-loop guard is now **rate limiting**:

```bash
# drive one client past its rpm_limit
# expect: that client refused with a clear error; OTHER clients still served
```

## 7b. Total-failure detection (SC-013)

The trap the spec names first: the gateway is alive, the database is fine, every backend is dead,
`/health/readiness` still returns 200, and the failure-rate alert stays silent because nobody is
calling. Break every backend, send **no** client traffic, and confirm `LlmRouterCanaryFailing` fires
within one canary interval. A green dashboard here is the failure.

**Exercised, twice.** First 2026-09-20 (T051), then re-run the same day after the local-tier leg
moved to TLS and after the `072` monitoring restore, because both changed the path this depends on:

```bash
launchctl unload ~/Library/LaunchAgents/no.hus-sky.hermes-tls-terminator.plist   # kill the only path to the Mac
#   /health/readiness -> 200          <- the trap, still green
#   canary -> 0, no client traffic sent
#   LlmRouterCanaryFailing -> firing
launchctl load ~/Library/LaunchAgents/no.hus-sky.hermes-tls-terminator.plist
#   canary -> 1, alert -> inactive, no operator action
```

Two things worth knowing before you run it:

- **Query the rule, not just the expression.** `llm_router_canary_success == 0` returns a result as
  soon as the metric is scraped, but the *rule* only transitions on its group interval (30s). Check
  `/api/v1/rules` for `state: firing`, or you will conclude the alert is broken when it is merely
  a few seconds behind.
- **The canary's own failure cools the deployment down**, so recovery needs one run after the
  cooldown lapses.

## 8. Blast radius (SC-006, SC-007, FR-008)

```bash
git grep -nE 'sk-|OPENROUTER_API_KEY=|ANTHROPIC_API_KEY=' -- ':!specs' ':!docs'   # expect no hits
curl -sk --max-time 5 https://llm-router.hus-sky.no/    # expect no such host — there is no route
```

Confirm the rendered `config.yaml` on the LXC contains only `os.environ/…` indirection.

**There IS a landing-page tile now, and that is deliberate** — FR-008 was amended. The card on
`hus-sky.no` links to the Grafana dashboard, not to the gateway; it creates no vhost, no DNS name and
no route. Verify by checking the page contains no `llm-router.hus-sky.no` and no internal IP.

**LAN reachability is expected**, not a finding — FR-008 forbids *public* reachability. Access is
gated by per-client keys, not by network position (research D-108).

## 9. Retier drill (SC-003)

Change one `deployments` entry in `ansible/group_vars/services/vars.yml`, redeploy, confirm the new
deployment serves the alias — and that **no client changed**. If it needs a template edit,
[contracts/alias-mapping.md](./contracts/alias-mapping.md) has been violated.

**Exercised 2026-09-20.** Repointed `hermes-fast` from `openai/fast` to `openai/coder`:

```
git diff --stat   ->  ansible/group_vars/services/vars.yml | 3 ++-      <- one file, no template
on the LXC        ->  model_name: hermes-fast / model: openai/coder     <- the retier took
canary            ->  llm_router_canary_success{alias="hermes-fast"} 1  <- unchanged client, still served
```

Then reverted and re-confirmed. The `git diff --stat` is the real assertion here — SC-003 is a claim
about *where the change lands*, not about whether the alias still answers.

## 10. Monitoring

Contracts render **only on the prod path**. `pve-service-deploy` layers
`inventories/${ENVIRONMENT}/hosts.yml` for the monitoring service, and the lab inventory holds one
host and no services — so a lab-path monitoring deploy silently renders nothing:

```bash
gh workflow run lxc-lifecycle.yml --ref <branch> \
  -f service=monitoring -f action=change -f environment=prod -f confirm_apply_prod=deploy-prod
```

Expect on `192.168.1.214`: an `llm-router` scrape job, an `llm-router-readiness` blackbox job, **six**
`LlmRouter*` alert rules (the sixth, `LlmRouterGatewayRateCapBinding`, arrived with backlog `071`),
and `llm-router.json` in Grafana's dashboards.

> **The warning above is now enforced in code, because writing it down was not enough.** On
> 2026-09-20 a lab-path monitoring deploy did exactly what this section describes and wiped the live
> config — 16 scrape jobs and 5 alert groups — despite the behaviour being documented here *and* in
> `tasks.md` T051. Two guards now refuse it: `pve-service-deploy` enumerates the layered inventory
> and stops unless the `services` group is populated, and the `monitoring_stack` role asserts at
> least one host declares `monitoring_contract.enabled` before anything renders. See backlog
> [`072`](../../docs/backlog/072-lab-monitoring-deploy-wipes-prod.md).

Verified 2026-09-20 after the restore: 16 scrape jobs, 28 targets, 0 unhealthy, 8 rule groups, all
six `LlmRouter*` rules `inactive`.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Every alias returns HTTP 500 "Connection error" | The container cannot resolve the Mac. Check `extra_hosts` in `/opt/llm-router/docker-compose.yml`, then `getent hosts xmjdvvw39y2t.local` on the LXC, then the announcer on the Mac |
| `getent` works on the LXC but not from a cold resolver | Expected — the Mac only announces. If it fails after 45s, the announcer is dead |
| Every alias hangs rather than erroring | `timeout` missing from the rendered `config.yaml`, or `num_retries` multiplying it |
| A dead backend costs full latency on *every* request | The deployment is not being ejected — check `allowed_fails: 0`; any higher value is unreachable when a failure takes longer than `cooldown_time` |
| Prisma `P1013: invalid port number` | `litellm_db_password` contains a `/`. Rotate to hex **and** wipe `/opt/llm-router-data/postgres`, since initdb only applies the password on first start |
| Second apply fails on duplicate key aliases | The `/key/list` idempotency lookup regressed — `/key/info?key_alias=` cannot answer this |
| Every client gets an auth failure | Postgres down or unmigrated — `/health/readiness` should be 503 (D-103) |
| Contract present but no Grafana data | The monitoring deploy ran on the lab path, or the host is missing from `ansible/inventories/prod/hosts.yml` (D-107) |
| A long request from a client **on the Mac** fails around 400s | Expected — the Mac's own outbound plaintext is subject to the same closer. Tooling on the Mac uses `http://localhost:4000` (loopback, unaffected); only a harness pointed at the gateway over the LAN hits this. Homelab-internal clients are fine |
| A PROD lifecycle run reports failure after a clean apply | Was the `ops_cli` forwarded-args bug; if it recurs, check the post-apply verification steps rather than the apply |
