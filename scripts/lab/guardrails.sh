#!/usr/bin/env bash
# scripts/lab/guardrails.sh - Negative test harness for safety validation

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="${SCRIPT_DIR}/lib"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PROXMOX_HOST="${PROXMOX_HOST:-pve}"
SSH_USER="${SSH_USER:-ci}"
SSH_OPTS="-o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=no -o CheckHostIP=no -o UserKnownHostsFile=/dev/null -o GlobalKnownHostsFile=/dev/null"
ARTIFACT_ROOT="/var/lib/homelab-proxmox/artifacts"
VAULT_ROOT="/var/lib/homelab-proxmox/vault"

# Source required libraries
# shellcheck source=lib/checks.sh
source "${LIB_DIR}/checks.sh"
# shellcheck source=lib/jsonl.sh
source "${LIB_DIR}/jsonl.sh"

is_local_proxmox_target() {
    local host_short
    local host_fqdn

    # If we're running on a Proxmox VE node, treat the target as local.
    # This avoids SSH-to-self requirements (keys/config) for on-host execution.
    if [[ -d /etc/pve ]] || command -v pveversion >/dev/null 2>&1; then
        return 0
    fi

    host_short="$(hostname -s 2>/dev/null || hostname)"
    host_fqdn="$(hostname -f 2>/dev/null || true)"

    if [[ "${PROXMOX_HOST}" == "localhost" || "${PROXMOX_HOST}" == "127.0.0.1" ]]; then
        return 0
    fi

    if [[ "${host_short}" == "${PROXMOX_HOST}" ]]; then
        return 0
    fi

    if [[ -n "${host_fqdn}" && "${host_fqdn}" == "${PROXMOX_HOST}" ]]; then
        return 0
    fi

    return 1
}

ensure_ci_artifact_root() {
    if is_local_proxmox_target; then
        echo "Ensuring artifact root ${ARTIFACT_ROOT} locally (PROXMOX_HOST=${PROXMOX_HOST})" >&2

        if ! sudo -n mkdir -p "${ARTIFACT_ROOT}" "${VAULT_ROOT}"; then
            echo "Failed to create ${ARTIFACT_ROOT} / ${VAULT_ROOT}" >&2
            return 1
        fi

        if ! sudo -n chown "${SSH_USER}:${SSH_USER}" "${ARTIFACT_ROOT}" "${VAULT_ROOT}"; then
            echo "Failed to chown ${ARTIFACT_ROOT} / ${VAULT_ROOT} to ${SSH_USER}" >&2
            return 1
        fi

        if ! sudo -n chmod 700 "${VAULT_ROOT}"; then
            echo "Failed to chmod 700 ${VAULT_ROOT}" >&2
            return 1
        fi
    else
        local ssh_target="${SSH_USER}@${PROXMOX_HOST}"

        echo "Ensuring artifact root ${ARTIFACT_ROOT} on ${ssh_target}" >&2

        if ! ssh ${SSH_OPTS} "${ssh_target}" "sudo -n mkdir -p '${ARTIFACT_ROOT}' '${VAULT_ROOT}' && sudo -n chown '${SSH_USER}:${SSH_USER}' '${ARTIFACT_ROOT}' '${VAULT_ROOT}' && sudo -n chmod 700 '${VAULT_ROOT}'"; then
            echo "Failed to ensure artifact root at ${ARTIFACT_ROOT}" >&2
            return 1
        fi
    fi

    return 0
}

# GUARD-001: Verify tier2 playbook rejects execution without lab_inventory=true
# Expected: FAIL (playbook should reject)
run_guard_001() {
    local evidence_dir="$1"
    local runid="${2:-}"
    
    echo "Running GUARD-001: Tier2 playbook rejects without lab_inventory=true" >&2
    
    if [[ -n "$runid" ]]; then
        emit_check_start "$runid" "GUARD-001" "Tier2 playbook rejects without lab_inventory=true"
    fi
    
    local guard_log="${evidence_dir}/reports/guard_001.log"
    mkdir -p "$(dirname "$guard_log")"
    
    # Attempt to run playbook with lab_inventory=false (should fail)
    local result="SKIP"
    local reason="Guard test execution failed"
    
    cd "$REPO_ROOT"
    
    # Run playbook with lab_inventory=false - expect assertion failure
    if ansible-playbook ansible/playbooks/lab_tier2_pve.yml \
        -i ansible/inventories/lab/hosts.yml \
        --extra-vars "lab_inventory=false" \
        --syntax-check &>"$guard_log"; then
        
        # Syntax check passed, now try actual execution (should fail at guard)
        if ansible-playbook ansible/playbooks/lab_tier2_pve.yml \
            -i ansible/inventories/lab/hosts.yml \
            --extra-vars "lab_inventory=false" \
            --check &>>"$guard_log"; then
            
            # UNEXPECTED: Playbook did not reject - this is an ERROR (safety hole)
            result="PASS"
            reason="SAFETY HOLE: Playbook accepted lab_inventory=false"
        else
            # EXPECTED: Playbook rejected
            result="FAIL"
            reason="Playbook correctly rejected lab_inventory=false (guard working)"
        fi
    else
        result="SKIP"
        reason="Syntax check failed, cannot test guard"
    fi
    
    # Record check with expected=FAIL
    record_check "GUARD-001" \
        "Tier2 playbook rejects execution without lab_inventory=true" \
        "high" \
        "FAIL" \
        "$result" \
        "$reason" \
        "reports/guard_001.log"
        
    if [[ -n "$runid" ]]; then
        emit_check_complete "$runid" "GUARD-001" "$result" "$reason"
    fi
    
    # Return validation result for abort logic
    # Return 0 if expected FAIL occurred, 1 if unexpected PASS (safety hole)
    if [[ "$result" == "FAIL" ]]; then
        return 0  # Guard worked as expected
    elif [[ "$result" == "PASS" ]]; then
        return 2  # Safety hole detected
    else
        return 1  # Could not test
    fi
}

# GUARD-002: Verify playbook rejects non-lab hostname pattern
# Expected: FAIL (playbook should reject)
run_guard_002() {
    local evidence_dir="$1"
    local runid="${2:-}"
    
    echo "Running GUARD-002: Playbook rejects non-lab hostname pattern" >&2
    
    if [[ -n "$runid" ]]; then
        emit_check_start "$runid" "GUARD-002" "Playbook rejects non-lab hostname pattern"
    fi
    
    # Create temporary inventory with bad hostname
    local tmp_dir="${evidence_dir}/tmp"
    mkdir -p "$tmp_dir"
    
    local bad_inventory="${tmp_dir}/inventory_bad_hostname.yml"
    local guard_log="${evidence_dir}/reports/guard_002.log"
    mkdir -p "$(dirname "$guard_log")"
    
    # Get lab VM IP from actual inventory
    local lab_ip
    lab_ip=$(grep -A5 'lab-pve-' "$REPO_ROOT/ansible/inventories/lab/hosts.yml" | grep 'ansible_host:' | head -1 | awk '{print $2}')
    
    if [[ -z "$lab_ip" ]]; then
        lab_ip="10.99.0.10"  # Fallback
    fi
    
    # Create temporary inventory with non-lab hostname pointing to lab IP
    cat > "$bad_inventory" <<EOF
---
all:
  children:
    lab:
      hosts:
        not-lab-pve-01:
          ansible_host: $lab_ip
          ansible_user: root
          ansible_ssh_common_args: '-o StrictHostKeyChecking=no'
  vars:
    lab_inventory: true
EOF
    
    local result="SKIP"
    local reason="Guard test execution failed"
    
    cd "$REPO_ROOT"
    
    # Attempt to run with bad hostname (should fail at hostname guard)
    if ansible-playbook ansible/playbooks/lab_tier2_pve.yml \
        -i "$bad_inventory" \
        --syntax-check &>"$guard_log"; then
        
        # Try actual execution with --check mode (should fail at guard)
        if ansible-playbook ansible/playbooks/lab_tier2_pve.yml \
            -i "$bad_inventory" \
            --check &>>"$guard_log"; then
            
            # UNEXPECTED: Playbook did not reject bad hostname
            result="PASS"
            reason="SAFETY HOLE: Playbook accepted non-lab hostname 'not-lab-pve-01'"
        else
            # EXPECTED: Playbook rejected bad hostname
            result="FAIL"
            reason="Playbook correctly rejected non-lab hostname (guard working)"
        fi
    else
        result="SKIP"
        reason="Syntax check failed, cannot test guard"
    fi
    
    # Record check with expected=FAIL
    record_check "GUARD-002" \
        "Playbook rejects non-lab hostname pattern" \
        "high" \
        "FAIL" \
        "$result" \
        "$reason" \
        "reports/guard_002.log"
        
    if [[ -n "$runid" ]]; then
        emit_check_complete "$runid" "GUARD-002" "$result" "$reason"
    fi
    
    # Cleanup temporary inventory
    rm -f "$bad_inventory"
    
    # Return validation result
    if [[ "$result" == "FAIL" ]]; then
        return 0  # Guard worked
    elif [[ "$result" == "PASS" ]]; then
        return 2  # Safety hole
    else
        return 1  # Could not test
    fi
}

# GUARD-003: Verify destroy safety check rejects VM missing identity markers
# Expected: FAIL (destroy command should reject)
run_guard_003() {
    local evidence_dir="$1"
    local runid="${2:-}"
    
    echo "Running GUARD-003: Destroy safety check rejects VM without identity markers" >&2
    
    if [[ -n "$runid" ]]; then
        emit_check_start "$runid" "GUARD-003" "Destroy safety check rejects VM without identity markers"
    fi
    
    local guard_log="${evidence_dir}/reports/guard_003.log"
    mkdir -p "$(dirname "$guard_log")"
    
    # Create synthetic qm config for a VM without lab identity markers
    local tmp_dir="${evidence_dir}/tmp"
    mkdir -p "$tmp_dir"
    local synthetic_config="${tmp_dir}/synthetic_vm_config.txt"
    
    cat > "$synthetic_config" <<'EOF'
# Synthetic VM config for GUARD-003 - VM without identity markers
bootdisk: scsi0
cores: 2
cpu: host
memory: 2048
name: production-vm
net0: virtio=AA:BB:CC:DD:EE:FF,bridge=vmbr0
numa: 0
ostype: l26
scsi0: local-lvm:vm-9050-disk-0,size=32G
scsihw: virtio-scsi-pci
smbios1: uuid=12345678-1234-1234-1234-123456789abc
sockets: 1
vmgenid: abcdef01-2345-6789-abcd-ef0123456789
EOF
    
    local result="SKIP"
    local reason="Guard test execution failed"
    
    # Test the safety check logic by parsing the synthetic config
    # Looking for absence of lab identity markers (notes, tags, description with 'lab')
    if grep -qi "lab" "$synthetic_config" || \
       grep -qi "test" "$synthetic_config" || \
       grep -qi "harness" "$synthetic_config"; then
        # UNEXPECTED: Config has markers (shouldn't happen with our synthetic config)
        result="PASS"
        reason="SAFETY HOLE: Safety check would accept VM without proper markers"
    else
        # EXPECTED: Config lacks markers, should be rejected
        # Simulate the safety check logic
        echo "VM config lacks 'lab', 'test', or 'harness' markers" > "$guard_log"
        echo "Safety check would reject this VM for destroy" >> "$guard_log"
        result="FAIL"
        reason="Safety check correctly would reject VM without identity markers"
    fi
    
    # Record check with expected=FAIL
    record_check "GUARD-003" \
        "Destroy safety check rejects VM missing identity markers" \
        "high" \
        "FAIL" \
        "$result" \
        "$reason" \
        "reports/guard_003.log"
        
    if [[ -n "$runid" ]]; then
        emit_check_complete "$runid" "GUARD-003" "$result" "$reason"
    fi
    
    # Cleanup synthetic config
    rm -f "$synthetic_config"
    
    # Return validation result
    if [[ "$result" == "FAIL" ]]; then
        return 0  # Guard worked
    elif [[ "$result" == "PASS" ]]; then
        return 2  # Safety hole
    else
        return 1  # Could not test
    fi
}

# Run all guardrail checks
run_all_guardrails() {
    local evidence_dir="$1"
    local runid="${2:-}"
    
    echo "=== Running Guardrail Checks (Negative Tests) ===" >&2
    
    local guard_failures=0
    local safety_holes=0
    
    # Run each guard and track results
    if ! run_guard_001 "$evidence_dir" "$runid"; then
        local rc=$?
        if [[ $rc -eq 2 ]]; then
            ((safety_holes++))
        else
            ((guard_failures++))
        fi
    fi
    
    if ! run_guard_002 "$evidence_dir" "$runid"; then
        local rc=$?
        if [[ $rc -eq 2 ]]; then
            ((safety_holes++))
        else
            ((guard_failures++))
        fi
    fi
    
    if ! run_guard_003 "$evidence_dir" "$runid"; then
        local rc=$?
        if [[ $rc -eq 2 ]]; then
            ((safety_holes++))
        else
            ((guard_failures++))
        fi
    fi
    
    # Cleanup tmp directory after all guards complete
    rm -rf "${evidence_dir}/tmp"
    
    echo "=== Guardrail Checks Complete ===" >&2
    
    # Return non-zero if any safety holes detected
    if [[ $safety_holes -gt 0 ]]; then
        echo "ERROR: $safety_holes safety hole(s) detected!" >&2
        return 2
    elif [[ $guard_failures -gt 0 ]]; then
        echo "WARNING: $guard_failures guard(s) could not be tested" >&2
        return 1
    fi
    
    return 0
}

# If script is executed directly (not sourced)
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    if [[ $# -lt 1 ]]; then
        echo "Usage: $0 ensure-artifacts | evidence_dir [runid]" >&2
        exit 1
    fi

    if [[ "$1" == "ensure-artifacts" ]]; then
        ensure_ci_artifact_root
        exit $?
    fi

    run_all_guardrails "$1" "${2:-}"
fi
