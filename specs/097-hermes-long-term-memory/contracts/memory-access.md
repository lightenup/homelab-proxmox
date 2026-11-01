# Contract: memory endpoint access (097)

Base URL `https://memory-api.hus-sky.no`, published through Caddy (TLS) and reachable only from the
LAN and the tailnet. Every request carries `Authorization: Bearer hmem_…`. The web UI is at
`https://memory.hus-sky.no` behind its own login (research R-020). It calls this API server-side
as the `control-plane` client.

## Surfaces

| Surface | Path | Used by |
|---|---|---|
| Health | `GET /health` (unauthenticated, database check only) | Monitoring, `scripts/healthcheck/memory.sh` (direct `memory_ip:8888`) |
| Metrics | `GET /metrics` (direct `memory_ip:8888`, not routed by Caddy) | Prometheus |
| REST | `/v1/default/banks/{bank}/…` | Adapters, backup, import, restore drill, deploy probe |
| MCP | `/mcp/owner/` (Streamable HTTP, bank bound by the path) | Agent, Open WebUI, Claude Code (interactive browse and edit) |
| Web UI | `https://memory.hus-sky.no` (login), `GET /api/health` unauthenticated on `memory_ip:9999` | Owner's browser; health check |

**Verified locally 2026-10-31** (stock `1.1.0-slim` with the shim): `/health` and `/metrics`
answer 200 without a key, `/v1/...` without a key answers 401 and MCP without a key answers 401.
The LAB rehearsal re-checks it on the LXC.

**Export**: Hindsight 1.1.0 runs no validator hook on document export, so any authenticated key
can export the bank, not only `admin` (research R-001 "Not gated by the validator"). The export
is asynchronous: `POST .../document-transfer/export` returns an `operation_id`, and the archive
is downloaded from the operation's `result_metadata.download_url`.

## REST operations used

| Operation | Method and path | Caller | Scope needed |
|---|---|---|---|
| Recall | `POST /v1/default/banks/owner/memories/recall` | Every adapter | any |
| Retain | `POST /v1/default/banks/owner/memories` (`async: true` for adapters, `false` for probes) | Adapters, import | `readwrite`, `admin` |
| Bank stats | `GET /v1/default/banks/{bank}/stats` | Backup, drill, deploy probe | any |
| Export | `POST /v1/default/banks/owner/document-transfer/export` | Backup | `admin` |
| Import | `POST /v1/default/banks/{bank}/document-transfer` | Restore drill | `admin` |
| Delete document | `DELETE /v1/default/banks/{bank}/documents/{id}` | Web UI, deploy probe, runbook | `curator`, `admin` |
| Retry operation | `POST /v1/default/banks/owner/operations/{id}/retry` | Web UI, runbook (`MemoryRetainFailures`) | `curator`, `admin` |

Exact request bodies follow upstream's OpenAPI at the pinned version
(`docs/backlog/097-spike/results/hindsight-portability/openapi-routes.txt`).

## MCP tools exposed

`HINDSIGHT_API_MCP_ENABLED_TOOLS` limits the endpoint to these six tools, out of 39:

| Tool | Purpose | Scope needed |
|---|---|---|
| `recall` | "What do you remember about my car?" | any |
| `list_memories` | Browse | any |
| `list_tags` | Show which clients wrote what | any |
| `retain` | Explicitly remember something | `readwrite` |
| `update_memory` | Correct, or forget one fact by redaction | `readwrite` |
| `invalidate_memory` | Forget a whole turn | `readwrite` |

These are never exposed: `delete_document`, `clear_memories`, `delete_bank`, `reflect`, the
mental-model tools, the knowledge-base tools and the directive tools.

## Responses to refusals

| Case | HTTP | MCP |
|---|---|---|
| No key, unknown key, revoked key | 401 | 401 at session start |
| Scope too low (for example a read-only retain, or a whole-bank operation without `admin`) | 403, reason `scope <scope> may not <operation>` | Tool error with the same reason |
| Operation refused for every scope (webhook, reflect, consolidation, mental model, directive, clone) | 403, reason `<operation> is disabled` | Tool not exposed |
| Forged `client:*` tag from a non-admin key | Accepted. The tag is replaced with the caller's | Same |

## Access matrix (tests: `python/tests/memory_access/`, harness, quickstart § 6)

Rows are callers, columns are operations. ✓ means allowed, ✗ means refused (403), and 401 means
not authenticated.

| Caller | recall | retain | update / invalidate | delete document / retry | export / import / bank config | clear / delete bank | webhook / reflect / consolidate |
|---|---|---|---|---|---|---|---|
| `hermes` | ✓ | ✓ (tag `client:hermes`) | ✓ | ✗ | ✗ | ✗ | ✗ |
| `open-webui` | ✓ | ✓ (tag `client:open-webui`) | ✓ | ✗ | ✗ | ✗ | ✗ |
| `claude-code` (`readwrite`) | ✓ | ✓ (tag `client:claude-code`) | ✓ | ✗ | ✗ | ✗ | ✗ |
| `claude-code` (`readonly`) | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| `claude-code` (revoked) | 401 | 401 | 401 | 401 | 401 | 401 | 401 |
| `control-plane` (`curator`, web UI) | ✓ | ✓ (tag `client:control-plane`) | ✓ | ✓ | ✗ | ✗ | ✗ |
| `backup` (`admin`) | ✓ | ✓ (supplied tag kept) | ✓ | ✓ | ✓ | ✓ | ✗ |
| no key or wrong key | 401 | 401 | 401 | 401 | 401 | 401 | 401 |
| async worker (`internal`) | n/a | ✓ (already validated at submit) | n/a | n/a | n/a | n/a | n/a |
