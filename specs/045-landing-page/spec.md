# Feature Specification: Service Landing Page at hus-sky.no

**Feature Branch**: `045-landing-page`
**Created**: 2026-06-13
**Status**: Draft
**Input**: User description: "A website that lists all the subdomains under hus-sky.no, announcing itself on hus-sky.no. Either dynamic (no updating when new subdomains are added by discovery) or driven by the Caddy config. Must be architecturally sound and take no shortcuts."

## Summary

Today there is no page at the apex domain `hus-sky.no` — only the per-service subdomains
(`immich.hus-sky.no`, `jellyfin.hus-sky.no`, …) resolve to anything. This feature adds a
single landing page at `https://hus-sky.no` that lists every user-facing service as a card,
links to it, and shows its live up/down health.

The list of services is **not** maintained by hand on the page. It is **generated** from a
single declarative source of truth — a `caddy_services` list in Ansible — which already (after
this feature) drives the per-service Caddy site blocks and the blackbox health-probe targets.
Adding a service to that one list makes its route, its health probe, and its landing-page card
all appear together, with no separate page edit. Live health reuses the existing Prometheus +
blackbox exporter stack (feature `042-monitoring-tier-c`); the page does **not** introduce a
new health-checking mechanism.

This is the "generated from a single source of truth" approach rather than runtime discovery
via the Caddy admin API: in this repository every subdomain is already declared through Ansible,
so build-time generation delivers the same zero-touch property without adding a runtime service.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Discover All Services from One Page (Priority: P1)

As a homelab user, I want to open `https://hus-sky.no` and see a list of every service I can
access, each as a clickable card, so that I don't have to remember each subdomain by hand.

**Why this priority**: This is the primary driver. Without it, users must memorize or bookmark
each `<service>.hus-sky.no` URL individually. The landing page is the feature's reason to exist.

**Independent Test**: Open `https://hus-sky.no` in a browser on the LAN. Verify a card appears
for each enabled, user-facing service (Immich, Jellyfin, Nextcloud, Grafana), each with a title,
description, and a working link to the correct `<service>.hus-sky.no` URL. Home Assistant (disabled) MUST NOT appear.

**Acceptance Scenarios**:

1. **Given** the reverse proxy is deployed, **When** a user navigates to `https://hus-sky.no`,
   **Then** the page loads over HTTPS with a valid Let's Encrypt certificate and no security
   warnings, and displays one card per enabled user-facing service.
2. **Given** the landing page is displayed, **When** the user clicks a service card, **Then**
   the browser navigates to that service's `https://<service>.hus-sky.no` URL.
3. **Given** a service is flagged `enabled: false` (e.g. Home Assistant) or `user_facing: false`
   (e.g. the metrics endpoint), **When** the page is rendered, **Then** no card is shown for it.

---

### User Story 2 - Live Service Health at a Glance (Priority: P2)

As a homelab user, I want each service card to show whether the service is currently up or down,
so that I can tell at a glance which services are healthy without opening each one.

**Why this priority**: A static link list is useful, but the live health indicator turns the
page into a lightweight status dashboard, reusing monitoring data the homelab already collects.
It is secondary to simply listing services (US-1), which must work even if health data is
unavailable.

**Independent Test**: With all services running, open `https://hus-sky.no` and verify each card
shows a green "up" indicator. Stop one service (or its backend), wait for the next blackbox
probe + page refresh, and verify that card's indicator turns red ("down"). Stop Prometheus and
verify cards degrade to an "unknown" state rather than breaking the page.

**Acceptance Scenarios**:

1. **Given** a service is passing its blackbox HTTPS probe, **When** the landing page loads or
   refreshes its health data, **Then** that service's card shows an "up" indicator.
2. **Given** a service is failing its blackbox HTTPS probe, **When** the landing page refreshes
   its health data, **Then** that service's card shows a "down" indicator.
3. **Given** Prometheus is unreachable, **When** the landing page loads, **Then** the page still
   renders all service cards and links (US-1 still works), and health indicators show "unknown"
   rather than producing an error or a blank page.

---

### User Story 3 - Single Source of Truth for Subdomains (Priority: P1)

As a homelab operator, I want to declare each service exactly once and have its reverse-proxy
route, its health probe, and its landing-page card all derive from that one declaration, so that
adding or removing a service never requires editing three places that can drift apart.

**Why this priority**: This is the architectural backbone of the feature and the reason it is
sound rather than a shortcut. Today the subdomain list exists in three hand-maintained forms
(per-service `.caddy` templates, per-service `*_ip`/`*_port` vars, and `blackbox_https_targets`).
Without consolidation, a landing page would become a fourth copy to keep in sync.

**Independent Test**: Add a new service entry to the `caddy_services` list and run the deploy.
Verify, without any other edit, that (a) a new Caddy site block routes the subdomain and (b) a new
blackbox target probes it; remove the entry and verify both disappear. (The third derived artifact —
a landing-page **card** — is delivered by US-1; the full three-way add/remove check, SC-003, is
verified once US-1 is in place. US-3 on its own is testable via the route + probe outputs.)

**Acceptance Scenarios**:

1. **Given** a service is added to the `caddy_services` list, **When** the reverse proxy and
   monitoring roles are deployed, **Then** the Caddy route, the blackbox probe target, and the
   landing-page card for that service are all generated from that single entry.
2. **Given** the `caddy_services` list is the source of truth, **When** the operator inspects
   the repository, **Then** there is no separate hand-maintained subdomain list on the landing
   page, in the blackbox target list, or in duplicated per-service Caddy templates.
3. **Given** a service entry sets `enabled: false`, **When** the roles are deployed, **Then**
   that service is excluded from the route, the probe targets, and the landing page consistently.

---

### Edge Cases

- **Apex certificate**: `hus-sky.no` (the bare apex) needs its own certificate via the same
  DNS-01 / Domeneshop flow already used for subdomains. There is no port conflict — Caddy routes
  by Host/SNI on the shared 443 listener, so the apex coexists with all subdomains. Port 80
  auto-redirects to HTTPS as it does for subdomains.
- **Health endpoint exposure**: The page's health data path must not expose the full Prometheus
  query API to the browser. The query must be pinned server-side so a client can only retrieve
  the fixed health metric, never arbitrary PromQL.
- **Apex DNS record**: The existing wildcard `*.hus-sky.no` does NOT cover the bare apex, so
  `hus-sky.no` itself needs a **public DNS A record at Domeneshop** → `192.168.1.211`, parallel to the
  existing wildcard. DNS is public-only (per `docs/network-layout.md`: public DNS resolves to the LAN
  IP; split-horizon not used). Both LAN and Tailscale clients resolve the apex via this public record.
- **Service with no description/title**: A `caddy_services` entry missing display metadata must
  still render a usable card (fall back to the hostname) rather than breaking the page.
- **Stale health data**: If the blackbox probe interval is long, a just-stopped service may still
  show "up" until the next probe. The indicator reflects the last successful probe, not real-time
  state; this is acceptable and should be understood as monitoring-derived, not live ping.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST serve a landing page at `https://hus-sky.no` (the apex domain)
  presenting a valid Let's Encrypt certificate with no browser security warnings. *(traces to US-1)*
- **FR-002**: The landing page MUST display one card per enabled, user-facing service, each with
  a title, a short description, and a hyperlink to that service's `https://<service>.hus-sky.no`
  URL. *(traces to US-1)*
- **FR-003**: The list of services rendered on the landing page MUST be generated at deploy time
  from a single declarative source of truth (a `caddy_services` list in Ansible), not hand-edited
  on the page. *(traces to US-1, US-3)*
- **FR-004**: The same `caddy_services` source of truth MUST generate the per-service Caddy site
  blocks (reverse proxy routes), replacing the current per-service `.caddy` templates with a
  single generated/looped form. *(traces to US-3)*
- **FR-005**: The same `caddy_services` source of truth MUST generate the blackbox exporter HTTPS
  probe target list (`blackbox_https_targets`), replacing the current hand-maintained list.
  *(traces to US-3)*
- **FR-006**: A service entry MUST support flags to exclude it from rendering and probing — at
  minimum an `enabled` flag (service deployed yet?) and a `user_facing` flag (should it appear on
  the landing page / be probed as a user service?). Excluded services MUST be omitted consistently
  from the route (when disabled), the probe targets, and the landing page. *(traces to US-1, US-3)*
- **FR-007**: Each landing-page card MUST display a live health indicator (up / down / unknown)
  for its service. *(traces to US-2)*
- **FR-008**: Health indicators MUST be derived from the existing Prometheus + blackbox exporter
  data (`probe_success` per HTTPS target), not from a new health-checking mechanism. *(traces to US-2)*
- **FR-009**: The browser MUST obtain health data via a same-origin endpoint on `hus-sky.no` that
  proxies a **pinned, read-only** Prometheus query; the endpoint MUST NOT allow the client to
  submit arbitrary PromQL or otherwise expose the general Prometheus query API. *(traces to US-2)*
- **FR-010**: The landing page MUST render all service cards and links even when the health data
  source is unavailable, degrading health indicators to "unknown" rather than failing to load.
  *(traces to US-2)*
- **FR-011**: The apex domain `hus-sky.no` MUST resolve to the reverse proxy LXC IP
  (`192.168.1.211`) for LAN and Tailscale clients, via a **public DNS A record at Domeneshop** for the
  bare apex (the existing `*.hus-sky.no` wildcard does not cover it). Resolution is public-DNS only. *(traces to US-1)*
- **FR-012**: The card-to-health join MUST be derived from the shared `caddy_services` source so
  that a card and its health metric cannot reference mismatched hostnames. *(traces to US-2, US-3)*
- **FR-013**: All changes MUST be deployable from both CI/CD (GitHub Actions) and a developer
  laptop (dual-provisioning parity), consistent with existing roles. *(traces to US-3)*
- **FR-014**: The landing page assets and the apex Caddy site block MUST be managed by the
  existing `reverse_proxy` Ansible role (no new LXC, no new long-running service). *(traces to US-3)*

### Key Entities

- **Service Definition (`caddy_services` entry)**: The single source of truth for one service.
  Fields: `host` (subdomain label), `ip`, `port` (backend), `title`, `desc` (display metadata),
  `enabled` (deployed/active), `user_facing` (appears on landing page and as a user health probe).
  One entry drives the Caddy route, the blackbox target, and the landing-page card.
- **Landing Page Asset**: The generated static `index.html` (plus any CSS/JS) served by Caddy's
  `file_server` at the apex. Regenerated from `caddy_services` on every deploy; never hand-edited.
- **Apex Site Block**: The Caddy configuration for `hus-sky.no` — a `file_server` for the landing
  assets plus the pinned health-data handler.
- **Health Data Endpoint**: A same-origin path on the apex (e.g. `/api/status`) that reverse-proxies
  a fixed Prometheus query (`probe_success`) and returns it to the browser. Read-only and pinned.
- **Health Indicator State**: Per-service up / down / unknown, derived from `probe_success` for
  that service's HTTPS target, joined to the card by hostname.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `https://hus-sky.no` loads in a browser on the LAN with a valid Let's Encrypt
  certificate and no security warnings, showing a card for every enabled user-facing service.
- **SC-002**: Every service card links to the correct `https://<service>.hus-sky.no` URL, verified
  by clicking each card and reaching the intended service.
- **SC-003**: Adding one entry to `caddy_services` and deploying produces — with no other edit —
  a working route, a blackbox probe target, and a landing-page card for that service; removing the
  entry removes all three.
- **SC-004**: After this feature, there is exactly one hand-maintained subdomain list in the
  repository (`caddy_services`); a repository search finds no separate landing-page list, no
  separate `blackbox_https_targets` literal list, and no per-service duplicated `.caddy` templates.
- **SC-005**: With all services running, every card shows "up"; stopping one service causes its
  card to show "down" after the next probe cycle and a page refresh.
- **SC-006**: With Prometheus stopped, `https://hus-sky.no` still renders all cards and links, and
  health indicators show "unknown" — the page does not error or blank out.
- **SC-007**: The health endpoint rejects or ignores any attempt to run a Prometheus query other
  than the pinned health query (verified by requesting `/api/status` with an alternate query and
  confirming the pinned result is returned, not the alternate).
- **SC-008**: The feature deploys successfully from both a GitHub Actions run and a developer
  laptop using the same Ansible roles.

## Assumptions

- **A-001**: The reverse proxy LXC (`192.168.1.211`) and its custom Caddy build with the Domeneshop
  DNS provider already exist (feature `039-https-services`). No new LXC or binary work is needed.
- **A-002**: The Prometheus + blackbox exporter stack (feature `042-monitoring-tier-c`) is running
  on the monitoring LXC (`192.168.1.214`), Prometheus on port `9090`, and already probes the
  service subdomains via `blackbox_https_targets`, producing `probe_success` metrics.
- **A-003**: The Domeneshop DNS-01 flow can issue a certificate for the bare apex `hus-sky.no`
  exactly as it does for subdomains.
- **A-004**: A public DNS A record for the bare apex `hus-sky.no → 192.168.1.211` can be added at
  Domeneshop (the `*.hus-sky.no` wildcard does not cover the apex). DNS is public-only and resolves to
  the LAN IP for both LAN and Tailscale clients (per `docs/network-layout.md`).
- **A-005**: All current service backend IPs and ports remain unchanged; this feature changes only
  the reverse proxy (apex block + generated subdomain blocks), the blackbox target generation, and
  adds the landing assets.
- **A-006**: The landing page is a static page with a small amount of client-side JavaScript for
  health polling; no server-side application runtime is introduced beyond Caddy itself.
- **A-007**: Services are reachable only on the LAN and via Tailscale (not the public internet),
  consistent with the existing posture, so the apex landing page inherits the same access model.

## Out of Scope

- **Runtime discovery via the Caddy admin API** — Querying `localhost:2019` to discover subdomains
  live at request time is explicitly not chosen: in this repo all subdomains are declared through
  Ansible, so build-time generation gives the same zero-touch result without a runtime dependency
  or loss of display metadata/intent. Revisit only if subdomains ever start being added outside
  this Ansible role.
- **Third-party dashboard apps** (Homepage / Homer / Dashy / Heimdall) — Their auto-discovery is
  Docker-label-based and does not fit the per-LXC service topology; adopting one would mean hand-
  maintaining its config, a worse version of the single-source-of-truth approach.
- **Authentication / access control on the landing page** — The page inherits the LAN + Tailscale
  access model of the rest of the homelab. Adding SSO or auth in front of the apex is a separate
  concern. (If the apex is ever exposed beyond LAN/Tailscale, the health endpoint should be gated;
  see Decision Log D-004.)
- **Rich widgets** (weather, system stats, per-service deep metrics, latency graphs) — The cards
  show link + up/down only. Anything richer is a future enhancement layered on the same data path.
- **Service icons / theming polish** — A clean, readable card layout is in scope; bespoke icon
  sets, dark-mode toggles, and visual theming are deferred.
- **Certificate expiry / uptime alerting for the apex** — Monitoring of the landing page itself is
  a separate observability task; the page consumes health data, it does not add new alerts.
- **Configurable per-user dashboards / favorites** — A single shared page for all users; no
  personalization.

## Decision Log

| # | Ambiguity | Decision | Rationale |
|---|-----------|----------|-----------|
| D-001 | Dynamic runtime discovery vs generated-from-config | Generate the page (and routes and probe targets) at deploy time from a single `caddy_services` list. | In this repo every subdomain is already declared via Ansible, so there is no "out-of-band" addition for runtime discovery to catch. Generation gives the zero-touch property without a runtime service, keeps config in git (IaC-consistent), and preserves display metadata/intent that the admin API cannot express. |
| D-002 | Where the subdomain source of truth lives | A single `caddy_services` list in `group_vars/services/vars.yml`, driving Caddy site blocks, blackbox targets, and the landing page. | Collapses three existing hand-maintained copies into one. Eliminates drift; satisfies the "no shortcuts / architecturally sound" requirement directly. |
| D-003 | Source of live health data | Reuse Prometheus `probe_success` from the existing blackbox exporter; do not add a new health checker. | The blackbox stack already probes the exact subdomains over HTTPS. Reusing it avoids a second, divergent definition of "healthy" and adds no new runtime component. |
| D-004 | How the browser gets health data without exposing Prometheus | A same-origin `/api/status` handler on the apex that reverse-proxies a **pinned** query (`probe_success`) to Prometheus; the client cannot submit arbitrary PromQL. | Same-origin avoids CORS; pinning the query prevents the landing page from becoming an open Prometheus query proxy. If the apex is ever exposed beyond LAN/Tailscale, this endpoint should additionally be auth-gated. |
| D-005 | Apex serving and port concerns | Add a `hus-sky.no` site block on the existing shared 443 listener; no special port handling. | Caddy routes by Host/SNI, so the apex coexists with subdomains. The user's "maybe not port 80" concern does not apply — port 80 simply auto-redirects to HTTPS as for subdomains. |
| D-006 | Static page vs server-side app | Static `index.html` + minimal client-side JS for health polling, served by Caddy `file_server`. | No new long-running service, nothing to monitor or that can drift; the page loads even if the health source is down. Health is the only dynamic part and it degrades gracefully. |
| D-007 | Disabled/internal services (Home Assistant, metrics `:9180`) | Control inclusion with `enabled` and `user_facing` flags on each `caddy_services` entry. | Lets the declaration express intent — a not-yet-deployed or internal-only endpoint is omitted from page and probes consistently, which runtime discovery could not infer. |
| D-008 | Scope of the consolidation refactor | Fold the existing per-service `.caddy` templates and the `blackbox_https_targets` literal into the `caddy_services`-driven generation as part of this feature. | The refactor is what makes the page sound rather than a fourth duplicate list. It touches the `reverse_proxy` and `monitoring_stack` roles and is the bulk of the work; it must be sequenced to preserve current routes/probes (no service interruption). |

## Open Questions

- **Q-001**: What blackbox probe interval is currently configured, and is its staleness window
  acceptable for the "down" indicator latency in SC-005? (Resolve during planning by reading the
  `042-monitoring-tier-c` scrape config; may not need any change.)
- **Q-002**: Does `probe_success` label the target by full URL (`https://immich.hus-sky.no`) or by
  another label? The card→metric join (FR-012) must use whatever label blackbox emits; confirm the
  exact label during planning so the JS join key matches.
