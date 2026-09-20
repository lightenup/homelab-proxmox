# Backlog: a cold large-context request dies at ~420s on the gateway→Mac path

**Status**: Backlog — measured 2026-09-20 running `064`'s context-escalation drill (T038). Cause not
yet identified.
**Consequence**: `hermes-deep` advertises a 262,144-token context window that cannot be reached with
a cold prompt through the gateway.

## What was measured

Same ~108k-token prompt (589,902 chars) in four configurations:

| path | result |
|---|---|
| Mac's LiteLLM directly, `reasoner` | **200 in 396.8s**, `prompt_tokens=108615` |
| gateway `hermes-deep`, **cold**, `timeout: 180` | `408 Timeout` at 180.3s — the gateway's own limit |
| gateway `hermes-deep`, **cold**, `timeout: 1200` | **connection error at 420.0s** |
| gateway `hermes-deep`, **cold**, `timeout: 1200`, `stream: true` | **connection error at 433.0s, zero SSE events** |
| gateway `hermes-deep`, **warm** (identical prompt re-sent) | **200 in 3.8s** |

The gateway logged `InternalServerError: OpenAIException - Connection error.. Received Model
Group=hermes-deep`, not a timeout. So above roughly 400s the cross-host request loses its connection
from some layer that is not either end's configured request timeout — the Mac's own LiteLLM allows
`request_timeout: 2400`, and the gateway's per-deployment timeout was 1200s at the time.

Streaming does not help: **zero** SSE events arrived before the failure, so nothing is emitted during
prefill and the flow is quiet either way.

## What has been ruled out, and what has not

- **Not the gateway's request timeout.** At 180s it failed cleanly at 180.3s with `408`; raising it to
  1200s moved the failure to ~420s and changed its shape to a connection error.
- **Not the Mac's LiteLLM request timeout** — `request_timeout: 2400` in its config.
- **Not simply "any request over 400s"** — the same-host call succeeded at 396.8s, which is close
  enough to the ceiling that it does not discriminate.
- **An idle-flow timeout is the obvious suspect and is NOT yet confirmed.** A probe that held a
  cross-host TCP connection open and sent one byte every 30s survived 660s — but sending a byte every
  30s is exactly what prevents an idle timeout from firing, so that probe was badly designed and
  proves little. A correct version must hold the connection *completely* silent.

Remaining candidates: Docker Desktop's port forwarder on the Mac (`com.docker.backend` proxies
`0.0.0.0:4000`), the macOS packet filter's state timeout for a quiet flow, or the router's NAT/conntrack
table. All three sit outside this repo, and two are MDM-managed.

## Why it matters beyond the drill

`enable_pre_call_checks` decides whether to escalate using the **declared** `context_window`. A
declared 262144 that cannot actually be served means the gateway accepts requests it will fail, which
is the "configured and inert" failure mode `064` has hit repeatedly — here inverted into
"configured and unservable".

It also means **the >131k escalation path is untested**: a request never survives long enough to reach
`reasoner`'s window boundary, so the Mac's `context_window_fallbacks: reasoner →
Qwen3.8-27B-8bit:qwen-long` has never been exercised end to end. What *is* confirmed is that the Mac's
pre-call check is live — a 431k-token prompt was correctly refused with "No models have context window
large enough for this".

## Suggested first step

Hold a **silent** cross-host TCP connection open from the LXC to the Mac's `:4000` and time how long
it survives with no bytes in either direction. If it dies near 400-430s, the ceiling is an idle-flow
timeout and the fix is either a keepalive (TCP or application-level) or raising the offending timer.
If it survives, the cause is inside Docker Desktop's forwarder or the Mac's LiteLLM under load, and
the next probe is a large request sent from a second LAN host to rule the LXC out.

Until then, the honest options are to declare a `context_window` for `hermes-deep` that reflects what
completes cold (~100k), or to document the ceiling and leave the declaration aspirational. The second
is what is in place today, deliberately, because the warm path genuinely does serve far more.
