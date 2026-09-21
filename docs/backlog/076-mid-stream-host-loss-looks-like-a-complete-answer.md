# Losing the inference host mid-stream produces a truncated answer marked "complete"

**Status**: Backlog — measured 2026-09-21 running spec `065`'s T089.
**Impact**: **Silent data corruption of the conversation record.** A generation interrupted
by the Mac going away is delivered as a normal, successful assistant message: truncated
mid-sentence, flagged `finish_reason: "stop"`, terminated with `data: [DONE]`, zero error
chunks. Neither Hermes nor the owner has any signal that the answer is incomplete.

**This is more serious than [`075`](./075-first-request-hangs-when-inference-host-away.md).**
A hang is honest — the owner knows something is wrong. This is dishonest: it produces a
plausible-looking answer that is missing 73% of itself, and stores it in the chat history
where it is indistinguishable from a real one weeks later.

## What was measured

A streaming completion against the gateway with the real Hermes client key, asking for a
~1200-word essay (`max_tokens: 1500`). Nine seconds in, with tokens flowing normally, the
Mac's TLS terminator was stopped — the same "host goes away" event as `075`, but *during* the
response instead of before it.

| | |
|---|---|
| streaming normally at | 11,006 bytes after 9s |
| host pulled away at | t+9.099s |
| stream ended at | **t+9.202s — 0.1s later** |
| curl exit code | **0 (clean)** |
| `data: [DONE]` markers | **1** |
| chunks mentioning an error | **0** |
| `finish_reason` values seen | **`"stop"`** |
| answer delivered | **322 words of ~1200 — 27%** |
| final text | `…attributed to the 13th century. While` |

The last content chunk ends mid-sentence, and the very next chunk declares the generation
finished normally.

## Why this is the failure US-5 exists to prevent

Spec `065`'s user story 5 is titled *"Hermes degrades honestly when models are unavailable"*.
Every other observed behaviour honours that: the UI stays up, recovery is automatic, and the
eventual error names the cooled deployment. **This one degrades dishonestly**, which is the
one outcome the story rules out. T089 was written precisely to catch "a half-delivered
response that looks complete", and that is exactly what it found.

The consequence is not confined to the moment. Open WebUI receives a well-formed, successful
SSE stream, so it has nothing to detect: it will render the message normally and persist it
to the conversation store. The chat history then contains answers that are silently missing
their conclusions, caveats or corrections — with no marker distinguishing them.

## Likely mechanism, not confirmed

When the terminator dies, the TCP connection from the gateway to the Mac simply closes.
End-of-stream on a socket looks identical to "upstream finished", so the gateway appears to
synthesise the terminal chunk itself rather than relaying one. The Mac cannot have sent
`finish_reason: "stop"` — it was mid-sentence when it vanished.

**Unverified.** Distinguishing "the gateway synthesised a terminal chunk" from "something
upstream sent one" needs a packet-level or debug-log look at the gateway during the event.
Worth doing before choosing a fix, because it determines whether this is a LiteLLM
configuration matter, a LiteLLM defect, or ours.

## Directions, none verified

1. **Detect the absence of an upstream terminal chunk.** The honest behaviour is to emit an
   error chunk when the upstream connection closes without having delivered a `finish_reason`.
   Whether LiteLLM can be configured to do this, or whether it is an upstream fix, is the
   first thing to establish.
2. **Compare against `stream_options: {"include_usage": true}`.** A usage chunk is normally
   emitted only on genuine completion, so its absence may be a reliable client-side tell —
   which would let Hermes distinguish the cases even if the gateway cannot.
3. **Client-side length sanity.** Weakest option, and guessy: a response far under
   `max_tokens` that ends without terminal punctuation is suspicious but not conclusive.

Option 1 is the correct fix; option 2 is worth testing because it might be free.

## Relationship to 075

Same trigger, opposite symptom, and they want opposite things from a fix:

| | `075` | this |
|---|---|---|
| when the host leaves | before the request | during the response |
| symptom | hangs ≥90s | ends in 0.1s |
| honesty | honest but slow | **fast and wrong** |

Fixing `075` by shortening timeouts does nothing for this. This one is about **what the
stream says when it ends**, not how long it takes to end.
