# Ansible Contract: Tier 2 Playbook

**Playbook**: `ansible/playbooks/lab_tier2_pve.yml`

## Inventory Variables
These variables must be defined in `ansible/inventories/lab/group_vars/all.yml` or passed via extra-vars.

| Variable | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `lab_inventory` | Boolean | `true` | Guard to ensure we are running against lab inventory. |
| `pve_repository_url` | String | `http://download.proxmox.com/debian/pve` | Base URL for Proxmox repo. |
| `pve_dist` | String | `trixie` | Distribution codename. |
| `pve_keyring_url` | String | `https://enterprise.proxmox.com/debian/proxmox-release-trixie.gpg` | URL to fetch the signing key. |

## Host Requirements
*   **OS**: Debian 13 (Trixie)
*   **Hostname**: Must match `lab-pve-*`
*   **Resources**: >= 4GB RAM, >= 2 vCPU
