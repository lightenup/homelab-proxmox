# Contract — Monitoring

**Feature**: `064-llm-router` | Satisfies FR-009, SC-005, SC-012

Declared in `ansible/host_vars/llm-router.yml`; consumed by `monitoring_stack` through `hostvars`,
the same mechanism `market-model` uses.

> **Precondition (D-107):** the host must be present in `ansible/inventories/prod/hosts.yml`. The
> monitoring templates iterate `groups['all']` / `groups['services']`; a host absent from the
> inventory contributes no scrape target, no probe and no alert, and the contract below silently
> does nothing.

## Shape

```yaml
healthcheck_url:
  scheme: http
  port: 4000
  path: /health/readiness
healthcheck_profile: lan
healthcheck_expect_status: 200

monitoring_contract:
  enabled: true
  scrape_targets:
    - job_name: "llm-router"
      port: 4000
      path: /metrics
  liveness_targets:
    - job_name: "llm-router-readiness"
      url: "http://192.168.1.220:4000/health/readiness"
      module: http_2xx
  alert_rules:
    - alert: LlmRouterDown                # severity: critical
    - alert: LlmRouterLocalTierDown       # severity: info
    - alert: LlmRouterAllBackendsFailing  # severity: critical
    - alert: LlmRouterCanaryFailing       # severity: critical
    - alert: LlmRouterBudgetCapExhausted  # severity: critical
```

## Signals and severities

| Signal | Source | Severity | Why |
|---|---|---|---|
| Gateway down or database unreachable | blackbox on `/health/readiness` | **critical** | Every client is refused. FR-009 requires the gateway being down to alert. |
| Local tier (Mac) unavailable | `litellm_deployment_state` for the local deployments | **info** | FR-009 requires this to be informational, not critical. Routed to Pushover at priority `-1` since 2026-09-22 (043 FR-016), i.e. delivered silently. **The rationale was revisited — see below.** |
| **All backends failing, under traffic** | failure ratio across all deployments > 90% over 10m | **critical** | FR-018. The gateway is alive and the database is fine, but nothing can be served. |
| **All backends failing, no traffic** | synthetic canary request fails (every attempt) | **warning** | FR-018, SC-013. The failure-rate signal is silent with no clients calling — which is exactly how this trap goes unnoticed until someone tries to use the gateway. **Was `critical` until 2026-09-22** — see below. |
| Gateway-wide budget cap exhausted | `litellm_remaining_team_budget_metric` at/near zero | **critical** | SC-012. This refuses every client at once, so it is an availability event, not just a spend one. **Cannot currently fire** — spend is structurally 0.0. |
| **Gateway-wide rate cap binding** | 429s across ≥2 distinct `api_key_alias` on the gateway team | **warning** | FR-010's second level, live since 2026-09-20. Warning not critical: the window resets every minute and the backstop is doing its job — it means the homelab is at its ceiling. |
| Per-client **rate-limit** breach | `litellm_proxy_failed_requests_metric_total{exception_status="429"}` by `api_key_alias` | (dashboard only) | SC-010 — visible and attributable, but one client hitting its own limit is working as designed, not an incident. **Verified 2026-09-20**, `doctor-fault-injection.md` § Row 11. |
| ~~Per-client budget breach~~ | ~~spend metric per key alias~~ | — | **Cannot occur.** Local tiers carry no pricing, so `spend` is 0.0 forever. Superseded by the rate-limit row above, which is the guard that actually bites. |

> **Do not build a "requests remaining" panel on `litellm_remaining_api_key_requests_for_model`.**
> Measured 2026-09-20: it reports `9.223372036854776e+18` (int64 max) for *every* key,
> including one with `rpm_limit: 10` that was actively being refused. It does not reflect
> the configured limit. The `429`-filtered failure counter above is the working signal.

> **Gateway-wide rate cap, added 2026-09-20** (backlog
> [`071`](../../../docs/backlog/071-gateway-wide-rate-limit-missing.md), resolved). LiteLLM
> emits the **same** metric and label set for a team-level refusal as for a key-level one —
> only the error body differs (`for team:` vs `for api_key:`) — so there is no series that
> means "the gateway cap bound". `LlmRouterGatewayRateCapBinding` uses blast radius instead:
> 429s under **two or more** `api_key_alias` values at once. One client over its own limit
> touches one alias and is deliberately not alerted.
>
> Two clients independently breaching their own limits at the same moment give an identical
> signal — known, documented on the alert, and not worth more machinery than that.
>
> **When testing it: `rate()` needs the counter to rise across scrapes.** A short burst from
> a never-refused key is one flat sample and `rate() = 0`, so a 10-second test looks like a
> broken alert. Sustain refusals across several 30 s scrapes. Validated both ways on the
> live Prometheus: silent on one client, value 2 on two.

The severity split is the substance of this contract. A downed Mac and a downed gateway look similar
in a naive dashboard and could not be more different operationally.

### The local-tier severity, revisited 2026-09-20

That row used to read "the Mac is a discount, not a dependency" — SC-001. **SC-001 is
withdrawn.** The metered tiers are gone, every alias resolves to the same Mac, so *the Mac
being unavailable and every backend failing are now the same event.*

The behaviour is still right, and it is worth being explicit about why rather than leaving
a stale justification in place:

- The **`litellm_deployment_state` signal stays `info`**. Its value now is the timeline —
  the Mac's duty cycle, visible on the dashboard — not the alert.
- The **critical alert comes from the canary** (`LlmRouterCanaryFailing`), which fires on
  exactly this condition and fires whether or not clients are calling.

So the operator does get paged when the Mac is down; the page just arrives from the signal
that is *about* total unavailability rather than from the one that is about a backend.
Promoting the local-tier signal to critical would double-alert the same event.

**This leaves FR-009 stating a rationale that no longer holds** ("the Mac being down MUST
be informational, not critical" — written when the Mac was optional). The requirement's
*effect* is still what we want; its *reason* changed. Flagged rather than silently
rewritten, because it is the account owner's call whether an unavailable Mac should now be
a first-class critical in its own right.

### Answered 2026-09-22: no, and the canary steps down with it

The owner's call, recorded: **an unavailable Mac is not a page.** Both halves of the
argument above are now settled in the same direction, which changes the second bullet.

- `litellm_deployment_state` **stays `info`**, unchanged — but `info` finally has a route.
  It had none, so it fell through to Alertmanager's root receiver and arrived on the phone
  titled `[WARNING]`, the exact opposite of what this row asks for. It now resolves to
  `pushover-info` at priority `-1`: delivered, silent (043 FR-016).
- `LlmRouterCanaryFailing` **drops from `critical` to `warning`**, so the sentence "the
  critical alert comes from the canary" no longer holds and nothing above it replaces the
  page. That is deliberate, not an oversight.

Why the premise collapsed. The canary was a sound proxy for "the Mac is gone" only while a
failed canary meant something rare. It does not. oMLX returns `400 prefill memory guard
rejected this prompt` whenever the Mac is under memory pressure, and the guard projects
peak usage from resident memory plus a 20–37 GB KV/SDPA transient rather than from prompt
size — so the canary's own 14-token `max_tokens:1` request is refused while the gateway is
healthy and every other alias is serving. Measured 2026-09-22: **244 such 400s in 24 h, 488
of 503 against model group `fast`**, which is precisely what the canary calls. The alert was
firing on ordinary laptop memory pressure, at Pushover priority 2 — re-alerting every 60 s
for an hour, per firing.

What replaces it, and what does not:

- **Nothing pages for "Mac away, no traffic."** Accepted. The Mac is a laptop that sleeps;
  the condition is routine. The owner gets one normal-priority push from the canary warning.
- `LlmRouterAllBackendsFailing` **still raises a critical** whenever real traffic is broadly
  failing — the case that actually costs something, because someone is waiting on it.
- The canary's meaning is tightened at the source rather than in the alert: `canary.sh`
  retries `llm_router_canary_attempts` times before writing a `0`, so a firing now denotes
  three consecutive failures. `for:` stays `0m` — the metric is a level refreshed hourly, so
  any `for:` would only add to an already up-to-60-minute sampling gap without suppressing
  anything, and SC-013 ("an alert fires within one canary interval") still holds because the
  retries complete inside one run.

**Known residue, not fixed here.** A sleeping Mac still fires both rules: the canary warning
(audible, priority 0) and the local-tier info (silent). An Alertmanager inhibit rule keyed on
`LlmRouterCanaryFailing` suppressing `LlmRouterLocalTierDown` would collapse them, and needs
no `equal:` clause because the two carry different `instance` labels. Left out deliberately —
it is a second change to the same surface and the audible half is one push per four hours at
`repeat_interval`, which the owner accepted.

**Why two all-backends signals rather than one.** `/health/readiness` returns 200 while every
deployment is dead — it only checks the database. The failure-rate signal closes that, but only while
clients are calling; a homelab gateway can sit idle for hours, so a traffic-derived alert can stay
green through a total outage. The canary is the half that makes SC-013 testable: it is a real
low-cadence request against the cheapest alias, so it is **client traffic, not a health probe**, and
therefore does not count against SC-011's probe budget. While the Mac is up it is served locally at
zero marginal cost.

## Grafana panels (SC-005)

- Per-alias request volume — by `requested_model`.
- Per-deployment success/failure — `litellm_deployment_success_responses` /
  `_failure_responses` by `model_info.id`, which is what makes SC-002 ("`hermes-fast` demonstrably
  served locally") checkable rather than assumed.
- Metered spend per alias — `litellm_spend_metric`, **or** the `LiteLLM_SpendLogs` fallback
  (research D-105).
- Local-tier availability timeline — makes the intermittent Mac's duty cycle visible, which is what
  tells the operator whether retiering to a bigger local model is worth it.

## Scrape-config note (D-105 — resolved by live testing)

Live-tested against the pinned `v1.83.3-stable` image: `/metrics` is **open by default** (not
bearer-gated, contrary to the docs' prose), and enabling `require_auth_for_metrics_endpoint: true`
reproducibly hangs the master key against this endpoint specifically (confirmed: the same key works
instantly on every other admin endpoint). No working authenticated path was found for this pinned
version, so the endpoint ships at its default (open), documented explicitly in `config.yaml.j2`
rather than relying on silent default behaviour — `/metrics` publishes spend and deployment
topology, not credentials, and FR-008 already accepts LAN reachability for the gateway itself
(D-108). An optional, default-off `authorization` block was still added to the shared
`prometheus.yml.j2` (byte-identical output for every other service's contract) so a future service
that does need scrape auth has it available. Revisit `require_auth_for_metrics_endpoint` on the next
LiteLLM version bump. `/metrics` also redirects to `/metrics/` (307) — the scrape target's `path` is
set to `/metrics/` directly to skip the extra hop.
