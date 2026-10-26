# Feature Specification: Two-way ntfy — talk to Hermes and act on notifications from the phone

**Feature Branch**: `095-ntfy-two-way`
**Created**: 2026-10-25
**Status**: Slice 1 (chat, approvals, gap notice) shipped and verified on PROD 2026-10-26 (merged
`main` via #287): ntfy, hermes and monitoring deployed; ACL check, phone chat, approval scopes
(once/session/always), the gap notice and the SC-006 revocation drill all pass
([`specs/095-ntfy-two-way/`](../../specs/095-ntfy-two-way/)). Outstanding before the slice is fully
closed: push the rotated `pve_backup` ntfy token to the bare-metal host
(`ansible/playbooks/backup_proxmox.yml`, outside the LXC service pipeline) and the SC-004 7-day
silence check (T061, due ~2026-11-02), which closes `093` for good. Slice 2 (action buttons) not
started.
Amends [`082`](./082-ntfy-push-service.md) (Direction: publish-only) and
[`083`](./083-hermes-agent-runtime.md) (FR-011: delivery only). Supersedes
[`093`](./093-hermes-agent-ntfy-403.md) (the 403 noise disappears once the agent subscribes to a
topic it may read).
**Input**: Make ntfy a two-way channel. First consumer: the Hermes Agent, so the owner can chat
with it from the phone, answer its approval prompts and reply to its scheduled-job output. Second
consumer: action buttons on estate notifications (silence an alert, re-run a backup, snooze a
version) that are executed by a small deterministic relay, not by the agent.

---

## Why this exists

ntfy (`082`) reaches the phone and Hermes (`083`) runs jobs that report there — but every message
is a dead end. To act on one, the owner opens a laptop: Open WebUI to ask Hermes a follow-up,
Alertmanager to silence a flapping alert, a terminal to re-run a backup.

Two concrete gaps:

1. **The agent can never get an approval.** `agent-config.yaml.j2` sets `approvals: mode: manual`
   with `cron_mode`, `single_query_mode` and `unattended_mode` all `deny`. Every Open WebUI request
   goes through the API server, which is non-interactive, so **every flagged terminal command is
   refused**, even with the owner present. ntfy would be the first interactive surface where a
   prompt can be shown and answered.
2. **Job output can't be answered.** `model-scout` says "new model X"; the natural next step,
   "benchmark it", needs a new session somewhere else, with the context retyped.

What exists today, measured 2026-10-25:

- The agent's ntfy adapter already subscribes to `NTFY_TOPIC` and is refused (`403`, ~19/hour)
  because the `hermes` token is write-only. `083`'s `agent.env.j2` documents that refusal as
  control #1 and the unset `NTFY_ALLOWED_USERS` as control #2. Both are deliberate.
- The adapter can subscribe to one topic and publish to another (`NTFY_TOPIC` /
  `NTFY_PUBLISH_TOPIC`). The gateway's text approval fallback (`/approve`, `/deny`) works on any
  platform without native buttons, and that includes ntfy on the stock image.
- **ntfy never tells a subscriber who published a message.** `model/model.go` marks
  `Sender`/`User` `json:"-"`. The adapter therefore pins `user_id` to the *topic name*. **Write
  access to the inbound topic is the only identity check.**
- **The agent can read its own secrets.** `/opt/data/.env` (`600`, uid `hermes`) holds every token,
  and the agent's terminal runs as that uid. So no credential that can approve or command may ever
  be given to the agent.

## Decisions recorded (2026-10-25)

| decision | choice | why |
|---|---|---|
| Scope | Hermes chat, replies to job output, approvals, **and** action buttons for alerts and other estate notifications | Owner choice. Delivered in slices: Hermes first. |
| What a phone message may make Hermes do | **Full agent, same tools as Open WebUI; approvals answered on the phone** | The point is to unblock flagged commands with a human present. Cron, API server and unattended runs stay `deny`. |
| Sender identity | **Dedicated inbound topic + dedicated phone token** | Only the phone can write the inbound topic. The agent may read it but never write it, so it cannot command or approve itself. Outbound stays on `hermes`. |
| Messages while the agent is offline | **Dropped, and the agent says so when it is back** | No stale commands replayed from the 72 h cache. The owner learns that the gap existed. |
| Approval UX | **Action buttons, with typed `/approve` as fallback** | Typed works on the stock image now. Buttons are a later slice and only if the agent cannot forge a press (see FR-012). |
| Where action buttons go | **An ntfy actions topic, consumed by a small deterministic relay** with a fixed allowlist | Nothing new exposed beyond ntfy, no LLM in the loop for estate actions, one auth model. Rejected: routing through Hermes (non-deterministic, widens agent egress). Rejected: direct service APIs (per-service exposure, a credential in every notification). |
| First deliverable | **Hermes chat + approvals + offline notice** | Highest value and nothing new to build: configuration of the stock image plus ACL changes. |
| Detail | Full spec + plan in `specs/095-ntfy-two-way/` | Technology choices live in `plan.md`/`research.md`, not here. |

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Chat with Hermes from the phone (Priority: P1)

**Independent Test**: On mobile data with Tailscale, type "what's the disk usage of your data dir?"
into the ntfy app on the inbound topic. A reply arrives on the `hermes` topic within the model's
normal latency. A message published with any other credential, or none, is refused by ntfy and
never reaches the agent.

**Acceptance Scenarios**:
1. **Given** the phone's inbound token, **When** the owner publishes text to the inbound topic,
   **Then** the agent treats it as one turn of an ongoing conversation and replies on `hermes`.
2. **Given** any other estate token (including the agent's own), **When** it publishes to the
   inbound topic, **Then** ntfy refuses it.
3. **Given** a follow-up message, **When** it arrives, **Then** the agent keeps the conversation's
   context. A reset command starts a fresh session.
4. **Given** a reply longer than the per-message limit, **When** the agent sends it, **Then** the
   owner can tell it was truncated or split.

### User Story 2 - Answer an approval prompt on the phone (Priority: P1)

**Independent Test**: Ask Hermes (from the phone) to do something that triggers an approval, such
as deleting a file in its data dir. A prompt arrives on the phone. Reply `/approve`: it runs.
Repeat with `/deny`, and repeat with no answer: it does not run, and the timeout is stated in the
prompt.

**Acceptance Scenarios**:
1. **Given** a flagged command in a phone-originated session, **When** the agent wants to run it,
   **Then** the owner receives a prompt showing the command, the reason and the deadline.
2. **Given** that prompt, **When** the owner approves from the phone, **Then** the command runs
   once. **When** the owner denies or does not answer before the deadline, **Then** it does not
   run.
3. **Given** a flagged command in a cron job, a single query or an Open WebUI request, **When** it
   is reached, **Then** it is still refused exactly as today. This feature does not loosen
   non-interactive surfaces.
4. **Given** the agent itself (a terminal command, a script, a tool), **When** it tries to send an
   approval or any message to the inbound topic, **Then** it is refused, because it holds no
   credential that can write there.

### User Story 3 - Reply to scheduled-job output (Priority: P2)

**Independent Test**: `model-scout` reports a new model on `hermes`. The owner replies "benchmark
it" on the inbound topic, and the agent acts with the report's context, without the owner pasting
the report.

**Acceptance Scenarios**:
1. **Given** a job report delivered to the phone, **When** the owner replies, **Then** the agent can
   see which report the reply refers to (the latest, or one the owner names).
2. **Given** a no-agent job (no LLM), **When** the owner replies, **Then** the reply starts an agent
   session that has the report as context. It does not re-run the script.

### User Story 4 - Know when messages were missed (Priority: P1)

**Independent Test**: Stop the agent container, publish a message on the inbound topic, then start
it. The message is not acted on, and within a minute of reconnecting the agent posts on `hermes`
that it was unreachable from T1 to T2 and that messages sent in that window were not received.

**Acceptance Scenarios**:
1. **Given** the agent was offline or its subscription dropped, **When** it reconnects, **Then** it
   does **not** process messages published during the gap.
2. **Given** a gap longer than a threshold (to be set in the plan), **When** it reconnects, **Then**
   it notifies the owner with the gap's bounds. Short reconnects (keepalive blips) stay silent.

### User Story 5 - Act on an alert from the notification (Priority: P2)

**Independent Test**: Fire a test alert. The ntfy notification carries a "Silence 1h" button.
Pressing it creates a matching silence in Alertmanager, a confirmation arrives, and the button
can't be replayed to create a second silence later.

**Acceptance Scenarios**:
1. **Given** a firing alert, **When** it reaches ntfy, **Then** it carries at most three action
   buttons drawn from an allowlist (e.g. silence 1h / 24h, open dashboard).
2. **Given** a press, **When** the relay receives it, **Then** it validates the action against the
   allowlist and the target's current state (e.g. the alert still exists), executes it, and
   confirms on the phone. Anything off the allowlist is refused and reported.
3. **Given** the same press replayed later, or a press older than its expiry, **When** the relay
   receives it, **Then** it does nothing and says why.
4. **Given** the relay is down, **When** a button is pressed, **Then** the owner learns the action
   did not happen (no silent loss), and the alert keeps reaching Pushover as before.

### User Story 6 - Act on other estate notifications (Priority: P3)

**Independent Test**: A backup-failure notification offers "Re-run". Pressing it re-runs that
backup job through the relay and the result is reported.

Candidate actions, each confirmed during planning before it is admitted: re-run a failed service
backup (`pve_backup`); snooze a version-currency finding (`versions`, `090`); re-run the mutation
gate (`mutation`, `087`). Each one is added to the allowlist explicitly; nothing generic like
"run a command".

### Edge Cases

- **Inbound token leaked**: whoever holds it can command the agent, within approvals and the
  egress allowlist. The token must be revocable in one deploy, and revocation is part of the
  runbook.
- **Prompt injection via job output or web content** asks the agent to approve itself or to post to
  the inbound topic: refused by ACL, because the agent has no write credential there (US-2/4).
- **Both an approval prompt and a chat message pending**: a reply must resolve the prompt it is
  meant for, not the wrong one.
- **Phone off the tailnet**: outbound messages wait in the 72 h cache as today. Inbound messages
  simply can't be sent.
- **ntfy down**: chat and buttons are unavailable. Alerts still reach Pushover. The ntfy liveness
  alert is unchanged (`082` FR-006).
- **LAB deploys** must stay unable to receive commands: `083` FR-014 (no push token on LAB)
  extends to the inbound token.
- **Echo**: the agent must not process its own outbound messages. With separate inbound and
  outbound topics this holds structurally.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: There MUST be a dedicated inbound topic for the agent, separate from the outbound
  `hermes` topic. The agent's credential MUST be able to read it and MUST NOT be able to write to it.
- **FR-002**: Exactly one credential, held only on the owner's phone, MUST be able to write the
  inbound topic. No estate service, publisher or the agent may hold it.
- **FR-003**: The agent MUST act only on messages from the inbound topic and MUST reject anything
  else, with the agent-side allowlist naming that topic exactly (never a wildcard and never
  allow-all).
- **FR-004**: A phone-originated session MUST have the same tools as an Open WebUI session.
  Flagged commands MUST raise an approval prompt to the phone with the command, the reason and the
  deadline. They MUST run only on an explicit approve from the phone, and MUST NOT run on deny or
  timeout.
- **FR-005**: Non-interactive surfaces (cron, single query, API server/Open WebUI, unattended)
  MUST keep failing closed exactly as `083` specifies.
- **FR-006**: Messages published while the agent is not subscribed MUST NOT be processed later.
  On reconnect after a gap above a set threshold, the agent MUST tell the owner the gap's bounds.
- **FR-007**: A reply to a scheduled-job report MUST give the agent that report as context (P2).
- **FR-008**: Action buttons MUST deliver their press to a dedicated actions topic, executed by a
  relay that is deterministic (no LLM), runs a fixed allowlist of actions with bounded parameters
  (e.g. maximum silence duration), validates against target state, refuses replays and expired
  presses, and confirms or refuses on the phone (P2).
- **FR-009**: Every inbound command, approval decision and relay action MUST be logged with
  timestamp, topic, message id and outcome, and those logs MUST reach the estate's log aggregation
  (`092`).
- **FR-010**: The inbound and actions credentials MUST be revocable and rotatable by a single
  deploy, documented in a runbook alongside the phone setup.
- **FR-011**: LAB deploys MUST render no inbound or actions credential (extends `083` FR-014).
- **FR-012**: Native approval buttons (P2) MUST NOT be implementable with any credential the
  agent can read. If no design meets that, approvals stay typed-only.
- **FR-013**: `082`'s Direction decision and `083`'s FR-011 and `agent.env.j2` control comments
  MUST be amended to describe the new model. `093` MUST be closed as superseded.

### Key Entities

- **Inbound topic** (agent): written by the phone only, read by the agent only.
- **Outbound topic** `hermes`: unchanged; the agent writes it and the phone reads it.
- **Actions topic**: button presses go here. Written by the action credential, read by the relay.
- **Phone credential(s)**: the owner's existing read token, plus write on the inbound topic. Whether
  this is one token or two is a plan decision.
- **Action relay**: a small deterministic service with an allowlist of `(action, parameters,
  validation, executor)`.
- **Approval prompt**: one pending flagged command with an id, a deadline and a session.

## Success Criteria *(mandatory)*

- **SC-001**: From the phone on mobile data, a chat turn round-trips and an approval prompt can be
  approved, denied and left to time out, each with the correct outcome (scripted plus manual).
- **SC-002**: A scripted ACL matrix shows that only the phone credential can write the inbound
  topic, that the agent's credential is refused on write, and that every other estate token is
  refused on both read and write.
- **SC-003**: A message published while the agent is down is never processed, and a gap notice
  arrives after reconnect.
- **SC-004**: After rollout, the `[Ntfy] Stream error … 403` warning is absent from
  `hermes_agent` logs for 7 days (`093` closed).
- **SC-005** (P2): A silence button creates exactly one bounded silence. A replayed or expired
  press creates none. Every outcome is confirmed on the phone.
- **SC-006**: Revoking the phone's inbound credential and redeploying takes effect within one
  deploy, verified by a refused publish.

## Assumptions

- The phone keeps Tailscale always-on (`082`). The ntfy Android app can publish to a topic from its
  message bar using the server account configured in the app.
- The agent stays on the stock `nousresearch/hermes-agent` image for P1. The text approval fallback
  and the split subscribe/publish topics need no code change.
- The gateway treats an ntfy conversation as an interactive session, so `approvals: mode: manual`
  prompts there instead of denying. This must be verified first in the plan (research).

## Out of Scope

- Any channel other than ntfy (Telegram, Signal, e-mail inbound).
- Exposing Alertmanager or other service APIs to the phone directly.
- Giving the agent estate-wide powers it does not have today. Egress and tools are unchanged.
- Replacing Pushover (still `082`'s separate decision).
- Generic "run a command" actions in the relay.

## Dependencies

- [`082`](./082-ntfy-push-service.md) (ntfy server, ACL model) and
  [`083`](./083-hermes-agent-runtime.md) (agent runtime): both amended.
- [`092`](./092-log-aggregation.md) for FR-009 audit logs.
- P2 silence buttons: the relay needs LAN reach to Alertmanager on the monitoring LXC.

## Open Questions

1. ~~**One phone token or two?**~~ **Resolved** (research R-004): the Android app holds one
   user per server, and ntfy ACLs attach to users, not tokens. The phone credential is therefore
   the existing `owner` user, which gains `read-write` on the inbound and actions topics.
2. **Native approval buttons (FR-012)**: an `http` action would embed a token in agent-composed
   content, so it is rejected. **Candidate** (R-006): a `broadcast` action with
   `intent=io.heckel.ntfy.SEND_MESSAGE`. The ntfy app then publishes the press itself with its own
   account, and the notification holds no credential. Two things are unverified until tested on
   the device: whether the app receives its own broadcast, and whether it publishes with the
   configured user. Buttons also need an adapter change, preferably upstream. Approvals stay typed
   until then.
3. ~~**Offline-gap detection**~~ **Resolved** (R-007): a read-only `gateway:startup` hook posts the
   gap, measured from the last heartbeat. Mid-run stream drops are covered by a `092` Loki rule on
   sustained `Stream error` lines. Once the permanent 403 is gone, those lines become a real signal.
4. **Which estate actions are worth a button?** Silence is the only P2 action. Re-run backup, snooze
   version and re-run mutation each need their own threat check (P3).
5. ~~**Where does the relay run?**~~ **Resolved** (R-011): in the monitoring LXC's compose stack,
   next to Alertmanager. Nothing new is exposed and no new LXC is needed.
6. **Upstream**: contribute native ntfy approval buttons and `view`/`broadcast` actions on
   adapter messages to `nousresearch/hermes-agent`. 403-as-fatal no longer matters for us.

Found during research, now requirements in the plan:

- **`/yolo` and `/update` over ntfy** would let one phone message turn approvals off or update the
  agent. They are gated with upstream's per-platform slash-command policy, and the LAB gate must
  prove that before PROD (R-002).
- **ntfy server templates cannot emit action buttons** (only title, message and priority), so
  alert buttons mean the relay takes over Alertmanager's ntfy formatting (R-010). Pushover is
  untouched.
- **The chat is split across two topic views** (type in `hermes-in`, read on `hermes`), because
  the agent must never write `hermes-in`. This is accepted. A "Reply" deep-link button comes with
  the same upstream PR (R-013).
