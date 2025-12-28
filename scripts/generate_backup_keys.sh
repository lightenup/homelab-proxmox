#!/usr/bin/env bash
# Script to generate Age encryption keys for Proxmox Backup
# Usage: ./generate_backup_keys.sh

set -euo pipefail

KEY_FILE="../ansible/secrets/age.key"
VARS_FILE="../ansible/group_vars/proxmox_hosts/vars.yml"

# Ensure age is installed
if ! command -v age-keygen &> /dev/null; then
    echo "Error: age-keygen is not installed."
    echo "Install it with: brew install age (macOS) or apt install age (Linux)"
    exit 1
fi

# Create secrets directory if it doesn't exist
mkdir -p "$(dirname "$KEY_FILE")"

if [[ -f "$KEY_FILE" ]]; then
    echo "Key file already exists at $KEY_FILE"
    echo "To regenerate, delete this file first."
else
    echo "Generating new Age key pair..."
    age-keygen -o "$KEY_FILE"
    chmod 600 "$KEY_FILE"
    echo "Key generated at $KEY_FILE"
fi

# Extract keys
PUBLIC_KEY=$(grep "public key" "$KEY_FILE" | cut -d: -f2 | tr -d ' ')
PRIVATE_KEY=$(grep "AGE-SECRET-KEY" "$KEY_FILE")

echo ""
echo "=== Configuration Instructions ==="
echo "1. Update 'proxmox_backup_age_public_key' in $VARS_FILE:"
echo "   proxmox_backup_age_public_key: \"$PUBLIC_KEY\""
echo ""
echo "2. Encrypt the private key for Ansible Vault:"
echo "   ansible-vault encrypt_string '$PRIVATE_KEY' --name 'proxmox_backup_age_private_key'"
echo ""
echo "3. Paste the encrypted output into $VARS_FILE"
echo ""
echo "=== IMPORTANT ==="
echo "Store these keys in a secure password manager (e.g., Bitwarden)."
echo "If you lose the private key, your backups will be unrecoverable."
