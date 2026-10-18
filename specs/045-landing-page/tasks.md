---
description: "Task list for 045-landing-page implementation"
---

# Tasks: Service Landing Page at hus-sky.no

**Input**: Design documents from `/specs/045-landing-page/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: This is an Infrastructure-as-Code feature. No automated unit/contract test files are
generated (none requested in the spec). Per the constitution ("Test-Driven Changes" — non-destructive
validation), each story ends with `caddy validate` / `ansible --check --diff` / `curl` verification
tasks instead.

**Organization**: Tasks are grouped by user story. US3 (single source of truth) is sequenced before
US1/US2 because the landing page and health are generated from the consolidated source; doing the
consolidation first avoids a temporary "fourth copy" and proves zero route/probe drift (plan D-008).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 / US2 / US3 (Setup & Foundational & Polish carry no story label)

## Path Conventions

IaC repo — no `src/`/`tests/` tree. Real paths: `ansible/group_vars/`, `ansible/roles/reverse_proxy/`,
`ansible/roles/monitoring_stack/`, `ansible/playbooks/` (per plan.md Structure Decision).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Capture the parity baseline so the consolidation can be proven drift-free.

- [X] T001 [P] Record the parity baseline before any change. Today **four** per-service blocks render
  (immich, nextcloud, grafana, jellyfin; `ha` does NOT render,
  guarded off by `homeassistant_active: false`) and **four** `blackbox_https_targets` exist (grafana,
  immich, nextcloud, jellyfin), as listed in
  `specs/045-landing-page/contracts/caddy_services.schema.md` (initial-population table). The US3
  consolidation must reproduce the four active services exactly.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Establish the single declarative source that ALL three stories derive from.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T002 Define `caddy_services` in `ansible/group_vars/services/vars.yml` per
  `specs/045-landing-page/contracts/caddy_services.schema.md`: entries for grafana, immich, nextcloud,
  jellyfin (`enabled: true`, `user_facing: true`), and ha (`enabled: false`). Each entry's `ip`/`port` MUST reference the
  existing central backend vars
  (e.g. `ip: "{{ immich_ip }}"`, `port: "{{ immich_port }}"`; grafana → `{{ monitoring_ip }}`/`{{ grafana_port }}`;
  ha → `{{ homeassistant_ip }}`/`{{ homeassistant_port }}`)
  so IP strings stay centrally defined (constitution Networking rule), not duplicated.
- [X] T003 Add `caddy_base_domain: "hus-sky.no"` to `ansible/group_vars/services/vars.yml` and remove
  the now-redundant `caddy_base_domain` default from `ansible/roles/reverse_proxy/defaults/main.yml`,
  so both the `reverse_proxy` role and the `monitoring_stack` role (its host is in the `services`
  group) resolve one shared value (research R-006).

**Checkpoint**: `caddy_services` + `caddy_base_domain` are in shared scope. Stories can begin.

---

## Phase 3: User Story 3 - Single Source of Truth for Subdomains (Priority: P1)

**Goal**: One `caddy_services` declaration generates the Caddy routes AND the blackbox probe targets,
replacing the six per-service templates and the literal target list — with zero change to the actual
routes/probes (no service interruption).

**Independent Test**: Add an entry to `caddy_services`, deploy → a new route and a new probe target
appear from that one entry; remove it → both disappear. Repo search finds no per-service `.caddy.j2`
and no literal `blackbox_https_targets` list.

- [X] T004 [P] [US3] Create `ansible/roles/reverse_proxy/templates/service.caddy.j2` — a generic
  per-service site block (`{{ item.host }}.{{ caddy_base_domain }}` → `reverse_proxy {{ item.ip }}:{{ item.port }}`
  with the same three `header_up` lines as today's `immich.caddy.j2`).
- [X] T005 [US3] In `ansible/roles/reverse_proxy/tasks/main.yml`, replace the six per-service
  `Deploy <service> Caddy configuration` template tasks with one looped task over
  `caddy_services | selectattr('enabled')` (route gated by `enabled` only) rendering `service.caddy.j2`
  → `{{ caddy_conf_dir }}/{{ item.host }}.caddy`, `loop_control.label: "{{ item.host }}"`, notify Restart caddy.
- [X] T006 [P] [US3] Delete the five obsolete templates in `ansible/roles/reverse_proxy/templates/`:
  `immich.caddy.j2`, `nextcloud.caddy.j2`, `grafana.caddy.j2`, `jellyfin.caddy.j2`,
  `homeassistant.caddy.j2`.
- [X] T007 [P] [US3] In `ansible/group_vars/monitoring/vars.yml`, replace the literal
  `blackbox_https_targets` list with a generated expression: for each `caddy_services` entry where
  `enabled and user_facing`, emit `"https://{{ item.host }}.{{ caddy_base_domain }}"` (e.g. a Jinja
  `map`/loop). `prometheus.yml.j2` consumes it unchanged.
- [X] T008 [US3] Validate consolidation parity (non-destructive): run the deploy with
  `ansible-playbook -i ansible/inventories/prod/hosts.yml ansible/playbooks/site.yml --tags reverse_proxy,monitoring --check --diff`
  and the in-role `caddy validate`; confirm the resolved `blackbox_https_targets` and the rendered
  site blocks match the Phase 1 (T001) baseline for the **four active services** (grafana, immich,
  nextcloud, jellyfin) — no probe drift, no route drift for those.
  `ha` is absent both before and after (already guarded off) — true parity.

**Checkpoint**: Routes and probes for the four active services are generated from one source, identical
to before; old duplicate templates/literal removed.

---

## Phase 4: User Story 1 - Discover All Services from One Page (Priority: P1) 🎯 MVP

**Goal**: `https://hus-sky.no` serves a landing page with one card per enabled, user-facing service —
each a working link — over a valid Let's Encrypt cert.

**Independent Test**: Browse `https://hus-sky.no` on the LAN: valid cert, one card per active service
(Immich, Jellyfin, Nextcloud, Grafana), each linking to the correct `https://<service>.hus-sky.no`.
Disabled/internal entries show no card.

- [X] T009 [P] [US1] Add apex/landing defaults to `ansible/roles/reverse_proxy/defaults/main.yml`:
  `caddy_landing_root: /var/www/hus-sky` (web root for the generated assets).
- [X] T010 [P] [US1] Create `ansible/roles/reverse_proxy/templates/index.html.j2` — render one card per
  `caddy_services | selectattr('enabled') | selectattr('user_facing')` entry: heading `{{ item.title | default(item.host | capitalize) }}`,
  description `{{ item.desc | default('') }}`, anchor to `https://{{ item.host }}.{{ caddy_base_domain }}`,
  and `data-probe="https://{{ item.host }}.{{ caddy_base_domain }}"` with default health state `unknown`.
  Include minimal inline CSS for a readable card grid. (Health JS is added in US2 — T015.)
- [X] T011 [P] [US1] Create `ansible/roles/reverse_proxy/templates/apex.caddy.j2` — the
  `hus-sky.no { ... }` site block with `root * {{ caddy_landing_root }}` and `file_server`. (The
  `/api/status` handler is added in US2 — T014.) Relies on the existing global `acme_dns` for the apex cert.
- [X] T012 [US1] In `ansible/roles/reverse_proxy/tasks/main.yml`, add tasks (after the looped service
  task): ensure `{{ caddy_landing_root }}` dir exists; template `index.html.j2` → `{{ caddy_landing_root }}/index.html`;
  template `apex.caddy.j2` → `{{ caddy_conf_dir }}/apex.caddy` — all notify Restart caddy.
- [X] T013 [US1] Deploy and verify (SC-001, SC-002, FR-011): run
  `ansible-playbook -i ansible/inventories/prod/hosts.yml ansible/playbooks/site.yml --tags reverse_proxy,monitoring`.
  Complete the one-time apex DNS step (a **public DNS A record at Domeneshop** `hus-sky.no → 192.168.1.211`,
  per quickstart) — this is a manual step. DNS is public-only.
  **Explicitly verify apex resolution before the browser check** (FR-011): from both a LAN client and a
  Tailscale client, `dig +short hus-sky.no` (or `nslookup`) returns `192.168.1.211`. Then browse
  `https://hus-sky.no` — valid cert, a card per active service, each link reaches the right subdomain;
  no card for ha.

**Checkpoint**: Landing page is live and lists all services (MVP). Health indicators are still `unknown`.

---

## Phase 5: User Story 2 - Live Service Health at a Glance (Priority: P2)

**Goal**: Each card shows live up/down/unknown health, sourced from Prometheus `probe_success` via a
pinned same-origin `/api/status`, degrading to `unknown` if Prometheus is down.

**Independent Test**: All running → all cards `up`. Stop one service, wait ~30s + refresh → that card
`down`. Stop Prometheus → page still renders all cards/links, indicators `unknown`.

- [X] T014 [US2] Add the `/api/status` handler to `ansible/roles/reverse_proxy/templates/apex.caddy.j2`
  per `specs/045-landing-page/contracts/api-status.contract.md`:
  `handle /api/status { rewrite * /api/v1/query?query=probe_success; reverse_proxy {{ monitoring_ip }}:9090 }`
  (inline `9090` — single use, monitoring's Prometheus port; `monitoring_ip` is already shared via
  `group_vars/services/vars.yml`). The rewrite discards any client query so only `probe_success` reaches Prometheus.
- [X] T015 [US2] Add the health-polling script to `ansible/roles/reverse_proxy/templates/index.html.j2`
  (inline `<script>`): on load and every 30s, `fetch('/api/status')`, parse the `probe_success` vector,
  and for each card match `data-probe` to the metric `instance` label — `"1"` → up, `"0"` → down,
  absent/fetch-error → unknown. Never throw on failure (FR-010). (Edits the US1 file — after T010.)
- [X] T016 [US2] Deploy and verify health (SC-005, SC-006, SC-007): redeploy; confirm all cards `up`;
  stop one backend, wait ~30s + refresh → `down`; `curl -s 'https://hus-sky.no/api/status?query=node_load1'`
  returns `probe_success` instances (pinning holds); stop Prometheus → page renders with `unknown`.

**Checkpoint**: All three user stories functional and independently verifiable.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T017 [P] SC-004 audit: `rg` confirms no per-service `*.caddy.j2` remain (only `service.caddy.j2` +
  `apex.caddy.j2`), no literal `blackbox_https_targets` list, and `caddy_services` is the only
  hand-maintained subdomain list.
- [X] T018 [P] Update any subdomain/service listing in `docs/` to point at `caddy_services` as the
  single source of truth (if such a doc exists).
- [X] T019 SC-008 / dual-provisioning parity: run `act -l` to confirm workflows still parse (no
  workflow change expected — no new service), and confirm the tagged `site.yml` run works from both a
  GitHub Actions dispatch and a laptop.
- [ ] T020 Run the full `specs/045-landing-page/quickstart.md` verification checklist end to end.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (T001)**: no dependencies — do first (read-only baseline).
- **Foundational (T002–T003)**: depends on Setup; BLOCKS all stories.
- **US3 (T004–T008)**: depends on Foundational. Independent of US1/US2.
- **US1 (T009–T013)**: depends on Foundational; should follow US3 so the page is built on the
  consolidated source (no temporary fourth list). Technically US1 only needs `caddy_services`, but
  sequence after US3 per plan D-008.
- **US2 (T014–T016)**: depends on US1 (the page/cards must exist) — `probe_success` already exists,
  so US2 does not depend on US3's blackbox regeneration.
- **Polish (T017–T020)**: after all desired stories.

### Within Each Story

- US3: T004 (template) → T005 (use it); T006/T007 parallel to T004; T008 validates after T005–T007.
- US1: T009/T010/T011 parallel (different files) → T012 (wires them in tasks/main.yml) → T013 (verify).
- US2: T014 (apex.caddy.j2) and T015 (index.html.j2) are different files → parallel; T016 verifies.

### Parallel Opportunities

- T004, T006, T007 [P] within US3 (distinct files).
- T009, T010, T011 [P] within US1 (distinct files).
- T014, T015 [P] within US2 (distinct files).
- T017, T018 [P] in Polish.
- Note: every task editing `ansible/roles/reverse_proxy/tasks/main.yml` (T005, T012) is sequential —
  same file, no [P].

---

## Implementation Strategy

### MVP scope

US3 + US1 (both P1) = the consolidated source of truth plus the live landing page listing every
service. This is a shippable increment: a working `hus-sky.no` with links, generated from one list,
even before health indicators exist (cards default to `unknown`).

### Incremental delivery

1. Setup + Foundational → single source of truth in place.
2. US3 → routes + probes generated from it, old duplicates gone (verify parity, T008).
3. US1 → landing page live (MVP — STOP and validate SC-001/SC-002).
4. US2 → live health layered on (SC-005/SC-006/SC-007).
5. Polish → SC-004 audit, docs, parity, full quickstart.

### Notes

- Deploy throughout with the single tagged run: `ansible-playbook ... site.yml --tags reverse_proxy,monitoring`.
- `caddy validate` runs inside the `reverse_proxy` role on every deploy — treat a validation failure as a blocking gate.
- Commit after each task or logical group; the consolidation (US3) must keep every existing route/probe working at each step.
