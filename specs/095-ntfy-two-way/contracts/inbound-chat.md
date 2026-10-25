# Contract: inbound chat on `hermes-in` (095, slice 1)

## Message in

- Published by the ntfy app (message bar) with the `owner` account to
  `https://ntfy.hus-sky.no/hermes-in`.
- The body is plain text. Title, tags and priority are ignored by the agent; the title is
  publisher-controlled and is never used for authorisation.
- Leading `/` = slash command, typed in the ntfy app's message bar. Allowed on ntfy (spec FR-014):
  `approve`, `deny`, `new`, `reset`, `stop`, `status`, `compress`, `retry`, `undo`, `usage`,
  `title`, `model`, plus upstream's always-allowed `help` and `whoami`. `/help` lists exactly this
  set (upstream filters the catalog by the gating policy). Anything else is refused with a short
  reply and an audit line `event=slash_refused`.
- While a prompt is pending, bare words also answer it (research R-014): `yes|ok|okay|confirm|y|👍`
  = `/approve`, `no|deny|reject|cancel|n|👎` = `/deny`, `session` = `/approve session`,
  `always|remember` = `/approve always`. With no prompt pending they are ordinary chat.

## Agent behaviour

| Input | Result |
|---|---|
| Free text | One conversational turn in the `hermes-in` session. Reply on `hermes` |
| Flagged command reached | Text prompt on `hermes`: command, reason, scope of each choice, deadline (900 s) |
| Second flagged command while a prompt is pending | Withheld until the first prompt is resolved (R-014) |
| `/approve` while a prompt is pending | Runs once; confirmation on `hermes` |
| `/approve session` | Runs, and later commands with the same pattern run unprompted until `/new` or `/reset` |
| `/approve always` | Runs; pattern approved process-wide until agent restart; `HermesPermanentApprovalGranted` fires (R-014) |
| `/deny`, or no answer before the deadline | Does not run; outcome on `hermes` |
| `/compress`, `/retry`, `/undo`, `/usage`, `/title`, `/model` | Upstream behaviour, conversation-scoped (FR-014) |
| `/yolo`, `/update`, others | Refused (R-002, FR-014) |
| Message published while the agent is offline | Never processed (no `since=`) |

## Messages out (on `hermes`)

- Replies are Markdown (`NTFY_MARKDOWN=true`). The adapter cuts any single publish at 4096
  characters with **no** visible marker (`adapter.py:280-284`); the gateway's
  `max_message_length=4096` is expected to split long replies first. The LAB gate (T008) verifies
  which happens; spec US1 AS-4 needs a split or a visible cut.
- Gap notice after every gateway start (R-007), at ntfy priority 2 (silent).
- Unchanged: cron job reports and failure notices.

## Audit (stdout → Loki)

One line per inbound message, approval decision and refused slash command:
see [data-model.md § Audit line](../data-model.md).
