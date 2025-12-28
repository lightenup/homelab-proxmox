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

**Available playbooks**:

- `site.yml` - Apply all configurations to all hosts (bootstrap + services + host config)
- `bootstrap.yml` - Initial setup of LXC containers (run after Terraform provision)
- `services.yml` - Configure LXC services (Immich, AdGuard, Home Assistant, reverse proxy)
- `host_proxmox.yml` - Configure Proxmox host-specific settings
- `backup_proxmox.yml` - Deploy Proxmox configuration backup system
- `tailscale.yml` - Configure Tailscale subnet router for remote access
- `verify_tailscale.yml` - Verify Tailscale configuration (diagnostics)
- `update_monthly.yml` - Monthly security updates with orchestrated reboots

---

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

### Disaster Recovery

Disaster recovery procedures for Immich photo backups and Proxmox configuration backups.

- **Immich DR**: [docs/runbooks/disaster-recovery-drill.md](docs/runbooks/disaster-recovery-drill.md)
- **Proxmox Backup**: [docs/operations/backups-proxmox-config.md](docs/operations/backups-proxmox-config.md)
- **Proxmox Restore**: [docs/operations/backups-proxmox-config-restore.md](docs/operations/backups-proxmox-config-restore.md)
- **Last Drill**: See `scripts/dr/drill-reports/` for execution history

#### Proxmox Configuration Backup (Feature 013)

**Automated daily backups** of Proxmox VE configuration to NAS:
- **Schedule**: Daily at 2:00 AM via systemd timer
- **Location**: `192.168.1.109:/volume1/homelab_backups/proxmox/`
- **Retention**: 30 daily + 12 monthly backups
- **Contents**: LXC configs, storage config, network config, fstab, IaC artifacts (optional)
- **Encryption**: Age (age-encryption.org) with public key cryptography
- **Verification**: Automated post-backup checksum validation
- **Notifications**: Email alerts on backup failures (Gmail SMTP relay)

**Quick Recovery**:
1. Mount NAS: `mount -t nfs 192.168.1.109:/volume1/homelab_backups/proxmox /mnt/nas-backup`
2. Decrypt latest: `age --decrypt -i /root/.age/proxmox-backup.key backup.tar.zst.age > backup.tar.zst`
3. Extract: `tar --use-compress-program=zstd -xvf backup.tar.zst`
4. Follow [restore runbook](docs/operations/backups-proxmox-config-restore.md)

**Manual Backup**: `ssh root@192.168.1.112 /usr/local/sbin/proxmox-config-backup`

### Operational Runbooks

- [Monthly Patching](docs/runbooks/monthly-patching.md) - Security updates and reboot orchestration
- [Tailscale Subnet Router Setup](docs/runbooks/tailscale-setup.md) - Remote access configuration and troubleshooting

### Architecture & Design

- [Architecture Overview](docs/architecture.md) - Overall system design
- [Network Layout](docs/network-layout.md) - Network segmentation and VLAN planning
- [Naming and mDNS](docs/naming-and-mdns.md) - Hostname resolution strategy
- [Reverse Proxy](docs/reverse-proxy.md) - Caddy reverse proxy configuration
- [Operations Guide](docs/operations.md) - Day-to-day operational procedures

### Service-Specific

- [Immich Backup/Restore](docs/immich-backup-restore.md) - Photo backup and recovery procedures
- [Immich Maintenance](docs/immich-maintenance.md) - Routine maintenance tasks
