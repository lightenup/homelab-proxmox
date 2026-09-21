# Amendment: two capability aliases added for Hermes retrieval

**Date**: 2026-09-20, **completed 2026-09-21** · **Amends**: `ansible/group_vars/services/vars.yml`
(`llm_router_aliases`) · **Status**: **live and verified end to end** · **Driven by**: spec `065-hermes-ai-workspace`, contracts/gateway-usage.md

## Why

065 (Hermes) needs embeddings and reranking for document Q&A (FR-015, FR-016), and research
R-002 there decided both run on the inference host through this gateway, as two more
capability aliases — never a third-party embedding API (FR-008).

## What changed here

Two entries added to `llm_router_aliases`: `hermes-embed` and `hermes-rerank`, both
`tier: local`, addressed at the Mac by mDNS name like every other alias (FR-013), and both
`health_checked: false` — the background health check probes with a chat-style call, and
sending that against an embeddings/rerank-only deployment is untested against the pinned
LiteLLM version. Absence is still caught at first real use (FR-009); only the background
probe is skipped.

**No client-scope change was needed.** `virtual_keys.yml` scopes every client key to *all*
`llm_router_aliases` names uniformly — there is no per-client allowlist — so adding the two
aliases here already extends the Hermes key's permitted scope. This is contracts/gateway-usage.md's
"the Hermes client key's permitted model scope extended to both new aliases" row, done
implicitly by the existing mechanism rather than by a second edit.

## Completed 2026-09-21 — what the placeholders became

Both aliases now resolve to real models on the inference host:

| alias | Mac role alias | oMLX model | verified |
|---|---|---|---|
| `hermes-embed` | `embed` | `Qwen3-Embedding-0.6B-8bit` (1024 dims, 0.62 GB) | 200 through the gateway |
| `hermes-rerank` | `rerank` | `Qwen3-Reranker-0.6B-mxfp8` (0.60 GB) | 200, relevant 1.0 / irrelevant 5e-06 |

Downloaded through oMLX's own admin API (`hf_download`, wrapped by local-llm's client — the
convention `quant_compare.py` already uses), so the app that owns `~/.omlx/models` did the
writing. oMLX's discovery classified both correctly as `engine: embedding` / `engine: reranker`.
No profile entries were needed: profiles carry sampling and thinking fields, which an embedder
has neither of, and `definitions.py` is scoped to the 27B.

`access_groups: ["local"]` on both Mac-side entries was load-bearing — without it the gateway's
key is refused with `key not allowed to access model … models=['local']` at first use.

### The provider prefixes are not interchangeable, and this cost real time

`hermes-embed` uses `openai/`. `hermes-rerank` **cannot**:

- **`openai/rerank`** → `Unsupported provider: openai` from `rerank_api/main.py`. LiteLLM's
  rerank API accepts only a fixed provider set and `openai` is absent. Fails at **call** time.
- **`litellm_proxy/rerank`** → **404**. Looks like the obvious choice for chaining to another
  LiteLLM proxy; there is no `litellm_proxy.rerank` module, so it falls through to a generic path.
- **`hosted_vllm/`** → would **rewrite** `/v1/rerank` to `/rerank` and miss oMLX's route.
- **`infinity/`** → correct. It appends `/rerank` to an api_base already ending in `/v1`.

One more, Mac-side: oMLX returns `document` Cohere-shaped as an object, and infinity's handler
assumes a bare string and wraps it, so LiteLLM rejects its own response
(`results.0.document.text: Input should be a valid string`). `return_documents: false` fixes it
and costs nothing — Open WebUI's `ExternalReranker` reads only `index` and `relevance_score`.

## Still open

**`scripts/healthcheck/llm-router-doctor.py` was not extended** for the two new aliases. Now
that they answer, there is finally something live to check — an `alias answers` row for each,
mirroring the chat-alias checks. Recorded rather than silently skipped.

**Remaining**: extend `llm-router-doctor.py`, and run 065's SC-007 document-Q&A drill (T061),
which is now unblocked for the first time.
