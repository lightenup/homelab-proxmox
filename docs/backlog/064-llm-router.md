# Feature Specification: LLM Router (gateway LXC)

**Feature Branch**: `064-llm-router`
**Created**: 2026-08-29
**Status**: Spec, plan, tasks and implementation complete on branch `064-llm-router` — see
`specs/064-llm-router/`. **Not yet deployed**: registration, Terraform module, Ansible role,
monitoring and alerting are all built and validated (syntax/lint/render/live-image testing), but no
LXC exists yet in LAB or PROD. Remaining work is live deployment and the acceptance drills
(`specs/064-llm-router/tasks.md` T009, T023–T043, T050–T057, T062–T064) plus vault secrets, which
need real credentials only the account owner holds. Independent; no blocking dependency.
**Input**: Deploy a self-hosted LLM gateway on its own gated LXC that exposes **one
OpenAI-compatible endpoint** to homelab clients, addressed by **intent aliases** (`hermes-fast`,
`hermes-balanced`, `hermes-deep`) rather than provider model IDs. Backends: a Mac on the tailnet
running Ollama/LM Studio (free, private, **intermittently available**), a hosted aggregator
(OpenRouter) and an Anthropic API key. Health-check-driven routing plus ordered fallbacks make the
Mac's availability invisible to callers. Tailnet-only; observable in the existing
Prometheus/Grafana stack.

## Summary

The homelab has no inference capacity of its own — the PVE node is an i3-12100 with a UHD 730 iGPU,
so local models are not viable on the hypervisor. The Mac is the only real local inference box, and
it comes and goes. That single fact shapes the whole design: **the local tier must be a discount
that is usually available, never a dependency**.

A gateway LXC solves three problems at once. It gives every homelab client one URL and one key
instead of N provider SDKs; it turns "the Mac is asleep" from an application concern into a config
concern (background health checks pull a failing deployment from the pool *before* a request lands
on it, and an ordered fallback carries the request); and it puts spend and routing behaviour into
the Prometheus stack that already exists.

The load-bearing design choice is **indirection on the alias**. Clients ask for an intent, never a
model. The alias→deployment mapping lives in `group_vars` as data. This matters more than it
normally would because the hardware is about to change: the Mac is **32 GB today, 128 GB soon**,
which moves `hermes-balanced` from a 14–32B model to a 70B-class one and may pull work back from
the metered tier entirely. With the indirection, that upgrade is a one-line edit and a deploy. Without
it, it is a change to every client.

This item covers **the router only**. Hermes itself, and the Claude-subscription "plan door", are
[`065-hermes-service`](./065-hermes-service.md).

## User Scenarios & Testing

### User Story 1 - A client gets an answer regardless of the Mac's state (P1)

A homelab client asks the gateway for `hermes-fast` and receives a completion whether the Mac is
awake, asleep, or off the tailnet entirely.

**Acceptance**:
1. **Given** the Mac is serving, **When** a client requests `hermes-fast`, **Then** the request is
   served by the local deployment at zero marginal cost, and the serving deployment is identifiable
   from metrics.
2. **Given** the Mac is powered off, **When** the same request is made, **Then** it is served by the
   standby deployment with no client-visible error and no unbounded retry.
3. **Given** the Mac fails its health check, **When** the next request arrives, **Then** it is
   routed to the standby *without* first attempting and timing out on the dead deployment.
4. **Given** the Mac comes back, **When** its health check next passes, **Then** it re-enters the
   pool automatically with no operator action.

### User Story 2 - Deploy comes up healthy through the gated pipeline (P1)

**Acceptance**:
1. **Given** the pinned image tag, **When** the apply runs, **Then** the container is `Up (healthy)`
   and the gateway's readiness endpoint returns 200.
2. **Given** a re-run, **When** the apply repeats, **Then** it is idempotent and the version stays
   pinned.
3. **Given** the post-apply healthcheck, **When** the pipeline runs it, **Then** it passes and
   writes evidence.

### User Story 3 - Retiering is a config edit, not a code change (P1)

The Mac goes from 32 GB to 128 GB and `hermes-balanced` should move from a hosted model to a large
local one.

**Acceptance**:
1. **Given** the new model is pulled on the Mac, **When** the alias mapping in `group_vars` is
   changed and the service is deployed, **Then** subsequent `hermes-balanced` requests are served
   locally.
2. **Given** that change, **When** clients are inspected, **Then** **no client configuration or code
   changed** — clients still address the same alias.

### User Story 4 - Routing and spend are observable (P2)

**Acceptance**:
1. **Given** the monitoring contract, **When** Prometheus scrapes, **Then** per-alias request counts
   and per-deployment success/failure are visible in Grafana.
2. **Given** the Mac is unreachable, **When** the blackbox probe runs, **Then** "local tier down" is
   an explicit signal rather than something inferred later from a metered bill.
3. **Given** metered usage, **When** spend accrues, **Then** it is visible per alias.

### Edge Cases

- **Gateway liveness green while a backend is broken** — the documented trap: the process is alive,
  every request fails. Readiness *and* a backend probe MUST both be monitored, not just the former.
- **Mac awake but the model is not loaded** — LM Studio JIT-loads on first request, so a cold call
  can take tens of seconds and trip a naive timeout into a false fallback. Timeouts MUST account for
  cold load, or a keep-loaded policy MUST be set on the Mac.
- **Input too long for the small model** — MUST escalate a tier rather than returning a context-length
  error to the caller.
- **All deployments in cooldown** — MUST fail fast with a clear error; MUST NOT hang or retry forever.
- **Health checks cost money** — probing metered deployments on a short interval bills real tokens.
  Probe cadence/mode MUST be chosen so background checks are not a line item.
- **The router holds every provider key you own** — it is the highest-value credential target in the
  homelab. Tailnet-only, vault-sourced, no public route.
- **Runaway client loop** — an agent in a retry loop against a metered alias can bill unbounded.
  A per-client budget/limit is required, not optional.
- **`latest` tag drift** — MUST pin, and record the pin centrally.
- **Unauthenticated backend on the LAN** — `--host 0.0.0.0` on Ollama/LM Studio has no auth. The
  backend MUST be reached over the tailnet, not exposed on the LAN.
- **Known upstream bug (LiteLLM)** — "No deployments available for selected model" has been reported
  against apparently healthy deployments; whichever gateway is chosen, the deploy MUST pin a version
  that has been exercised against a deliberately-downed backend.

## Requirements

- **FR-001**: Run a pinned gateway image via `docker_compose_v2` on a dedicated `lxc_service` LXC
  (unprivileged + nesting), sized small (baseline **2 vCPU / 2 GB / 8 GB disk** — it proxies, it does
  not infer). Record the pin in `ansible/group_vars/services/vars.yml` alongside the other
  `*_version` pins.
- **FR-002**: Expose exactly **one** OpenAI-compatible endpoint. Clients address **intent aliases**;
  a client MUST NOT need to know a provider model ID.
- **FR-003**: The alias→deployment mapping MUST be declarative data in `group_vars`, templated into
  the gateway config by the role. Changing the model behind an alias MUST NOT require editing role
  logic or any client.
- **FR-004**: Every alias with a remote equivalent MUST declare **ordered deployments** so that
  primary failure falls back automatically. `hermes-fast` falls back to `hermes-balanced`;
  `hermes-balanced` falls back to the metered tier.
- **FR-005**: Background health checks MUST be enabled (they are off by default in the leading
  candidate) with an interval ≤ 60 s, so a failed deployment leaves the pool *before* a request lands.
- **FR-006**: Inputs exceeding a deployment's context window MUST escalate to a larger tier rather
  than erroring to the caller.
- **FR-007**: All provider credentials come from `ansible-vault`; none in git. The router MUST NOT
  hold Anthropic **subscription/OAuth** credentials of any kind — the Anthropic backend is an **API
  key billed to the account owner**. (Rationale and the terms language: `065`, Research & decisions.)
- **FR-008**: Tailnet-only exposure. No public Caddy route in this item. If a landing-page entry is
  wanted later it MUST be `user_facing: false` or gated.
- **FR-009**: Publish a `monitoring_contract` in `ansible/host_vars/<svc>.yml` covering (a) gateway
  liveness, (b) a scrape of the gateway's metrics endpoint, and (c) a **blackbox probe of the Mac
  backend** so local-tier availability is a first-class signal. Alert on the gateway being down;
  the Mac being down is informational, not critical.
- **FR-010**: Enforce a per-client spend/rate limit so a looping client cannot bill unbounded.
- **FR-011**: Deploy through the gated LAB→PROD pipeline with the full registration set:
  `scripts/lab/service-scope-allowlist.json` entry (protected path → PR needs the
  `allow-protected-path-changes` label), `scripts/healthcheck/<svc>.sh`, and the `service` dropdown
  in `lxc-deploy-lab.yml`, `lxc-promote-lab.yml`, `lxc-promote-prod.yml`.
- **FR-012**: No user data persisted. Any request logging stays on the LXC's local disk with bounded
  retention; **no NFS mount** (`features_mount` omitted). Prompt/response bodies SHOULD NOT be
  logged by default.
- **FR-013**: The Mac backend MUST be addressed over the tailnet (MagicDNS name), never a LAN IP,
  and MUST NOT be reachable unauthenticated from the LAN.

## Success Criteria

- **SC-001**: With the Mac powered off, every alias still returns a valid completion; no client
  changes, no manual intervention.
- **SC-002**: With the Mac serving, `hermes-fast` is demonstrably served locally (provider visible in
  metrics) at zero marginal cost.
- **SC-003**: Remapping an alias to a different model is a single `group_vars` edit plus a deploy,
  with zero client-side change.
- **SC-004**: Pipeline deploys idempotently; container `Up (healthy)`; readiness 200; post-apply
  healthcheck green with evidence.
- **SC-005**: Grafana shows per-alias request volume, per-deployment failures and metered spend; a
  downed Mac raises its own distinct signal.
- **SC-006**: No credential in git; the router holds no Anthropic subscription credential.
- **SC-007**: The gateway is unreachable from outside the tailnet.
- **SC-008**: A deliberately-downed backend (stop the Mac's server mid-test) produces fallback, not
  an error — exercised as part of acceptance, not assumed.

## Research & decisions

**Landscape (surveyed Aug 2026).** "LLM router" conflates four things: self-hosted **gateways**
(LiteLLM, Bifrost, LLM Gateway, Portkey, Kong AI Gateway, TrueFoundry); hosted **aggregators**
(OpenRouter, Requesty); **routing brains** that pick a model per prompt (vLLM Semantic Router,
RouteLLM); and **client re-pointers** (Claude Code Router). This item builds the first, backed by
the second. Kong and TrueFoundry are the wrong shape (we run Caddy, not Kong; one LXC, not
Kubernetes). Portkey's useful parts are behind its managed control plane. Helicone was acquired in
March 2026 and is in maintenance mode — not a candidate.

**D-001 (OPEN — decide in the spec): which gateway.** Deliberately left open. Both finalists satisfy
the FRs; the trade is runtime weight against maturity.

| | **LiteLLM** | **Bifrost** |
| --- | --- | --- |
| License / language | MIT, Python | Apache-2.0, Go |
| Providers | 100+ | 20+ |
| Alias → N deployments | Yes (`model_name` repeated) | Yes |
| Background health checks | Yes, documented, **off by default** | Present; semantics less documented |
| Fallbacks / cooldowns | `fallbacks`, `context_window_fallbacks`, `allowed_fails`, `cooldown_time` | Supported |
| Budgets / per-client limits | Virtual keys + budgets | Virtual keys + budgets (first-class) |
| Prometheus | `/metrics` in OSS tier (some metrics enterprise-gated) | Async request logging |
| Footprint | Python; full feature set wants Postgres + Redis | Single Go binary, ~11 µs overhead |
| Risk | Open bug: "No deployments available" on healthy endpoints | Younger project, thinner docs |

Decide on: (1) does the OSS Prometheus surface actually carry per-alias spend, or is the useful half
enterprise-gated; (2) does Bifrost's health-check/fallback behaviour survive the downed-backend test
in FR/SC-008; (3) is the Postgres+Redis footprint acceptable for one LXC. **Lean: LiteLLM**, on
documentation depth for exactly the intermittent-backend case.

**D-002 (DECIDED): route on declared intent, not measured difficulty.** RouteLLM (LMSYS) showed ~85%
cost reduction at 95% of GPT-4 quality by sending only 14% of queries to the strong model, and the
vLLM Semantic Router productises per-prompt classification. Both are real; both are premature here.
The caller already knows whether a job is "classify this" or "reason about this", so intent is
cheaper, deterministic and debuggable. Revisit semantic routing once there is traffic worth
optimising — it slots in above the gateway without changing clients.

**D-003 (OPEN): aggregator choice.** OpenRouter (400+ models, one key, automatic provider failover,
a `:free` tier, BYOK; 5.5% credit fee / 5% BYOK) vs Requesty (Rust, ~8 ms P50). OpenRouter is the
default lean on ecosystem size.

**D-004 (OPEN, hardware-dated): tier→model mapping.** Mac is **32 GB now, 128 GB soon**. Initial:
`hermes-fast` → 4–8B local; `hermes-balanced` → 14–32B local, standby on the aggregator;
`hermes-deep` → Anthropic API (`claude-sonnet-5` class). On the 128 GB upgrade, revisit whether
`hermes-balanced` becomes a 70B-class local model and whether some `hermes-deep` traffic moves local.
FR-003 exists so this is a config edit.

**Mac serving.** Run headless so it is not an app that can be quit: `lms server start --host 0.0.0.0
--port 1234 --cors`, or Ollama with `OLLAMA_HOST=0.0.0.0`. Neither has authentication, hence FR-013.
LM Studio's **LM Link** is Tailscale-based device-to-device access built for this case and survives
the Mac leaving the LAN. Wake-on-LAN over Wi-Fi on Apple Silicon is unreliable; over Ethernet with
Power Nap it mostly works — but the design does not depend on it.

**Config sketch** (LiteLLM shape, illustrative — the values come from `group_vars` per FR-003):

```yaml
model_list:
  - model_name: hermes-fast              # preferred deployment
    litellm_params:
      model: ollama_chat/<small-model>
      api_base: http://<mac>.<tailnet>.ts.net:11434
    model_info: {mode: chat}
  - model_name: hermes-fast              # same alias, standby deployment
    litellm_params:
      model: openrouter/<small-model>
      api_key: os.environ/OPENROUTER_API_KEY
  - model_name: hermes-deep
    litellm_params:
      model: anthropic/claude-sonnet-5
      api_key: os.environ/ANTHROPIC_API_KEY

router_settings:
  fallbacks: [{"hermes-fast": ["hermes-balanced"]}, {"hermes-balanced": ["hermes-deep"]}]
  context_window_fallbacks: [{"hermes-fast": ["hermes-deep"]}]
  allowed_fails: 2
  cooldown_time: 60
  enable_pre_call_checks: true

general_settings:
  background_health_checks: true         # off by default — this is the intermittent-Mac fix
  health_check_interval: 60
```

**Sources**: LiteLLM health-check-driven routing and health endpoints
(https://docs.litellm.ai/docs/proxy/health_check_routing, https://docs.litellm.ai/docs/proxy/health);
reliability/fallback config (https://docs.litellm.ai/docs/proxy/reliability); Prometheus metrics
(https://docs.litellm.ai/docs/proxy/prometheus); open router-pool bug
(https://github.com/BerriAI/litellm/issues/11330); LM Studio headless + network serving
(https://lmstudio.ai/docs/developer/core/headless, https://lmstudio.ai/docs/developer/core/server/serve-on-network)
and LM Link (https://lmstudio.ai/link); vLLM Semantic Router
(https://github.com/vllm-project/semantic-router); RouteLLM (https://github.com/lm-sys/RouteLLM).

## Verification (acceptance)

1. **Deploy**: run the pipeline; Terraform creates the LXC; compose reports `healthy`; readiness
   endpoint 200; gate green with healthcheck evidence.
2. **Happy path**: request each of the three aliases; each returns a completion; metrics attribute
   each to the expected deployment.
3. **Downed-backend drill** (the acceptance that matters): stop the Mac's server, repeat the
   `hermes-fast` request → served by the standby, no client error. Restart it, wait one health
   interval → served locally again with no operator action.
4. **Escalation**: send an input longer than the small model's context → answered by a larger tier,
   not a 400.
5. **Blast radius**: confirm no public route; confirm the endpoint is unreachable off-tailnet;
   confirm no credential in git and none in the rendered config on disk beyond vault-sourced env.
6. **Budget**: exceed a per-client limit deliberately → request refused, alert visible.
7. **Retier drill**: change one alias mapping in `group_vars`, deploy, confirm the new deployment
   serves it and that no client changed.
8. **Monitoring**: liveness, metrics scrape and the Mac blackbox probe all present in the monitoring
   contract and green in Grafana.

## Dependencies

- **Blocked by**: nothing.
- **Blocks**: [`065-hermes-service`](./065-hermes-service.md) — Hermes is the first consumer.
- **Assumes**: Tailscale running on the Mac and reachable from the LXC; small PVE headroom (~2 GB);
  an OpenRouter (or Requesty) account and an Anthropic API key, both billed to the account owner;
  `caddy_services`/monitoring workflows as used by `market-model` and `eurooffice`.
- **Out of scope**: Hermes itself and the Claude-subscription plan door (`065`); semantic /
  difficulty-based routing (D-002, revisit later); local inference on the PVE node (not viable on a
  UHD 730); a chat UI in front of the gateway.
