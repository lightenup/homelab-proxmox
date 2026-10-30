#!/usr/bin/env bash
set -euo pipefail

# lib/snapshot.sh - LAB inventory snapshot generator

snapshot_repo_root() {
    if [[ -n "${REPO_ROOT:-}" && -d "${REPO_ROOT}" ]]; then
        echo "${REPO_ROOT}"
        return 0
    fi
    return 1
}

snapshot_collect_latest_evidence() {
    local environment="${1:?snapshot_collect_latest_evidence requires environment}"

    if ! command -v jq >/dev/null 2>&1; then
        echo "{}"
        return 0
    fi

    if [[ -z "${ARTIFACT_ROOT:-}" || -z "${ARTIFACT_RUNS_DIR:-}" ]]; then
        echo "{}"
        return 0
    fi

    local repo_root
    if ! repo_root="$(snapshot_repo_root)"; then
        echo "{}"
        return 0
    fi

    local evidence_runs_root
    evidence_runs_root="${ARTIFACT_ROOT%/}/${ARTIFACT_RUNS_DIR}"
    if [[ ! -d "${evidence_runs_root}" ]]; then
        echo "{}"
        return 0
    fi

    local services_root="${repo_root%/}/terraform/services"
    if [[ ! -d "${services_root}" ]]; then
        echo "{}"
        return 0
    fi

    local ndjson=""
    local service_dir
    while IFS= read -r -d '' service_dir; do
        local service
        service="$(basename "${service_dir}")"

        local latest_path
        latest_path="$(ls -1dt "${evidence_runs_root}/${environment}-${service}-"* 2>/dev/null | head -n 1 || true)"
        if [[ -z "${latest_path}" ]]; then
            continue
        fi
        if [[ ! -d "${latest_path}" ]]; then
            continue
        fi

        local run_id
        run_id="$(basename "${latest_path}")"

        ndjson+="$(jq -cn --arg svc "${service}" --arg run_id "${run_id}" --arg path "${latest_path}" '{($svc):{run_id:$run_id,path:$path}}')"$'\n'
    done < <(find "${services_root}" -mindepth 1 -maxdepth 1 -type d -print0 2>/dev/null || true)

    if [[ -z "${ndjson}" ]]; then
        echo "{}"
        return 0
    fi

    printf '%s' "${ndjson}" | jq -s 'reduce .[] as $i ({}; . + $i)'
}

snapshot_collect_mount_checks() {
    local containers_json="${1:-[]}" # array of containers
    local mount_path="${2:-/media/video}"

    if ! command -v jq >/dev/null 2>&1; then
        echo "[]"
        return 0
    fi

    if ! command -v pct >/dev/null 2>&1; then
        echo "[]"
        return 0
    fi

    local ndjson=""
    local vmid
    while IFS= read -r vmid; do
        [[ -z "${vmid}" ]] && continue

        local status
        status="$(jq -r --argjson vmid "${vmid}" '.[] | select(.vmid == $vmid) | .status' <<<"${containers_json}" | head -n 1)"
        if [[ "${status}" != "running" ]]; then
            continue
        fi

        local line
        if line="$(sudo -n pct exec "${vmid}" -- awk -v mp="${mount_path}" '$2==mp{print $1"\t"$4; exit}' /proc/mounts 2>/dev/null)"; then
            :
        else
            line="$(pct exec "${vmid}" -- awk -v mp="${mount_path}" '$2==mp{print $1"\t"$4; exit}' /proc/mounts 2>/dev/null || true)"
        fi

        if [[ -z "${line}" ]]; then
            ndjson+="$(jq -cn --argjson vmid "${vmid}" --arg mp "${mount_path}" '{container_vmid:$vmid, mount_path:$mp, mounted:false}')"$'\n'
            continue
        fi

        local source opts
        source="$(awk -F'\t' '{print $1}' <<<"${line}")"
        opts="$(awk -F'\t' '{print $2}' <<<"${line}")"

        local ro=false
        if [[ ",${opts}," == *",ro,"* ]]; then
            ro=true
        fi

        ndjson+="$(jq -cn --argjson vmid "${vmid}" --arg mp "${mount_path}" --arg source "${source}" --argjson ro "${ro}" '{container_vmid:$vmid, mount_path:$mp, mounted:true, read_only:$ro, source:$source}')"$'\n'
    done < <(jq -r '.[].vmid' <<<"${containers_json}" 2>/dev/null || true)

    if [[ -z "${ndjson}" ]]; then
        echo "[]"
        return 0
    fi

    printf '%s' "${ndjson}" | jq -s '.'
}

# Write a LAB snapshot JSON file matching scripts/lab/contracts/evidence-lab-snapshot.schema.json
# Usage: write_lab_snapshot <output_path> [environment] [state_root]
write_lab_snapshot() {
    local output_path="${1:?write_lab_snapshot requires output_path}"
    local environment="${2:-${ENVIRONMENT:-lab}}"
    local state_root

    # Use state library if available
    if command -v resolve_state_root >/dev/null 2>&1; then
        state_root="$(resolve_state_root "${environment}" 2>/dev/null)" || state_root="${3:-/var/lib/homelab-proxmox/state/${environment}}"
    else
        state_root="${3:-/var/lib/homelab-proxmox/state/${environment}}"
    fi

    local generated_at
    generated_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

    local -a errors=()

    if ! command -v jq >/dev/null 2>&1; then
        echo "ERROR: jq is required for snapshot generation" >&2
        return 1
    fi

    local containers_ndjson=""

    if command -v pct >/dev/null 2>&1; then
        local pct_out
        if pct_out="$(sudo -n pct list 2>/dev/null)"; then
            :
        else
            pct_out="$(pct list 2>/dev/null || true)"
        fi

        if [[ -n "${pct_out}" ]]; then
            while IFS= read -r line; do
                [[ -z "${line}" ]] && continue
                # Skip header line
                if [[ "${line}" =~ ^VMID[[:space:]]+Status ]]; then
                    continue
                fi

                local vmid status name
                vmid="$(awk '{print $1}' <<<"${line}")"
                status="$(awk '{print $2}' <<<"${line}")"
                name="$(awk '{print $4}' <<<"${line}")"

                if [[ -z "${vmid}" || -z "${status}" ]]; then
                    continue
                fi

                case "${status}" in
                    running|stopped) ;;
                    *)
                        errors+=("pct list: unknown status '${status}' for vmid=${vmid}")
                        continue
                        ;;
                esac

                local hostname
                hostname="${name:-}"

                if [[ -n "${vmid}" ]]; then
                    local cfg
                    if cfg="$(sudo -n pct config "${vmid}" 2>/dev/null)"; then
                        :
                    else
                        cfg="$(pct config "${vmid}" 2>/dev/null || true)"
                    fi

                    local cfg_hostname
                    cfg_hostname="$(awk -F': ' '/^hostname:/{print $2; exit}' <<<"${cfg}")"
                    if [[ -n "${cfg_hostname}" ]]; then
                        hostname="${cfg_hostname}"
                    fi
                fi

                if [[ -z "${hostname}" ]]; then
                    hostname="ct-${vmid}"
                fi

                # ipv4 is optional; baseline snapshot leaves it empty.
                containers_ndjson+="$(jq -cn \
                    --argjson vmid "${vmid}" \
                    --arg hostname "${hostname}" \
                    --arg status "${status}" \
                    '{vmid:$vmid, hostname:$hostname, status:$status, ipv4:""}')"$'\n'
            done <<<"${pct_out}"
        else
            errors+=("pct list returned no output")
        fi
    else
        errors+=("pct not found; cannot enumerate containers")
    fi

    local containers_json
    if [[ -n "${containers_ndjson}" ]]; then
        containers_json="$(printf '%s' "${containers_ndjson}" | jq -s '.')"
    else
        containers_json="[]"
    fi

    local services_ndjson=""
    if [[ -d "${state_root}" ]]; then
        while IFS= read -r -d '' dir; do
            local service
            service="$(basename "${dir}")"
            services_ndjson+="$(jq -cn --arg service "${service}" --arg state_path "${dir}" '{service:$service, state_path:$state_path}')"$'\n'
        done < <(find "${state_root}" -mindepth 1 -maxdepth 1 -type d -print0 2>/dev/null || true)
    else
        errors+=("state_root not found: ${state_root}")
    fi

    local services_json
    if [[ -n "${services_ndjson}" ]]; then
        services_json="$(printf '%s' "${services_ndjson}" | jq -s '.')"
    else
        services_json="[]"
    fi

    local latest_evidence_json
    if latest_evidence_json="$(snapshot_collect_latest_evidence "${environment}")"; then
        :
    else
        latest_evidence_json="{}"
        errors+=("latest_evidence scan failed")
    fi

    local mount_checks_json
    if mount_checks_json="$(snapshot_collect_mount_checks "${containers_json}" "/media/video")"; then
        :
    else
        mount_checks_json="[]"
        errors+=("mount_checks collection failed")
    fi

    local errors_json
    if [[ "${#errors[@]}" -gt 0 ]]; then
        errors_json="$(printf '%s\n' "${errors[@]}" | jq -R . | jq -s '.')"
    else
        errors_json="[]"
    fi

    mkdir -p "$(dirname "${output_path}")"

    jq -n \
        --arg generated_at "${generated_at}" \
        --arg environment "${environment}" \
        --argjson containers "${containers_json}" \
        --argjson services "${services_json}" \
        --argjson latest_evidence "${latest_evidence_json}" \
        --argjson mount_checks "${mount_checks_json}" \
        --argjson errors "${errors_json}" \
        '{generated_at:$generated_at, environment:$environment, containers:$containers, services:$services, latest_evidence:$latest_evidence, mount_checks:$mount_checks, errors:$errors}' \
        >"${output_path}"
}
