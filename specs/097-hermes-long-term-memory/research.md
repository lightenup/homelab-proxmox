# Research: Long-term memory for Hermes (097)

Findings come from three sources:

- Upstream source, checked 2026-10-31:
  - Hindsight server at tag `v1.1.0` (`a5a619b`), the latest release. Paths are under
    `hindsight-api-slim/hindsight_api/`.
  - The Hermes plugin at `integrations/hermes/v1.2.1` and `v1.2.3`. Paths are under
    `hindsight-integrations/hermes/`.
  - `hermes-agent` `v0.21.6`.
  - Open WebUI `v0.11.3` (pinned), `v0.12.5` and `v0.6.43`.
- The repository as of `64914c4`.
- The 2026-10-30 spike and portability test
  ([`docs/backlog/097-spike/`](../../docs/backlog/097-spike/)).

Line numbers are from those tags. Anything not verified is marked **UNVERIFIED**, with the step
that verifies it.

## R-001: Per-client credentials (FR-011, FR-012)

- **Finding**:
  - Upstream's `ApiKeyTenantExtension` compares one `HINDSIGHT_API_TENANT_API_KEY` (spike).
  - **Loading**: an extension is loaded from `HINDSIGHT_API_<KIND>_EXTENSION=module:Class`, and
    every other `HINDSIGHT_API_<KIND>_*` variable reaches its constructor as `config`, lower-cased
    with the prefix stripped (`extensions/loader.py:106-153`).
  - **Tenant extension**: `TenantExtension.authenticate(ctx) -> TenantContext` may set
    `ctx.api_key_id` and `ctx.tenant_id` (`extensions/tenant.py:84`). MCP runs the same hook
    (`authenticate_mcp`, defaults to `authenticate`, `:205`), and `AuthenticationError` gives 401
    on both surfaces.
  - **Operation validator**: `OperationValidatorExtension` sees every operation, MCP included.
    MCP tools call the same engine methods (`mcp_tools.py:465-482`). Hooks used here:
    - `validate_retain` (`:766`);
    - `validate_memory_update` (edit, invalidate, revert, `:1119`);
    - `validate_bank_write` (delete document, clear, import, delete bank, `:1182`, operations
      `:416-459`);
    - `validate_bank_read` (includes `EXPORT_KNOWLEDGE_BASE`, `:378-413`);
    - `validate_import` (`:1221`).
  - **Rejecting**: `ValidationResult.reject(reason, status_code=403)`.
  - **Worker caveat**: the async retain worker re-runs `validate_retain` with
    `RequestContext(internal=True, api_key=None, api_key_id, tenant_id)`
    (`engine/memory_engine.py:4385-4395`).
  - **Not gated by the validator** (checked 2026-10-31 at `v1.1.0` and in a local run):
    document export (`submit_export_documents_async`) and bank clone call no validator hook
    for the source bank. Export checks only the tag scope, and clone validates `create_bank` on
    the target. Any authenticated key can therefore start an export of `owner` (local run:
    `202` for the `hermes` key) and download the archive. This exposes nothing a key cannot
    already read through recall and list, since every client reads the whole bank. It does not
    reach the internet: webhooks stay refused. Clone needs `create_bank`, which only `admin`
    holds. Open: accept this, or narrow export by giving non-admin clients a write tag scope
    (`resolve_write_tag_scope`), which would also restrict their edits to their own tags.
  - **Write surface** (checked 2026-10-31 for the web UI, R-020): `validate_bank_write` covers about
    45 operations (`operation_validator.py:416-459`). They include `CREATE_WEBHOOK` and
    `UPDATE_WEBHOOK` (outbound HTTP from the server to any URL), `UPDATE_BANK_CONFIG` and
    `RESET_BANK_CONFIG` (which could switch extraction or consolidation back on),
    `SUBMIT_ASYNC_CONSOLIDATION`, the directive and mental-model writes, and clone. The memory LXC
    has no egress firewall, and the agent can read its own key file (R-003). A denylist of a few
    whole-bank operations would therefore let the agent send memories to the internet over REST.
- **Decision**: one custom extension pair, delivered as a pure policy module plus a thin shim.
  - **Key file**: `clients.json` (root, 0400, mounted read-only) lists
    `{id, sha256, scope}` per client. Scope is `readonly`, `readwrite`, `curator` or `admin`.
    Clients: `hermes` (readwrite), `open-webui` (readwrite), `claude-code` (readwrite, can be
    switched to readonly), `control-plane` (curator, the web UI, R-020), `backup` (admin).
  - **Revocation**: remove the entry and deploy.
  - **Authentication**: hash the bearer, compare in constant time, set `ctx.api_key_id = <id>`.
    Every tenant uses the one default schema.
  - **Validator** (keyed on `api_key_id`, never on `api_key`, because the worker drops the key):
    - Internal calls are accepted, since they were validated at submit time.
    - **Allowlist, not denylist**: every scope lists the operations it may perform, and anything
      unlisted is refused (403). A Hindsight bump that adds an operation therefore refuses it until
      someone classifies it. A guard test compares the policy's operation names with the pinned
      Hindsight enums.
    - `readonly`: recall and the bank-read operations needed to browse (list memory units, list
      documents, document chunks, tags, stats, operation status). It may not retain, update or
      perform any bank write.
    - `readwrite`: `readonly` plus retain and memory update (edit, invalidate, revert). No bank
      write.
    - `curator`: `readwrite` plus `DELETE_DOCUMENT` and `RETRY_OPERATION` (owner choice
      2026-10-31).
    - `admin`: `curator` plus export, import, bank create, bank config and delete bank. It is used
      only by the backup, the restore drill, the deploy probe and the import task.
    - **Refused for every scope, admin included** (FR-004 and exfiltration): webhooks (create,
      update), reflect, consolidation (run, submit, retry), mental-model create and refresh,
      directives, document reprocess, entity regeneration, clone, and the knowledge-base writes.
  - **Code split**: `memory_access.py` in `python/src/homelab_proxmox_orchestrator/` holds all
    decisions as pure functions over plain data. `roles/memory/files/hindsight_ext/shim.py`
    subclasses Hindsight's two base classes and only translates. Both are mounted read-only at
    `/opt/memory-ext`, with `PYTHONPATH` set. The stock image is unchanged.
- **Re-check on bump**: a guard test pins the Hindsight version the shim was verified against.
  Bumping `hindsight_version` fails it until the shim's signatures are re-read and the harness
  re-run (FR-021).
- **Alternatives rejected**:
  - A Caddy bearer per client: it cannot filter MCP, and tags stay self-declared.
  - One shared key: revoking Claude Code would rotate every client.
  - `resolve_tag_scope` read isolation: shared memory is the point, so every client reads
    everything.

## R-002: Enforced client tag

- **Finding**: `ValidationResult.accept_with(contents=...)` replaces the retained items, and
  retain uses the rewritten `contents` (`operation_validator.py:54-73`,
  `memory_engine.py:6937-6939`). `document_tags` are not in `RetainContext` and cannot be
  rewritten.
- **Decision**: on every non-internal retain, the validator strips any `client:*` tag from each
  item and adds `client:<api_key_id>`. Attribution reads item tags only. Document-level tags are
  never trusted for attribution (`data-model.md`).
- **Test**: unit tests cover a forged tag, a missing tag, several items and an internal worker
  call. SC-005 and the US-2 check read the tag back from the store.

## R-003: Hermes adapter (FR-001, FR-002, FR-005, FR-008, FR-019)

- **Finding**:
  - Plugin `1.2.1`, the spike version, caches a failed `/version` probe for the life of the
    process, and append mode then stays off (`__init__.py:156-196`). `1.2.2` fixes this, and
    `1.2.3` is the latest (2026-10-15).
  - **Defaults that break recall here**: `recall_types: ["observation"]` returns nothing with
    observations off, and `recall_sync: false` injects only from turn two (spike).
  - **Modes**: `memory_mode: context` registers no tools (`:1512`). Recall is injected, and the
    agent browses and edits through the MCP endpoint instead (R-009).
  - **Server down**: retains run on a background writer and never block a turn. A failed retain
    is logged and dropped (`:839-856`). A recall error returns an empty string.
    `HINDSIGHT_TIMEOUT` defaults to 120 s and bounds a synchronous prefetch on a hung server.
  - **Runtime install**: the catalog install builds a 1.6 GB runtime under
    `$HERMES_HOME/installs` and writes `config.yaml` (spike). The stock image already has every
    transitive dependency except four pure-Python packages (spike Dockerfile).
- **Decision**:
  - **Stock image** (`083` R-002 kept). At deploy, `tasks/memory_plugin.yml`:
    - fetches the plugin tarball for tag `integrations/hermes/v1.2.3` (`get_url` with
      `checksum:`);
    - downloads `hindsight-client`, `hindsight-embed` and `aiohttp-retry` at exact versions with
      `--require-hashes --no-deps --only-binary :all:`;
    - unpacks the plugin to `{{ hermes_agent_plugins_dir }}/memory/hindsight` and the wheels to
      `{{ hermes_agent_plugins_dir }}/memory-deps`, both root-owned.
  - **Mounts**: both directories are mounted `:ro` at `/opt/data/plugins/hindsight` and
    `/opt/hermes-memory-deps`, plus a `.pth` file in the venv's site-packages that adds the
    second to `sys.path` (see the correction below; `PYTHONPATH` does not reach the gateway).
    The `:ro` mount assertion covers all three.
  - **Plugin config** `hindsight-config.json` (root, 0644, mounted `:ro` at
    `/opt/data/hindsight/config.json`):

    | Setting | Value |
    |---|---|
    | `mode` | `local_external` |
    | `api_url` | `https://memory-api.hus-sky.no` |
    | `bank_id` | `owner` |
    | `memory_mode` | `context` |
    | `auto_recall`, `auto_retain` | `true` |
    | `recall_sync` | `true` |
    | `recall_types` | `["world"]` (chunks are stored as `world`) |
    | `recall_budget` | `mid` |
    | `retain_every_n_turns` | `1` |
    | `retain_async` | `true` |
    | `retain_tags` | `["client:hermes"]` (cosmetic; R-002 enforces it) |
    | `retain_user_prefix` / `retain_assistant_prefix` | `User` / `Assistant` |
    | timeout | 10 s |

  - **Key location**: the plugin key is in the config file, not in `agent.env`, so it never
    becomes an environment variable of the agent's children. The agent can still read the file.
    This is accepted: the key carries only the `hermes` scope (no whole-bank operations) and can
    be revoked alone.
  - **Config protection** (FR-008): `memory.provider: hindsight` sits in the read-only
    `agent-config.yaml`.
- **Verified locally 2026-10-31** (stock `hermes-agent:v0.21.6`, the `render-prod.sh` output
  mounted read-only):
  - `1.2.3`'s `plugin.yaml` declares no `requires_hermes`, so nothing excludes `v0.21.6`. The
    deploy task still asserts the version and any future range.
  - `hermes memory status` reports `Provider: hindsight`, `Plugin: installed`,
    `Status: available`. It does not import the client, so it does not prove the packages load.
  - **Correction (first harness run, 2026-10-31)**: a `PYTHONPATH` set in compose does not reach
    the gateway. The image's launcher replaces it with
    `/opt/hermes/.:/opt/hermes/.venv/lib/python3.14/site-packages`, and every recall failed with
    `ModuleNotFoundError: hindsight_client`. Decision: a one-line `hermes-memory-deps.pth`
    (`/opt/hermes-memory-deps`), mounted `:ro` into the venv's site-packages. Python reads it at
    startup whatever `PYTHONPATH` holds; checked as root and as `hermes` with the launcher's
    value. The deploy asserts the import after the agent is healthy, and the confinement check
    requires every mount under `/opt/hermes/` to be `:ro`.
  - Recall injection and retain against a live server are proven by the harness gate (T036).
- **Alternatives rejected**:
  - A derived image: it breaks `083` R-002, and the repo has no image pipeline.
  - Vendoring the plugin source: about 1,500 upstream lines in the repo, drifting from the pin.
  - `memory_mode: hybrid`: it duplicates the MCP tools in the agent's context (FR-009).

## R-004: Server configuration (FR-003, FR-004)

- **Finding**:
  - `/health` checks only `SELECT 1` (`api/http.py:5815-5845`).
  - The OpenAI embeddings provider sends a startup probe only when the dimension is unknown
    (`engine/embeddings.py:1065-1078`).
  - LLM verification is skipped with `HINDSIGHT_API_LLM_PROVIDER=none`, and the reranker init
    makes no network call.
  - The tokenizer is compiled in. The slim image has no local models, and its providers default
    to `local`, so they must be set explicitly.
- **Decision** (`server.env.j2`):

  | Variable | Value | Why |
  |---|---|---|
  | `HINDSIGHT_API_RETAIN_EXTRACTION_MODE` | `chunks` | Verbatim storage, no LLM |
  | `HINDSIGHT_API_ENABLE_OBSERVATIONS` | `false` | |
  | `HINDSIGHT_API_ENABLE_AUTO_CONSOLIDATION` | `false` | |
  | `HINDSIGHT_API_LLM_PROVIDER` | `none` | Asserted; no LLM endpoint configured at all |
  | `HINDSIGHT_API_EMBEDDINGS_PROVIDER` | `openai` | |
  | `HINDSIGHT_API_EMBEDDINGS_OPENAI_BASE_URL` | `http://{{ llm_router_ip }}:{{ llm_router_port }}/v1` | |
  | `HINDSIGHT_API_EMBEDDINGS_OPENAI_MODEL` | `hermes-embed` | |
  | `HINDSIGHT_API_EMBEDDINGS_OPENAI_DIMENSIONS` | `1024` | No startup probe; starts with the gateway down |
  | `HINDSIGHT_API_RERANKER_PROVIDER` | `litellm` | |
  | `HINDSIGHT_API_RERANKER_LITELLM_API_BASE` | gateway base URL | |
  | `HINDSIGHT_API_RERANKER_LITELLM_MODEL` | `hermes-rerank` | |
  | `HINDSIGHT_API_MCP_ENABLED_TOOLS` | `recall,retain,list_memories,update_memory,invalidate_memory,list_tags` | FR-009 (1.1.0 has 39 tools) |
  | `HINDSIGHT_API_METRICS_BACKLOG_ENABLED` | `true` | Failed-operation gauge (R-015) |
  | `HINDSIGHT_ENABLE_CP` | `false` | No control-plane UI |
  | `HF_HUB_OFFLINE`, `TRANSFORMERS_OFFLINE` | `1` | Belt and braces |
  | `HINDSIGHT_API_TENANT_EXTENSION`, `HINDSIGHT_API_OPERATION_VALIDATOR_EXTENSION` | the shim's classes | R-001 |

  - **Cloud-default guard**: a guard test asserts that no rendered value contains `openai.com`,
    `openrouter`, `huggingface` or `anthropic`, and that the LLM provider is `none` (FR-003).
  - **Egress**: SC-004 egress is measured by the harness. The PROD LXC is not firewalled
    (estate-wide), so a container-level check is quickstart § 5.
- **Verified locally 2026-10-31** (stock `1.1.0-slim` and `pgvector 0.8.1-pg17` on the dev Mac,
  with the rendered `server.env`, the shim and no gateway): the server starts with
  `LLM: provider=none` in chunks mode, both extensions load, and `/health` answers 200 with
  the gateway unreachable. Reflect answers 400 ("requires an LLM provider") before any
  validator runs. Idle memory: API 306 MiB, Postgres 52 MiB. The LAB stage re-checks it on
  the LXC.

## R-005: Placement, sizing and network path (FR-010, FR-017)

- **Decision**:
  - **LXC**: `memory` at `192.168.1.223` (free in every config file; `pct list` checked before
    create), with 2 cores, 2048 MB and a 16 GB disk.
  - **Sizing rationale**: the spike measured Hindsight at 319 MiB and Postgres at 69 MiB idle,
    and the sparing run peaked at 964 MiB including the agent. 2048 MB leaves more than 30 %
    headroom for SC-007 after the import.
  - **Ports**: compose binds the API to `{{ memory_ip }}:8888` and the web UI to
    `{{ memory_ip }}:9999` only.
  - **Publishing**: two Caddy `caddy_services` entries.
    - `memory-api`: proxies port 8888, `user_facing: false`. The route exists and no tile is shown.
    - `memory`: proxies port 9999, `user_facing: true`. This creates the portal tile "Memory" and
      a blackbox HTTPS probe (R-020).
  - **Access**: every API client uses `https://memory-api.hus-sky.no`. The owner's browser uses
    `https://memory.hus-sky.no`.
  - **Direct port** (spec FR-010): `memory_ip:8888` stays reachable on the LAN, because Caddy
    (`.211`), Prometheus (`.214`) and the health check script need it. A source-address firewall
    was rejected: the health check runs from `pve`, a laptop and CI, and lab addresses differ.
    Instead, guard tests assert that no client config (plugin, filter valves, MCP entry) uses
    the direct port. Every request there still needs a key, and the agent's egress chain rejects
    `192.168/16` apart from its allowed destinations.
  - **Sizing with the UI**: the web UI adds an UNVERIFIED 100–200 MB (a Next.js standalone server),
    measured in the LAB rehearsal. 2048 MB is kept unless SC-007's 30 % headroom fails.
- **Agent egress**: the agent already may reach `reverse_proxy_ip:443` (egress script rule 6,
  accepted risk `083` R-008), so FR-017 adds **no** rule.
  - The memory entry in `hermes_mcp_servers` gets `via_proxy: true`. The egress script then skips
    its derived per-host rule, which needs an IP, and the deploy probe tests the proxy instead.
  - The backlog's "the agent's egress allowlist gains one rule" is superseded: the path through
    Caddy needs none.
- **Alternatives rejected**:
  - Direct `http://memory_ip:8888` for the agent: no TLS for one client, plus an extra rule.
  - Running inside the `hermes` LXC: rejected by the owner (own lifecycle, backup and
    monitoring).

## R-006: Turn format and untrusted content (FR-014)

- **Finding**: the Hermes plugin retains one item per turn. Its content is a JSON array of
  `{"role","content","timestamp"}` with `"User: …"` and `"Assistant: …"` prefixes
  (`__init__.py:1342-1500`), using `document_id` = session id and `update_mode: append`. Tool
  output never reaches the plugin: `sync_turn` receives only the user and assistant text
  (`agent/memory_manager.py:595-620`), redacted, and interrupted turns are skipped. Recall
  injects `- {text}` only (`:1279`). Tags and metadata are not shown, but the prefixes survive
  inside the chunk text.
- **Decision**:
  - All three adapters retain the plugin's format: role prefixes `User:` and `Assistant:` in the
    stored text, never tool output, never fetched content.
  - The prefixes are the source labels FR-014 requires. They are stored, recalled and visible to
    the model.
  - Open WebUI and Claude Code add a short preamble stating that `User:` lines are the owner's
    words and `Assistant:` lines are earlier replies that may be wrong.
  - Contract: [turn-format.md](./contracts/turn-format.md).
- **Residual risk** (spec edge case): injected text that an assistant repeats is stored, labelled
  `Assistant:`.

## R-007: Open WebUI filter (FR-019)

- **Finding**:
  - Open WebUI `0.11.3` runs outlet filters server-side, inline after completion
    (`utils/middleware.py:3872`).
  - `inlet(body, __user__, __metadata__)` may edit `body["messages"]`.
  - Functions live in `webui.db` table `function`. No env or file loader exists. The admin API
    needs an admin API key.
  - The role already reconciles `webui.db` with `docker exec -i hermes_open_webui python3`, with
    the payload on stdin (`reconcile_config.py`, the tool-server reconcile).
- **Decision**:
  - **Source**: `files/open_webui/memory_filter.py`, about 120 lines, standard library plus
    `requests` from Open WebUI's environment.
  - **Inlet**: recall with the last user message (3 s timeout), then insert one system message
    with the preamble and up to `recall_max_tokens` of results.
  - **Outlet**: one async retain of the last user and assistant pair, with
    `document_id = owui-<chat_id>`, `update_mode: append` and tag `session:owui-<chat_id>`.
  - **Failure**: both directions fail open and log one line.
  - **Skipped**:
    - task requests (`__metadata__["task"]`: titles, tags, follow-ups);
    - chats whose model is served by the agent connection (`hermes_agent_api_base_url`). The
      agent's plugin retains those itself, so the filter would store them twice (new spec edge
      case).
  - **Provisioning**: a reconcile task upserts the function row (`id = shared_memory`, active,
    global, valves `{url, key, bank, agent_model_ids}`) and restarts Open WebUI only when the
    content hash changed. The agent model ids come from the agent's `/v1/models` at deploy.
  - **Key**: `memory_client_open_webui_key` lives in the valves, which only admins can read.
- **UNVERIFIED** (the function cache picks up a content change after restart): the LAB stage
  verifies it. Open WebUI runs in the hermes lab copy, and the filter fails open there because
  memory is unreachable.
- **Alternative rejected**: the admin functions API, which needs a new admin API key and
  `ENABLE_API_KEYS`. `/api/v1/functions/sync` deletes every unlisted function.

## R-008: Import and retire Open WebUI's memories (FR-016)

- **Finding**: `0.11.3` has `ENABLE_MEMORIES` (`config.py:424`, persisted as `memories.enable`,
  `:2856`) and `USER_PERMISSIONS_FEATURES_MEMORIES` (`:1940`). `GET /api/v1/memories/` is
  per-user only.
- **Decision**:
  1. A one-shot task reads the `memory` table through `docker exec` (one owner).
  2. It retains each row with the `admin` key: `document_id = owui-memory-<id>` (idempotent
     upsert), tags `origin:open-webui-memory` and `client:open-webui`. The validator stamps
     `client:<id>` for every scope except `admin`, which may keep a supplied client tag; that is
     how imported rows keep the client they came from.
  3. It asserts the row count in the store.
  4. Then it sets `ENABLE_MEMORIES=false` and `USER_PERMISSIONS_FEATURES_MEMORIES=false` in
     compose, and `memories.enable: false` in `hermes_managed_config`.
  - The `memory` table is left in place and dropped in a later release.
- **Order**: steps 1–3 run only while `memories.enable` is still true, and the import is skipped
  if the count already matches.

## R-009: MCP access for browsing and editing (FR-009, FR-010, FR-013)

- **Finding**: `hermes_mcp_servers` renders both the agent's `mcp_servers` and Open WebUI's
  `TOOL_SERVER_CONNECTIONS`, with one key (`main.yml:217-236`).
- **Decision**:
  - **Entry**: one `memory` entry with `url: https://memory-api.hus-sky.no/mcp/owner/`,
    `auth: bearer`, `credential_env: AUXILIARY_MCP_MEMORY_API_KEY` and
    `vault_var: memory_client_hermes_key`.
  - **Bank in the URL** (checked on PROD 2026-10-31): on `/mcp/` a call without `bank_id` goes to
    a bank named `default` ("Bank 'default' not found"). `/mcp/owner/` binds the bank and drops
    `bank_id` from all six tool schemas, so a model cannot aim at another bank. The validator
    allows `update_memory` and `invalidate_memory` for a `readwrite` key.
  - **New fields**: `webui_vault_var: memory_client_open_webui_key` and `via_proxy: true`
    (R-005).
  - **Key selection**: the connection fact uses `webui_vault_var` when set. Every model then sees
    six memory tools, at most 10 (FR-009).
  - **Claude Code**: adds the same URL as an MCP server in the private installation only, with
    its own key (T069, amended by T048).
- **Lab**: the entry stays enabled. The tool connection fails quietly, the egress probe is
  skipped in lab like every other non-searxng destination, and no secret beyond the existing
  internal class is rendered.

## R-010: Claude Code adapter (FR-012, FR-019)

- **Finding** (Claude Code hooks docs):
  - **UserPromptSubmit**: gets `prompt`. With exit 0, it injects stdout or
    `hookSpecificOutput.additionalContext`, capped at 10,000 characters. The default timeout is
    30 s, and the prompt proceeds on timeout.
  - **Stop**: gets `transcript_path` and `last_assistant_message`, and the docs note the
    transcript can lag.
- **Decision** (owner's dotfiles, not this repo):
  - **Script**: `claude-memory-hook` with two modes.
    - `recall`: 3 s curl timeout, output capped at 8,000 characters, preamble from the turn
      format.
    - `retain`: async. Pairs the last prompt (from the transcript) with `last_assistant_message`,
      `document_id = cc-<session_id>`, append.
  - **Key**: on macOS from the keychain (`security find-generic-password -s homelab-memory -a
    claude-code -w`), on Linux from Bitwarden through `rbw` (item `homelab-memory/claude-code`).
    A locked or missing source means no memory for that turn, never a prompt.
  - **Where enabled** (amended 2026-10-31, T048): in the user settings of the owner's private
    Claude Code installation only: `~/.claude-private/settings.json` on the Mac (launched as
    `claude-private`, `CLAUDE_CONFIG_DIR=~/.claude-private`) and `~/.claude/settings.json` on the
    Linux laptop. Repository settings are rejected: `.claude/settings.local.json` applies to
    whichever account opens the repository, including the EY seat on the same Mac.
  - **Guard**: the hook does nothing unless `HOMELAB_MEMORY_CLIENT=claude-code` is set (only the
    private installation's hook commands set it) and `CLAUDE_PROJECT_DIR` is under
    `~/Development/private`. A hook entry copied into the EY setup by mistake therefore sends
    nothing.
  - **Gate**: resolved 2026-10-31 by using the private account (spec Assumptions).
- **Revocation and read-only**: change the `claude-code` scope in `clients.json` (vault-backed
  list) and deploy `memory`. Hermes and Open WebUI keys are untouched (SC-009).
- **Reachability**: the Mac reaches `memory-api.hus-sky.no` → `192.168.1.211` over the LAN (the
  corporate proxy blocks the tailnet). Verified in quickstart § 7.

## R-011: Gateway client (FR-004, SC-003) and lab classification (FR-020)

- **Finding**:
  - Every client key is scoped to all aliases (`virtual_keys.yml:136-138`), and the reconcile
    loop updates `models` on existing keys.
  - rpm and budget apply only at key creation.
  - Every existing gateway client key is classified **`internal`** in `test_lab_switches.py`.
    `lan` is for ntfy and SNMP.
- **Decision**:
  - **Client entry**: `llm_router_clients` gains `{alias: memory, key_env:
    LLM_ROUTER_CLIENT_MEMORY_KEY, max_budget: 1.00, budget_duration: 30d, rpm_limit: 30,
    models: [hermes-embed, hermes-rerank]}`.
  - **Optional field**: `models` defaults to `llm_router_client_allowed_models`.
  - **Rate band**: still holds. Max client 60 ≤ gateway 65 < sum 122. Budget sum $28 < $50.
  - **Classification**: `llm_router_client_memory_key` is classified `internal`, like its
    siblings. **Spec fix**: FR-020 said `lan`. The intent ("needs no lab switch") is unchanged.
- **Rate check**: per turn, recall is 1 embed and 1 rerank, and retain is about 1 embed. Three
  clients at chat pace stay far below 30 rpm.

## R-012: Correct and forget semantics (FR-013, US-5)

- **Finding**:
  - In chunks mode a memory unit is a chunk (up to 3,000 characters) holding one or more turns.
  - `update_memory` edits a unit's text. `invalidate_memory` removes a unit from recall but
    keeps it for audit, and it is reversible (`mcp_tools.py:3823-3830`).
  - `delete_document` removes a whole session.
- **Decision**:
  - **Correct**: `update_memory` on the unit, replacing the wrong text.
  - **Forget one fact**: `update_memory` with that fact redacted from the unit's text. Precise,
    keeps the rest of the turn.
  - **Forget a whole turn**: `invalidate_memory`.
  - **Hard delete**: `delete_document`, from the web UI (`curator`, R-020) or the runbook (admin).
    It is not in the MCP allowlist, so no model can wipe a session.
  - **Backups**: a forgotten fact persists in backups until retention ages it out (spec
    Assumptions).
- **UNVERIFIED** (whether a later append to the same session document resurrects an edited or
  invalidated chunk, given that delta retain keeps unchanged chunks): verified by quickstart
  § 8, which forgets a fact, continues the same session and recalls. If the fact resurrects,
  adapters switch to one document per turn (`document_id = <session>-<turn>`), a one-line change
  in each adapter.

## R-013: Backup (FR-007)

- **Decision**:
  - **Registration**: `service_backups.memory` with host `memory`, mount and dir
    `/mnt/memory/backups`, schedule `*-*-* 05:30:00` (the next free slot after Home Assistant).
  - **Snapshot**: `snapshot/memory.sh.j2` takes
    `docker exec memory_postgres pg_dump -Fc -U hindsight hindsight > $WORK_DIR/db.dump`, then
    exports the bank with
    `curl -H "Authorization: Bearer $ADMIN_KEY" -X POST .../banks/owner/document-transfer/export -o $WORK_DIR/owner-export.zip`.
  - **Admin key**: read from a root-only file on the LXC. The snapshot copies the compose file
    and `clients.json`, which holds only hashes, but never `server.env`.
  - **Gate**: the playbook entry carries `when: (deploy_environment | default('prod')) != 'lab'`.
  - **NAS**: share `homelab_memory` (Synology, manual), `proxmox_mounts` entry, and
    `service_mountpoints.memory` in `prod.tfvars.template`.
  - **Integrity**: the export ZIP is the portable copy (FR-018), and `pg_restore --list` is
    checked on the dump at backup time.

## R-014: Restore drill (US-4, SC-006)

- **Decision**: `playbooks/memory-restore-drill.yml`, following `restore-drill.yml` (Immich) for
  the Postgres leg:
  1. Find the latest archive.
  2. In a `block`, extract and start a throwaway `pgvector` plus `hindsight` from
     `restore/memory-compose.yml.j2` on test port `8889` and its own network.
  3. Run `pg_restore` and wait for `/health`.
  4. Compare `/v1/default/banks/owner/stats` (`total_documents`, `total_nodes`) with the values
     recorded in the archive at backup time.
  5. Run the probe set from `drill-probes.json` in the archive: up to 3 random active units picked
     at backup time, each stored as `{unit_id, query}`, where the query is the first 200
     characters of the unit's text. Each query is recalled on the restored instance with the
     admin key and the gateway's embedder, and its unit must be in the top 3 results. The set is
     generated from the store and lives only in the archive on the NAS. No question about the
     owner is committed to this public repository.
  6. An `always:` block tears everything down.
  - **Second leg**: import the export ZIP into an empty bank on the same throwaway instance and
    check the document count. This proves FR-018's portable path.

## R-015: Monitoring (FR-015)

- **Decision** (`host_vars/memory.yml` `monitoring_contract`):
  - **Liveness**: `liveness_targets` probes `https://memory-api.hus-sky.no/health` (`http_2xx`).
    Alert `MemoryDown` after 5 minutes, severity critical.
  - **Scrape**: `scrape_targets` covers `{{ memory_ip }}:8888/metrics`.
  - **Failed writes**: alert `MemoryRetainFailures` fires on the failed-operations gauge > 0 for
    30 minutes (backlog metrics on, R-004). This covers async retains that were reported as
    queued and then failed (FR-006).
  - **Silent write loss**: alert `MemoryWritesStalled` fires when retains are 0 over 12 hours
    while gateway chat completions exceed 20 in the same window. It catches a store that stops
    growing while chats happen.
  - **Log rules** (`092`): memory container `ERROR` lines, plus Hermes plugin lines matching
    `Hindsight (retain|recall) failed` in `host_vars/hermes.yml`. Both start `enabled: false`
    with `disabled_reason: awaiting 7-day baseline`, per the estate pattern.
  - **Redaction**: an Alloy redaction pattern covers memory keys. Keys are generated with a
    fixed `hmem_` prefix so the pattern is exact.
- **Metric names** (read 2026-10-31 from a local `1.1.0-slim` with backlog metrics on; the
  LAB rehearsal re-reads them, T027 step 5):
  - Backlog gauge: `hindsight_async_operations{operation_type, status, tenant}`, with
    `status` one of `pending`, `processing` or `failed` ("stranded"). Retains show as
    `operation_type="retain"` and `"batch_retain"`.
  - Operations counter: `hindsight_operation_operations_total{operation, source, success}`
    (`source` is `api` or `worker`).
  - Also present: `hindsight_http_requests_total`, `hindsight_http_duration_seconds_*`,
    `hindsight_process_memory_bytes`, `hindsight_db_pool_*`, `hindsight_consolidation_backlog`.

## R-016: Lab fit (FR-020, SC-008)

- **Decision**:
  - **Overrides**: `memory_ip: "10.99.0.223"` in `lab-overrides.yml`. The lab tfvars are derived
    automatically, and the backup is gated off in lab.
  - **Credentials**: no `internet` credential is rendered. The memory gateway key is `internal`.
  - **Lab copy start**: it starts with the gateway unreachable (dimension set, LLM `none`, R-004)
    and passes `scripts/healthcheck/memory.sh`, which checks `/health` directly on
    `memory_ip:8888`. No Caddy exists in a single-copy lab.
  - **Deploy probe**: skipped in lab and listed in `reports/lab/skipped-checks.txt`.
  - **Hermes lab copy**: renders the plugin config pointing at `memory-api.hus-sky.no`. In lab, the
    nftables rule and the agent's chain reject that address, so the plugin fails within its
    timeout. The stage checks that the agent's `/health` stays healthy and that one turn through
    the API server completes without memory. The turn ends in the expected 429, because the
    gateway is also absent. The check is that the 429 arrives and the process does not crash.
- **Guards**: `test_lab_overrides.py` and `test_lab_tfvars.py` count bumps (12 → 13 services,
  8 → 9 mounts), `test_service_backup.py` covers the lab gate, and `test_lab_switches.py` covers
  the classification.

## R-017: Harness gate against production config (FR-021)

- **Decision**: the spike harness gains a `prod-render` candidate.
  - **Render**: `docs/backlog/097-spike/render-prod.sh` renders `server.env.j2`, `clients.json.j2`
    and `hindsight-config.json.j2` with `ansible localhost -m template`, using production vars and
    harness-local keys. It rewrites only the gateway URL to `llmproxy`, plus Caddy to plain HTTP
    inside the harness network.
  - **Images**: it runs the pinned images, the shim and the policy module.
  - **Extended portability test**: three keys (hermes, open-webui, claude-code). The Open WebUI
    and Claude Code legs replay the turn format from the contract. The test checks SC-005 (6/6),
    a read-only refusal and forged-tag stamping.
  - **Results**: written to `results/<YYYY-MM-DD>-prod-render/`, with the scores linked in the PR
    description.
- **When**: before the first PROD promotion that turns memory on, and on any change to the
  Hindsight, plugin or agent pin, the server env, the plugin config, the policy module, the shim
  or the Open WebUI filter.
- **Enforcement**: a guard test (`test_memory_harness_gate.py`) computes a fingerprint over those
  pins and files and the values they render from (memory role defaults, hermes memory settings).
  It fails unless a committed `results/*-prod-render/gate.json` both passed SC-001 to SC-004 and
  carries the current fingerprint. `gate.py` writes that verdict at the end of `run.sh` and
  checks that compose ran the images rendered from the PROD pins. Hand judgements are bound to
  the reviewed answer's digest (PR #318 review).
  The Claude Code hook is not fingerprinted: it lives in dotfiles, and the harness replays its
  turn format without running the script.

- **Gap found in the first PROD deploy (2026-10-31)**: the harness sends embeddings straight to
  the Mac's LiteLLM, not through the homelab gateway, so it could not see that the gateway's
  LiteLLM (`v1.83.3-stable`) refuses the `dimensions` parameter Hindsight sends (400
  UnsupportedParamsError, whatever `drop_params` says). The PROD deploy probe caught it, as
  R-019 intends. Fix: `allowed_openai_params: [dimensions]` on the `hermes-embed` deployment,
  reproduced and verified against the pinned image with a stub backend, and guarded by
  `test_llm_router_embed_params.py`. Open: run the harness through a gateway-shaped proxy, so a
  gateway incompatibility shows before PROD.

## R-018: Pins, version currency and guard updates

- **Decision**:
  - **Service versions block**: gains `hindsight_version: "1.1.0"` (image tag suffix `-slim` in
    role defaults), `memory_postgres_version: "0.8.1-pg17"` and
    `hermes_hindsight_plugin_version: "1.2.3"`.
  - **Version sources**: each gets a `version-sources.yml` entry. Hindsight and the plugin use
    `latest` (GitHub `vectorize-io/hindsight`; the plugin's tags have the `integrations/hermes/`
    prefix, so `unchecked` with a reason if the checker cannot filter tag prefixes). Postgres is
    `support-only`.
  - **Wheels**: wheel pins and hashes live in `roles/hermes/defaults/main.yml`, next to the
    plugin, and are re-checked with it.
  - **Guards updated**:
    - `test_hermes_ntfy_config.py`: plugin list unchanged; the memory provider is set in
      `memory:`, not in `plugins.enabled`.
    - `test_hermes_env_modes.py`: credential freeze adds `AUXILIARY_MCP_MEMORY_API_KEY` in PROD
      and LAB, recorded per R-016 of `095`.
    - `test_lab_switches.py`, `test_lab_overrides.py`, `test_lab_tfvars.py`,
      `test_service_backup.py`, `test_version_pins.py` and `test_log_pipeline.py`
      (`EXPECTED_LOG_RULE_SERVICES` += memory).
  - **New guards**: `test_memory_config.py` covers the server env (R-004), the tool allowlist,
    no cloud defaults, `LLM_PROVIDER=none`, `clients.json` (hashes only), the plugin config
    values (R-003), the shim's verified-version pin, the web UI's mandatory access key and
    `memory_ip`-only binding (R-020), and that every operation name in the policy's allowlists
    exists in the pinned Hindsight enums (R-001).
  - **Lab-switch classification**: `memory_ui_access_key`, `memory_client_*_key`,
    `memory_admin_key` and `memory_db_password` are all `internal`.

## R-019: Deploy-time write check (edge case "silent write loss")

- **Decision**: after `compose up`, PROD only, `roles/memory/tasks/bank.yml`:
  1. Ensures bank `owner` exists with chunks-mode settings, and bank `deploy-probe` exists.
  2. With the admin key, syncs a retain of a random sentence into `deploy-probe`.
  3. Recalls it and asserts it comes back.
  4. Asserts that `stats.total_documents` grew by 1, then deletes the document.
  - The synthetic probe never touches the `owner` bank or any client's history. A failure fails
    the deploy.
  - In lab it is skipped and listed, because there are no embeddings.

- **First PROD deploy (2026-10-31)**: the probe failed its count check although retain, recall
  and delete all worked. Bank stats are served from a 60-second cache
  (`HINDSIGHT_API_BANK_STATS_CACHE_TTL_SECONDS`), so before and after read the same value. The
  probe and the backup's `stats.json` now ask for `?refresh=true`.
- **Resolved with the web UI (2026-10-31)**: a document delete, and a memory edit, submit
  `submit_async_graph_maintenance` (and deletes `submit_async_vector_index_maintenance`) in the
  caller's own context; retains submit them from the worker (`internal`), which was always
  accepted. The policy refused them for every scope, so deletes left stale links and orphaned
  entities (6 refusals logged in PROD by the first deletes). Both jobs relink, prune and index
  without an LLM or egress, so `readwrite` and up now allow them. The harness gate re-ran.

## R-020: Memory web UI (FR-023, SC-011)

- **Finding** (Hindsight `v1.1.0`, `hindsight-control-plane/`, `docker/standalone/`):
  - **Images**: the web UI ("control plane", a Next.js standalone app) ships in two forms. It is
    built into the `hindsight:*-slim` image (the `standalone` target, off by default through
    `HINDSIGHT_ENABLE_CP`), and published on its own as
    `ghcr.io/vectorize-io/hindsight-control-plane:1.1.0` (`cp-only` target, `node:24-alpine`; tag
    confirmed on ghcr.io 2026-10-31).
  - **Login**: `HINDSIGHT_CP_ACCESS_KEY` gates every page and API route (`src/middleware.ts`), with
    a constant-time compare (`app/api/auth/login/route.ts`). A login sets an HMAC session cookie
    valid for 24 h (`lib/auth/session.ts:6`), `SameSite=Lax`, `Secure` behind TLS.
  - **Open by default**: with the key unset, the middleware lets every request through (the UI is
    open).
  - **API connection**: the UI calls the API server-side with `HINDSIGHT_CP_DATAPLANE_API_URL` and
    one bearer, `HINDSIGHT_CP_DATAPLANE_API_KEY` (`lib/hindsight-client.ts:15-16`). The browser
    never sees that key.
  - **Pages**: 73 API routes covering banks, documents, chunks, memories, tags, stats, operations,
    recall and retain. They also include reflect, mental models, directives, consolidation,
    webhooks, bank config, export and import, clone, entity regeneration and the knowledge base.
- **Decision** (owner choices 2026-10-31: read-write, own container, `memory` for the UI and
  `memory-api` for the API, hard delete and retry allowed):
  - **Container**: a third service `memory_ui` in the memory compose stack, image
    `hindsight-control-plane:{{ hindsight_version }}` (stock).
    - It reaches the API on the compose network (`http://memory_api:8888`). Its environment holds
      only the access key and its API key: no gateway key, no database password.
    - It has a memory limit of 384 MB and restarts independently of the API.
  - **Client**: `control-plane`, scope `curator` (R-001). Retains made in the UI are stamped
    `client:control-plane`. Corrections, hides, hard deletes and retries are allowed. Everything
    else the UI offers returns 403, and those pages show an error.
  - **Login key**: `memory_ui_access_key` (vault and the owner's password manager, `hmem_` prefix
    for log redaction).
    - The role's preflight refuses to render the UI with an empty key.
    - A guard test asserts that the compose service carries `HINDSIGHT_CP_ACCESS_KEY` and binds
      only to `memory_ip`.
  - **Portal**: the `caddy_services` entry `memory` (`user_facing: true`, title "Memory",
    description "Shared AI memory: browse and edit") renders the tile and the blackbox probe. The
    probe follows the redirect to `/login`, which returns 200.
  - **Lab**:
    - The UI's lab copy starts with the API's lab copy.
    - `scripts/healthcheck/memory.sh` also checks `GET /api/health` on `memory_ip:9999`, which
      needs no login.
    - Both keys are classified `internal` in `test_lab_switches.py`.
  - **Pins**: the UI shares `hindsight_version` with the API. Upstream releases them together
    (`release.yml`, one matrix).
- **UNVERIFIED** (UI RAM and its behaviour on refused routes, which should be an error toast and
  not a crash loop): measured and checked in the LAB rehearsal and quickstart § 11.
- **Alternatives rejected**:
  - `HINDSIGHT_ENABLE_CP=true` inside the API container: it shares the API's environment
    (gateway key, database password), memory budget and restarts.
  - The UI holding the admin key: one login could export or delete the whole store.
