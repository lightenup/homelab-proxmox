# ~~FR-010's gateway-wide half has no working guard~~ — RESOLVED

**Status**: **RESOLVED 2026-09-20**, same day it was found. Deployed and verified live.
**Was**: clients each stayed inside their own `rpm_limit` and could still saturate the Mac
together; nothing at the gateway refused them and nothing alerted.

## Resolution

`llm_router_gateway_budget.rpm_limit: 65`, passed to `/team/new`, reconciled onto the
existing team, asserted live, alerted on, and exercised at both levels.

Verified on the live gateway after deploy:

```
team  alias=llm-router-gateway-wide  rpm=65  max_budget=50.0
```

| level | test | result |
|---|---|---|
| per-client | `canary` (rpm 10), 16 concurrent | 10 × `200`, 6 × `429`; other clients unaffected |
| **gateway-wide** | two keys at rpm 3 on a team at rpm 4, three requests each — **neither key over its own limit** | 4 × `200`, 2 × `429` |
| distinguishable? | compare the two refusal bodies | **yes**: `for api_key: <hash>` vs `for team: <id>` |

That third row is FR-010's "an error distinguishing which was hit", tested for the first
time — it could not be tested before, because only one of the two levels existed.

The three things it needed are below, and two of them were the traps this note predicted.

### 1. The value, and why 65

```yaml
llm_router_gateway_budget:
  max_budget: 50.00
  budget_duration: "30d"
  rpm_limit: 65
```

65 rather than 60 (the `max(client)` floor) because at exactly 60 a fully-loaded `hermes`
would consume the entire gateway allowance and starve the synthetic canary — blinding the
monitoring that exists to notice outages. The canary needs one request an hour; 5 rpm of
headroom is plenty.

### 2. The preflight inequality inverts — as predicted

```
budget:  gateway  >  sum(clients)     a low cap is a self-inflicted outage
rate:    gateway  <  sum(clients)     a high cap can never bind
rate:    gateway  >= max(client)      so one compliant client trips its OWN limit first
```

All three are asserted. `65 >= 60` and `65 < 70` both hold. There is also a `debug` warning
for the case where a client declares no `rpm_limit` at all, which makes the sum unbounded
and the upper-bound check meaningless — it is skipped rather than silently passing.

### 3. The team was write-once — as predicted

`/team/new` is guarded by "does the alias already exist", so **every** gateway-wide setting
was write-once: changing `max_budget` or `rpm_limit` in `group_vars` was a silent no-op on
an already-deployed gateway. That is how this bug survived — the declaration and the
reality diverged with nothing to notice.

Fixed with an unconditional `/team/update` reconcile on every run, and then — the part that
matters more — **an assertion that reads the team back and compares**. A `200` from
`/team/update` with the field still `null` is exactly this bug, and it is invisible without
checking. The deploy now fails rather than drifting.

### Alerting

`LlmRouterGatewayRateCapBinding` (**warning**, `for: 5m`). LiteLLM emits the *same* metric
and label set for a team-level refusal as for a key-level one — only the error body
differs — so there is no series meaning "the gateway cap bound". What separates them is
blast radius: one client over its own limit produces 429s under exactly one
`api_key_alias`; the shared cap starves everyone calling.

```promql
count(count by (api_key_alias) (rate(litellm_proxy_failed_requests_metric_total{
  exception_status="429", team_alias="llm-router-gateway-wide"}[5m]) > 0)) > 1
```

Validated against live Prometheus in both directions: **does not fire** on a single
client's breach, **fires with value 2** under sustained refusal across two aliases.

Two caveats recorded rather than papered over:

- **Known ambiguity.** Two clients independently breaching their *own* limits at the same
  moment produce an identical signal. Read a refusal body to tell them apart. The
  operational response is similar either way, and the case worth excluding — one client
  misbehaving alone — *is* excluded.
- **`rate()` needs the counter to increase across scrapes.** A brief burst from a
  never-before-refused key gives one flat sample and `rate() = 0`, so the alert stays
  silent. That is correct for a `for: 5m` alert aimed at sustained saturation, but it does
  mean a 10-second test will look like a broken alert. Sustain the refusals across several
  30 s scrapes when testing. (Learned the hard way; the first validation attempt failed for
  exactly this reason.)

---

## Original note

**Impact**: clients each stay inside their own `rpm_limit` and can still saturate the Mac
together. Nothing at the gateway refuses them, and nothing alerts.

## What FR-010 asks for

> The gateway MUST enforce **rate** limits at two levels — per-client and gateway-wide —
> refused with an error distinguishing which was hit, and a per-client breach MUST NOT
> affect other clients.

The per-client level works, precisely, and was verified end to end
([`doctor-fault-injection.md` § Row 11](../../specs/064-llm-router/doctor-fault-injection.md)).
The gateway-wide level does not exist.

## What is actually deployed

```
team  alias=llm-router-gateway-wide  rpm=None  tpm=None  max_budget=50.0  spend=0.0
key   alias=hermes                   rpm=60    max_budget=20.0  spend=0.0
key   alias=canary                   rpm=10    max_budget=1.0   spend=0.0
```

Two things are true at once, and each hides the other:

1. **The gateway-wide *spend* cap exists but can never fire.** Local deployments carry no
   per-token pricing, so `spend` is exactly 0.0 regardless of traffic. This is already
   recorded — SC-012 is marked not-verifiable, T056/T057 are open.
2. **The gateway-wide *rate* cap was never configured.** `llm_router_gateway_budget`
   declares only `max_budget` and `budget_duration`, and `virtual_keys.yml` creates the
   team from exactly those two fields. There is no `rpm_limit` anywhere at team level.

Finding 2 is the new one. It is easy to miss because finding 1 makes the backstop *look*
present-but-dormant, when the half that could work today was simply never built.

## Why it matters here specifically

The Mac is a single machine serving every alias. `hermes` at 60 rpm plus `canary` at 10
is 70 requests/minute of real inference, each potentially a long prefill. Nothing needs to
misbehave for that to be more than the backend can absorb — two well-behaved clients are
enough. The per-client limits bound each caller; nothing bounds the sum.

This is also the only remaining runaway guard. Budgets are inert, so if the rate ceiling
is absent there is no ceiling.

## The fix

Add an `rpm_limit` to `llm_router_gateway_budget` and pass it through to `/team/new`:

```yaml
llm_router_gateway_budget:
  max_budget: 50.00
  budget_duration: "30d"
  rpm_limit: 50        # must be BELOW the sum of client rpm_limits, unlike max_budget
```

Two things to get right, and they are not symmetrical with the budget case:

- **The direction of the assertion inverts.** The preflight requires the gateway *budget*
  to exceed the sum of client budgets, because a cap below the sum turns normal usage into
  an outage. A gateway-wide *rate* cap above the sum of client rates can never bind and is
  therefore pointless — it has to sit below. Reusing the existing assertion here would
  enforce exactly the wrong inequality.
- **`virtual_keys.yml` cannot currently change an existing team.** The team is created once
  and never updated (`when: llm_router_gateway_team_id == ""`), and the `/key/update` pass
  only reconciles `models` — not `rpm_limit`. So adding this to `group_vars` alone would
  be a no-op on an already-provisioned gateway, which is the same class of silent-no-op
  this feature keeps producing. A `/team/update` call is part of the work.

Then extend the drill: breach the team limit with two keys that are each individually
compliant, and confirm the refusal is distinguishable from a per-client one (FR-010 says
the error must say which was hit — currently untested in either direction, since only one
of the two can fire).

## Related

- [`070`](./070-context-escalation-boundary-band.md) — the other open `064` measurement gap
- `specs/064-llm-router/tasks.md` T056/T057 — the spend half, blocked on pricing
- `specs/064-llm-router/spec.md` FR-010, SC-012
