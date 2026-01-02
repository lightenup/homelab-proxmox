# Implementation Plan: Proxmox CI hardening

**Branch**: `021-proxmox-ci-hardening` | **Date**: 2026-01-02 | **Spec**: [specs/021-proxmox-ci-hardening/spec.md](specs/021-proxmox-ci-hardening/spec.md)
**Input**: Feature specification from specs/021-proxmox-ci-hardening/spec.md

**Note**: Generated via /speckit.plan. Phase outputs: research.md (Phase 0), data-model.md/contracts/quickstart.md (Phase 1), tasks.md (Phase 2).

## Summary

Make proxmox-apply run green on the pi-ci runner using ci@pve only, with artifacts rooted at /var/lib/homelab-proxmox/artifacts and excluded from rsync, least-privilege sudoers for ci (sudo -n helper), robust pve-lab dependency checks and checks.json generation, expanded provisioning SSH wait with automatic evidence collection, and documentation for Ansible/Terraform operating without root.

## Technical Context

**Language/Version**: Bash scripts, GitHub Actions YAML, Ansible 2.x, Terraform with telmate/proxmox provider 2.x
**Primary Dependencies**: ssh/rsync/jq on PVE; qm/pct/pvesh CLI; GitHub Actions on pi-ci; Proxmox API for Terraform if used; Ansible become via sudo -n
**Storage**: Filesystem artifacts on PVE at /var/lib/homelab-proxmox/artifacts; no DB changes
**Testing**: scripts/lab/ci-verify.sh fixtures/evidence-packs/valid; proxmox-apply workflow runs on pi-ci
**Target Platform**: pi-ci GitHub Actions runner (ARM64 Debian) deploying to Proxmox VE host `pve`
**Project Type**: Infra automation (CI/CD, scripts, Ansible, Terraform)
**Performance Goals**: Provisioning SSH readiness within configured timeout; 95% success target per spec; zero root SSH usage
**Constraints**: No root SSH; sudo -n only via allowlisted commands; artifacts path immutable at /var/lib/homelab-proxmox/artifacts; avoid deleting runtime artifacts; maintain checks.json validity
**Scale/Scope**: Single Proxmox homelab environment and pi-ci runner; workflows limited to proxmox-apply path

## Constitution Check

| Gate | Status | Notes |
|------|--------|-------|
| Spec-driven changes only | PASS | Working from specs/021-proxmox-ci-hardening/spec.md; plan aligns. |
| Secrets policy | PASS | No secrets to be committed; use existing GitHub Secrets/SSH keys. |
| Separation of concerns | PASS | Terraform only for Proxmox API/token usage; Ansible for config; scripts/workflows orchestrate. |
| Provider strategy | PASS | Staying on telmate/proxmox; no provider swaps planned. |
| Networking boundaries | PASS | No network changes; only CI/orchestration. |
| Access control expectations | PASS | Moving away from root SSH; ci with scoped sudo aligns. |

## Project Structure

### Documentation (this feature)

```text
specs/021-proxmox-ci-hardening/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
└── tasks.md (created in /speckit.tasks)
```

### Source Code (repository root)

```text
.github/workflows/
  proxmox-apply.yml          # CI workflow to update for ci@pve, rsync excludes, sudo smoke checks
scripts/lab/
  pve-lab                    # Orchestrator to refactor for sudo helper, timeouts, evidence
  lib/                       # Shared helpers to adjust for sudo -n and artifact path
  artifacts/ (local only)    # On PVE: /var/lib/homelab-proxmox/artifacts
ansible/                     # Ensure remote_user/become settings align (ci with sudo -n)
terraform/                   # If used, ensure Proxmox API token (non-root) docs/variables
docs/                        # Add documentation for pi-ci hub, ci sudoers policy, runbook
```

**Structure Decision**: Infra automation centered on workflow + scripts; no new app projects introduced. Focused paths: .github/workflows/proxmox-apply.yml, scripts/lab/pve-lab + scripts/lab/lib/*, documentation under docs/.

## Complexity Tracking

No constitution violations requiring justification.
