# Amendment: two capability aliases added for Hermes retrieval

**Date**: 2026-09-20 · **Amends**: `ansible/group_vars/services/vars.yml`
(`llm_router_aliases`) · **Status**: config landed, unexercised until the Mac-side work below
lands · **Driven by**: spec `065-hermes-ai-workspace`, contracts/gateway-usage.md

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

## What did NOT change, and why that is a real gap

**`provider_model: "openai/embed"` and `"openai/rerank"` are placeholders.** They must match
whatever role-alias names the Mac's own `~/Development/private/local-llm/proxy/litellm-config.yaml`
gives the embedding model and reranker once loaded — that is Mac-side work (065 tasks
T055/T056), outside this repo, and has not happened yet. Verify with `GET /v1/models`
against the Mac's router before trusting these names.

**`scripts/healthcheck/llm-router-doctor.py` was not extended.** contracts/gateway-usage.md
calls for "064's preflight and doctor updated for the new aliases" — the preflight half is
covered generically (065's own preflight asserts these alias names exist in
`llm_router_aliases`), but the doctor script's live, behavioural checks were not touched.
Recorded here rather than silently skipped, the same way 065's own doctor honesty style
would call it: this doctor update is **open**, and is gated on the same Mac-side work as the
aliases themselves — there is nothing live to check against until an embedding/reranker
alias actually answers.

**Re-arm when**: T055/T056 land on the Mac. At that point: (1) fix `provider_model` above to
match the real alias names, (2) extend `llm-router-doctor.py` with an `alias answers` check
for `hermes-embed`/`hermes-rerank` mirroring the existing chat-alias checks, and (3) run
065's SC-007 drill.
