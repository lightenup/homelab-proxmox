# Contract: publishing to the owner's phone

This is the interface this feature offers every sender in the estate. `083` is the first consumer
after Alertmanager.

## Endpoint

`POST https://ntfy.hus-sky.no/<topic>`. It is reachable from the LAN and the tailnet only.

## Authentication

`Authorization: Bearer <publisher token>`. Tokens come from vault (`ntfy_<publisher>_token`) and are
never placed in URLs, logs or source control. Do not use `?auth=` (it puts the credential in proxy
access logs).

## Request

The body is the plain-text message. Optional headers are `Title`, `Priority` (`1`–`5`, or
`min`/`low`/`default`/`high`/`urgent`), `Tags` and `Click`. Or POST a JSON body with
`?template=<name>`, for a template that exists in `template-dir`.

## Responses a publisher must handle

| Status | Meaning |
|---|---|
| `200` | Accepted and cached for `cache-duration` (72 h) |
| `401` / `403` | Wrong or missing token, or the token has no write access to this topic |
| `413` | Body over `message-size-limit` (32 KB) |
| `429` | Rate limited (ntfy per-visitor defaults) |
| connection error / `502` | ntfy or Caddy down. The publisher must not treat this as delivered |

## Guarantees and non-guarantees

- Delivered to the phone if it connects within 72 h. Older messages are lost.
- At-most-once from the phone's point of view. A publisher that retries after a timeout can cause
  a duplicate.
- Publishing is **not** a substitute for alerting. A sender whose silence matters must also
  have a monitoring signal (`083` owns its scheduler heartbeat).

## Onboarding a new publisher

1. Add an account, its topic and a `write-only` ACL to `ntfy_users` (data-model). The topic name
   must be new.
2. Add `ntfy_<name>_token` and `ntfy_<name>_password_hash` to vault.
3. Deploy ntfy. The owner's `*` read grant already covers the new topic. Subscribe to it in the app.
4. Extend the SC-002 check matrix with the new row and column.
