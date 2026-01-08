#!/usr/bin/env bash
set -euo pipefail

usage() {
	cat <<'EOF'
Usage:
  backup_tfstate.sh [--state-path <path>] [--backup-dir <dir>] [--prefix <name>]

Defaults:
  --state-path: terraform/terraform.tfstate (repo-local)
  --backup-dir: /mnt/synology/terraform-backups
  --prefix: terraform

Output:
  Prints the backup file path (and sha256 if available) to stdout.
EOF
}

# Adjust mount path /share as needed
BACKUP_DIR="/mnt/synology/terraform-backups"
PREFIX="terraform"

cd "$(dirname "$0")/.."

STATE_PATH="${PWD}/terraform/terraform.tfstate"

while [[ $# -gt 0 ]]; do
	case "$1" in
		--state-path)
			STATE_PATH="${2:-}"
			shift 2
			;;
		--backup-dir)
			BACKUP_DIR="${2:-}"
			shift 2
			;;
		--prefix)
			PREFIX="${2:-}"
			shift 2
			;;
		-h|--help)
			usage
			exit 0
			;;
		*)
			echo "ERROR: Unknown argument: $1" >&2
			usage >&2
			exit 2
			;;
	esac
done

if [[ -z "${STATE_PATH}" ]]; then
	echo "ERROR: --state-path is required" >&2
	exit 2
fi
if [[ ! -f "${STATE_PATH}" ]]; then
	echo "ERROR: State file does not exist: ${STATE_PATH}" >&2
	exit 1
fi

mkdir -p "${BACKUP_DIR}"

ts="$(date -u +"%Y%m%d-%H%M%S")"
dest="${BACKUP_DIR}/${PREFIX}.terraform.tfstate.${ts}"

cp "${STATE_PATH}" "${dest}"

echo "backup_file=${dest}"
if command -v shasum >/dev/null 2>&1; then
	sha="$(shasum -a 256 "${dest}" | awk '{print $1}')"
	echo "backup_sha256=${sha}"
fi
