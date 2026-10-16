# Contract: ntfy server configuration

Rendered by the `ntfy` role to `/opt/ntfy/server.yml` (mode `0600`, root), bind-mounted read-only at
`/etc/ntfy/server.yml`. Every key listed here is required. Keys under **Forbidden** must never
appear, and preflight fails the deploy if they do (FR-004).

## Required keys

| Key | Value | Requirement / research |
|---|---|---|
| `base-url` | `https://ntfy.{{ caddy_base_domain }}` | FR-003 |
| `listen-http` | `:80` | Caddy upstream `{{ ntfy_ip }}:{{ ntfy_port }}` |
| `behind-proxy` | `true` | Per-visitor rate limiting sees the client, not Caddy |
| `metrics-listen-http` | `:9090` | FR-011, R-006 (off the proxied name) |
| `cache-file` | `/var/lib/ntfy/cache.db` | R-008 |
| `cache-duration` | `"72h"` (inline; one consumer) | FR-013 |
| `auth-file` | `/var/lib/ntfy/user.db` | R-002 (disposable, rebuilt from config) |
| `auth-default-access` | `deny-all` | FR-005 |
| `auth-users` | one line per account: `name:hash:user` | FR-006, data-model § Account |
| `auth-access` | lines from data-model § Access entry | FR-006 |
| `auth-tokens` | one line per account: `name:token:<label>` | FR-007 |
| `template-dir` | `/etc/ntfy/templates` | R-003 |
| `message-size-limit` | `"32k"` | R-004 |

`/var/lib/ntfy` is bind-mounted from `/opt/ntfy-data` on the LXC's local disk. `/etc/ntfy/templates`
is bind-mounted read-only from `/opt/ntfy/templates`.

## Left at upstream defaults (deliberately)

| Key | Default | Why it stays |
|---|---|---|
| `web-root` | `/` | The front-page probe of `https://ntfy.hus-sky.no/` needs a 200 (R-007) |
| `enable-signup`, `enable-login`, `require-login` | `false` | No self-service accounts. The phone uses basic auth on subscribe, which needs none of these |
| `attachment-cache-dir` | unset | Attachments disabled |

## Forbidden

`upstream-base-url`, `upstream-access-token`, `firebase-key-file`, `web-push-public-key`,
`web-push-private-key`, `smtp-sender-*`, `twilio-*`. Each of these sends message content or
metadata outside the estate (FR-004, R-009).

## Compose shape (no secrets in it)

One service, `ntfy`, image `binwiederhier/ntfy:{{ ntfy_version }}`, `command: serve`. Ports
`{{ ntfy_port }}:80` and `{{ ntfy_metrics_port }}:9090`, both bound to the LXC address. Three
bind mounts (config, templates, data) and `restart: unless-stopped`. Healthcheck:
`wget -q --spider http://localhost/v1/health`.
