# Review: HTTPS for All Homelab Services

## Verdict: APPROVED

---

## Test Gate

- **Tests run**: 74
- **Tests passed**: 74
- **Coverage**: 89.85%
- **Test command**: `source adapter/test-config.sh && run_project_tests && run_project_lint`

### Lint / Static Analysis Results

| Command | Result | Notes |
|---------|--------|-------|
| `run_project_tests` | PASS | 74/74, coverage 89.85% (≥80% threshold) |
| `run_project_lint` (adapter) | PASS | 0 failures, 0 warnings on 202/213 files |
| `ansible-lint ansible/roles/reverse_proxy roles/nextcloud roles/monitoring_stack` | PASS | `min` profile met; production profile also passes |
| `ansible-playbook --syntax-check ansible/playbooks/reverse_proxy.yml` | PASS | Exits 0 (expected `[WARNING]: Could not match supplied host pattern` — no live inventory) |
| `ansible-playbook --syntax-check ansible/playbooks/monitoring.yml` | PASS | Exits 0 |
| `ansible-playbook --syntax-check ansible/playbooks/services.yml` | PRE-EXISTING FAIL | `adguard` role not installed locally; `services.yml` and `adguard.yml` are excluded in `.ansible-lint`; predates this feature |
| `rg 'DOMENESHOP_API_TOKEN=[^{]' .` | PASS | 0 matches outside spec/docs |
| `rg 'DOMENESHOP_API_SECRET=[^{]' .` | PASS | 0 matches outside spec/docs |

> **Note on `services.yml`**: The syntax-check failure is pre-existing. `git log` shows `adguard.yml` was added long before this feature, and the `adguard` role requires a local `ansible-galaxy install`. The `.ansible-lint` config explicitly excludes `ansible/playbooks/services.yml` and `ansible/playbooks/adguard.yml`. This feature only appended the `reverse_proxy` import to `services.yml`; the `reverse_proxy` playbook syntax-checks cleanly.

---

## Spec Compliance

| User Story | Acceptance Criteria | Status | Evidence |
|------------|---------------------|--------|----------|
| US-1 | Nextcloud mobile app connects via `https://nextcloud.hus-sky.no` | PASS | `nextcloud.caddy.j2`: FQDN site address; `nextcloud/defaults/main.yml`: `nextcloud_domain: nextcloud.hus-sky.no`, `nextcloud_overwrite_protocol: https` |
| US-1 | Immich mobile app connects via `https://immich.hus-sky.no` | PASS | `immich.caddy.j2`: FQDN site address; `immich_ip`/`immich_port` in `services/vars.yml` |
| US-1 | Tailscale remote access identical to LAN | PASS | A-010 design decision: public DNS A record returns private IP; Tailscale subnet route makes it reachable; no additional config required |
| US-2 | `https://nextcloud.hus-sky.no` shows Let's Encrypt cert | PASS | `Caddyfile.j2:2`: `acme_dns lego_deprecated domeneshop` global; FQDN site block enables auto-HTTPS |
| US-2 | `https://immich.hus-sky.no` shows Let's Encrypt cert | PASS | `immich.caddy.j2` FQDN; global `acme_dns` applies |
| US-2 | `https://grafana.hus-sky.no` with valid cert; Grafana functional | PASS | `grafana.caddy.j2` exists; `monitoring_ip`/`grafana_port` defined in `services/vars.yml` |
| US-2 | `https://jellyfin.hus-sky.no` with valid cert | PASS | `jellyfin.caddy.j2` exists; `jellyfin_ip`/`jellyfin_port` in `services/vars.yml` |
| US-2 | `https://adguard.hus-sky.no` with valid cert | PASS | `adguard.caddy.j2` exists; `adguard_ip`/`adguard_web_port` in `services/vars.yml` |
| US-3 | Certificates issued automatically within 5 minutes of first start | PASS | Caddy auto-HTTPS triggered by FQDN site blocks + global `acme_dns lego_deprecated domeneshop` |
| US-3 | Certificate renewal automatic (30-day window) | PASS | Caddy's built-in ACME renewal engine handles natively; no operator action required |
| US-3 | New certificate served without interruption after renewal | PASS | Caddy hot-rotates certificates without service restart |
| US-4 | Nextcloud user accounts/files preserved after migration | PASS | Config-only changes; Docker volumes and NFS mounts unchanged |
| US-4 | Immich photos/albums preserved after migration | PASS | Backend IP/port unchanged; only proxy layer modified |
| US-4 | Nextcloud trusts both `nextcloud.local` and `nextcloud.hus-sky.no` | PASS | `nextcloud_trusted_domains_extra: ["nextcloud.local"]` in `nextcloud/defaults/main.yml:9–11`; `.env.j2:21` uses Jinja2 loop |
| US-4 | Grafana dashboards intact after migration | PASS | `GF_SERVER_ROOT_URL={{ grafana_protocol }}://{{ grafana_domain }}` — no hardcoded port; Docker volumes unchanged |
| US-5 | Domeneshop credentials encrypted in vault | PASS | `group_vars/services/vault.yml` is AES-256 encrypted (`$ANSIBLE_VAULT;1.1;AES256`); ciphertext changed in implementation commit confirms new entries added |
| US-5 | Credentials injected at runtime via systemd EnvironmentFile | PASS | `domeneshop.env.j2` (`mode: 0600`, `owner: root`) + `caddy-domeneshop.conf.j2` (`[Service] EnvironmentFile=/etc/caddy/domeneshop.env`) |
| US-5 | No real credential values visible in repository | PASS | `rg 'DOMENESHOP_API_TOKEN=[^{]'` returns 0 real-value matches; vault file is opaque ciphertext |

---

## Functional Requirements Check

| FR | Description | Status | Evidence |
|----|-------------|--------|----------|
| FR-001 | All 5 services HTTPS at `<service>.hus-sky.no` | PASS | 5 site block templates deployed in `tasks/main.yml` |
| FR-002 | Let's Encrypt DNS-01 via Domeneshop | PASS | `Caddyfile.j2:2`: `acme_dns lego_deprecated domeneshop` |
| FR-003 | Automatic cert renewal | PASS | Caddy ACME engine manages renewal lifecycle |
| FR-004 | Reverse proxy terminates TLS; backends remain HTTP | PASS | All site blocks: `reverse_proxy <ip>:<port>` with `header_up X-Forwarded-Proto https` |
| FR-005 | DNS A records at registrar pointing to `192.168.1.211` | PASS | Out-of-band one-time step per A-003; documented in `quickstart.md` |
| FR-006 | AdGuard DNS rewrites for all subdomains | PASS | Manual one-time step per D-002; documented in `quickstart.md` |
| FR-007 | Nextcloud reconfigured with new domain + HTTPS | PASS | `nextcloud_domain: nextcloud.hus-sky.no`; `nextcloud_overwrite_protocol: https`; `OVERWRITECLIURL` templated |
| FR-008 | Nextcloud trusts both old and new domains | PASS | `nextcloud_trusted_domains_extra: ["nextcloud.local"]` + Jinja2 loop in `.env.j2` |
| FR-009 | Grafana root URL updated for proxy | PASS | `GF_SERVER_ROOT_URL={{ grafana_protocol }}://{{ grafana_domain }}` — no hardcoded port |
| FR-010 | New Caddy site blocks for Grafana, Jellyfin, AdGuard | PASS | All three templates created and deployed; backend vars in `services/vars.yml` |
| FR-011 | `auto_https off` removed from Caddyfile | PASS | `Caddyfile.j2` contains no `auto_https` directive |
| FR-012 | Custom Caddy binary with Domeneshop DNS module | PASS | xcaddy build tasks in `tasks/main.yml`; `caddy_xcaddy_plugins: ["github.com/caddy-dns/lego-deprecated"]` |
| FR-013 | Domeneshop credentials in vault only; injected at runtime | PASS | AES-256 encrypted vault; systemd EnvironmentFile `mode: 0600` |
| FR-014 | Deployable from CI/CD and developer laptop | PASS | `ansible/playbooks/reverse_proxy.yml` exists; `reverse_proxy` in all four GitHub Actions workflow service dropdowns |
| FR-015 | Home Assistant site block conditional on `homeassistant_active` | PASS | `homeassistant.caddy.j2:1`: `{% if homeassistant_active \| default(false) %}`; default `false` |
| FR-016 | Existing service data preserved | PASS | Config-only changes; Docker volumes/NFS mounts unchanged |

---

## Variable Resolution

- **Scanned**: 20 files (all new/modified templates, defaults, vars, and task files from implementation commit)
- **Undefined**: None

| Variable | Template(s) | Defined In | Status |
|----------|-------------|------------|--------|
| `caddy_base_domain` | all `*.caddy.j2`, `Caddyfile.j2` | `reverse_proxy/defaults/main.yml` | ✅ |
| `caddy_acme_dns_provider` | `Caddyfile.j2` | `reverse_proxy/defaults/main.yml` | ✅ |
| `caddy_acme_dns_provider_name` | `Caddyfile.j2` | `reverse_proxy/defaults/main.yml` | ✅ |
| `caddy_conf_dir` | `Caddyfile.j2`, `tasks/main.yml` | `reverse_proxy/defaults/main.yml` | ✅ |
| `caddy_custom_binary` | `tasks/main.yml` | `reverse_proxy/defaults/main.yml` | ✅ |
| `caddy_xcaddy_plugins` | `tasks/main.yml` | `reverse_proxy/defaults/main.yml` | ✅ |
| `go_version` | `tasks/main.yml` | `reverse_proxy/defaults/main.yml` | ✅ |
| `homeassistant_active` | `homeassistant.caddy.j2` | `reverse_proxy/defaults/main.yml` | ✅ |
| `nextcloud_ip` | `nextcloud.caddy.j2` | `group_vars/services/vars.yml` | ✅ |
| `nextcloud_port` | `nextcloud.caddy.j2` | `group_vars/services/vars.yml` | ✅ |
| `immich_ip` | `immich.caddy.j2` | `group_vars/services/vars.yml` | ✅ |
| `immich_port` | `immich.caddy.j2` | `group_vars/services/vars.yml` | ✅ |
| `monitoring_ip` | `grafana.caddy.j2` | `group_vars/services/vars.yml` | ✅ |
| `grafana_port` | `grafana.caddy.j2` | `group_vars/services/vars.yml` | ✅ |
| `jellyfin_ip` | `jellyfin.caddy.j2` | `group_vars/services/vars.yml` | ✅ |
| `jellyfin_port` | `jellyfin.caddy.j2` | `group_vars/services/vars.yml` | ✅ |
| `adguard_ip` | `adguard.caddy.j2` | `group_vars/services/vars.yml` | ✅ |
| `adguard_web_port` | `adguard.caddy.j2` | `group_vars/services/vars.yml` | ✅ |
| `homeassistant_ip` | `homeassistant.caddy.j2` | `group_vars/services/vars.yml` | ✅ |
| `homeassistant_port` | `homeassistant.caddy.j2` | `group_vars/services/vars.yml` | ✅ |
| `domeneshop_api_token` | `domeneshop.env.j2` | `group_vars/services/vault.yml` (AES-256 encrypted) | ✅ |
| `domeneshop_api_secret` | `domeneshop.env.j2` | `group_vars/services/vault.yml` (AES-256 encrypted) | ✅ |
| `nextcloud_domain` | `nextcloud/.env.j2` | `nextcloud/defaults/main.yml` | ✅ |
| `nextcloud_overwrite_protocol` | `nextcloud/.env.j2` | `nextcloud/defaults/main.yml` | ✅ |
| `nextcloud_trusted_domains_extra` | `nextcloud/.env.j2` | `nextcloud/defaults/main.yml` | ✅ |
| `reverse_proxy_ip` | `nextcloud/.env.j2` | `group_vars/services/vars.yml` | ✅ |
| `grafana_protocol` | `docker-compose.yml.j2` | `group_vars/monitoring/vars.yml` | ✅ |
| `grafana_domain` | `docker-compose.yml.j2` | `group_vars/monitoring/vars.yml` | ✅ |

---

## Task Completion

- **Total tasks**: 19
- **Completed `[X]`**: 19
- **Remaining `[ ]`**: 0

All tasks marked complete. Task file covers all phases: Setup (T001–T003), Foundational (T004–T005), US5 Secrets (T006–T007), US1 Mobile (T008–T011), US2 Browser (T012–T017), US3 Cert Lifecycle (T018), Polish (T019).

---

## Spec/Plan Immutability Check

- `specs/039-https-services/spec.md`: **UNCHANGED** during implementation — `git diff 2c6656e 2269085 -- spec.md` → 0 lines
- `specs/039-https-services/plan.md`: **UNCHANGED** during implementation — `git diff 957d1b9 2269085 -- plan.md` → 0 lines

---

## TODO/FIXME/HACK/XXX Scan

Scanned all new/modified files (`ansible/roles/reverse_proxy/`, `ansible/roles/nextcloud/`, `ansible/roles/monitoring_stack/`, `ansible/group_vars/`). **Zero markers found.**

---

## Constitution Compliance

- [x] **Principle I: Spec-Driven Workflow** — PASS. All 16 FRs trace to accepted `spec.md` requirements. All 19 tasks reference FR/US IDs. No undocumented changes.
- [x] **Principle II: Secrets Policy** — PASS. `vault.yml` is AES-256 encrypted. `domeneshop.env` is generated from vault at deploy time with `mode: 0600`. No plaintext credentials in any committed file.
- [x] **Principle III: Separation of Concerns** — PASS. All changes are Ansible-only. No Terraform modifications per A-008.
- [x] **Principle IV: Dual-Provisioning Parity** — PASS. `ansible/playbooks/reverse_proxy.yml` exists; `reverse_proxy` is in all four GitHub Actions workflow service dropdowns (`lxc-deploy-lab.yml`, `lxc-promote-lab.yml`, `lxc-promote-prod.yml`, `lab-integration-tests.yml`).

---

## Blocking Issues

None.

---

## Observations (non-blocking)

1. **`services.yml` ansible-lint noise (pre-existing)** — The lint adapter prints `ERROR: Failed to load services.yml playbook` but exits 0 because `services.yml` is in `.ansible-lint` `exclude_paths`. Root cause is the `adguard` role not being installed via `ansible-galaxy install` on the developer machine; `pve-service-deploy` runs `ensure_ansible_galaxy_requirements` at runtime which resolves it. Not introduced by this feature.

2. **xcaddy build idempotency on version/plugin change** — The build task uses `creates: /usr/local/bin/caddy-custom`. If `go_version` or `caddy_xcaddy_plugins` are updated in future, Ansible will not trigger a rebuild unless the file is manually removed. A version-stamped output path (e.g., `/usr/local/bin/caddy-custom-{{ go_version }}`) or a `stat`/`checksum` guard would be more robust. Acceptable for a homelab with manual deploys.

3. **`monitoring_ip`/`grafana_port` defined in two group_vars** — Both `group_vars/services/vars.yml` and `group_vars/monitoring/vars.yml` define these variables. While the values are consistent today, a future update to one without the other could cause drift. A comment in `services/vars.yml` noting the duplication and its reason would improve maintainability.

---

## Feedback for Developer

None required. The implementation is complete and approved.

---

## Verdict

**APPROVED**
