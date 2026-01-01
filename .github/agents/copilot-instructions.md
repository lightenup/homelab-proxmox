# homelab-proxmox Development Guidelines

Auto-generated from all feature plans. Last updated: 2025-12-30

## Active Technologies
- Bash 5.x (existing `pve-lab` script) + jq (JSON processing), git (provenance capture), existing Ansible playbooks (019c1-semantic-safety-closure)
- File-based evidence packs in `artifacts/019-lab/<runid>/` (019c1-semantic-safety-closure)
- Python 3 (stdlib only: json, pathlib, sys, argparse) + None (Standard Library) (019e1-evidence-governance-strictness)
- Filesystem (JSON artifacts in `artifacts/` and `scripts/lab/fixtures/`) (019e1-evidence-governance-strictness)
- Bash (scripts), Python 3.x (verify_evidence.py), Ansible 2.16+ (roles/playbooks) + Ansible core modules, Proxmox CLI (qm/pct), Python stdlib only for verify mutations (020-rebuild-acceptance-hardening)
- Filesystem evidence packs (artifacts/*), no databases (020-rebuild-acceptance-hardening)

- Bash (Harness), Ansible 2.14+ (Playbooks) + `pve-lab` script, Proxmox VE 9 (Debian 13) repositories (019b-proxmox-lab-harness-tier2)

## Project Structure

```text
src/
tests/
```

## Commands

# Add commands for Bash (Harness), Ansible 2.14+ (Playbooks)

## Code Style

Bash (Harness), Ansible 2.14+ (Playbooks): Follow standard conventions

## Recent Changes
- 020-rebuild-acceptance-hardening: Added Bash (scripts), Python 3.x (verify_evidence.py), Ansible 2.16+ (roles/playbooks) + Ansible core modules, Proxmox CLI (qm/pct), Python stdlib only for verify mutations
- 019f-rebuild-orchestrator: Added Rebuild Orchestrator (`pve-lab rebuild`), Baseline Checks (`HOST-*`, `TPL-*`), and Offline Fixtures
- 019e1-evidence-governance-strictness: Added Python 3 (stdlib only: json, pathlib, sys, argparse) + None (Standard Library)


<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
