# hermes-agent's ntfy stream subscription gets `403 Forbidden` about every 3 minutes

**Status**: **Superseded by [`095`](./095-ntfy-two-way.md)**. The agent's token gets read access to its inbound topic `hermes-in`, which removes the cause. The fix ships with 095's PROD rollout; the 7-day zero-403 check (095 SC-004, T061) closes it for good.
**Impact**: none observed yet (the agent evidently reconnects), but it is a live defect that
would otherwise have gone unnoticed forever — it only surfaced because spec 092's log sampling
looked at hermes_agent's output directly.

## What was measured

A 72-hour sample of `hermes_agent` container output on 2026-10-24 (research R8, spec 092):

- 2,848 total lines, **1,386 matching an error/warning pattern** — overwhelmingly one line
  repeated:

  ```
  WARNING ... [Ntfy] Stream error: Client error '403 Forbidden' for url '...'
  ```

- **1,359 occurrences in 72 h** — about once every 3 minutes, around the clock.
- The spec 092 per-service log rule for hermes (`HermesErrorLogs`) deliberately does **not**
  match this: it filters on `ERROR`/`CRITICAL`, and this line is `WARNING`. That exclusion was a
  conscious design choice in 092 (research R8), not an oversight — but it means this defect has
  no alert of its own and would otherwise sit in the logs unnoticed.

## Likely cause

The agent holds a long-lived subscription to its own ntfy topic to receive push notifications or
commands. A `403` on that stream points at either:

- the agent's ntfy auth token being wrong, expired, or lacking read access to the topic, or
- an ACL/topic-permission mismatch introduced by spec `083` (hermes-agent runtime), which is
  where this subscription was wired up.

## How to verify

1. Confirm the subscription still gets refused:
   `docker logs --since 10m hermes_agent | grep -c "403 Forbidden"` (expect several).
2. Identify the topic and token in use from the agent's config/environment
   (`083`'s ntfy integration).
3. Check that topic's ACL on the ntfy server side (`082`, `083`) against the token's permissions.
4. Try the same subscription manually with `curl` using the agent's token against the topic to
   confirm the 403 reproduces outside the agent.

## Suggested fix

Correct the token or ACL for the agent's ntfy topic (spec 083), then confirm the warning stops
appearing in `hermes_agent`'s output.
