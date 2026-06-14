# Phase 1 Data Model: Service Landing Page at hus-sky.no

This feature has no database. The "data model" is the shape of the single declarative source of
truth (`caddy_services`) and the derived/runtime values computed from it. Each entity below maps to
a Key Entity in the spec.

## Entity: Service Definition — one `caddy_services` entry

The single source of truth for one service. A list of these lives in
`ansible/group_vars/services/vars.yml`.

| Field | Type | Required | Default | Drives | Notes |
|-------|------|----------|---------|--------|-------|
| `host` | string | yes | — | subdomain label, route, probe target, card link, join key | e.g. `immich` → `immich.hus-sky.no` |
| `ip` | string — Jinja ref to central var (`"{{ <svc>_ip }}"`) resolving to an IPv4 | yes | — | Caddy `reverse_proxy` upstream host | references the existing central IP var, not a duplicated literal |
| `port` | string — Jinja ref to central var (`"{{ <svc>_port }}"`) resolving to a port | yes | — | Caddy `reverse_proxy` upstream port | references the existing central port var |
| `title` | string | no | `host` (capitalized) | card heading | fallback prevents broken card (edge case) |
| `desc` | string | no | `""` | card description line | omitted cleanly if empty |
| `enabled` | bool | no | `true` | route + probe + card inclusion | `false` ⇒ omitted from all three (Home Assistant disabled; AdGuard unused) |
| `user_facing` | bool | no | `true` | card inclusion + probe-eligibility | `false` ⇒ internal endpoint, no card, not a user health probe (e.g. metrics) |

### Validation rules (derived from FR-002, FR-006, edge cases)

- `host`, `ip`, `port` MUST be present for an `enabled` entry. (A disabled entry MAY be a stub.)
- `host` MUST be unique within the list (it is the join key; duplicates would collide on
  `instance="https://<host>.hus-sky.no"`).
- `title`/`desc` absent ⇒ card still renders (fallback to `host`); MUST NOT error.
- An entry with `enabled: false` MUST NOT appear in the Caddy route, the blackbox targets, or the
  landing page — consistently (FR-006, SC-003).
- An entry with `user_facing: false` MUST NOT appear on the landing page and MUST NOT be added as a
  user-service blackbox target, but MAY still be routed by Caddy if `enabled` (internal route).

### Inclusion matrix (how the two flags gate the three outputs)

| `enabled` | `user_facing` | Caddy route | Blackbox target | Landing card |
|-----------|---------------|-------------|-----------------|--------------|
| true | true | yes | yes | yes |
| true | false | yes | no | no |
| false | * | no | no | no |

## Entity: Landing Page Asset (generated)

- **Identity**: `index.html` (+ optional `style.css`) under the apex web root
  (`/var/www/hus-sky`, exact path = `caddy_landing_root` default).
- **Generation**: rendered from `index.html.j2` over the *card-eligible* subset
  (`enabled and user_facing`) of `caddy_services` at every deploy. Never hand-edited.
- **Per-card output**: heading (`title`|`host`), description (`desc`), anchor to
  `https://{{ host }}.{{ caddy_base_domain }}`, and a `data-probe` attribute equal to that same URL
  plus a default health state `unknown`.

## Entity: Derived blackbox target list

- **Identity**: `blackbox_https_targets` in `group_vars/monitoring/vars.yml`.
- **Generation**: `https://{{ item.host }}.{{ caddy_base_domain }}` for each `caddy_services` entry
  with `enabled and user_facing`. Consumed unchanged by `prometheus.yml.j2`.
- **Invariant**: the target URL string equals the card `data-probe` and the metric `instance` label.

## Entity: Health Indicator State (runtime, client-side)

- **Values**: `up` | `down` | `unknown`.
- **Source**: `probe_success{instance="<url>"}` from `/api/status`. `1` ⇒ `up`, `0` ⇒ `down`,
  metric absent / fetch failed ⇒ `unknown`.
- **Lifecycle**: initial = `unknown` (server-rendered); updated on each successful `/api/status`
  poll (~30s); reverts to / stays `unknown` on fetch error (FR-010).
- **Join**: card `data-probe` URL ⟷ metric `instance` label (exact string match).

## Relationships

```text
caddy_services entry ──┬─> service.caddy.j2 loop ──> <host>.caddy site block (route)
   (single source)     ├─> index.html.j2 loop  ──> landing card (link + data-probe)
                       └─> blackbox_https_targets ──> prometheus blackbox-https job ──> probe_success
                                                                                          │
landing card.data-probe ◀────────── join on full URL ──────────── probe_success.instance ┘
```
