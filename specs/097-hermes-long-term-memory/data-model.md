# Data Model: Long-term memory for Hermes (097)

## Bank

One Hindsight bank holds every memory. A second bank holds deploy probes only.

| Bank | Holds | Written by | Read by |
|---|---|---|---|
| `owner` | Every client's turns, the imported Open WebUI memories | `hermes`, `open-webui`, `claude-code` (when `readwrite`), `control-plane` (web UI), `backup` (import only) | Every key |
| `deploy-probe` | One synthetic sentence per deploy, deleted at once (research R-019) | `backup` | `backup` |

Bank settings on `owner`: retain extraction `chunks`, observations off, auto-consolidation off,
embedding `hermes-embed` (1024 dimensions). A change of embedding model is not done in place:
export, wipe and import re-embed with the new model (spike portability test, FR-018).

## Memory document

One per conversation, appended per turn.

| Field | Source | Notes |
|---|---|---|
| `document_id` | adapter, then server | Sent: `<session_id>` (Hermes), `owui-<chat_id>` (Open WebUI), `cc-<session_id>` (Claude Code). Stored per turn: `<session>--<sha256 of the turn>[:16]` (T071, research R-012). Imports keep theirs: `owui-memory-<id>`, `hermes-builtin-memory-<hash>` |
| content | adapter | JSON array of turns, per [turn-format.md](./contracts/turn-format.md) |
| `update_mode` | adapter | `append` |
| `context` | adapter | Fixed string per client, for example "conversation between Hermes Agent and the User" |
| `metadata` | adapter | `retained_at`, `turn_index`, `platform`; never used for attribution |

## Memory unit (chunk)

What recall returns and what the owner corrects or forgets.

| Field | Notes |
|---|---|
| `id` | Hindsight unit id. Used by `update_memory` and `invalidate_memory` |
| `text` | Up to 3,000 characters of verbatim turn text, carrying the `User:`/`Assistant:` labels (FR-014) |
| `fact_type` | Always `world` in chunks mode. The adapters recall `["world"]` |
| `tags` | Exactly one `client:<id>` (`hermes`, `open-webui`, `claude-code`, `control-plane`), stamped by the server (research R-002); `session:<…>`; for imports, `origin:open-webui-memory` |
| `state` | `active` or `invalidated` (removed from recall, kept for audit, reversible) |
| `created_at` | Server time |

**Attribution rule**: the writing client is the unit's `client:*` tag. Document-level tags and
metadata are client-supplied and never trusted for attribution.

**State transitions**:

```text
          retain                       update_memory (correct / redact a fact)
 (none) ─────────▶ active ◀────────────────────────────────┐
                     │  └──────────────────────────────────┘
                     │ invalidate_memory (forget the turn)
                     ▼
                 invalidated ── revert (admin runbook) ──▶ active
                     │
                     │ delete_document (web UI or admin runbook, whole conversation)
                     ▼
                  (gone; still in backups until retention ages them out)
```

## Client

Rendered to `clients.json` on the memory LXC (root, 0400, mounted read-only). Only key hashes are
stored there.

| `id` | Scope | Key (vault) | Held by |
|---|---|---|---|
| `hermes` | `readwrite` | `memory_client_hermes_key` | Agent plugin config, agent MCP (`AUXILIARY_MCP_MEMORY_API_KEY`) |
| `open-webui` | `readwrite` | `memory_client_open_webui_key` | Filter valves, Open WebUI MCP connection |
| `claude-code` | `readwrite`, switchable to `readonly`, or absent (revoked) | `memory_client_claude_code_key` | Vault, Mac keychain, Bitwarden (Linux laptop) |
| `control-plane` | `curator` | `memory_client_control_plane_key` | The web UI container's environment only (research R-020) |
| `backup` | `admin` | `memory_admin_key` | Root-only file on the memory LXC; restore drill; import task |

Validation rules:

- `id` matches `^[a-z][a-z0-9-]{1,31}$` and is unique. Hashes are unique.
- Exactly one `admin` client.
- Every key starts with `hmem_` (log redaction, research R-015). Keys are at least 32 random
  bytes.
- Removing a client is revocation. Changing a scope takes effect at the next `memory` deploy (the
  file is read at start-up).

## Scope matrix

Enforced by the validator as an allowlist: an operation not listed for a scope is refused
(research R-001). The contract test matrix is in [memory-access.md](./contracts/memory-access.md).

| Operation | `readonly` | `readwrite` | `curator` | `admin` |
|---|---|---|---|---|
| recall and every bank read (memories, documents, chunks, tags, stats, operations, timeline, graphs, entities, knowledge-base and feature views), except bank config and the bulk knowledge-base export | yes | yes | yes | yes |
| retain | no | yes, tag stamped | yes, tag stamped | yes, supplied client tag kept |
| update memory, invalidate memory, revert, and the graph and vector-index maintenance an edit or delete submits | no | yes | yes | yes |
| delete document, retry operation, read bank config | no | no | yes | yes |
| export, import, create bank, change bank config, clear bank, delete bank | no | no | no | yes |
| webhooks, reflect, consolidation, mental-model create or refresh, directives, reprocess, entity regeneration, clone, knowledge-base writes, the bulk knowledge-base export | no | no | no | no |

## Web UI login

| Item | Value |
|---|---|
| Login key | `memory_ui_access_key` (vault, owner's password manager), `hmem_` prefix |
| Session | HMAC cookie, 24 h, `SameSite=Lax`, `Secure` |
| Without a key | The role refuses to deploy (upstream would serve the UI open) |
| API identity | `control-plane` (`curator`), server-side only; the browser never holds an API key |

## Hostnames

| Host | Serves | Portal tile |
|---|---|---|
| `memory.hus-sky.no` | Web UI (port 9999) | Yes, "Memory" |
| `memory-api.hus-sky.no` | REST and MCP (port 8888) | No |

## Gateway client

| Alias | Key (vault) | Models | rpm | Budget |
|---|---|---|---|---|
| `memory` | `llm_router_client_memory_key` | `hermes-embed`, `hermes-rerank` | 30 | $1 / 30 days |

Lab-switch class: `internal` (research R-011).

## Backup set (nightly, NAS `homelab_memory`)

| File | What | Restore path |
|---|---|---|
| `db.dump` | `pg_dump -Fc` of the whole store, embeddings included | `pg_restore` (fast, exact) |
| `owner-export.zip` | Hindsight document transfer: `manifest.json` (schema 1) plus one JSON per document (text, chunks, tags, metadata), no embeddings | Import into any bank, re-embedded (portable, FR-018) |
| `stats.json` | `total_documents`, `total_nodes` at backup time | Restore drill comparison |
| `drill-probes.json` | Up to 3 `{unit_id, query}` picked at random from the store at backup time | Restore drill recall check (never committed to the repo) |
| `docker-compose.yml`, `clients.json` | Configuration (hashes only) | Reference |

Retention follows `service_backup` (7 daily, 4 weekly, 6 monthly).
