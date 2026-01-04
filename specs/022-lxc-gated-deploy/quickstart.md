# Quickstart: Gated LXC Deploy (Least Privilege)

This quickstart describes how the planned CI/CD workflow will be exercised once implemented.

## Prerequisites

- GitHub Actions runner (self-hosted) can SSH to `ci@pve`.
- `ANSIBLE_VAULT_PASSWORD` is available in GitHub Secrets (or `act --secret-file` locally).
- Proxmox API credentials for Terraform are provided via CI secrets/environment (never committed).

## Plan / Preflight

- Trigger the workflow with `environment=lab` and `service=jellyfin`.
- Expected outcome:
  - No changes are made.
  - A plan artifact is produced indicating `create` / `update` / `no-op`.

## Apply to LAB

- Trigger apply for LAB.
- Expected outcome:
  - Terraform creates the LXC if missing.
  - Ansible configures Jellyfin.
  - Evidence bundle is written under `/var/lib/homelab-proxmox/artifacts/<runs-dir>/<run_id>` on PVE.
  - Offline verification passes.

## Apply to PROD (Gated)

- Trigger apply for PROD.
- Must be blocked unless:
  - The PROD GitHub Environment approval is granted.
  - The explicit `confirm` input matches the expected confirmation string.

## Offline Evidence Verification

- The workflow downloads the evidence bundle and runs the existing offline verification script against it.

## Notes

- This feature is planning-only until `tasks.md` exists and is approved.
