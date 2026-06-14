# Implementation Plan: 046-financial-scenario-deploy

## Tech Stack
- HCL (Terraform) — `telmate/proxmox` provider, `lxc_service` module
- YAML (Ansible) — `community.docker` collection, `geerlingguy.docker` role
- Jinja2 — docker-compose.yml.j2 template

## Architecture
- New LXC `financial-scenario` at `192.168.1.217` (prod) / `192.168.20.218` (lab)
- 2 cores / 2048 MB / 16 GB — same sizing as adguard/homeassistant
- Three containers from two private GHCR images: `api`, `mcp` (same image, different command), `gui`
- Tailscale/LAN-only — no Caddy route, no landing-page card, no public DNS
- Vault-backed GHCR pull credential (first private registry pull in this repo)
- MCP bearer token from vault
- Reference-data bind-mount at `/opt/financial-scenario-data/reference_data`
- Blackbox HTTP liveness probe (new `http_2xx` module) + down-alert

## Ports
- `financial_scenario_gui_port: 3000` — nginx serving React, proxies /api → api:8000, /mcp → mcp:8001
- `financial_scenario_api_port: 8000` — FastAPI
- `financial_scenario_mcp_port: 8001` — FastMCP server

## File Structure

```text
terraform/
  main.tf                                          (add module "financial_scenario_lxc")
  environments/
    lab.tfvars                                     (add financial-scenario IP 192.168.20.218)
    lab.tfvars.template                            (add financial-scenario IP 192.168.1.217)
    prod.tfvars.template                           (add financial-scenario IP 192.168.1.217)
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
    vault.yml                                      (add ghcr_pull_* and financial_scenario_mcp_token — MANUAL: encrypted)
  host_vars/
    financial-scenario.yml                         (new)
  inventories/prod/
    hosts.yml                                      (add financial-scenario host)
.github/workflows/
  lxc-deploy-lab.yml                              (add financial-scenario to service choices)
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
financial_scenario_mcp_token: "<bearer-token>"
```
