#!/usr/bin/env bash
# Dependency preflight checks for lab orchestrator
# Verifies required CLI tools are present before running rebuild/apply/verify

set -euo pipefail

# local logging wrappers to avoid hard dependency on caller symbols
log_dep_info() {
    if command -v log_info >/dev/null 2>&1; then
        log_info "$1"
    else
        echo "[INFO] $1"
    fi
}

log_dep_error() {
    if command -v log_error >/dev/null 2>&1; then
        log_error "$1"
    else
        echo "[ERROR] $1" >&2
    fi
}

run_dependency_preflight() {
    local start_ts
    start_ts=$(date +%s)
    local deps=(jq ssh rsync)

    for dep in "${deps[@]}"; do
        if ! command -v "$dep" >/dev/null 2>&1; then
            log_dep_error "Missing dependency: $dep. Install it before running (e.g., apt-get install $dep)."
            return 1
        fi
        # quick self-check for jq to ensure it can emit valid JSON
        if [[ "$dep" == "jq" ]]; then
            if ! jq -n '"ok"' >/dev/null 2>&1; then
                log_dep_error "jq is installed but failed a self-check; reinstall jq."
                return 1
            fi
        fi
    done

    local elapsed
    elapsed=$(( $(date +%s) - start_ts ))
    log_dep_info "Dependency preflight completed in ${elapsed}s"

    if [[ $elapsed -gt 60 ]]; then
        log_dep_error "Dependency preflight exceeded 60s (elapsed=${elapsed}s); investigate slow/misbehaving dependencies."
        return 1
    fi

    return 0
}
