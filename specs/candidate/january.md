# Manual Tasks To Automate (January 2026)

## Current manual steps
- Maintain a prod tfvars copy on PVE at /var/lib/homelab-proxmox/tfvars/prod.tfvars (create/copy from repo), including the real proxmox_api_token_secret.
- Rotate and paste the Proxmox API token secret manually into prod.tfvars; validate token ID matches terraform@pve!terraform-token.
- Align local/CI Terraform runs with the correct var-file: ensure prod.tfvars exists on PVE before triggering prod apply.
- Work around prerequisite checks expecting a feature branch (currently blocks check-prerequisites on main) when doing hotfixes.

## Why automate
- Reduce 401 auth failures and drift from missing/placeholder secrets on PVE.
- Eliminate manual secret pasting by sourcing TF_VAR_proxmox_api_token_* via CI secrets/KeyVault and templating prod.tfvars from a managed secret store.
- Enforce prerequisite gating regardless of branch name, with an override path for hotfixes.
- Keep PVE tfvars in sync with repo examples to avoid missing files during prod applies.
