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
- 063-ci-confidence-path-gate: Added GitHub Actions workflow YAML; Bash (POSIX/`bash`) in `run:` steps; `git` for + `actions/checkout@v4` (with `fetch-depth: 0` for merge-base), `git`,
- 062-eurooffice-deploy: Added HCL (Terraform, `telmate/proxmox`), YAML (Ansible 2.x), Jinja2, Caddyfile — no new language + `modules/lxc_service` (Terraform), `geerlingguy.docker` + `community.docker.docker_compose_v2` (Ansible), public image `ghcr.io/euro-office/documentserver:v9.3.2`, Nextcloud `eurooffice` connector app v11.0.1
- 060-nextcloud-upgrade-33-34: Added YAML (Ansible 2.x), Jinja2, Bash — no new language. + `community.docker.docker_compose_v2`; official `nextcloud:33` / `nextcloud:34`


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
