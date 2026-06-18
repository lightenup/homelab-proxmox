# Implementation Plan: 046-financial-scenario-deploy

## Tech Stack
- HCL (Terraform) — `telmate/proxmox` provider, `lxc_service` module
- YAML (Ansible) — `community.docker` collection, `geerlingguy.docker` role
- Jinja2 — docker-compose.yml.j2 template

## Architecture
- New LXC `financial-scenario`. Prod is on `192.168.1.0/24` → `192.168.1.217` (committed
  templates + prod inventory). Lab is a separate subnet `192.168.20.0/24`, so the operator's
  (gitignored, local) `lab.tfvars` uses `192.168.20.218`.
- 2 cores / 2048 MB / 16 GB — same sizing as adguard/homeassistant
- Three containers from two private GHCR images: `api`, `mcp` (same image, different command), `gui`
- Tailscale/LAN-only — no Caddy route, no landing-page card, no public DNS
- Vault-backed GHCR pull credential (first private registry pull in this repo)
- MCP auth: gate is enforced in the GUI image's nginx `/mcp` route with an **image-baked** secret
  (PFS 044). It is NOT vault-injectable with the shipped images, and `mcp:8001` is never published
  directly. See backlog spec FR-009 and the upstream PFS follow-up.
- Reference-data bind-mount `/opt/financial-scenario-data/reference_data` → `/app/config/reference_data`,
  **seeded from the image on first deploy** (the empty host dir would otherwise mask the baked-in
  defaults), preserved across re-pulls.
- Blackbox HTTP liveness probe (new `http_2xx` module) + down-alert

## Ports
- Only the **GUI** port is published; the GUI nginx fronts the stack (`/api`, `/docs`, `/mcp`).
- `financial_scenario_gui_port: 3000` (host) → nginx on container port `80`.
- `api:8000` and `mcp:8001` are internal container ports (not published). The mcp container runs with
  `MCP_TRANSPORT=http` (it defaults to stdio and would otherwise never bind a port).

## File Structure

```text
terraform/
  main.tf                                          (add module "financial_scenario_lxc")
  environments/
    lab.tfvars.template                            (add financial-scenario IP 192.168.1.217)
    prod.tfvars.template                           (add financial-scenario IP 192.168.1.217)
    # NOTE: live lab.tfvars/prod.tfvars are gitignored (operator-local). The lab
    # operator sets 192.168.20.218 (lab subnet); only the templates are committed.
ansible/
  playbooks/
    financial_scenario.yml                         (new)
  roles/
    financial_scenario/
      defaults/main.yml                            (new)
      tasks/main.yml                               (new)
      tasks/preflight.yml                          (new)
      templates/docker-compose.yml.j2             (new)
      handlers/main.yml                            (new)
  group_vars/services/
    vars.yml                                       (add financial_scenario_* vars)
    vault.yml                                      (add ghcr_pull_* — MANUAL: encrypted)
  host_vars/
    financial-scenario.yml                         (new)
  inventories/prod/
    hosts.yml                                      (add financial-scenario host)
.github/workflows/
  lxc-deploy-lab.yml                              (add financial-scenario to service choices)
  lxc-promote-lab.yml                            (add financial-scenario to service choices)
  lxc-promote-prod.yml                           (add financial-scenario to service choices)
scripts/lab/
  service-scope-allowlist.json                    (add financial-scenario entry)
monitoring_stack role:
  templates/blackbox.yml.j2                       (add http_2xx module)
  templates/prometheus.yml.j2                     (add blackbox-http job using liveness_targets)
```

## Vault Variables Required (manual — encrypted)
Add to `ansible/group_vars/services/vault.yml`:
```yaml
ghcr_pull_username: "<github-username>"
ghcr_pull_token: "<read:packages PAT>"
```
There is **no** MCP token to add: the MCP `/mcp` gate's secret is baked into the GUI image
(`mcp-local-secret`), not injected from vault. Making it configurable needs an upstream PFS change.
