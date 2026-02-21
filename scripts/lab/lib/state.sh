#!/usr/bin/env bash
# scripts/lab/lib/state.sh
# State path resolution for NAS-backed storage
# Task: D-004 from specs/033-idempotent-rebuild/plan-delta-state-storage.md

# Resolve state root based on platform and environment
resolve_state_root() {
  local env="${ENVIRONMENT:?ENVIRONMENT must be set}"

  # Validate environment
  case "$env" in
    lab|prod) ;;
    *)
      echo "ERROR: Unknown environment '$env'. Must be 'lab' or 'prod'." >&2
      return 1
      ;;
  esac

  # Platform-specific NAS mount points
  local nas_base
  if [[ "$(uname)" == "Darwin" ]]; then
    nas_base="/Volumes/nas/homelab_ci"
  else
    nas_base="/mnt/nas/homelab_ci"
  fi

  # Check if NAS-backed state enabled
  if [[ "${USE_NAS_STATE:-}" == "true" ]]; then
    local state_root="${nas_base}/infra_state/${env}"

    # Verify NAS mount accessible
    if [[ ! -d "$nas_base" ]]; then
      echo "ERROR: NAS mount not found at $nas_base" >&2
      echo "  On PVE: Ensure /mnt/nas/homelab_ci mounted (ansible/roles/proxmox_mounts)" >&2
      echo "  On macOS: Run setup from docs/runbooks/laptop-nfs-setup.md" >&2
      return 1
    fi

    # Verify state root exists
    if [[ ! -d "$state_root" ]]; then
      echo "ERROR: State root not found at $state_root" >&2
      echo "  Run: ansible-playbook ansible/playbooks/setup-state-dirs.yml" >&2
      return 1
    fi

    echo "$state_root"
  else
    # Legacy path (existing behavior)
    echo "/var/lib/homelab-proxmox/state/services"
  fi
}

# Get state file path for a specific service
get_service_state_path() {
  local service="${1:?Service name required}"
  local state_root

  state_root="$(resolve_state_root)" || return 1

  if [[ "${USE_NAS_STATE:-}" == "true" ]]; then
    # NAS: <root>/<service>/terraform.tfstate
    echo "${state_root}/${service}/terraform.tfstate"
  else
    # Legacy: <root>/<service>/terraform.tfstate
    echo "${state_root}/${service}/terraform.tfstate"
  fi
}

# Get Ansible inventory path for environment
get_inventory_path() {
  local env="${ENVIRONMENT:?ENVIRONMENT must be set}"
  local state_root

  state_root="$(resolve_state_root)" || return 1

  if [[ "${USE_NAS_STATE:-}" == "true" ]]; then
    # NAS: <root>/ansible/inventories/generated/hosts.yml
    echo "${state_root}/ansible/inventories/generated/hosts.yml"
  else
    # Legacy: Repo-local generated inventory
    local repo_root="${REPO_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || echo "$PWD")}"
    echo "${repo_root}/ansible/inventories/generated/hosts.yml"
  fi
}

# Verify state path accessible (fail-fast)
verify_state_access() {
  local state_root
  state_root="$(resolve_state_root)" || return 1

  # Test write access
  local test_file="${state_root}/.state-access-test-$$"
  if ! touch "$test_file" 2>/dev/null; then
    echo "ERROR: Cannot write to state root: $state_root" >&2
    echo "  Check NFS mount permissions" >&2
    return 1
  fi
  rm -f "$test_file"

  return 0
}
