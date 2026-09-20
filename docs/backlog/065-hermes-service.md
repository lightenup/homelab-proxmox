# Feature Specification: Hermes — self-hosted AI workspace on local models

**Feature Branch**: `065-hermes-service`
**Created**: 2026-08-29 | **Rewritten**: 2026-09-20
**Status**: Draft — ready for `/speckit.specify`. Unblocked: [`064-llm-router`](./064-llm-router.md) closed 2026-09-20.
**Input**: Run **Hermes** as a gated LXC: a self-hosted AI workspace reachable as a web app on
desktop and mobile, using **only** the local models behind the `064` gateway, able to call the
homelab's MCP servers, listed on the `hus-sky.no` front page with a liveness probe, and reachable by
SSH. Deliver it as **configuration over the estate's existing patterns**, not as new software.

---

## What changed from the 2026-08-29 draft, and why

The original draft is superseded. Two of its three pillars are gone:

| dropped | why |
|---|---|
| **The Claude "plan door"** — an always-on LXC running the unmodified Claude Code CLI for heavy work | Decision 2026-09-20: local models exclusively. Exploration also found the account available is an **EY enterprise** seat whose org policy sets `allow_routines: false` and `allow_remote_control: false` — precisely the capabilities a plan door needs. It would have required a separate personal subscription. Not pursued. |
| **Quota-awareness** — modelling the 5-hour rolling window and weekly per-model allowance | Those are consumer Pro/Max constructs. With no subscription in the design there is no window to model. The local tier's real constraint is different and is handled by FR-012. |

**What survives:** the persistence split, and the LXC-like-every-other-service shape. Both are
carried forward below.

**What is new:** the web-app interaction model, MCP consumption, embeddings and reranking on the
Mac, and four capabilities chosen deliberately (FR-013 to FR-016).

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The account owner uses Hermes from a phone and a laptop (Priority: P1)

Hermes is only useful if it is *there* — on the sofa, on a train, at a desk — without a VPN dance or
a terminal.

**Independent Test**: Open `https://hermes.hus-sky.no` on a phone and on a desktop browser, sign in,
hold a conversation against a local model, and install it to the phone's home screen.

**Acceptance Scenarios**:
1. **Given** a phone browser, **When** the owner visits the public hostname, **Then** a login is
   required before any chat surface is reachable, and the layout is usable at phone width.
2. **Given** a successful login, **When** the owner sends a prompt, **Then** it is served by a local
   model through the `064` gateway and no provider model ID is named by the client.
3. **Given** the site is open on a phone, **When** the owner adds it to the home screen, **Then** it
   launches as a standalone app (PWA).
4. **Given** anyone who is not the account owner, **When** they reach the public hostname, **Then**
   they cannot self-register and cannot reach any chat surface.

### User Story 2 - It appears on the front page and its state is honest there (Priority: P1)

**Independent Test**: Load `hus-sky.no`, see a Hermes card whose indicator reflects reality, click it,
land on Hermes.

**Acceptance Scenarios**:
1. **Given** the landing page, **When** it loads, **Then** a Hermes card is present with a liveness
   indicator driven by the same `/api/status` mechanism every other card uses.
2. **Given** Hermes is down, **When** the landing page loads, **Then** the card shows it as down
   rather than showing stale success.
3. **Given** the card, **When** it is clicked, **Then** it opens Hermes itself — not a dashboard
   about Hermes. *(This differs from the `llm-router` card deliberately: that one cannot be routed
   to, this one is meant to be.)*

### User Story 3 - Hermes uses the homelab's MCP servers (Priority: P1)

**Independent Test**: In a chat, ask a question only answerable via `market-model` or
`financial-scenario`, and confirm the tool call happens and is attributable.

**Acceptance Scenarios**:
1. **Given** the configured MCP servers, **When** the owner asks something requiring one, **Then**
   Hermes calls it and uses the result.
2. **Given** an MCP server that requires authentication, **When** Hermes calls it, **Then** it
   presents the credential from the vault and is not refused.
3. **Given** an MCP server that is down, **When** a tool call is attempted, **Then** the chat shows a
   legible error naming the server — never a hang, never a silent wrong answer.
4. **Given** a new MCP server appears in the homelab, **When** it is added, **Then** it is a
   configuration entry, not a code change.

### User Story 4 - The owner reaches the box, and the box survives a rebuild (Priority: P1)

**Independent Test**: SSH in by key; destroy and rebuild the LXC from code; restore; confirm
conversations, settings and knowledge are intact.

**Acceptance Scenarios**:
1. **Given** the LXC, **When** the owner SSHes with their key, **Then** they get a shell — by key
   only, from the LAN.
2. **Given** accumulated state, **When** the LXC is rebuilt from code and restored, **Then** prior
   conversations, users, settings and knowledge return.
3. **Given** the state store, **When** its location is inspected, **Then** it is on the LXC's **local
   disk**, bind-mounted so the backup role can reach it — **not** on an NFS mount.
4. **Given** the backup role, **When** it runs on schedule, **Then** a restorable artifact lands on
   the Synology and its age is monitored.

### User Story 5 - Hermes degrades honestly when the Mac is away (Priority: P2)

The defining constraint: Hermes is always-on, its brain is not. Everything on the Mac is
session-scoped and dies at logout.

**Independent Test**: Log the Mac out, use Hermes, observe the failure.

**Acceptance Scenarios**:
1. **Given** the Mac is asleep or logged out, **When** the owner sends a prompt, **Then** Hermes
   returns a legible error naming the unavailable backend within seconds — never a hang.
2. **Given** the Mac is away, **When** the owner loads Hermes, **Then** the UI itself still loads and
   past conversations are readable.
3. **Given** the Mac returns, **When** the next prompt is sent, **Then** it is served with no
   operator action.
4. **Given** a scheduled job (FR-016) fires while the Mac is away, **Then** it fails clean and its
   failure is visible — it does not silently produce nothing.

### User Story 6 - Documents and knowledge (Priority: P3)

**Independent Test**: Upload a document, ask a question answerable only from it, get a grounded
answer with a citation.

**Acceptance Scenarios**:
1. **Given** an uploaded document, **When** the owner asks about its contents, **Then** the answer
   cites the source passage.
2. **Given** retrieval, **When** it runs, **Then** embeddings and reranking come from the local
   stack — no third-party embedding API is called.

### Edge Cases

- **Open WebUI's own overhead multiplies request rate.** It issues additional "task model" calls per
  chat — title generation, tag generation, query rewriting. Against a 60 rpm client key and a
  single-Mac backend this can exceed the ceiling during ordinary use. Must be configured
  deliberately (FR-012), not discovered.
- **A long local generation exceeds the reverse proxy's timeout.** `064` holds 20-minute requests;
  Caddy must not cut them shorter. `caddy_services` supports `proxy_timeout` — it must be set.
- **The Mac sleeps mid-generation.** Open connections die; the UI must surface an error, not spin.
- **A scheduled job runs while nobody is watching** and fails silently — see AS-5.4.
- **The admin account is the only thing between the internet and the homelab's MCP servers.**
- **RAG indexing of a large document set** while the Mac is the only embedding source: slow, and it
  competes with interactive chat for the same rate limit.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Hermes MUST be delivered as **configuration of existing, unmodified upstream software**
  — no bespoke application code. The chosen application is **Open WebUI**, deployed by
  `docker_compose_v2` on an unprivileged `lxc_service` LXC, pinned to a specific non-`latest` tag.
- **FR-002**: Hermes MUST address models **only** through the `064` gateway's intent aliases
  (`hermes-fast`, `hermes-balanced`, `hermes-deep`) using the `hermes` client key. It MUST NOT hold a
  provider credential, name a provider model, or reach oMLX directly.
- **FR-003**: Hermes MUST be reachable at a **public hostname** (`hermes.hus-sky.no`) served by the
  existing Caddy reverse proxy, and MUST present a **usable interface on both phone and desktop**
  browsers, installable as a PWA.
- **FR-004**: **Hermes MUST authenticate every request itself.** The reverse proxy provides no
  authentication. Self-registration MUST be disabled; accounts are created by the administrator. No
  chat surface, model list, tool, or uploaded document may be reachable unauthenticated.
- **FR-005**: Hermes MUST appear on the `hus-sky.no` landing page as a card that **links to Hermes
  itself**, with a liveness indicator driven by the existing `/api/status` → `probe_success`
  mechanism.
- **FR-006**: The LXC MUST be reachable by **SSH with key authentication** from the LAN, via
  `lxc_service`'s `ssh_public_keys`. No public SSH route.
- **FR-007**: Hermes MUST be able to call the homelab's **MCP servers** over Streamable HTTP, as
  configuration. Servers requiring authentication MUST receive their credential from the Ansible
  vault; no credential in git. Initial set: `market-model`, `financial-scenario`.
- **FR-008**: **State MUST live on the LXC's local disk**, bind-mounted so a dedicated backup role can
  reach it, with backups pushed to the Synology and their age monitored. State MUST NOT sit on an NFS
  mount — a SQLite database or vector index over NFS invites locking failures and corruption.
- **FR-009**: Hermes MUST publish a **monitoring contract**: a liveness probe, a scrape target if the
  application exposes one, and an alert when it is unreachable. Backup age MUST alert.
- **FR-010**: When the local tier is unavailable, Hermes MUST **fail clean** — a legible error naming
  the backend, within seconds, never a hang. The UI and prior conversations MUST remain usable.
- **FR-011**: **Retrieval MUST use the local stack.** Embedding and reranking models MUST be served by
  **oMLX on the Mac** and reached through the `064` gateway as additional aliases. No third-party
  embedding API. *(Verified 2026-09-20: oMLX serves `/v1/embeddings` and `/v1/rerank` and supports
  BERT, BGE-M3 and ModernBERT; the installed build carries `scheduler.embedding_batch_size`.)*
- **FR-012**: The deployment MUST **bound its own request rate** against the gateway. The
  application's auxiliary model calls (title, tag and query generation) MUST be configured
  deliberately — pointed at the cheapest alias, or disabled — and the `hermes` key's `rpm_limit` in
  `064` reviewed against measured usage rather than assumed.

#### Chosen capabilities

- **FR-013**: **Web search.** Hermes MUST be able to search the web and cite results, using a
  **self-hosted SearXNG** — no third-party search API key, no query leaving the estate to a
  commercial engine. Whether SearXNG is a sidecar container on the Hermes LXC or its own service is a
  planning decision.
- **FR-014**: **Voice.** Hermes MUST support speech-to-text and text-to-speech, with STT served
  **locally** (Whisper), so dictation on mobile does not send audio to a third party.
- **FR-015**: **An outbound API.** Hermes MUST expose its own OpenAI-compatible endpoint so other
  homelab services and scripts can call it *with its models, tools and knowledge attached* rather
  than calling the raw gateway. This endpoint is subject to FR-004.
- **FR-016**: **Scheduled work.** Hermes MUST support recurring prompts on a schedule, running
  through the normal chat pipeline so tools and knowledge apply. Failures MUST be visible (AS-5.4).
  *(Verified 2026-09-20: Open WebUI has a native Automations feature with hourly/daily/weekly/RRULE
  scheduling, gated by `ENABLE_AUTOMATIONS`.)*

### Key Entities

| Entity | Notes |
|---|---|
| **Workspace state** | Conversations, users, settings, prompts, knowledge. SQLite on local disk by default; Postgres is an alternative if concurrency ever justifies it. The backup unit. |
| **Vector store** | Embeddings for uploaded documents. Local disk, same backup unit. Rebuildable from source documents but expensive to rebuild. |
| **MCP server registration** | `{name, url, transport, auth}`. Configuration, never code. |
| **Model alias** | Owned by `064`, not here. Hermes names aliases only. |
| **Scheduled job** | `{name, prompt, model, schedule}`. User-owned; part of workspace state. |

---

## Success Criteria *(mandatory)*

- **SC-001**: The owner can hold a conversation with a local model from a phone browser, away from
  the LAN, in under 30 seconds from tapping the front-page card.
- **SC-002**: An unauthenticated request to any Hermes surface is refused — verified against the
  chat UI, the model list, and the FR-015 API endpoint.
- **SC-003**: A question requiring an MCP tool is answered using that tool, and the call is visible.
- **SC-004**: Adding a new MCP server, or repointing to a different alias, is a configuration edit
  with no template or code change.
- **SC-005**: With the Mac logged out, every prompt returns a legible error in under 10 seconds, the
  UI stays up, and past conversations remain readable.
- **SC-006**: The LXC is destroyed, rebuilt from code and restored; prior conversations, users,
  settings and knowledge are all present.
- **SC-007**: A document uploaded and queried returns an answer citing it, with embeddings and
  reranking served from the Mac.
- **SC-008**: Under a representative hour of interactive use, the `hermes` key stays inside its
  `rpm_limit` — measured from gateway metrics, not estimated.
- **SC-009**: A generation lasting 15 minutes completes without the reverse proxy cutting it.
- **SC-010**: A scheduled job that fires while the Mac is away is visibly failed, not silently absent.

---

## Decisions

- **D-001 — Open WebUI over LibreChat.** Both are configuration-driven and OpenAI-compatible.
  Deciding factor: **Open WebUI's native MCP support is Streamable HTTP, and both homelab MCP servers
  speak exactly that** (verified 2026-09-20 — `market-model` and `financial-scenario` both answer MCP
  protocol handshakes over HTTP). LibreChat's broader stdio/SSE transports buy nothing here, and it
  brings MongoDB and Meilisearch to back up instead of one SQLite file. Open WebUI also ships the PWA,
  Automations, SearXNG and Whisper integrations this spec needs, as configuration.
- **D-002 — Application-level authentication, not a new auth layer.** Caddy adds none today and every
  public service here authenticates itself. Adding `forward_auth`/Authelia would be better defence in
  depth *and benefit the whole estate*, but it is a service and a spec of its own and it touches the
  proxy everything depends on. **Deliberately deferred, and recorded as the top risk below** — this is
  the weakest point in the design, not an oversight.
- **D-003 — Embeddings on the Mac rather than in-container.** Chosen for quality and for "local
  models exclusively" meaning one place for inference. Accepted cost: **retrieval stops working when
  the Mac is away**, where in-container CPU embeddings would have kept working. Consistent with
  FR-010 — it must fail clean.
- **D-004 — Reranking is in scope because it became free.** oMLX serves `/v1/rerank` and Open WebUI's
  retrieval supports hybrid search with reranking. This was not requested; it is a small addition
  that materially improves RAG quality on the same infrastructure.
- **D-005 — SQLite on local disk, not Postgres.** Single user. `financial-scenario` sets the
  precedent: local disk specifically so the backup role can reach it. Postgres remains available if
  concurrency ever justifies it.

## Assumptions

- The Mac remains the sole inference host, session-scoped, and its absence is normal rather than
  exceptional. Hermes is built around that, not in spite of it.
- `192.168.1.221` is the next free service address (`.210`–`.220` are allocated).
- The account owner is the only user. Multi-user is not designed for, though the application supports
  it if that changes.
- The `hermes` client key in `064` will need its `models` scope extended to cover the new embedding
  and reranking aliases — a `064` change, made as part of this feature.

## Out of Scope

- **Any Anthropic subscription, OAuth session or "plan door".** Removed by decision — see the table
  at the top.
- **Quota modelling of consumer subscription windows.** No subscription in the design.
- **An estate-wide authentication layer.** Worth doing, deliberately not done here (D-002).
- **Multi-user, SSO, LDAP.** Available upstream; not configured.
- **Image generation.** No backend for it, and no GPU on the LXC.
- **Making the Mac always-on.** The fail-clean behaviour is the answer, not new hardware.

## Dependencies

- **[`064-llm-router`](./064-llm-router.md)** — closed. Provides the gateway, the `hermes` key and
  the aliases. This feature **amends** it: new embedding and reranking aliases, and an extended
  `models` scope on the `hermes` key.
- **The Mac** — oMLX must additionally host an embedding model and a reranker, and the Mac's LiteLLM
  must expose them. Both are new Mac-side work.
- **Reverse proxy** — a `caddy_services` entry with `user_facing: true` and a `proxy_timeout` long
  enough for FR-010's 20-minute ceiling.
- **Monitoring** — a monitoring contract. Note [`072`](./072-lab-monitoring-deploy-wipes-prod.md):
  monitoring deploys go through the **prod** path only.
- **Backup** — a dedicated backup role, following `financial_scenario_backup`.

## Risks & Fallbacks

| risk | mitigation |
|---|---|
| **An internet-facing app login is the only thing guarding the LLM gateway and the homelab's MCP servers.** A CVE in that login is a hole with real reach. | Pin the image and track releases deliberately; disable self-registration; a strong unique admin credential; keep the blast radius small by scoping the `hermes` key to aliases only. Revisit D-002 — `forward_auth` remains the real fix. |
| Auxiliary model calls blow the rate limit during ordinary use | FR-012 — configure them explicitly and measure before raising limits |
| RAG silently degrades when the Mac sleeps | FR-010 fail-clean applies to retrieval too, not just chat |
| Long generations cut by the proxy | `proxy_timeout` set and covered by SC-009 |
| Backup exists but has never been restored | SC-006 makes restore an acceptance criterion, not a hope |
| SearXNG becomes a second unmaintained service | Decide sidecar vs own service at planning; a sidecar keeps it inside this feature's backup and monitoring |
