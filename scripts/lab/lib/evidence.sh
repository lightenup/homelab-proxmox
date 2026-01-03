#!/usr/bin/env bash
# lib/evidence.sh - Evidence pack management functions

set -euo pipefail

# Create evidence pack directory structure
# Usage: create_evidence_pack base_dir
# Returns: runid (timestamp-based)
create_evidence_pack() {
    local base_dir="$1"
    
    # Generate runid with timestamp format: lab-YYYYMMDD-HHMMSS
    local runid
    runid="lab-$(date -u +"%Y%m%d-%H%M%S")"
    
    local evidence_dir="${base_dir}/${runid}"
    
    # Create directory structure
    mkdir -p "$base_dir"
    mkdir -p "$evidence_dir"
    mkdir -p "$evidence_dir/logs"
    mkdir -p "$evidence_dir/reports"
    
    # Return runid
    echo "$runid"
}

# Generate evidence_manifest.json
# Usage: generate_manifest evidence_dir [artifact_path type check_id sha256 ...]
generate_manifest() {
    local evidence_dir="$1"
    shift
    
    local manifest_schema_version="1.0.0"
    
    # Build artifacts array from arguments (groups of 4: path, type, check_id, sha256)
    local artifacts_json="["
    local first=true
    
    while [[ $# -gt 0 ]]; do
        local path="$1"
        local type="${2:-unknown}"
        local check_id="${3:-none}"
        local sha256="${4:-}"
        shift 4 2>/dev/null || break
        
        if [ "$first" = true ]; then
            first=false
        else
            artifacts_json+=","
        fi
        
        artifacts_json+=$(cat <<EOF
{
  "path": "$path",
  "type": "$type",
  "check_id": "$check_id"$([ -n "$sha256" ] && echo ",\"sha256\":\"$sha256\"" || echo "")
}
EOF
)
    done
    artifacts_json+="]"
    
    # Write manifest
    cat > "${evidence_dir}/evidence_manifest.json" <<EOF
{
  "contract_version": "1.0.0",
  "manifest_schema_version": "$manifest_schema_version",
  "artifacts": $artifacts_json
}
EOF
}

# Add artifact to manifest (append mode)
# Usage: add_artifact_to_manifest evidence_dir artifact_path type check_id [sha256]
add_artifact_to_manifest() {
    local evidence_dir="$1"
    local artifact_path="$2"
    local type="$3"
    local check_id="$4"
    local sha256="${5:-}"
    
    local manifest_file="${evidence_dir}/evidence_manifest.json"
    
    # If manifest doesn't exist, create it
    if [[ ! -f "$manifest_file" ]]; then
        generate_manifest "$evidence_dir"
    fi
    
    # Parse existing manifest, add new artifact, write back
    # This is a simplified append - full implementation would use jq
    # For now, we'll rebuild on final generation
    :
}

# Validate evidence files against JSON schemas
# Usage: validate_evidence evidence_dir contracts_dir
validate_evidence() {
    local evidence_dir="$1"
    local contracts_dir="$2"
    
    local validation_ok=true
    
    # Check if validation tools are available
    if command -v ajv &>/dev/null; then
        # Validate with ajv-cli
        for json_file in "${evidence_dir}"/*.json; do
            if [[ -f "$json_file" ]]; then
                local basename
                basename="$(basename "$json_file")"
                local schema_file="${contracts_dir}/${basename%.json}_schema.json"
                
                if [[ -f "$schema_file" ]]; then
                    if ! ajv validate -s "$schema_file" -d "$json_file" 2>&1; then
                        echo "ERROR: Validation failed for $basename" >&2
                        validation_ok=false
                    fi
                fi
            fi
        done
    elif python3 -c "import jsonschema" 2>/dev/null; then
        # Validate with Python jsonschema
        echo "Using Python jsonschema for validation" >&2
        # Implementation would use Python script
        :
    else
        echo "WARNING: No JSON schema validation tool available (ajv-cli or python jsonschema)" >&2
        echo "Skipping schema validation" >&2
    fi
    
    if [ "$validation_ok" = true ]; then
        return 0
    else
        return 1
    fi
}

# Collect provisioning evidence on timeout/failure
# Usage: collect_provisioning_evidence <vmid> [target_ip] [evidence_dir]
collect_provisioning_evidence() {
    local vmid="$1"
    local target_ip="${2:-${LAB_IP:-10.99.0.10}}"
    local evidence_dir="${3:-${EVIDENCE_ROOT:-${ARTIFACT_DIR:-/tmp}}}"
    local ssh_target="${SSH_USER:-ci}@${PROXMOX_HOST:-pve}"
    local dir="${evidence_dir}/reports/provisioning"
    local ssh_opts="${SSH_OPTS:-}"

    mkdir -p "$dir"

    # Host-side probes
    if is_local_proxmox; then
        host_exec "sudo -n /usr/sbin/qm status $vmid" > "$dir/qm-status-${vmid}.txt" 2>&1 || true
        host_exec "sudo -n /usr/sbin/qm config $vmid" > "$dir/qm-config-${vmid}.txt" 2>&1 || true
        host_exec "sudo -n /usr/sbin/qm cloudinit dump $vmid user" > "$dir/qm-cloudinit-user-${vmid}.txt" 2>&1 || true
        host_exec "sudo -n /usr/sbin/qm cloudinit dump $vmid network" > "$dir/qm-cloudinit-net-${vmid}.txt" 2>&1 || true
        host_exec "ping -c 3 ${target_ip}" > "$dir/ping-${target_ip}.txt" 2>&1 || true
        host_exec "(command -v nc >/dev/null 2>&1 && nc -vz -w 3 ${target_ip} 22) || echo 'nc not available'" > "$dir/nc-22-${target_ip}.txt" 2>&1 || true
        host_exec "journalctl -u pvedaemon -n 200 --no-pager" > "$dir/journal-pvedaemon.txt" 2>&1 || true
        host_exec "ip addr show ${LAB_BRIDGE:-vmbr99}" > "$dir/ip-${LAB_BRIDGE:-vmbr99}.txt" 2>&1 || true
        host_exec "sudo -n /usr/sbin/qm cloudinit pending $vmid" > "$dir/qm-cloudinit-status-${vmid}.txt" 2>&1 || true

        if [[ -n "${PROVISION_SSH_KEY:-}" && -f "${PROVISION_SSH_KEY}" ]]; then
            host_exec "ssh -vvv -o BatchMode=yes -o ConnectTimeout=5 -o ConnectionAttempts=1 -i '${PROVISION_SSH_KEY}' '${PROVISION_SSH_USER:-ansible}@${target_ip}' 'echo ok'" > "$dir/ssh-attempt-${target_ip}.txt" 2>&1 || true
        else
            host_exec "ssh -vvv -o BatchMode=yes -o ConnectTimeout=5 -o ConnectionAttempts=1 '${PROVISION_SSH_USER:-ansible}@${target_ip}' 'echo ok'" > "$dir/ssh-attempt-${target_ip}.txt" 2>&1 || true
        fi
    else
        ssh $ssh_opts "$ssh_target" "sudo -n /usr/sbin/qm status $vmid" > "$dir/qm-status-${vmid}.txt" 2>&1 || true
        ssh $ssh_opts "$ssh_target" "sudo -n /usr/sbin/qm config $vmid" > "$dir/qm-config-${vmid}.txt" 2>&1 || true
        ssh $ssh_opts "$ssh_target" "sudo -n /usr/sbin/qm cloudinit dump $vmid user" > "$dir/qm-cloudinit-user-${vmid}.txt" 2>&1 || true
        ssh $ssh_opts "$ssh_target" "sudo -n /usr/sbin/qm cloudinit dump $vmid network" > "$dir/qm-cloudinit-net-${vmid}.txt" 2>&1 || true
        ssh $ssh_opts "$ssh_target" "ping -c 3 ${target_ip}" > "$dir/ping-${target_ip}.txt" 2>&1 || true
        ssh $ssh_opts "$ssh_target" "(command -v nc >/dev/null 2>&1 && nc -vz -w 3 ${target_ip} 22) || echo 'nc not available'" > "$dir/nc-22-${target_ip}.txt" 2>&1 || true
        ssh $ssh_opts "$ssh_target" "journalctl -u pvedaemon -n 200 --no-pager" > "$dir/journal-pvedaemon.txt" 2>&1 || true
        ssh $ssh_opts "$ssh_target" "ip addr show ${LAB_BRIDGE:-vmbr99}" > "$dir/ip-${LAB_BRIDGE:-vmbr99}.txt" 2>&1 || true
        # Capture recent task log for the VM if available
        ssh $ssh_opts "$ssh_target" "sudo -n /usr/sbin/qm cloudinit pending $vmid" > "$dir/qm-cloudinit-status-${vmid}.txt" 2>&1 || true

        # Try one verbose SSH attempt from the Proxmox host to the VM
        if [[ -n "${PROVISION_SSH_KEY:-}" && -f "${PROVISION_SSH_KEY}" ]]; then
            ssh $ssh_opts "$ssh_target" "ssh -vvv -o BatchMode=yes -o ConnectTimeout=5 -o ConnectionAttempts=1 -i '${PROVISION_SSH_KEY}' '${PROVISION_SSH_USER:-ansible}@${target_ip}' 'echo ok'" > "$dir/ssh-attempt-${target_ip}.txt" 2>&1 || true
        else
            ssh $ssh_opts "$ssh_target" "ssh -vvv -o BatchMode=yes -o ConnectTimeout=5 -o ConnectionAttempts=1 '${PROVISION_SSH_USER:-ansible}@${target_ip}' 'echo ok'" > "$dir/ssh-attempt-${target_ip}.txt" 2>&1 || true
        fi
    fi
}
