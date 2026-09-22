# Phase 0 — Research & Decisions: LLM Router

**Feature**: `064-llm-router` | **Date**: 2026-08-29

Spec-level choices (gateway, aggregator, client-auth shape, local runtime) were settled in
[spec.md § Decisions](./spec.md#decisions). This document resolves the *implementation* unknowns the
plan surfaced, and records two corrections to assumptions the spec carried.

---

## D-101 — Health checks that find the dead Mac without billing for it

**Decision**: Enable background health checks at a 60 s interval, and **scope them to the local model
group only** via `background_health_check_model_groups`. Metered deployments additionally carry
`disable_background_health_check: true` in their `model_info`.

```yaml
general_settings:
  background_health_checks: true          # off by default — this is the intermittent-Mac fix
  health_check_interval: 300              # was 60; FR-005's bound amended 2026-09-22 (= LiteLLM default)
  background_health_check_model_groups: ["hermes-fast-local", "hermes-balanced-local"]
```

**Rationale**: FR-005 requires bounded probing so a dead deployment leaves the pool before a request
lands; the "health checks cost money" edge case requires that probing not become a line item. Both
are satisfiable at once because the only deployment that actually needs probing is the intermittent
one. OpenRouter and Anthropic are always-available metered endpoints — probing them buys nothing and
bills real tokens. Confirmed against the LiteLLM health docs: `health_check_interval` defaults to
300 s, and both the model-group allowlist and the per-model `disable_background_health_check` opt-out
exist.

**Alternatives considered**: probing everything at 60 s (bills continuously — rejected on the spec's
own edge case); probing nothing and relying on request-time failure plus cooldown (rejected: it makes
the *first* request after the Mac dies pay a full timeout, which is Acceptance Scenario 1.3's
explicit prohibition).

---

## D-102 — How the LXC reaches a roaming Mac (correction to a spec assumption)

**Decision**: Run `tailscaled` in **userspace-networking mode as a compose sidecar** with an outbound
HTTP proxy, and point LiteLLM's Ollama deployment at the Mac's MagicDNS name through that proxy.

**The correction**: the spec assumes "Tailscale is running on the Mac and reachable from the LXC" and
FR-013 requires MagicDNS addressing. **That path does not exist today.** Tailscale runs only on the
PVE host (`ansible/roles/tailscale_router`, `tailscale_subnet_routes: "192.168.1.0/24"`), where it
advertises the *LAN into the tailnet* so tailnet devices can reach homelab services. It does not give
a LAN-only LXC a route to a tailnet device. Service LXCs have a static LAN IP with the LAN router as
gateway and no `100.64.0.0/10` route. Without new work, the LXC cannot reach the Mac once it leaves
the house — which is the entire scenario this feature exists for.

**Why userspace mode specifically**: normal `tailscaled` needs `/dev/net/tun`. Passing that into an
unprivileged LXC requires a `pct set` device-passthrough step — Tier-2 orchestrator territory, and
the orchestrator's bind-mount allowlist rejects any host path outside `/mnt/nas/`
(`pve-service-deploy:2309`). Userspace networking needs no TUN device, no privileged container, and
no `pct set`, so the deploy stays inside Tier 1 and the Constitution's privilege model is untouched.

```yaml
# compose sidecar (illustrative)
tailscale:
  image: tailscale/tailscale:<pinned>
  environment:
    TS_AUTHKEY: ${TS_AUTHKEY}          # vault-sourced, ephemeral+tagged
    TS_USERSPACE: "true"
    TS_EXTRA_ARGS: "--hostname=llm-router --outbound-http-proxy-listen=0.0.0.0:1055"
# litellm reaches the Mac through it
litellm:
  environment:
    HTTP_PROXY: "http://tailscale:1055"
    NO_PROXY: "localhost,127.0.0.1,postgres"
```

`NO_PROXY` matters: without it, LiteLLM's Postgres and loopback traffic would also be pushed at the
proxy.

**Verification owed (do not assume)**: that LiteLLM's httpx client honours `HTTP_PROXY` on the
`ollama_chat` provider path, and that MagicDNS names resolve through the outbound proxy. Both are
expected — httpx trusts proxy env vars by default and the proxy resolves names inside the tailnet —
but neither has been exercised here. This is a first-deploy LAB check, and the fallback if it fails
is `ALL_PROXY` with the SOCKS5 listener instead.

**Alternatives considered**: a static `100.64.0.0/10` route on the LXC via the PVE host (works only
while the PVE host forwards, and gives no MagicDNS resolution — the LXC's DNS is AdGuard on the LAN);
Tailscale installed in the LXC with TUN passthrough (rejected on the Tier-2 allowlist collision
above); addressing the Mac by LAN IP (rejected — violates FR-013 and fails exactly when it matters).

---

## D-103 — The local-tier signal comes from the gateway, not a second tailnet probe

**Decision**: Take "local tier down" from LiteLLM's own `litellm_deployment_state` /
`litellm_deployment_failure_responses` metrics, scraped from the LXC over the LAN. Use blackbox
against `/health/readiness` for gateway-and-database liveness. Do **not** put a blackbox probe on the
Mac itself.

**The correction**: FR-009(c) asks for "a blackbox probe of the Mac backend". Implemented literally,
that probe would run from the **monitoring** LXC, which has no tailnet path either — so satisfying
FR-009(c) as written would mean solving D-102 a second time, on a second LXC, purely for a probe.
The requirement's *intent* — "local-tier availability is a first-class signal" — is met more cheaply
and more accurately by the gateway, which is already probing the Mac every 60 s under D-101 and knows
whether the deployment is in the pool. A blackbox probe would only tell us whether a port answers;
`litellm_deployment_state` tells us whether LiteLLM will actually route to it, which is the thing the
operator cares about.

Three signals, matching FR-009's three clauses:

| FR-009 clause | Implementation | Severity |
|---|---|---|
| (a) gateway liveness | blackbox `http_2xx` → `http://192.168.1.220:4000/health/readiness` | critical |
| (b) metrics scrape | Prometheus scrape → `192.168.1.220:4000/metrics` | — |
| (c) local-tier availability | `litellm_deployment_state` for the Ollama deployment | **informational** |

`/health/readiness` is the right liveness target rather than `/health/liveliness`: it is
unauthenticated (so blackbox needs no credential) **and** it returns 503 when the database is
unreachable. That single choice also covers the plan's "backing services down presents as auth
failure for every client" edge case — a broken Postgres turns the liveness probe red instead of
silently breaking key validation. `/health` (the endpoint that reports `healthy_endpoints` /
`unhealthy_endpoints`) is deliberately *not* used: it is authenticated, and it works by firing real
requests at every deployment, which reintroduces the billing problem D-101 just solved.

**Gap this originally left, now closed (FR-018)**: the three signals above cover the gateway, its
database and the *local* tier — but not "every backend is failing at once". `/health/readiness` stays
200 when all deployments are dead (it only checks the DB), and metered deployments have background
checks disabled under D-101, so their `deployment_state` never updates. The spec's headline edge case
was therefore unmitigated. Closed by two additions: a failure-rate alert across all deployments, and a
low-cadence **synthetic canary request** so the condition is detectable with no client traffic
flowing. The canary is client traffic rather than a health probe, so it sits outside SC-011's probe
budget by construction.

**Alternatives considered**: Tailscale on the monitoring LXC so blackbox can reach the Mac (rejected —
a second tailnet dependency for one probe); accepting no local-tier signal (rejected — SC-005
requires a distinct downed-Mac signal); a failure-rate alert alone for the all-backends case (rejected
— silent when no traffic flows, which is exactly how the trap goes unnoticed).

---

## D-104 — Redis is not justified at one worker (DECIDED: dropped)

**Decision**: **Ship without Redis.** Run LiteLLM single-worker with in-memory router state. *Confirmed by the operator during `/speckit.analyze` remediation; FR-014 was amended to make Redis conditional on worker count, so the spec and this decision now agree.*

**Rationale**: this narrows the spec's D-001 decision, and deliberately so. LiteLLM uses Redis to
share router cooldown state and rate-limit counters *between workers*; at one worker there is no
second consumer, which is precisely the case Constitution IV ("do not add indirection unless at least
two concrete consumers exist today") rules out. Critically, **nothing the operator chose D-001 for is
lost**: virtual keys, per-client budgets and spend logging are all Postgres-backed, not Redis-backed.
Redis would add a third stateful container to patch, back up and monitor in exchange for a capability
this deployment does not use.

LiteLLM's `use_shared_health_check` (which does require Redis) is likewise a multi-pod feature.

**Reversible**: if the gateway ever needs multiple workers, Redis is a four-line compose service plus
a `litellm_settings.cache_params` block. Nothing in the alias mapping or the role structure changes.

**Alternatives considered**: including Redis as specified (rejected on the economy gate — surfaced to the operator rather than applied silently, and confirmed by them).

---

## D-105 — Per-alias spend: RESOLVED by live testing against the pinned image

**Status update (implementation phase):** this was planned as a "verify on first LAB deploy" item.
It was instead resolved during implementation by running the exact pinned `ghcr.io/berriai/litellm:
v1.83.3-stable` image locally against a real Postgres backend (Docker, no homelab impact) — three
separate empirical findings came out of that, all encoded directly in the shipped config rather than
left as an assumption for LAB to discover.

**Finding 1 — the metrics ARE free-tier**, resolving the documentation ambiguity conclusively: with
`litellm_settings.callbacks: ["prometheus"]` set, `/metrics` emits the full metric set with no
license or enterprise gate. Real metric names confirmed (note the `_total` suffix Prometheus's client
library appends to counters, which the docs prose omits):
`litellm_deployment_state`, `litellm_deployment_success_responses_total`,
`litellm_deployment_failure_responses_total`, `litellm_deployment_total_requests_total`,
`litellm_spend_metric_total`, `litellm_remaining_team_budget_metric`,
`litellm_remaining_api_key_budget_metric`. The `LiteLLM_SpendLogs` fallback is therefore **not
needed** — dropped from scope.

**Finding 2 — `callbacks: ["prometheus"]` was missing from the original template design.** Without
it, `/metrics` exists as an endpoint but never emits any `litellm_*` series — confirmed by testing
the config both ways. Added to `config.yaml.j2`.

**Finding 3 — a reproducible bug in `require_auth_for_metrics_endpoint: true` against this pinned
version.** The docs describe this flag (default `false`, i.e. open) as the way to require a bearer
token on `/metrics`. Live-tested: with it set to `true`, requests with the correct master key
**hang indefinitely** (no response, no server-side log line — the request appears to never reach the
application layer), while a wrong key or no key both correctly and instantly return 401. A freshly
generated virtual key fails fast instead of hanging, but is rejected outright
("Only proxy admin can access /metrics") — there is no found working authenticated path against this
version. **Decision: leave `require_auth_for_metrics_endpoint` at its default (`false`, open)**,
documented explicitly in `config.yaml.j2` rather than relying on silent default behaviour. `/metrics`
carries spend and topology data, not credentials, and FR-008 already accepts LAN reachability for the
gateway itself (D-108) — extending that acceptance to one read-only endpoint was the pragmatic
trade against blocking observability on an upstream bug. The `prometheus.yml.j2` bearer-auth
extension (below) was still built, since it's a small, generically useful, default-off addition —
just not exercised for llm-router. Revisit `require_auth_for_metrics_endpoint` on the next LiteLLM
version bump.

**One operational detail confirmed**: `/metrics` redirects `GET /metrics` → `GET /metrics/` (307).
The scrape target's `path` is set to `/metrics/` directly to avoid the extra hop.

**Prometheus scrape-config gap (built, not exercised)**: The repo's `monitoring_contract.scrape_
targets` template (`prometheus.yml.j2`) originally emitted only `job_name`/`port`/`path`/
`scrape_interval` — no credential field. An optional, default-off `authorization` block was added
(a small change to the shared monitoring role, byte-identical output for every contract that doesn't
set `bearer_token`) so a future service that *does* need scrape auth doesn't have to solve this again.

**Multi-worker note (unchanged)**: `PROMETHEUS_MULTIPROC_DIR` would be needed if the worker count
ever rises above one (D-104) — not applicable today.

---

## D-106 — Anthropic tier: model ID and a dated pricing note

**Decision**: `hermes-deep` maps to `anthropic/claude-sonnet-5`, keyed by `ANTHROPIC_API_KEY`.

**Rationale**: matches the spec's stated `claude-sonnet-5`-class intent. Current published rates are
**$3.00 / $15.00 per 1M tokens** input/output, with introductory pricing of **$2.00 / $10.00 running
through 2026-08-31 — two days from this plan's date**. Budget figures set from a pre-31-August
observation will understate steady-state cost by ~50%, which matters because FR-010's per-client and
gateway-wide caps are dollar-denominated. Set the caps against list price, not the intro rate.

`claude-opus-5` ($5.00 / $25.00, 1M context) is the escalation target if `hermes-deep` proves
underpowered; that is a one-line alias remap under FR-003.

**FR-007 restated as an implementation constraint**: the router holds an **API key billed to the
account owner** and must never hold an Anthropic subscription or OAuth credential. Nothing in the
LiteLLM Anthropic provider path requires one; the preflight asserts the vault variable is present and
the role never writes it to disk outside the container environment.

---

## D-107 — Where the new service plugs into existing repo machinery

**Decision**: allocate `192.168.1.220/24`, service name `llm-router`, Terraform module
`module.llm_router_lxc`, Ansible role `llm_router`.

`.220` is the next free address in `service_ips` (`.210`–`.219` are taken, with `.219` = eurooffice).

**Pre-existing gap noticed, and deliberately not fixed here**: `ansible/inventories/prod/hosts.yml`
lists services only up to `financial-scenario` (`.217`) — **`market-model` and `eurooffice` are
missing from it**. Because the monitoring templates iterate `groups['all']`/`groups['services']` via
`hostvars`, a service absent from that inventory contributes no scrape target, no liveness probe and
no alert rule. This feature must add its own `llm-router` entry (or FR-009 silently no-ops), and that
task is in scope. Repairing the two pre-existing omissions is **not** in this feature's scope, but it
is worth a separate backlog item — it likely means `market-model` and `eurooffice` are currently
unmonitored in prod.

---

## D-108 — Exposure scope: LAN + tailnet, no public route

**Decision**: the gateway listens on `0.0.0.0:4000` at `192.168.1.220`, reachable from the LAN and
the tailnet, with no public route, no public DNS name and no landing-page entry. FR-008 and SC-007
were reworded from "tailnet-only" to match.

**Rationale**: "tailnet-only" was unsatisfiable as written alongside FR-009. Prometheus and
blackbox_exporter run on the monitoring LXC, which is LAN-only; a genuinely tailnet-bound listener
would need the monitoring LXC on the tailnet too — solving D-102 a second time, for one scrape and
one probe. The narrowing keeps the monitoring path unchanged.

**The trade, stated plainly**: any host on the LAN can reach the service holding every provider
credential in the homelab. That is a real widening and it is recorded as an accepted risk in the
spec, not buried. Mitigations are per-client keys (FR-015) and the two-level spend caps (FR-010) —
LAN reachability is not the same as unauthenticated access. If the LAN stops being a trusted
segment, this is the first decision to revisit.

**Alternatives considered**: binding to the tailnet interface (rejected on the doubled-egress cost
above); a source-IP firewall allowlist on the LAN (deferred, not rejected — a reasonable hardening
step if the LAN's trust assumption weakens, and it does not change any other decision).

---

## D-109 — Two-level budgets: LiteLLM teams, not a standalone Budget object (implementation-phase finding)

**Decision**: the gateway-wide cap is a LiteLLM **team** ("llm-router-gateway-wide"), and every
client's virtual key is generated on that team. Each key's own `max_budget` is LiteLLM's
"team member budget" — an individual limit enforced within the team's shared cap.

**Why this changed from the original design**: the first implementation used a standalone object via
`POST /budget/new`, matching the spec's "gateway-wide cap" language literally. Live-tested against
the pinned image: it works (creates and stores correctly), but **has no corresponding Prometheus
metric** — only team/org/key/user-scoped budgets are exposed (`litellm_remaining_team_budget_metric`
et al.). A cap Prometheus can't see can't back the `LlmRouterBudgetCapExhausted` alert (SC-012), so
the requirement as originally built was silently unobservable. Rebuilding on LiteLLM's team primitive
(also live-tested: `/team/new` + `/key/generate` with `team_id` both correct and fast) fixes this by
using the platform's own two-level primitive instead of inventing one — it maps onto FR-010 exactly:
team budget = gateway-wide backstop, team-member budget = per-client limit, one breaching the other
without both keys colliding.

**Alternatives considered**: the standalone Budget object (reverted — unobservable, see above);
deriving the gateway-wide cap post-hoc by summing `litellm_remaining_api_key_budget_metric` across
all keys (rejected — reconstructs a number the team primitive already gives natively, adds a
PromQL aggregation as a single point of failure for a safety mechanism).

## D-110 — Dashboard provisioning: a latent host-name/role-name bug, now fixed generally

**Finding**: `monitoring_stack`'s `provision_dashboards.yml` resolves a service's dashboard file at
`roles/{{ item }}/files/...`, where `item` is the **inventory hostname** — documented as relying on
"the role name by project convention". That convention holds for single-word services (`jellyfin`
host → `jellyfin` role) but **silently breaks for any hyphenated host name**, because Ansible role
directories conventionally use underscores (`market-model` host → `market_model` role,
`llm-router` host → `llm_router` role). No hyphenated-name service had `dashboard_file` set before
this feature, so the gap was real but unexercised.

**Decision**: fixed generally rather than worked around — `roles/{{ item | replace('-', '_') }}/
files/...`. No-ops for every existing single-word service (confirmed: `'jellyfin' | replace('-',
'_')` is unchanged); resolves correctly for `llm-router` and retroactively for `market-model` and
`financial-scenario` if either ever adds a `dashboard_file`. A one-line change to a shared task file,
confirmed via `ansible-lint` (production profile, 0 findings) across the whole `monitoring_stack`
role.

## D-111 — node_exporter textfile collector: a small, generic, reusable addition

**Finding**: the synthetic canary (FR-018) needs a way to get an ad-hoc metric (`llm_router_canary_
success`) into Prometheus that doesn't come from LiteLLM itself. Two off-the-shelf options exist —
Prometheus's own Pushgateway (not present in this stack) or node_exporter's textfile collector
(standard, minimal, and node_exporter already runs on every service LXC via `lxc_base`) — and neither
required inventing a new mechanism.

**Decision**: enabled `--collector.textfile.directory` on the shared `node_exporter` role
(`node_exporter_textfile_directory` default, a directory-creation task, one flag on the systemd
unit). Backward compatible: an empty directory means node_exporter reports nothing extra, so every
other service is unaffected. The canary script writes one `.prom` file via write-then-atomic-rename
so node_exporter never reads a half-written file.

**Alternatives considered**: a bespoke `blackbox_exporter` module issuing the canary's POST request
directly (rejected — would require putting the canary's API key into a *shared* monitoring template
rather than scoped to the `llm_router` role, a larger blast-radius trade for no real benefit); a
Pushgateway (rejected — a fourth piece of stack infrastructure for one metric).

---

## Summary of what Phase 0 changed

| Item | Spec assumption | Phase 0 outcome |
|---|---|---|
| Mac reachability | "Tailscale running on the Mac and reachable from the LXC" | Path does not exist; added a userspace-networking sidecar (D-102) |
| FR-009(c) Mac probe | blackbox probe of the Mac | Gateway deployment-state metric instead; avoids a second tailnet dependency (D-103) |
| Redis | Part of the D-001 decision | No consumer at one worker; recommend dropping (D-104) |
| Per-alias spend | Native, "served natively rather than reconstructed" | Ambiguous licensing; verify on first LAB deploy, SpendLogs fallback ready (D-105) |
| Health-check cost | "cadence/mode chosen so probes are not a line item" | Scope background checks to the local model group only (D-101) |
| Monitoring wiring | Assumed to work like market-model | market-model itself is missing from the prod inventory (D-107) |
| Exposure | "Tailnet-only" | Unsatisfiable alongside FR-009; narrowed to no-public-route with the LAN trade recorded (D-108) |
| All-backends-down | Edge case named, no mechanism | Failure-rate alert + synthetic canary; FR-018 added (D-103) |

*Amendments from `/speckit.analyze` remediation are folded into D-103, D-104 and D-108 above; spec.md
was updated in the same pass so the two artifacts agree.*
