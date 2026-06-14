# Implementation Plan: Service Landing Page at hus-sky.no

**Branch**: `045-landing-page` | **Date**: 2026-06-13 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/045-landing-page/spec.md`

## Summary

Add a static landing page at the apex `https://hus-sky.no` that renders one card per
user-facing service (link + live up/down/unknown health), served by the existing Caddy reverse
proxy with no new LXC or long-running service. The page, the per-service Caddy site blocks, and
the blackbox HTTPS probe targets are all **generated from a single `caddy_services` list** in
`group_vars/services/vars.yml`, collapsing three hand-maintained copies into one. Live health
reuses the existing Prometheus `probe_success` metric via a same-origin `/api/status` handler on
the apex that reverse-proxies a **pinned** Prometheus query (no arbitrary PromQL reaches the
browser). The work is a consolidation refactor of the `reverse_proxy` and `monitoring_stack`
roles that must preserve every current route and probe (no service interruption).

## Technical Context

**Language/Version**: YAML (Ansible 2.x), Jinja2 templates, Caddyfile syntax, static HTML/CSS + vanilla JS (no framework)
**Primary Dependencies**: Caddy (custom xcaddy build w/ Domeneshop DNS, already deployed); Prometheus v3.8.1 + blackbox_exporter v0.28.0 (already deployed, feature `042`); `community.general` / builtin Ansible modules only
**Storage**: N/A — landing assets are generated files under `/var/www/hus-sky` on the reverse-proxy LXC; no database
**Testing**: `caddy validate` (already in role), `ansible-playbook --check`/`--syntax-check`, `act -l` for workflow parse; manual browser verification per quickstart
**Target Platform**: Debian LXC `reverse_proxy` (192.168.1.211) on shared :443 listener; Prometheus on `monitoring` (192.168.1.214:9090)
**Project Type**: Infrastructure-as-Code (Ansible roles), not an application — maps to existing `ansible/roles/` layout, no `src/`/`tests/` scaffold
**Performance Goals**: Page is static; first paint < 1s on LAN. Health poll is a single same-origin request returning the `probe_success` vector (small JSON). Health latency bounded by the existing 30s `blackbox-https` scrape interval (see research Q-001)
**Constraints**: No new LXC, no new daemon (D-006); page MUST render with cards+links even when Prometheus is down (FR-010); `/api/status` MUST NOT expose arbitrary PromQL (FR-009); dual-provisioning parity CI + laptop (FR-013); preserve all existing routes/probes during the refactor (D-008)
**Scale/Scope**: 4 active services (Immich, Jellyfin, Nextcloud, Grafana); AdGuard unused (`enabled: false`, dead route removed) and Home Assistant disabled; 2 roles touched (`reverse_proxy`, `monitoring_stack`); 1 new shared var list

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment | Pass |
|-----------|------------|------|
| I. Spec-Driven Workflow | Work is driven from `specs/045-landing-page/`; behaviour/architecture changes (var consolidation) are captured in this plan and the spec. | ✅ |
| II. Secrets Policy | No new secrets. Domeneshop creds already injected via systemd drop-in + gitignored vault. `/api/status` proxies to Prometheus over the LAN with no credential. | ✅ |
| III. Separation of Concerns | Pure Ansible change (config inside the LXC). No Terraform touched — the reverse-proxy and monitoring LXCs already exist (A-001, A-002). | ✅ |
| IV. Code Economy (YAGNI) | **Net reduction**: replaces 6 near-identical `.caddy.j2` templates + a literal target list with one generated loop over a list that has >1 item today (loop justified). No new indirection beyond what removes duplication. New files (landing template, `/api/status` block) are justified by separation of concerns. | ✅ |
| V. Dual-Provisioning Parity | No new service ⇒ no workflow dropdown change required; `reverse_proxy.yml` and `monitoring.yml` already run from both CI and laptop. Verify `act -l` still parses (no workflow edit expected). | ✅ |

**Gate result: PASS.** No violations; Complexity Tracking section omitted. The consolidation is a simplification, directly serving Principle IV.

Re-evaluation after Phase 1 design: **PASS (unchanged).** The design adds exactly one shared
var list, one generated Caddy template (replacing six), one landing template + asset, and one
`/api/status` handler. No abstraction layers, no new runtime component, no Terraform.

## Project Structure

### Documentation (this feature)

```text
specs/045-landing-page/
├── plan.md              # This file
├── research.md          # Phase 0 — decisions, Q-001/Q-002 resolved
├── data-model.md        # Phase 1 — caddy_services entry schema
├── quickstart.md        # Phase 1 — deploy + verify steps
├── contracts/
│   ├── caddy_services.schema.md   # The shared var contract (fields, defaults, validation)
│   └── api-status.contract.md     # The /api/status health endpoint contract
└── tasks.md             # Phase 2 — created by /speckit.tasks (NOT here)
```

### Source Code (repository root)

This feature edits existing Ansible roles; it introduces no `src/`/`tests/` tree. Concrete paths:

```text
ansible/
├── group_vars/
│   └── services/
│       └── vars.yml                     # ADD caddy_services list (single source of truth).
│                                        #   Visible to monitoring host too — it is a member of
│                                        #   the `services` group (inventories/prod/hosts.yml).
├── roles/
│   ├── reverse_proxy/
│   │   ├── tasks/main.yml               # REPLACE the six per-service template tasks with one
│   │   │                                #   loop generating <host>.caddy; add apex site block +
│   │   │                                #   landing assets + /api/status handler.
│   │   ├── templates/
│   │   │   ├── service.caddy.j2         # NEW generic per-service block (replaces the six)
│   │   │   ├── apex.caddy.j2            # NEW hus-sky.no block: file_server + /api/status
│   │   │   ├── index.html.j2            # NEW landing page generated from caddy_services
│   │   │   └── (DELETE immich/nextcloud/grafana/jellyfin/adguard/homeassistant .caddy.j2)
│   │   └── defaults/main.yml            # ADD caddy_landing_root, caddy_status_query, etc.
│   └── monitoring_stack/
│       └── (no template change needed)  # blackbox_https_targets becomes a generated var,
│                                        #   see below — prometheus.yml.j2 already loops it.
└── group_vars/
    └── monitoring/vars.yml              # REPLACE literal blackbox_https_targets with a value
                                         #   derived from caddy_services (generated, not hand-kept)
```

**Structure Decision**: Follow the existing repository layout (constitution "Repo Layout":
`ansible/roles`, `ansible/group_vars`). No new top-level directories. The landing page is the
only "frontend" artifact and lives inside the `reverse_proxy` role's `templates/` as a generated
file — it is config output, not an application project, so no `frontend/` tree is created.

## Key Design Decisions (detail in research.md)

1. **Single source location**: `caddy_services` lives in `group_vars/services/vars.yml`. The
   `monitoring` host is a member of the `services` inventory group, so the list is in scope for
   both the `reverse_proxy` role and the `monitoring_stack` role without duplication or
   cross-group plumbing. (Resolves the "how does monitoring see it" risk in D-002.)
2. **Per-service Caddy generation**: One `service.caddy.j2` rendered in a `loop` over
   `caddy_services | selectattr('enabled') | selectattr('user_facing')`-style filters, replacing
   the six hand-written templates. All six current blocks are byte-for-byte equivalent except the
   host/ip/port, so a single template preserves behaviour (no service interruption, D-008).
3. **blackbox targets generated**: `blackbox_https_targets` in `group_vars/monitoring/vars.yml`
   becomes a Jinja expression deriving `https://<host>.hus-sky.no` from the enabled, user-facing,
   probe-eligible `caddy_services` entries. `prometheus.yml.j2` already loops this var unchanged.
4. **Health endpoint pinning**: `/api/status` is a Caddy `handle` that `rewrite`s any client
   request to the fixed upstream path `/api/v1/query?query=probe_success` and `reverse_proxy`es to
   `{{ monitoring_ip }}:9090` (shared `monitoring_ip` var + inline port; `prometheus_port` is out of
   the reverse_proxy role's scope), discarding client-supplied query string. The browser cannot
   inject PromQL (FR-009, SC-007).
5. **Card→health join key**: `probe_success` is labelled `instance="https://<host>.hus-sky.no"`
   (confirmed from `prometheus.yml.j2` relabel_configs). The landing JS joins each card to its
   metric on that exact full-URL key, and that URL is itself derived from `caddy_services` so the
   two can never drift (FR-012).
6. **Graceful degradation**: The landing HTML renders all cards server-side from `caddy_services`
   at deploy time; health is a progressive enhancement applied by JS after a successful
   `/api/status` fetch. If the fetch fails or Prometheus is down, cards stay in the default
   "unknown" state — the page never blanks (FR-010, SC-006).
7. **Single deploy entrypoint**: Both halves are applied by one `site.yml` run, not two separate
   playbook invocations. `site.yml` already imports `services.yml` (which includes `reverse_proxy.yml`,
   tag `reverse_proxy`) **before** `monitoring.yml` (tag `monitoring`), so routes + landing page
   regenerate first, then the blackbox targets — both from the same source. A scoped run uses the
   existing tags: `ansible-playbook site.yml --tags reverse_proxy,monitoring`. No new orchestration
   playbook is created (Principle IV — reuse existing `site.yml`). The reverse-proxy-then-monitoring
   ordering means routes exist before/as their probes are (re)generated; since both derive from
   `caddy_services` the definitions cannot drift, only their apply-timing within the single run.

## Open Questions — Resolved

- **Q-001 (probe interval / staleness)**: `blackbox-https` job uses `scrape_interval: 30s`
  (hard-coded in `prometheus.yml.j2`). A stopped service shows "down" within ~30s + the page's
  poll interval. Acceptable for SC-005; **no change needed**.
- **Q-002 (`probe_success` label)**: Labelled by `instance` set to the **full target URL**
  (`https://immich.hus-sky.no`) via the `blackbox-https` relabel_configs. The JS join key is that
  full URL, derived from `caddy_services`. **No ambiguity remains.**

## Complexity Tracking

> No constitution violations — section intentionally empty.
