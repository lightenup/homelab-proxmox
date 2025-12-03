#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

OUT_JSON=$(terraform -chdir=terraform output -json ansible_inventory)

SERVICES=$(echo "$OUT_JSON" | jq -r '.services | keys[]')

mkdir -p ansible/inventories/generated

{
  echo "all:"
  echo "  children:"
  echo "    services:"
  echo "      hosts:"
  for svc in $SERVICES; do
    ip=$(echo "$OUT_JSON" | jq -r ".services[\"$svc\"]")
    echo "        ${svc}:"
    echo "          ansible_host: ${ip}"
    echo "          ansible_user: root"
  done
} > ansible/inventories/generated/hosts.yml
