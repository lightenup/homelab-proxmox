# Data Model: Two-way ntfy (095)

## Topics

| Topic | Purpose | Writers | Readers | Slice |
|---|---|---|---|---|
| `hermes` | Agent replies, approval prompts, job reports, gap notices (unchanged) | `hermes` | `owner` | existing |
| `hermes-in` | Owner → agent chat and typed approvals | `owner` | `hermes`, `owner` (own echo) | 1 |
| `alerts` | Alert notifications with action buttons | `action_relay` (replaces `alertmanager`) | `owner` | 2 |
| `actions` | Button presses (action commands) | `owner` (through the app's `SEND_MESSAGE`) | `action_relay`, `owner` | 2 |
| `relay` | Relay confirmations and refusals | `action_relay` | `owner` | 2 |

Rule kept from `082`: one publisher per topic, never shared. `owner` is the exception, as the
human.

## ntfy users and ACL entries

Rendered into `auth-access` from `ntfy_users[*].access` (per-user list) plus the owner block.
Longer patterns take precedence over `owner:*` (`user/access_cache.go`).

| User | Entries | Changed by |
|---|---|---|
| `owner` | `*:read-only`, `hermes-in:read-write`, `actions:read-write` | 095 (the last two) |
| `hermes` | `hermes:write-only`, `hermes-in:read-only` | 095 (the second) |
| `alertmanager` | `alerts:write-only` → **removed** when slice 2 ships | 095 P2 |
| `action_relay` | `alerts:write-only`, `relay:write-only`, `actions:read-only` | 095 P2 (new) |
| `hermes_lab` | `hermes-lab-in:read-only`, `hermes-lab:write-only` | 095 (LAB gate) |
| `owner` (LAB pair) | `hermes-lab-in:read-write` | 095 (LAB gate) |
| `pve_backup`, `version_check`, `mutation` | unchanged | — |

Validation: no user other than `owner` has write on `hermes-in`, `actions` or `hermes-lab-in`;
`hermes_lab` has no grant on any production topic (guard test and SC-002).

Server `message-size-limit` stays `32k` (spec Edge Case "Oversized inbound message").

## Agent ntfy settings (three branches, tasks T014)

| Setting | PROD (`hermes_agent_operational`) | LAB rig (`lab_inventory`) | Pipeline LAB stage | Was |
|---|---|---|---|---|
| `NTFY_TOPIC` (subscribe) | `hermes-in` | `hermes-lab-in` | not set (ntfy platform off, `required_env`) | `hermes` |
| `NTFY_PUBLISH_TOPIC` | `hermes` | `hermes-lab` | `hermes` (inert, no token) | `hermes` |
| `NTFY_HOME_CHANNEL` | `hermes` | `hermes-lab` | `hermes` (inert) | `hermes` |
| `NTFY_ALLOWED_USERS` | `hermes-in` (= topic name, R-003) | `hermes-lab-in` | not set | unset |
| `NTFY_TOKEN` | `ntfy_hermes_token` | `ntfy_hermes_lab_token` | not set (083 FR-014) | PROD only |
| `NTFY_ALLOW_ALL_USERS` / `GATEWAY_ALLOW_ALL_USERS` | never set | never set | never set | unset |

Slash gating (all branches, spec FR-014): root-level `ntfy:` block with `allow_admin_from: ["no-admin"]`
(matches no sender id) and `user_allowed_commands: [approve, deny, new, reset, stop, status,
compress, retry, undo, usage, title, model]`; `help` and `whoami` are always allowed upstream.

Not rendering `NTFY_TOPIC` on the pipeline LAB stage ends today's anonymous 403s there.

## Approval prompt (upstream entity, for reference)

`session_key`, `command`, `description`, deadline (`approvals.timeout` = 900 s, spec FR-004),
choices `once | session | always | deny` (research R-014):

- `/approve` (or a bare `yes`/`ok`/👍) = `once`.
- `/approve session` = the flagged *pattern* is approved for the rest of the conversation; other
  flagged commands still prompt; `/new` or `/reset` clears it.
- `/approve always` (or a bare `always`/`remember`) = permanent and process-wide until the agent
  restarts (the read-only config makes the save fail). It also lets that pattern through cron and
  other unattended surfaces. It cannot be blocked by configuration; it is detected by
  `HermesPermanentApprovalGranted` and revoked by restarting `hermes_agent`.
- At most one prompt is pending per conversation: concurrent prompts queue behind upstream's
  authorization gate, and `/approve` resolves the oldest.

## Action command (P2), carried on `actions`

```text
<verb> <target> [<param>=<value> ...] exp=<unix> v=1
```

| Field | Rule |
|---|---|
| `verb` | In the allowlist: P2 starts with `silence` only |
| `target` | `silence`: an Alertmanager alert fingerprint (16 hex characters) that the relay saw fire within the last 24 h (in-memory map fingerprint → labels, last seen) |
| `dur` | `silence`: one of `1h`, `24h`, `morning` (until the next 07:00 Europe/Oslo, at most 24 h), matching the three buttons. Anything else is refused |
| `exp` | Unix seconds. Refused if in the past. The relay sets it to render time + 24 h |
| `v` | Grammar version |

States: `received → (refused: unknown verb | bad params | expired | duplicate | target unknown) |
executed → confirmed`. Every transition is logged (FR-009) and every terminal state is published
to `relay`.

## Gap notice

`{started_at, last_heartbeat_at}`. It is sent once per gateway start, at ntfy priority 2 (silent;
083 kept restarts silent).

## LAB scratch pair (spec FR-011)

| Topic | Writers | Readers |
|---|---|---|
| `hermes-lab-in` | `owner` | `hermes_lab`, `owner` |
| `hermes-lab` | `hermes_lab` | `owner` |

`hermes_lab` is rendered only on the LAB rig (`lab_inventory`) and has no access to any
production topic. The pipeline's LAB stage (production machine, `deploy_environment=lab`) renders
no ntfy topic at all, which disables the ntfy platform there (`required_env=["NTFY_TOPIC"]`). The text names the window
during which `hermes-in` messages were not received.

## Audit line (stdout to Loki)

`ntfy_audit event=<inbound|approve|deny|slash_refused> topic=<t> msg_id=<id> text="<first 80 chars>"`
