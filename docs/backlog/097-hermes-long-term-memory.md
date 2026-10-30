# Feature Specification: long-term memory for Hermes, shared with the owner's other AI clients

**Feature Branch**: `097-hermes-long-term-memory`
**Created**: 2026-10-30
**Status**: Draft, **ready for `/speckit-specify`** (2026-10-30). Bake-off and portability test done. Bake-off done
2026-10-30 (see [Spike results](#spike-results-2026-10-30)); provider, placement and Open WebUI
migration decided. Amends [`083`](./083-hermes-agent-runtime.md) (FR-018: built-in memory only) and
[`065`](./065-hermes-service.md) (Open WebUI's own memories retired).
**Input**: Give the Hermes Agent a long-term memory that remembers facts about the owner beyond the
built-in `USER.md`/`MEMORY.md` budget, and share that memory with Open WebUI and Claude Code, so
the three clients stop knowing different things. Memory is its own service; each client reaches it
through a thin adapter. Local only, LLM calls kept sparse.

---

## Why this exists

Hermes (`083`) has upstream's built-in memory: two curated files injected into every system prompt,
plus FTS5 search over past sessions. It works, and the spike shows it works well for a handful of
facts. But it is bounded by design, and it is private to one client:

1. **The budget is small.** `memory_char_limit: 2200` and `user_char_limit: 1375` (upstream
   defaults, `hermes_cli/config_defaults.py:1318-1319` at v0.21.6). About 500 tokens for everything
   the agent knows about the owner. Beyond that the agent must drop or compress facts.
2. **Memory is siloed.** Open WebUI keeps its own memories (in use: `065` quickstart restored one),
   Hermes keeps `USER.md`, and Claude Code on the Mac knows neither. A fact told to one is unknown
   to the other two.
3. **Nothing is shared or searchable by meaning.** Session search is keyword-only, and only Hermes
   can use it.

Hermes supports exactly one external *memory provider* next to the always-on built-in memory
(`memory.provider`). Several exist; they differ sharply in how many LLM calls they make, what they
need to run, and whether other clients can reach them.

## Decisions recorded (2026-10-28 – 2026-10-30)

| decision | choice | why |
|---|---|---|
| Gaps to close | **Facts about the owner** (beyond the built-in budget) **and shared memory** across clients | Owner choice. Also exploratory: the spike decides whether the first gap is real. |
| Data locality | **Local only** for storage, embeddings and memory-side LLM calls | Owner choice. Rules out the cloud tiers of Honcho, Mem0, Supermemory, RetainDB, Hindsight Cloud. |
| Infrastructure | **A new service or LXC is acceptable** | Owner choice. |
| Memory-side LLM calls | **Sparingly**: periodic or batched passes, not several calls per turn | Owner choice. Every call competes with chat for the one inference host (the Mac). |
| Clients | **Hermes Agent, Open WebUI and Claude Code, read-write** | Owner choice. Claude Code is the one cloud model; see Accepted risk. |
| Selection method | **A measured bake-off**, not vendor benchmarks | Vendor numbers use different judges and none tests Norwegian. Candidates: built-in only, Holographic, Mnemosyne, Hindsight (3 variants), Honcho. |
| Spike site | **Local Docker on the dev Mac**, synthetic mixed NO/EN data | No estate change, no personal data, repeatable. |
| Modularity | **Memory is a service, the agent integration an adapter** (FR-018); portability is an evaluation column | Owner choice (architect's preference for modular design). Switching agent framework must not mean migrating memory. Also what makes cross-client sharing work. |
| Provider | **Hindsight, verbatim-chunks mode** (2026-10-30) | Bake-off winner: 16/16 at zero memory-side LLM calls, high portability. Runner-up Honcho (14/16, 2–4 LLM calls per turn, junk facts from questions, AGPL). Mnemosyne rejected (8/16, below the built-in baseline). |
| Placement | **Its own LXC** (2026-10-30) | FR-018 in practice: own lifecycle, own backup and monitoring, reached by every client the same way. The agent's egress allowlist gains one rule. |
| Recall path per client | **Injected, through a thin adapter per client**; MCP for browsing, correcting and forgetting | The bake-off's main result: injected recall (Hindsight, Honcho) beat tool-driven recall (Mnemosyne, Holographic, session search). Local models call memory tools unreliably. FR-019. |
| Open WebUI's own memories | **Imported once, then turned off** (2026-10-30) | One memory for every client. Amends `065`. |
| Per-client credentials | **A small custom Hindsight extension in this repo** (2026-10-30): tenant extension with one key per client, plus an operation validator that enforces the `client:<id>` tag and a read-only scope | Upstream has one shared key (portability test). Lets Claude Code be revoked or made read-only alone. Rejected: Caddy per-client bearers (no read-only on MCP, tags stay self-declared); one shared key (revoking one client rotates all). Cost: code re-checked on every Hindsight bump. |
| Claude Code hooks | **Private repositories only** (2026-10-30), as project settings, never global | EY work never reads from or writes to the private store; keeps the accepted risk small. |

### Accepted risk: memory reaches Anthropic through Claude Code

Claude Code on the Mac runs on Anthropic's models under an EY enterprise seat. Any memory it
recalls is sent there as prompt content, and anything it writes can carry work context into the
private store. The owner accepts this for read-write sharing. To be confirmed against the Claude
Enterprise Guidance & Guidelines before implementation. Bounded by FR-012: Claude Code's own
revocable, optionally read-only credential, and hooks only in private repositories.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Hermes remembers more about me than fits in USER.md (Priority: P1)

**Independent Test**: Tell Hermes ~40 facts about yourself across ten conversations (more than the
1,375-character `USER.md` budget). In a new conversation, ask about facts from the first and the
last of those conversations. Both are answered correctly, and facts that changed (moved city,
quit coffee) come back in their latest form.

**Acceptance Scenarios**:
1. **Given** more facts than the built-in budget holds, **When** a fresh conversation asks about
   any of them, **Then** the agent answers from memory, not from general knowledge.
2. **Given** a fact was later contradicted, **When** asked, **Then** the newer value is given and
   the old one is not presented as current.
3. **Given** nothing was ever said about a topic (a cat), **When** asked, **Then** the agent says it
   does not know, rather than inventing.
4. **Given** facts told in Norwegian, **When** asked in English (or the reverse), **Then** recall
   works across the language boundary.

### User Story 2 - What I tell one client, the others know (Priority: P1)

**Independent Test**: Tell Open WebUI (plain chat, not the agent) "my sister lives in Tromsø". In
Claude Code on the Mac, ask "where does my sister live?". It answers from the shared memory. Then
tell Claude Code a new fact and ask Hermes over ntfy.

**Acceptance Scenarios**:
1. **Given** a fact written by any one client, **When** another client asks, **Then** it is found.
2. **Given** a memory, **When** the owner asks which client wrote it, **Then** the store says so
   (per-client identity, FR-011).

### User Story 3 - Memory costs little inference (Priority: P1)

**Independent Test**: Over a day of normal use, memory-side LLM calls through the gateway are
counted separately from chat and stay within the SC-003 budget. With the Mac asleep, chat fails as
today and memory writes queue or degrade without losing data.

### User Story 4 - Memory survives a rebuild and can be restored (Priority: P2)

**Independent Test**: A restore drill for the memory LXC, modelled on
`playbooks/hermes-restore-drill.yml`, restores the store from the nightly dump into a fresh
container, and a probe question answered before the drill is answered the same after.

### User Story 5 - I can see, correct and forget memories (Priority: P2)

**Independent Test**: Ask "what do you remember about my car?", correct a wrong fact, and ask to
forget the licence plate. The listing is accurate, the correction holds, the forgotten fact is gone
from all three clients.

### Edge Cases

- **Mac asleep or away**: embeddings come from oMLX through the gateway. A write that cannot embed
  must not be silently dropped (US-3), and recall must fail visibly rather than return "no memories".
- **Silent write loss**: a provider that reports success while persisting nothing (Mnemosyne #1177
  is exactly this) must be caught by the deploy check and by monitoring (FR-015).
- **First message of a conversation**: a provider whose recall is asynchronous injects nothing on
  turn one (observed with Hindsight's `recall_sync: false` default). Open WebUI and ntfy probes are
  mostly single-turn, so recall must be synchronous on the first turn.
- **Two writers**: plugin in the agent and MCP server for the other clients on one store
  (SQLite lock and WAL bugs in Mnemosyne #1183, #707).
- **Prompt injection into memory**: a web page or tool result read by the agent can be written to
  memory and then injected into every later conversation of every client.
- **The agent edits its own memory config**: Mnemosyne reads a writable
  `$HERMES_HOME/mnemosyne/config.yaml`; Hindsight's plugin key sits in a file the agent can read.
- **Hermes upgrade disables the provider** (Mnemosyne #1169; v0.22 "updates disable a plugin that
  no longer fits").
- **Lazy installs**: catalog plugins install dependencies at runtime unless
  `security.allow_lazy_installs: false`, which the egress allowlist would break in any case.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Hermes MUST use Hindsight as its one external memory provider, set in the
  deploy-owned, read-only `agent-config.yaml.j2` (`memory.provider: hindsight`). Built-in memory
  stays on (`083` FR-018).
- **FR-002**: The provider and its dependencies MUST be installed at build or deploy time, pinned
  to exact versions, never at runtime (no lazy installs, no model downloads). Every pin is re-checked
  when `hermes_agent_version` is bumped, like `_config_version`.
- **FR-003**: Storage, embeddings and any memory-side LLM calls MUST stay in the estate. Embeddings
  use the gateway's `hermes-embed` alias; LLM calls use a gateway alias. Every vendor default that
  points at a cloud endpoint (OpenRouter, OpenAI, Hugging Face) MUST be overridden and asserted.
- **FR-004**: The store MUST run in verbatim-chunks mode with auto-consolidation, observations and
  reflection off: zero memory-side LLM calls, embeddings and rerank only. Any later LLM pass
  (consolidation, extraction) is a separate decision, runs in a scheduled quiet window and never
  holds the inference queue while chat is active. Memory traffic MUST use its own gateway client
  key, so it is counted and rate-limited apart from chat.
- **FR-005**: Recall MUST work on the first turn of a fresh conversation: synchronous prefetch
  (`recall_sync: true`) and recall types that include raw facts and chunks, not only observations
  (the plugin defaults `recall_sync: false` and `recall_types: ["observation"]` return nothing here).
- **FR-006**: A failed memory write (embedding down, store locked) MUST NOT be reported as success;
  it is retried or surfaced.
- **FR-007**: The store (Postgres with pgvector) MUST sit on the memory LXC's local disk (no NFS,
  `083` FR-002), with a nightly `pg_dump` and a bank export (Hindsight's documented ZIP: manifest
  plus one JSON per document, no embeddings) through `service_backup` to Synology, and a restore
  drill (US-4). The export is the portable copy (FR-018); the dump is the fast one.
- **FR-008**: The agent MUST NOT be able to change the provider's configuration (read-only mounts,
  as for `config.yaml`).
- **FR-009**: The tool surface offered to any model MUST be bounded (≤ 10 tools), because tool
  schemas consume a local model's context. Hindsight's MCP endpoint offers 36 tools by default; the
  server allowlist (`HINDSIGHT_API_MCP_ENABLED_TOOLS`) is set to the browse-and-edit set (`recall`,
  `retain`, `list_memories`, `update_memory`, `invalidate_memory`, `list_tags`).
- **FR-010**: Every client MUST reach the same store over the network: the Hermes plugin and the
  injection adapters through Hindsight's REST API, interactive browsing and editing through its MCP
  endpoint over Streamable HTTP. Bearer authentication on both, TLS through Caddy, LAN and tailnet
  only.
- **FR-011**: Each client MUST have its own credential, and every memory records which client wrote
  it. A credential can be revoked without affecting the others. Delivered by a custom Hindsight
  tenant extension (several keys, one schema) and an operation validator that stamps the
  `client:<id>` tag from the key, not from the request. Both are small, tested in `python/tests/`,
  pinned to the Hindsight version and re-checked on every bump. Keys live in the vault.
- **FR-012**: Claude Code's access MUST be its own credential so it can be cut off or reduced to
  read-only (the validator refuses `retain` and edits) without touching Hermes or Open WebUI.
  Its hooks are enabled only in the project settings of private repositories, never globally, so
  EY work sessions neither read nor write the store (Accepted risk).
- **FR-013**: The owner MUST be able to list, correct and delete memories from any client (US-5).
- **FR-014**: Memory written from untrusted content (web pages, tool output) MUST be distinguishable
  from what the owner said, or not written at all. *(Provider-dependent; see Open Questions.)*
- **FR-015**: Monitoring MUST cover: the memory endpoint's liveness (`monitoring_contract` probe),
  a store that stops growing while chats happen (silent write loss), and memory error lines via the
  `092` Loki rules.
- **FR-016**: Existing memory MUST carry over: `USER.md`/`MEMORY.md` stay; Open WebUI's own memories
  are imported once into the store (tagged with their origin), then Open WebUI's memory feature is
  turned off.
- **FR-017**: The egress allowlist (`083` FR-008) gains only what the chosen placement needs.
- **FR-018**: The memory MUST be modular, independent of the agent framework: the store runs as its
  own service reachable over MCP or REST, its data has a documented export format, and the Hermes
  integration is a thin adapter that can be replaced without migrating the store. Switching agent
  framework (or adding a fourth client) MUST mean writing or swapping an adapter, not moving memory.
  Embedding-model coupling is stated explicitly: a model change requires a re-embed, and the plan
  records how.
- **FR-019**: Each client MUST get recall injected before the turn and its turns retained after,
  through a thin adapter against the same API: the Hindsight plugin for Hermes, a filter function
  (inlet recall, outlet retain) for Open WebUI, and prompt-submit and stop hooks for Claude Code.
  Each adapter is small, versioned in this repo (or the owner's dotfiles for Claude Code) and
  replaceable on its own. MCP tools are not the recall path.

### Key Entities

- **Memory item**: a fact, preference or event, with its source client, timestamp, and (if the
  provider supports it) validity window and the item it supersedes.
- **Client identity**: Hermes Agent, Open WebUI, Claude Code. One credential each.
- **Memory service**: Hindsight server and its Postgres on their own LXC; the one store.
- **Client adapter**: per client, injects recall before a turn and retains the turn after it
  (Hermes plugin, Open WebUI filter, Claude Code hooks).
- **Memory endpoint**: the service's REST API (adapters) and MCP endpoint (interactive tools).

## Success Criteria *(mandatory)*

Measured with the spike harness's dataset (synthetic, mixed NO/EN, 9 conversations, 16 probes),
re-run on the LAB rig with the chosen provider.

- **SC-001**: Recall ≥ 14 of 16 probes, including all "volume" probes beyond the built-in budget,
  and strictly better than the built-in-only baseline.
- **SC-002**: Zero stale answers on the two update probes, zero inventions on the negative probe.
- **SC-003**: Zero memory-side LLM calls across the dataset; embedding and rerank calls counted on
  the memory client key and within its rate limit.
- **SC-004**: No egress attempt beyond the gateway during a full run.
- **SC-005**: A fact written by each of the three clients is found by the other two.
- **SC-006**: The restore drill brings back the memory store; the probe set scores the same after.
- **SC-007**: The memory LXC's peak memory within its limit with 30 % headroom (spike: about
  0.4 GB for server and Postgres on a small bank; re-measured after the Open WebUI import).

## Spike results (2026-10-30)

Harness and raw results: [`097-spike/`](./097-spike/). `nousresearch/hermes-agent:v0.21.6`, driven through the gateway API server
exactly as Open WebUI does (full history, no session header), on an internal Docker network whose
only exit is a logging proxy to the Mac's LiteLLM (`coder` for chat, `embed` for embeddings). Every
LLM and embedding call is counted per candidate and phase.

**Baseline, built-in memory only (first run, CLI path, 5 conversations)**: all planted facts landed in
`USER.md`/`MEMORY.md`, and both contradicted facts were *replaced* correctly (Bergen → Trondheim,
coffee → green tea). Failures were the model, not memory: it suggested almond butter with the nut
allergy in `USER.md`, and read "what am I building" as a question about its working directory. The
built-in memory is a strong baseline at small scale; the bake-off therefore adds a volume phase
that overflows the budget.

| candidate | recall /16 | volume /8 | memory LLM calls / turn | embed calls | peak RAM | install path | portability (FR-018) | notes |
|---|---|---|---|---|---|---|---|---|
| built-in only | 11 | 6 | 0 (agent: 4.1 chat calls/turn) | 0 | 381 MiB | stock | **low**: text files; no shared access; Hermes-only injection | evicted the coffee→tea update and the backup decision once full; never stored the sauna |
| Holographic | 12 | 7 | 0 (agent: 2.5) | 0 | 382 MiB | bundled | **low**: SQLite, own schema; no shared access; Hermes-only plugin | no embeddings; English-only auto-extract; missed both Norwegian-only facts (p4, p6) |
| Mnemosyne 4.0.0 / plugin 0.7.7 | **8** | 4 | ~0 (agent: 2.3) | 115 | 648 MiB | derived image | **medium**: one SQLite file + JSON export; MCP; in-process plugin, 42 tools | facts *were* stored but not found: "ingen info om hunden din" with the dog in the store. Norwegian queries fail (upstream #937/#1263). Tool-driven recall: up to 11 memory/search calls on one probe |
| Hindsight 1.1.0, sparing | 15 | 7 | ~1.2 (extraction; estimate: 3.5 vs 2.3 chat/turn) | 75 + 32 rerank | 964 MiB | derived image + ro plugin | **high**: standalone server (Postgres); REST + MCP + SDKs; thin Hermes adapter | answered 15 of 16 probes from *injected* recall, zero memory tool calls; missed only the "ask before network changes" preference |
| Hindsight, chunks (no LLM) | **16** | **8** | **0** | 74 + 33 rerank | 774 MiB | as above | **high**, as above | best score at the lowest cost: verbatim turns, embeddings + rerank only; fewest chat calls on probes (33 vs 63 baseline) |
| Hindsight, full defaults | aborted | n/a | unbounded | n/a | n/a | as above | as above | **starves chat**: one consolidation call held the Mac's one-at-a-time inference queue ~36 min; agent calls got `429` after 600 s. Aborted after 4 of 9 conversations |
| Honcho 3.5.0 (sparing config) | 14 | 7 | ~2–4 (deriver + dialectic; estimate: 6.6 chat/turn vs 2.3) | 237 (most) | 1,062 MiB | derived image + ro plugin; tokenizer files baked in | **medium**: standalone server (Postgres + deriver); REST + MCP + SDKs; thin adapter, but a Honcho-specific data model; AGPL | mostly injected recall. **Derives junk facts from questions**: "owner's winter tyres are stored in a location unknown to owner", "owner belongs to a band" (from the probes). Needs JSON-schema output and tool calling from the model |
| built-in only, rerun (attribution) | 10 | 6 | 0 | 0 | 361 MiB | stock | low | same harness, same data: 10 vs 11 in the first run. **Run-to-run noise is ±1–2 probes** |

Scores were checked answer by answer: the keyword scorer was corrected seven times for false
failures (Norwegian synonyms such as *havbiolog*, "nut-free" read as a nut) and twice for false
passes; p16 (a preference, not a fact) is judged by hand (`overrides.json`). Attribution comes from
each run's `state.db`: which tools answered each probe. Memory-side LLM calls for Hindsight sparing
are estimated from the chat-call difference to the chunks variant, which makes none by design.
Small dataset, one run per candidate (the baseline twice): differences of 1–2 probes are noise. What
is not noise: Hindsight (15–16) and Honcho (14) above the built-in baseline (10–11), Mnemosyne (8)
below it, and the full-defaults stall.

**Reading of the results**: the providers that *inject* recall before the turn (Hindsight, Honcho)
beat the ones that leave recall to the model's tool calls (Mnemosyne, Holographic, built-in session
search). Local models call memory tools unreliably and expensively. Verbatim storage (Hindsight
chunks) did at least as well as LLM extraction and costs no LLM calls, so extraction is not worth
its inference cost on this hardware.

Portability is assessed on three layers, worst layer decides: **data** (exportable in a documented
format, re-embeddable when the embedding model changes), **shared access** (any MCP/REST client,
independent of the agent), and **injection** (pre-turn recall and post-turn write are a thin,
replaceable adapter, not logic inside the agent framework). Rating: *high* = all three hold,
*medium* = data and access hold but the adapter is thick or framework-bound, *low* = data only.

### Findings that bind the plan

- **Mnemosyne refuses to send the embedding key over plain HTTP** (`embeddings.py`, 4.0.0) and
  falls back to `OPENAI_API_KEY`; the PROD gateway is plain HTTP at `192.168.1.220:4000`. It also
  reads its own writable config file that overrides the environment, and `auto_sleep` defaults to on.
  With no embedding URL it defaults to OpenRouter; its fallback LLM downloads a 656 MB GGUF.
- **Hindsight's Hermes plugin defaults break recall for us**: `recall_types: ["observation"]`
  returns nothing when observations are off, and `recall_sync: false` injects recall only on the
  *next* turn. `retain_every_n_turns > 1` buffers in memory and is lost on restart, so it is not a
  safe lever; the extraction mode is.
- **Catalog plugin install builds a separate ~1.6 GB runtime under `$HERMES_HOME/installs`** and
  writes `memory.provider` into `config.yaml`. With our read-only config and backed-up data dir,
  dependencies belong in a derived image.
- **Background LLM work must be off or scheduled.** Hindsight's upstream defaults (consolidation
  after every retain) held the Mac's one-at-a-time inference queue for ~36 min and starved the
  agent's own calls (`429` after 600 s in queue). Any provider's consolidation, dreaming or
  reflection runs in a quiet window or not at all.
- **Questions become "facts" in LLM-extracting providers.** Honcho's deriver stored "owner's winter
  tyres are stored in a location unknown to owner" from the question "where are my winter tyres
  stored?". Extraction quality on the local model is a correctness risk, not only a cost.
- **Honcho downloads its tokenizer at startup** (`openaipublic.blob.core.windows.net`) and crashes
  without egress; its embedding dimension is fixed at deploy (change = new deployment + replay).
- **Hindsight has one shared API key.** `ApiKeyTenantExtension` checks a single
  `HINDSIGHT_API_TENANT_API_KEY`: no per-client identity, no revoking one client, no read-only scope.
  Tags and metadata carry a source per memory, but the client declares them itself. Per-client keys
  need a small custom `TenantExtension` (several keys, one schema) plus an
  `OperationValidatorExtension` (refuse `retain` for a read-only key, stamp an enforced
  `client:<id>` tag). A Caddy layer with one bearer per client could block REST writes but cannot
  filter MCP tools (JSON-RPC on one URL).

### Portability test (2026-10-30, Hindsight chunks mode)

Evidence in [`097-spike/results/hindsight-portability/`](./097-spike/results/hindsight-portability/). Zero chat-model calls (20 embed, 10 rerank).

| test | result |
|---|---|
| Auth on REST and MCP | 401 without or with a wrong key, both surfaces |
| Second client over MCP (Streamable HTTP) | 3/3 recalls correct, including NO question for an EN fact and the reverse |
| Cross-client write | fact written over MCP tagged `client:claude-code`, recalled over REST by the other client |
| Export, wipe Postgres, import into a fresh server | 7/7 documents and facts back in 2 s, re-embedded on import, 6/6 recalls correct, tags kept |
| Re-embed on model change | import re-embeds with the target bank's model; in-place dimension change refused (route: export, wipe, import) |
| `pg_dump` | 128 KB in < 1 s; restore not tested |
| Per-client credentials | **fail as shipped**, see above |
| RAM, idle, 7 documents | Hindsight 319 MiB, Postgres 69 MiB |

Portability is therefore **measured high** for Hindsight on all three layers: documented export,
REST and MCP access independent of Hermes, thin adapter.

## Assumptions

- The Mac remains the only inference host; the gateway's `hermes-embed` (Qwen3-Embedding-0.6B,
  1024 dims, multilingual) is the embedding model for all clients.
- `hermes_agent_version` may be bumped (v0.22.x moved memory providers into the plugin catalog) as a
  separate change if the chosen provider needs it.
- Claude Code reaches the endpoint over the LAN (the corporate proxy blocks the tailnet on the Mac,
  `local-llm` `HOMELAB-LAN-EXPOSURE.md`).

## Out of Scope

- Cloud memory services of any kind.
- Replacing the built-in memory or the curator.
- Memory for other estate services (Home Assistant, financial-scenario).
- Multi-user memory: there is one owner.

## Dependencies

- [`083`](./083-hermes-agent-runtime.md): the agent, its read-only config, egress allowlist, backup.
- [`064`](./064-llm-router.md): `hermes-embed`, `hermes-rerank`, client keys and rate limits.
- [`065`](./065-hermes-service.md): Open WebUI and its MCP connections (`hermes_mcp_servers`).
- [`092`](./092-log-aggregation.md): log-based alerts for memory errors.
- [`067`](./067-lab-prod-same-address-space.md): a real lab for the gate; until then the LAB rig.

## Open Questions

1. ~~**Which provider?**~~ **Resolved** 2026-10-30: Hindsight, verbatim-chunks mode.
2. ~~**Placement**~~ **Resolved** 2026-10-30: its own LXC.
3. ~~**Open WebUI's own memories**~~ **Resolved** 2026-10-30: import once, then turn off.
4. **Untrusted content (FR-014)**: does Hindsight record provenance per memory, or must the
   adapters retain only the owner's own messages (not tool output or fetched pages)?
5. **Hermes version**: the Hindsight plugin (1.2.1) needs Hermes ≥ 0.21.4, so v0.21.6 works with a
   derived image. A bump to v0.22.x stays a separate change.
6. ~~**Per-client credentials (FR-011, FR-012)**~~ **Resolved** 2026-10-30: custom tenant extension
   plus operation validator.
7. ~~**Claude Code adapter scope**~~ **Resolved** 2026-10-30: private repositories only.
