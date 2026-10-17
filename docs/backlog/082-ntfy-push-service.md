# Feature Specification: ntfy — self-hosted push notifications to the owner's phone

**Feature Branch**: `082-ntfy-push-service`
**Created**: 2026-10-16
**Status**: **Implemented** — live on PROD since 2026-10-17 ([`specs/082-ntfy-push-service/`](../../specs/082-ntfy-push-service/)). Dual delivery with Pushover in a 4-week trial until 2026-11-14. Unblocks [`083`](./083-hermes-agent-runtime.md).
**Input**: Run **ntfy** on its own LXC as the estate's push channel to the owner's Android phone.
Two publishers from the start: **Alertmanager** (alongside Pushover, not replacing it) and the
**Hermes Agent** scheduler from `083`. LAN and tailnet only, like every other service. Delivered as
configuration of the upstream image, not new software.

---

## Why this exists

Today the only route to the owner's phone is Alertmanager → Pushover
(`ansible/roles/monitoring_stack/templates/alertmanager.yml.j2`). That is fine for alerts and wrong
for everything else: there is no way for a scheduled job, a script or an agent to say "this
happened" to a phone without going through an alert rule. Open WebUI (Hermes, `065`) cannot do it
either — its browser notifications fire only while the app is open, and it has no push service.

Measured need that triggered this: a daily model scout in the `local-llm` repo that should tell
the owner when a new MLX model worth benchmarking appears. It is the first of a class of scheduled
jobs; `083` makes those jobs cheap, and this feature gives them somewhere to report.

Why ntfy:

- **Native Android app that talks to a self-hosted server directly.** For any server other than
  `ntfy.sh` the app uses its own persistent connection ("instant delivery"), not Firebase, in both
  the Play and F-Droid flavours. Nothing about a message leaves the estate.
- **A supported delivery target in Hermes Agent** (`083`): `NTFY_SERVER_URL`, `NTFY_TOKEN`,
  `NTFY_HOME_CHANNEL`, usable by cron jobs out-of-process from the gateway.
- **Alertmanager without a bridge**: ntfy ships a pre-defined `alertmanager` message template
  (`?template=alertmanager`), so Alertmanager's plain webhook receiver is enough.
- **Real access control**: `auth-default-access: deny-all`, per-user topic ACLs, bearer tokens.

## Decisions recorded (2026-10-16)

| decision | choice | why |
|---|---|---|
| Where ntfy runs | **Its own LXC** | One service per LXC (constitution). It serves the whole estate (Alertmanager, Hermes, future jobs), not Hermes alone. |
| Reach off the home network | **Tailscale always-on** on the phone | ntfy stays LAN/tailnet-only like every service behind Caddy (`hus-sky.no` names resolve to Caddy's LAN address, `reverse_proxy_ip`). No new internet-facing exposure class. |
| Relation to Pushover | **Alongside first** | Add an ntfy receiver next to Pushover, compare over a trial window, decide in a later change. |
| Direction | **Publish to the phone only** | No inbound use in this feature. Hermes Agent's ntfy adapter can *receive* commands from a topic; `083` deliberately does not enable that (see its FR-011). |
| iOS | Out of scope | The owner's phone is Android. iOS would need `upstream-base-url: https://ntfy.sh` for APNs. |

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - An alert reaches the phone through ntfy (Priority: P1)

**Independent Test**: Fire a test alert in Alertmanager; the phone, on mobile data with Tailscale
connected, shows it in the ntfy app, formatted, within a minute — and Pushover still receives it
as before.

**Acceptance Scenarios**:
1. **Given** a firing alert of any severity, **When** Alertmanager routes it, **Then** it is
   delivered to **both** Pushover (unchanged) and the ntfy `alerts` topic.
2. **Given** the ntfy message, **When** the owner reads it, **Then** it is rendered by the
   `alertmanager` template (alert name, state, summary), not raw JSON.
3. **Given** severities `critical` / `warning` / `info`, **When** they reach ntfy, **Then** they
   map to distinct ntfy priorities, with `info` silent — mirroring today's Pushover mapping
   (2 / 0 / −1).
4. **Given** an alert that resolves, **When** Alertmanager sends the resolution, **Then** ntfy
   shows it as resolved.

### User Story 2 - A script or scheduled job notifies the phone (Priority: P1)

**Independent Test**: From the Hermes LXC, publish to the `hermes` topic with the Hermes publisher
token; the phone shows it. Publish with no token, or with the Alertmanager token: refused.

**Acceptance Scenarios**:
1. **Given** a publisher token scoped to topic `hermes`, **When** it publishes there, **Then** the
   phone receives it.
2. **Given** the same token, **When** it publishes to `alerts` or reads any topic, **Then** it is
   refused.
3. **Given** no credentials, **When** anyone on the LAN or tailnet reads or publishes any topic,
   **Then** it is refused (`deny-all`).

### User Story 3 - ntfy is on the front page and its state is honest (Priority: P2)

**Independent Test**: The `hus-sky.no` landing page shows an ntfy card whose indicator turns red
when the container is stopped.

### User Story 4 - The phone keeps receiving away from home (Priority: P1)

**Independent Test**: Phone on mobile data, Wi-Fi off, Tailscale always-on; send a test message;
it arrives without opening the app. Then turn Tailscale off; send another; it arrives after
Tailscale reconnects (ntfy caches undelivered messages).

### Edge Cases

- **ntfy down**: Alertmanager still reaches Pushover; ntfy's own liveness alert fires through
  Pushover. ntfy must never be the only path for its own outage alert.
- **Phone off the tailnet for hours**: messages wait in ntfy's cache up to its cache duration;
  anything older is lost by design and that duration is recorded.
- **Battery optimisation** kills the app's persistent connection on some Android builds: the
  setup instructions include the battery exemption, and US-4 is tested after a night idle.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: ntfy MUST run on its own unprivileged LXC (`lxc_service` module, Debian 12, Docker
  Compose like the other services), at the next free address in the estate's topology (a new `ntfy_ip` next to the other
  `*_ip` variables in `group_vars/services/vars.yml`, or wherever
  [`081`](./081-externalise-prod-topology.md) has moved topology to by then).
- **FR-002**: The image MUST be pinned in the `group_vars` versions block, like every other service
  (`consolidate-service-versions`).
- **FR-003**: ntfy MUST be reachable as `ntfy.hus-sky.no` through Caddy (`caddy_services`,
  `user_facing: true`), on the LAN and over the tailnet only. No port forward, no public DNS.
- **FR-004**: Access control MUST be `auth-default-access: deny-all`, with users and ACLs declared
  in `server.yml` from vault:
  - `owner` — read on all topics, the account the phone logs in with;
  - `alertmanager` — write-only on `alerts`;
  - `hermes` — write-only on `hermes` (used by `083`).
  Each publisher gets its own token. Tokens and password hashes live in vault; nothing in git.
  Proposed vault names: `ntfy_owner_password_hash`, `ntfy_owner_token`,
  `ntfy_alertmanager_token`, `ntfy_hermes_token` (the last is consumed by `083` FR-011).
- **FR-005**: Alertmanager MUST gain an ntfy webhook receiver **in addition to** Pushover on every
  route, posting to `…/alerts?template=alertmanager` with the `alertmanager` bearer token and
  `send_resolved: true`. Severity → ntfy priority via one receiver per severity (query parameter
  `priority`), matching today's Pushover semantics: `critical` urgent, `warning` default, `info`
  min/silent.
- **FR-006**: ntfy's own liveness MUST be probed and alerted through the existing monitoring
  contract (`host_vars/ntfy.yml`, `monitoring_contract`), and that alert MUST reach Pushover.
  If ntfy exposes metrics (`enable-metrics`), scrape them.
- **FR-007**: The landing page MUST show an ntfy card with a liveness indicator produced the same
  way as every other card.
- **FR-008**: No message content leaves the estate: no `upstream-base-url`, no Firebase, no
  `ntfy.sh` dependency.
- **FR-009**: Message cache duration MUST be set deliberately and recorded (proposal: 72 h), so
  "phone was off the tailnet" has a known bound.
- **FR-010**: State that matters is declarative (users, ACLs and tokens come from vault on every
  deploy), so the message cache is disposable and the service needs **no backup role** —
  the same reasoning as `market-model`. A rebuild from scratch MUST restore working delivery
  with no manual step other than the phone already being subscribed.
- **FR-011**: Phone setup MUST be documented in a runbook: ntfy Android app, add server
  `https://ntfy.hus-sky.no`, log in as `owner`, subscribe to `alerts` and `hermes`, battery
  exemption, Tailscale always-on VPN.

### Key Entities

- **Topic**: `alerts` (Alertmanager), `hermes` (Hermes Agent and its scheduled jobs). Further
  topics are added per publisher, never shared between publishers.
- **Publisher**: one ntfy user + token per sending system, write-only to its own topic.
- **Subscriber**: the owner's phone, read-only.

## Success Criteria *(mandatory)*

- **SC-001**: A test alert of each severity arrives on the phone via ntfy, on mobile data with
  Tailscale, within 60 s, while Pushover still receives it.
- **SC-002**: Every unauthorised read/publish combination in US-2 is refused (scripted check).
- **SC-003**: Stopping the ntfy container raises its liveness alert on Pushover within the
  contract's `for:` window.
- **SC-004**: A from-scratch rebuild of the LXC restores delivery with no manual step.
- **SC-005**: After a trial window (proposal: 4 weeks), a comparison of ntfy vs Pushover
  delivery (missed, late, duplicates) is written up as input to the "drop Pushover?" decision.

## Assumptions

- The owner's phone is Android, runs Tailscale as an always-on VPN, and the tailnet ACL
  (`ansible/roles/tailscale_acl`) lets it reach `reverse_proxy_ip` on 443.
- Caddy's existing TLS setup covers a new `ntfy.hus-sky.no` vhost like the others.

## Out of Scope

- Replacing Pushover (separate decision after SC-005).
- iOS clients, public exposure, ntfy.sh.
- Two-way messaging / using ntfy as a chat channel to an agent.
- Web push / the ntfy web app beyond what the image serves by default.

## Dependencies

- None blocking. `083` consumes FR-004's `hermes` publisher.

## Open Questions

1. **Priority mapping**: ~~confirm that ntfy's `priority` query parameter combines with
   `?template=alertmanager` on a webhook POST~~ — **Resolved** (research R-003): a custom Go
   template (`homelab-alertmanager.yml`) computes `priority` from the payload itself, so one
   webhook definition is enough and no query-parameter precedence is relied on.
2. **Cache duration**: ~~72 h proposed; long enough for a weekend off the tailnet~~ —
   **Resolved** (FR-013): 72 h, inlined in `server.yml.j2` as `cache-duration: "72h"`.
