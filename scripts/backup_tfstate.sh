#!/usr/bin/env bash
set -euo pipefail

# Adjust mount path /share as needed
BACKUP_DIR="/mnt/synology/terraform-backups"

cd "$(dirname "$0")/.."

mkdir -p "${BACKUP_DIR}"
ts=$(date +"%Y%m%d-%H%M%S")
cp terraform/terraform.tfstate "${BACKUP_DIR}/terraform.tfstate.${ts}"
