# Backlog: FR-010's gateway-wide half has no working guard

**Status**: Backlog — found 2026-09-20 running `064`'s T054/T055 rate-limit breach drill.
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
