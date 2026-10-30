#!/usr/bin/env bash
# scripts/lab/lib/state.sh
# Terraform state paths on the PVE host's local disk (067, constitution State Management).
#
#   <STATE_ROOT>/prod/<svc>/terraform.tfstate   the one production state per service
#   <STATE_ROOT>/lab/<svc>/terraform.tfstate    exists only while a lab run is in flight
#
# STATE_ROOT defaults to /var/lib/homelab-proxmox/state. The prod tree is backed up to Synology
# by the PVE config backup; the lab tree never is.

# Print the state root for an environment ("lab" or "prod").
resolve_state_root() {
  local env="${1:?resolve_state_root requires an environment}"

  case "$env" in
    lab|prod) ;;
    *)
      echo "ERROR: Unknown environment '$env'. Must be 'lab' or 'prod'." >&2
      return 1
      ;;
  esac

  echo "${STATE_ROOT:-/var/lib/homelab-proxmox/state}/${env}"
}

# Print the state file path for a service in an environment.
get_service_state_path() {
  local env="${1:?Environment required}"
  local service="${2:?Service name required}"
  local state_root

  state_root="$(resolve_state_root "$env")" || return 1
  echo "${state_root}/${service}/terraform.tfstate"
}

# Generated Ansible inventory path (repo-local).
get_inventory_path() {
  local repo_root="${REPO_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || echo "$PWD")}"
  echo "${repo_root}/ansible/inventories/generated/hosts.yml"
}

# Verify the state root is writable (fail-fast).
verify_state_access() {
  local env="${1:?verify_state_access requires an environment}"
  local state_root
  state_root="$(resolve_state_root "$env")" || return 1

  local test_file="${state_root}/.state-access-test-$$"
  if ! touch "$test_file" 2>/dev/null; then
    echo "ERROR: Cannot write to state root: $state_root" >&2
    echo "  State is local to the PVE host; run this on pve as ci (setup: ansible/playbooks/setup-state-dirs.yml)" >&2
    return 1
  fi
  rm -f "$test_file"

  return 0
}
