# Implementation Report: Gated LXC Deploy (Least Privilege) (022)

**Date**: 2026-01-04

## Goal

Deliver a gated, least-privilege CI/CD pipeline for provisioning and configuring a *single service* LXC on Proxmox (baseline: Jellyfin) with:

- Safe **plan/preflight** (no changes) with a strict scope guard.
- **LAB apply** (automatic) with evidence + idempotency verification.
- **PROD apply** (manual approval + explicit confirmation) with evidence.
- Durable evidence packs stored on PVE and verified offline.
- No committed secrets (vault data lives on PVE; password provided via CI secret).

## What Changed

### Gated workflow

- Added the gated deploy workflow at `.github/workflows/lxc-deploy.yml`.
- Plan/preflight runs first and produces an offline-verifiable evidence pack.
- LAB apply runs only on `workflow_dispatch` with `environment=lab` and performs a second apply to assert idempotency.
- PROD apply runs only on `workflow_dispatch` with `environment=prod` and `confirm=deploy-prod`, and is additionally gated by the GitHub Environment `prod`.

### PVE-side orchestrator

- Added `scripts/lab/pve-service-deploy` to run plan/apply on PVE as `ci@pve` (no root SSH).
- Implements:
  - deterministic run IDs and evidence directories under `/var/lib/homelab-proxmox/artifacts/service-deploy-runs/<run_id>`
  - Terraform scope guard (fails if plan touches resources outside the target service allowlist)
  - Ansible execution using `ANSIBLE_VAULT_PASSWORD_FILE` and optional vault-id identity
  - healthcheck capture and offline verification (`scripts/lab/ci-verify.sh`)

### Baseline service (Jellyfin)

- Added a baseline Terraform service module instantiation and outputs for Jellyfin.
- Added Ansible playbook/role for Jellyfin and a service healthcheck script.

### Secrets and vault governance

- Removed the committed service secrets file (`ansible/group_vars/services/secrets.yml`).
- Vault-encrypted YAML is sourced from PVE (preferred layout described in `docs/operations/lxc-deploy-ci.md`).
- Vault password is supplied as `ANSIBLE_VAULT_PASSWORD` (GitHub Secret) and streamed to PVE into a temp file.

### Documentation

- Added/updated operator docs: `docs/operations/lxc-deploy-ci.md`.
- Linked the new workflow from `docs/operations/proxmox-ci.md`.
- Updated spec quickstart to match validated `act` commands.

## Validation Performed

- Local posture/fixtures:
  - `./scripts/lab/ci-validate-iac.sh`
  - `./scripts/lab/ci-verify.sh fixtures/evidence-packs/valid`
- End-to-end via `act` (LAB):
  - `.github/workflows/lxc-deploy.yml` job `apply_lab` completed successfully, including offline evidence verification.

## Operational Cleanup (PVE)

- Removed test/implementation Jellyfin LXCs that were left running during development.
  - Containers destroyed: 101, 105–114 (all named `jellyfin`).

## How To Run (Post-merge)

- **LAB**: Trigger workflow `LXC Deploy (Gated)` via `workflow_dispatch` with `environment=lab` and `service=jellyfin`.
- **PROD**: Trigger via `workflow_dispatch` with `environment=prod`, `service=jellyfin`, and `confirm=deploy-prod`, then approve the `prod` environment.

## Pointers

- Workflow: `.github/workflows/lxc-deploy.yml`
- Orchestrator: `scripts/lab/pve-service-deploy`
- Runbook: `docs/operations/lxc-deploy-ci.md`
- Spec: `specs/022-lxc-gated-deploy/spec.md`
