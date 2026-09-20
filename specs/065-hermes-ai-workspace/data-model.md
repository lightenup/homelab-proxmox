# Data Model — Hermes

**Feature**: `065-hermes-ai-workspace` | **Date**: 2026-09-20

This feature writes no application code, so the "data model" is the **configuration the operator
edits** plus the **state the running service accumulates**. Both are specified here because both
have rules that must hold, and both are things a future change can silently break.

---

## Entity: Service configuration

Lives in `ansible/group_vars/services/vars.yml`. The single artefact an operator edits.

| Field | Type | Rules |
|---|---|---|
| `hermes_ip` | string | `192.168.1.221`. Defined once, centrally; never repeated in a role or template (Constitution § Networking). |
| `hermes_version` | string | Pinned image tag. MUST NOT be empty or `latest`. |
| `hermes_searxng_version` | string | Same rule. Pinned independently of the application. |
| `hermes_port` | integer | Published only to the LXC; the public surface is the reverse proxy. |
| `hermes_gateway_base_url` | string | The `064` gateway's OpenAI-compatible endpoint. |
| `hermes_task_alias` | string | Capability alias used for housekeeping calls. MUST be the cheapest alias (FR-011). |
| `hermes_embedding_alias` | string | Capability alias for embeddings. MUST exist in `064`'s mapping. |
| `hermes_reranking_alias` | string | Capability alias for reranking. Same rule. |
| `hermes_mcp_servers` | list | See below. |
| `hermes_data_dir` | string | Local disk. MUST NOT resolve under an NFS mount (FR-019). |

### Validation (preflight — the deploy fails, it does not warn)

1. Both image tags pinned and non-`latest`.
2. `hermes_data_dir` is not on an NFS mount.
3. Every alias named (`task`, `embedding`, `reranking`) exists in `064`'s alias mapping **and** is
   within the Hermes client key's permitted model scope. An alias the key may not call fails at
   first use, not at deploy, which is the worse failure.
4. Every credential referenced resolves to a non-empty vault variable.
5. **`RAG_OPENAI_API_BASE_URL` and `RAG_OPENAI_API_KEY` are both set explicitly.** They do not
   reliably inherit from `OPENAI_API_*` (research R-008 / upstream #22084), and left unset the
   service silently reaches for `api.openai.com` — a broken feature *and* an FR-008 breach. This
   assertion is the difference between the two.
6. `ENABLE_SIGNUP` is false (FR-003). Asserted rather than assumed, because the upstream default is
   true and a version bump could reintroduce it.

---

## Entity: MCP server registration

| Field | Type | Rules |
|---|---|---|
| `name` | string | Display name. |
| `url` | string | Streamable HTTP endpoint. |
| `auth` | enum | `none` \| `bearer`. |
| `credential_env` | string \| null | Vault variable name when `auth: bearer`; never the value (Constitution II). |
| `enabled` | bool | Lets a server be disabled without deleting its configuration. |

**Validation**: `auth: bearer` ⇒ `credential_env` names a non-empty vault variable.

**Initial population**: `market-model` (`auth: none`). `financial-scenario` is **omitted at launch**
— its gate uses a secret baked into a third-party image that this repo does not hold (research
R-008). Adding it later is a list entry, which is exactly what FR-013 requires.

---

## Entity: Workspace state *(runtime — owned by the application)*

| Part | Where | Backed up | Rebuildable |
|---|---|---|---|
| Conversations, accounts, settings, saved prompts, scheduled runs | SQLite on local disk | yes | **no** |
| Uploaded documents | local disk | yes | no — the originals |
| Vector index | local disk | yes | yes, but expensively — re-embedding costs inference time against a rate-limited single host |

All three live under `hermes_data_dir`, bind-mounted so the backup role reaches them. This is the
`financial-scenario` split, for the same reason: SQLite and vector indexes over NFS invite locking
failures and corruption.

**The restore path is an acceptance criterion (SC-006), not a hope.** A backup that has never been
restored is a belief.

---

## Entity: Capability alias *(owned by `064`, consumed here)*

Hermes names capabilities and never models. This feature **adds two** to `064`'s mapping —
embeddings and reranking — and extends the Hermes client key's permitted scope to include them.

That is a change to a closed feature. It belongs in `064`'s own records as well as this one;
see [contracts/gateway-usage.md](./contracts/gateway-usage.md).

---

## Entity: Scheduled run *(runtime)*

| Field | Rules |
|---|---|
| `prompt`, `capability`, `recurrence` | Owned by the account that created it; part of workspace state. |
| outcome | MUST be distinguishable between "ran and failed" and "never ran" (SC-010). A run that fires while the inference host is away must be visibly failed. |
