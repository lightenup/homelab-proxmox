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
- 026-separate-prod-apply: Added Bash + Python 3 (repo scripts), YAML (GitHub Actions), Terraform (HCL), Ansible (YAML) + GitHub Actions (workflow_dispatch, environments), Terraform CLI, Ansible, Proxmox (PVE) host, existing repo scripts under `scripts/lab/*`
- 026-separate-prod-apply: Added Bash + Python 3 (runner-provided) + GitHub Actions YAML
- 024-pipeline-promotion-ux: Added Bash 5.x (Proxmox host scripts), GitHub Actions YAML (workflow definitions), Python 3.x (evidence verification)


<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
