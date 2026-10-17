# Phone delivery drill (T037, SC-001, SC-005, quickstart § 4)

Phone: owner's Android, ntfy app subscribed to `alerts` and `hermes` on `https://ntfy.hus-sky.no`.

| # | Condition | Sent (UTC) | Arrived | Delta | Result |
|---|---|---|---|---|---|
| 0 | Initial subscribe: 8 cached T033 payloads delivered on first subscribe | 2026-10-17 | 2026-10-17 | — | PASS |
| A | Wi-Fi off, mobile data + Tailscale, app closed | 10:49:23 | 10:49:30 | 7 s | PASS |
| A2 | Same as A, repeat run | 10:55:49 | 10:55:56 | 7 s | PASS |
| B | Tailscale off, ~5 min gap, then reconnect (Tailscale on 11:02 UTC) | 10:56:32 | 11:02 | arrived on reconnect, < 1 min after Tailscale on | PASS |
| WS | WebSocket protocol enabled in app, mobile data, app closed | 11:26:47 | 11:26:54 | 7 s | PASS |
| C | Overnight idle, app not opened | — | — | — | Not run — accepted by owner 2026-10-17 |
| D | Each severity (T035 alerts, critical/warning/info + resolutions) | 10:20:24 | 10:20:54 | 30 s (Alertmanager group_wait) | PASS |
