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

**Policy**: rebuild from configuration; back up only what cannot be rebuilt; no Proxmox guest
backups. Every service backup is one entry in `service_backups`
(`ansible/group_vars/all/vars.yml`), installed by the `service_backup` role, and refuses to write
unless its destination is an NFS mount.

| Host | Class | Reason |
|------|-------|--------|
| proxmox | Backed up | `/etc` and `/var/lib/pve-cluster`, age-encrypted to the NAS (`proxmox_backup`) |
| immich | Backed up | Postgres database; the photos are on NFS. The archive carries no `.env` |
| nextcloud | Backed up | MariaDB and `config.php`; the data is on NFS |
| financial-scenario | Backed up | `scenarios.db` |
| hermes | Backed up | SQLite, documents, vector index and agent state |
| jellyfin | Backed up | `jellyfin.db` (users, watch history) and `/etc/jellyfin`; metadata and trickplay regenerate |
| reverse_proxy | Rebuilt from configuration | The Caddyfile is templated; certificates reissue over DNS-01 |
| monitoring | Rebuilt from configuration | Prometheus keeps 15 days; dashboards and rules are provisioned |
| llm-router | Rebuilt from configuration | Virtual keys are generated with the vault value and re-applied on every deploy |
| ntfy | Rebuilt from configuration | Declarative (spec 082) |
| market-model | Disposable | A cache |
| eurooffice | Disposable | Documents live in Nextcloud |
| pi-runner | Not a Proxmox guest | Self-hosted runner; rebuilt from its own setup |
| synology | Not a Proxmox guest | The NAS itself |

- **Proxmox Configuration Backup**:
  - Automated daily backup of `/etc` and `/var/lib/pve-cluster`.
  - Encrypted with `age` and stored on NAS.
  - Controlled by `proxmox_backup_email_mode` Ansible variable (`disabled` by default).

- **Monitoring**: `BackupStale` (36 h, and never-succeeded) on
  `backup_last_success_timestamp_seconds`, one series per backup, written by
  `/usr/local/bin/backup-success-metric` after a verified run.

- **Synology NAS**
  - Provides storage (e.g. NFS) for services, especially Immich.
  - Also stores backups (including Terraform state backups).

- **Raspberry Pi**
  - Runs a self-hosted GitHub Actions runner.
  - Applies Terraform and Ansible changes to Proxmox and services.

- **LXCs (one per service)**
  - `immich-lxc` – Immich photo service, data on Synology via NFS.
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
