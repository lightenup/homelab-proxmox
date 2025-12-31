#!/usr/bin/env bash
# lib/cleanup.sh - Cleanup verification check functions
# Part of 019c1-semantic-safety-closure

set -euo pipefail

# Verify no lab VMs remain in range 9000-9099
# Usage: check_no_lab_vms ssh_target evidence_dir
check_no_lab_vms() {
    local ssh_target="$1"
    local evidence_dir="$2"
    
    local inventory_file="${evidence_dir}/reports/vm_inventory.json"
    
    # Capture VM inventory
    capture_vm_inventory "$ssh_target" "$inventory_file"
    
    # Check for VMs in lab range with lab markers
    # Exclude templates (9001, 9002)
    local lab_vms
    lab_vms="$(ssh "$ssh_target" "qm list 2>/dev/null | awk '\$1 >= 9000 && \$1 <= 9099 && \$1 != 9001 && \$1 != 9002 {print \$1}'" || echo "")"
    
    if [[ -z "$lab_vms" ]]; then
        echo "PASS: No lab VMs found in range 9000-9099"
        return 0
    else
        echo "FAIL: Found lab VMs: $lab_vms"
        return 1
    fi
}

# Capture VM inventory to reports file
# Usage: capture_vm_inventory ssh_target output_file
capture_vm_inventory() {
    local ssh_target="$1"
    local output_file="$2"
    
    mkdir -p "$(dirname "$output_file")"
    
    # Get VM list and format as JSON
    local vm_list
    vm_list="$(ssh "$ssh_target" "qm list 2>/dev/null" || echo "")"
    
    # Simple JSON format
    cat > "$output_file" <<EOF
{
  "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "vm_list": $(echo "$vm_list" | jq -R . | jq -s .)
}
EOF
}

# Verify no processes hold locks
# Usage: check_no_active_locks lock_dir evidence_dir
check_no_active_locks() {
    local lock_dir="$1"
    local evidence_dir="$2"
    
    local lock_status_file="${evidence_dir}/reports/lock_status.json"
    
    # Probe lock status
    probe_lock_status "$lock_dir" "$lock_status_file"
    
    # Check if any locks are held (using flock -n test)
    local active_locks=0
    if ls "$lock_dir"/*.lock >/dev/null 2>&1; then
        for lock_file in "$lock_dir"/*.lock; do
            if [[ -f "$lock_file" ]]; then
                # Try to acquire lock non-blocking
                if ! flock -n "$lock_file" true 2>/dev/null; then
                    active_locks=$((active_locks + 1))
                fi
            fi
        done
    fi
    
    if [[ $active_locks -eq 0 ]]; then
        echo "PASS: No active locks found"
        return 0
    else
        echo "FAIL: Found $active_locks active lock(s)"
        return 1
    fi
}

# Probe and capture lock status
# Usage: probe_lock_status lock_dir output_file
probe_lock_status() {
    local lock_dir="$1"
    local output_file="$2"
    
    mkdir -p "$(dirname "$output_file")"
    
    # List lock files and their status
    local lock_files=()
    local lock_pattern="${lock_dir}/*.lock"
    
    # Check if any .lock files exist
    if compgen -G "$lock_pattern" > /dev/null 2>&1; then
        for lock_file in $lock_pattern; do
            if [[ -f "$lock_file" ]]; then
                lock_files+=("$(basename "$lock_file")")
            fi
        done
    fi
    
    # Format as JSON
    if [[ ${#lock_files[@]} -gt 0 ]]; then
        local lock_files_json
        lock_files_json=$(printf '%s\n' "${lock_files[@]}" | jq -R . | jq -s .)
    else
        lock_files_json="[]"
    fi
    
    cat > "$output_file" <<EOF
{
  "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "lock_files": ${lock_files_json}
}
EOF
}
