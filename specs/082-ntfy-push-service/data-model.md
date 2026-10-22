# Data Model: ntfy push service (082)

There is no application data model. The "entities" are configuration objects declared in Ansible
and applied to ntfy on every deploy. The only runtime state is the message cache, which is
disposable (FR-014).

## Account

| Field | Values | Source |
|---|---|---|
| `name` | `owner`, `alertmanager`, `hermes`, `pve_backup` (`089`) | `ntfy_users` in role defaults |
| `role` | `user` (all accounts; no `admin`) | role defaults |
| `password_hash` | bcrypt, cost ≥ 10 (validated by ntfy at startup) | vault `ntfy_<name>_password_hash` |
| `token` | `tk_` + 29 chars, one per account | vault `ntfy_<name>_token` |

**Rules**
- Exactly one token per account. Tokens are never shared between accounts (FR-007).
- Publisher accounts (`alertmanager`, `hermes`, `pve_backup`) authenticate by token only. ntfy rejects an
  `auth-users` line without a valid bcrypt hash (`parseUsers` → `ValidPasswordHash`). Each
  publisher therefore gets a vault-stored hash of a random password that is discarded at
  generation. Generating the hash at render time is rejected: a fresh salt on every deploy changes
  `server.yml` and restarts the service each time.
- No account has role `admin`. With `admin`, a leaked publisher token could read every topic.
  ntfy also refuses ACL entries for non-`user` roles.

## Topic

| Topic | Publisher (write-only) | Subscriber (read-only) |
|---|---|---|
| `alerts` | `alertmanager` | `owner` |
| `hermes` | `hermes` (`083`) | `owner` |
| `pve-backup` | `pve_backup` (`089`) | `owner` |

**Rules**
- A topic has exactly one publisher. A new sending system gets a new topic, a new account and a
  new token (spec, Key Entities).
- Topic names are literal. No wildcard grants to publishers.

## Access entry (ACL)

Derived from the two tables above and rendered as `auth-access` lines:

| Account | Pattern | Permission |
|---|---|---|
| `owner` | `*` | `read-only` |
| `alertmanager` | `alerts` | `write-only` |
| `hermes` | `hermes` | `write-only` |
| `pve_backup` | `pve-backup` | `write-only` |

Everything not listed falls through to `auth-default-access: deny-all`. Anonymous access gets
`deny-all` on every topic.

**The access matrix the SC-002 check asserts** (✓ = allowed, everything else must be refused with
401/403):

| Credential ↓ / action → | read `alerts` | read `hermes` | read `pve-backup` | write `alerts` | write `hermes` | write `pve-backup` | write `other` |
|---|---|---|---|---|---|---|---|
| none | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| `owner` token | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ |
| `alertmanager` token | ✗ | ✗ | ✗ | ✓ | ✗ | ✗ | ✗ |
| `hermes` token | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ | ✗ |
| `pve_backup` token | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ |

## Message (runtime, disposable)

| Field | Notes |
|---|---|
| topic, title, message, priority (1–5), time | priority from the publisher, or, for `alerts`, computed by the template (research R-003) |
| retention | `cache-duration: 72h` (FR-013), then deleted |

**State transitions** (as seen by the phone): published → cached → delivered (phone connected), or
published → cached → expired (phone absent longer than 72 h; lost by design).

## Alert → notification mapping

| Alertmanager payload | Title | Priority |
|---|---|---|
| `status=firing`, severity `critical` | `[CRITICAL] <alertname>` | 5 |
| `status=firing`, severity `warning` or none | `[WARNING] <alertname>` | 3 |
| `status=firing`, severity `info` | `[INFO] <alertname>` | 1 |
| `status=resolved`, severity `info` | `[RESOLVED] <alertname>` | 1 |
| `status=resolved`, other | `[RESOLVED] <alertname>` | 3 |

Message body: one `annotations.summary` line per alert, at most 10 alerts (`max_alerts`). The
title gets a `(+N more)` suffix when `truncatedAlerts > 0`.
