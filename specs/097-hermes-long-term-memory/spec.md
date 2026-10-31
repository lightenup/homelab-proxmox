# Feature Specification: Long-term memory for Hermes, shared with the owner's other AI clients

**Feature Branch**: `097-hermes-long-term-memory`

**Created**: 2026-10-31

**Status**: Draft

**Input**: Backlog item [`docs/backlog/097-hermes-long-term-memory.md`](../../docs/backlog/097-hermes-long-term-memory.md).
The owner wants the Hermes agent to remember facts about them beyond the small built-in memory
budget, and wants that one memory shared with Open WebUI and Claude Code, so the three clients
stop knowing different things. Memory runs as its own service; each client reaches it through a
thin adapter. Everything stays local, and memory makes as few inference calls as possible. The
provider (Hindsight, verbatim-chunks mode), its placement (its own LXC) and the Open WebUI
migration were decided after a measured bake-off on 2026-10-30; the evidence and the findings that
bind the plan are in the backlog item and [`097-spike/`](../../docs/backlog/097-spike/). This
feature amends `083` (built-in memory only) and `065` (Open WebUI keeps its own memories).

## Clarifications

### Session 2026-10-31

- Q: Which part of each turn do the adapters store (FR-014)? → A: Full turns, the owner's message
  and the assistant's reply, each labelled with its source. Raw tool output and fetched pages are
  never stored.
- Q: Should the memory service's own web UI be offered, and with what rights? → A: Yes, listed on
  the portal page, read-write. It may also hard-delete a whole conversation and retry failed writes.
  It may not change memory settings or start any inference feature (FR-023).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Hermes remembers more about me than its built-in memory holds (Priority: P1)

The owner tells Hermes about themselves over many conversations. In a later conversation, Hermes
answers from what it was told, including facts from long ago, and gives the latest value of facts
that changed.

**Why this priority**: This is the first gap the feature closes. The built-in memory holds about
500 tokens about the owner; beyond that, facts are dropped or compressed. The bake-off showed the
built-in memory evicting an update and a decision once full.

**Independent Test**: Tell Hermes about 40 facts across ten conversations, more than the built-in
budget holds. In a new conversation, ask about facts from the first and the last conversation. Both
are answered correctly, and facts that changed (moved city, quit coffee) come back in their latest
form.

**Acceptance Scenarios**:

1. **Given** more facts than the built-in memory holds, **When** a fresh conversation asks about
   any of them, **Then** the agent answers from memory, not from general knowledge.
2. **Given** a fact that was later contradicted, **When** the owner asks about it, **Then** the
   newer value is given and the old one is not presented as current.
3. **Given** a topic the owner never mentioned (a cat), **When** the owner asks about it, **Then**
   the agent says it does not know rather than inventing an answer.
4. **Given** facts told in Norwegian, **When** the owner asks in English (or the reverse), **Then**
   recall works across the language boundary.
5. **Given** a fresh conversation, **When** the owner's first message needs a remembered fact,
   **Then** the fact is available on that first turn.

---

### User Story 2 - What I tell one client, the others know (Priority: P1)

A fact told to Open WebUI, Hermes or Claude Code is known to the other two, and the owner can see
which client recorded it.

**Why this priority**: This is the second gap. Today Open WebUI, Hermes and Claude Code each know
different things, and Claude Code knows nothing from the other two.

**Independent Test**: Tell Open WebUI (plain chat, not the agent) "my sister lives in Tromsø". In
Claude Code on the Mac, ask "where does my sister live?" and get the answer from shared memory. Then
tell Claude Code a new fact and ask Hermes about it from the phone.

**Acceptance Scenarios**:

1. **Given** a fact recorded by any one client, **When** another client asks about it, **Then** it
   is found.
2. **Given** a memory, **When** the owner asks which client recorded it, **Then** the memory shows
   the client, and that client identity cannot be set by the client itself.
3. **Given** the owner works in a non-private (work) repository in Claude Code, **When** a session
   runs, **Then** it neither reads from nor writes to the shared memory.

---

### User Story 3 - Memory costs little inference and never blocks chat (Priority: P1)

Memory adds no inference calls of its own, its traffic is counted apart from chat, and an outage of
the memory service or of the inference host never stops a conversation or loses a write silently.

**Why this priority**: The Mac is the one inference host and serves one request at a time. In the
bake-off, one provider's background work held the queue for about 36 minutes and starved chat.

**Independent Test**: Over a day of normal use, memory-side traffic through the gateway is counted
under memory's own client identity and contains no chat-model calls. With the memory service
stopped, a Hermes conversation still completes using built-in memory, and the failure is logged.
With the Mac asleep, a write that cannot be stored is reported as failed, not as stored.

**Acceptance Scenarios**:

1. **Given** normal use, **When** memory stores and recalls, **Then** it makes embedding and
   rerank calls only, under its own gateway identity and rate limit.
2. **Given** the memory service is unreachable, **When** the owner chats with any client, **Then**
   the turn completes without shared memory and the failure is logged.
3. **Given** the inference host is unavailable, **When** a client tries to store a memory, **Then**
   the write is retried or reported as failed, and recall fails visibly instead of returning "no
   memories".

---

### User Story 4 - Memory survives a rebuild and can be restored (Priority: P2)

The memory store is backed up nightly in two forms, a fast restore copy and a portable export, and
a restore drill proves it comes back.

**Why this priority**: Once memory holds more than the built-in files, losing it costs more. It
depends on the store existing (US-1).

**Independent Test**: A restore drill, modelled on the existing Hermes restore drill, restores the
store from the nightly backup into a fresh container. A probe question answered before the drill is
answered the same after.

**Acceptance Scenarios**:

1. **Given** a nightly backup, **When** the drill restores it into a fresh container, **Then** the
   probe set scores the same as before.
2. **Given** the portable export, **When** it is imported into a fresh store, **Then** all memories
   and their client identities come back, re-embedded with the current embedding model.

---

### User Story 5 - I can see, correct and forget memories (Priority: P2)

The owner asks any client what it remembers about a topic, corrects a wrong fact and asks it to
forget something. The change holds for every client.

**Why this priority**: Memory that cannot be inspected or corrected becomes a liability over time,
especially for facts that should not be kept.

**Independent Test**: Ask "what do you remember about my car?", correct a wrong fact, and ask to
forget the licence plate. The listing is accurate, the correction holds, and the forgotten fact is
gone from all three clients. Repeat the listing and a correction in the memory web UI from the
portal page.

**Acceptance Scenarios**:

1. **Given** memories about a topic, **When** the owner asks to see them from any client, **Then**
   the listing matches the store.
2. **Given** a wrong memory, **When** the owner corrects it, **Then** every client recalls the
   corrected value.
3. **Given** a memory the owner asks to forget, **When** any client is later asked about it,
   **Then** it is not recalled.
4. **Given** the memory web UI on the portal page, **When** the owner signs in, **Then** they can
   browse, search, correct and hide memories, delete a whole conversation and retry failed writes,
   and every change is recorded as made from the web UI.
5. **Given** the memory web UI, **When** anyone opens it without signing in, **Then** no memory is
   shown. **When** the signed-in owner tries to change memory settings, add a webhook or start an
   inference feature, **Then** it is refused.

---

### Edge Cases

- **Inference host asleep or away**: embeddings come from the Mac through the gateway. A write that
  cannot be embedded is not silently dropped, and recall fails visibly.
- **Silent write loss**: a store that reports success while persisting nothing (seen in a rejected
  candidate during the bake-off) is caught by the deploy check and by monitoring.
- **First message of a conversation**: Open WebUI and phone conversations are mostly single-turn,
  so recall that arrives only on the second turn is useless.
- **Two writers at once**: the agent and the other clients write to the same store concurrently
  without lock errors or lost writes.
- **Prompt injection into memory**: a web page or tool result read by the agent is written to
  memory and then injected into every later conversation of every client. Raw tool output is never
  stored (FR-014); injected text the assistant repeats in its reply is stored, labelled as the
  assistant's, not the owner's.
- **The agent edits its own memory configuration** or reads a credential it could misuse.
- **A Hermes upgrade disables the memory integration** without anyone noticing.
- **Memory service unreachable**: an outage, a restart, or every LAB run of Hermes (its lab copy
  cannot reach the production memory service). Chat carries on with built-in memory only.
- **Lab copy without embeddings**: the memory service's lab copy cannot reach the gateway (`067`),
  so it must start and pass its liveness check without embedding anything.
- **Runtime installs**: a component that downloads packages or models at runtime fails behind the
  agent's egress allowlist, or pulls unpinned code.
- **Open WebUI chat with the agent model**: the agent stores that turn itself; Open WebUI must not
  store it a second time.
- **Claude Code read-only or revoked**: the owner cuts Claude Code's access or makes it read-only;
  Hermes and Open WebUI keep working unchanged.
- **Web UI without its login key**: the upstream UI is open to anyone who can reach it when no
  login key is set; the deploy must refuse to start it that way.
- **Write operations beyond memories**: the store offers about 45 write operations (webhooks, bank
  settings, directives, mental models). A client key that is allowed "everything but a few" could
  send memories to the internet through a webhook or switch inference back on.
- **Forgotten facts in backups**: a forgotten fact remains in older backups until they age out.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Hermes MUST use Hindsight as its one external memory provider, set in the
  deploy-owned, read-only agent configuration. Hermes's built-in memory stays on (`083`).
- **FR-002**: The provider, its adapters and their dependencies MUST be installed at build or deploy
  time, pinned to exact versions, never at runtime (no lazy package installs, no model downloads).
  Every pin MUST be re-checked when the Hermes version or the Hindsight version is bumped.
- **FR-003**: Storage, embeddings and any memory-side inference MUST stay in the estate. Embeddings
  and rerank MUST go through the estate gateway. Every vendor default that points at a cloud
  endpoint MUST be overridden, and the override MUST be asserted by a test.
- **FR-004**: The store MUST run in verbatim-chunks mode with consolidation, observations and
  reflection off, so it makes zero memory-side chat-model calls (embeddings and rerank only). Any
  later inference pass (consolidation, extraction) is a separate decision, MUST run in a scheduled
  quiet window, and MUST never hold the inference queue while chat is active. Memory traffic MUST
  use its own gateway client identity, so it is counted and rate-limited apart from chat.
- **FR-005**: Recall MUST work on the first turn of a fresh conversation and MUST return stored
  turns and facts, not only derived summaries (the plugin's defaults return nothing in this mode;
  see backlog findings).
- **FR-006**: A failed memory write (embedding unavailable, store busy) MUST NOT be reported as
  success. It MUST be retried or surfaced in the client's logs.
- **FR-007**: The store MUST sit on the memory LXC's local disk (no NFS, `083`). It MUST be backed
  up nightly to the NAS through the estate's service backup in two forms: a database dump (the fast
  restore) and the provider's documented export (the portable copy, FR-018). A restore drill MUST
  prove the dump restores (US-4).
- **FR-008**: The agent MUST NOT be able to change the provider's configuration, as for its own
  configuration today.
- **FR-009**: The memory tool surface offered to any model MUST be at most 10 tools, because tool
  schemas consume a local model's context. The service's interactive tool endpoint MUST expose only
  the browse-and-edit set: recall, store, list, update, invalidate and list tags.
- **FR-010**: Every client MUST reach the same store over the network: adapters through the
  service's REST API, interactive browsing and editing through its MCP endpoint. Both MUST require a
  bearer credential, MUST be served over TLS through the reverse proxy, and MUST be reachable from
  the LAN and the tailnet only. The web UI (FR-023) reaches the API inside the memory service; the
  owner's browser reaches the UI over TLS through the reverse proxy. The service's direct port on
  its own address exists only for the reverse proxy, monitoring and health checks. No client is
  configured to use it, and a test asserts this. A request there still needs a credential, and
  the agent's egress rules block it.
- **FR-011**: Each client MUST have its own credential, and every memory MUST record which client
  wrote it. The service MUST derive that identity from the credential, never from the request. A
  credential MUST be revocable without affecting the other clients. Each credential MUST be
  limited to an explicit list of allowed operations; anything not listed is refused. Only the
  backup credential may export, import or change memory settings, and no credential may create
  webhooks or start an inference pass (FR-004). Upstream offers one shared key
  only, so this is delivered by a small extension kept in this repo, unit-tested, pinned to the
  Hindsight version and re-checked on every bump. Credentials live in the vault.
- **FR-012**: Claude Code's credential MUST be revocable alone and reducible to read-only (stores
  and edits refused) without touching Hermes or Open WebUI. Claude Code's adapter MUST be enabled
  only in the owner's private Claude Code installation (personal account, never the EY enterprise
  seat) and only for the owner's private repositories, so work sessions neither read nor write the
  store.
- **FR-013**: The owner MUST be able to list, correct and delete memories from any client (US-5).
- **FR-014**: Memory derived from untrusted content (web pages, tool output) MUST be distinguishable
  from what the owner said, or not stored at all. Adapters MUST store full turns, the owner's
  message and the assistant's reply, each labelled with its source, and MUST NOT store raw tool
  output or fetched pages. Recalled memory MUST keep the label, so a client can tell the owner's
  words from the assistant's.
- **FR-015**: Monitoring MUST cover the memory endpoint's liveness through the estate's standard
  probe, a store that stops growing while chats happen (silent write loss), and memory error lines
  through the log-aggregation rules of `092`.
- **FR-016**: Existing memory MUST carry over. Hermes's built-in memory files stay. Open WebUI's own
  memories MUST be imported once into the store, tagged with their origin, and Open WebUI's memory
  feature MUST then be turned off.
- **FR-017**: The agent's egress allowlist (`083`) MUST gain only the rule the memory service's
  placement needs.
- **FR-018**: The memory MUST be independent of the agent framework: the store runs as its own
  service, its data has a documented export format, and each client integration is a thin adapter
  that can be replaced without migrating the store. Switching agent framework or adding a client
  MUST mean writing or swapping an adapter, not moving memory. A change of embedding model requires
  a re-embed, and the plan MUST record how it is done.
- **FR-019**: Each client MUST get recall injected before a turn and its turn stored after it,
  through a thin adapter against the same API: the provider's plugin for Hermes, a filter for Open
  WebUI, and prompt-submit and stop hooks for Claude Code. Each adapter is small, versioned in this
  repo (or the owner's dotfiles for Claude Code) and replaceable on its own. Tool calls are not the
  recall path.
- **FR-020**: The memory service MUST fit the isolated lab of `067`. It is created with the
  lifecycle workflow and deployed only through the promotion workflow. It gets a production address
  and a mirrored lab address in the lab overrides. Its backup timer is not created in lab. Its
  gateway credential is classified `internal`, like every other gateway client key, so no lab
  switch is needed. Its LAB check is
  liveness only and needs no embeddings. Hermes's LAB rehearsal MUST pass with the memory service
  unreachable.
- **FR-021**: Before the first PROD promotion that turns memory on, and before any later change to
  the provider, its version, its mode or an adapter, the spike harness MUST run on the dev Mac
  against the exact pinned images and the production-rendered memory configuration, and MUST meet
  SC-001 to SC-005. Its results MUST be recorded with the change.
- **FR-022**: `083`'s "built-in memory only" requirement and `065`'s use of Open WebUI's own
  memories MUST be amended to describe the shared memory.
- **FR-023**: The memory service's web UI MUST be listed on the portal page and MUST require its
  own login (a key held in the vault and the owner's password manager); it MUST NOT start without
  one. It acts as a fourth client with its own credential, so its changes are attributed to it. It
  may browse, search, add, correct and hide memories, delete a whole conversation and retry failed
  writes. Every other write it offers (memory settings, webhooks, directives, mental models,
  export, import, bank deletion) and every inference feature MUST be refused.

### Key Entities

- **Memory item**: a stored turn or fact, with the client that wrote it, when it was written, its
  source within the turn (owner or assistant), and its origin (for imported Open WebUI memories).
- **Client identity**: Hermes, Open WebUI, Claude Code or the web UI, plus the backup. One
  credential each, with a scope (read-only, read-write, curator for the web UI, admin for the
  backup) and a revocation state.
- **Memory service**: the one store, on its own LXC, with its own lifecycle, backup and monitoring.
- **Client adapter**: per client, injects recall before a turn and stores the turn after it.
- **Memory endpoint**: the service's REST API (adapters) and MCP endpoint (interactive browsing and
  editing).
- **Memory web UI**: the service's own browser interface on the portal page, behind its own login.
- **Memory export**: the portable copy of the store, without embeddings, importable into a fresh
  store.

## Success Criteria *(mandatory)*

SC-001 to SC-005 are measured with the spike harness's dataset (synthetic, mixed Norwegian and
English, 9 conversations, 16 probes) on the dev Mac before the PROD promotion (FR-021). SC-006 and
SC-007 are measured on the production LXC after it. SC-008 is the LAB rehearsal. Run-to-run noise
in the bake-off was 1 to 2 probes.

### Measurable Outcomes

- **SC-001**: At least 14 of 16 probes are answered correctly, including all 8 probes that exceed
  the built-in budget, and the score is strictly above the built-in-only baseline on the same run.
- **SC-002**: Zero stale answers on the 2 update probes and zero invented answers on the negative
  probe.
- **SC-003**: Zero memory-side chat-model calls across the dataset. All embedding and rerank calls
  are counted under memory's own gateway identity and stay within its rate limit.
- **SC-004**: No outbound connection attempt beyond the gateway during a full run.
- **SC-005**: A fact written by each of the 3 clients is found by the other 2 (6 of 6 cross-client
  recalls).
- **SC-006**: The restore drill brings back the memory store, and the probe set scores the same
  after as before.
- **SC-007**: The memory LXC's peak memory use stays within its limit with at least 30 % headroom,
  measured after the Open WebUI import (spike: about 0.4 GB on a small store).
- **SC-008**: The LAB rehearsals of the memory service and of Hermes both pass, the production
  fingerprint is unchanged (`067`), and no backup timer, scrape target or probe is created for the
  lab copy.
- **SC-009**: With Claude Code's credential set to read-only, a store attempt from Claude Code is
  refused while recall still works; with it revoked, Claude Code gets no memory and Hermes and Open
  WebUI are unaffected.
- **SC-010**: With the memory service stopped, a Hermes conversation completes and the failure
  appears in the estate's logs within 5 minutes.
- **SC-011**: The web UI is on the portal page. Without signing in it shows no memory. A
  correction made in it is recalled by all three clients and attributed to the web UI. A memory
  settings change, a webhook and a reflect request from it are all refused.

## Assumptions

- The Mac remains the only inference host, and the gateway's multilingual embedding model is the
  embedding model for all clients.
- Hermes stays on its current version (v0.21.6) and its stock image. The provider's plugin and its
  four pinned packages are fetched at deploy with checksums and mounted read-only (plan research
  R-003). A bump to v0.22.x is a separate change.
- Claude Code reaches the memory endpoint over the LAN, because the corporate proxy blocks the
  tailnet on the Mac.
- Claude Code runs on Anthropic's models, so anything it recalls is sent to Anthropic as prompt
  content. Resolved 2026-10-31 (T048): the owner uses only a private Claude Code installation on a
  personal account for this, on the Mac (its own config directory) and on the Linux laptop. The EY
  enterprise seat never holds the hooks, the MCP server or the key, so the Claude Enterprise Guidance
  & Guidelines check no longer applies and no work context reaches the store. Read-write sharing,
  bounded by FR-012.
- A forgotten memory remains in older backups until the estate's backup retention ages them out
  (up to about 6 months for monthly copies). Forgetting applies to the live store only.
- The address `192.168.1.223` (lab `10.99.0.223`) is free; to be confirmed in the plan.
- Whether the provider starts and answers liveness without an embedding endpoint, and whether the
  Hermes plugin fails open when the service is down, were not tested in the spike. The plan verifies
  both (backlog open question 8).

## Out of Scope

- Cloud memory services of any kind.
- Replacing Hermes's built-in memory or its curator.
- Memory for other estate services (Home Assistant, financial-scenario).
- Multi-user memory: there is one owner.
- Any memory-side inference pass (consolidation, extraction); a later, separate decision (FR-004).

## Dependencies

- `083` Hermes agent runtime: the agent, its read-only configuration, egress allowlist and backup.
  Amended.
- `064` LLM router: the embedding and rerank aliases, client keys and rate limits.
- `065` Hermes service: Open WebUI and its tool connections. Amended.
- `092` log aggregation: log-based alerts for memory errors.
- `067` isolated lab: constrains the LAB rehearsal (FR-020) and moves quality checks to the
  harness (FR-021).
- A private Claude Code installation on a personal account (resolved 2026-10-31, see Assumptions).
