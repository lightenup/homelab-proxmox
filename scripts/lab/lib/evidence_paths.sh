#!/usr/bin/env bash
set -euo pipefail

# Evidence path helpers (Spec 025). These are *pointers* (strings) intended for UI summaries.
# They should not be used as authority for file operations on the runner.

# shellcheck source=lib/artifacts.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/artifacts.sh"

pve_runs_dir() {
    # The directory that contains evidence packs on the Proxmox host.
    artifact_runs_path
}

pve_run_dir() {
    local run_id="${1:?run_id required}"
    artifact_run_path "${run_id}"
}
