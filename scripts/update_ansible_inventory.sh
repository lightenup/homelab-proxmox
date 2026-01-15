#!/bin/bash
set -euo pipefail

# Path-stable shim for inventory generation.
#
# Removal condition: remove once all callers use `task inventory:update` (or call the Python module)
# and no protected-path tooling depends on this path.
#
# Supported inputs remain env-var based for compatibility with existing callers:
# - ANSIBLE_INVENTORY_JSON / ANSIBLE_INVENTORY_JSON_PATH
# - ANSIBLE_SSH_PRIVATE_KEY_FILE

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "${repo_root}"

PYTHONPATH="${repo_root}/python/src${PYTHONPATH:+:${PYTHONPATH}}" \
  python3 -m homelab_proxmox_orchestrator.inventory
