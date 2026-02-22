# Quickstart: Nextcloud Deployment

**Branch**: `034-add-nextcloud` | **Date**: 2026-02-22

## Prerequisites

1. Proxmox VE host running with Terraform-managed infrastructure
2. Synology NAS accessible at `192.168.1.109` with NFS exports configured
3. NFS export created on Synology: `/volume1/homelab_nextcloud` (UID 33 / GID 33 permissions)
4. Proxmox host NFS mount at `/mnt/nas/homelab_nextcloud` (managed by host_proxmox playbook)
5. Terraform `prod.tfvars` updated with Nextcloud IP and mountpoints
6. Ansible vault password available

## Deployment Steps

### 1. Provision the LXC (Terraform)

```bash
cd terraform
terraform plan -var-file=environments/prod.tfvars
terraform apply -var-file=environments/prod.tfvars
```

This creates the `nextcloud-lxc` container with:
- 4 cores, 4 GB RAM, 32 GB disk
- Static IP `192.168.20.216/24`
- NAS bind mount at `/mnt/nextcloud`

### 2. Configure the service (Ansible)

```bash
cd ansible
ansible-playbook playbooks/nextcloud.yml -i inventories/prod/hosts.yml
```

This:
- Bootstraps the LXC (base packages, SSH)
- Installs Docker + Docker Compose
- Deploys the Nextcloud stack (Nextcloud + MariaDB + Redis)
- Configures apps (enable Deck, Office, TOTP; disable Photos, Talk)
- Sets up daily database backup
- Registers mDNS hostname (`nextcloud.local`)

### 3. Configure the reverse proxy

```bash
cd ansible
ansible-playbook playbooks/services.yml -i inventories/prod/hosts.yml --tags reverse_proxy
```

Or run the full services playbook. This adds `nextcloud.local` → `192.168.20.216:8080` routing to Caddy.

### 4. Verify

1. Open `http://nextcloud.local` in a browser
2. Log in with the admin credentials (from Ansible vault)
3. Upload a test file — verify it appears on the NAS at `/mnt/nas/homelab_nextcloud/data/admin/files/`
4. Create a document — verify the Office editor opens
5. Navigate to Deck — create a board

## Post-Deployment

- **Admin URL**: `http://nextcloud.local`
- **Direct IP**: `http://192.168.20.216:8080` (emergency access)
- **Backup timer**: Runs daily at 03:00 UTC
- **Backup location**: `/mnt/nextcloud/backups/` (on NAS)
- **Logs**: `docker logs nextcloud_app` (inside the LXC)

## Troubleshooting

| Problem | Check |
|---------|-------|
| Can't resolve `nextcloud.local` | `systemctl status avahi-daemon` on LXC |
| 502 Bad Gateway | `docker ps` inside LXC — is nextcloud_app running? |
| "Data directory not writable" | Check NFS mount: `mount | grep nextcloud` |
| Brute-force lockout | Whitelist LAN: `php occ config:system:set ...` |
| Slow file operations | Verify Redis is running: `docker logs nextcloud_redis` |
