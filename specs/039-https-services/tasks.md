# Tasks: HTTPS for All Homelab Services

**Branch**: `039-https-services` | **Date**: 2026-02-28
**Input**: Design documents from `/specs/039-https-services/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅

**Tests**: Not requested — validation is via `ansible-lint`, `ansible-playbook --syntax-check`, `caddy validate` (on-target), and `rg` secrets audit (IaC project).

**Organization**: Tasks grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1–US5 from spec.md)
- Exact file paths included in every description

---

## Summary

- **Total tasks**: 21
- **Estimated complexity**: Medium-High (Ansible-only; ~8 new files, ~8 modified files, no Terraform changes)
- **Parallel tracks**: 3 independent tracks in Phase 1 (group_vars, vault, role defaults); 4 parallel tracks in Phase 2 (templates + handler); 6 parallel site block tasks in Phases 4–5
- **MVP scope**: Phases 1–4 → HTTPS working for Nextcloud and Immich mobile apps (US1, US3, US5)
- **Plan gap addressed**: `ansible/playbooks/reverse_proxy.yml` does not exist but is required by `scripts/lab/pve-service-deploy` (which expects `playbooks/${SERVICE}.yml`). Added as T017. Traces to FR-014 and Constitution IV.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Centralize all service IP/port variables needed by the reverse proxy role, add vault secrets, and define role defaults for the HTTPS configuration. No user story label — this is shared infrastructure required by all stories.

- [ ] T001 [P] Add service IP/port variables to `ansible/group_vars/services/vars.yml`: append `nextcloud_port: 8080`, `jellyfin_ip: "192.168.1.215"`, `jellyfin_port: 8096`, `adguard_ip: "192.168.1.210"`, `adguard_web_port: 3000`, `homeassistant_ip: "192.168.1.212"`, `homeassistant_port: 8123`, `monitoring_ip: "192.168.1.214"`, `grafana_port: 3000` under a new `# Reverse Proxy — backend addresses` comment block. These are needed because the reverse_proxy role runs on a different host than the service roles, so role defaults are not in scope — group_vars is the cross-host mechanism.
  - **Source**: A-007 (backend IPs/ports), data-model E-001 (Service Subdomain Mapping), terraform `environments/prod.tfvars.template` lines 41–52 (IP provenance)
  - **Done-condition**: `grep -c 'jellyfin_ip\|adguard_ip\|homeassistant_ip\|monitoring_ip\|nextcloud_port\|grafana_port' ansible/group_vars/services/vars.yml` returns 6. No duplicate variable definitions within the file.

- [ ] T002 [P] Add Domeneshop API credentials to `ansible/group_vars/services/vault.yml`: add `domeneshop_api_token: "OPERATOR_MUST_REPLACE"` and `domeneshop_api_secret: "OPERATOR_MUST_REPLACE"` entries using `ansible-vault edit`. These are placeholder values — the operator replaces them with real credentials before first deploy (per quickstart.md §2).
  - **Traces to**: FR-013, US-5
  - **Done-condition**: `ansible-vault view ansible/group_vars/services/vault.yml` (with vault password) shows both `domeneshop_api_token` and `domeneshop_api_secret` keys. `rg 'domeneshop' ansible/ --glob '!vault.yml' --glob '!*.j2' --glob '!defaults/*'` returns zero matches in non-template, non-default files (secrets not leaked).

- [ ] T003 [P] Update reverse proxy role defaults in `ansible/roles/reverse_proxy/defaults/main.yml`: add variables `caddy_base_domain: "hus-sky.no"`, `caddy_acme_dns_provider: "lego_deprecated"`, `caddy_acme_dns_provider_name: "domeneshop"`, `caddy_custom_binary: true`, `caddy_xcaddy_plugins: ["github.com/caddy-dns/lego-deprecated"]`, `go_version: "1.22.0"`, `homeassistant_active: false`. Retain existing `caddy_conf_dir: /etc/caddy/conf.d`.
  - **Traces to**: FR-001 (base domain), FR-012 (custom binary), FR-015 (HA conditional), R-001 (lego_deprecated), R-002 (Go version)
  - **Done-condition**: All 7 new variables present in `ansible/roles/reverse_proxy/defaults/main.yml` alongside existing `caddy_conf_dir`. File is valid YAML (`python3 -c "import yaml; yaml.safe_load(open('ansible/roles/reverse_proxy/defaults/main.yml'))"`).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Create all templates and handler updates that MUST exist before the main task file (T008) can be written. Templates define the rendered config files; the handler provides the daemon-reload trigger.

**⚠️ CRITICAL**: T004–T007 must complete before T008 can begin (T008 references these templates and handlers by name).

- [ ] T004 [P] [US5] Create `ansible/roles/reverse_proxy/templates/domeneshop.env.j2` per contract `contracts/systemd-override.md`: file contains `# Managed by Ansible — DO NOT EDIT MANUALLY`, `DOMENESHOP_API_TOKEN={{ domeneshop_api_token }}`, `DOMENESHOP_API_SECRET={{ domeneshop_api_secret }}`. No blank lines between key-value pairs (systemd EnvironmentFile format).
  - **Traces to**: FR-013, US-5, D-006, R-003
  - **Done-condition**: File exists at the specified path. File contains exactly the two variable references `{{ domeneshop_api_token }}` and `{{ domeneshop_api_secret }}`. No hardcoded credential values in the file.

- [ ] T005 [P] [US5] Create `ansible/roles/reverse_proxy/templates/caddy-domeneshop.conf.j2` per contract `contracts/systemd-override.md`: file contains `# Managed by Ansible — DO NOT EDIT MANUALLY`, `[Service]`, `EnvironmentFile=/etc/caddy/domeneshop.env`.
  - **Traces to**: FR-013, US-5, D-006, R-003
  - **Done-condition**: File exists at the specified path. File contains `[Service]` section header and `EnvironmentFile=/etc/caddy/domeneshop.env` directive.

- [ ] T006 [P] [US3] Update `ansible/roles/reverse_proxy/templates/Caddyfile.j2` per contract `contracts/caddyfile-global.md`: (1) REMOVE `auto_https off` line, (2) ADD `acme_dns {{ caddy_acme_dns_provider }} {{ caddy_acme_dns_provider_name }}` inside the global options block, (3) RETAIN `log { output stdout }` and `import {{ caddy_conf_dir }}/*.caddy`. Final file should match the contract exactly.
  - **Traces to**: FR-011 (remove auto_https off), FR-002 (DNS-01 challenges), FR-003 (auto-renewal), R-008 (global acme_dns)
  - **Done-condition**: File does NOT contain `auto_https off`. File contains `acme_dns {{ caddy_acme_dns_provider }} {{ caddy_acme_dns_provider_name }}` inside the global block. File still contains `import {{ caddy_conf_dir }}/*.caddy`. Jinja2 syntax is valid (`python3 -c "from jinja2 import Environment; Environment().parse(open('ansible/roles/reverse_proxy/templates/Caddyfile.j2').read())"`).

- [ ] T007 [P] [US5] Update `ansible/roles/reverse_proxy/handlers/main.yml`: add a `Reload systemd` handler (`ansible.builtin.systemd: daemon_reload: true`) BEFORE the existing `Restart caddy` handler. Handler ordering matters — daemon-reload must execute before restart so the systemd override is loaded.
  - **Traces to**: FR-013 (secrets injection requires daemon-reload after override deploy), contract `systemd-override.md`
  - **Done-condition**: Handler file contains both `Reload systemd` and `Restart caddy` handlers. `Reload systemd` appears before `Restart caddy` in the file. `Reload systemd` uses `ansible.builtin.systemd` with `daemon_reload: true`.

**Checkpoint**: All templates and handlers exist. T008 can now reference them.

---

## Phase 3: US5 — Secrets Security (P1) + US3 — Certificate Lifecycle (P1)

**Goal**: Replace stock Caddy with custom xcaddy build including lego-deprecated DNS module, deploy systemd secrets injection, and wire up all site block deployments. This is the core orchestration task.

**Independent Test**: After deployment, `caddy list-modules | grep lego` returns the lego_deprecated module. `/etc/caddy/domeneshop.env` exists with mode 0600 owned by root. `systemctl show caddy --property=EnvironmentFiles` shows the env file is loaded.

- [ ] T008 [US5/US3] Rewrite `ansible/roles/reverse_proxy/tasks/main.yml` with the following task sequence (preserving existing functionality, adding new tasks):
  1. **Keep existing**: Install prerequisites (apt: debian-keyring, apt-transport-https, curl), Add Caddy GPG key, Add Caddy repository, Install Caddy
  2. **NEW — Go installation**: Install Go {{ go_version }} from `https://go.dev/dl/go{{ go_version }}.linux-amd64.tar.gz` to `/usr/local/go` (with `creates: /usr/local/go/bin/go` for idempotency)
  3. **NEW — xcaddy installation**: Install xcaddy via `go install github.com/caddyserver/xcaddy/cmd/xcaddy@latest` with `PATH=/usr/local/go/bin:{{ ansible_env.PATH }}` and `GOPATH=/opt/xcaddy-build`
  4. **NEW — Build custom binary**: Run `xcaddy build --with {{ caddy_xcaddy_plugins | join(' --with ') }}` in `/opt/xcaddy-build`, producing `/opt/xcaddy-build/caddy`. Conditional: `when: caddy_custom_binary | default(false)`. Register result for changed_when.
  5. **NEW — dpkg-divert**: Run `dpkg-divert --divert /usr/bin/caddy.dpkg-dist --rename /usr/bin/caddy` to protect custom binary from APT overwrites. Conditional: `when: caddy_custom_binary | default(false)`. Idempotent (check if divert already exists).
  6. **NEW — Install custom binary**: Copy `/opt/xcaddy-build/caddy` to `/usr/bin/caddy` with mode 0755, owner root. Conditional: `when: caddy_custom_binary | default(false)`. Notify `Restart caddy`.
  7. **Keep existing**: Ensure Caddy configuration directory exists
  8. **MODIFIED — Deploy main Caddyfile**: Existing template task, unchanged (validate step now works because custom binary is installed first). Notify `Restart caddy`.
  9. **Keep existing**: Ensure Caddy service is enabled and running
  10. **NEW — Create systemd override directory**: `file: path=/etc/systemd/system/caddy.service.d state=directory mode=0755`
  11. **NEW — Deploy Domeneshop env file**: Template `domeneshop.env.j2` to `/etc/caddy/domeneshop.env` with `mode: '0600'`, `owner: root`, `group: root`. Notify: `[Reload systemd, Restart caddy]`.
  12. **NEW — Deploy systemd drop-in override**: Template `caddy-domeneshop.conf.j2` to `/etc/systemd/system/caddy.service.d/domeneshop.conf` with `mode: '0644'`. Notify: `[Reload systemd, Restart caddy]`.
  13. **MODIFIED — Deploy Immich Caddy configuration**: Existing task, unchanged in structure (template src=immich.caddy.j2). Notify `Restart caddy`.
  14. **MODIFIED — Deploy Nextcloud Caddy configuration**: Existing task, unchanged in structure (template src=nextcloud.caddy.j2). Notify `Restart caddy`.
  15. **NEW — Deploy Grafana Caddy configuration**: Template `grafana.caddy.j2` to `{{ caddy_conf_dir }}/grafana.caddy`, mode 0644, validate `caddy validate --adapter caddyfile --config %s`. Notify `Restart caddy`.
  16. **NEW — Deploy Jellyfin Caddy configuration**: Template `jellyfin.caddy.j2` to `{{ caddy_conf_dir }}/jellyfin.caddy`, mode 0644, validate. Notify `Restart caddy`.
  17. **NEW — Deploy AdGuard Caddy configuration**: Template `adguard.caddy.j2` to `{{ caddy_conf_dir }}/adguard.caddy`, mode 0644, validate. Notify `Restart caddy`.
  18. **NEW — Deploy Home Assistant Caddy configuration** (conditional): Template `homeassistant.caddy.j2` to `{{ caddy_conf_dir }}/homeassistant.caddy`, mode 0644, validate. `when: homeassistant_active | default(false)`. Notify `Restart caddy`.
  - **Dependencies**: T001 (service IPs/ports), T002 (vault vars), T003 (role defaults), T004-T007 (templates + handlers)
  - **Traces to**: FR-012 (custom binary), FR-013 (secrets injection), FR-010 (new site blocks), FR-001 (HTTPS for all services), FR-004 (TLS termination), R-002 (xcaddy), R-003 (systemd EnvironmentFile)
  - **Done-condition**: `ansible-lint ansible/roles/reverse_proxy/tasks/main.yml` returns 0. File contains tasks for: Go installation, xcaddy build, dpkg-divert, custom binary install, systemd override directory creation, domeneshop.env deploy, systemd drop-in deploy, and deploy tasks for all 6 site blocks (immich, nextcloud, grafana, jellyfin, adguard, homeassistant). The Go/xcaddy/binary tasks are conditional on `caddy_custom_binary`. The homeassistant deploy task is conditional on `homeassistant_active`.

**Checkpoint**: Reverse proxy role is complete. HTTPS infrastructure is in place. US5 (secrets) and US3 (cert lifecycle) are satisfied once deployed.

---

## Phase 4: US1 — Mobile App Connectivity via HTTPS (P1) 🎯 MVP

**Goal**: Update existing Caddy site blocks for Immich and Nextcloud to use FQDN addresses with HTTPS headers, enabling mobile app connectivity.

**Independent Test**: After deployment, `curl -sI https://immich.hus-sky.no` returns HTTP 200 with valid cert. Immich mobile app connects to `https://immich.hus-sky.no`.

- [ ] T009 [P] [US1] Update `ansible/roles/reverse_proxy/templates/immich.caddy.j2` per contract `contracts/caddy-site-block.md` — Immich section: replace `:80` site address with `immich.{{ caddy_base_domain }}`, change `header_up X-Forwarded-Proto http` to `https`, add `header_up X-Real-IP {remote_host}` and `header_up X-Forwarded-For {remote_host}` inside the `reverse_proxy` block (matching the nextcloud pattern).
  - **Traces to**: FR-001, FR-004, contract caddy-site-block.md (Immich section)
  - **Done-condition**: File does NOT contain `:80`. File contains `immich.{{ caddy_base_domain }}` as the site address. `X-Forwarded-Proto` is `https`. Headers `X-Real-IP` and `X-Forwarded-For` are present. Jinja2 syntax is valid.

- [ ] T010 [P] [US1] Update `ansible/roles/reverse_proxy/templates/nextcloud.caddy.j2` per contract `contracts/caddy-site-block.md` — Nextcloud section: replace `http://nextcloud.local` site address with `nextcloud.{{ caddy_base_domain }}`, change `header_up X-Forwarded-Proto http` to `https`. Retain existing `X-Real-IP` and `X-Forwarded-For` headers.
  - **Traces to**: FR-001, FR-004, FR-007 (new domain), contract caddy-site-block.md (Nextcloud section)
  - **Done-condition**: File does NOT contain `http://nextcloud.local`. File contains `nextcloud.{{ caddy_base_domain }}` as the site address. `X-Forwarded-Proto` is `https`. Existing `X-Real-IP` and `X-Forwarded-For` headers retained. Jinja2 syntax is valid.

**Checkpoint**: Immich and Nextcloud accessible via HTTPS with FQDN addresses. US1 acceptance: mobile apps connect successfully.

---

## Phase 5: US2 — Browser-Trusted Access to All Services (P2)

**Goal**: Create new Caddy site block templates for Grafana, Jellyfin, AdGuard, and Home Assistant (placeholder), enabling browser-trusted HTTPS access for all services.

**Independent Test**: After deployment, `curl -sI https://grafana.hus-sky.no` returns HTTP 200 with valid Let's Encrypt cert. Repeat for jellyfin and adguard.

- [ ] T011 [P] [US2] Create `ansible/roles/reverse_proxy/templates/grafana.caddy.j2` per contract `contracts/caddy-site-block.md` — Grafana section: site address `grafana.{{ caddy_base_domain }}`, reverse_proxy to `{{ monitoring_ip }}:{{ grafana_port }}`, standard HTTPS proxy headers (`X-Forwarded-Proto https`, `X-Real-IP {remote_host}`, `X-Forwarded-For {remote_host}`).
  - **Traces to**: FR-010, contract caddy-site-block.md (Grafana section)
  - **Done-condition**: File exists. Site address is `grafana.{{ caddy_base_domain }}`. Backend is `{{ monitoring_ip }}:{{ grafana_port }}`. All three proxy headers present. Jinja2 syntax is valid.

- [ ] T012 [P] [US2] Create `ansible/roles/reverse_proxy/templates/jellyfin.caddy.j2` per contract `contracts/caddy-site-block.md` — Jellyfin section: site address `jellyfin.{{ caddy_base_domain }}`, reverse_proxy to `{{ jellyfin_ip }}:{{ jellyfin_port }}`, standard HTTPS proxy headers.
  - **Traces to**: FR-010, contract caddy-site-block.md (Jellyfin section)
  - **Done-condition**: File exists. Site address is `jellyfin.{{ caddy_base_domain }}`. Backend is `{{ jellyfin_ip }}:{{ jellyfin_port }}`. All three proxy headers present. Jinja2 syntax is valid.

- [ ] T013 [P] [US2] Create `ansible/roles/reverse_proxy/templates/adguard.caddy.j2` per contract `contracts/caddy-site-block.md` — AdGuard section: site address `adguard.{{ caddy_base_domain }}`, reverse_proxy to `{{ adguard_ip }}:{{ adguard_web_port }}`, standard HTTPS proxy headers.
  - **Traces to**: FR-010, contract caddy-site-block.md (AdGuard section)
  - **Done-condition**: File exists. Site address is `adguard.{{ caddy_base_domain }}`. Backend is `{{ adguard_ip }}:{{ adguard_web_port }}`. All three proxy headers present. Jinja2 syntax is valid.

- [ ] T014 [P] [US2] Create `ansible/roles/reverse_proxy/templates/homeassistant.caddy.j2` per contract `contracts/caddy-site-block.md` — Home Assistant section (conditional): entire config wrapped in `{% if homeassistant_active | default(false) %}...{% endif %}`. Site address `ha.{{ caddy_base_domain }}`, reverse_proxy to `{{ homeassistant_ip }}:{{ homeassistant_port }}`, standard HTTPS proxy headers.
  - **Traces to**: FR-015, A-009, D-003, contract caddy-site-block.md (Home Assistant section)
  - **Done-condition**: File exists. Contains `{% if homeassistant_active | default(false) %}` guard. Site address is `ha.{{ caddy_base_domain }}` (not `homeassistant`). Backend is `{{ homeassistant_ip }}:{{ homeassistant_port }}`. Jinja2 syntax is valid.

**Checkpoint**: All 5 active service site blocks + 1 conditional placeholder exist. US2 acceptance: all services present valid Let's Encrypt certificates.

---

## Phase 6: US4 — Graceful Migration from HTTP to HTTPS (P3)

**Goal**: Migrate Nextcloud and Grafana to their new HTTPS domains, preserving all existing data, users, and settings. Nextcloud trusts both old and new domains for backward compatibility.

**Independent Test**: After deployment, existing Nextcloud users and files are accessible at `https://nextcloud.hus-sky.no`. Grafana dashboards are intact at `https://grafana.hus-sky.no`.

- [ ] T015 [P] [US4] Update Nextcloud domain configuration — two files:
  (a) `ansible/roles/nextcloud/defaults/main.yml`: change `nextcloud_domain: "nextcloud.local"` to `nextcloud_domain: "nextcloud.hus-sky.no"`, add `nextcloud_trusted_domains_extra: ["nextcloud.local"]`, add `nextcloud_overwrite_protocol: "https"`.
  (b) `ansible/roles/nextcloud/templates/.env.j2`: change `OVERWRITEPROTOCOL=http` to `OVERWRITEPROTOCOL={{ nextcloud_overwrite_protocol | default('https') }}`, change `OVERWRITECLIURL=http://{{ nextcloud_domain }}` to `OVERWRITECLIURL={{ nextcloud_overwrite_protocol | default('https') }}://{{ nextcloud_domain }}`, change `NEXTCLOUD_TRUSTED_DOMAINS={{ nextcloud_domain }} {{ nextcloud_ip }}` to `NEXTCLOUD_TRUSTED_DOMAINS={{ nextcloud_domain }} {{ nextcloud_ip }}{{ ' ' + nextcloud_trusted_domains_extra | join(' ') if nextcloud_trusted_domains_extra is defined and nextcloud_trusted_domains_extra | length > 0 else '' }}`.
  - **Traces to**: FR-007 (new domain + HTTPS), FR-008 (dual-domain trust), FR-016 (data preserved — only URL/protocol changes), D-004 (both domains trusted indefinitely), R-005
  - **Done-condition**: `nextcloud_domain` in defaults is `nextcloud.hus-sky.no`. `nextcloud_trusted_domains_extra` contains `nextcloud.local`. `.env.j2` renders `OVERWRITEPROTOCOL=https` and `OVERWRITECLIURL=https://nextcloud.hus-sky.no`. `NEXTCLOUD_TRUSTED_DOMAINS` includes both `nextcloud.hus-sky.no` and `nextcloud.local`. Jinja2 syntax of `.env.j2` is valid.

- [ ] T016 [P] [US4] Update Grafana domain configuration — three files:
  (a) `ansible/group_vars/monitoring/vars.yml`: change `grafana_domain: "monitoring.local"` to `grafana_domain: "grafana.hus-sky.no"`, add `grafana_protocol: "https"`.
  (b) `ansible/roles/monitoring_stack/defaults/main.yml`: add `grafana_protocol: "http"` as a safe default (below existing `grafana_domain` line).
  (c) `ansible/roles/monitoring_stack/templates/docker-compose.yml.j2`: change `GF_SERVER_ROOT_URL=http://{{ grafana_domain }}:{{ grafana_port }}` to `GF_SERVER_ROOT_URL={{ grafana_protocol | default('https') }}://{{ grafana_domain }}` (port removed — users access via reverse proxy on 443, not directly on 3000).
  - **Traces to**: FR-009 (Grafana root URL), R-006
  - **Done-condition**: `grafana_domain` in group_vars/monitoring/vars.yml is `grafana.hus-sky.no`. `grafana_protocol: "https"` is present in group_vars. `grafana_protocol: "http"` default is in monitoring_stack role defaults. `GF_SERVER_ROOT_URL` in docker-compose template does NOT contain `:{{ grafana_port }}` and uses `{{ grafana_protocol | default('https') }}://{{ grafana_domain }}`. Jinja2 syntax of docker-compose template is valid.

**Checkpoint**: Domain migration configured for both Nextcloud and Grafana. US4 acceptance: existing data, accounts, and dashboards accessible at new HTTPS URLs.

---

## Phase 7: Integration (Cross-Cutting)

**Purpose**: Create the reverse proxy playbook (missing from repo) and add it to the services aggregator. Required for CI/CD deployment and Constitution IV (Dual-Provisioning Parity).

- [ ] T017 [P] Create `ansible/playbooks/reverse_proxy.yml` following the pattern of `ansible/playbooks/jellyfin.yml` and `ansible/playbooks/adguard.yml`: two plays — (1) `hosts: reverse_proxy, become: true, roles: [lxc_base]`, (2) `hosts: reverse_proxy, become: true, roles: [reverse_proxy]`. This playbook is required by `scripts/lab/pve-service-deploy` which runs `ansible-playbook playbooks/${SERVICE}.yml`.
  - **Traces to**: FR-014, Constitution IV (Dual-Provisioning Parity)
  - **Done-condition**: File exists at `ansible/playbooks/reverse_proxy.yml`. File has two plays targeting `hosts: reverse_proxy`. First play includes `lxc_base` role. Second play includes `reverse_proxy` role. `ansible-playbook --syntax-check ansible/playbooks/reverse_proxy.yml` passes (when run from `ansible/` directory with proper inventory).

- [ ] T018 Add reverse proxy import to `ansible/playbooks/services.yml`: append `- name: Configure Reverse Proxy` / `import_playbook: reverse_proxy.yml` / `tags: reverse_proxy` following the existing pattern (after the Nextcloud import). This enables `ansible-playbook playbooks/services.yml --tags reverse_proxy` from a developer laptop and includes the reverse proxy in the `site.yml → services.yml` chain.
  - **Traces to**: FR-014, Constitution IV
  - **Done-condition**: `ansible/playbooks/services.yml` contains `import_playbook: reverse_proxy.yml` with `tags: reverse_proxy`. `ansible-playbook --syntax-check ansible/playbooks/services.yml` passes (when run from `ansible/` directory with proper inventory).

---

## Phase 8: Verification

**Purpose**: Static analysis to catch errors before deployment. All verification tasks depend on Phases 1–7 being complete.

- [ ] T019 Run `ansible-lint` on all modified roles: `ansible-lint ansible/roles/reverse_proxy ansible/roles/nextcloud ansible/roles/monitoring_stack`. Fix any errors or warnings. Ignore rules that are pre-existing (not introduced by this feature).
  - **Traces to**: SC-007 (deployment works), constitution Test-Driven Changes
  - **Done-condition**: `ansible-lint` returns exit code 0 for all three roles (or only pre-existing warnings remain).

- [ ] T020 Run `ansible-playbook --syntax-check` on affected playbooks: `ansible-playbook --syntax-check ansible/playbooks/reverse_proxy.yml`, `ansible-playbook --syntax-check ansible/playbooks/services.yml`, `ansible-playbook --syntax-check ansible/playbooks/nextcloud.yml`, `ansible-playbook --syntax-check ansible/playbooks/monitoring.yml`. Fix any syntax errors.
  - **Traces to**: SC-007, FR-014
  - **Done-condition**: All four `--syntax-check` commands return exit code 0.

- [ ] T021 Run secrets audit: execute `rg 'DOMENESHOP_API_TOKEN|DOMENESHOP_API_SECRET|domeneshop_api_token|domeneshop_api_secret' . --glob '!vault.yml' --glob '!*.j2' --glob '!defaults/main.yml' --glob '!specs/**' --glob '!docs/**'` from repository root. This confirms credentials are never hardcoded outside of vault, template, and default-value files.
  - **Traces to**: SC-005, FR-013, US-5, Constitution II (Secrets Policy)
  - **Done-condition**: The grep command returns zero matches. No Domeneshop credential values appear in any committed file outside of: vault.yml (encrypted), .j2 templates (Jinja references), defaults/main.yml (variable names only), and documentation.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — T001, T002, T003 all parallel-safe (different files)
- **Foundational (Phase 2)**: No dependency on Phase 1 for T004, T005, T007. T006 is independent. All parallel-safe.
- **US5+US3 (Phase 3)**: T008 depends on ALL of Phase 1 (T001–T003) AND Phase 2 (T004–T007) — it references all templates, handlers, and variables by name
- **US1 (Phase 4)**: T009, T010 depend on T003 (caddy_base_domain variable). Parallel with each other. Can start once T003 is complete.
- **US2 (Phase 5)**: T011–T014 depend on T001 (service IPs/ports) and T003 (caddy_base_domain). Parallel with each other and with Phase 4.
- **US4 (Phase 6)**: T015, T016 have no dependencies on other phases — they modify different roles (nextcloud, monitoring_stack). Parallel with each other and Phases 3–5.
- **Integration (Phase 7)**: T017 is independent. T018 depends on T017 (playbook must exist before import).
- **Verification (Phase 8)**: T019–T021 depend on ALL previous phases.

### Dependency Graph

```
T001 ───────────────────────────────────┐
T002 ───────────────────────────────────┤
T003 ──────────┬────────────────────────┤
               │                        │
T004 ──────────┤                        │
T005 ──────────┤                        │
T006 ──────────┼────────────────────────┼──► T008 (tasks/main.yml)
T007 ──────────┘                        │
                                        │
T009 ◄── T003 (caddy_base_domain)       │
T010 ◄── T003 (caddy_base_domain)       │
                                        │
T011 ◄── T001 + T003                    │
T012 ◄── T001 + T003                    │
T013 ◄── T001 + T003                    │
T014 ◄── T001 + T003                    │
                                        │
T015 ──── (independent)                 │
T016 ──── (independent)                 │
                                        │
T017 ──── (independent)                 │
T018 ◄── T017                           │
                                        │
T019 ◄── all previous ─────────────────┘
T020 ◄── all previous
T021 ◄── all previous
```

### Parallel Batches

| Batch | Tasks | Precondition |
|-------|-------|--------------|
| Batch 1 | T001, T002, T003, T004, T005, T006, T007, T015, T016, T017 | None — all parallel |
| Batch 2 | T008, T009, T010, T011, T012, T013, T014, T018 | After Batch 1 |
| Batch 3 | T019, T020, T021 | After Batch 2 |

---

## Parallel Execution Examples

### Parallel Example: Batch 1 (Setup + Foundation + Migration + Playbook)

```bash
# All 10 tasks touch different files — run together:
Task: T001 — ansible/group_vars/services/vars.yml (append)
Task: T002 — ansible/group_vars/services/vault.yml (vault edit)
Task: T003 — ansible/roles/reverse_proxy/defaults/main.yml
Task: T004 — ansible/roles/reverse_proxy/templates/domeneshop.env.j2 (NEW)
Task: T005 — ansible/roles/reverse_proxy/templates/caddy-domeneshop.conf.j2 (NEW)
Task: T006 — ansible/roles/reverse_proxy/templates/Caddyfile.j2
Task: T007 — ansible/roles/reverse_proxy/handlers/main.yml
Task: T015 — ansible/roles/nextcloud/ (defaults + template)
Task: T016 — ansible/group_vars/monitoring/ + ansible/roles/monitoring_stack/
Task: T017 — ansible/playbooks/reverse_proxy.yml (NEW)
```

### Parallel Example: Batch 2 (Site Blocks + Tasks + Integration)

```bash
# T008 touches tasks/main.yml only; T009-T014 touch templates only; T018 touches services.yml
Task: T008 — ansible/roles/reverse_proxy/tasks/main.yml
Task: T009 — ansible/roles/reverse_proxy/templates/immich.caddy.j2
Task: T010 — ansible/roles/reverse_proxy/templates/nextcloud.caddy.j2
Task: T011 — ansible/roles/reverse_proxy/templates/grafana.caddy.j2 (NEW)
Task: T012 — ansible/roles/reverse_proxy/templates/jellyfin.caddy.j2 (NEW)
Task: T013 — ansible/roles/reverse_proxy/templates/adguard.caddy.j2 (NEW)
Task: T014 — ansible/roles/reverse_proxy/templates/homeassistant.caddy.j2 (NEW)
Task: T018 — ansible/playbooks/services.yml
```

---

## Traceability Matrix

| Requirement | Tasks |
|-------------|-------|
| FR-001 (HTTPS for all services) | T003, T006, T008, T009, T010, T011–T014 |
| FR-002 (DNS-01 via Domeneshop API) | T006 (acme_dns directive) |
| FR-003 (auto-renewal) | T006 (Caddy handles renewal once DNS provider is configured) |
| FR-004 (TLS termination at proxy) | T009, T010, T011–T014 (all use HTTPS proxy headers) |
| FR-005 (DNS records → proxy IP) | Documented in quickstart.md §1 (manual registrar step) |
| FR-006 (AdGuard DNS rewrites) | Documented in quickstart.md §3 (manual one-time step) |
| FR-007 (Nextcloud new domain) | T010, T015 |
| FR-008 (Nextcloud dual-domain trust) | T015 (nextcloud_trusted_domains_extra) |
| FR-009 (Grafana root URL) | T016 |
| FR-010 (new Caddy site blocks) | T008, T011, T012, T013 |
| FR-011 (remove auto_https off) | T006 |
| FR-012 (custom Caddy binary) | T003, T008 |
| FR-013 (vault secrets injection) | T002, T004, T005, T007, T008 |
| FR-014 (dual-provisioning parity) | T017, T018 |
| FR-015 (Home Assistant placeholder) | T001, T003, T014 |
| FR-016 (data preservation) | T015, T016 (URL/protocol changes only; no data migration) |

---

## File Manifest

### New Files (8)

| File | Created In | Purpose |
|------|------------|---------|
| `ansible/roles/reverse_proxy/templates/domeneshop.env.j2` | T004 | Systemd EnvironmentFile for DNS API credentials |
| `ansible/roles/reverse_proxy/templates/caddy-domeneshop.conf.j2` | T005 | Systemd drop-in override |
| `ansible/roles/reverse_proxy/templates/grafana.caddy.j2` | T011 | Grafana HTTPS reverse proxy site block |
| `ansible/roles/reverse_proxy/templates/jellyfin.caddy.j2` | T012 | Jellyfin HTTPS reverse proxy site block |
| `ansible/roles/reverse_proxy/templates/adguard.caddy.j2` | T013 | AdGuard HTTPS reverse proxy site block |
| `ansible/roles/reverse_proxy/templates/homeassistant.caddy.j2` | T014 | Home Assistant HTTPS reverse proxy site block (conditional) |
| `ansible/playbooks/reverse_proxy.yml` | T017 | Reverse proxy deployment playbook |
| *(vault entries — not a new file)* | T002 | Domeneshop credentials added to existing vault |

### Modified Files (8)

| File | Modified In | Change |
|------|-------------|--------|
| `ansible/group_vars/services/vars.yml` | T001 | Add 9 service IP/port variables for reverse proxy backends |
| `ansible/group_vars/services/vault.yml` | T002 | Add 2 Domeneshop credential entries |
| `ansible/roles/reverse_proxy/defaults/main.yml` | T003 | Add 7 new role default variables |
| `ansible/roles/reverse_proxy/templates/Caddyfile.j2` | T006 | Remove auto_https off, add acme_dns |
| `ansible/roles/reverse_proxy/handlers/main.yml` | T007 | Add Reload systemd handler |
| `ansible/roles/reverse_proxy/tasks/main.yml` | T008 | Add xcaddy build, systemd override, new site deploys |
| `ansible/roles/reverse_proxy/templates/immich.caddy.j2` | T009 | FQDN address + HTTPS headers |
| `ansible/roles/reverse_proxy/templates/nextcloud.caddy.j2` | T010 | FQDN address + HTTPS headers |
| `ansible/roles/nextcloud/defaults/main.yml` | T015 | New domain + protocol + extra trusted domains |
| `ansible/roles/nextcloud/templates/.env.j2` | T015 | HTTPS protocol + dual trusted domains |
| `ansible/group_vars/monitoring/vars.yml` | T016 | New Grafana domain + protocol |
| `ansible/roles/monitoring_stack/defaults/main.yml` | T016 | Add grafana_protocol default |
| `ansible/roles/monitoring_stack/templates/docker-compose.yml.j2` | T016 | Update GF_SERVER_ROOT_URL |
| `ansible/playbooks/services.yml` | T018 | Add reverse_proxy import |

---

## Implementation Strategy

### MVP (US1 + US5 First)

1. Complete Batch 1 (T001–T007, T015–T017) — All setup, templates, and migration config
2. Complete Batch 2 (T008–T014, T018) — Task orchestration, site blocks, services.yml
3. Complete Batch 3 (T019–T021) — Verification
4. **VALIDATE**: Deploy to LAB → verify HTTPS certs → test mobile apps

### Incremental Delivery

After MVP:
- Phase 4 (US1) delivers mobile app connectivity (Nextcloud + Immich)
- Phase 5 (US2) adds remaining services (Grafana, Jellyfin, AdGuard)
- Phase 6 (US4) handles domain migration for Nextcloud and Grafana
- All phases can be deployed together in a single run since they're all Ansible config

### Syntax Validation Gates

Before marking implementation complete, run:
```bash
# Ansible lint
cd ansible && ansible-lint roles/reverse_proxy roles/nextcloud roles/monitoring_stack

# Ansible syntax
ansible-playbook --syntax-check playbooks/reverse_proxy.yml
ansible-playbook --syntax-check playbooks/services.yml
ansible-playbook --syntax-check playbooks/nextcloud.yml
ansible-playbook --syntax-check playbooks/monitoring.yml

# Secrets audit
cd .. && rg 'DOMENESHOP_API_TOKEN|DOMENESHOP_API_SECRET' . --glob '!vault.yml' --glob '!*.j2' --glob '!defaults/main.yml' --glob '!specs/**' --glob '!docs/**'
```

---

## Constitution Check

| Principle | Status | Evidence |
|-----------|--------|----------|
| I. Spec-Driven Workflow | ✅ PASS | Every task traces to FR/US IDs in spec.md; traceability matrix complete |
| II. Secrets Policy | ✅ PASS | Domeneshop credentials in vault (T002); injected via systemd EnvironmentFile with 0600 mode (T004, T008); never in Caddyfile or committed plaintext; verified by T021 |
| III. Separation of Concerns | ✅ PASS | All changes are Ansible-only (configuration inside machines); no Terraform changes per A-008 |
| IV. Dual-Provisioning Parity | ✅ PASS | Playbook created (T017) for CI; services.yml updated (T018) for laptop; same roles used in both contexts |
| Token Privilege Tiers | ✅ PASS | No Terraform or Proxmox API operations; no tier changes |
| Networking (Static IPs) | ✅ PASS | All IPs sourced from terraform tfvars templates (centralized); referenced in group_vars (T001) |
| Test-Driven Changes | ✅ PASS | ansible-lint, syntax-check, caddy validate (on-target), secrets audit — all non-destructive |
| CI/CD Expectations | ✅ PASS | reverse_proxy already in workflow dropdown; playbook now exists to support it (T017) |
| Local Workflow Testing | ✅ N/A | No workflow file changes in this feature |

---

## Self-Critique

### Strengths
- Every task has an exact file path, concrete done-condition, and traceability to spec requirements
- The missing `reverse_proxy.yml` playbook gap was identified and addressed (T017, T018) — this would have caused CI failures
- Variable scoping is explicitly handled (group_vars for cross-host access vs role defaults for single-host)
- Task ordering respects Ansible execution model (custom binary before Caddyfile validate)
- Parallel opportunities are clearly identified with 3 batch execution

### Issues Found
- **[severity: low]** T008 is a large task (18 sub-steps in a single tasks/main.yml rewrite). Could be split into "xcaddy build tasks" and "deploy tasks" but since they're in the same file, splitting would require multiple edits to the same file which violates the [P] constraint. Keeping as one task is pragmatic.
- **[severity: low]** T002 requires vault password to execute — this is inherent to the vault mechanism and cannot be avoided. The done-condition assumes the developer has vault access.
- **[severity: low]** The `caddy validate` step on individual site block files validates them as standalone Caddyfiles. This confirms syntax but does NOT validate the full composed config (global + site blocks together). Full validation happens at runtime when Caddy starts. This is acceptable because Caddy itself validates the full config at startup.

### Verdict
ACCEPT — All quality gate criteria are met. Tasks are specific, ordered, traceable, and have mechanical done-conditions. The plan gap (missing playbook) is addressed. Constitution check passes on all applicable principles.
