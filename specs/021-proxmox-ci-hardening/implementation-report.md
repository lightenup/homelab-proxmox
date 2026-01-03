# Implementation Report: Proxmox CI hardening (021)

**Date**: 2026-01-03

## Goal

Make the GitHub Actions workflow **Proxmox Apply + Verify** run green in a least-privilege manner (ci-only), produce durable evidence, and be runnable locally via `act` against the lab host `pve`.

## What Changed

### CI workflow now runs as `ci@pve`

- The workflow uses `ci@pve` for all `ssh`/`rsync` operations.
- Runtime artifacts on PVE are rooted at `/var/lib/homelab-proxmox/artifacts` and are **excluded** from repo sync.
- Evidence packs are fetched from `/var/lib/homelab-proxmox/artifacts/lab-runs/<RUN_ID>` and verified offline.

### Evidence paths renamed to semantic namespace

- Replaced spec-number-derived artifact subdirectory naming (e.g. `019-lab`) with the semantic namespace **`lab-runs`**.
- Centralized artifact path construction in helpers so the workflow and scripts stay consistent.

### Safety identity tag renamed

- Proxmox-managed VM template ownership marker changed from `ManagedBy=019a` to `ManagedBy=homelab-proxmox` (default; remains overridable where supported).

### Local `act` support hardened (without committing secrets)

- Added gitignored local secrets convention via `.act.secrets` (and a committed `.act.secrets.example`).
- Documented local `act` run invocation with `--secret-file` so `ANSIBLE_VAULT_PASSWORD` is available during Ansible runs.

### Verification fixtures no longer mutate the repo

- Updated `scripts/lab/ci-verify.sh` to verify each fixture using a temporary copy, preventing accidental writes into `scripts/lab/fixtures/**` (e.g., generated `reports/verify.json`).

### Documentation updates

- Updated the Proxmox CI runbook to reflect `lab-runs` and local `act` usage.
- Updated the 021 quickstart instructions to reflect `lab-runs` and correct RUN_ID capture.

### Cleanups

- Removed low-signal/spec-trace “meta” comments from scripts where they did not add operational value.
- Deleted the deprecated spec folder `specs/001-proxmox-ci-hardening/`.

## How to Run

### On pi-ci (GitHub Actions)

- Trigger **Proxmox Apply + Verify**.
- Required secrets/credentials:
  - SSH access for `ci@pve`
  - `ANSIBLE_VAULT_PASSWORD` configured as a GitHub Secret

### Locally with `act` (macOS)

1. Create a local secrets file (do not commit it):

```bash
cp .act.secrets.example .act.secrets
${EDITOR:-nano} .act.secrets
```

2. Run:

```bash
act workflow_dispatch -W .github/workflows/proxmox-apply.yml -j apply \
  --secret-file .act.secrets \
  --container-options "-v $(pwd)/.act-ssh:/root/.ssh:ro"
```

## Validation Performed

- Local gates:
  - `./scripts/lab/ci-validate-iac.sh` (posture checks)
  - `./scripts/lab/ci-verify.sh fixtures/evidence-packs/valid` (offline evidence verification)
- End-to-end local workflow:
  - `act` run of `.github/workflows/proxmox-apply.yml` job `apply` completed successfully.

## Operational Notes / Risks

- `ANSIBLE_VAULT_PASSWORD` is required for playbooks that reference Vault-encrypted variables. For local runs, it must be supplied via `act --secret-file`.
- The artifact root on PVE must remain excluded from rsync; workflows/scripts should never delete or overwrite `/var/lib/homelab-proxmox/artifacts`.

## Pointers

- Workflow: `.github/workflows/proxmox-apply.yml`
- Orchestrator: `scripts/lab/pve-lab`
- Artifact helpers: `scripts/lab/lib/artifacts.sh`
- Runbook: `docs/operations/proxmox-ci.md`
