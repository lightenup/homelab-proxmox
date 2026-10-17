# Phone delivery drill (T037, SC-001, SC-005, quickstart § 4)

Phone: owner's Android, ntfy app subscribed to `alerts` and `hermes` on `https://ntfy.hus-sky.no`.

| # | Condition | Sent (UTC) | Arrived | Delta | Result |
|---|---|---|---|---|---|
| 0 | Initial subscribe: 8 cached T033 payloads delivered on first subscribe | 2026-10-17 | 2026-10-17 | — | PASS |
| A | Wi-Fi off, mobile data + Tailscale, app closed | 10:49:23 | 10:49:30 | 7 s | PASS |
| A2 | Same as A, repeat run | 10:55:49 | 10:55:56 | 7 s | PASS |
| B | Tailscale off, ~5 min gap, then reconnect | | | | |
| C | Overnight idle, app not opened | | | | |
| D | Each severity on mobile data (after T034/T035) | | | | |
