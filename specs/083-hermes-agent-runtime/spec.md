# Feature Specification: Hermes Agent behind Hermes — a stock agent runtime and scheduler

**Feature Branch**: `083-hermes-agent-runtime`

**Created**: 2026-10-17

**Status**: Implemented. Live on PROD since 2026-10-17/18; every user story verified (quickstart "Results so far"). The two-week review Q-P10 (T050) was skipped by owner decision. Q-P6: the line is behind ISP Carrier-Grade NAT, so no inbound port forward is possible. Accepted deviations: research R-004 (flagged commands from chat are held as pending, not BLOCKED) and R-004 key-scope finding

**Input**: User description: "083-hermes-agent-runtime.md" — the backlog entry
[`docs/backlog/083-hermes-agent-runtime.md`](../../docs/backlog/083-hermes-agent-runtime.md): add the
upstream Hermes Agent runtime to the existing Hermes AI workspace (`065`) as a second backend behind the
existing chat surface, so that chats can use a full agent with a terminal, tools and memory, and so that
**any scheduled job is one script plus one scheduling command**, delivered to the owner's phone through
the self-hosted push channel (`082`), instead of a new deployment role and timer per job. Delivered as
configuration of unmodified upstream software. Amends `065`.

## Background

"Hermes" today (`065`) is a good chat surface but not an agent: it has no terminal, and its scheduled
prompts are model-only and land as chats the owner has to go and look at.

The first concrete need was a daily **model scout** (public repo `lightenup/local-llm`) that tells the
owner when a new local model worth benchmarking appears. Done the estate's current way, it needs its own
role, timer, secrets, delivery code and monitoring contract — and so would every similar job after it.
That per-job cost is the problem this feature removes.

The agent runtime brings, upstream and documented: **script-only scheduled jobs** that make no model call
(non-empty output is delivered, empty output is a silent tick, a failure alerts), **agent scheduled jobs**
that run a prompt with the agent's tools, **delivery targets** including the self-hosted push channel, an
**interface the chat surface can connect to as a model**, and **tool access** (the estate's tool
services, the existing private web search, terminal, files, persistent memory).

No agent runtime was evaluated when `065` was specified (its research compared chat surfaces only). This
feature keeps the chat surface and adds the runtime behind it.

### Decisions already taken (2026-10-16, owner)

| Decision | Choice | Consequence |
|---|---|---|
| Where it runs | Same Hermes machine, alongside the chat surface and web search | One machine, one backup, one monitoring contract. Machine sizing must be re-measured. |
| Chat path | Both connections in the chat surface | Gateway-direct stays the default for plain chat and retrieval; the agent appears as a separate model (`hermes-agent`) for tool work. |
| Terminal | Full terminal, confined to the agent's own container | Accepted risk, see below. |
| Front-door auth | Not a prerequisite | Every `hus-sky.no` name is reachable only on the LAN or over the tailnet. |
| Push channel | `082`, notify-only | The agent delivers; it never listens on a topic. |
| Chat-surface scheduled prompts | Retired | One scheduler. Owner reports none in use; still checked before disabling. |
| Default model | `hermes-balanced` for agent chats and agent jobs | A job may override per job. Script-only jobs use no model. |
| Tool services | In both the chat surface and the agent | Plain chat keeps its tools; both lists come from one source. |
| Agent memory | On, and in the backup | Losing it on rebuild would be a regression. |
| Approvals | Fail closed | A flagged command with nobody to approve it is refused at once. |

### Decisions taken at specification (2026-10-17, owner)

| Decision | Choice | Consequence |
|---|---|---|
| Lab vs production | **Production is the only operational instance.** The lab instance is a deploy gate: no operational jobs, no push credential, delivery local only | The owner never gets duplicate or lab messages. The path *Hermes machine → reverse proxy → push channel* is proven on production, not by the lab gate. |
| Proof of no internet exposure | **Automated public-DNS check on every deploy + a one-time recorded manual router check** | The precondition of the accepted risk is re-asserted on every deploy at low cost. |
| Agent network reach | **Allowlist** — internet plus the estate services the agent needs; all other private and tailnet destinations blocked | Limits what a prompt-injected agent can reach (hypervisor, NAS, router, other services). |

### Accepted risk: a full terminal behind the chat surface's own login

Whoever holds the chat surface's admin session can make the agent run shell commands on the Hermes
machine. With a terminal, the impact of the missing front-door auth (`065` D-002) grows from "read my
chats" to "shell on an estate host holding a gateway key and tool-service credentials".

Accepted because exposure is LAN + tailnet only (asserted, FR-017). Bounded by: the agent's interface and
dashboard never published (FR-004, FR-005); the terminal confined to the agent's container with no
container-runtime control and no host access beyond its own data (FR-007); outbound reach limited to an
allowlist (FR-008), which by the owner's choice includes the reverse proxy and therefore, at network
level, every site it serves, each behind its own login; the agent's own gateway identity and allowance (FR-009); no inbound push topic
(FR-012). **Revisit if any `hus-sky.no` name ever becomes internet-reachable** — front-door auth then
becomes a prerequisite.

### Correction to `065`

`065` US-1 describes Hermes as reachable "from a phone browser on mobile data … no VPN step". The deployed
estate does not do that: every `hus-sky.no` name resolves to the reverse proxy's LAN address and is
reachable off-LAN only through the tailnet. "Public" on the front page means *routed by the reverse
proxy*, not internet-facing. This feature's risk acceptance rests on that, so `065`'s wording is corrected
as part of this feature (FR-022).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A new scheduled job is a script and one command (Priority: P1)

The owner (or the agent, asked in chat) drops a script into the agent's scripts location and schedules
it. Its output reaches the phone; silence means nothing to report.

**Why this priority**: This is the reason the feature exists — removing the per-job deployment cost. The
model scout is waiting on it.

**Independent Test**: On production, install the model scout as a script-only job delivering to the
`hermes` topic; run it once on demand; the phone shows the report. Run again with no new models: no
message.

**Acceptance Scenarios**:

1. **Given** a script in the agent's scripts location, **When** the owner schedules it with one command,
   **Then** it runs on schedule with no deployment-code change, no new timer and no new secret.
2. **Given** a run whose script prints nothing, **When** it completes, **Then** nothing is sent.
3. **Given** a run whose script fails, **When** it completes, **Then** a failure message naming the job
   reaches the phone.
4. **Given** the inference host is asleep, **When** a script-only job fires, **Then** it runs and
   delivers normally.

---

### User Story 2 - Chat with an agent that can act, without changing plain chat (Priority: P1)

**Why this priority**: The second half of the value: tool work from the existing chat surface, with the
everyday chat path left exactly as it is.

**Independent Test**: In the chat surface, pick `hermes-agent` and ask it to check disk usage on its host
and look something up on the web; it uses the terminal and the private web search. Pick
`hermes-balanced` for a normal question; it answers exactly as before, retrieval unchanged.

**Acceptance Scenarios**:

1. **Given** the agent connection, **When** the owner selects `hermes-agent`, **Then** requests run
   through the agent with terminal, file, web-search and tool-service tools available.
2. **Given** the gateway connection, **When** the owner selects a gateway capability name, **Then**
   behaviour, tools and retrieval are unchanged from `065`.
3. **Given** the inference host is away, **When** the owner chats with `hermes-agent`, **Then** a
   readable error appears within seconds, as for the gateway, rather than an indefinite wait.
4. **Given** a chat that leads the agent to a command the approval policy flags, **When** it is
   attempted, **Then** it is refused at once with a readable message — not after a timeout.
5. **Given** a chat that leads the agent to contact an estate destination outside its allowlist (e.g.
   the hypervisor or the NAS), **When** it is attempted, **Then** the connection fails.

---

### User Story 3 - Scheduled prompts run in one place, with failures visible (Priority: P2)

**Why this priority**: Consolidates scheduling into one place; valuable, but nothing depends on it today.

**Independent Test**: Create an agent job (e.g. a weekly summary using web search) delivering to the
phone; run it; it arrives. Make it fail (unknown model name); the failure reaches the phone. The chat
surface's own scheduled prompts are disabled and no longer offered.

**Acceptance Scenarios**:

1. **Given** an agent job, **When** it runs successfully, **Then** its output reaches the phone.
2. **Given** an agent job that fails, **When** it runs, **Then** a failure message naming it reaches the
   phone.
3. **Given** the chat surface, **When** the owner looks for its scheduled-prompt feature, **Then** it is
   not available.

---

### User Story 4 - The scheduler itself is watched (Priority: P2)

**Why this priority**: A scheduler that stops silently looks identical to "nothing to report" — the one
failure the owner cannot notice unaided.

**Independent Test**: Stop the agent on production; within the alert window an alert reaches the phone
through the estate's alerting. The owner can tell "scheduler down" from "job ran and found nothing".

**Acceptance Scenarios**:

1. **Given** the scheduler is running, **When** jobs find nothing, **Then** no alert fires.
2. **Given** the scheduler has stopped (or its container is down), **When** the staleness window passes,
   **Then** an alert names the Hermes agent scheduler as stale.

---

### User Story 5 - The agent survives a rebuild (Priority: P2)

**Why this priority**: Jobs, scripts, memory and job state are now owner content; losing them on rebuild
would silently undo work and make the scout re-report old models.

**Independent Test**: Run the Hermes restore drill; afterwards the job list shows the same jobs, the
scripts and memory are present, and the model scout's next run does not re-report models it had already
reported.

**Acceptance Scenarios**:

1. **Given** a restore from backup, **When** the drill completes, **Then** the job list, scripts, memory
   and job state match the backup, and one job runs successfully.
2. **Given** a restore, **When** the agent starts, **Then** its secrets are re-rendered from the vault,
   not taken from the backup.

### Edge Cases

- **Gateway allowance exhausted by an agent loop** → the agent's own identity hits its own rate limit;
  the chat surface's plain chat (separate identity) is unaffected.
- **A job script needs a secret** → the secret is added to the vault and rendered into the agent's
  environment (the one case where a new job needs a deploy change). Job scripts do not inherit model
  provider credentials by default (upstream behaviour, kept).
- **A job's output exceeds the push channel's message limit** → the agent truncates it (upstream, at
  4096 characters) and delivers the rest; it is never silently dropped.
- **The push channel is down when a job delivers** → the job's failure handling makes it visible; the
  scheduler heartbeat (FR-016) is unaffected because it does not depend on the push channel.
- **Upstream releases are frequent** → pinned, upgraded deliberately, like the chat surface.
- **The agent edits its own configuration or jobs via the terminal** → expected with a full terminal; the
  backup is the recovery path, and jobs created this way appear in the job list.
- **A job is created on the lab instance** → it can only deliver locally; it never reaches the phone.
- **A job needs an estate service not on the allowlist** → the allowlist is extended through deployment
  configuration; the agent cannot extend it itself.

## Requirements *(mandatory)*

### Functional Requirements

**Runtime**

- **FR-001**: The agent runtime MUST run on the existing Hermes machine as an additional service
  alongside the chat surface and web search, from the unmodified upstream image, pinned to a specific
  release next to the chat surface's pin, with a recorded upgrade procedure.
- **FR-002**: Its data (jobs, scripts, memory, sessions, skills, configuration, workspace, job state)
  MUST live on the machine's local disk, not on network storage.
- **FR-003**: All model calls MUST go through the `064` gateway by capability name only. Default model
  `hermes-balanced`; an agent job MAY override the model per job.
- **FR-004**: The agent's chat interface MUST require a vault-sourced key and MUST be reachable only by
  the other services on the Hermes machine — never on the LAN and never through the reverse proxy.
- **FR-005**: The agent's dashboard MUST NOT be run, or, if run, MUST be reachable only from inside the
  agent's own container.

**Chat surface**

- **FR-006**: The chat surface MUST gain a second model connection to the agent, alongside the gateway
  connection, so that the agent appears as model `hermes-agent`. The gateway connection stays the
  default; retrieval is unchanged. The connection is reconciled on every deploy like the chat surface's
  other persisted settings.

**Terminal, network and tools**

- **FR-007**: Terminal commands MUST run inside the agent's own container: no control of the container
  runtime, no elevated privileges, no host access beyond its own data (FR-002). Commands the upstream
  approval policy flags MUST always need a human, and MUST be refused immediately wherever no human can
  answer — every request arriving from the chat surface and every scheduled agent job. An unanswered
  interactive approval MUST be denied after a bounded wait. Unflagged commands run (accepted risk).
- **FR-008**: The agent's outbound network reach MUST be limited to the internet plus an explicit
  allowlist of estate destinations it needs (the model gateway, the estate tool services it is
  configured with, the push channel via the reverse proxy, and web search on the same machine). All
  other private-network and tailnet destinations (including the hypervisor, the NAS and the router) MUST
  be unreachable from the agent's container. The allowlist is deployment configuration; the agent MUST
  NOT be able to change it from its terminal. The chat surface's own reach is unchanged.
- **FR-009**: The agent MUST have its own gateway client identity with its own rate limit and budget
  (proposal: 20 requests/minute, $5 per 30 days), checked against `064`'s sizing rule
  `max(client) ≤ gateway < sum(clients)`. Limits are reviewed against measured use, never raised first.
- **FR-010**: Every secret the agent uses (gateway key, chat-interface key, push token, tool-service
  tokens) MUST come from the vault at deploy, be asserted present before deploy without being logged,
  and never be committed. Secrets MUST be excluded from the backup and re-rendered on restore.
- **FR-011**: The agent MUST be configured with the estate's tool services and with the existing
  private web search on the Hermes machine. No paid content-extraction provider (`065` FR-008). The chat
  surface keeps its own tool-service registrations; both MUST be rendered from one list so they cannot
  drift.

**Delivery**

- **FR-012**: On production, the agent MUST deliver to the `082` push channel's `hermes` topic using
  `082`'s write-only Hermes credential, with markdown rendering on. It MUST NOT be possible to send
  the agent commands through the push channel: a topic that can talk to the agent would be a shell
  credential. Upstream's push adapter always attempts a subscription (research R-006), so this is held
  by two independent controls. First, the push channel refuses the subscription, because the credential
  is write-only. Second, the agent's inbound allowlist is empty, so it acts on nothing it receives. A
  refused subscription MUST NOT prevent delivery.
- **FR-013**: Every scheduled job MUST have a delivery target and a failure delivery that reaches the
  phone. A job that fails silently is a defect.
- **FR-014**: The lab instance MUST NOT hold the push credential and MUST NOT run operational jobs (the
  model scout, the heartbeat or any owner job). Jobs created on the lab instance for verification MUST
  deliver locally only.

**Scheduling**

- **FR-015**: The chat surface's own scheduled-prompt feature MUST be retired: existing scheduled
  prompts are listed first (expected: none), then the feature is disabled and its settings removed, with
  the persisted value reconciled so it stays off. `065` FR-025 is then satisfied by the agent's
  scheduler.

**Monitoring**

- **FR-016**: On production, a script-only **heartbeat** job (every 15 minutes) MUST record a timestamp
  the estate's metrics collection reads, with an alert when it is older than 1 hour, declared in the
  Hermes machine's monitoring contract. This proves the scheduler runs, independently of any job's
  outcome and of the push channel; an agent that is down trips the same alert.

**Exposure precondition**

- **FR-017**: Every deploy MUST fail if any `hus-sky.no` name resolves, in public DNS, to an address
  outside private or tailnet ranges. In addition, a one-time manual check that the router forwards no
  port to the reverse proxy MUST be performed and its result recorded with this feature's verification.

**Persistence**

- **FR-018**: Persistent agent memory MUST be enabled. The agent's data (FR-002, secrets excluded) MUST
  be included in the Hermes backup, and the Hermes restore drill MUST verify the job list and one job run
  after restore.

**First job**

- **FR-019**: The `local-llm` model scout MUST be the acceptance job, installed and scheduled on
  production **as job content, not through deployment code** (daily at 07:30, delivering to `hermes`,
  failures delivered too). Its script, state handling and runbook already exist in the public
  `local-llm` repo. The agent's environment MUST provide what the script needs (version control client
  and a recent Python), verified on the lab instance.

**Configuration only**

- **FR-020**: No platform (chat surface, agent runtime, web search) is patched or built. Job scripts are
  content, like prompts — not application code.
- **FR-021**: The agent service MUST be deployable through both the pipeline and a developer laptop,
  with no new deploy target (it is part of the existing Hermes service).
- **FR-022**: `065`'s specification MUST be amended in the same change: FR-025 (scheduled prompts now
  delivered by the agent scheduler to the phone, failures delivered), FR-026 (job scripts are content),
  US-1 wording (LAN + tailnet, not public), and its research (the agent-runtime question it did not ask,
  and this answer).

### Key Entities

- **Job**: a scheduled entry in the agent — schedule, script-only or prompt, script, delivery target,
  failure delivery, optional model override. Lives in the agent's data; owner content.
- **Script**: an executable in the agent's scripts location; job content, not application code.
- **Agent client**: the agent's own gateway identity, with its rate limit and budget.
- **Heartbeat**: the timestamp the scheduler's heartbeat job writes, and the alert that watches it.
- **Egress allowlist**: the estate destinations the agent may reach; deployment configuration.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Adding a second scheduled job after the model scout requires **zero** changes to
  deployment code, machine definitions or the vault (unless the job needs a new secret).
- **SC-002**: The model scout delivers to the phone with the inference host asleep.
- **SC-003**: A deliberately failing job produces a phone notification naming it within one scheduled
  interval.
- **SC-004**: Stopping the agent on production raises the scheduler-stale alert within 1 hour plus the
  alert's hold time.
- **SC-005**: Plain chat on a gateway capability shows no change in latency or behaviour versus `065`
  (same prompts, same retrieval results).
- **SC-006**: The agent's gateway use never pushes the chat surface's own client into rate-limit
  refusals over the first two weeks.
- **SC-007**: The restore drill passes with jobs, scripts, memory and scout state intact.
- **SC-008**: A flagged command requested from the chat surface is refused in under 5 seconds, every
  time.
- **SC-009**: From the agent's terminal, 100% of attempts to reach non-allowlisted estate destinations
  (hypervisor, NAS, router) fail, while every allowlisted service is reachable.
- **SC-010**: Over the first two weeks, the owner receives zero messages originating from the lab
  instance and zero duplicate scout reports.
- **SC-011**: The machine runs the chat surface, web search and agent through a real agent turn without
  memory pressure (measured, and resized if needed).

## Assumptions

- The Hermes machine (provisional 4 cores / 6 GB / 32 GB) can host a third service; this is measured,
  not assumed, and the machine is resized if needed (`065` T082).
- The agent's custom-provider support drives tool calls correctly through the gateway's capability
  names, as upstream documents for this gateway. Verified on the lab instance per capability.
- The lab environment is a persistent staging copy of the estate; the lab Hermes stays up between
  deploys, which is why FR-014 keeps it non-operational rather than relying on it being short-lived.
- Tailnet access controls already restrict who on the tailnet can reach the reverse proxy.
- The owner is the only user of the chat surface (`065`).
- The 15-minute heartbeat with a 1-hour staleness window is enough; a missed tick or two is not an
  incident.
- Facts taken from upstream documentation and still to be observed in this estate (verified on the lab
  instance): immediate refusal of flagged commands from the chat surface; the image provides a version
  control client and Python ≥ 3.11 to scripts; out-of-process delivery to the self-hosted push channel
  with no inbound subscription; the chat surface lists the agent as `hermes-agent`.

## Dependencies

- **`082`** (done, live since 2026-10-17) — the push channel, its publisher contract
  ([`specs/082-ntfy-push-service/contracts/publisher-interface.md`](../082-ntfy-push-service/contracts/publisher-interface.md)),
  the write-only Hermes credential and the phone's existing `hermes` subscription. 082 never published
  *from the Hermes machine*; this feature proves that path on production (FR-012, US-1).
- **`064`** — a new gateway client (FR-009).
- **`065`** — the Hermes machine, chat surface, web search, backup and restore drill; amended (FR-022).
- **`local-llm`** (public repo, done) — the model scout script and runbook.

## Out of Scope

- Front-door auth (`065` D-002) — not required while LAN/tailnet-only; becomes a prerequisite if that
  changes.
- Inbound messaging to the agent (push channel, chat apps).
- Removing tool services from the chat surface.
- Paid web-extraction providers.
- Moving the agent to its own machine (revisit if sizing says so).
- Restricting the chat surface's or web search's network reach (FR-008 applies to the agent only).
- Running operational jobs on the lab instance, or a separate lab push topic.
