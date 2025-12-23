#!/usr/bin/env bash
# scripts/backup/run_proxmox_backup.sh
# Manual wrapper for Proxmox backup deployment
# Feature: 013-proxmox-config-backup

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

echo "==> Deploying Proxmox backup system..."
echo ""
echo "Prerequisites:"
echo "  1. NAS share created: /volume1/homelab_backups/proxmox"
echo "  2. NFS export configured for 192.168.1.112"
echo "  3. Age keys generated and stored in Bitwarden"
echo "  4. PROXMOX_BACKUP_AGE_PUBLIC_KEY environment variable set"
echo ""

# Verify age public key environment variable
if [[ -z "${PROXMOX_BACKUP_AGE_PUBLIC_KEY:-}" ]]; then
  echo "ERROR: PROXMOX_BACKUP_AGE_PUBLIC_KEY not set"
  echo ""
  echo "Set environment variable:"
  echo "  export PROXMOX_BACKUP_AGE_PUBLIC_KEY='age1xxx...'"
  echo ""
  echo "Retrieve from Bitwarden: Proxmox Backup Encryption Key → Public Key"
  exit 1
fi

# Run Ansible playbook with inventory
echo "==> Running Ansible playbook..."
ANSIBLE_ROLES_PATH="${REPO_ROOT}/ansible/roles" ansible-playbook -i ansible/inventories/static/hosts.yml ansible/playbooks/backup_proxmox.yml "$@"

echo ""
echo "==> Deployment complete!"
echo ""
echo "Next steps:"
echo "  1. SSH to Proxmox: ssh root@192.168.1.112"
echo "  2. Deploy private key (replace \$KEY with actual key from Bitwarden):"
echo "       mkdir -p /root/.age"
echo "       echo 'AGE-SECRET-KEY-1xxx...' > /root/.age/proxmox-backup.key"
echo "       chmod 600 /root/.age/proxmox-backup.key"
echo "  3. Test manual backup: /usr/local/sbin/proxmox-config-backup"
echo "  4. Check logs: journalctl -u proxmox-backup.service -f"
echo "  5. Verify timer: systemctl status proxmox-backup.timer"
echo ""
