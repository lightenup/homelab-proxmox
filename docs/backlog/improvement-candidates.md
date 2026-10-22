# Improvement candidates (consolidated)

Sparse backlog of operability / monitoring / security improvements, carried over from the retired
`specs/candidate/candidates.md` (full original text in git history). Grouped, one line each. Status:
**Open** = not started · **Done** = shipped, kept only for context.

## Onboarding & operability

- **Service scaffold generator** — `task service:scaffold` from a per-service `service.yml` manifest;
  generate the ~17 boilerplate files (Terraform root, Ansible role skeleton, host_vars, playbook
  import, healthcheck, scope allowlist, workflow option, docs). Extends today’s `service:add`. *Open*
- **`task deploy:preflight`** — statically validate before any CI run: all Jinja `{{ var }}` refs
  resolve; files referenced by tasks are git-tracked (catches `.gitignore` exclusions); `service_ips`
  subnet matches `network_gateway`; `nameserver` set when PVE uses Tailscale; healthcheck script,
  scope allowlist entry, and workflow option exist. *Open*
- **NFS root_squash guard + docs** — document the constraint (no `owner:`/`group:` on NFS paths; keep
  NFS out of Docker-entrypoint `rsync --chown` targets) and lint/preflight flag for it. Caused 3
  separate nextcloud failures. *Open*
- **PVE tfvars drift detection** — CI step comparing PVE tfvars *keys* (not values) against the
  `.tfvars.example` files; flag missing/extra keys. *Done (038-tfvars-template-separation)*
- **Subnet validation in Terraform** — `validation` block asserting `service_ips` share the gateway’s
  /24. *Done (037-ci-fresh-deploy-fixes)*
- **Ansible vault bootstrap** — `task vault:init` to create the vault password file; scaffold a vault
  template with placeholders + onboarding doc. *Open*
- **LAB inventory snapshot artifact** — per apply/plan: containers (vmid/hostname/status/IP), per-service
  evidence pointers, workload-check summary, links to state/evidence. *Open*
- **DR scripts as a portable bundle** — versioned tarball/task so drills don’t depend on manual copy
  into `~/dr-drill-sources/` on PVE. *Open*
- **Cheaper off-site backup target for NAS** — evaluate replacing Hetzner object storage (current DR
  off-site target in `scripts/dr/`) with a cheaper provider (e.g. Hetzner Storage Box, Backblaze B2,
  Cloudflare R2); compare per-GB + egress cost, rclone backend support, and DR-restore workflow impact.
  *Open*
- **Prerequisite gating regardless of branch** — allow check-prerequisites on `main` with an explicit
  hotfix override (currently blocks hotfixes). *Open*
- **Static prod inventory for config-only deploys** — `services` group in `inventories/prod/hosts.yml`
  so laptop `ansible-playbook` works without generated inventory. *Done*

## Monitoring gaps

- **Watchdog / dead-man’s-switch** — always-firing `vector(1)` alert routed to an external heartbeat
  (Healthchecks.io / Pushover Glances) so a broken alert pipeline is itself detected. *Open*
- **Restart/flapping + reboot detection** — cAdvisor for `container_start_time_seconds`
  (`changes(...[10m]) > 2`) and `changes(node_boot_time_seconds[1h]) > 0`. *Open*
- **Backup job monitoring** — Pushgateway (or node textfile collector) + `BackupStale` alert
  (`time() - backup_last_success_timestamp > 48h`). *Specified in [`091`](./091-backup-coverage-and-staleness.md)*
- **NFS mount health alerting** — `node_filesystem_readonly{mountpoint=~"/mnt/.*"} == 1` and
  `absent(node_filesystem_avail_bytes{mountpoint="…"})` per known mount. *Open*
- **Alertmanager config validation in CI** — `amtool check-config` in `validate_alerts.yml`. *Open*
- **Grafana security overview dashboard** — single pane: fail2ban bans, TLS expiry, availability
  heatmap, (SSH logins / upgrade status if those candidates land). *Open*
- **Application-level error/log alerting** — Promtail/Alloy → Loki; alert on app error-rate spikes,
  stack traces, and OOM-kills (`kernel: Out of memory`) per service. Current alerting is host/infra +
  endpoint only, so a wedged app that still answers its port and doesn't saturate CPU/disk is invisible
  (only Caddy 5xx rate covers app correctness today). Highest-value gap alongside backup monitoring. *Specified in [`092`](./092-log-aggregation.md)*
- **LXC base Debian 12 → 13** — Debian 12 left regular security support on 2026-07-11 (LTS until
  2028-06-30); the PVE host is already on Debian 13 and lab templates exist (`lab-tpl-debian-13-*`).
  Template change plus rolling LXC rebuilds. Not urgent before 2028. *Open*
- **Per-container liveness** — cAdvisor (or docker exporter) `up`/health per container, not just host
  node_exporter + blackbox endpoint probes; catches a crashed/wedged container whose port still listens
  or whose host is otherwise healthy. Overlaps with the restart/flapping candidate above. *Open*
- **ACME/TLS renewal-failure alert** — detect Caddy failing to *renew* (DNS-01 error, rate-limit)
  before the cert is near expiry, rather than only alerting on raw `TLSCertExpiringSoon`. *Open*
- **Predictive disk-fill** — `predict_linear(node_filesystem_avail_bytes[6h], 24*3600) < 0` to warn on
  fast-filling disks before the static 85/95% thresholds trip. *Open*
- **Proxmox host/guest + storage health** — `pve` node_exporter/pve-exporter for per-VM/LXC state and
  ZFS/LVM pool health (degraded pool, failing disk); today only blackbox/self-metrics touch the PVE host. *Open; node_exporter on `pve` is
  part of [`091`](./091-backup-coverage-and-staleness.md)*
- **Drifted monitoring role defaults** (2026-10-22, spec 090) — the non-version values in
  `roles/monitoring_stack/defaults/main.yml` have drifted from `group_vars/monitoring/vars.yml`, e.g.
  `monitoring_install_dir` vs `monitoring_base_path`, and `grafana_domain` (`monitoring.local` vs
  `grafana.hus-sky.no`). Out of scope for 090 (research R-04). *Open*
- **Exporter pins outside the currency check** (2026-10-22, spec 090) — move
  `jellyfin_exporter_version` and `fail2ban_exporter_version` from role defaults into the
  `# Service versions` block of `group_vars/services/vars.yml`, so the 090 currency check covers
  them (spec 090 research R-10, out of scope there). *Open*

## Security hardening

- **SSH hardening role** — `ssh_hardening` via `lxc_base`: `PermitRootLogin prohibit-password`,
  `PasswordAuthentication no`, `MaxAuthTries 3`, drop-in config + sshd-alive alert. *Open*
- **Unattended security updates for LXCs** — `unattended-upgrades` (security-only, no auto-reboot) in
  `lxc_base`; today only the PVE host has it. *Open*
- **Proxmox firewall baseline** — datacenter/node/container deny-inbound default + per-service allow
  rules; integrate with Terraform container defs. *Open*
- **Login anomaly alerting** — Promtail/Alloy → Loki; alert on successful SSH from non-whitelisted IP,
  unexpected `sudo`, off-hours login. *Specified in [`092`](./092-log-aggregation.md)*
- **CrowdSec** — replace/supplement fail2ban with shared ban lists + community blocklists + Caddy
  bouncer; add exporter to monitoring. *Open*
- **PVE HTTPS via Caddy** — `pve.hus-sky.no` → `reverse_proxy https://192.168.1.112:8006`
  (`tls_insecure_skip_verify`), DNS rewrite, add to blackbox HTTPS probes. *Open*
- **fail2ban in `site.yml`** — `fail2ban.yml` is not imported by `site.yml`. *Partially done (PR #195):*
  the `fail2ban` role is now in the reverse_proxy/nextcloud/jellyfin service playbooks, so the gated
  per-service pipeline (Promote→Apply) deploys and keeps it in sync — a rebuild via the pipeline no
  longer drops it. `site.yml` / the rebuild orchestrator still don't import it (see next item). *Partial*
- **Ansible phase in rebuild orchestrator** — add an `ansible` phase (after `services`, before
  `verify`) running `site.yml` + `fail2ban.yml` so config/monitoring is restored without a manual run.
  *Open (partial — mount remediation already calls `task ansible:mounts`)*

## Manual steps to eliminate (from prod operations)

- Prod `prod.tfvars` is maintained by hand on PVE (`/var/lib/homelab-proxmox/tfvars/`) incl. the real
  API token secret; source `TF_VAR_proxmox_api_token_*` from a managed secret store instead.
  *Done (026-separate-prod-apply / 036-token-privilege-separation)*
- Manual Proxmox API token rotation/paste + token-ID alignment. *Done (036)*
