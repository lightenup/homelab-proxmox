# Improvement Candidates

## Current manual steps
- Maintain a prod tfvars copy on PVE at /var/lib/homelab-proxmox/tfvars/prod.tfvars (create/copy from repo), including the real proxmox_api_token_secret.
- Rotate and paste the Proxmox API token secret manually into prod.tfvars; validate token ID matches terraform@pve!terraform-token.
- Align local/CI Terraform runs with the correct var-file: ensure prod.tfvars exists on PVE before triggering prod apply.
- Work around prerequisite checks expecting a feature branch (currently blocks check-prerequisites on main) when doing hotfixes.

- Copy scripts/dr into a dedicated `~/dr-drill-sources/` folder on PVE so long-running drills aren’t overwritten by rsync/builds.

- Limited visibility into “what’s currently in LAB” (running LXCs, IPs, health, mount status). Today this requires ad-hoc `pct list`, `pct config <id>`, and SSHing into guests.

## Recent automation wins (to build on)

- Task-first operator workflows via `Taskfile.yml` (single entrypoint)
- Inventory generation, tfstate backup, and healthcheck runner migrated into Python with unit + smoke tests
- Service lifecycle now runs via tasks (`service:add|change|remove`) instead of ad-hoc shell scripts
- Ongoing approach: keep path-stable shims only when required; otherwise deprecate scripts and remove all references

## Why automate
- Reduce 401 auth failures and drift from missing/placeholder secrets on PVE.
- Eliminate manual secret pasting by sourcing TF_VAR_proxmox_api_token_* via CI secrets/KeyVault and templating prod.tfvars from a managed secret store.
- Enforce prerequisite gating regardless of branch name, with an override path for hotfixes.
- Keep PVE tfvars in sync with repo examples to avoid missing files during prod applies.

- Add a lightweight LAB “inventory snapshot” artifact to each apply/plan run (and optionally on-demand):
	- list of containers (vmid, hostname, status, IPv4)
	- per-service evidence pointers (latest run id / evidence dir)
	- workload checks summary (e.g., `/media/video` mounted RO for Jellyfin)
	- quick links/paths to state (`/var/lib/homelab-proxmox/state/services/<service>/terraform.tfstate`) and evidence packs

- Package the DR scripts (and templates) into a portable bundle (versioned tarball or task) to make drills more mobile and avoid manual copy steps.

---

## Learnings from nextcloud deploy (February 2026)

Deploying nextcloud required 12 incremental fix commits across ~10 CI runs. Every issue below was discoverable before the first pipeline run but wasn't, because there is no pre-deploy validation that catches these classes of errors.

### What went wrong (chronological)

| # | Failure | Root cause | Time wasted |
|---|---------|-----------|-------------|
| 1 | Terraform plan: missing variable | GitHub secret `PROXMOX_API_TOKEN_SECRET` didn't exist | 1 run |
| 2 | Terraform apply: 401 invalid token | Bitwarden had the password, not the API token | 1 run |
| 3 | Terraform apply: 403 bind mount | `terraform@pve` token can't create bind mounts (root@pam only) | 2 runs |
| 4 | SSH wait timeout (300s blind) | Deploy key not in container; no network diagnostics | 1 run |
| 5 | Container unreachable (100% packet loss) | `service_ips` used `192.168.20.0/24` but network is `192.168.1.0/24` | 1 run |
| 6 | `apt-get update` hangs | Tailscale hijacked PVE resolv.conf to `100.100.100.100`; no `nameserver` in tfvars | 1 run |
| 7 | `nextcloud_db_name` undefined | Ansible role had no DB defaults; no vault file for secrets | 1 run |
| 8 | `.env.j2` not found | `.gitignore` pattern `.env*` excluded the Jinja template | 1 run |
| 9 | Nextcloud container crash-loop | Entrypoint `rsync --chown` fails on NFS (root_squash) | 2 runs |
| 10 | `nextcloud_backup_path` undefined | Backup role had no defaults | 1 run |
| 11 | `chown` on NFS backup dir | Same NFS root_squash issue in backup role | 1 run |
| 12 | Missing healthcheck script | Orchestrator expects `scripts/healthcheck/<service>.sh` | 1 run |

### Improvements to make

#### 1. Service definition manifest + scaffolding generator
**Problem**: Adding a service touches 29 files across 6 categories. 17 of those are pure boilerplate. Missing any one of them causes a CI failure that takes ~3 minutes to discover.
**Proposal**: Create a `service.yml` manifest per service (name, IP, port, cores, memory, mountpoints, NFS paths, docker-compose vars, healthcheck). A generator (`task service:scaffold`) reads it and creates all boilerplate files: Terraform root (4 files), Ansible role skeleton, host_vars, playbook import, healthcheck script, scope allowlist entry, workflow option, docs entry. The existing `task service:add` does a fraction of this -- extend it.

#### 2. Pre-deploy preflight check (`task deploy:preflight`)
**Problem**: Most failures above (wrong subnet, missing vars, missing templates, missing healthcheck) are statically detectable before any CI run.
**Proposal**: A local preflight command that validates:
- All Jinja `{{ var }}` refs in role templates resolve to a defined default, group_var, or vault var
- All files referenced by Ansible tasks exist and are tracked by git (catches `.gitignore` exclusions)
- `service_ips` subnet matches `network_gateway` subnet
- `nameserver` is set when PVE uses Tailscale
- Healthcheck script exists for the service
- Scope allowlist entry exists
- Workflow options include the service name

#### 3. NFS compatibility documentation and Ansible guard
**Problem**: NFS with root_squash silently breaks `chown` in Docker entrypoints and Ansible `file` tasks. This caused 3 separate failures.
**Proposal**: (a) Document the NFS constraint in the service onboarding checklist: "If a mount is NFS, do not use `owner`/`group` in `ansible.builtin.file` tasks, and mount outside Docker entrypoint rsync targets." (b) Add an Ansible lint rule or preflight check that flags `owner:`/`group:` on paths under known NFS mounts.

#### 4. Network subnet validation in Terraform
**Problem**: `service_ips` used `192.168.20.x` for years while the actual network was `192.168.1.x`. This was documented in spec 001 but never enforced.
**Proposal**: Add a Terraform `validation` block on the `network_gateway` and `service_ips` variables that checks all IPs share the same /24 prefix as the gateway. Catches subnet mismatches at `terraform plan` time.

#### 5. PVE tfvars drift detection
**Problem**: The PVE `lab.tfvars` is not in the repo (gitignored, contains secrets). It drifts from reality silently. The `192.168.20.x` subnet, missing `nameserver`, and missing `nextcloud` entry were all drift.
**Proposal**: Add a CI step that compares PVE tfvars structure (keys, not values) against the `.tfvars.example` files. Flag any keys present in the example but missing from PVE, or vice versa. Secrets are compared by presence, not value.

#### 6. Static prod inventory for config-only deploys
**Problem**: The prod inventory (`inventories/prod/hosts.yml`) only contains the Proxmox host and infra nodes. Service LXCs are not listed — they only exist in dynamically generated inventories created by `pve-service-deploy` on the PVE host. This means config-only changes to existing LXCs (e.g., updating Caddy templates, changing Nextcloud env vars) cannot be run from a developer laptop without ad-hoc inventory hacks.
**Proposal**: Add a `services` group to `inventories/prod/hosts.yml` with static entries for each service LXC (hostname, `ansible_host` IP, `ansible_user`). This lets `ansible-playbook playbooks/<service>.yml -i inventories/prod/hosts.yml` work directly from a laptop for config-only changes, while `pve-service-deploy` continues to use generated inventories for full provisioning. The service entries should match the hostnames expected by `host_vars/` and playbook `hosts:` directives.

#### 7. PVE HTTPS via Caddy
**Problem**: PVE host (192.168.1.112:8006) uses a self-signed Proxmox CA cert. Works for direct LAN access but no trusted TLS. Not probed by blackbox.
**Proposal**: Add `pve.hus-sky.no` behind Caddy with a Let's Encrypt cert. Requires: (a) DNS record + AdGuard DNS rewrite for LAN, (b) `pve.caddy.j2` template with `reverse_proxy https://192.168.1.112:8006` and `tls_insecure_skip_verify` (upstream is self-signed), (c) websocket support for noVNC/xterm.js console (Caddy handles by default), (d) add to blackbox HTTPS probe targets. Small scope — one Caddy template, one reverse_proxy role task, DNS entry. Same pattern as existing services.

#### 8. AdGuard LXC provisioning
**Problem**: AdGuard LXC does not exist on Proxmox (no container among the 6 running). Terraform module `adguard_lxc` is defined but never applied to prod. The `adguard.hus-sky.no` blackbox probe fails, and the AdGuard exporter (Tier B) has no host to run on.
**Proposal**: Full service provisioning: (a) `prod.tfvars` with Proxmox API credentials, (b) `terraform apply -target=module.adguard_lxc`, (c) `ansible-playbook playbooks/adguard.yml` (installs AdGuard Home + exporter), (d) AdGuard Home initial setup (web UI wizard), (e) DNS rewrites for `*.hus-sky.no` → 192.168.1.211. Medium scope. Blocks: AdGuard exporter metrics, DNS monitoring, blackbox probe for adguard.hus-sky.no.

#### 9. fail2ban.yml not in site.yml
**Problem**: `ansible/playbooks/site.yml` imports `services.yml` (which covers adguard, immich, jellyfin, nextcloud, reverse_proxy) and `monitoring.yml`, but does NOT import `fail2ban.yml`. A full `site.yml` run after a rebuild would restore the entire monitoring stack but leave fail2ban unconfigured on all 3 hosts (reverse_proxy, jellyfin, nextcloud).
**Proposal**: Add `fail2ban.yml` to `site.yml` after `services.yml` and before `monitoring.yml` (fail2ban must be running before Prometheus scrape targets for fail2ban-exporter come online). Needs testing to confirm idempotency and ordering.

#### 10. Rebuild orchestrator has no Ansible phase
**Problem**: The rebuild orchestrator (`scripts/rebuild/run-rebuild.sh`) has 5 phases: mounts, restore, iac, services, verify. The `services` phase only runs Terraform (creates LXC containers). There is no phase that runs Ansible playbooks to configure the containers. After a rebuild, the operator must manually run `ansible-playbook playbooks/site.yml` (and `fail2ban.yml`, see candidate 9) to restore all service configuration, monitoring, alerting, dashboards, and fail2ban.
**Proposal**: Add an `ansible` phase to the rebuild orchestrator (after `services`, before `verify`) that runs `site.yml` + `fail2ban.yml` against the freshly provisioned containers. Requires vault password access during rebuild. Medium-high scope — touches rebuild config, rebuild.sh, and needs careful ordering and error handling.

#### 11. Ansible vault bootstrap
**Problem**: Secrets had to be manually generated and added to a vault file. The vault password file had to be manually placed at the correct path. There was no vault file at all until nextcloud needed one.
**Proposal**: `task service:scaffold` generates a vault template with placeholder values and instructions. `task vault:init` creates the vault password file at the expected path if it doesn't exist. Document the vault password location in the onboarding checklist.

#### 12. Watchdog / DeadMansSwitch alert
**Problem**: There is no alert that fires when the alerting pipeline itself is broken. If Prometheus stops evaluating rules, or Alertmanager stops sending notifications, the failure is silent -- no alerts means no alert about missing alerts.
**Proposal**: Add a `Watchdog` alert rule that always fires (`expr: vector(1)`). Route it to an external heartbeat service (e.g., Healthchecks.io free tier, or Pushover Glances API) that expects a ping every N minutes. If the ping stops, the external service notifies the operator. Requires: (a) one Prometheus rule, (b) one Alertmanager receiver + route, (c) an external heartbeat endpoint. Small scope.

#### 13. Container restart / flapping detection
**Problem**: `ServiceDown` requires `up == 0` for 2 minutes. A Docker container that crash-loops and restarts every 90 seconds will never trigger it, but is clearly broken. Node reboots also go undetected unless the node stays down for the full `for` duration.
**Proposal**: (a) Add cAdvisor to the monitoring stack to get `container_start_time_seconds`. Alert on `changes(container_start_time_seconds[10m]) > 2`. (b) For LXC reboots, alert on `changes(node_boot_time_seconds[1h]) > 0`. Medium scope -- cAdvisor is one container + one Prometheus scrape target + two alert rules.

#### 14. Backup job monitoring
**Problem**: The monitoring stack has a backup cron job (`backup_cron.yml`) but no alert if it fails or misses a scheduled run. A silent backup failure means data loss goes unnoticed until a restore is needed.
**Proposal**: (a) Add a Prometheus Pushgateway to the monitoring stack. (b) Modify the backup script to push a `backup_last_success_timestamp` metric on completion. (c) Add a `BackupStale` alert: `time() - backup_last_success_timestamp > 86400 * 2` (no successful backup in 48 hours). Alternatively, use `node_textfile_collector` with a timestamp file written by the backup script. Small-medium scope.

#### 15. NFS mount health alerting
**Problem**: NFS mounts can silently go stale or become read-only. Services that depend on NFS (Nextcloud data, Jellyfin media, monitoring backups) continue running but fail on writes or serve stale data. There is no alert for this condition.
**Proposal**: (a) Alert on `node_filesystem_readonly{mountpoint=~"/mnt/.*"} == 1` -- catches NFS mounts that flip to read-only. (b) Alert on disappearance of expected mountpoints: `absent(node_filesystem_avail_bytes{mountpoint="/mnt/nextcloud"})` for each known NFS mount. (c) Optionally, a synthetic write-probe (cron job that writes a timestamp file and reads it back, pushing a metric on failure). Small scope for (a) and (b) -- two alert rules.

#### 16. Alertmanager config validation in CI
**Problem**: Prometheus alert rules are validated with `promtool check rules` during deployment, but the Alertmanager configuration is not validated. A syntax error in `alertmanager.yml.j2` (e.g., bad YAML indentation in a Pushover receiver) would only be caught when Alertmanager fails to start.
**Proposal**: Add `amtool check-config` to the `validate_alerts.yml` task file, running against the deployed `alertmanager.yml`. Requires `amtool` binary on the monitoring LXC (ships with the Alertmanager Docker image, can be exec'd). Small scope -- one Ansible task.

#### 17. SSH hardening role
**Problem**: LXC containers are created from Proxmox templates with permissive SSH defaults (root login with password). There is no enforced baseline for SSH configuration across the fleet.
**Proposal**: Create an `ssh_hardening` Ansible role applied via `lxc_base` that enforces: `PermitRootLogin prohibit-password`, `PasswordAuthentication no`, `MaxAuthTries 3`, `AllowAgentForwarding no`, `X11Forwarding no`. Role deploys `/etc/ssh/sshd_config.d/99-hardening.conf` (drop-in, no clobbering) and restarts `sshd`. Add a monitoring contract alert rule: `node_systemd_unit_state{name="sshd.service"} != 1` to detect sshd crashes post-hardening. Small scope -- one role, one template, one service restart handler.

#### 18. Unattended security updates for LXCs
**Problem**: Only the Proxmox host has `unattended-upgrades`. The 5 service LXCs receive updates only during manual monthly runs (`update_monthly.yml`). A critical CVE published between monthly runs remains unpatched for up to 30 days.
**Proposal**: Add `unattended-upgrades` to the `lxc_base` role, configured for security-only updates (aligned with `security_only_repos`). Deploy `/etc/apt/apt.conf.d/50unattended-upgrades` restricting to `Debian-Security` origin, and `/etc/apt/apt.conf.d/20auto-upgrades` enabling daily checks. Add `Unattended-Upgrade::Mail` for notification and `Unattended-Upgrade::Automatic-Reboot "false"` to avoid surprise reboots. Small scope -- two config templates added to `lxc_base`.

#### 19. Proxmox firewall baseline
**Problem**: The Proxmox host and LXC containers have no proactive firewall. fail2ban provides reactive banning on 3 hosts, but all ports are open by default on all hosts. An accidental service binding to `0.0.0.0` is immediately LAN-exposed.
**Proposal**: Enable Proxmox's built-in firewall at datacenter + node + container level via Ansible. Define a baseline policy: deny inbound by default, allow SSH (22), allow service ports per container (e.g., 8080 for Nextcloud, 3000 for Grafana), allow Prometheus scrape ports from the monitoring LXC only. Managed via `/etc/pve/firewall/cluster.fw` and per-container `.fw` files. Medium scope -- new role, per-service port definitions in host_vars, integration with Terraform container definitions.

#### 20. Login anomaly alerting (new SSH sessions from unknown IPs)
**Problem**: fail2ban detects brute-force failures but not successful unauthorized access. A compromised key or leaked password results in a successful login that generates no alert. The first sign of compromise is damage, not the login itself.
**Proposal**: Deploy Promtail (or Alloy) sidecar on each LXC to ship auth logs (`/var/log/auth.log`) to a Loki instance on the monitoring stack. Create alert rules for: (a) successful SSH login from an IP not in a trusted whitelist, (b) `sudo` commands executed outside expected automation patterns, (c) login outside business hours. Requires: Loki + Promtail containers, one Grafana datasource, LogQL alert rules. Medium-high scope but high security value -- moves from reactive (ban after attack) to proactive (alert on suspicious success).

#### 21. CrowdSec collaborative intrusion prevention
**Problem**: fail2ban operates independently on each host with local-only ban lists. An attacker that probes one service gets banned on that host but can freely target others. There is no shared threat intelligence across the homelab, and no benefit from community-reported malicious IPs.
**Proposal**: Replace or supplement fail2ban with CrowdSec on each LXC. CrowdSec provides: (a) shared local ban list across all hosts via the CrowdSec Central API, (b) community blocklists (free tier includes curated IP reputation feeds), (c) bouncers for Caddy (plugin), iptables, and Nextcloud. Deploy CrowdSec agent on each LXC, register with the free CrowdSec Console, install the Caddy bouncer on reverse_proxy. Add a `crowdsec-exporter` scrape target to monitoring contracts for Prometheus metrics. Medium scope -- replaces fail2ban role or runs alongside it.

#### 22. Grafana security overview dashboard
**Problem**: Security metrics exist (fail2ban bans, blackbox probes, TLS expiry) but are spread across individual service dashboards. There is no single-pane-of-glass view showing the security posture of the homelab.
**Proposal**: Create a dedicated Grafana dashboard aggregating: (a) fail2ban ban counts and top banned IPs across all hosts, (b) TLS certificate expiry countdown for all endpoints, (c) endpoint availability heatmap, (d) SSH login events (if candidate #20 is implemented), (e) unattended-upgrades status per host (if candidate #18 is implemented). Provisioned via `monitoring_contract.dashboard_file` pattern. Small-medium scope -- one JSON dashboard file, no new data sources required for (a)-(c).
