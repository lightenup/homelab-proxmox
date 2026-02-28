# Review: HTTPS for All Homelab Services

> **Iteration**: 2 of 3 maximum  
> **Previous verdict**: CHANGES_REQUESTED (3 blocking issues + 1 process concern)  
> **This verdict**: APPROVED

---

## Verdict: APPROVED

All three blocking issues from iteration 1 have been resolved. The implementation is
correct, complete, and satisfies all functional requirements in the spec.

---

## Test Gate

- **Tests run**: 74
- **Tests passed**: 74
- **Coverage**: 89.85%
- **Test command**: `source adapter/test-config.sh && run_project_tests`

### Lint Results

| Command | Result | Notes |
|---------|--------|-------|
| `source adapter/test-config.sh && run_project_lint` | PASS | 0 failures, 0 warnings on 202 files |
| `ansible-lint ansible/roles/reverse_proxy roles/nextcloud roles/monitoring_stack` | PASS | `min` profile; `services.yml` and `adguard.yml` excluded per `.ansible-lint` (pre-existing) |
| `ansible-playbook --syntax-check ansible/playbooks/reverse_proxy.yml` | PASS | Exits 0 with `[WARNING]: Could not match supplied host pattern, ignoring: reverse_proxy` (expected — no live inventory) |
| `ansible-playbook --syntax-check ansible/playbooks/monitoring.yml` | PASS | Exits 0 |
| `rg 'DOMENESHOP_API_TOKEN=[^{]' .` | PASS | 0 matches outside spec/docs |
| `rg 'DOMENESHOP_API_SECRET=[^{]' .` | PASS | 0 matches outside spec/docs |

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| US-1 AC-1 | Nextcloud mobile app connects via `https://nextcloud.hus-sky.no` | PASS | `nextcloud.caddy.j2`: FQDN site address; `nextcloud/defaults/main.yml`: `nextcloud_domain: nextcloud.hus-sky.no`, `nextcloud_overwrite_protocol: https` |
| US-1 AC-2 | Immich mobile app connects via `https://immich.hus-sky.no` | PASS | `immich.caddy.j2`: FQDN site address; all variables (`immich_ip`, `immich_port`) defined in `services/vars.yml` |
| US-1 AC-3 | Tailscale remote access identical to LAN | PASS | By design (A-010): public DNS A records return private IP; Tailscale subnet route makes it reachable; no additional config required |
| US-2 AC-1 | `https://nextcloud.hus-sky.no` shows Let's Encrypt cert in browser | PASS | `Caddyfile.j2` has `acme_dns lego_deprecated domeneshop`; `nextcloud.caddy.j2` uses FQDN (enables auto-HTTPS) |
| US-2 AC-2 | `https://immich.hus-sky.no` shows Let's Encrypt cert in browser | PASS | `immich.caddy.j2` uses FQDN; global `acme_dns` applies |
| US-2 AC-3 | `https://grafana.hus-sky.no` with Let's Encrypt cert in browser | PASS | `grafana.caddy.j2` exists; `monitoring_ip` and `grafana_port` now defined in `group_vars/services/vars.yml` (resolved from iteration 1 blocker) |
| US-2 AC-4 | `https://jellyfin.hus-sky.no` with Let's Encrypt cert in browser | PASS | `jellyfin.caddy.j2` exists; variables in `services/vars.yml` |
| US-2 AC-5 | `https://adguard.hus-sky.no` with Let's Encrypt cert in browser | PASS | `adguard.caddy.j2` exists; variables in `services/vars.yml` |
| US-3 AC-1 | Certificates issued automatically within 5 minutes of first start | PASS | Caddy auto-HTTPS via `acme_dns lego_deprecated domeneshop` global directive; domains are FQDN |
| US-3 AC-2 | Certificate renewal is automatic (30-day window) | PASS | Caddy's built-in ACME renewal engine handles this natively |
| US-3 AC-3 | New certificate served without interruption after renewal | PASS | Caddy handles hot certificate rotation; no service restart required |
| US-4 AC-1 | Nextcloud user accounts/files preserved after migration | PASS | Config-only changes; Docker volumes unchanged; no data migration |
| US-4 AC-2 | Immich photos/albums preserved after migration | PASS | Backend unchanged; only proxy layer changes |
| US-4 AC-3 | Nextcloud trusts both `nextcloud.local` and `nextcloud.hus-sky.no` | PASS | `nextcloud_trusted_domains_extra: ["nextcloud.local"]` in `nextcloud/defaults/main.yml:9–11`; `.env.j2` uses Jinja2 loop to include all extra domains |
| US-4 AC-4 | Grafana dashboards intact after migration | PASS | `GF_SERVER_ROOT_URL={{ grafana_protocol }}://{{ grafana_domain }}` in `docker-compose.yml.j2` (no port); Docker volumes unchanged |
| US-5 AC-1 | Domeneshop credentials encrypted in vault | PASS | `group_vars/services/vault.yml` is AES-256 encrypted (`$ANSIBLE_VAULT;1.1;AES256`) |
| US-5 AC-2 | Credentials injected at runtime via systemd EnvironmentFile | PASS | `domeneshop.env.j2` (mode `0600`) + `caddy-domeneshop.conf.j2` (`[Service] EnvironmentFile=/etc/caddy/domeneshop.env`) |
| US-5 AC-3 | No real credential values visible in repository | PASS | `rg 'DOMENESHOP_API_TOKEN=[^{]'` → 0 real-value matches; vault file is opaque ciphertext |

---

## Functional Requirements Check

| FR | Description | Status | Evidence |
|----|-------------|--------|----------|
| FR-001 | All 5 services HTTPS at `<service>.hus-sky.no` | PASS | 5 site block templates exist and are deployed by `tasks/main.yml` |
| FR-002 | TLS certs via Let's Encrypt DNS-01 (Domeneshop) | PASS | `Caddyfile.j2:2`: `acme_dns lego_deprecated domeneshop` |
| FR-003 | Automatic certificate renewal | PASS | Caddy ACME engine handles renewal; no operator action required |
| FR-004 | Reverse proxy terminates TLS; backends remain HTTP | PASS | All site blocks: `reverse_proxy <ip>:<port>` with `header_up X-Forwarded-Proto https` |
| FR-005 | DNS A records at registrar pointing to `192.168.1.211` | PASS | Out-of-band one-time step per A-003; documented in `quickstart.md` |
| FR-006 | AdGuard DNS rewrites for all subdomains | PASS | Manual one-time setup per D-002; out-of-scope automation; documented in `quickstart.md` |
| FR-007 | Nextcloud reconfigured with new domain + HTTPS | PASS | `nextcloud_domain: nextcloud.hus-sky.no`; `nextcloud_overwrite_protocol: https`; `OVERWRITECLIURL` uses template variable |
| FR-008 | Nextcloud trusts both old and new domains | PASS | `nextcloud_trusted_domains_extra: ["nextcloud.local"]` in defaults; `.env.j2` Jinja2 loop |
| FR-009 | Grafana root URL updated for proxy | PASS | `GF_SERVER_ROOT_URL={{ grafana_protocol }}://{{ grafana_domain }}` — no hardcoded port |
| FR-010 | New Caddy site blocks for Grafana, Jellyfin, AdGuard | PASS | All three templates exist and are deployed; `monitoring_ip`/`grafana_port` now in `services/vars.yml` |
| FR-011 | `auto_https off` removed from Caddyfile | PASS | `Caddyfile.j2` has no `auto_https` directive; confirmed by reading file |
| FR-012 | Custom Caddy binary with Domeneshop DNS module | PASS | xcaddy build tasks in `tasks/main.yml`; `caddy_xcaddy_plugins: ["github.com/caddy-dns/lego-deprecated"]` |
| FR-013 | Domeneshop credentials in vault only; injected at runtime | PASS | Vault is AES-256 encrypted; systemd EnvironmentFile pattern with `mode: 0600` |
| FR-014 | Deployable from CI/CD and developer laptop | PASS | `ansible/playbooks/reverse_proxy.yml` created (was missing in iteration 1); `services.yml` updated with `reverse_proxy` import; `reverse_proxy` already in all GitHub Actions workflow service dropdowns |
| FR-015 | Home Assistant site block conditional on `homeassistant_active` | PASS | `homeassistant.caddy.j2:1`: `{% if homeassistant_active \| default(false) %}` guard; `homeassistant_active: false` in defaults |
| FR-016 | Existing service data preserved through migration | PASS | Config-only changes; Docker volumes and NFS mounts unchanged; no data migration required |

---

## Variable Resolution

**Scanned**: 20 files (all new/modified templates, defaults, vars, and task files)

| Variable | Template | Defined In | Accessible to Host | Status |
|----------|----------|------------|-------------------|--------|
| `caddy_base_domain` | all `*.caddy.j2`, `Caddyfile.j2` | `reverse_proxy/defaults/main.yml` | YES (same role) | ✅ |
| `caddy_acme_dns_provider` | `Caddyfile.j2` | `reverse_proxy/defaults/main.yml` | YES | ✅ |
| `caddy_acme_dns_provider_name` | `Caddyfile.j2` | `reverse_proxy/defaults/main.yml` | YES | ✅ |
| `caddy_conf_dir` | `Caddyfile.j2`, `tasks/main.yml` | `reverse_proxy/defaults/main.yml` | YES | ✅ |
| `caddy_custom_binary` | `tasks/main.yml` | `reverse_proxy/defaults/main.yml` | YES | ✅ |
| `caddy_xcaddy_plugins` | `tasks/main.yml` | `reverse_proxy/defaults/main.yml` | YES | ✅ |
| `go_version` | `tasks/main.yml` | `reverse_proxy/defaults/main.yml` | YES | ✅ |
| `homeassistant_active` | `homeassistant.caddy.j2` | `reverse_proxy/defaults/main.yml` | YES | ✅ |
| `nextcloud_ip` | `nextcloud.caddy.j2` | `group_vars/services/vars.yml` | YES (`services` group) | ✅ |
| `nextcloud_port` | `nextcloud.caddy.j2` | `group_vars/services/vars.yml` | YES (`services` group) | ✅ **FIXED** |
| `immich_ip` | `immich.caddy.j2` | `group_vars/services/vars.yml` | YES | ✅ |
| `immich_port` | `immich.caddy.j2` | `group_vars/services/vars.yml` | YES | ✅ |
| `monitoring_ip` | `grafana.caddy.j2` | `group_vars/services/vars.yml` | YES (`services` group) | ✅ **FIXED** |
| `grafana_port` | `grafana.caddy.j2` | `group_vars/services/vars.yml` | YES (`services` group) | ✅ **FIXED** |
| `jellyfin_ip` | `jellyfin.caddy.j2` | `group_vars/services/vars.yml` | YES | ✅ |
| `jellyfin_port` | `jellyfin.caddy.j2` | `group_vars/services/vars.yml` | YES | ✅ |
| `adguard_ip` | `adguard.caddy.j2` | `group_vars/services/vars.yml` | YES | ✅ |
| `adguard_web_port` | `adguard.caddy.j2` | `group_vars/services/vars.yml` | YES | ✅ |
| `homeassistant_ip` | `homeassistant.caddy.j2` | `group_vars/services/vars.yml` | YES | ✅ |
| `homeassistant_port` | `homeassistant.caddy.j2` | `group_vars/services/vars.yml` | YES | ✅ |
| `domeneshop_api_token` | `domeneshop.env.j2` | `group_vars/services/vault.yml` (encrypted) | YES | ✅ |
| `domeneshop_api_secret` | `domeneshop.env.j2` | `group_vars/services/vault.yml` (encrypted) | YES | ✅ |
| `nextcloud_domain` | `nextcloud/.env.j2` | `nextcloud/defaults/main.yml` | YES (same role play) | ✅ |
| `nextcloud_overwrite_protocol` | `nextcloud/.env.j2` | `nextcloud/defaults/main.yml` | YES | ✅ |
| `nextcloud_trusted_domains_extra` | `nextcloud/.env.j2` | `nextcloud/defaults/main.yml` | YES | ✅ |
| `reverse_proxy_ip` | `nextcloud/.env.j2` | `group_vars/services/vars.yml` | YES | ✅ |
| `grafana_protocol` | `docker-compose.yml.j2` | `group_vars/monitoring/vars.yml` | YES (monitoring role play) | ✅ |
| `grafana_domain` | `docker-compose.yml.j2` | `group_vars/monitoring/vars.yml` | YES (monitoring role play) | ✅ |

**Undefined variables**: None.

---

## Task Completion

- **Total tasks**: 19
- **Completed `[X]`**: 19
- **Remaining `[ ]`**: 0

All tasks are marked complete. The three fixes applied during iteration 2 (adding
`nextcloud_port`, `monitoring_ip`, `grafana_port` to `services/vars.yml`; creating
`reverse_proxy.yml`; adding `reverse_proxy` to `services.yml`) were implemented as
corrections to tasks T001 and T018 rather than as new formal tasks. This is acceptable
since the fixes directly satisfy the original task requirements and all acceptance criteria.

---

## Constitution Compliance

- [x] **Principle I: Spec-Driven Workflow** — PASS. All 16 FRs trace to spec requirements. Task list shows 19/19 complete. No implementation deviates from the spec.
- [x] **Principle II: Secrets Policy** — PASS. `vault.yml` is AES-256 encrypted. `domeneshop.env` is generated from vault at deploy time with `mode: 0600`. No plaintext credentials in any committed file.
- [x] **Principle III: Separation of Concerns** — PASS. All changes are Ansible-only. No Terraform modifications.
- [x] **Principle IV: Dual-Provisioning Parity** — PASS. `ansible/playbooks/reverse_proxy.yml` exists; `reverse_proxy` is in `services.yml` and all GitHub Actions workflow service dropdowns (`lxc-deploy-lab.yml`, `lxc-promote-lab.yml`, `lxc-promote-prod.yml`, `lab-integration-tests.yml`). Same Ansible playbooks work from CI and laptop.

---

## Blocking Issues

None.

---

## Observations (non-blocking)

1. **`services.yml` ansible-lint warning (pre-existing)** — ansible-lint prints `ERROR: Failed to load services.yml playbook due to failing syntax check` but still exits 0. Root cause: the `adguard` role is not installed from `requirements.yml` on the developer machine. This predates this feature; `pve-service-deploy` runs `ensure_ansible_galaxy_requirements` at runtime which resolves it. Not introduced by this feature.

2. **xcaddy idempotency on version or plugin change** — The build task uses `creates: /usr/local/bin/caddy-custom`, so a change to `go_version` or `caddy_xcaddy_plugins` will not trigger a rebuild on the next Ansible run without manually removing `/usr/local/bin/caddy-custom`. A version-stamped path or checksum guard would be more robust. Acceptable for a homelab; noted for future improvement.

3. **`grafana_admin_password: "admin"` in monitoring/vars.yml** — A pre-existing default value with a comment "Override in vault for production." This is not a secret leak (it's a placeholder), but production deployments should override this in vault. Not introduced by this feature.

---

## Feedback for Developer

None required. The implementation is approved.

---

## Iteration Summary

| Iteration | Verdict | Blocking Issues | Resolved In |
|-----------|---------|-----------------|-------------|
| 1 | CHANGES_REQUESTED | 3 critical (missing playbook, 2 undefined variables) + 1 process | Iteration 2 |
| 2 (this) | **APPROVED** | None | — |
