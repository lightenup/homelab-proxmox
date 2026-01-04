#!/bin/bash
set -e

# Configuration
TERRAFORM_DIR="terraform"
INVENTORY_DIR="ansible/inventories/generated"
INVENTORY_FILE="$INVENTORY_DIR/hosts.yml"

# Prerequisites check
if ! command -v jq &> /dev/null; then
    echo "Error: jq is required but not installed."
    exit 1
fi

# Ensure inventory directory exists
mkdir -p "$INVENTORY_DIR"

echo "Fetching Terraform outputs..."
TF_OUTPUT=""
if [[ -n "${ANSIBLE_INVENTORY_JSON:-}" ]]; then
  TF_OUTPUT="${ANSIBLE_INVENTORY_JSON}"
elif [[ -n "${ANSIBLE_INVENTORY_JSON_PATH:-}" ]]; then
  if [[ ! -f "${ANSIBLE_INVENTORY_JSON_PATH}" ]]; then
    echo "Error: ANSIBLE_INVENTORY_JSON_PATH does not exist: ${ANSIBLE_INVENTORY_JSON_PATH}"
    exit 1
  fi
  TF_OUTPUT="$(cat "${ANSIBLE_INVENTORY_JSON_PATH}")"
else
  if ! command -v terraform &> /dev/null; then
    echo "Error: terraform is required but not installed (or provide ANSIBLE_INVENTORY_JSON/ANSIBLE_INVENTORY_JSON_PATH)."
    exit 1
  fi
  TF_OUTPUT=$(terraform -chdir="$TERRAFORM_DIR" output -json ansible_inventory)
fi

if [ -z "$TF_OUTPUT" ]; then
    echo "Error: Failed to get Terraform output or output is empty."
    exit 1
fi

echo "Generating inventory file at $INVENTORY_FILE..."

# Optional: set a dedicated SSH private key path for connecting to service hosts.
# This is especially useful for freshly provisioned hosts where we control which
# key is injected at provision time.
ANSIBLE_SSH_PRIVATE_KEY_FILE_VALUE="${ANSIBLE_SSH_PRIVATE_KEY_FILE:-}"

# Logic:
# 1. Extract .services object
# 2. Map each entry to a host object with ansible_host (stripping CIDR)
# 3. Wrap in the required YAML structure

JQ_FILTER='
  .services | to_entries | map({
    key: .key,
    value: {
      ansible_host: (.value | split("/")[0])
    }
  }) | from_entries as $hosts |
  {
    all: {
      children: {
        services: {
          hosts: $hosts,
          vars: (
            {
              ansible_user: "ansible",
              ansible_become: true
            }
            + (if $keyfile != "" then { ansible_ssh_private_key_file: $keyfile } else {} end)
          )
        }
      }
    }
  }
'

if command -v yq &> /dev/null; then
    echo "Using yq for YAML generation..."
  echo "$TF_OUTPUT" | jq -r --arg keyfile "${ANSIBLE_SSH_PRIVATE_KEY_FILE_VALUE}" "$JQ_FILTER" | yq -P > "$INVENTORY_FILE"
else
    echo "yq not found, using manual YAML generation..."
    
    cat <<YAML > "$INVENTORY_FILE"
all:
  children:
    services:
      hosts:
YAML

    # Parse JSON and append hosts
    echo "$TF_OUTPUT" | jq -r '.services | to_entries[] | "        \(.key):\n          ansible_host: \(.value | split("/")[0])"' >> "$INVENTORY_FILE"

    # Append vars
    cat <<YAML >> "$INVENTORY_FILE"
      vars:
        ansible_user: ansible
        ansible_become: true
YAML

    if [[ -n "${ANSIBLE_SSH_PRIVATE_KEY_FILE_VALUE}" ]]; then
      printf '        ansible_ssh_private_key_file: %s\n' "${ANSIBLE_SSH_PRIVATE_KEY_FILE_VALUE}" >> "$INVENTORY_FILE"
    fi
fi

echo "Inventory generated successfully:"
cat "$INVENTORY_FILE"
