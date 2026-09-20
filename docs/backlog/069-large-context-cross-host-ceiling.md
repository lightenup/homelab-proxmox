# The Mac closes inbound LAN connections that go application-silent for ~300s

**Status**: **RESOLVED 2026-09-20 — the local-tier leg now runs over TLS.**
Encrypting the payload removes what the closer acts on. Measured twice at 1500s and 1800s of
complete silence, and proven end to end: a cold 108k-token prompt that returned `408` at 180s
and a connection error at 417s over plaintext **completed in 395.6s over TLS**.
Implementation and install: [`specs/064-llm-router/mac-tls-terminator/`](../../specs/064-llm-router/mac-tls-terminator/README.md).

The investigation below is kept because six other approaches were measured and rejected, and
re-deriving them is expensive.

---

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

## What was rejected, and why

Each was measured, not argued. Recorded so nobody re-derives them.

| approach | why it failed |
|---|---|
| **reverse SSH tunnel** | the tunnel process dies on its own; requests failed at 417s and 711s. `autossh` reconnects but **cannot resume an in-flight HTTP request**, and raising `ServerAliveCountMax` only delays when ssh notices an already-dead flow |
| **mosh** | survives disconnects by design, but has **no port forwarding** |
| **LiteLLM SSE keepalive pings** | raises the floor but does not bound the drop (658s with pings every 20s), and the code gates it on `stream is True`, so non-streaming gets nothing |
| **LiteLLM response cache + retry** | `_cancel_llm_call_on_client_disconnect` actively cancels the upstream call on `http.disconnect` and raises 499. One call site, **unconditional — no setting gates it**. The work never completes, so nothing is cached |
| **retry alone** | an aborted prefill is **discarded**: abort at 120s, re-send took 689.7s, fully cold. A completed prefill re-sends in 13.2s, so caching works — it just never gets populated |
| **chunked prefix warming** | oMLX gives only 10–15 % on an extending prompt: 48k tokens cost 73s against 82s cold, 73k cost 105s against 124s. No usable prefix reuse |
| **TCP keepalive** | no help — the closer counts application data, not packets |

## The fix

TLS on the LAN leg, terminated on the Mac, relayed to LiteLLM over loopback.

```
gateway  --https, cert-verified-->  terminator :4443  --loopback-->  LiteLLM :4000  -->  oMLX
```

LiteLLM and oMLX both return to `127.0.0.1`, so the terminator is the only LAN-exposed
process — tighter than before — and `mac_litellm_key` stops crossing the LAN in plaintext.
Per-deployment timeouts went to 1200s on all three aliases, since the transport can now hold
them and the operating requirement is 20 minutes.

## A measurement worth keeping: prefill is superlinear

Gathered while testing prefix reuse, and it corrects an earlier estimate in this file:

```
 24k tokens ->  41s   (587 tok/s)
 48k tokens ->  73s
 73k tokens -> 105s
108k tokens -> 397s and 690s
```

Rate is strongly size-dependent, so "tokens per second" is the wrong unit for capacity
planning and a constant-rate extrapolation understates the usable context badly.

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

## One caveat: a client running ON the Mac is still subject to the closer

The TLS fix covers the **gateway → Mac** leg. It does not change what happens when something
on the Mac makes a long, silent, plaintext request *outbound* to the homelab — measured
failing at ~407s against the gateway, while the identical request from `pve` completed in
449s.

In practice this does not affect normal use: tooling on the Mac talks to the Mac's own
LiteLLM over loopback (`http://localhost:4000`), which is unaffected. It matters only if you
point something on the Mac at the gateway over the LAN — a test harness, for instance. It
cost two misattributed test results here before being recognised.

Homelab-internal clients (Hermes and anything else on an LXC) are unaffected: LXC → pve held
1500s of complete silence.
