# Tasks: HTTPS for All Homelab Services

**Input**: Design documents from `specs/039-https-services/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅

**Tests**: No test tasks generated — none requested in the feature spec. Verification is done via `ansible-lint`, `ansible-playbook --syntax-check`, and `openssl s_client` runtime checks (Plan Step 12).

**Organization**: Tasks are grouped by user story (US5 → US1 → US2 → US3 → US4) to match priority order. US5 (secrets) is placed first because it is a hard prerequisite for certificate issuance (US1, US2, US3).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2…US5)
- Include exact file paths in descriptions

## Path Conventions

All paths are relative to the repository root:
- `ansible/group_vars/` — shared variables for host groups
- `ansible/roles/<role>/defaults/main.yml` — role default variables
- `ansible/roles/<role>/tasks/main.yml` — role task list
- `ansible/roles/<role>/handlers/main.yml` — role event handlers
- `ansible/roles/<role>/templates/` — Jinja2 templates

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Centralize variables and role defaults required by all subsequent phases. All three tasks are independent and can run in parallel.

**Done-condition checkpoint**: `grep -E 'jellyfin_ip|homeassistant_ip' ansible/group_vars/services/vars.yml` returns 2 matches. `grep 'caddy_base_domain' ansible/roles/reverse_proxy/defaults/main.yml` returns 1 match.

- [X] T001 [P] Add missing service IPs/ports to `ansible/group_vars/services/vars.yml`: `jellyfin_ip: "192.168.1.215"`, `jellyfin_port: 8096`, `homeassistant_ip: "192.168.1.212"`, `homeassistant_port: 8123` (Plan Step 1, FR-010, FR-015, data-model E-001)
- [X] T002 [P] Add encrypted vault entries `domeneshop_api_token` and `domeneshop_api_secret` to `ansible/group_vars/services/vault.yml` using `ansible-vault edit` (Plan Step 2, FR-013, US5, data-model E-005)
- [X] T003 [P] Add HTTPS and xcaddy role defaults to `ansible/roles/reverse_proxy/defaults/main.yml`: `caddy_base_domain: "hus-sky.no"`, `caddy_acme_dns_provider: "lego_deprecated"`, `caddy_acme_dns_provider_name: "domeneshop"`, `caddy_custom_binary: true`, `caddy_xcaddy_plugins: ["github.com/caddy-dns/lego-deprecated"]`, `go_version: "1.22.0"`, `homeassistant_active: false` (Plan Step 3, FR-001, FR-012, FR-015, data-model variable registry)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Enable automatic HTTPS globally and register the `Reload systemd` handler. Both tasks are prerequisites for all user story phases.

**⚠️ CRITICAL**: No user story implementation work can begin until this phase is complete.

**Done-condition checkpoint**: `grep 'auto_https' ansible/roles/reverse_proxy/templates/Caddyfile.j2` returns 0 matches. `grep 'acme_dns' ansible/roles/reverse_proxy/templates/Caddyfile.j2` returns 1 match. `grep 'Reload systemd' ansible/roles/reverse_proxy/handlers/main.yml` returns 1 match.

- [X] T004 Update `ansible/roles/reverse_proxy/templates/Caddyfile.j2`: remove `auto_https off` from the global options block and add `acme_dns {{ caddy_acme_dns_provider }} {{ caddy_acme_dns_provider_name }}` per the `caddyfile-global.md` contract (Plan Step 4, FR-011, FR-002, FR-003, R-008). Depends on T003.
- [X] T005 [P] Add `Reload systemd` handler to `ansible/roles/reverse_proxy/handlers/main.yml` using `ansible.builtin.systemd` with `daemon_reload: true`. Ensure handler ordering: `Reload systemd` before `Restart caddy` (Plan Step 9, FR-013, R-003). No dependencies.

**Checkpoint**: Foundation ready — all user story phases can now start.

---

## Phase 3: User Story 5 — Secrets Security (Priority: P1) 🔐

**Goal**: Store Domeneshop API credentials exclusively in Ansible vault and inject them into Caddy at runtime via systemd EnvironmentFile, so they never appear in plaintext in any committed file.

**Independent Test**: `rg 'DOMENESHOP_API_TOKEN=[^{]' . --type-not yaml` from repo root returns 0 matches. `ansible-vault view ansible/group_vars/services/vault.yml --vault-password-file ansible/.vault-pass.txt | grep -c 'domeneshop_api'` returns 2.

### Implementation for User Story 5

- [X] T006 [P] [US5] Create NEW `ansible/roles/reverse_proxy/templates/domeneshop.env.j2` with content: `DOMENESHOP_API_TOKEN={{ domeneshop_api_token }}` and `DOMENESHOP_API_SECRET={{ domeneshop_api_secret }}` per the `systemd-override.md` contract. File must contain only template variables — no hardcoded credential values (Plan Step 7, FR-013, R-003). Depends on T002.
- [X] T007 [P] [US5] Create NEW `ansible/roles/reverse_proxy/templates/caddy-domeneshop.conf.j2` as a systemd drop-in override with `[Service]` section containing `EnvironmentFile=/etc/caddy/domeneshop.env` per the `systemd-override.md` contract (Plan Step 7, FR-013, R-003, D-006). Depends on T002.

**Checkpoint**: Secrets templates ready. `grep 'EnvironmentFile' ansible/roles/reverse_proxy/templates/caddy-domeneshop.conf.j2` returns 1 match.

---

## Phase 4: User Story 1 — Mobile App Connectivity via HTTPS (Priority: P1) 🎯 MVP

**Goal**: Make `https://nextcloud.hus-sky.no` and `https://immich.hus-sky.no` reachable with valid Let's Encrypt certificates so the Nextcloud and Immich mobile apps can connect.

**Independent Test**: `curl -sI https://nextcloud.hus-sky.no | head -1` returns `HTTP/2 200` (or redirect). `echo | openssl s_client -connect nextcloud.hus-sky.no:443 -servername nextcloud.hus-sky.no 2>/dev/null | openssl x509 -noout -issuer` shows `Let's Encrypt`. Repeat for `immich.hus-sky.no`. Nextcloud mobile app connects at `https://nextcloud.hus-sky.no` and file sync completes.

### Implementation for User Story 1

- [X] T008 [P] [US1] Modify `ansible/roles/reverse_proxy/templates/immich.caddy.j2`: replace `:80` site address with `immich.{{ caddy_base_domain }}`, set `header_up X-Forwarded-Proto https`, add `header_up X-Real-IP {remote_host}` and `header_up X-Forwarded-For {remote_host}` per the `caddy-site-block.md` contract (Plan Step 5, FR-001, FR-004). Depends on T003.
- [X] T009 [P] [US1] Modify `ansible/roles/reverse_proxy/templates/nextcloud.caddy.j2`: replace `http://nextcloud.local` site address with `nextcloud.{{ caddy_base_domain }}`, set `header_up X-Forwarded-Proto https`, add standard proxy headers per the `caddy-site-block.md` contract (Plan Step 5, FR-001, FR-004, FR-005). Depends on T003.
- [X] T010 [P] [US1] Modify `ansible/roles/nextcloud/defaults/main.yml`: change `nextcloud_domain` default from `nextcloud.local` to `nextcloud.hus-sky.no`, add `nextcloud_trusted_domains_extra: ["nextcloud.local"]`, add `nextcloud_overwrite_protocol: "https"` (Plan Step 10, FR-007, FR-008, D-004). No dependencies.
- [X] T011 [US1] Modify `ansible/roles/nextcloud/templates/.env.j2`: replace hardcoded `http` with `{{ nextcloud_overwrite_protocol }}` in `OVERWRITEPROTOCOL` and `OVERWRITECLIURL`, update `NEXTCLOUD_TRUSTED_DOMAINS` to include both `{{ nextcloud_domain }}` and each entry from `{{ nextcloud_trusted_domains_extra }}` (e.g., via Jinja2 loop) alongside `{{ nextcloud_ip }}` (Plan Step 10, FR-007, FR-008, R-005). Depends on T010.

**Checkpoint**: User Story 1 fully implementable. `grep 'nextcloud_overwrite_protocol' ansible/roles/nextcloud/templates/.env.j2` returns ≥1 match. `grep 'nextcloud.local' ansible/roles/nextcloud/templates/.env.j2` returns 0 matches (old hardcoded value gone; old domain now comes through the `nextcloud_trusted_domains_extra` variable).

---

## Phase 5: User Story 2 — Browser-Trusted Access to All Services (Priority: P2)

**Goal**: Add HTTPS-proxied site blocks for Grafana, Jellyfin, and Home Assistant (conditional), and update Grafana's root URL so all four active services are browser-accessible at their `hus-sky.no` subdomains.

**Independent Test**: `for svc in grafana jellyfin; do curl -sI https://$svc.hus-sky.no | head -1; done` returns HTTP 200/redirect for each. Browser padlock icon with Let's Encrypt cert visible on all four services. `openssl s_client -connect grafana.hus-sky.no:443 2>/dev/null | openssl x509 -noout -issuer` shows `Let's Encrypt`.

### Implementation for User Story 2

- [X] T012 [P] [US2] Create NEW `ansible/roles/reverse_proxy/templates/grafana.caddy.j2`: site block for `grafana.{{ caddy_base_domain }}` proxying to `{{ monitoring_ip }}:{{ grafana_port }}` with HTTPS headers per `caddy-site-block.md` contract (Plan Step 6, FR-010). Depends on T001, T003.
- [X] T013 [P] [US2] Create NEW `ansible/roles/reverse_proxy/templates/jellyfin.caddy.j2`: site block for `jellyfin.{{ caddy_base_domain }}` proxying to `{{ jellyfin_ip }}:{{ jellyfin_port }}` with HTTPS headers per `caddy-site-block.md` contract (Plan Step 6, FR-010). Depends on T001, T003.
- [X] T015 [P] [US2] Create NEW `ansible/roles/reverse_proxy/templates/homeassistant.caddy.j2`: site block for `ha.{{ caddy_base_domain }}` proxying to `{{ homeassistant_ip }}:{{ homeassistant_port }}` wrapped in `{% if homeassistant_active | default(false) %}...{% endif %}` guard per `caddy-site-block.md` contract (Plan Step 6, FR-015, A-009, D-003). Depends on T001, T003.
- [X] T016 [P] [US2] Modify `ansible/group_vars/monitoring/vars.yml`: change `grafana_domain` from `monitoring.local` to `grafana.hus-sky.no`, add `grafana_protocol: "https"` (Plan Step 11, FR-009, R-006). No dependencies.
- [X] T017 [US2] Modify `ansible/roles/monitoring_stack/templates/docker-compose.yml.j2`: update `GF_SERVER_ROOT_URL` from `http://{{ grafana_domain }}:{{ grafana_port }}` to `{{ grafana_protocol }}://{{ grafana_domain }}` (no port — proxy handles 443). `GF_SERVER_DOMAIN` remains `{{ grafana_domain }}` (Plan Step 11, FR-009, R-006). Depends on T016.

**Checkpoint**: All site templates created and Grafana domain updated. `grep 'caddy_base_domain' ansible/roles/reverse_proxy/templates/grafana.caddy.j2` returns 1 match. `grep 'GF_SERVER_ROOT_URL' ansible/roles/monitoring_stack/templates/docker-compose.yml.j2` does not contain a hardcoded port number.

---

## Phase 6: User Story 3 — Automatic Certificate Lifecycle (Priority: P2)

**Goal**: Replace the stock Caddy APT binary with a custom xcaddy build including the `caddy-dns/lego-deprecated` module, configure the systemd override for secrets injection, and deploy all new site configurations so that Let's Encrypt certificates are issued automatically on first start and renewed without operator intervention.

**Independent Test**: After deployment, `systemctl status caddy` shows active on `192.168.1.211`. `journalctl -u caddy --no-pager | grep 'certificate'` shows certificate obtained events. `openssl s_client -connect nextcloud.hus-sky.no:443 2>/dev/null | openssl x509 -noout -dates` shows `notAfter` ≥ 60 days from today. `caddy version` on the proxy LXC returns a version string containing `lego_deprecated`.

### Implementation for User Story 3

- [X] T018 [US3] Modify `ansible/roles/reverse_proxy/tasks/main.yml`: add the following task blocks in order after the existing APT install tasks: (1) install Go `{{ go_version }}` and xcaddy build tool; (2) build custom Caddy binary with `xcaddy build --with {{ caddy_xcaddy_plugins | join(' --with ') }}` when `caddy_custom_binary` is true; (3) use `dpkg-divert` to prevent APT from overwriting the custom binary; (4) copy the built binary to `/usr/bin/caddy`; (5) create `/etc/systemd/system/caddy.service.d/` directory; (6) template `domeneshop.env.j2` to `/etc/caddy/domeneshop.env` with `mode: '0600'` (notifies `Reload systemd` then `Restart caddy`); (7) template `caddy-domeneshop.conf.j2` to `/etc/systemd/system/caddy.service.d/domeneshop.conf` (notifies `Reload systemd` then `Restart caddy`); (8) add deploy tasks for `grafana.caddy.j2`, `jellyfin.caddy.j2`, and `homeassistant.caddy.j2` to `{{ caddy_conf_dir }}/` (each with `caddy validate` in validate parameter, notifies `Restart caddy`) (Plan Step 8, FR-012, FR-013, FR-010, R-002, R-003, D-005, D-006). Depends on T004, T005, T006, T007, T008, T009, T012, T013, T015.

**Checkpoint**: `ansible-lint ansible/roles/reverse_proxy` returns exit 0. `grep -c 'xcaddy' ansible/roles/reverse_proxy/tasks/main.yml` ≥ 1. `grep -c 'domeneshop.env' ansible/roles/reverse_proxy/tasks/main.yml` ≥ 1. `grep -c 'grafana.caddy' ansible/roles/reverse_proxy/tasks/main.yml` ≥ 1.

---

## Phase 7: User Story 4 — Graceful Migration from HTTP to HTTPS (Priority: P3)

**Goal**: Preserve all existing service data, user accounts, and settings during the domain migration.

**Note**: US4 has **no unique implementation tasks**. It is fully satisfied by tasks already defined in earlier phases:
- **FR-007** (Nextcloud HTTPS protocol): T010 + T011
- **FR-008** (Nextcloud dual-domain trust for `nextcloud.local`): T010 + T011 — `nextcloud_trusted_domains_extra` includes `nextcloud.local` indefinitely per D-004
- **FR-009** (Grafana root URL update): T016 + T017
- **FR-016** (Data preservation): No data migration is needed — only URL/protocol configuration changes. All data remains in existing Docker volumes and NFS mounts.

The rollback procedure in `quickstart.md` documents how to revert if migration fails (already authored in the quickstart document).

**Independent Test**: After deployment via `ansible-playbook playbooks/services.yml --tags reverse_proxy` and `ansible-playbook playbooks/nextcloud.yml`: Nextcloud user accounts and files accessible at `https://nextcloud.hus-sky.no`. All Immich photos present. All Grafana dashboards intact at `https://grafana.hus-sky.no`. (Acceptance per SC-006.)

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Static analysis and secrets audit across all modified files. Verifies constitution principles II (secrets) and IV (dual-provisioning parity).

**Done-condition checkpoint**:
- `ansible-lint ansible/roles/reverse_proxy ansible/roles/nextcloud ansible/roles/monitoring_stack` exits 0
- `ansible-playbook --syntax-check playbooks/services.yml -i inventories/prod/hosts.yml` exits 0
- `ansible-playbook --syntax-check playbooks/monitoring.yml -i inventories/prod/hosts.yml` exits 0
- `rg 'DOMENESHOP_API_TOKEN=[^{]' . --type-not yaml` from repo root returns 0 matches
- `rg 'DOMENESHOP_API_SECRET=[^{]' . --type-not yaml` from repo root returns 0 matches

- [X] T019 Run static analysis: `ansible-lint ansible/roles/reverse_proxy ansible/roles/nextcloud ansible/roles/monitoring_stack`; run `ansible-playbook --syntax-check` for `playbooks/services.yml` and `playbooks/monitoring.yml`; run `rg 'DOMENESHOP_API_TOKEN=[^{]'` and `rg 'DOMENESHOP_API_SECRET=[^{]'` from repo root. Fix all errors before marking complete (Plan Step 12, SC-005, SC-007, FR-014, constitution II, constitution IV). Depends on T018.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately, all tasks parallel
- **Foundational (Phase 2)**: T004 depends on T003. T005 has no dependencies. Both block US story phases.
- **US5 (Phase 3)**: T006, T007 depend on T002. Can start in parallel with Phase 2.
- **US1 (Phase 4)**: T008, T009 depend on T003. T010 is independent. T011 depends on T010.
- **US2 (Phase 5)**: T012–T015 depend on T001 and T003. T016 is independent. T017 depends on T016.
- **US3 (Phase 6)**: T018 depends on T004, T005, T006, T007, T008, T009, T012, T013, T015 — all template tasks complete.
- **Polish (Phase 8)**: T019 depends on T018 (all changes in place).

### User Story Dependencies

- **US5 (P1)**: Depends on T002 from Setup. No story-level dependencies.
- **US1 (P1)**: Depends on T003 (for caddy_base_domain). No dependency on US5 for template files, but US5 must be complete before deployment works end-to-end.
- **US2 (P2)**: Depends on T001, T003. Independent from US1 at the file level.
- **US3 (P2)**: Depends on all template tasks (US1, US2, US5 all complete). T018 is the integration step.
- **US4 (P3)**: Covered entirely by US1 (T010, T011) and US2 (T016, T017). No additional tasks.

### Within Each User Story

- Template tasks within a story are parallel-safe (different files)
- Defaults-before-template ordering applies: T010 before T011, T016 before T017
- Integration task T018 must be last among implementation tasks (all templates must exist)

### Dependency Graph

```
T001 ─────────────────────────────────────────┐
T002 ──► T006 ─────────────────────────────── │
         T007 ─────────────────────────────── │
T003 ──► T004 ─────────────────────────────── ├──► T018 ──► T019
         T005 ─────────────────────────────── │
         T008 ─────────────────────────────── │
         T009 ─────────────────────────────── │
         T012 ─────────────────────────────── │
         T013 ─────────────────────────────── │
         T015 ─────────────────────────────── │
T010 ──► T011 ─────────────────────────────── │
T016 ──► T017 ─────────────────────────────── ┘
```

## Implementation Order

1. **Immediately (parallel)**: T001, T002, T003, T005 — no dependencies at all
2. **After T003**: T004, T008, T009, T012, T013, T015
3. **After T002**: T006, T007
4. **After T010**: T011
5. **After T016**: T017
6. **After all of the above**: T018 (integration step)
7. **After T018**: T019 (verification)

---

## Parallel Examples

### Phase 1 — All setup tasks in parallel

```bash
# All three can be executed simultaneously:
Task: "Add service IPs/ports to ansible/group_vars/services/vars.yml"   # T001
Task: "Add vault entries to ansible/group_vars/services/vault.yml"       # T002
Task: "Update reverse proxy role defaults in defaults/main.yml"          # T003
```

### Phases 4 & 5 — Templates in parallel after T003

```bash
# All can execute simultaneously (different files):
Task: "Update immich.caddy.j2 to FQDN + HTTPS"                         # T008
Task: "Update nextcloud.caddy.j2 to FQDN + HTTPS"                      # T009
Task: "Create grafana.caddy.j2"                                          # T012
Task: "Create jellyfin.caddy.j2"                                         # T013
Task: "Create homeassistant.caddy.j2"                                    # T015
Task: "Update nextcloud/defaults/main.yml for HTTPS vars"               # T010
Task: "Update monitoring/vars.yml for grafana domain/protocol"          # T016
```

---

## Implementation Strategy

### MVP First (User Stories 5 + 1 Only)

1. Complete Phase 1: Setup (T001, T002, T003)
2. Complete Phase 2: Foundational (T004, T005) — **CRITICAL: blocks everything**
3. Complete Phase 3: US5 Secrets (T006, T007)
4. Complete Phase 4: US1 Mobile Connectivity (T008, T009, T010, T011)
5. Complete Phase 6: US3 Cert Lifecycle (T018 — xcaddy build + systemd secrets only, skip new site templates T012–T015)
6. **STOP and VALIDATE**: Deploy to proxy LXC, test Nextcloud + Immich mobile apps
7. Verify `https://nextcloud.hus-sky.no` and `https://immich.hus-sky.no` work with Let's Encrypt certs

### Full Delivery

8. Add Phase 5: US2 Browser Access (T012–T017)
9. Update T018 to include new site template deploy tasks (if not already done)
10. Complete Phase 8: Polish (T019)
11. **Deploy and validate all 5 services**

### Single-Operator Strategy (sequential)

1. T001 → T002 → T003 (Setup)
2. T004 → T005 (Foundational)
3. T006 → T007 (US5)
4. T008 → T009 → T010 → T011 (US1)
5. T012 → T013 → T015 → T016 → T017 (US2)
6. T018 (Integration)
7. T019 (Verify)

---

## Summary

- **Total tasks**: 19
- **Estimated complexity**: Medium
- **Parallel tracks**: 4 independent tracks identified (vars, vault, defaults, handlers in Phase 1+2; templates in US1+US2 phases)
- **No test tasks**: Tests not requested in spec; verification via ansible-lint, syntax-check, openssl s_client
- **Files created (NEW)**: 6 files
  - `ansible/roles/reverse_proxy/templates/domeneshop.env.j2`
  - `ansible/roles/reverse_proxy/templates/caddy-domeneshop.conf.j2`
  - `ansible/roles/reverse_proxy/templates/grafana.caddy.j2`
  - `ansible/roles/reverse_proxy/templates/jellyfin.caddy.j2`
  - `ansible/roles/reverse_proxy/templates/homeassistant.caddy.j2`
- **Files modified (EXISTING)**: 12 files
  - `ansible/group_vars/services/vars.yml`
  - `ansible/group_vars/services/vault.yml`
  - `ansible/group_vars/monitoring/vars.yml`
  - `ansible/roles/reverse_proxy/defaults/main.yml`
  - `ansible/roles/reverse_proxy/tasks/main.yml`
  - `ansible/roles/reverse_proxy/handlers/main.yml`
  - `ansible/roles/reverse_proxy/templates/Caddyfile.j2`
  - `ansible/roles/reverse_proxy/templates/immich.caddy.j2`
  - `ansible/roles/reverse_proxy/templates/nextcloud.caddy.j2`
  - `ansible/roles/nextcloud/defaults/main.yml`
  - `ansible/roles/nextcloud/templates/.env.j2`
  - `ansible/roles/monitoring_stack/templates/docker-compose.yml.j2`
- **Constitution check**: All principles PASS (carried forward from plan.md — no violations introduced by task decomposition)
