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

#### 6. Ansible vault bootstrap
**Problem**: Secrets had to be manually generated and added to a vault file. The vault password file had to be manually placed at the correct path. There was no vault file at all until nextcloud needed one.
**Proposal**: `task service:scaffold` generates a vault template with placeholder values and instructions. `task vault:init` creates the vault password file at the expected path if it doesn't exist. Document the vault password location in the onboarding checklist.
