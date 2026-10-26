# Contract: action buttons and the `actions` topic (095, slice 2)

## Button rendering (relay → `alerts`)

Each firing alert notification carries at most 3 action buttons, and its `Click` header is the
alert's Grafana URL, so tapping the notification opens the dashboard without using a button slot.
P2 set:

```text
broadcast, Silence 1h, intent=io.heckel.ntfy.SEND_MESSAGE,
  extras.base_url=https://ntfy.hus-sky.no, extras.topic=actions,
  extras.message=silence <fingerprint> dur=1h exp=<render time + 24h> v=1, clear=true
broadcast, Silence until 07:00, … dur=morning …
broadcast, Silence 24h, … dur=24h …
```

The notification contains **no credential**. The ntfy app publishes the press with its configured
`owner` account (research R-006; verified on device before P2 ships). Resolved notifications carry
no buttons.

The title, priority and message are the same as today's `homelab-alertmanager.yml` output (parity
test).

## Command grammar (on `actions`)

See [data-model.md § Action command](../data-model.md). The relay ignores the title and tags. The
body must parse completely, or the command is refused.

## Relay responses (relay → `relay` topic)

| Outcome | Message |
|---|---|
| executed | `Silenced <alertname> until HH:MM. Silence id <id>.` (also when the alert has just resolved) |
| already silenced | `<alertname> already silenced until HH:MM; nothing changed.` |
| expired | `Button expired (<age>); not executed.` |
| duplicate | Silent, logged only (the same message id seen again) |
| target unknown | `<alertname> has not fired in the last 24 h (or the relay restarted since); not silenced.` |
| refused | `Refused: <reason>.` (unknown verb, bad parameter) |
| error | `Failed: <reason>. Nothing changed.` |

Every outcome is also logged as one line on stdout (FR-009).

## Alertmanager wiring

The ntfy receiver URL changes from `https://ntfy…/alerts?template=…` to the relay's local webhook
(`http://action-relay:<port>/alertmanager`). The Pushover receivers are unchanged.
`send_resolved: true` is kept.
