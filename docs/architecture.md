# Homelab Architecture

## Overview

This homelab runs on a single physical node with **Proxmox VE** as the hypervisor.

Goals:

- Manage everything as code with **Terraform + Ansible**.
- Be able to rebuild from:
  - This git repo,
  - A Raspberry Pi (CI runner),
  - The target Proxmox machine.
- Keep the Proxmox host as a "small pet", everything else as close to "cattle" as feasible.

## Components

- **Proxmox VE host**
  - Installed manually from ISO.
  - Runs a VLAN-aware Linux bridge for multiple logical networks.

## Backup & Monitoring

- **Proxmox Configuration Backup**:
  - Automated daily backup of `/etc` and `/var/lib/pve-cluster`.
  - Encrypted with `age` and stored on NAS.
  - Monitoring: Prometheus/Alertmanager `ServiceDown` alert on the `node-exporter` scrape target.
  - Controlled by `proxmox_backup_email_mode` Ansible variable (`disabled` by default).

- **Synology NAS**
  - Provides storage (e.g. NFS) for services, especially Immich.
  - Also stores backups (including Terraform state backups).

- **Raspberry Pi**
  - Runs a self-hosted GitHub Actions runner.
  - Applies Terraform and Ansible changes to Proxmox and services.

- **LXCs (one per service)**
  - `immich-lxc` – Immich photo service, data on Synology via NFS.
  - `adguard-lxc` – AdGuard DNS.
  - `homeassistant-lxc` – Home Assistant.
  - `reverse-proxy-lxc` – Caddy/Traefik or similar.
  - `hermes-lxc` – Open WebUI + SearXNG, a self-hosted AI workspace on local models only,
    reached through the `llm-router-lxc` gateway. State (SQLite, documents, vector index) on
    local disk, backed up to Synology (spec 065).

## Tooling

- **Terraform**
  - Uses `telmate/proxmox` provider (supporting `proxmox_lxc` resources).
  - Declares LXCs, network attachments, disks, etc.
  - Exposes outputs for Ansible inventory.

- **Ansible**
  - Configures the Proxmox host: apt, unattended-upgrades, basic hardening.
  - Configures each LXC: base OS tweaks, service install & config.

- **GitHub Actions**
  - `ci` workflow:
    - `terraform fmt`, `validate`, `plan`
    - `ansible-lint`
  - `deploy` workflow:
    - `terraform apply`
    - Regenerate Ansible inventory
    - Run Ansible playbooks

## Hardware acceleration

- CPU: Intel Core i3-12100 with UHD 730 iGPU.
- Immich role should be configured to use Intel Quick Sync (VAAPI) for media transcoding via /dev/dri.
