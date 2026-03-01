# homelab-proxmox Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-01-04

## Active Technologies
- Bash 5.x (existing `pve-lab` script) + jq (JSON processing), git (provenance capture), existing Ansible playbooks (019c1-semantic-safety-closure)
- File-based evidence packs in `artifacts/lab-runs/<runid>/` (019c1-semantic-safety-closure)
- Python 3 (stdlib only: json, pathlib, sys, argparse) + None (Standard Library) (019e1-evidence-governance-strictness)
- Filesystem (JSON artifacts in `artifacts/` and `scripts/lab/fixtures/`) (019e1-evidence-governance-strictness)
- Bash (scripts), Python 3.x (verify_evidence.py), Ansible 2.16+ (roles/playbooks) + Ansible core modules, Proxmox CLI (qm/pct), Python stdlib only for verify mutations (020-rebuild-acceptance-hardening)
- Filesystem evidence packs (artifacts/*), no databases (020-rebuild-acceptance-hardening)
- Bash (5.x), Terraform (1.x), Ansible (2.x), Python (3.x), GitHub Actions (YAML) + Terraform `telmate/proxmox` provider + existing `terraform/modules/lxc_service`, Ansible, `jq`, SSH/rsync, `act` (local CI simulation) (022-lxc-gated-deploy)
- Local Terraform state on runner; filesystem evidence packs on PVE under `/var/lib/homelab-proxmox/artifacts/<runs-dir>/<run_id>` (022-lxc-gated-deploy)
- Bash 5.x (Proxmox host scripts), GitHub Actions YAML (workflow definitions), Python 3.x (evidence verification) (024-pipeline-promotion-ux)
- Bash + Python 3 (runner-provided) + GitHub Actions YAML (026-separate-prod-apply)
- Files on PVE under `/var/lib/homelab-proxmox/artifacts/service-deploy-runs/<run_id>` (evidence packs) (026-separate-prod-apply)
- Bash + Python 3 (repo scripts), YAML (GitHub Actions), Terraform (HCL), Ansible (YAML) + GitHub Actions (workflow_dispatch, environments), Terraform CLI, Ansible, Proxmox (PVE) host, existing repo scripts under `scripts/lab/*` (026-separate-prod-apply)
- Files on PVE host (Terraform state local on PVE; evidence packs under `/var/lib/homelab-proxmox/artifacts/...`) (026-separate-prod-apply)
- Python 3.x (existing repo subproject in `python/`) + Runtime: Python stdlib (preferred), existing repo utilities. Dev/test: `pytest`, `mutmut` (028-sunset-shell-tools)
- Local filesystem repo artifacts; Terraform/Ansible state/artifacts as already implemented (no new state system introduced) (028-sunset-shell-tools)
- Python 3.11 (mutmut/pytest tooling), shell scripts for automation + mutmut, pytest, uv, GitHub Actions (029-mutmut-shared-cache)
- NAS NFS share mounted on PVE at `/mnt/nas/homelab_ci` (per-branch cache subdirs) (029-mutmut-shared-cache)
- Terraform (HCL), Ansible (YAML), Python 3.x, GitHub Actions (YAML), shell scripts + elmate/proxmox Terraform provider, Ansible, Taskfile, GitHub Actions, Python automation scripts (031-lxc-lifecycle-pipeline)
- Local Terraform state on PVE host; NFS mounts for service data (NAS) (031-lxc-lifecycle-pipeline)
- Terraform (HCL), Ansible (YAML), Python 3.x, shell scripts + elmate/proxmox Terraform provider, Ansible, Taskfile, Python orchestration scripts (032-audit-rebuild-readiness)
- Local Terraform state on PVE host; NAS-backed NFS mounts for backups and shared data (032-audit-rebuild-readiness)
- Shell scripts + Python (existing orchestration), Terraform (HCL), Ansible (YAML) + Taskfile, scripts/lab, telmate/proxmox Terraform provider, Ansible (033-idempotent-rebuild)
- Local Terraform state on PVE; NAS-backed NFS mounts for backups and shared data (033-idempotent-rebuild)
- N/A (third-party application; IaC is Terraform HCL + Ansible YAML) + Nextcloud 30 (Docker), MariaDB 11, Redis 7, Caddy (existing), Docker + Docker Compose (existing `geerlingguy.docker` role) (034-add-nextcloud)
- MariaDB for metadata (local disk); NFS mount from Synology NAS for user files (034-add-nextcloud)
- HCL (Terraform ≥ 1.5.7), YAML (Ansible), Jinja2 (templates), Bash (backup scripts) + `telmate/proxmox` Terraform provider (= 2.9.11), `community.docker.docker_compose_v2` Ansible module, `geerlingguy.docker` Ansible role (034-add-nextcloud)
- MariaDB 11 (local disk), Redis 7 (local disk), user files on Synology NAS via NFS (034-add-nextcloud)
- Bash 5.x (orchestrator), HCL/Terraform 1.6.x (infrastructure), Python 3.x (inline parsing) + Proxmox `pct` CLI, Terraform (Telmate provider 2.9.x), jq, python3 (036-token-privilege-separation)
- N/A (no database; config in tfvars, state in local terraform.tfstate) (036-token-privilege-separation)
- Bash (POSIX-compatible, runs on Debian 12 Proxmox host) + `pct` (Proxmox CLI), `ping`, `ssh-keygen`, `grep`, `sudo` (037-ci-fresh-deploy-fixes)
- N/A (evidence artifacts are flat files in the evidence pack) (037-ci-fresh-deploy-fixes)
- Bash (POSIX-compatible, runs on Debian 12 Proxmox host) + `sed`, `awk`, `grep`, `sha256sum`/`shasum` (standard POSIX tools) (038-tfvars-template-separation)
- Ansible 2.10+, Jinja2 templates, Go 1.22+ (build dependency for xcaddy) + Caddy v2 (custom build), xcaddy, `caddy-dns/lego-deprecated`, `go-acme/lego` v4.9.1 (039-https-services)
- N/A (certificates managed by Caddy in `/var/lib/caddy/`) (039-https-services)
- Ansible (YAML/Jinja2), Prometheus 3.x PromQL, Grafana 12.x JSON Schema v1 + Ansible roles, Docker Compose, Prometheus node_exporter v1.10.2 (040-monitoring-overhaul)
- Prometheus TSDB (Docker volume), Grafana SQLite (Docker volume) (040-monitoring-overhaul)
- Ansible 2.x (YAML/Jinja2), Telegraf TOML, Grafana JSON, Go binaries + Docker (geerlingguy.docker), Telegraf 1.37.0, Prometheus v3.8.1, Grafana 12.3.1 (041-monitoring-tier-b)
- N/A (metrics stored in Prometheus TSDB, already provisioned) (041-monitoring-tier-b)

- Bash (Harness), Ansible 2.14+ (Playbooks) + `pve-lab` script, Proxmox VE 9 (Debian 13) repositories (019b-proxmox-lab-harness-tier2)

## Project Structure

```text
.github/
	workflows/

terraform/
	modules/
		lxc_service/

ansible/
	inventories/
	playbooks/
	roles/

scripts/
	lab/
		lib/

docs/
specs/
```

## Commands

# Add commands for Bash (Harness), Ansible 2.14+ (Playbooks)

## Code Style

Bash (Harness), Ansible 2.14+ (Playbooks): Follow standard conventions

## Recent Changes
- 041-monitoring-tier-b: Added Ansible 2.x (YAML/Jinja2), Telegraf TOML, Grafana JSON, Go binaries + Docker (geerlingguy.docker), Telegraf 1.37.0, Prometheus v3.8.1, Grafana 12.3.1
- 040-monitoring-overhaul: Added Ansible (YAML/Jinja2), Prometheus 3.x PromQL, Grafana 12.x JSON Schema v1 + Ansible roles, Docker Compose, Prometheus node_exporter v1.10.2
- 039-https-services: Added Ansible 2.10+, Jinja2 templates, Go 1.22+ (build dependency for xcaddy) + Caddy v2 (custom build), xcaddy, `caddy-dns/lego-deprecated`, `go-acme/lego` v4.9.1


<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
