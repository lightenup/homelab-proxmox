# Contract — how Hermes uses, and amends, the `064` gateway

**Feature**: `065-hermes-ai-workspace` | Satisfies FR-007, FR-008, FR-011, FR-015, FR-016

`064` is closed. This feature changes it. That change is a contract between the two features and is
recorded in both.

## What Hermes may do

1. **Address capability aliases only.** Never a provider model ID, never the inference host
   directly. The gateway's FR-002 already refuses raw provider IDs; this contract is the intent
   behind that refusal.
2. **Present exactly one credential** — the Hermes client key, from the vault. Hermes holds no
   provider credential of its own.
3. **Stay inside its request allowance.** The key is rate-limited. Hermes generates more requests
   than a human does: every conversation may add housekeeping calls on top of the owner's prompt.

## What `064` must gain

| change | why |
|---|---|
| An **embedding** capability alias, backed by an embedding model on the inference host | FR-015/016 — retrieval must run on the owner's hardware |
| A **reranking** capability alias | Research R-002 — the inference host serves `/v1/rerank`, and hybrid retrieval uses it |
| The Hermes client key's **permitted model scope extended** to both new aliases | Without it the key is refused at first use. The scope is what makes `064`'s FR-002 real; widening it is deliberate, not incidental |
| `064`'s **preflight and doctor updated** for the new aliases | Otherwise the additions are unvalidated and invisible to the health check |

**Sequencing**: the gateway amendment and the inference-host models must both land before the
retrieval acceptance criteria (SC-007) can pass. Chat, tools, search and scheduling do not depend on
them and can be accepted first.

## Rate discipline (FR-011, SC-008)

The client key's allowance sits below the gateway-wide cap, which sits below the sum of all client
allowances — the gateway's own sizing rule. Hermes must not be the client that makes that cap bind
for everyone else.

- Housekeeping calls MUST be pointed at the cheapest alias, or disabled.
- The allowance MUST be reviewed against **measured** usage from gateway metrics. Raising the limit
  before measuring hides the problem rather than solving it.
- Embedding a large document set competes with interactive chat for the same allowance. Bulk
  indexing is not an interactive operation and should not be treated as one.

## Failure behaviour

When the inference host is away, every request through the gateway fails clean — an error naming
the unreachable backend, never a hang. `064` has no fallback tier by design, so this is the only
behaviour available, and Hermes must surface it rather than retry into a wall (FR-009, FR-010).

**This applies to retrieval too.** A document question with no embedding model available must fail
readably, not quietly answer without the document (spec US-6 AS-3).
