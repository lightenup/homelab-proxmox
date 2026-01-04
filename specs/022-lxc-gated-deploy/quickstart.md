# Quickstart: Gated LXC Deploy (Least Privilege)

This quickstart describes the validated local (`act`) flow for exercising the gated CI/CD workflow.

## Prerequisites

- GitHub Actions runner (self-hosted) can SSH to `ci@pve`.
- `ANSIBLE_VAULT_PASSWORD` is available in GitHub Secrets (or `act --secret-file` locally).
- Proxmox API credentials for Terraform are provided via CI secrets/environment (never committed).

See `docs/operations/lxc-deploy-ci.md` for the required secret names and the PVE-side vault layout.

## Local validation with `act`

Create a workflow_dispatch payload (LAB example):

```bash
cat > /tmp/act-lxc-event-lab.json <<'JSON'
{
  "inputs": {
    "environment": "lab",
    "service": "jellyfin",
    "confirm": ""
  }
}
JSON
```

Run the plan job:

```bash
act \
  -W .github/workflows/lxc-deploy.yml \
  -e /tmp/act-lxc-event-lab.json \
  -j plan \
  --secret-file .act.secrets
```

Run the LAB apply job:

```bash
act \
  -W .github/workflows/lxc-deploy.yml \
  -e /tmp/act-lxc-event-lab.json \
  -j apply_lab \
  --secret-file .act.secrets
```

Notes:

- Under `act`, `actions/upload-artifact` is intentionally skipped (the workflow gates this via `if: env.ACT != 'true'`). Evidence verification still runs locally.
- Use `-v` (and optionally `tee`) if you want a full debug log: `act ... -v | tee /tmp/act-lxc-apply-lab.log`.

## Plan / Preflight

- Trigger the workflow with `environment=lab` and `service=jellyfin` (baseline example).
- Expected outcome:
  - No changes are made.
  - A plan artifact is produced indicating `create` / `update` / `no-op`.

## Apply to LAB

- Trigger apply for LAB.
- Expected outcome:
  - Terraform creates the LXC if missing.
  - Ansible configures the target service (baseline example: Jellyfin).
  - Evidence bundle is written under `/var/lib/homelab-proxmox/artifacts/service-deploy-runs/<run_id>` on PVE.
  - Offline verification passes.

## Apply to PROD (Gated)

- Trigger apply for PROD.
- Must be blocked unless:
  - The PROD GitHub Environment approval is granted.
  - The explicit `confirm` input matches `deploy-prod`.

## Offline Evidence Verification

- The workflow downloads the evidence bundle and runs the existing offline verification script against it.

## Notes

- For operator-facing setup (vault files on PVE, vault id usage, secrets), use `docs/operations/lxc-deploy-ci.md`.
