#!/usr/bin/env bash
# checks.d/rebuild-mounts.sh - Rebuild mount validation checks

set -euo pipefail

rebuild_config_path() {
    echo "${REBUILD_CONFIG_PATH:-${REPO_ROOT:-}/scripts/lab/rebuild-config.json}"
}

rebuild_required_mounts() {
    local config
    config="$(rebuild_config_path)"
    jq -r '.required_host_mounts[]' "$config"
}

rebuild_immich_mounts() {
    local config
    config="$(rebuild_config_path)"
    jq -r '.immich_bind_mounts[] | "\(.mp)\t\(.path)"' "$config"
}

find_immich_ctid() {
    if [[ -n "${REBUILD_IMMICH_CTID:-}" ]]; then
        echo "$REBUILD_IMMICH_CTID"
        return 0
    fi

    local config
    config="$(rebuild_config_path)"
    local configured
    configured=$(jq -r '.immich_ctid // empty' "$config")
    if [[ -n "$configured" && "$configured" != "null" ]]; then
        echo "$configured"
        return 0
    fi

    local ctid
    ctid=$(host_exec "pct list" 2>/dev/null | awk 'NR>1 {print $1"\t"$3}' | awk '$2 ~ /^immich/ {print $1; exit}')
    echo "$ctid"
}

run_rebuild_host_mount_checks() {
    local evidence_dir="${EVIDENCE_ROOT:-${ARTIFACT_DIR:-/tmp}}/reports/mounts"
    mkdir -p "$evidence_dir"

    local idx=0
    local failed=0
    local mounts_file="${evidence_dir}/required-mounts.txt"

    mapfile -t required_mounts < <(rebuild_required_mounts)
    printf '%s\n' "${required_mounts[@]}" > "$mounts_file"

    if [[ ${#required_mounts[@]} -eq 0 ]]; then
        if command -v log_error >/dev/null 2>&1; then
            log_error "No required mounts configured. Check scripts/lab/rebuild-config.json"
        fi
        record_check "MNT-000" "Required mount list present" "blocker" "PASS" "FAIL" "No required mounts configured" "reports/mounts/required-mounts.txt"
        return 1
    fi

    for mount_path in "${required_mounts[@]}"; do
        idx=$((idx + 1))
        local check_id="MNT-00${idx}"
        local evidence_file="${evidence_dir}/${check_id}.txt"
        local cmd="mountpoint -q ${mount_path}"

        if host_exec "$cmd" >/dev/null 2>&1; then
            echo "${mount_path} mounted" > "$evidence_file"
            record_check "$check_id" "Host mount present: ${mount_path}" "blocker" "PASS" "PASS" "Mount present" "reports/mounts/${check_id}.txt"
        else
            host_exec "mount | grep -E '${mount_path}'" > "$evidence_file" 2>&1 || true
            record_check "$check_id" "Host mount present: ${mount_path}" "blocker" "PASS" "FAIL" "Mount missing" "reports/mounts/${check_id}.txt"
            failed=1
        fi
    done

    return $failed
}

run_rebuild_immich_bind_mount_checks() {
    local evidence_dir="${EVIDENCE_ROOT:-${ARTIFACT_DIR:-/tmp}}/reports/mounts"
    mkdir -p "$evidence_dir"

    local ctid
    ctid=$(find_immich_ctid)

    local config_evidence="${evidence_dir}/IMMICH-CTID.txt"
    if [[ -z "$ctid" ]]; then
        echo "Immich CTID not found" > "$config_evidence"
        if command -v log_error >/dev/null 2>&1; then
            log_error "Immich CTID not found. Set REBUILD_IMMICH_CTID or immich_ctid in scripts/lab/rebuild-config.json."
        fi
        record_check "IMMICH-001" "Immich LXC found" "high" "PASS" "FAIL" "Immich CTID not found" "reports/mounts/IMMICH-CTID.txt"
        return 1
    fi

    echo "Immich CTID=${ctid}" > "$config_evidence"
    record_check "IMMICH-001" "Immich LXC found" "high" "PASS" "PASS" "Immich CTID ${ctid} found" "reports/mounts/IMMICH-CTID.txt"

    local config_file="${evidence_dir}/IMMICH-CONFIG.txt"
    host_exec "sudo -n /usr/sbin/pct config ${ctid}" > "$config_file" 2>&1 || true

    local failed=0
    while IFS=$'\t' read -r mp path; do
        local check_id="IMMICH-${mp^^}"
        local pattern="^${mp}:.*mp=${path}"

        if grep -E "$pattern" "$config_file" >/dev/null 2>&1; then
            record_check "$check_id" "Immich bind mount ${mp} configured" "blocker" "PASS" "PASS" "${mp} -> ${path} configured" "reports/mounts/IMMICH-CONFIG.txt"
        else
            record_check "$check_id" "Immich bind mount ${mp} configured" "blocker" "PASS" "FAIL" "${mp} missing or incorrect" "reports/mounts/IMMICH-CONFIG.txt"
            failed=1
        fi
    done < <(rebuild_immich_mounts)

    return $failed
}
