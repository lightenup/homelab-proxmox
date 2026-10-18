# Implementation Report: Pipeline Promotion UX (Spec 024)

**Date**: 2026-01-09
**Branch**: `024-pipeline-promotion-ux`

## Summary
Spec 024 is implemented end-to-end: LAB deploy and LAB→PROD promote workflows generate verifiable evidence packs (including LAB snapshot and PROD tfvars proof), enforce bounded inputs and destructive-change confirmations, and gate production via the `prod` GitHub Environment.

A follow-up hardening was added to unblock PROD planning when GitHub secrets are not available: PROD tfvars provisioning now safely reuses an existing `/var/lib/homelab-proxmox/tfvars/prod.tfvars` on PVE instead of failing or overwriting the file with an empty secret.

## What Changed (Delta)
### PROD tfvars provisioning fallback (PVE-side)
- Updated [scripts/lab/lib/tfvars.sh](../../scripts/lab/lib/tfvars.sh) to:
  - Prefer GitHub-provided secret env vars (`PROXMOX_API_TOKEN_SECRET` or legacy `PROXMOX_TOKEN_SECRET`).
  - If no secret env var is provided and an existing `${TFVARS_DIR}/prod.tfvars` exists, treat it as the template and validate the secret value from the file (without printing it).
  - Avoid overwriting `proxmox_api_token_secret` when the secret env var is empty.
  - Keep evidence proof redacted: token id + booleans + hash only.

**Commit**: `3baa437` (pushed to `024-pipeline-promotion-ux`)

## Validation Performed
### 1) Workflow YAML parse + job graph
- `act -l` lists all workflows and `workflow_dispatch` entries.
- Dry-run graphs:
  - `act -n workflow_dispatch -W .github/workflows/lxc-deploy-lab.yml`
  - `act -n workflow_dispatch -W .github/workflows/lxc-promote.yml`

### 2) Offline evidence verification (fixtures)
- `scripts/lab/ci-verify.sh` passes for the fixture packs:
  - Valid packs accepted
  - Invalid packs rejected

### 3) End-to-end plan-only run touching PVE (no apply)
A plan-only dry run was executed against PVE to validate the full path:
- Sync repo to PVE via rsync
- Execute `scripts/lab/pve-service-deploy plan` for LAB and PROD
- Fetch evidence packs via `tar` + `scp`
- Verify evidence packs locally with `scripts/lab/ci-verify.sh`

**Evidence directory (local)**: `tmp/e2e-dryrun-pve-20260109-125807`

**Run IDs**:
- LAB: `lab-<service>-unknown-20260109-125748`
- PROD: `prod-<service>-unknown-20260109-125759`

**Key confirmations from evidence**:
- PROD tfvars proof was **PASS** with `secret_source=existing_file` (the PROD run's `reports/prod-tfvars/provisioning.txt` and `validation.json`).
- Plans were non-destructive (`destructive=false`).
- PROD plan requested a single in-place update for the service's LXC:
  - LXC `nameserver` `192.168.1.1` → `1.1.1.1`

## Notes / Operational Implications
- If GitHub secrets are missing in PROD jobs, PROD plan can still proceed **only if** a valid `prod.tfvars` already exists on PVE in `${TFVARS_DIR}`.
- This fallback does not relax any destructive-change gates or approval gates.
- No secret values are written into evidence packs; only hashes/booleans are recorded.

## Follow-ups
- Optional: add a small “local plan-only dry-run” helper script under `scripts/lab/` to standardize the exact PVE dry-run procedure used above.
- Optional: decide whether `tmp/` should be cleaned manually after local validation (it remains untracked by git).
