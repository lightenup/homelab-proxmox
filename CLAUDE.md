# homelab-proxmox Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-05-25

## Active Technologies
- YAML (Ansible 2.x), Jinja2 templates, Caddyfile syntax, static HTML/CSS + vanilla JS (no framework) + Caddy (custom xcaddy build w/ Domeneshop DNS, already deployed); Prometheus v3.8.1 + blackbox_exporter v0.28.0 (already deployed, feature `042`); `community.general` / builtin Ansible modules only (045-landing-page)
- N/A — landing assets are generated files under `/var/www/hus-sky` on the reverse-proxy LXC; no database (045-landing-page)
- HCL (Terraform, `telmate/proxmox`), YAML (Ansible 2.x), Jinja2, Bash (backup + `lxc_service` Terraform module; `geerlingguy.docker` + `community.docker` (048-financial-scenario-v2-deploy)
- SQLite (WAL mode) scenario store at `/app/data/scenarios.db` inside the `api` container, (048-financial-scenario-v2-deploy)
- YAML (Ansible 2.x), Jinja2, Bash — no new language. + `community.docker.docker_compose_v2`; official `nextcloud:33` / `nextcloud:34` (060-nextcloud-upgrade-33-34)
- MariaDB on local LXC disk (`/opt/nextcloud/mariadb`); **user data on Synology NFS** (060-nextcloud-upgrade-33-34)
- HCL (Terraform, `telmate/proxmox`), YAML (Ansible 2.x), Jinja2, Caddyfile — no new language + `modules/lxc_service` (Terraform), `geerlingguy.docker` + `community.docker.docker_compose_v2` (Ansible), public image `ghcr.io/euro-office/documentserver:v9.3.2` (AGPL fork of ONLYOFFICE; rollback target `onlyoffice/documentserver:9.3`), Nextcloud `eurooffice` connector app v11.0.1 (062-eurooffice-deploy)
- Docker bind volumes on the LXC's local disk for data/logs (`/opt/eurooffice-data`); no NFS bind-mount (documents live in Nextcloud). No user-data backup in scope. (062-eurooffice-deploy)
- GitHub Actions workflow YAML; Bash (POSIX/`bash`) in `run:` steps; `git` for + `actions/checkout@v4` (with `fetch-depth: 0` for merge-base), `git`, (063-ci-confidence-path-gate)
- N/A — no persistent data. Decision lives only in a job output for the run's lifetime. (063-ci-confidence-path-gate)
- HCL (Terraform, `telmate/proxmox`), YAML (Ansible 2.x), Jinja2, Bash. No new language. + `modules/lxc_service` (Terraform); `geerlingguy.docker` + `community.docker.docker_compose_v2` (Ansible); `ghcr.io/berriai/litellm` (pinned, non-`latest`); `postgres:17-alpine`; `tailscale/tailscale` (userspace sidecar) (064-llm-router)
- PostgreSQL on the LXC's local disk (`/opt/llm-router-data/postgres`) for virtual keys, budgets and `LiteLLM_SpendLogs`. No NFS mount (`features_mount` omitted) — FR-012. No user data persisted; prompt/response bodies not logged. (064-llm-router)
- No application code (FR-026) — configuration only: HCL, YAML (Ansible 2.x), Jinja2 + `modules/lxc_service` (Terraform); `geerlingguy.docker` + `community.docker.docker_compose_v2` (Ansible); Open WebUI and SearXNG images pinned non-`latest`; the `064` gateway; oMLX embedding + reranker models on the inference hos (065-hermes-ai-workspace)
- SQLite + vector store on the LXC's local disk, bind-mounted for backup to Synology; no NFS for state (FR-019) (065-hermes-ai-workspace)
- HCL (Terraform, `telmate/proxmox`), YAML (Ansible 2.x), Jinja2, Bash, Go + `modules/lxc_service`; `geerlingguy.docker` + (082-ntfy-push-service)
- SQLite message cache and auth DB under `/opt/ntfy-data` on the LXC's local disk. Both (082-ntfy-push-service)
- YAML (Ansible 2.x), Jinja2, Bash; HCL only if LXC memory must grow. No (083-hermes-agent-runtime)
- agent data on the LXC's local disk under `{{ hermes_data_dir }}/agent`. It holds SQLite (083-hermes-agent-runtime)
- Ansible, Jinja2 systemd unit template, Bash + `geerlingguy.docker` (`docker_daemon_options`), `community.docker.docker_compose_v2` (089-backup-log-rotation-fixes)
- Synology NAS over NFS: `/mnt/nas-backup` on `pve`, `/mnt/immich` bind mount on `immich` (089-backup-log-rotation-fixes)

- HCL (Terraform), YAML (Ansible), JSON (Grafana dashboard), Caddyfile (reverse proxy) + `telmate/proxmox` Terraform provider, `lxc_service` Terraform module, `geerlingguy.docker` Ansible role, `community.docker.docker_compose_v2` Ansible module (044-transcriber-proxmox-deploy)

## Project Structure

```text
src/
tests/
```

## Commands

# Add commands for HCL (Terraform), YAML (Ansible), JSON (Grafana dashboard), Caddyfile (reverse proxy)

## Code Style

HCL (Terraform), YAML (Ansible), JSON (Grafana dashboard), Caddyfile (reverse proxy): Follow standard conventions

## Recent Changes
- 089-backup-log-rotation-fixes: PVE backup unit sandbox fix, immich_backup wired into immich.yml, Docker json-file log rotation via `docker_daemon_options`
- 083-hermes-agent-runtime: Added YAML (Ansible 2.x), Jinja2, Bash; HCL only if LXC memory must grow. No
- 082-ntfy-push-service: Added HCL (Terraform, `telmate/proxmox`), YAML (Ansible 2.x), Jinja2, Bash, Go + `modules/lxc_service`; `geerlingguy.docker` +


<!-- MANUAL ADDITIONS START -->

## Working with Git (Zscaler constraint)

**`git push` and SSH to GitHub are blocked by Zscaler on the dev Mac** — the `git-receive-pack`
upload returns HTTP 403, and SSH is dropped on ports 22/443. This affects any shell on the Mac.
Committing locally works; only the push leg is blocked. (A non-fast-forward rejection can appear
first and look normal — that's git bailing before it uploads; a force-push still 403s.)

To land commits, **push via the GitHub Git-Data API with `gh api`** (blobs → tree → commit → ref),
then `git fetch origin <branch> && git reset --hard origin/<branch>` to realign local history.
Open PRs with `gh pr create`. `git fetch`/`clone` over HTTPS work.

Pipeline deploys run on the `pve` host (which has unrestricted GitHub access) and are **unaffected**
by the Mac's push block. Full procedure and gotchas: [AGENTS.md](./AGENTS.md).

<!-- MANUAL ADDITIONS END -->
