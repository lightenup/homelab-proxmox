#!/bin/bash
set -euo pipefail

# Path-stable shim for running the healthcheck suite.
#
# Removal condition: only if all callers migrate off this path (notably Ansible role/playbook callers)
# and a path-stable replacement exists for remote execution on target hosts.

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${repo_root}"

PYTHONPATH="${repo_root}/python/src${PYTHONPATH:+:${PYTHONPATH}}" \
  python3 -m homelab_proxmox_orchestrator.healthcheck_runner "$@"
