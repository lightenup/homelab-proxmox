# ntfy 4-Week Trial Report (SC-006)

**Trial start**: 2026-10-17 (T035 passed: 3 synthetic alerts plus resolutions delivered on both
Pushover and ntfy)

**Trial end**: 2026-11-14

**Purpose**: Compare ntfy delivery against Pushover over a real alerting window before any
decision to drop Pushover. The comparison is like-for-like: the same alert text reaches both
channels (research R-003), so differences in timing or reliability are attributable to the
channel, not the content.

## Delivery log

| Alert | Fired at (UTC) | Pushover at (UTC) | ntfy at (UTC) | Missed / late / duplicate |
|---|---|---|---|---|
| | | | | |

## Notes

- "Late" = ntfy delivery more than 60 s after Pushover for the same alert.
- "Duplicate" = the same alert arrived more than once on the phone (at-most-once is the
  guarantee; a publisher retry after a timeout can cause one — see contracts/publisher-interface.md).
- "Missed" = the alert reached Pushover but not ntfy within the trial window.

## Verdict

_(to be written at the end of the window: keep both, drop Pushover, or other)_
