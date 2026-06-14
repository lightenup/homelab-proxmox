# homelab-proxmox Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-05-25

## Active Technologies
- YAML (Ansible 2.x), Jinja2 templates, Caddyfile syntax, static HTML/CSS + vanilla JS (no framework) + Caddy (custom xcaddy build w/ Domeneshop DNS, already deployed); Prometheus v3.8.1 + blackbox_exporter v0.28.0 (already deployed, feature `042`); `community.general` / builtin Ansible modules only (045-landing-page)
- N/A — landing assets are generated files under `/var/www/hus-sky` on the reverse-proxy LXC; no database (045-landing-page)

- HCL (Terraform), YAML (Ansible), JSON (Grafana dashboard), Caddyfile (reverse proxy) + `telmate/proxmox` Terraform provider, `lxc_service` Terraform module, `geerlingguy.docker` Ansible role, `community.docker.docker_compose_v2` Ansible module (044-transcriber-proxmox-deploy)

## Project Structure

```text
src/
tests/
```

## Commands

# Add commands for HCL (Terraform), YAML (Ansible), JSON (Grafana dashboard), Caddyfile (reverse proxy)

## Code Style

HCL (Terraform), YAML (Ansible), JSON (Grafana dashboard), Caddyfile (reverse proxy): Follow standard conventions

## Recent Changes
- 045-landing-page: Added YAML (Ansible 2.x), Jinja2 templates, Caddyfile syntax, static HTML/CSS + vanilla JS (no framework) + Caddy (custom xcaddy build w/ Domeneshop DNS, already deployed); Prometheus v3.8.1 + blackbox_exporter v0.28.0 (already deployed, feature `042`); `community.general` / builtin Ansible modules only

- 044-transcriber-proxmox-deploy: Added HCL (Terraform), YAML (Ansible), JSON (Grafana dashboard), Caddyfile (reverse proxy) + `telmate/proxmox` Terraform provider, `lxc_service` Terraform module, `geerlingguy.docker` Ansible role, `community.docker.docker_compose_v2` Ansible module

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
