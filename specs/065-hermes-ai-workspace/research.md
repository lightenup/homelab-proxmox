# Phase 0 Research — Hermes

**Feature**: `065-hermes-ai-workspace` | **Date**: 2026-09-20

Everything below was checked against the live estate or upstream documentation rather than assumed.
One item remains unresolved and is escalated to the plan's Complexity Tracking.

---

## R-001 — Application choice

**Decision**: **Open WebUI**, pinned to a specific non-`latest` tag.

**Rationale**: The deciding factor is not polish, it is transport compatibility. Open WebUI's native
MCP support is **Streamable HTTP only**, and both homelab MCP servers speak exactly that — verified
by probing them: `market-model` at `/mcp` rejects a malformed call with
`Missing session ID` (an MCP protocol error, so the endpoint is live), and `financial-scenario`
returns `401`. No `mcpo` translation layer is needed, which removes a container and a failure mode.
It also ships, as configuration, every capability the spec requires: PWA, automations, SearXNG
search, local Whisper, its own OpenAI-compatible endpoint. That is what satisfies FR-026.

**Alternatives considered**:
- **LibreChat** — broader MCP transports (stdio, SSE) that buy nothing here, and it brings MongoDB
  *and* Meilisearch to operate and back up instead of one SQLite file. Rejected on operational cost.
- **AnythingLLM** — RAG-first; the chat and tool surface is the weaker part. Rejected on fit.

---

## R-002 — Where retrieval runs

**Decision**: Embeddings **and reranking** served by oMLX on the inference host, reached through the
`064` gateway as two new capability aliases.

**Rationale**: oMLX exposes `/v1/embeddings` **and `/v1/rerank`** and supports BERT, BGE-M3 and
ModernBERT; the installed build carries `scheduler.embedding_batch_size` in its settings, so the
capability is present in the deployed version and not just upstream. Keeping inference in one place
matches the owner's "local models exclusively" constraint and gives better quality than a small
CPU model in the container.

**Reranking is in scope because it became nearly free** — the same host, the same gateway, one more
alias, and Open WebUI's retrieval supports hybrid search with an external reranker.

**Accepted cost**: retrieval stops working when the inference host sleeps. In-container CPU
embeddings would have survived that. FR-009's fail-clean rule is therefore extended to retrieval
(spec US-6 AS-3).

**Alternatives considered**: in-container `sentence-transformers` (survives host absence, weaker
quality, ~1–2 GB RAM); a third-party embedding API (violates FR-008).

---

## R-003 — Open WebUI configuration surface

All confirmed against upstream documentation.

| need | variable(s) |
|---|---|
| Gateway backend | `OPENAI_API_BASE_URL`, `OPENAI_API_KEY` |
| Disable self-registration (FR-003) | `ENABLE_SIGNUP=False` |
| Embedding engine (FR-015/016) | `RAG_EMBEDDING_ENGINE=openai`, `RAG_EMBEDDING_MODEL`, `RAG_OPENAI_API_BASE_URL`, `RAG_OPENAI_API_KEY` |
| External reranker (R-002) | `RAG_RERANKING_ENGINE=external`, `RAG_RERANKING_MODEL`, `RAG_EXTERNAL_RERANKER_URL`, `RAG_EXTERNAL_RERANKER_API_KEY` |
| Housekeeping model (FR-011) | `TASK_MODEL_EXTERNAL`, `ENABLE_TITLE_GENERATION` |
| Web search (FR-022) | `SEARXNG_QUERY_URL` |
| Scheduled prompts (FR-025) | `ENABLE_AUTOMATIONS`, `AUTOMATION_MIN_INTERVAL` |

### ⚠ Known upstream defect that this deployment must work around

**`RAG_OPENAI_API_BASE_URL` and `RAG_OPENAI_API_KEY` do not reliably inherit from
`OPENAI_API_BASE_URL` / `OPENAI_API_KEY`** (open-webui issue #22084). The documented behaviour is
that they fall back; the observed behaviour is that they do not.

Left unset, retrieval would silently attempt `https://api.openai.com` — which is both a broken
feature **and an FR-008 violation** (content leaving the estate). **Both pairs MUST be set
explicitly**, and the deployment MUST assert it. This is the same class of failure `064` hit
repeatedly: configuration that reads correctly and does nothing.

---

## R-004 — Housekeeping request volume (FR-011, SC-008)

**Decision**: point `TASK_MODEL_EXTERNAL` at the cheapest capability alias, and disable title
generation unless the owner wants it.

**Rationale**: Open WebUI issues extra model calls per conversation — naming the chat, tagging it,
rewriting search queries. The client key's allowance is 60 requests/minute against a gateway-wide
cap of 65, and the backend is a single machine. Overhead alone can exhaust that during ordinary use.
Measure from gateway metrics (SC-008) before raising any limit — raising the limit first would hide
the problem rather than solve it.

---

## R-005 — Self-hosted search topology

**Decision**: SearXNG as a **second container in the same compose stack on the Hermes machine**, not
its own service.

**Rationale**: Constitution IV (Code Economy). Its own LXC would mean a new address, a new Terraform
root, a new Ansible role, a new monitoring contract, a new backup consideration and a new entry in
every registration point — for a component with exactly one consumer. As a sidecar it inherits all
of those from Hermes and is not published to the LAN at all.

**Revisit if** a second consumer appears; that is the point at which the extra artifacts earn their
keep.

---

## R-006 — State and backup

**Decision**: SQLite plus the vector store on the machine's local disk, bind-mounted so a backup
role can reach it, pushed to the Synology.

**Rationale**: Exactly the split `financial-scenario` already makes, and for the same reason —
SQLite and vector indexes over NFS invite locking failures and corruption. Single user, so Postgres
would be complexity without a consumer (Constitution IV).

**Revisit if** concurrent use ever justifies it; Open WebUI supports Postgres natively.

---

## R-007 — Address and sizing

**Decision**: `192.168.1.221`. `.210`–`.220` are allocated, `.221` is next free.

Sizing is deferred to implementation and must be **measured, not guessed** — the footprint depends
on whether retrieval runs in-container (it does not, per R-002) and on document volume. Start from
the `financial-scenario` allocation and adjust against observed use.

---

## R-008 — RESOLVED: ship with one MCP server; the authenticated one waits on upstream

**Decision (owner, 2026-09-20)**: **Ship with `market-model` only.**

`financial-scenario`'s `/mcp` returns `401` with no `WWW-Authenticate` header, and this repo does
not hold the credential. From `roles/financial_scenario/tasks/preflight.yml`:

> The MCP shared secret is NOT injected here. The auth gate lives in the GUI image's nginx (`/mcp`),
> with the secret **baked into that image** (PFS 044). The mcp service is never published directly,
> so there is no per-deploy MCP token to assert. **Making the secret configurable requires a PFS
> change.**

So FR-012 is satisfiable for `market-model` today and **not** for `financial-scenario`.

**Options**, for the owner to decide:

| option | consequence |
|---|---|
| **Ship with `market-model` only** | FR-012 and SC-003 are met by one server; the second is added later as pure configuration, which FR-013 already requires to be cheap |
| **Extract the baked secret from the image** | Works immediately, but depends on an image internal nobody manages and breaks silently on the next image bump. Not recommended |
| **Make it configurable upstream first** | Correct, and blocks this feature on work in another repository |

**Chosen**: the first. It delivers the capability, proves the pattern end to end, and leaves the
second server as a configuration change once upstream makes it possible.

### The consequence, stated rather than buried

FR-012 requires the system to call tool services **"including those that require a credential"**.
With only `market-model` — which requires none — **the credentialed path is configured but never
exercised at launch**. Spec acceptance scenario US-3 AS-2 ("presents the credential and is not
refused") therefore cannot be demonstrated.

This is the same shape as `064`'s T056/T057: a mechanism that is correctly built and structurally
untestable until something outside the feature changes. Handle it the same way — build the
credential path, assert its configuration in preflight, and record the acceptance scenario as
**not-verifiable at launch** with its re-arm condition, rather than quietly dropping the
requirement or claiming a pass it did not earn.

**Re-arm when**: the `personal-financial-scenarios` image makes its MCP secret configurable. At
that point the work here is one list entry in `hermes_mcp_servers` plus a vault variable — which is
precisely the cheapness FR-013 demands, and adding it will itself be the test of FR-013.

---

## Sources

- [Open WebUI MCP support](https://docs.openwebui.com/features/extensibility/mcp/)
- [Open WebUI environment configuration](https://docs.openwebui.com/reference/env-configuration/)
- [open-webui issue #22084 — `RAG_OPENAI_*` do not inherit](https://github.com/open-webui/open-webui/issues/22084)
- [Open WebUI automations](https://docs.openwebui.com/features/chat-conversations/chat-features/automations/)
- [oMLX](https://omlx.ai/) — embedding and reranker model support
- Live probes of `market-model` and `financial-scenario` MCP endpoints, 2026-09-20
- `ansible/roles/financial_scenario/tasks/preflight.yml`, `templates/docker-compose.yml.j2`
