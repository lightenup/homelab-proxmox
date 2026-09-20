# Contract — Client-Facing Gateway API

**Feature**: `064-llm-router` | Satisfies FR-002, FR-006, FR-010, FR-015

The gateway exposes **exactly one** OpenAI-compatible endpoint on `192.168.1.220:4000`, reachable
from the LAN and the tailnet. **No public route, no public DNS name, no landing-page entry**
(FR-008). LAN reachability is a deliberate narrowing of the original "tailnet-only" wording — see
research D-108 for the trade.

## Client surface

```http
POST http://192.168.1.220:4000/v1/chat/completions
Authorization: Bearer <per-client key>
Content-Type: application/json

{"model": "hermes-fast", "messages": [{"role": "user", "content": "..."}]}
```

`model` MUST be one of `hermes-fast`, `hermes-balanced`, `hermes-deep`. **A client never sends a
provider model ID** — that is the whole point of FR-002, and it is what makes the retier drill
(SC-003) a zero-client-change operation.

Also available, same auth, same alias vocabulary: `/v1/completions`, `/v1/embeddings` (if an
embedding alias is added later), `/v1/models` (lists the aliases, not the deployments).

## Response behaviour the acceptance criteria depend on

| Condition | Behaviour | Requirement |
|---|---|---|
| Preferred deployment healthy | Served by it; the serving deployment is identifiable in metrics | SC-002 |
| Preferred deployment in cooldown | Served by the next deployment **without attempting the dead one** | FR-004, AS-1.3 |
| All deployments for the alias in cooldown | Escalates to `fallback_to`'s alias — **dormant**, see below | FR-004 |
| Input exceeds the alias's context window | Escalates to `context_window_fallback_to` — **not** a 400. **Delegated to the Mac**, see below | FR-006, SC-009 |
| Every alias in the fallback chain exhausted | **Fails fast** with a clear error; no hang, no unbounded retry | Edge case, AS-1.5 |
| Client over its own budget | `400`/`429` naming the per-client limit; **other clients unaffected** | FR-010, SC-010 |
| Gateway-wide cap exhausted | Error **distinguishable** from a per-client breach; distinct alert fires | FR-010, SC-012 |

### Two rows that describe machinery nothing currently triggers (2026-09-20)

`fallback_to` and `context_window_fallback_to` are **null on every alias**, so neither
escalation row fires today. The rendering and preflight support both, and the contract is
unchanged — but a reader testing against this table will see no escalation and should not
conclude it is broken.

- **`fallback_to` is dormant** because there is nothing to fall back *to*. Every alias
  resolves to the same Mac; cross-alias fallback within one host is theatre. Row three
  therefore collapses into row five: all deployments in cooldown **fails fast**.
- **`context_window_fallback_to` is delegated, not dropped.** The Mac's own router
  escalates `reasoner` onto a 262k profile, which is why `hermes-deep` declares
  `context_window: 262144`. FR-006 and SC-009 are satisfied one hop down, by the layer
  that owns the models. Verified end to end in `tasks.md` T038: a 170,305-token prompt
  completed in 901.8 s. The gateway declaring the escalation too would second-guess the
  only hop that can act on it.

Both are one `group_vars` line away from active if a second backend ever appears.

The two budget errors being distinguishable is a contract requirement, not a nicety: an operator
seeing a refusal must be able to tell "one agent looped" from "the homelab is out of budget" without
opening the database.

## Health endpoints

| Path | Auth | Returns | Used for |
|---|---|---|---|
| `/health/liveliness` | none | `"I'm alive!"` / 503 while shutting down | not used — too weak, see below |
| `/health/readiness` | none | `{"status": "healthy", "db": "connected"}`; **503 if the database is unreachable** | blackbox liveness probe (FR-009a) and the post-apply healthcheck |
| `/health` | **bearer** | `{"healthy_endpoints": [...], "unhealthy_endpoints": [...]}` by firing real requests at every deployment | **deliberately not monitored** — it bills on every call |
| `/metrics` | **bearer** by default | Prometheus exposition | scrape target (FR-009b) |

`/health/readiness` is the liveness target rather than `/health/liveliness` because it fails when
Postgres is down. That is exactly the "gateway liveness green while everything is broken" trap the
spec calls out: a live process with a dead database validates no keys and serves no client, and
`/health/liveliness` would still report green.

## Non-contract

- No public hostname, no TLS termination, no Caddy entry, no landing-page tile (FR-008). The listener
  is **not** restricted to the tailnet interface; any LAN host can reach it, and per-client keys
  (FR-015) rather than network position are what gate access.
- No streaming-specific guarantees beyond LiteLLM's OpenAI-compatible passthrough.
- No admin UI is exposed; virtual keys are managed by the Ansible role, not by hand.
