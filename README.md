# homelab-proxmox

Infrastructure-as-code for my Proxmox-based homelab.

- **Terraform** manages Proxmox resources (VMs, LXCs, networks, disks).
- **Ansible** configures the Proxmox host and services inside LXCs.
- **GitHub Actions** runs on a self-hosted runner (Raspberry Pi) to apply changes.
- Services are split into **one LXC per service** (Immich, AdGuard, Home Assistant, reverse proxy).

See:

- `docs/architecture.md` – overall design.
- `docs/network-layout.md` – planned network segmentation.
- `.github/copilot-instructions.md` – how AI assistants should work with this repo.

## Prerequisites

- **Terraform** >= 1.5.7
- **Ansible** >= 2.10
- **Proxmox VE** 8.x
- A `prod.tfvars` file (see `terraform/terraform.tfvars.example`) with your Proxmox credentials.

### Proxmox User Setup

To allow Terraform to manage resources, create a dedicated API user and token:

1.  **Create User**:
    *   Datacenter → Permissions → Users → Add
    *   User name: `terraform`
    *   Realm: `Proxmox VE authentication server`
2.  **Create API Token**:
    *   Datacenter → Permissions → API Tokens → Add
    *   User: `terraform@pve`
    *   Token ID: `terraform-token`
    *   **Uncheck "Privilege Separation"**: This allows the token to inherit the user's permissions. If you leave it checked, you must assign permissions to the token specifically.
    *   **Save the Secret**: You only see it once.
3.  **Assign Permissions**:
    *   Datacenter → Permissions → Add → ACL
    *   Path: `/`
    *   User: `terraform@pve`
    *   Role: `Administrator` (or `PVEAdmin` if available/sufficient)
    *   Propagate: Checked

Update your local `terraform/prod.tfvars`:

```hcl
proxmox_api_token_id     = "terraform@pve!terraform-token"
proxmox_api_token_secret = "YOUR_SECRET_HERE"
```

## Usage

### 1. Provision Infrastructure (Terraform)

```bash
cd terraform
terraform init
terraform validate
terraform plan -var-file=prod.tfvars
# terraform apply -var-file=prod.tfvars
```

### 2. Configure Services (Ansible)

First, generate the inventory from Terraform state:

```bash
./scripts/update_ansible_inventory.sh
```

Then run the playbooks:

```bash
cd ansible
ansible-playbook playbooks/site.yml
```

### 3. Monthly Maintenance

Run monthly security updates with automatic reboots:

```bash
cd ansible
ansible-playbook playbooks/update_monthly.yml
```

This orchestrates package updates across all services with serial execution to minimize downtime. See [Monthly Patching Runbook](docs/runbooks/monthly-patching.md) for detailed procedures.

**Optional**: Patch Proxmox host with reboot:
```bash
ansible-playbook playbooks/update_monthly.yml -e "allow_host_reboot=true"
```

## Documentation

### Operational Runbooks

- [Monthly Patching](docs/runbooks/monthly-patching.md) - Security updates and reboot orchestration
- [Tailscale Mobile Access](docs/runbooks/tailscale-mobile.md) - Remote access from phone (when available)

### Architecture & Design

- [Architecture Overview](docs/architecture.md) - Overall system design
- [Network Layout](docs/network-layout.md) - Network segmentation and VLAN planning
- [Naming and mDNS](docs/naming-and-mdns.md) - Hostname resolution strategy
- [Reverse Proxy](docs/reverse-proxy.md) - Caddy reverse proxy configuration
- [Operations Guide](docs/operations.md) - Day-to-day operational procedures

### Service-Specific

- [Immich Backup/Restore](docs/immich-backup-restore.md) - Photo backup and recovery procedures
- [Immich Maintenance](docs/immich-maintenance.md) - Routine maintenance tasks
