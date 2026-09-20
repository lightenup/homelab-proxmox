# Feature Specification: Hermes — a self-hosted AI workspace on local models

**Feature Branch**: `065-hermes-ai-workspace`
**Created**: 2026-09-20
**Status**: Draft
**Input**: User description: "Hermes: a self-hosted AI workspace on a gated LXC, reachable as a public web app on desktop and mobile, using only the local models behind the 064 gateway, able to call the homelab MCP servers, listed on the hus-sky.no front page with a liveness probe, and reachable by SSH. Delivered as configuration of existing upstream software rather than new code."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The owner talks to a local model from wherever they are (Priority: P1)

The account owner opens Hermes from a phone on the train, or a laptop at a desk, signs in, and holds
a conversation with a model running on hardware they own. No VPN step, no terminal, no third party
receiving the conversation.

**Why this priority**: This is the feature. Everything else is in service of it, and on its own it is
already worth deploying — a private assistant reachable from anywhere is the whole point.

**Independent Test**: Visit the public address from a phone browser on mobile data, sign in, send a
prompt, receive an answer, and add the site to the phone's home screen.

**Acceptance Scenarios**:

1. **Given** a phone browser away from the home network, **When** the owner visits the public
   address, **Then** they are asked to sign in before any conversation surface is reachable.
2. **Given** a signed-in session, **When** the owner sends a prompt, **Then** an answer is produced
   by a model running on the owner's own hardware, and the request never leaves the owner's estate.
3. **Given** the site open on a phone, **When** the owner adds it to the home screen, **Then** it
   launches as a standalone application rather than a browser tab.
4. **Given** the interface at phone width, **When** the owner uses it, **Then** every primary action
   is reachable without horizontal scrolling or zooming.
5. **Given** a person who is not the account owner, **When** they reach the public address, **Then**
   they cannot create an account and cannot reach any conversation, model list, or document.

---

### User Story 2 - Hermes appears on the homelab front page and tells the truth there (Priority: P1)

The owner lands on the homelab's front page and sees Hermes alongside the other services, with an
indicator showing whether it is actually up. Clicking the card opens Hermes.

**Why this priority**: Discoverability is how the estate works, and an indicator that lies is worse
than no indicator. Independently valuable: the card is the owner's route in.

**Independent Test**: Load the front page, observe the Hermes card and its state, stop Hermes,
reload, observe the state change, restart, click through.

**Acceptance Scenarios**:

1. **Given** the front page, **When** it loads, **Then** a Hermes card is shown with a liveness
   indicator produced the same way every other service's indicator is produced.
2. **Given** Hermes is unavailable, **When** the front page loads, **Then** the card reports it as
   down rather than showing a stale success.
3. **Given** the Hermes card, **When** it is clicked, **Then** it opens Hermes itself.

---

### User Story 3 - Hermes can use the homelab's own tools (Priority: P1)

The owner asks a question that can only be answered by one of the homelab's existing tool services.
Hermes calls it and answers from the result, instead of guessing.

**Why this priority**: A local model without tools is a toy; with the estate's own data behind it,
it answers questions nothing else can. Independently testable and valuable on its own.

**Independent Test**: Ask a question answerable only through a homelab tool service, and confirm the
tool was used and the answer reflects its output.

**Acceptance Scenarios**:

1. **Given** the configured tool services, **When** the owner asks something requiring one, **Then**
   Hermes calls it and the answer is derived from what it returned.
2. **Given** a tool service that requires a credential, **When** Hermes calls it, **Then** it
   presents the credential and is not refused. *(**Not verifiable at launch**, recorded 2026-09-20:
   the estate's only credentialed tool service gates on a secret baked into a third-party image
   that this repository does not hold, and making it configurable requires an upstream change. The
   credential path is still built and validated in configuration — only its demonstration is
   deferred. Re-arm when that image makes its secret configurable; adding the server is then one
   configuration entry, which is itself the test of FR-013. See `research.md` R-008.)*
3. **Given** a tool service that is unavailable, **When** a call is attempted, **Then** the
   conversation shows a readable error naming the service — never an indefinite wait, never a
   fabricated answer presented as tool output.
4. **Given** a new tool service is added to the homelab, **When** the owner wants Hermes to use it,
   **Then** it is a configuration entry requiring no code change.

---

### User Story 4 - The owner can get into the box, and nothing is lost on a rebuild (Priority: P1)

The owner administers Hermes over SSH. When the machine is destroyed and rebuilt from code,
conversations, settings and accumulated knowledge come back.

**Why this priority**: Everything else in the estate works this way, and state that only exists on a
running machine is state that will eventually be lost. Independently testable by a rebuild drill.

**Independent Test**: Sign in over SSH with a key; destroy the machine; rebuild it from code; run the
restore; confirm prior conversations, settings and knowledge are present.

**Acceptance Scenarios**:

1. **Given** the owner's key, **When** they connect over SSH from the home network, **Then** they
   get a shell. Password authentication is refused, and there is no route in from the public
   internet.
2. **Given** accumulated state, **When** the machine is rebuilt from code and the restore procedure
   is run, **Then** prior conversations, accounts, settings and knowledge are all present.
3. **Given** the scheduled backup, **When** it runs, **Then** a restorable copy reaches the estate's
   backup storage, and the age of the most recent copy is monitored.
4. **Given** a backup that has stopped running, **When** its age exceeds the expected interval,
   **Then** an alert is raised.

---

### User Story 5 - Hermes degrades honestly when the models are unavailable (Priority: P2)

The machine hosting the models is a personal computer that sleeps and gets logged out. When it is
away, Hermes says so plainly instead of hanging.

**Why this priority**: The models being absent is the normal case, not an exception, so the
behaviour is a feature rather than error handling. P2 only because US-1 must exist first to observe
it.

**Independent Test**: Make the inference host unavailable, use Hermes, and time the failure.

**Acceptance Scenarios**:

1. **Given** the inference host is unavailable, **When** the owner sends a prompt, **Then** a
   readable error naming the unavailable backend appears within seconds — never an indefinite wait.
2. **Given** the inference host is unavailable, **When** the owner opens Hermes, **Then** the
   interface still loads and previous conversations remain readable.
3. **Given** the inference host returns, **When** the next prompt is sent, **Then** it is answered
   with no administrative action.
4. **Given** a scheduled run fires while the inference host is unavailable, **Then** it fails
   visibly and the owner can see that it did not run — it does not silently produce nothing.

---

### User Story 6 - The owner asks questions of their own documents (Priority: P3)

The owner uploads documents and asks questions answered from their contents, with the source shown.

**Why this priority**: Genuinely useful, but the feature is worth deploying without it, and it is the
part that depends most on the inference host being awake.

**Independent Test**: Upload a document, ask something answerable only from it, confirm the answer
cites it.

**Acceptance Scenarios**:

1. **Given** an uploaded document, **When** the owner asks about its contents, **Then** the answer
   identifies the passage it came from.
2. **Given** retrieval is in use, **When** it runs, **Then** every step of it is performed on the
   owner's own hardware and no document content is sent to a third party.
3. **Given** the inference host is unavailable, **When** the owner asks a document question,
   **Then** it fails readably rather than silently answering without the document.

---

### Edge Cases

- **Hermes generates more requests than the owner expects.** Assistant interfaces commonly issue
  extra background requests per conversation — naming a chat, tagging it, rewriting a search query.
  Against a single inference host with a fixed request allowance, ordinary use can exceed the
  allowance through overhead alone rather than through the owner's actual prompts.
- **A single answer takes many minutes.** Large inputs on local hardware can take a quarter of an
  hour before the first word appears. Anything in the path that gives up earlier will cut a request
  the model would have completed.
- **The inference host sleeps mid-answer**, leaving a half-delivered response.
- **A scheduled run fails while nobody is watching**, and the failure is only noticed when someone
  wonders why there was no output.
- **Indexing a large document set** competes with interactive conversation for the same limited
  inference capacity.
- **The sign-in page is the only thing between the public internet and the homelab's tools and
  models.** A weakness in it reaches further than a weakness in a media server would.
- **A tool service returns far more data than fits in a conversation**, or returns something
  malformed.

## Requirements *(mandatory)*

### Functional Requirements

#### Access and identity

- **FR-001**: The system MUST be reachable from the public internet at a stable address, over an
  encrypted connection, without the owner needing a VPN or terminal.
- **FR-002**: The system MUST authenticate every request itself and MUST NOT rely on the network
  path or on any other component for access control.
- **FR-003**: Self-registration MUST be disabled. Accounts MUST be created deliberately by an
  administrator.
- **FR-004**: No conversation, model list, tool, uploaded document, or programmatic interface may be
  reachable without authentication.
- **FR-005**: The system MUST present a usable interface on both phone-sized and desktop-sized
  screens, and MUST be installable from a phone so it launches as a standalone application.
- **FR-006**: An administrator MUST be able to reach the underlying machine over SSH using key
  authentication from the home network only. Password authentication MUST be refused and no public
  route to SSH may exist.

#### Models

- **FR-007**: The system MUST obtain all model responses through the existing homelab gateway, by
  requesting capability names rather than naming specific models, and MUST NOT hold any model
  provider credential of its own.
- **FR-008**: No prompt, document or conversation content may be sent outside the owner's estate.
- **FR-009**: When no model can serve a request, the system MUST return a readable error identifying
  what is unavailable, within seconds, and MUST NOT wait indefinitely.
- **FR-010**: The interface and previously stored conversations MUST remain available while models
  are not.
- **FR-011**: The system MUST bound the rate at which it issues requests to the gateway, and its
  background or housekeeping requests MUST be configured deliberately rather than left at defaults.

#### Tools

- **FR-012**: The system MUST be able to call the homelab's existing tool services, including those
  that require a credential, and MUST take those credentials from the estate's secret store rather
  than from source control.
- **FR-013**: Adding, removing or repointing a tool service MUST be a configuration change requiring
  no modification to software.
- **FR-014**: A failing or unavailable tool service MUST surface as a readable error naming the
  service, and MUST NOT be presented to the owner as a successful result.

#### Knowledge

- **FR-015**: The system MUST support asking questions of documents the owner supplies, with answers
  identifying the source passage.
- **FR-016**: Every stage of document retrieval MUST run on hardware the owner controls.

#### Presence and operations

- **FR-017**: The system MUST appear on the homelab's front page as an entry that links to the
  system itself, carrying a liveness indicator produced by the estate's existing mechanism.
- **FR-018**: The system MUST publish a monitoring contract consistent with the estate's other
  services, including an alert when it is unreachable and an alert when its backups stop.
- **FR-019**: Stored state MUST be held on storage local to the machine, arranged so the estate's
  backup mechanism can reach it, and MUST NOT be held on network-attached storage.
- **FR-020**: The complete state MUST be restorable onto a machine rebuilt from code.
- **FR-021**: Responses taking up to twenty minutes MUST complete without being terminated by any
  intermediary in the request path.

#### Additional capabilities

- **FR-022**: The owner MUST be able to have the system search the web and cite what it found,
  without queries being sent to a commercial search provider.
- **FR-023**: The owner MUST be able to speak to the system and have replies read aloud, with speech
  recognition performed on hardware the owner controls.
- **FR-024**: The system MUST expose a programmatic interface so other homelab services and scripts
  can use it with its configured models, tools and knowledge attached. This interface is subject to
  FR-002 and FR-004.
- **FR-025**: The owner MUST be able to schedule prompts to run on a recurring basis, with the same
  tools and knowledge available as in an interactive conversation, and with failures visible.

#### Delivery constraint

- **FR-026**: The feature MUST be satisfiable by deploying and configuring existing, unmodified
  software. Delivering it MUST NOT require writing bespoke application code.

### Key Entities

- **Workspace state**: The owner's conversations, account, settings, saved prompts and uploaded
  knowledge. The unit that must survive a rebuild and the thing the backup protects.
- **Knowledge index**: A derived, searchable representation of the owner's uploaded documents.
  Rebuildable from the source documents, but expensive enough to rebuild that it is backed up.
- **Tool service registration**: A named, addressable homelab service the system may call, together
  with whatever credential it requires. Configuration, never code.
- **Capability name**: The indirection the system uses to ask for a model — owned by the gateway,
  not by this feature. This feature names capabilities and never models.
- **Scheduled run**: A saved prompt, the capability it should use, and a recurrence. Part of
  workspace state, owned by the account that created it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: From tapping the front-page entry on a phone away from home, the owner is signed in
  and receiving an answer in under 60 seconds.
- **SC-002**: Every one of the system's surfaces — conversation, model list, uploaded documents, and
  the programmatic interface — refuses an unauthenticated request. Verified surface by surface.
- **SC-003**: A question that can only be answered using a homelab tool service is answered
  correctly, and the owner can see which service was used.
- **SC-004**: Adding a tool service, or changing which model capability is used, is achieved by
  editing configuration alone, with no change to any software.
- **SC-005**: With the inference host switched off, every prompt returns a readable error in under
  10 seconds, the interface remains usable, and previous conversations remain readable.
- **SC-006**: The machine is destroyed, rebuilt from code and restored; 100% of prior conversations,
  accounts, settings and knowledge are present afterwards.
- **SC-007**: A question about an uploaded document is answered with the source passage identified,
  and no document content leaves the estate at any stage.
- **SC-008**: Across one hour of representative interactive use, the system stays within its
  allocated request budget — measured from gateway metrics, not estimated.
- **SC-009**: A response that takes 15 minutes to produce is delivered complete.
- **SC-010**: A scheduled run that cannot complete is visibly recorded as failed; the owner can
  distinguish "ran and failed" from "never ran".
- **SC-011**: The delivered change contains no bespoke application source code.
- **SC-012**: The owner completes a spoken question and hears the answer, on a phone, without any
  audio leaving the estate.
- **SC-013**: A question requiring information the models could not already know is answered with
  citations to sources fetched at the time of asking, and no query reaches a commercial search
  provider.
- **SC-014**: Another homelab service obtains an answer from the system programmatically, with the
  system's configured tools and knowledge applied — demonstrably more than the bare gateway would
  have returned for the same prompt.
- **SC-015**: A scheduled prompt runs unattended at its appointed time and its output is waiting for
  the owner afterwards.

## Assumptions

- **The account owner is the only user.** Multi-user, team access and directory integration are not
  designed for, though they must not be actively prevented.
- **The inference host is intermittent by design.** It is a personal computer that sleeps and logs
  out; its absence is the normal case and is handled as behaviour (FR-009, FR-010) rather than as an
  incident.
- **The existing gateway remains the only path to models**, and will be extended by this feature to
  also serve the retrieval capabilities FR-015 and FR-016 require. That extension is part of this
  feature's scope.
- **The estate's reverse proxy provides no authentication of its own.** This is why FR-002 places
  the entire access-control burden on this system. It is a known weakness and is recorded as the
  principal risk.
- **The estate's existing patterns apply**: an unprivileged container-hosting machine, a dedicated
  backup job, and a monitoring contract, all following services already deployed.
- **Selected implementation**: an established open-source AI workspace application, chosen because
  it satisfies FR-026 — every requirement above is met by configuring it rather than extending it.
  The specific product is recorded in the accompanying research note rather than in this
  specification, so that the requirements remain the contract.

## Dependencies

- **The homelab model gateway** (feature `064`, closed). Supplies the capability names, the client
  credential and the request budget. **This feature amends it**: retrieval capabilities must be
  added, and this system's credential must be permitted to use them.
- **The inference host**. Must additionally serve the retrieval capabilities; this is new work
  outside the machine this feature builds.
- **The estate's reverse proxy**. Must route the public address and must not terminate long
  responses (FR-021).
- **The estate's monitoring and backup mechanisms**. Reused, not rebuilt.

## Out of Scope

- Any third-party model subscription, and any workflow that depends on one.
- Modelling a commercial provider's usage allowances.
- An estate-wide authentication layer. It would be the correct answer to the principal risk, but it
  is a separate feature affecting every public service, not part of this one.
- Multi-user access, single sign-on and directory integration.
- Image generation.
- Making the inference host permanently available. The honest-degradation behaviour is the answer.
