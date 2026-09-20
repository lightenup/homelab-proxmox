# Quickstart — Hermes

**Feature**: `065-hermes-ai-workspace` | **Written**: 2026-09-20

Deploy, verify, and run the drills that make the acceptance criteria real rather than assumed.

> Written before implementation. Every command here is a **claim to be checked**, not a recording of
> something that worked — unlike `064`'s quickstart, which was rewritten against a live deploy.
> Update it as you go, and treat a step that needed changing as information worth keeping.

## 0. Prerequisites

**On the inference host** — four session-scoped processes, plus two new models:

| | |
|---|---|
| Existing four | `064`'s [`mac-side.md`](../064-llm-router/mac-side.md) — nothing auto-starts |
| **New**: embedding model | loaded in oMLX, exposed through the Mac's gateway |
| **New**: reranker | same |

**In `064`** — the two new capability aliases exist and the Hermes client key's scope includes them.
See [contracts/gateway-usage.md](./contracts/gateway-usage.md).

**In the vault** — the gateway client key, the admin bootstrap credential, and any MCP credential.

## 1. Deploy

Through the pipeline, as every service is. Plan first.

## 2. Verify the deploy

- The stack is up and the published port answers from the LXC.
- The public hostname resolves, serves a certificate, and presents a **login** before anything else.
- `ENABLE_SIGNUP` is off — confirm by attempting to register, not by reading the config.

## 3. The drills

These are the acceptance criteria. Each maps to a success criterion in [spec.md](./spec.md).

| # | drill | proves |
|---|---|---|
| 1 | Sign in from a phone on mobile data; send a prompt; add to home screen | SC-001 |
| 2 | Request every surface unauthenticated — chat, model list, documents, **and the programmatic endpoint** | SC-002 |
| 3 | Ask a question only answerable through an MCP server | SC-003 |
| 4 | Change a capability alias in `group_vars`; redeploy; confirm no template or code changed | SC-004 |
| 5 | **Log the inference host out.** Send a prompt; time the error; confirm the UI still loads and history is readable | SC-005 |
| 6 | Destroy the LXC, rebuild from code, restore, confirm everything returns | SC-006 |
| 7 | Upload a document, ask about it, confirm the citation — and that nothing left the estate | SC-007 |
| 8 | One hour of representative use; read the request rate from gateway metrics | SC-008 |
| 9 | A prompt whose response takes 15 minutes | SC-009 |
| 10 | Schedule a run; let it fire while the inference host is away | SC-010 |
| 11 | Inspect the diff: no bespoke application source | SC-011 |
| 12 | Speak a question on a phone, hear the answer | SC-012 |
| 13 | Ask something requiring current information; confirm citations and that no commercial search provider was called | SC-013 |
| 14 | Call the programmatic endpoint from another homelab service | SC-014 |
| 15 | A scheduled prompt runs unattended and its output is waiting | SC-015 |

### Drill 5 is the one that matters

It is the difference between a service that degrades honestly and one that hangs. `064` has no
fallback tier, so the failure is unavoidable — the only question is whether it is **legible and
fast**. Read a hang as the failure, not the error.

### Drill 8 needs a definition before it is run

"Representative use" must be agreed in advance or the measurement means nothing. Decide what an
hour of real use looks like — how many conversations, whether documents are indexed — and record it
alongside the result.

## 4. Things that will probably bite

Collected from the research and from `064`'s scars.

- **Retrieval silently reaching for `api.openai.com`.** `RAG_OPENAI_API_BASE_URL` and
  `RAG_OPENAI_API_KEY` do not reliably inherit from `OPENAI_API_*` (upstream #22084). Left unset,
  retrieval is both broken and a breach of FR-008. Preflight asserts both.
- **The proxy truncating a long generation.** `proxy_timeout` must clear 20 minutes. The symptom
  looks like a model failure.
- **Housekeeping calls exhausting the request allowance** before the owner's own prompts do.
- **Monitoring deployed through the lab path**, which renders an empty configuration over the live
  one — [backlog `072`](../../docs/backlog/072-lab-monitoring-deploy-wipes-prod.md). Prod path only.
- **The inference host being asleep** during almost any drill, producing a failure that looks like a
  bug in Hermes. Check the host first.
