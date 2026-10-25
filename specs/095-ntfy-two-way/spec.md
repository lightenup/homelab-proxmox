# Feature Specification: Two-way ntfy — talk to Hermes and act on notifications from the phone

**Feature Branch**: `095-ntfy-two-way`

**Created**: 2026-10-25

**Status**: Draft

**Input**: Backlog item [`docs/backlog/095-ntfy-two-way.md`](../../docs/backlog/095-ntfy-two-way.md).
The owner wants to chat with the Hermes agent from the phone, answer the agent's approval
prompts and reply to its scheduled-job output over the existing push channel. They also want
action buttons on estate notifications (silence an alert, re-run a backup and similar), executed
by a deterministic relay rather than by the agent. This feature amends `082` (push is publish-only)
and `083` (the agent is delivery-only), and supersedes `093`.

## Clarifications

### Session 2026-10-25

- Q: What may a phone message make the agent do? → A: The full agent, with the same tools as the
  web workspace. Flagged commands become approval prompts answered on the phone. Non-interactive
  surfaces stay deny.
- Q: How is the sender identified, given the push channel does not reveal publishers? → A: By a
  dedicated inbound channel that only one phone-held credential can write. The agent can read it
  and can never write it.
- Q: What happens to messages sent while the agent is offline? → A: They are dropped, never
  replayed, and the agent reports the gap when it is back.
- Q: How are approvals answered? → A: With action buttons, and a typed reply as fallback. Buttons
  only if the agent cannot forge a press.
- Q: Where do notification action buttons go? → A: To a dedicated actions channel consumed by a
  deterministic relay with a fixed allowlist.
- Q: What is the first deliverable? → A: Agent chat, approvals and the offline notice (P1).
  Buttons follow.
- Q: Should an approval from the phone cover exactly one command, or may the owner grant a
  session-wide approval? → A: Session-wide approval is allowed. It lasts until the conversation is
  reset. (Its scope is narrowed by the session-scope answer below.)
- Q: When the agent comes back after being down or disconnected, should it always report the
  gap's start and end on a restart, or only when the gap exceeds a configured threshold? → A:
  Always report on restart, however short the gap. Mid-run stream drops are reported only when
  sustained (over 10 minutes).
- Q: Can more than one approval prompt be pending at the same time in a single phone conversation,
  and if so, how does a typed reply pick which prompt it resolves? → A: One prompt at a time. The
  agent withholds the next prompt until the current one is resolved.
- Q: How should the estate and the owner find out that the action relay is down — a relay heartbeat
  that the estate's monitoring alerts on, or the owner simply noticing that presses get no response?
  → A: The relay emits a heartbeat; the estate's monitoring alerts through the normal route when it
  goes missing.
- Q: What should happen when the owner sends a message from the phone that is too long for the push
  server to accept (for example, a pasted log)? → A: Keep the push server's default size limit.
  Oversized messages are refused, and the app shows the error locally.
- Q: How should upstream's permanent `/approve always` be handled, given that it lets scheduled
  jobs skip their refusal until the agent restarts and no setting switches it off? → A: Ship with a
  detection control: alert on any permanent approval, revoke it by restarting the agent, and pursue
  an upstream switch in parallel (research R-014).
- Q: Should session-wide approval cover only that kind of command (upstream `/approve session`)
  rather than every flagged command? → A: Yes. A session approval covers the approved pattern for
  the rest of the conversation; other flagged commands still prompt.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Chat with the agent from the phone (Priority: P1)

The owner, away from a laptop, types a question or instruction to the agent in the push app and
gets the answer back as a notification. The conversation keeps its context across messages.

**Why this priority**: This is the core capability. Every other agent story builds on the inbound
path, and it removes the need to open the web workspace for quick tasks.

**Independent Test**: On mobile data, send "what's the disk usage of your data directory?" on the
inbound channel. A reply arrives on the agent's outbound channel. A message sent with any other
credential, or with none, is refused by the push server and never reaches the agent.

**Acceptance Scenarios**:

1. **Given** the owner credential, **When** the owner sends text on the inbound channel,
   **Then** the agent handles it as a turn in an ongoing conversation and replies on the outbound
   channel.
2. **Given** any other estate credential, including the agent's own, **When** it sends on the
   inbound channel, **Then** the push server refuses it.
3. **Given** a follow-up message, **When** it arrives, **Then** the agent keeps the conversation's
   context. **When** the owner sends the reset command, **Then** a fresh conversation starts.
4. **Given** a reply longer than one notification can hold, **When** the agent sends it, **Then**
   the owner can see that it was truncated or split.

---

### User Story 2 - Answer an approval prompt on the phone (Priority: P1)

When the agent wants to run a flagged command in a phone-originated conversation, the owner gets
a prompt showing what will run, why it was flagged and how long they have to decide, and can
approve or deny from the phone.

**Why this priority**: Today every flagged command is refused, because the only interactive
surface the agent has is non-interactive in practice. This story makes the agent useful for real
operations with a human in the loop.

**Independent Test**: From the phone, ask the agent to delete a scratch file, which is a flagged
operation. A prompt arrives. Approve it and the file is deleted. Repeat with deny, and repeat with
no answer: the file remains, and the deadline was stated in the prompt.

**Acceptance Scenarios**:

1. **Given** a flagged command in a phone-originated conversation, **When** the agent reaches it,
   **Then** the owner receives a prompt with the command, the reason and the deadline.
2. **Given** that prompt, **When** the owner approves, **Then** the command runs once. **When** the
   owner denies or the deadline passes, **Then** it does not run.
3. **Given** a flagged command reached by a scheduled job, a single query or a web-workspace
   request, **When** it is reached, **Then** it is refused exactly as before this feature.
4. **Given** the agent itself (any of its tools, scripts or commands), **When** it tries to send
   an approval or any message on the inbound channel, **Then** the push server refuses it.
5. **Given** an approval prompt, **When** the owner grants a session approval, **Then** later
   commands of the same kind in that conversation run without a new prompt, and a different flagged
   command still prompts. **When** the owner sends the reset command, **Then** prompting starts
   again.
6. **Given** a pending approval prompt, **When** the conversation reaches a second flagged command,
   **Then** its prompt is withheld until the first prompt is resolved, and then delivered.
7. **Given** an approval prompt, **When** the owner grants a permanent approval (typed or bare
   word), **Then** an alert arrives through the normal route, and restarting the agent revokes it.

---

### User Story 3 - Know when messages were missed (Priority: P1)

If the agent was down or disconnected, the owner is told when it comes back, so a message sent in
the gap is not silently assumed to have been handled.

**Why this priority**: The chosen policy drops messages sent during a gap so that stale commands
are never replayed. Without this notice, "dropped" would be indistinguishable from "ignored".

**Independent Test**: Stop the agent, send a message on the inbound channel, then start the agent.
The message is never acted on. Within one minute of reconnecting the agent reports that it was
unreachable from T1 to T2.

**Acceptance Scenarios**:

1. **Given** the agent was offline or disconnected, **When** it reconnects, **Then** it does not
   process messages sent during the gap.
2. **Given** the agent restarted after any gap, however short, **When** it comes back, **Then** it
   reports the gap's start and end to the owner.
3. **Given** a mid-run stream drop shorter than 10 minutes, **When** it recovers, **Then** nothing
   is reported.

---

### User Story 4 - Reply to scheduled-job output (Priority: P2)

A scheduled job reports something, for example "new model X is available". The owner replies "benchmark it" and the
agent acts with that report as context, without the owner pasting it.

**Why this priority**: This turns reports into conversations. It depends on US-1.

**Independent Test**: Trigger the model-scout report, reply to it from the phone, and observe that
the agent's answer refers to the reported model.

**Acceptance Scenarios**:

1. **Given** a job report on the phone, **When** the owner replies, **Then** the agent knows which
   report the reply refers to: the most recent one unless the owner names another.
2. **Given** a report from a job that runs without the agent, **When** the owner replies, **Then**
   an agent conversation starts with the report as context. The job itself is not re-run.

---

### User Story 5 - Act on an alert from the notification (Priority: P2)

A firing-alert notification carries buttons such as "Silence 1h". Pressing one silences the alert
and confirms it, without opening any other app.

**Why this priority**: A deterministic action with high everyday value (flapping alerts at night)
and lower risk than agent chat. It is independent of the agent.

**Independent Test**: Fire a test alert, press "Silence 1h", and verify that exactly one matching
silence exists and that a confirmation arrived. Replaying the same press later creates nothing and
says why.

**Acceptance Scenarios**:

1. **Given** a firing alert, **When** it is delivered, **Then** it carries at most three action
   buttons drawn from an allowlist, and tapping the notification itself opens the alert's dashboard.
2. **Given** a press, **When** the relay receives it, **Then** the relay validates it against the
   allowlist and checks that the target alert fired within the last 24 hours (it may have resolved
   since, as a flapping alert does), executes it, and confirms on the phone. Anything off the
   allowlist is refused and reported.
3. **Given** a replayed press, or one older than its expiry, **When** it is received, **Then**
   nothing happens and the owner is told why.
4. **Given** the relay is down, **When** a button is pressed, **Then** the owner can tell that the
   action did not happen, and alert delivery through the existing fallback channel is unaffected.
5. **Given** the relay is down, **When** its heartbeat goes missing, **Then** the estate's
   monitoring alerts through the normal route.

---

### User Story 6 - Native approval buttons (Priority: P2)

Approval prompts carry Approve/Deny buttons, so a typed reply is no longer needed.

**Why this priority**: Better UX than typing, but only acceptable if the agent cannot forge a
press (FR-012). The typed fallback from US-2 remains.

**Independent Test**: An approval prompt shows buttons. Pressing Approve runs the command. A forged
"press" built from anything the agent can read is refused.

**Acceptance Scenarios**:

1. **Given** an approval prompt, **When** the owner presses Approve or Deny, **Then** the outcome
   matches US-2.
2. **Given** a press constructed by the agent, **When** it is received, **Then** it has no effect.

---

### User Story 7 - Act on other estate notifications (Priority: P3)

Other notifications offer buttons for their natural next step: re-run a failed backup, snooze a
version-currency finding, re-run the mutation gate.

**Why this priority**: The value is real, but each action needs its own threat check. The pattern
comes from US-5.

**Independent Test**: A backup-failure notification offers "Re-run". Pressing it re-runs that
backup job and reports the result.

**Acceptance Scenarios**:

1. **Given** a candidate action, **When** it is proposed, **Then** it is admitted to the allowlist
   only after its own threat review. No generic "run a command" action exists.

---

### Edge Cases

- **Owner credential leaked**: whoever holds it can direct the agent, still bounded by approvals
  and the agent's existing network and tool limits. Revocation must take one deploy (FR-010).
- **Prompt injection** in job output or web content tells the agent to approve its own command or
  to post on the inbound channel: refused, because the agent holds no credential that can write
  there.
- **An approval and a chat message pending at the same time**: an answer resolves the prompt it is
  meant for and never a different one.
- **Session approval**: once the owner grants a session approval, later commands of the same kind
  in that conversation run without further prompting until the conversation is reset.
- **Permanent approval**: upstream's "always" choice lasts until the agent restarts and also lets
  that pattern through scheduled jobs. It raises an alert, and a restart revokes it (R-014).
- **Bare-word replies**: while a prompt is pending, replies such as "yes", "ok" or "always" count as
  the matching approval. With no prompt pending, they are ordinary chat.
- **Phone off the network**: outbound messages wait in the push server's cache as today. Inbound
  messages cannot be sent.
- **Oversized inbound message**: the push server refuses it at its current 32k size limit; the app
  shows the error locally, and the agent never sees the message.
- **Push server down**: chat and buttons are unavailable, and alerts still reach the fallback
  channel.
- **Echo**: the agent never processes its own outbound messages.
- **Rehearsal (LAB) deploys**: these can never receive commands on the production inbound or
  actions channels, because no credential for them is rendered there. The LAB rig may listen on a
  separate scratch channel pair (FR-011).
- **Slash commands**: only the commands in FR-014 work over the inbound channel; anything else gets a
  short refusal. `/help` lists exactly the allowed set.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The agent MUST have a dedicated inbound channel, separate from its outbound channel.
  The agent's credential MUST be able to read the inbound channel and MUST NOT be able to write to
  it.
- **FR-002**: Only the owner credential (the owner account: its password in the phone app and the
  password manager, its token in the vault) MUST be able to write the inbound channel. No estate
  service, publisher or the agent may hold it at runtime.
- **FR-003**: The agent MUST act only on messages from the inbound channel. Its own allowlist MUST
  name that channel exactly: no wildcard and no allow-all.
- **FR-004**: A phone-originated conversation MUST have the same tools as a web-workspace
  conversation. Flagged commands MUST raise a prompt to the phone with the command, the reason and
  the deadline; the approval deadline is 15 minutes, so a prompt that arrives while the owner is
  busy can still be answered. They MUST run only on an explicit approval from the phone, and MUST NOT run on deny
  or timeout. An approval MAY be for this command only or for the rest of the conversation
  ("session"); the prompt MUST state the scope of each approval choice. A session approval
  authorizes later commands of the same kind (the same flagged pattern) in that conversation
  without further prompting; other flagged commands still prompt, and it ends when the
  conversation is reset. A permanent approval ("always"), which upstream offers and cannot switch
  off, MUST raise an alert through the normal route, and the documented revocation (an agent
  restart) MUST clear it. The agent MUST keep at most one approval prompt pending in a
  conversation at a time, and MUST withhold the next prompt until the current one is resolved.
- **FR-005**: Non-interactive surfaces (scheduled jobs, single queries, web-workspace requests,
  unattended runs) MUST keep refusing flagged commands exactly as `083` specifies. (See Accepted
  risks: permanent approvals.)
- **FR-006**: Messages sent while the agent is not listening MUST NOT be processed later. On every
  restart, the agent MUST report the gap's start and end to the owner, however short the gap was,
  as a low-priority (silent) notification. Mid-run stream drops MUST raise an estate alert through
  the normal route only when they persist for more than 10 minutes.
- **FR-007**: A reply to a scheduled-job report MUST give the agent that report as context.
- **FR-008**: Notification action buttons MUST deliver presses to a dedicated actions channel
  consumed by a deterministic relay (no LLM). The relay MUST:
  - run a fixed allowlist of actions with bounded parameters (for silences: 1 h, 24 h, or until
    the next 07:00 local time);
  - validate each press against the target: it must have fired within the last 24 hours, whether
    or not it is still firing;
  - expire each button 24 hours after the notification carrying it was sent;
  - refuse replayed and expired presses;
  - confirm or refuse every press on the phone;
  - emit a heartbeat that the estate's monitoring alerts on when it goes missing.
- **FR-009**: Every inbound message, approval decision and relay action MUST be logged with time,
  channel, message id and outcome, and MUST be searchable in the estate's log aggregation (`092`).
- **FR-010**: The owner credential (password and token) MUST be revocable and rotatable with a
  single deploy, and the procedure MUST be documented together with the phone setup.
- **FR-011**: Rehearsal (LAB) deploys MUST render no credential that can read the production
  inbound channel or touch the actions channel (extends `083` FR-014). The LAB rig MAY render a
  LAB-only agent credential limited to a scratch pair (read `hermes-lab-in`, write `hermes-lab`),
  so the approval behaviour can be tested repeatably; the owner credential is the only writer of
  `hermes-lab-in`, and no LAB credential has access to any production topic.
- **FR-012**: Native approval buttons MUST NOT rely on any credential or value the agent can read.
  If no design meets this, approvals stay typed-only.
- **FR-013**: `082`'s publish-only decision, `083`'s delivery-only requirement, `083`'s decision to
  keep restarts silent (now a silent gap notice, FR-006), `083`'s approval timeout (300 s → 15 min,
  FR-004), `083` FR-014 (LAB scratch pair, FR-011) and the agent's documented control comments MUST
  be amended to describe the new model. `093` MUST be closed as superseded.
- **FR-014**: Over the inbound channel the agent MUST accept only these slash commands: `approve`,
  `deny`, `new`, `reset`, `stop`, `status`, `compress`, `retry`, `undo`, `usage`, `title`, `model`,
  plus upstream's always-allowed `help` and `whoami`. Every other command, including `/yolo` and
  `/update`, MUST be refused with a short reply and logged (FR-009). `/help` MUST list exactly the
  allowed set.

### Key Entities

- **Inbound channel**: carries messages to the agent. Written only by the owner credential, read
  only by the agent (and by the owner).
- **Outbound channel**: carries the agent's replies, prompts and job reports. Unchanged from today.
- **Actions channel**: carries button presses. Written only by the owner credential (the phone app
  publishes each press) and read by the relay.
- **Owner credential**: the existing owner account (one user, research R-004): read on every topic
  plus write on the inbound and actions channels. The phone app signs in with its password.
- **Action relay**: a small deterministic consumer with an allowlist of actions, each defined by
  its parameters, bounds, validation and executor. Emits a heartbeat for the estate's monitoring.
- **Approval prompt**: one pending flagged command, with an identifier, a deadline and its
  conversation.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: From the phone on mobile data, a chat turn round-trips. An approval prompt can be
  approved, denied and left to time out, and each case produces the correct outcome 100% of the
  time across a scripted run of all three. A session approval runs the next command of the same
  kind without a new prompt, a different flagged command still prompts, and a reset conversation
  prompts again. A permanent approval of a harmless scratch command raises the alert within 5
  minutes, and after an agent restart the same pattern prompts again.
- **SC-002**: A scripted access matrix shows that only the owner credential can write the inbound
  channel, that the agent's credential is refused on write, and that every other estate credential
  is refused on both read and write.
- **SC-003**: A message sent while the agent is down is never processed, and a gap notice arrives
  within one minute of reconnecting.
- **SC-004**: For 7 days after rollout, the agent's logs contain no subscription-refused warnings
  (`093` closed).
- **SC-005** (P2): A silence button press creates exactly one bounded silence, also when the alert
  resolved a moment earlier. A replayed or expired press creates none. Every press is confirmed or refused on the phone within 30 seconds. A down
  relay produces a missing-heartbeat alert through the estate's normal route.
- **SC-006**: After the owner password and token are rotated and deployed once, a publish attempt
  to the inbound channel with the old password and with the old token is refused.
- **SC-007**: Over the inbound channel, every FR-014 command works, `/yolo` and `/update` are
  refused, and `/help` lists exactly the FR-014 set.

## Assumptions

- The owner's phone keeps Tailscale always-on (`082`), and the push app can send messages on a
  channel using the account configured for the server.
- The agent stays on the stock upstream image for P1. Text approvals and separate inbound and
  outbound channels need no code changes (confirmed in research R-001, R-014).
- The agent's runtime treats a push-channel conversation as interactive, so approvals prompt
  rather than deny (confirmed from source in R-001; the LAB gate re-checks it).
- The agent's tool and network limits from `083` are unchanged.
- Accepted risk (research R-014): upstream's permanent approval cannot be switched off. Granted from
  the phone, it lets that command pattern through scheduled jobs and other non-interactive surfaces
  until the agent restarts, against FR-005. Detected by FR-004's alert, revoked by a restart, and
  closed when the upstream switch (the permanent-approval switch task in tasks.md) ships.
- Relay memory: the relay remembers which alerts fired in the last 24 hours in memory only. After a
  relay restart, presses for alerts that are no longer firing are refused as unknown until they fire
  again.

## Out of Scope

- Inbound channels other than ntfy.
- Exposing Alertmanager or any other service API directly to the phone.
- New powers for the agent: its tools and egress stay as in `083`.
- Replacing Pushover.
- Any generic "run a command" relay action.

## Dependencies

- `082` ntfy push service and `083` Hermes agent runtime: both amended.
- `092` log aggregation, for FR-009.
- US-5: the relay needs network reach to the alert manager on the monitoring host.
