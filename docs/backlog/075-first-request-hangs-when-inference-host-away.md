# The first request after the inference host disappears hangs instead of failing fast

**Status**: Backlog — measured 2026-09-21 running spec `065`'s Phase 7 drill (T050/SC-005).
**Impact**: SC-005 fails. A prompt sent while the Mac is away produces a spinner that hangs
for at least 90 seconds, not an error in under 10. The owner's most common failure mode is
also its least legible one.

## What was measured

Drill method: stop the TLS terminator LaunchAgent on the Mac
(`launchctl bootout gui/501/no.hus-sky.hermes-tls-terminator`), leaving oMLX and LiteLLM
running. Port 4443 closes, and the Mac's MDM-enforced stealth mode then **drops** the SYN
rather than refusing it — which is exactly what the LXC sees when the Mac is asleep or away
(backlog [`069`](./069-large-context-cross-host-ceiling.md)).

Requests are `POST /v1/chat/completions` against the gateway at `192.168.1.220:4000`,
`model=hermes-fast`, presenting the real Hermes client key.

| # | condition | result |
|---|---|---|
| 1 | baseline, host present | **200 in 0.91s** |
| 2 | host away, first request | **no response at 90.01s** — client aborted, gateway still waiting |
| 3 | host away, second request | **no response at 30.00s** |
| 4 | host away, later requests | **429 in 0.03s** — `No deployments available … cooldown_list=['fast-local']` |
| 5 | host restored | **200**, no administrative action |

So the machinery works — eventually. Rows 4 and 5 are the designed behaviour and they are
correct. **Row 2 is the defect.**

## Root cause: one timeout serving two opposed requirements

`065`'s own T049 anticipated this — "FR-009 vs FR-021 … these pull in opposite directions and
the split must be deliberate". The split was never actually made, because there is only one
knob:

| requirement | wants |
|---|---|
| FR-021 / SC-009 — a 20-minute generation must not be truncated | `timeout` **large** (currently 1200s) |
| FR-009 / SC-005 — a dead backend must surface in under 10s | `timeout` **small** |

LiteLLM's per-deployment `timeout` is a **total request** timeout, so it governs the connect
phase too. The long value wins, and connect inherits the 20-minute ceiling.

This only bites because the Mac **drops** the SYN. Against a host that refuses, connect fails
in ~0.001s and none of this matters. `064` already documented the stealth-mode behaviour and
its consequences for health checks; this is the same root cause reaching the user-facing path.

### Why the cooldown does not rescue it

`allowed_fails: 0` is meant to give "one slow failure, then fast clean errors for
cooldown_time". That is precisely what rows 2→4 show. But **the cooldown cannot engage until
the first failure completes**, and the first failure cannot complete until something times
out. The "one slow failure" is not merely slow, it is unbounded from the user's point of view.

Something did eventually cool the deployment inside ~2 minutes — most likely the background
health check (`background_health_checks: true`, `health_check_interval: 60`) rather than the
aborted requests. That bounds the hang window nearer 60s than 1200s, which is better than the
worst case but still six times SC-005's budget. **Not confirmed** — distinguishing "health
check cooled it" from "an abandoned request finally errored" needs another cycle with the
gateway logs open.

## Directions, none verified

1. **A separate connect timeout.** The correct fix in principle: seconds to connect, 1200s to
   generate. Whether LiteLLM exposes connect timeout independently per deployment needs
   research — if it passes an httpx timeout tuple through, this is a config change; if it only
   takes a scalar, it is an upstream matter.
2. **Shorten `health_check_interval`.** Does not fix the first request, only narrows the
   window. Cheap, and probes are local-tier only so they cost nothing.
3. **Make the Mac refuse rather than drop.** Turns every case into an instant
   connection-refused and dissolves the problem — but stealth mode is MDM-enforced and not
   ours to change (`069` established this).
4. **A cheap reachability pre-check** before dispatching to a local-tier deployment. Adds a
   mechanism, so weigh against Constitution IV.

Option 1 is the real answer if it exists; option 2 is the cheap mitigation meanwhile.

## What passes, and is worth keeping

The rest of US-5 holds, and the parts that hold are the ones that were least certain:

- **The interface stays up.** 200 in 0.06s with the backend gone — Hermes does not depend on
  the Mac to render, so conversations stay readable (US-5 AS-2).
- **Recovery is automatic.** Bringing the host back needs no deploy, no restart, no
  administrative action (US-5 AS-3).
- **When the error does arrive, it is legible and names the thing.** `cooldown_list=['fast-local']`
  identifies the exact deployment. That is the quality FR-010 asks for; the problem is purely
  how long the first one takes to arrive.
