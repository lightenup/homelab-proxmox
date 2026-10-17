# Failure-independence drill (T040, SC-003, research R-005, quickstart § 5)

Date: 2026-10-17. ntfy outage simulated by shutting down `ntfy-lxc` in the Proxmox UI.
Alerts injected via the Alertmanager v2 API (equivalent to `amtool alert add`). Times local (CEST).

| Step | Fired | Pushover | ntfy |
|---|---|---|---|
| Baseline (ntfy up): `TestNtfyBaseline` critical | 13:05:23 | 13:05:54 (31 s) | arrived |
| ntfy down confirmed (Caddy 502, direct no answer) | — | — | — |
| Outage: `TestNtfyOutage` critical | 13:13:36 | 13:14:07 (31 s) | not deliverable (expected) |
| `NtfyDown` fired (probe 0 for 5 min) | 13:19:02 | 13:19:33 | not deliverable (expected) |
| Front-page card | — | — | red while down |
| `ntfy-lxc` started; health 200, both probes 1 by 13:23 | — | — | — |
| `NtfyDown` resolved | — | arrived | arrived |
| Delayed ntfy copies (Outage, NtfyDown, resolution) | — | — | arrived after restart via Alertmanager retries |

**Result: PASS.** Pushover latency was identical (31 s) with ntfy down and up, so a failing
ntfy webhook in the shared receiver does not delay Pushover. The R-005 fallback (a separate
receiver on a `continue: true` route) is not needed.
