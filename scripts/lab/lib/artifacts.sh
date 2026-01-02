#!/usr/bin/env bash
# artifacts.sh - Artifact path helpers for lab orchestrator
# Centralizes artifact root location to avoid rsync deletion and ensure consistent ownership

set -euo pipefail

# Default artifact root on PVE (outside repo sync)
: "${ARTIFACT_ROOT:=/var/lib/homelab-proxmox/artifacts}"

artifact_root() {
    echo "$ARTIFACT_ROOT"
}

artifact_path() {
    local relative="$1"
    if [[ -z "$relative" ]]; then
        echo "$ARTIFACT_ROOT"
    else
        echo "$ARTIFACT_ROOT/${relative#./}"
    fi
}

ensure_artifact_root() {
    if [[ -d "$ARTIFACT_ROOT" ]]; then
        return 0
    fi

    if mkdir -p "$ARTIFACT_ROOT" 2>/dev/null; then
        return 0
    fi

    echo "ERROR: Unable to create artifact root at $ARTIFACT_ROOT. Ensure user has write permissions or pre-create with correct ownership." >&2
    return 1
}
