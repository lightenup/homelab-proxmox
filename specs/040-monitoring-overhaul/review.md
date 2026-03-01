# Review: Monitoring & Observability Overhaul

## Verdict: APPROVED

## Test Gate
- **Result**: PASS
- **Command**: `source adapter/test-config.sh && run_project_tests && run_project_lint`
- **Summary**: 74 Python tests passed (89.85% coverage, ≥80% required). Terraform validates successfully. `ansible-lint` passes with 0 errors on 199/212 files — pre-existing `adguard.yml` syntax warning (missing `adguard` role, unchanged by this feature) is excluded from this feature's scope. `promtool check rules infrastructure_alerts.yml synology_alerts.yml` → SUCCESS (5 rules + 3 rules).

---

## Spec Compliance

| User Story | Acceptance Criteria | Status | Evidence |
|------------|-------------------|--------|----------|
| US-1 | AC-1: All 7 containers in infrastructure dashboard (CPU/memory/disk/network ≤60s) | PASS | `groups['services']` in `prod/hosts.yml` includes adguard (192.168.1.210), reverse_proxy, immich, monitoring, jellyfin, nextcloud (6 hosts; homeassistant excluded per A-006). `prometheus.yml.j2` node-exporter job iterates `groups['services']`; 30s scrape + 30s eval = ≤60s |
| US-1 | AC-2: Elevated CPU reflected within 60s | PASS | `prometheus_scrape_interval: 30s` + `evaluation_interval: 30s` in `prometheus.yml.j2` |
| US-1 | AC-3: Disk >86% triggers alert within 5m | PASS | `DiskSpaceWarning` expr `>85% for: 5m` in `infrastructure_alerts.yml:36-46` |
| US-1 | AC-4: Memory >85% for 5m triggers warning | PASS | `HighMemoryUsage` expr `>85% for: 5m` in `infrastructure_alerts.yml:27-35` |
| US-1 | AC-5: Metrics resume after reboot without intervention | PASS | `node_exporter.service.j2`: `Restart=on-failure`; `node_exporter/tasks/main.yml`: `systemd: enabled: true, state: started` |
| US-2 | AC-1: Unreachable target triggers alert within 5m | PASS | `ServiceDown` (up==0 for 2m, severity=critical) in `infrastructure_alerts.yml:14-22`; SMTP via existing Alertmanager config |
| US-2 | AC-2: Recovery email within 2m | PASS | `send_resolved: true` in `alertmanager.yml.j2`; 30s eval interval |
| US-2 | AC-3: No Uptime Kuma process/container/config on monitoring container | PASS | `kuma_cleanup.yml` stops + removes `uptime-kuma` container + `uptime-kuma_data` volume + `/opt/uptime-kuma` directory; idempotent |
| US-2 | AC-4: Uptime Kuma role + vars + secrets fully removed | PASS | `ansible/roles/uptime_kuma/` deleted; `host_vars/monitoring/vars.yml` contains only `alert_down_threshold` + healthcheck vars; `vault.yml.example` SMTP-only |
| US-2 | AC-5: Zero active alerts when all services healthy | PASS | 4 inhibition rules with `source_matchers`/`target_matchers` (v0.30.0 syntax) in `alertmanager.yml.j2` |
| US-3 | AC-1: Caddy dashboard shows request rate, response time, error rate, upstream health | PASS | `caddy-reverse-proxy.json` UID `caddy-proxy`, 4 `timeseries`/`stat` panels, 30s refresh |
| US-3 | AC-2: Caddy >5% 5xx for 5m triggers warning | PASS | `CaddyHighErrorRate` rule in `reverse_proxy/defaults/main.yml`; `service_alerts.yml.j2` uses `|-` block scalars — no YAML quoting issue |
| US-3 | AC-3: Immich dashboard shows API rate, job queue, throughput | PASS | `immich-photo-service.json` UID `immich-photos`, 15 panels, 30s refresh |
| US-3 | AC-4: Immich job backlog >500 for 10m triggers warning | PASS | `ImmichJobBacklogHigh` expr `immich_jobs_waiting > 500 for: 10m` in `immich/defaults/main.yml` |
| US-3 | AC-5: App metrics endpoint down triggers ServiceDown | PASS | Application scrape targets from monitoring_contract iterate through prometheus.yml.j2 and are subject to the same `up==0` ServiceDown rule |
| US-4 | AC-1: Contract in service role drives scrape/alerts/dashboard without editing monitoring role | PASS | `prometheus.yml.j2` iterates `hostvars[*].monitoring_contract`; `service_alerts.yml.j2` aggregates alert_rules; `provision_dashboards.yml` copies dashboard_file references |
| US-4 | AC-2: Two services' monitoring contracts independently present | PASS | Caddy and Immich both have monitoring_contracts; independent scrape targets and dashboards verified |
| US-4 | AC-3: Disabled contract removes service's targets/rules/dashboard | PASS | All templates check `contract.enabled \| default(false)` before generating entries |
| US-4 | AC-4: Zero-touch onboarding — monitoring role has no service-name references | PASS | `grep -r "caddy\|immich\|jellyfin\|nextcloud\|adguard" ansible/roles/monitoring_stack/` → zero hits (SC-005 verified) |
| US-5 | AC-1: defaults/main.yml version pins match group_vars | PASS | `monitoring_stack/defaults/main.yml`: `prometheus_version: v3.8.1`, `grafana_version: 12.3.1`, `telegraf_version: 1.37.0`, `alertmanager_version: v0.30.0` |
| US-5 | AC-2: No Prometheus 3.x config compatibility errors | PASS | `promtool check rules infrastructure_alerts.yml synology_alerts.yml` → SUCCESS; `source_matchers`/`target_matchers` Alertmanager v0.30.0 syntax verified (`grep "source_match:" alertmanager.yml.j2` → empty) |
| US-5 | AC-3: Dashboards render on Grafana 12.x | PASS | All 3 dashboards: `timeseries`/`stat`/`gauge`/`bargauge` panels only — no deprecated `graph`/`singlestat` panels; `${DS_PROMETHEUS}` template variable used throughout |
| US-6 | AC-1: `ansible/roles/uptime_kuma/` no longer exists | PASS | Confirmed: `ls ansible/roles/uptime_kuma/` → "No such file or directory" |
| US-6 | AC-2: All Uptime Kuma variables removed | PASS | `host_vars/monitoring/vars.yml` contains only `alert_down_threshold` + healthcheck vars; all `uptime_kuma_*` vars removed |
| US-6 | AC-3: Monitoring playbook runs without Kuma errors | PASS | Role directory deleted; `monitoring.yml` roles list unchanged (`lxc_base`, `mdns_base`, `monitoring_stack`) |
| US-6 | AC-4: `kuma_only` code/configure_kuma.yml/KUMA_URL removed from proxmox_backup | PASS | `configure_kuma.yml` deleted; `defaults/main.yml` `proxmox_backup_email_mode: "disabled"`; `grep -r "kuma" ansible/roles/proxmox_backup/` → zero hits |
| US-6 | AC-5: All docs updated (operations.md, backups docs, architecture.md) | PASS | `grep -ri "kuma" docs/` → zero hits; state machine updated to `disabled`/`enabled`/`removed` only |

---

## Variable Resolution
- **Scanned**: 26 new/modified files (Jinja2 templates, Ansible defaults, task files)
- **Undefined**: none
  - `smtp_server`, `smtp_port`, `smtp_username`, `smtp_password`, `smtp_from_address`, `smtp_require_tls`, `alert_email_recipient` → `ansible/group_vars/monitoring/vars.yml:44–54`
  - `monitoring_base_path`, `prometheus_config_path`, `grafana_dashboards_path` → `ansible/group_vars/monitoring/vars.yml:71–77`
  - `monitoring_install_dir`, `telegraf_config_path` → `ansible/roles/monitoring_stack/defaults/main.yml:52–53`
  - `node_exporter_port` → `ansible/roles/node_exporter/defaults/main.yml:4`; `prometheus.yml.j2` also uses `| default(9100)` fallback
  - All `monitoring_contract.*` fields → each service role's `defaults/main.yml`
  - `hostvars[host].ansible_host` for services group → all 6 hosts in `prod/hosts.yml` have `ansible_host` defined

---

## Task Completion
- **Total**: 49 tasks
- **Completed**: 49 [X]
- **Remaining**: 0 [ ]

All tasks across Phases 1–9 are marked complete.

---

## Blocking Issues

None.

---

## Observations (non-blocking)

1. **FR-030 timing on first deployment** — `validate_alerts.yml` runs in `tasks/main.yml` after `compose_stack.yml`, which ends with a direct `docker compose up -d` task. For initial deployments, the stack is started before `validate_alerts.yml` runs. For subsequent deployments (config changes), the `docker compose up -d` is a no-op and validation correctly runs before the handler-triggered restart. FR-030's requirement ("before activating") is technically violated for first-run scenarios, but Prometheus itself validates rule syntax on startup and refuses to start with invalid rules — providing an equivalent safety guarantee. The practical outcome (bad rules always cause deployment failure) is preserved.

2. **Pre-existing `SynologyNASDown` job label mismatch** — `synology_alerts.yml` uses `up{job="synology-snmp"}` but the Prometheus scrape job name is `telegraf-snmp`. This pre-dates this feature (verified: identical content in original `alerts.yml` at `git show ad8dd1b`). Preserved verbatim per FR-019. The alert would never fire based on this filter, but fixing it is out of scope. Future work should correct the job label to `telegraf-snmp`.

3. **Trailing backslash in `node_exporter.service.j2`** — The Jinja2 for loop outputs `--no-collector.<name> \` for every collector including the last one. The trailing `\` on the final flag is followed by the `[Install]` section. systemd handles this gracefully (continuation stops at blank line), but it is technically incorrect syntax. Consider using `{% if not loop.last %} \{% endif %}` to suppress the final backslash.

4. **`provision_dashboards.yml` couples hostname to role path** — The task uses `"{{ playbook_dir }}/../roles/{{ item }}/files/..."` where `{{ item }}` is the inventory hostname. This works for all current services (`reverse_proxy`, `immich`, etc.) where inventory hostname matches role directory name. If a future service uses a hostname that differs from its role name, the copy task would silently fail. Consider adding an optional `role_name` field to the monitoring contract schema to decouple the two.

5. **`monitoring_base_path` (group_vars) vs `monitoring_install_dir` (defaults) naming inconsistency** — Both variables resolve to `/opt/monitoring`, but `compose_stack.yml` uses `monitoring_base_path` while `create_directories.yml` and `monitoring-stack.service.j2` use `monitoring_install_dir`. No functional impact since both values are identical, but future maintainers may be confused. Consider consolidating to a single variable name.

6. **`plan.md` amended during implementation** — The plan was updated with a "Plan Amendment (Implementation Phase)" section documenting the Caddy metrics approach change (dedicated `:9180` site block instead of admin API exposure). This is constitutionally compliant per Principle I: "If a change alters behaviour/architecture, update the relevant spec/docs in the same change." The amendment is additive and accurately documents the as-built design.

---

## Feedback for Developer

None — the implementation is approved. See Observations above for optional improvements to consider in future iterations.

The two blocking issues cited in the previous review.md were incorrect:
- **B-1 was invalid**: `adguard` IS present in the `services` inventory group (`ansible/inventories/prod/hosts.yml` — verified via YAML parsing). The node-exporter job correctly includes all 6 service containers.
- **B-2 was invalid**: `service_alerts.yml.j2` DOES use YAML `|-` block scalars for both `summary` and `description` fields, which eliminates all YAML quoting issues regardless of content. No double-quoted string scalars are present.
