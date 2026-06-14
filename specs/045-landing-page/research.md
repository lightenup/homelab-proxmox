# Phase 0 Research: Service Landing Page at hus-sky.no

All unknowns derive from existing repository config; no external research was required. Findings
below were obtained by reading the current `reverse_proxy` and `monitoring_stack` roles.

## R-001 — Where the single source of truth must live

**Decision**: Define `caddy_services` in `ansible/group_vars/services/vars.yml`.

**Rationale**: The list must be in variable scope for two roles that run on two different hosts —
`reverse_proxy` (host `reverse_proxy`, 192.168.1.211) and `monitoring_stack` (host `monitoring`,
192.168.1.214). Inspection of `ansible/inventories/prod/hosts.yml` shows the `monitoring` host is
itself a member of the `services` group. Therefore `group_vars/services/vars.yml` is automatically
in scope for the monitoring play as well — no `group_vars/all` placement and no cross-group
include is needed. This matches spec decision D-002.

**Alternatives considered**:
- `group_vars/all/vars.yml` — would work but widens scope unnecessarily (every host loads it) and
  buries a services concern in the global file. Rejected on Principle IV (least surprise / locality).
- A new `group_vars/all/caddy_services.yml` file — extra file for a single list; the existing
  `services/vars.yml` already holds the per-service `*_ip`/`*_port` vars this list supersedes, so
  co-locating is more coherent. Rejected (prefer modifying existing file).

## R-002 — Replacing six per-service `.caddy.j2` templates with one

**Decision**: One generic `service.caddy.j2` rendered with a `loop` over the enabled, user-facing
entries of `caddy_services`; delete the six per-service templates and their six template tasks.

**Rationale**: Direct diff of `immich/nextcloud/grafana/jellyfin/adguard.caddy.j2` shows they are
identical except for `host`, `ip`, and `port`; all five use the same three `header_up` lines.
`homeassistant.caddy.j2` differs only by an outer `{% if homeassistant_active %}` guard, which the
`enabled` flag now expresses generically. A single template with a loop therefore reproduces every
current site block byte-for-byte (modulo the variable substitution), satisfying D-008's "preserve
current routes, no service interruption" constraint. The loop has 5–6 items today, so it clears
the constitution's ">1 item" bar for justified templating (Principle IV).

**Alternatives considered**:
- Keep per-service templates, add only the landing page — rejected: leaves the third duplicated
  list in place, making the page a fourth copy (the exact anti-goal of US-3 / SC-004).
- Generate the whole `*.caddy` set into one file — rejected: the role currently imports
  `{{ caddy_conf_dir }}/*.caddy`; emitting one file per service via the loop keeps that glob import
  unchanged and makes per-service diffs legible.

## R-003 — Generating `blackbox_https_targets` from the same source

**Decision**: Replace the literal list in `group_vars/monitoring/vars.yml` with a Jinja expression
deriving `https://{{ item.host }}.{{ caddy_base_domain }}` for each `caddy_services` entry that is
`enabled` and probe-eligible (`user_facing`). `prometheus.yml.j2` already iterates
`blackbox_https_targets` and needs no change.

**Rationale**: `prometheus.yml.j2` (job `blackbox-https`) loops `blackbox_https_targets | default([])`
to emit probe targets; the consuming side is already list-shaped, so only the *definition* changes
from a hand-kept literal to a generated value. This removes the second duplicated subdomain list
(SC-004) while preserving the exact targets currently probed. `caddy_base_domain` (`hus-sky.no`) is
a `reverse_proxy` default; the monitoring side must reference the same domain — see R-006.

**Alternatives considered**:
- Compute targets inside `prometheus.yml.j2` directly from `caddy_services` — rejected: keeps the
  derivation where the var is consumed, but `blackbox_https_targets` is referenced by name elsewhere
  (alerts/dashboards may key on it); keeping the named var, now generated, is the smaller, safer change.

## R-004 — Pinning the health query so the browser can't run arbitrary PromQL

**Decision**: Apex `/api/status` is a Caddy `handle` that `rewrite`s to a fixed upstream URI
`/api/v1/query?query=probe_success` and `reverse_proxy`es to `{{ monitoring_ip }}:9090` (shared
`monitoring_ip` var; port `9090` inline since `prometheus_port` is out of the reverse_proxy role's scope).
The client-supplied query string is discarded by the rewrite.

**Rationale**: Same-origin (served from `hus-sky.no`) avoids CORS (D-004). Because Caddy replaces the
entire request URI before proxying, a client requesting `/api/status?query=<anything>` still reaches
Prometheus with `query=probe_success` only — the general query API is never exposed (FR-009, SC-007).
Prometheus' `/api/v1/query` is read-only by nature; no write path is reachable.

**Alternatives considered**:
- Expose Prometheus directly behind `/prometheus` — rejected: hands the browser the full query API
  (and admin endpoints), the explicit anti-goal of FR-009.
- A tiny server-side script to fetch/cache the metric — rejected on D-006/Principle IV: introduces a
  runtime component to monitor and keep alive; Caddy's `rewrite`+`reverse_proxy` needs none.

## R-005 — Q-001: blackbox probe interval and staleness window

**Finding**: The `blackbox-https` scrape job in `prometheus.yml.j2` sets `scrape_interval: 30s`
(literal, not the global default). `https_2xx` module timeout is `10s` (`blackbox.yml.j2`).

**Decision**: Accept as-is; no change. A stopped service is reflected as `probe_success 0` within
≤30s, then surfaces on the next page health poll. This meets SC-005 ("after the next probe cycle and
a page refresh"). The landing JS poll interval is set to ~30s to align (data-model / contract).

## R-006 — Q-002: `probe_success` label and the card→metric join key

**Finding**: In `prometheus.yml.j2` the `blackbox-https` job's `relabel_configs` copy
`__param_target` (the full `https://<host>.hus-sky.no` URL) into the `instance` label. So the metric
is `probe_success{instance="https://immich.hus-sky.no", job="blackbox-https"}`.

**Decision**: The JS join key is the **full target URL**. Each card carries a `data-probe` attribute
equal to `https://{{ host }}.{{ caddy_base_domain }}`, generated from the same `caddy_services` entry
that produced the blackbox target — so the card key and the metric `instance` are guaranteed equal
(FR-012). This resolves Q-002 with no config change.

**Cross-role domain reference**: Both the generated blackbox target (monitoring role) and the card
`data-probe` (reverse_proxy role) must use the identical base domain. `caddy_base_domain` is defined
in the `reverse_proxy` role defaults. Because the monitoring host shares the `services` group scope,
the safest single definition is to read the domain from one place; the generated `blackbox_https_targets`
expression will reference `caddy_base_domain`, which must be resolvable in the monitoring play. If it
is not already, promote `caddy_base_domain` to `group_vars/services/vars.yml` (alongside `caddy_services`)
so both roles resolve the same value. **Action for Phase 2 tasks**: confirm `caddy_base_domain` scope and
promote if needed.

## R-007 — Apex certificate and DNS

**Finding**: Caddy already issues per-subdomain certs via Domeneshop DNS-01. The apex `hus-sky.no` is
a distinct SAN; the same `acme_dns` global directive issues it (A-003). The shared `:443` listener
routes by SNI, so the apex block coexists with subdomain blocks — no port handling (D-005).

**Decision**: Add a `hus-sky.no { ... }` site block; rely on the existing global `acme_dns`. DNS:
`docs/network-layout.md` confirms DNS is **public-only** — a wildcard `*.hus-sky.no → 192.168.1.211`
at Domeneshop, with public DNS resolving to the LAN IP (split-horizon not used). The wildcard does
**not** cover the bare apex, so `hus-sky.no` needs its own **public DNS A record at Domeneshop**
→ 192.168.1.211, parallel to the wildcard. This is a one-time manual step in quickstart (FR-011);
DNS records at the registrar are not Ansible-managed in this repo. **AdGuard plays no role** — it is
unused in the current setup and serves no DNS; the earlier "AdGuard rewrite" idea was a wrong
assumption and has been removed.

## R-008 — Static page, graceful degradation

**Decision**: `index.html` is generated at deploy from `caddy_services` (cards rendered server-side as
plain HTML); a small inline/linked vanilla-JS snippet fetches `/api/status` once on load and every
~30s, setting each card's indicator from the returned `probe_success` vector. Missing/failed fetch
leaves cards in their default `unknown` state.

**Rationale**: No framework, no build step, nothing to keep running (D-006, Principle IV). Cards and
links exist without JS, so FR-010/SC-006 hold even with Prometheus down. Missing `title`/`desc` falls
back to the hostname (edge case "service with no description").

**Alternatives considered**: SSR framework / SPA — rejected outright (build tooling + runtime for a
~6-card page). Server-push/websocket health — rejected: polling a 30s-granularity metric needs no push.
