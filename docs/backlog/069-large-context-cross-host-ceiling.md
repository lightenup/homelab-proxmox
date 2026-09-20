# The Mac closes inbound LAN connections that go application-silent for ~300s

**Status**: **Diagnosed 2026-09-20.** Cause localised; no fix applied, because the two
viable fixes are a Mac-side setting and a declared-capability change — see *Decision needed*.
**Consequence**: `hermes-deep` advertises a 262,144-token context window that cannot be
reached with a **cold** prompt through the gateway. The practical cold ceiling is ~300s of
prefill, which is roughly **80k tokens**.

## The original symptom

Running `064`'s context-escalation drill (T038), the same ~108k-token prompt behaved four
different ways:

| path | result |
|---|---|
| Mac's LiteLLM directly (loopback), `reasoner` | **200 in 396.8s**, `prompt_tokens=108615` |
| gateway `hermes-deep`, cold, `timeout: 180` | `408 Timeout` at 180.3s — the gateway's own limit |
| gateway `hermes-deep`, cold, `timeout: 1200` | **connection error at 420.0s** |
| gateway `hermes-deep`, cold, `timeout: 1200`, `stream: true` | connection error at 433.0s, **zero SSE events** |
| gateway `hermes-deep`, **warm** (identical prompt re-sent) | **200 in 3.8s** — oMLX caches the prefill |

The gateway logged `OpenAIException - Connection error`, not a timeout, so something outside
either end's request timeout was closing the connection.

## Localising it

Each probe held a connection open with **no application data in either direction**, then sent
one byte to test liveness. (An earlier probe sent a byte every 30s — which is exactly what
prevents an idle timeout from firing, so it proved nothing and was discarded.)

Seven connections opened together and probed once each, against the Mac's `:4000`:

```
  silent  120s -> ALIVE   HTTP/1.1 200 OK
  silent  240s -> ALIVE   HTTP/1.1 200 OK
  silent  300s -> ALIVE   HTTP/1.1 200 OK
  silent  360s -> DEAD    peer closed (EOF)
  silent  420s -> DEAD    peer closed (EOF)
  silent  480s -> DEAD    peer closed (EOF)
  silent  600s -> DEAD    peer closed (EOF)
```

**The ceiling is between 300s and 360s**, and the failure is a clean **FIN** — the peer
closed. A NAT or conntrack expiry would blackhole and produce a timeout, not an EOF.

Then, isolating which component:

| path | 480s of silence |
|---|---|
| LXC → `pve` (Mac not in the path) | **survived**, HTTP 200 |
| Mac → Mac **loopback** | **survived**, HTTP 200 |
| LXC → Mac `:4999`, a plain `python3` listener, **no Docker** | **died** |
| LXC → Mac `:4000`, through Docker's forwarder | **died** |

So it is **specific to inbound LAN connections to the Mac**. Not the homelab network, not the
Mac's own TCP stack, and **not Docker Desktop's port forwarder** — a plain listener dies the
same way.

Finally, is it packet-level or application-level? Two connections, both application-silent
for 480s, one with `SO_KEEPALIVE` + `TCP_KEEPIDLE=60`:

```
  keepalive(60s)   after 480s -> DEAD   peer closed (EOF)
  control(none)    after 480s -> DEAD   peer closed (EOF)
```

**TCP keepalive does not help.** Packets were flowing every 30s and the connection was closed
anyway, so whatever closes it is counting **application-layer response data**, not packets.
That is an HTTP-aware middlebox, which rules out the packet-level app firewall / pf and points
at the Zscaler network filter (`com.zscaler.zscnetworkfilter`) — the same class of
corporate control that already explains why the Mac announces mDNS but never answers it.

## Why streaming does not rescue it

Streaming was the obvious mitigation and it fails for a concrete reason. On loopback, where
there is no ceiling to confound the measurement, a cold ~108k prompt streams like this:

```
   event   1 at    0.3s        <- LiteLLM's opening chunk
   event   2 at  384.3s        <- first real token, after prefill
   event   3 at  384.5s
   total 11 events, 389.2s
```

One chunk immediately, then **384 seconds of silence**, then the tokens. oMLX's
`server.sse_keepalive_mode: chunk` is already set, so whatever it does, it does not emit
during prefill. The stream is application-silent for longer than the ceiling, so it is closed
just like a non-streaming request.

## Decision needed

Two fixes, and both are someone's judgement call rather than a code change:

1. **Make the Mac emit something during prefill.** If oMLX can be made to send periodic SSE
   keepalives while prefilling — or if `scheduler.chunked_prefill: true` (currently `false`)
   causes output to begin earlier — the ceiling stops mattering and the full window becomes
   usable. This is the fix worth having, and it is entirely Mac-side. Start by asking whether
   `sse_keepalive_mode` has an interval, and what `chunked_prefill` changes about
   time-to-first-token.
2. **Declare a truthful `context_window`.** At ~397s for 108,615 tokens, 300s of prefill is
   roughly **80k tokens**. `enable_pre_call_checks` uses the declared window to decide whether
   to escalate, so declaring 262144 means the gateway accepts cold requests it cannot serve —
   the "configured and inert" failure mode inverted into "configured and unservable".

They are not exclusive; (2) is honest until (1) lands. The current configuration does neither,
deliberately, because the **warm** path genuinely serves the large window (3.8s for a cached
108k prompt) and reducing the declaration would misdescribe that.

## Consequences already recorded elsewhere

- The **>131k escalation path is still untested** — a cold request never survives long enough
  to reach `reasoner`'s window boundary, so the Mac's
  `context_window_fallbacks: reasoner → Qwen3.8-27B-8bit:qwen-long` has never fired end to end.
  Tracked as `tasks.md` T038.
- What *is* confirmed working: the Mac's `enable_pre_call_checks` (a 431k-token prompt was
  correctly refused with "No models have context window large enough"), and oMLX's prefill
  cache.
- The per-deployment timeouts (`tasks.md` T079) came out of this investigation and stand on
  their own: the single 180s default made `hermes-deep` fail inside its own declared window.
