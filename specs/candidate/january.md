# Manual Tasks To Automate (January 2026)

## Current manual steps
- Maintain a prod tfvars copy on PVE at /var/lib/homelab-proxmox/tfvars/prod.tfvars (create/copy from repo), including the real proxmox_api_token_secret.
- Rotate and paste the Proxmox API token secret manually into prod.tfvars; validate token ID matches terraform@pve!terraform-token.
- Align local/CI Terraform runs with the correct var-file: ensure prod.tfvars exists on PVE before triggering prod apply.
- Work around prerequisite checks expecting a feature branch (currently blocks check-prerequisites on main) when doing hotfixes.

- Limited visibility into “what’s currently in LAB” (running LXCs, IPs, health, mount status). Today this requires ad-hoc `pct list`, `pct config <id>`, and SSHing into guests.

## Recent automation wins (to build on)

- Task-first operator workflows via `Taskfile.yml` (single entrypoint)
- Inventory generation, tfstate backup, and healthcheck runner migrated into Python with unit + smoke tests
- Service lifecycle now runs via tasks (`service:add|change|remove`) instead of ad-hoc shell scripts
- Ongoing approach: keep path-stable shims only when required; otherwise deprecate scripts and remove all references

## Why automate
- Reduce 401 auth failures and drift from missing/placeholder secrets on PVE.
- Eliminate manual secret pasting by sourcing TF_VAR_proxmox_api_token_* via CI secrets/KeyVault and templating prod.tfvars from a managed secret store.
- Enforce prerequisite gating regardless of branch name, with an override path for hotfixes.
- Keep PVE tfvars in sync with repo examples to avoid missing files during prod applies.

- Add a lightweight LAB “inventory snapshot” artifact to each apply/plan run (and optionally on-demand):
	- list of containers (vmid, hostname, status, IPv4)
	- per-service evidence pointers (latest run id / evidence dir)
	- workload checks summary (e.g., `/media/video` mounted RO for Jellyfin)
	- quick links/paths to state (`/var/lib/homelab-proxmox/state/services/<service>/terraform.tfstate`) and evidence packs
