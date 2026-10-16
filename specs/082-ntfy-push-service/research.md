# Research: ntfy push service (082)

**Date**: 2026-10-16 | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

Upstream facts below were read from the ntfy **v2.28.0** source tree
(`cmd/serve.go`, `server/server.go`, `server/config.go`, `server/server.yml`,
`server/templates/alertmanager.yml`) and the release notes. Statements marked *verify on LAB* are
not settled by source reading alone and become tasks.

---

## R-001 — Image and version pin

- **Decision**: `binwiederhier/ntfy:v2.28.0`, pinned as `ntfy_version: "v2.28.0"` in the versions
  block of `ansible/group_vars/services/vars.yml` (FR-002).
- **Rationale**: Released 2026-08-27. It is the newest release older than two weeks (v2.29.0 came
  out 2026-10-07, v2.30.0 on 2026-10-12, v2.31.0 on 2026-10-15). It includes everything this
  feature relies on: declarative users, ACLs and tokens, plus template files (v2.14.0); a
  templated `priority` field (v2.17.0); and hardening of template execution against CPU and memory
  DoS (v2.26.0, v2.27.0). An amd64 image for the tag was confirmed on Docker Hub.
- **Alternatives**: `latest` was rejected because the estate pins every image. v2.31.0 was rejected
  as too new to have a track record.

## R-002 — Access control is fully declarative (FR-005, FR-006, FR-007, FR-014)

- **Decision**: Use `auth-default-access: deny-all`. Users, ACLs and tokens are declared in
  `server.yml` through `auth-users`, `auth-access` and `auth-tokens`, rendered from vault on every
  deploy. `auth-file` lives on local disk and is treated as disposable.
- **Upstream facts**:
  - `auth-users` entries are `"<name>:<bcrypt-hash>:<role>"` (`user` or `admin`), created or
    updated at startup.
  - `auth-access` entries are `"<name>:<topic-pattern>:<read-write|read-only|write-only|deny>"`.
    Entries removed from config are deleted from the database, so config is authoritative.
  - `auth-tokens` entries are `"<name>:<token>[:<label>]"`. A token is `tk_` plus 29 characters (32
    in total). Generate one with `ntfy token generate`, and a password hash with `ntfy user hash`.
  - The `auth-*` settings require `auth-file` to be set.
- **Rationale**: Everything access-related comes from config, so a rebuild needs no manual
  `ntfy user add` (SC-004). That is also why the service needs no backup role (FR-014). It
  mirrors the reasoning for `market-model`.
- **Alternatives**: Imperative `ntfy user`/`ntfy access` calls from Ansible were rejected because
  they are not idempotent without wrappers, and they leave drift when entries are removed.

## R-003 — Alert rendering and severity → priority: a custom template, not the built-in one

The backlog proposed the pre-defined `?template=alertmanager` plus a `priority` query parameter,
with one receiver per severity, and flagged as open question 1 whether the two combine.

**Finding**: The built-in `server/templates/alertmanager.yml` defines only `title` and `message`,
with no `priority`. Since v2.17.0 a template file may also define `priority` as a Go template.
Templates are loaded from `template-dir` (default `/etc/ntfy/templates`) and selected with
`?template=<name>`.

- **Decision**: Ship one custom template, `homelab-alertmanager.yml`, mounted into
  `template-dir`. It computes the priority from the payload itself:

  | Payload | ntfy priority | Pushover today |
  |---|---|---|
  | `commonLabels.severity == "info"` (firing or resolved) | 1 (min — no sound or vibration) | −1 |
  | `status == "resolved"` (non-info) | 3 (default) | 0 |
  | `critical`, firing | 5 (urgent) | 2 |
  | anything else (`warning`, or no severity label) | 3 (default) | 0 |

  The title mirrors Pushover's (`[CRITICAL] <alertname>` / `[RESOLVED] <alertname>`), and the
  message is one summary line per alert. The same text on both channels makes the SC-006
  comparison like for like.
- **Consequence**: One webhook definition is enough. It is added to each of the three existing
  Pushover receivers (`pushover-critical`, `pushover-warning`, `pushover-info`), so **no route
  changes** and no `continue: true` are needed. Open question 1 is closed without relying on
  query-parameter precedence.
- **Rationale**: This is the only option that matches Pushover's "critical firing is urgent,
  critical resolved is not". A static `?priority=5` per receiver would also make every critical
  *resolution* urgent.
- **Alternatives**: (a) The built-in template plus `?priority=` per receiver, rejected for the
  reason above, and it needs three webhook URLs. (b) Inline templating (`?tpl=yes&t=…&m=…&p=…`),
  rejected because a Go template in a URL is unreadable and has to be escaped twice, through both
  Jinja and Alertmanager.
- *verify on LAB*: render all four rows of the table with a synthetic payload (quickstart § 3).

## R-004 — Template body size limit

**Finding**: `handlePublishWithoutResponse` peeks the request body with
`util.Peek(r.Body, MessageSizeLimit)`, and `MessageSizeLimit` defaults to 4096 bytes. That buffer
is what a template is evaluated against. Alertmanager webhook payloads carry every label and
annotation of every alert in the group, plus the group and common labels. This estate's
`description` annotations run to several hundred characters, so a group of two or three alerts
can exceed 4 KB.

- **Decision**: (1) `message-size-limit: "32k"` on the server. (2) `max_alerts: 10` on the
  Alertmanager webhook config, which truncates a large group and sets `truncatedAlerts`. (3) The
  custom template emits only titles and summaries, so the rendered message stays well under 4 KB.
- **Trade-off**: ntfy logs a warning when the limit is above 4K, because clients are "largely
  untested" with large *messages*. Only the *input* is large here; the rendered output stays small.
- *verify on LAB*: a group of 10 alerts with long descriptions renders and arrives
  (quickstart § 3).
- **Alternatives**: `max_alerts: 1` alone was rejected because it hides grouped instances, and one
  long description can still approach 4 KB.

## R-005 — Alertmanager → ntfy path and independence from Pushover (FR-008, edge case "ntfy down")

- **Decision**: Webhook URL `https://ntfy.{{ caddy_base_domain }}/alerts?template=homelab-alertmanager`,
  authenticated with `http_config.authorization` (type `Bearer`) using the `alertmanager` token, and
  with `send_resolved: true`. The webhook is gated by a new `ntfy_enabled` flag in
  `group_vars/monitoring/vars.yml`, which mirrors `pushover_enabled`. With the flag off, the
  rendered `alertmanager.yml` is byte-identical to today's.
- **Why through Caddy rather than `http://ntfy_ip`**: The token travels over TLS. The same URL is
  used by every publisher (`083` included). The blackbox liveness probe already exercises this
  exact path.
- **Independence**: Alertmanager's notify pipeline fans out to each integration of a receiver
  separately, each with its own retry stage, so a failing webhook should not delay the Pushover
  integration alongside it. This estate has a recorded history of a failing **email** receiver
  stalling Pushover (comment in `alertmanager.yml.j2`, no root cause on file), so this is *not
  assumed*. It is a **drill**: stop ntfy, fire a critical test alert, and time Pushover delivery
  against its usual time (quickstart § 5). If the drill shows a delay, the fallback is to move the
  webhook to a separate receiver on a `continue: true` sibling route.
- **Self-alerting**: `NtfyDown` (critical) is routed like every other critical alert and reaches
  Pushover. Its copy to ntfy fails and retries, which is harmless. ntfy is never the only path for
  news of its own outage.

## R-006 — Metrics (FR-011)

- **Decision**: `metrics-listen-http: ":9090"`. Metrics are served on a dedicated listener that is
  published only on the LXC's LAN address. Prometheus scrapes `ntfy_ip:9090` through the existing
  `monitoring_contract.scrape_targets` mechanism (job `ntfy`).
- **Rationale**: `enable-metrics: true` on the main listener would expose `/metrics` through Caddy
  at `ntfy.hus-sky.no/metrics`. Upstream calls that data potentially sensitive, and ntfy has no
  authentication on it. A separate listener keeps it off the proxied name.
- No Grafana dashboard is planned (constitution IV: no consumer yet). The scrape exists so that a
  dashboard or rule can be added later without a redeploy.

## R-007 — Liveness and the front-page card (FR-011, FR-012)

- **Liveness alert**: The blackbox `http_2xx` probe of `https://ntfy.{{ caddy_base_domain }}/v1/health`
  (job `ntfy-health`, distinct from the metrics scrape job `ntfy`) feeds the `NtfyDown` rule (critical, `for: 5m`), which follows the
  `EuroOfficeDown`/`HermesDown` pattern. `/v1/health` is unauthenticated and does not depend on
  ACLs.
- **Front-page card**: No new mechanism. A `caddy_services` entry with `user_facing: true`
  produces the vhost, the card, and (via `blackbox_https_targets` in `group_vars/monitoring`) the
  `https://ntfy.hus-sky.no` root probe whose `instance` the card reads from `/api/status`.
- **Consequence for `web-root`**: Keep the default `/`. With `web-root: disable` the root path
  returns 404, which would turn the card permanently red. The web app is harmless here: with
  `deny-all` and `enable-login: false` it shows nothing.

## R-008 — Retention, storage and the "no backup" claim (FR-013, FR-014)

- **Decision**: `cache-file` (SQLite) and `auth-file` both live under `/opt/ntfy-data` on the LXC's
  local disk, with `cache-duration: "72h"` (default 12h). There is no `attachment-cache-dir`, so
  attachments stay disabled, and no NFS mount.
- **Rationale**: 72 h covers a weekend off the tailnet. The cache only bridges a phone being away,
  and losing it on a rebuild is acceptable (spec edge case). Everything else is re-applied from
  config, so no backup role is needed.

## R-009 — Nothing leaves the estate (FR-004)

- **Finding**: `upstream-base-url` defaults to `""` in v2.28.0 (`cmd/serve.go`). The setting is
  only needed for iOS through ntfy.sh. `firebase-key-file` defaults to none. Web push needs
  explicitly generated VAPID keys.
- **Decision**: Set none of these. The rendered `server.yml` is checked by a preflight assertion
  that fails the deploy if `upstream-base-url` or `firebase-key-file` appears, which makes FR-004 a
  tested invariant rather than a default.
- The Android app uses its own persistent connection to a self-hosted server ("instant delivery")
  in both the Play and F-Droid builds, so it does not need Firebase for a non-ntfy.sh server.

## R-010 — Placement, addressing and inventory (FR-001, FR-016)

- **Address**: `192.168.1.222`, the next free address after `hermes` (`.221`). Nothing else in the
  tree uses it. `081` (externalise topology) has not started, so the address goes in the existing
  places: `ntfy_ip` in `group_vars/services/vars.yml`, `service_ips.ntfy` in both tfvars templates,
  and `ansible_host` in `inventories/prod/hosts.yml`.
- **Inventory**: The prod inventory entry is **required**, not cosmetic. `prometheus.yml.j2`
  builds scrape targets from `hostvars[host].ansible_host`, and backlog `066` documents
  `market-model`/`eurooffice` losing all monitoring through exactly this omission.
- **Terraform**: A per-service root `terraform/services/ntfy/` (`main.tf`, `outputs.tf`), following
  `hermes`, which is the latest pattern. `terraform/main.tf` is not touched.
- **Sizing**: 1 core, 512 MB, 8 GB disk. ntfy is a single Go binary, and its SQLite cache at this
  volume is kilobytes.
- **Pipeline parity** (constitution V): `ntfy` is added to the dropdowns of `lxc-deploy-lab.yml`,
  `lxc-promote-lab.yml` and `lxc-promote-prod.yml`, and to `scripts/lab/service-scope-allowlist.json`
  (`module.ntfy_lxc`), in the same PR.

## R-011 — Configuration delivery: `server.yml`, not environment variables

- **Decision**: Render `/opt/ntfy/server.yml` from Jinja and bind-mount it read-only at
  `/etc/ntfy/server.yml`. The compose file carries no secrets.
- **Rationale**: bcrypt hashes contain `$`, which Docker Compose interpolates in `environment:`
  values. A mounted YAML file avoids escaping and keeps secrets out of `docker inspect` output.
  Mode `0600`, owned by root.

## R-012 — Secrets (FR-007, constitution II)

All six secrets go in `ansible/group_vars/services/vault.yml`. The `monitoring` host is in the
`services` group, so one definition serves both the ntfy LXC and Alertmanager.

| Vault variable | Format | Consumers |
|---|---|---|
| `ntfy_owner_password_hash` | bcrypt (`ntfy user hash`) | ntfy `auth-users` |
| `ntfy_owner_token` | `tk_` + 29 chars | ntfy `auth-tokens`, used by the scripted ACL check (SC-002) for the read checks |
| `ntfy_alertmanager_token` | `tk_` + 29 chars | ntfy `auth-tokens`, Alertmanager webhook |
| `ntfy_hermes_token` | `tk_` + 29 chars | ntfy `auth-tokens`, and `083` FR-011 |
| `ntfy_alertmanager_password_hash` | bcrypt of a random, discarded password | ntfy `auth-users` (required syntax only) |
| `ntfy_hermes_password_hash` | bcrypt of a random, discarded password | ntfy `auth-users` (required syntax only) |

The last two exist only because ntfy's `parseUsers` rejects an `auth-users` line without a valid
bcrypt hash (cost ≥ 10). Keeping them in vault rather than generating them at deploy time keeps the
rendered `server.yml` stable, so a deploy with no changes does not restart the service.

The phone signs in with **username and password**. The plaintext password exists only in the
owner's password manager and is never in vault. Only its hash is stored there.

## R-013 — Phone reach (US-3)

No server-side work. The phone runs Tailscale as an always-on VPN and resolves `ntfy.hus-sky.no`
through the estate's DNS to `reverse_proxy_ip`. Reaching `reverse_proxy_ip:443` from the
tailnet is what every `hus-sky.no` service already requires, and `docs/tailscale-acl.example.json`
grants `192.168.1.0/24:*`. The live policy is not in the repo, so quickstart § 4 confirms the phone's
reach before any delivery test. The runbook covers app setup, the battery exemption, and checking the app's
"instant delivery" state.
