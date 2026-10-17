# Feature Specification: ntfy — self-hosted push notifications to the owner's phone

**Feature Branch**: `082-ntfy-push-service`

**Created**: 2026-10-16

**Status**: Implemented — live on PROD since 2026-10-17. Dual delivery with Pushover in a 4-week
trial until 2026-11-14 (SC-006, `trial-report.md`)

**Input**: User description: "082-ntfy-push-service.md" — the backlog entry
[`docs/backlog/082-ntfy-push-service.md`](../../docs/backlog/082-ntfy-push-service.md): run a
self-hosted push-notification service on its own machine as the estate's channel to the owner's
Android phone. Two publishers from the start: the estate's alerting (alongside the existing
third-party push provider, not replacing it) and the agent scheduler of feature `083`. LAN and
tailnet only, like every other service. Delivered as configuration of existing upstream software,
not new code.

## Background

Today the only route to the owner's phone is the alerting pipeline's third-party push provider
(Pushover). That suits alerts and nothing else: a scheduled job, a script or an agent has no way to
tell the phone "this happened" without disguising itself as an alert rule. The AI workspace (`065`)
cannot do it either; its notifications fire only while it is open in a browser.

The need that triggered this is a daily job that should tell the owner when a new local model worth
benchmarking appears. It is the first of a class of scheduled jobs; `083` makes such jobs cheap, and
this feature gives them somewhere to report.

### Decisions already taken (2026-10-16)

| Decision | Choice | Why |
|---|---|---|
| Where the service runs | Its own machine | One service per machine (constitution). It serves the whole estate, not one consumer. |
| Reach off the home network | The phone keeps an always-on tailnet connection | The service stays LAN/tailnet-only like every other; no new internet-facing exposure. |
| Relation to the existing push provider | Alongside, first | Run both, compare over a trial window, decide in a later change. |
| Direction | Publish to the phone only | No inbound commands from the phone through this channel. |
| Platforms | Android only | The owner's phone is Android. iOS would require relaying through a public third party. |

## User Scenarios & Testing *(mandatory)*

### User Story 1 - An alert reaches the phone through the new channel (Priority: P1)

When something in the estate goes wrong, the owner's phone receives the alert through the
self-hosted channel, readable at a glance, and the existing provider still receives it as before.

**Why this priority**: Alerts are the highest-value traffic the channel will carry, and running both
paths side by side is how the owner learns whether the new one can be trusted.

**Independent Test**: Fire a test alert; the phone, on mobile data with the tailnet connected, shows
it in the notification app, formatted, within a minute. The existing provider also receives it.

**Acceptance Scenarios**:

1. **Given** a firing alert of any severity, **When** the alerting pipeline routes it, **Then** it is
   delivered to **both** the existing provider (unchanged) and the self-hosted channel's alerts topic.
2. **Given** an alert delivered through the new channel, **When** the owner reads it, **Then** it shows
   the alert name, its state and its summary as readable text, not raw machine data.
3. **Given** alerts of severity critical, warning and info, **When** they arrive, **Then** each has a
   distinct urgency on the phone, with info delivered silently — mirroring how the existing provider
   treats the same severities today.
4. **Given** an alert that resolves, **When** the resolution is sent, **Then** the phone shows it as
   resolved.

---

### User Story 2 - A script or scheduled job notifies the phone (Priority: P1)

A scheduled job in the estate finishes, finds something worth knowing, and puts a message on the
owner's phone, using a credential that lets it do that and nothing more.

**Why this priority**: This is the capability that does not exist today and the reason for the
feature. `083` depends on it.

**Independent Test**: From the agent scheduler's machine, publish to its own topic with its own
credential: the phone shows it. Publish with no credential, or with the alerting pipeline's
credential: refused.

**Acceptance Scenarios**:

1. **Given** a publisher credential scoped to its own topic, **When** it publishes there, **Then** the
   phone receives the message.
2. **Given** the same credential, **When** it publishes to another publisher's topic or tries to read
   any topic, **Then** it is refused.
3. **Given** no credential, **When** anyone on the LAN or tailnet tries to read or publish any topic,
   **Then** it is refused.

---

### User Story 3 - The phone keeps receiving away from home (Priority: P1)

The owner is out on mobile data. Messages still arrive promptly without the owner opening the app,
and messages sent while the phone was briefly unreachable arrive once it reconnects.

**Why this priority**: A notification channel that works only on home Wi-Fi fails exactly when it is
needed.

**Independent Test**: With Wi-Fi off and the tailnet always on, send a test message; it arrives
without opening the app. Disconnect the tailnet, send another, reconnect; it arrives then. Repeat
after the phone has been idle overnight.

**Acceptance Scenarios**:

1. **Given** the phone on mobile data with the tailnet connected, **When** a message is published,
   **Then** it arrives without the app being opened.
2. **Given** the phone off the tailnet, **When** a message is published and the phone reconnects
   within the retention window, **Then** the message arrives after reconnection.
3. **Given** the phone idle overnight, **When** a message is published in the morning, **Then** it
   arrives without the app being opened.

---

### User Story 4 - The service is on the front page and its state is honest (Priority: P2)

The owner sees the notification service on the homelab front page with an indicator that reflects
whether it is actually up.

**Why this priority**: Discoverability and honest state are estate conventions, but the channel
delivers value without them.

**Independent Test**: Load the front page and observe the card; stop the service; reload and see the
indicator report it as down.

**Acceptance Scenarios**:

1. **Given** the front page, **When** it loads, **Then** a card for the service is shown with a
   liveness indicator produced the same way as every other card's.
2. **Given** the service is stopped, **When** the front page loads, **Then** the card reports it down.

---

### Edge Cases

- **The notification service is down.** Alerts still reach the phone through the existing provider,
  and the service's own outage alert travels through the existing provider. The new channel is never
  the only path for news of its own failure.
- **The phone is off the tailnet longer than the retention window.** Messages older than the window
  are lost by design. The window is chosen deliberately and recorded.
- **Android battery optimisation kills the app's persistent connection.** The phone setup includes
  the battery exemption, and US-3 scenario 3 tests the result after a night idle.
- **A publisher credential leaks.** Because each publisher can only write to its own topic, the
  damage is limited to spam on that topic. It cannot read messages or impersonate another publisher.
- **The machine is rebuilt from scratch.** Delivery resumes with no manual step. The phone, already
  subscribed, reconnects. Messages cached before the rebuild may be lost.

## Requirements *(mandatory)*

### Functional Requirements

#### Placement and reach

- **FR-001**: The service MUST run on its own unprivileged machine, provisioned the same way as the
  estate's other single-service machines, at an address defined centrally with the estate's other
  addresses.
- **FR-002**: The service's software version MUST be pinned in the estate's central versions list,
  like every other service.
- **FR-003**: The service MUST be reachable at a stable `hus-sky.no` name through the estate's
  reverse proxy over an encrypted connection, on the LAN and the tailnet only. There MUST be no route
  from the internet to it: no port forward, and no DNS record created for it. Its name is covered by
  the estate's existing public wildcard, which resolves only to the reverse proxy's private address
  (`docs/network-layout.md`). That address is unreachable from outside, so this is not a route in.
- **FR-004**: No message content may leave the estate. The service MUST NOT relay through any public
  notification server or third-party push infrastructure.

#### Access control

- **FR-005**: Anonymous access MUST be denied for every topic, for both reading and publishing.
- **FR-006**: Accounts and permissions MUST be declared in configuration and applied on every deploy:
  - an **owner** account that can read every topic, used by the phone;
  - one **publisher** account per sending system, able to write only to its own topic and to read
    nothing. Initially: the alerting pipeline (topic `alerts`) and the agent scheduler of `083`
    (topic `hermes`).
- **FR-007**: Each publisher MUST have its own credential. Credentials and password material MUST
  come from the estate's secret store; nothing secret may be committed to source control.

#### Alert delivery

- **FR-008**: The alerting pipeline MUST deliver every alert to the new channel **in addition to** the
  existing provider, on every route, including resolutions.
- **FR-009**: Alerts delivered to the new channel MUST be rendered as human-readable text (alert
  name, state, summary).
- **FR-010**: Severity MUST map to phone urgency the same way it does for the existing provider today:
  critical urgent, warning normal, info silent.

#### Operations

- **FR-011**: The service MUST publish a monitoring contract consistent with the estate's other
  services, including a liveness probe and an alert when it is unreachable. That alert MUST be
  delivered through the existing provider. If the service exposes its own metrics, they MUST be
  collected.
- **FR-012**: The service MUST appear on the homelab front page with a liveness indicator produced by
  the estate's existing mechanism.
- **FR-013**: The message retention window MUST be set deliberately and recorded, giving
  "phone was off the tailnet" a known bound. The default is 72 hours.
- **FR-014**: All state that matters (accounts, permissions, credentials) MUST be re-applied from
  configuration on every deploy, so cached messages are disposable and the service needs no backup
  job. A from-scratch rebuild MUST restore working delivery with no manual step beyond the phone
  already being subscribed.
- **FR-015**: Phone setup MUST be documented in a runbook: install the app, add the server, sign in
  as the owner, subscribe to each topic, grant the battery exemption, and enable the tailnet as an
  always-on VPN.
- **FR-016**: The service MUST be deployable through both the CI/CD pipeline and a developer laptop,
  and MUST be added to the pipeline's service choices in the same change (constitution V).
- **FR-017**: The feature MUST be delivered by deploying and configuring existing, unmodified
  software. It MUST NOT require bespoke application code.

### Key Entities

- **Topic**: A named stream of messages. Initially `alerts` (the alerting pipeline) and `hermes` (the
  agent scheduler and its jobs). Topics are added per publisher and never shared between publishers.
- **Publisher**: A sending system, represented by one account and one credential that can write only
  to its own topic.
- **Subscriber**: The owner's phone, signed in as the owner account, read-only on all topics.
- **Retention window**: How long an undelivered message waits for the phone. It bounds what an absent
  phone can catch up on.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A test alert of each severity arrives on the phone through the new channel within 60
  seconds, on mobile data with the tailnet connected, while the existing provider still receives it.
- **SC-002**: 100% of the unauthorised read and publish combinations in US-2 are refused, verified by
  a repeatable scripted check.
- **SC-003**: When the service is stopped, its outage alert reaches the phone through the existing
  provider within the monitoring contract's alert window.
- **SC-004**: After a from-scratch rebuild of the machine, a test message reaches the already
  subscribed phone with no manual step.
- **SC-005**: A message sent while the phone has been idle overnight arrives without the app being
  opened.
- **SC-006**: After a 4-week trial window, a comparison of the new channel against the existing
  provider (missed, late and duplicate deliveries) is written up as input to the "drop the existing
  provider?" decision.
- **SC-007**: The delivered change contains no bespoke application source code.

## Assumptions

- **Selected implementation**: ntfy, the self-hosted open-source push service. Its Android app keeps
  its own persistent connection to a self-hosted server without using Google's push service, the
  agent runtime of `083` supports it as a delivery target, and the alerting pipeline can post to it
  without a bridge. The implementation inputs recorded in the backlog entry (account names, proposed
  secret names, how alerts are rendered and how severity maps to urgency) feed `/speckit-plan`.
- The owner's phone is Android, runs the tailnet as an always-on VPN, and the tailnet's access policy
  lets it reach the reverse proxy on 443.
- The reverse proxy's existing certificate setup covers a new `hus-sky.no` name like the others.
- Severity-to-urgency mapping combined with readable alert rendering is supported on a single
  delivery. This is to be verified on the lab deploy before relying on one alert route per severity
  (backlog open question 1).
- The owner is the only subscriber.

## Dependencies

- **None blocking.** The existing reverse proxy, monitoring, front page and alerting pipeline are
  reused, not rebuilt.
- **Consumed by `083`**: the `hermes` publisher account and its credential (FR-006, FR-007).
- **Topology location**: if [`081`](../../docs/backlog/081-externalise-prod-topology.md) has moved the
  estate's address definitions by the time this is planned, FR-001 follows them there.

## Out of Scope

- Replacing the existing push provider. That is a separate decision, informed by SC-006.
- iOS clients, public exposure, and any public relay server.
- Two-way messaging, or using this channel to send commands to an agent.
- Web push, and any use of the service's web interface beyond what it serves by default.
