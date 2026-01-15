#!/usr/bin/env bash
set -euo pipefail

# Path-stable shim for tfstate backups.
#
# Removal condition: remove once all callers use `python -m homelab_proxmox_orchestrator.terraform_backup`
# (or a Taskfile entrypoint) and no protected-path tooling depends on this path.
#
# Usage remains compatible:
#   backup_tfstate.sh [--state-path <path>] [--backup-dir <dir>] [--prefix <name>]

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repo_root}"

PYTHONPATH="${repo_root}/python/src${PYTHONPATH:+:${PYTHONPATH}}" \
  python3 -m homelab_proxmox_orchestrator.terraform_backup "$@"
