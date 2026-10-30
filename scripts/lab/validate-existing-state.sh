#!/usr/bin/env bash
# scripts/lab/validate-existing-state.sh
# Purpose: Inventory the production Terraform state files (state/prod/<svc>, 067)
# Usage: Run on PVE host to list existing state files

set -euo pipefail

STATE_ROOT="${STATE_ROOT:-/var/lib/homelab-proxmox/state}/prod"
SERVICES=(
  "ntfy" "market-model" "financial-scenario" "eurooffice" "llm-router" "jellyfin"
  "homeassistant" "nextcloud" "immich" "hermes" "monitoring" "reverse_proxy"
)

echo "======================================"
echo "Existing Terraform State Inventory"
echo "======================================"
echo ""
echo "State root: ${STATE_ROOT}"
echo "Survey date: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

total_found=0
total_missing=0

echo "----------------------------------------"
echo "Scanning for state files"
echo "----------------------------------------"

for svc in "${SERVICES[@]}"; do
  state_file="${STATE_ROOT}/${svc}/terraform.tfstate"

  if [[ -f "${state_file}" ]]; then
    # Get file size (cross-platform: stat -c for Linux, stat -f for macOS)
    if stat --version >/dev/null 2>&1; then
      # GNU stat (Linux)
      size=$(stat -c '%s' "${state_file}")
      mtime=$(stat -c '%y' "${state_file}")
    else
      # BSD stat (macOS)
      size=$(stat -f '%z' "${state_file}")
      mtime=$(stat -f '%Sm' "${state_file}")
    fi

    # Calculate checksum for verification
    if command -v sha256sum >/dev/null 2>&1; then
      checksum=$(sha256sum "${state_file}" | awk '{print $1}')
    else
      checksum=$(shasum -a 256 "${state_file}" | awk '{print $1}')
    fi

    echo "  ✓ ${svc}:"
    echo "      Path: ${state_file}"
    echo "      Size: ${size} bytes"
    echo "      Modified: ${mtime}"
    echo "      SHA256: ${checksum:0:16}..."

    total_found=$((total_found + 1))
  else
    echo "  ✗ ${svc}: NOT FOUND"
    total_missing=$((total_missing + 1))
  fi
done

echo ""
echo "======================================"
echo "Summary"
echo "======================================"
echo "Total state files found: ${total_found}"
echo "Total state files missing: ${total_missing}"
echo ""

if [[ ${total_missing} -eq ${#SERVICES[@]} ]]; then
  echo "✓ No state files found - fresh infrastructure (no migration needed)"
  echo ""
fi

# Exit with status indicating if any state files exist
if [[ ${total_found} -gt 0 ]]; then
  exit 0  # State files exist
else
  exit 1  # No state files (fresh start)
fi
