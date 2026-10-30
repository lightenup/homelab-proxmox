# Hindsight 1.1.0 (chunks mode): second-client and export round-trip, 2026-10-30

Client A = REST from llmproxy; client B = MCP Streamable HTTP from llmproxy (`llmproxy/portability.py`).
Zero chat-LLM calls: 20 embeddings + 10 rerank in total (`05-calls.txt`).

| test | result | evidence |
|---|---|---|
| 1 per-client keys | FAIL as shipped | `ApiKeyTenantExtension` compares one `HINDSIGHT_API_TENANT_API_KEY`; no identity, revocation or scope. Extension points exist: custom `TenantExtension` (RequestContext carries `api_key`, `api_key_id`, `tenant_id`) + `OperationValidatorExtension.validate_retain/recall` for read-only and enforced tags |
| 2 REST retain + provenance | PASS (self-declared) | 6 items, 200 in 0.1 s; `tags` and `metadata` stored per unit and document, listed by `/tags`. Provenance is whatever the client sends; server does not bind it to the key |
| auth | PASS | REST and MCP without key / wrong key: 401 |
| 3 MCP second client | PASS | initialize 200 (session id), 3/3 recalls correct incl. NO→EN and EN→NO; MCP retain (tag `client:claude-code`) recalled by client A over REST |
| tool count | 36 (FR-009 FAIL by default) | allowlist: `HINDSIGHT_API_MCP_ENABLED_TOOLS` (server) and per-bank `mcp_enabled_tools` |
| 4 export → wipe → import | PASS | `POST .../document-transfer/export` → ZIP (3,972 B; `manifest.json` schema_version 1 + one JSON per document: original text, chunks, facts, tags, metadata; no embeddings, no DB ids). Postgres volume deleted, fresh server, `POST .../document-transfer` → 7/7 documents and facts, re-embedded (8 embed calls), 6/6 recalls correct, both client tags intact. 2.0 s each way |
| re-embed path | PASS | import re-embeds with the target bank's model; an in-place dimension change refuses (`migrations.py`: delete + restart) |
| pg_dump | taken, restore not tested | `-Fc` 128 KB, <1 s |
| RAM (idle, 7 docs) | hindsight 319 MiB, postgres 69 MiB, llmproxy 19 MiB | `04a-export.log` |
