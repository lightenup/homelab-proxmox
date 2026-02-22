#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

export REPO_ROOT
export ANSIBLE_CONFIG="${REPO_ROOT}/ansible/ansible.cfg"

LIB_DIR="${REPO_ROOT}/scripts/lab/lib"
CHECKS_DIR="${REPO_ROOT}/scripts/lab/checks.d"

# shellcheck source=../lab/lib/artifacts.sh
source "${LIB_DIR}/artifacts.sh"
# shellcheck source=../lab/lib/evidence.sh
source "${LIB_DIR}/evidence.sh"
# shellcheck source=../lab/lib/checks.sh
source "${LIB_DIR}/checks.sh"
# shellcheck source=../lab/lib/rebuild_state.sh
source "${LIB_DIR}/rebuild_state.sh"
# shellcheck source=../lab/lib/rebuild.sh
source "${LIB_DIR}/rebuild.sh"
# shellcheck source=../lab/checks.d/deps.sh
source "${CHECKS_DIR}/deps.sh"
# shellcheck source=../lab/checks.d/rebuild-mounts.sh
source "${CHECKS_DIR}/rebuild-mounts.sh"

log_info() { echo "[INFO] $1"; }
log_warn() { echo "[WARN] $1"; }
log_error() { echo "[ERROR] $1" >&2; }

export PROXMOX_HOST="${PROXMOX_HOST:-pve}"
export SSH_USER="${SSH_USER:-ci}"
export SSH_OPTS="${SSH_OPTS:--o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=no -o CheckHostIP=no -o UserKnownHostsFile=/dev/null -o GlobalKnownHostsFile=/dev/null}"
export SSH_TARGET="${SSH_TARGET:-${PROXMOX_HOST}}"

export REBUILD_CONFIG_PATH="${REBUILD_CONFIG_PATH:-${REPO_ROOT}/scripts/lab/rebuild-config.json}"
export REBUILD_FORCE_LOCAL_ARTIFACTS="${REBUILD_FORCE_LOCAL_ARTIFACTS:-true}"

cmd_idempotent_rebuild "$@"
