#!/usr/bin/env bash
# scripts/lab/migrate-state-to-nas.sh
# Purpose: One-time migration of Terraform state from PVE filesystem to NAS
# Task: D-008 from specs/033-idempotent-rebuild/plan-delta-state-storage.md
# Usage: DRY_RUN=true|false ENVIRONMENT=lab|prod bash migrate-state-to-nas.sh

set -euo pipefail

ENVIRONMENT="${ENVIRONMENT:-lab}"
DRY_RUN="${DRY_RUN:-true}"

echo "======================================"
echo "State Migration to NAS"
echo "======================================"
echo "Environment: $ENVIRONMENT"
echo "Dry Run: $DRY_RUN"
echo ""

LEGACY_ROOT="/var/lib/homelab-proxmox/state/services"
NAS_ROOT="/mnt/nas/homelab_ci/infra_state/${ENVIRONMENT}"

# Validate environment
case "$ENVIRONMENT" in
  lab|prod) ;;
  *)
    echo "ERROR: Unknown environment '$ENVIRONMENT'. Must be 'lab' or 'prod'." >&2
    exit 1
    ;;
esac

# Check NAS root exists
if [[ ! -d "$NAS_ROOT" ]]; then
  echo "ERROR: NAS state root not found: $NAS_ROOT"
  echo "Run: ansible-playbook ansible/playbooks/setup-state-dirs.yml"
  exit 1
fi

# Check legacy root exists
if [[ ! -d "$LEGACY_ROOT" ]]; then
  echo "No legacy state directory found at $LEGACY_ROOT"
  echo "This appears to be a fresh installation (no migration needed)"
  exit 0
fi

SERVICES_FOUND=0
SERVICES_MIGRATED=0
SERVICES_SKIPPED=0
SERVICES_CONFLICT=0

for service_dir in "${LEGACY_ROOT}"/*; do
  [[ -d "$service_dir" ]] || continue

  service="$(basename "$service_dir")"
  legacy_state="${service_dir}/terraform.tfstate"
  nas_state="${NAS_ROOT}/${service}/terraform.tfstate"

  if [[ ! -f "$legacy_state" ]]; then
    echo "⊘ ${service}: No state file to migrate"
    continue
  fi

  SERVICES_FOUND=$((SERVICES_FOUND + 1))

  # Get file size (cross-platform)
  if stat --version >/dev/null 2>&1; then
    # GNU stat (Linux)
    size=$(stat -c '%s' "$legacy_state")
    mtime=$(stat -c '%y' "$legacy_state")
  else
    # BSD stat (macOS)
    size=$(stat -f '%z' "$legacy_state")
    mtime=$(stat -f '%Sm' "$legacy_state")
  fi

  # Check if NAS state already exists
  if [[ -f "$nas_state" ]]; then
    echo "⚠ ${service}: NAS state exists, comparing..."

    # Compare files
    if diff "$legacy_state" "$nas_state" >/dev/null 2>&1; then
      echo "  ✓ Identical, skipping"
      SERVICES_SKIPPED=$((SERVICES_SKIPPED + 1))
    else
      echo "  ✗ DIFFERS! Manual review required"
      echo "    Legacy: $legacy_state"
      echo "    NAS: $nas_state"
      echo "    Action: Compare files manually and resolve conflict"
      SERVICES_CONFLICT=$((SERVICES_CONFLICT + 1))
    fi
    continue
  fi

  # Perform migration
  if [[ "$DRY_RUN" == "true" ]]; then
    echo "➜ ${service}: Would copy ${size} bytes"
    echo "    From: $legacy_state"
    echo "    To: $nas_state"
    echo "    Modified: $mtime"
  else
    echo "➜ ${service}: Copying ${size} bytes..."
    mkdir -p "$(dirname "$nas_state")"
    cp -a "$legacy_state" "$nas_state"

    # Verify copy succeeded
    if diff "$legacy_state" "$nas_state" >/dev/null 2>&1; then
      echo "  ✓ Complete and verified"
      SERVICES_MIGRATED=$((SERVICES_MIGRATED + 1))
    else
      echo "  ✗ ERROR: Copy verification failed!"
      exit 1
    fi
  fi
done

echo ""
echo "======================================"
echo "Migration Summary"
echo "======================================"
echo "Services found: $SERVICES_FOUND"
echo "Services migrated: $SERVICES_MIGRATED"
echo "Services skipped (identical): $SERVICES_SKIPPED"
echo "Services with conflicts: $SERVICES_CONFLICT"
echo ""

if [[ "$DRY_RUN" == "true" ]]; then
  echo "Dry run complete. To execute migration:"
  echo "  DRY_RUN=false ENVIRONMENT=${ENVIRONMENT} bash $0"
else
  echo "Migration complete!"
  echo ""
  echo "Next steps:"
  echo "  1. Verify state files:"
  echo "     ls -lh ${NAS_ROOT}/*/terraform.tfstate"
  echo ""
  echo "  2. Test NAS state access:"
  echo "     USE_NAS_STATE=true ENVIRONMENT=${ENVIRONMENT} bash -c 'source scripts/lab/lib/state.sh && resolve_state_root'"
  echo ""
  echo "  3. Deploy symlinks for backward compatibility:"
  echo "     cd ansible && ansible-playbook -i inventories/prod/hosts.yml playbooks/setup-state-symlinks.yml -e proxmox_state_symlinks_enabled=true"
  echo ""
fi

# Exit with error if conflicts detected
if [[ $SERVICES_CONFLICT -gt 0 ]]; then
  echo "⚠️  WARNING: Conflicts detected. Resolve before deploying symlinks."
  exit 1
fi

exit 0
