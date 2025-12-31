#!/usr/bin/env bash
# scripts/lab/guardrails.sh - Negative test harness for safety validation
# Part of 019c1-semantic-safety-closure

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="${SCRIPT_DIR}/lib"

# Source required libraries
# shellcheck source=lib/checks.sh
source "${LIB_DIR}/checks.sh"

# GUARD-001: Verify tier2 playbook rejects execution without lab_inventory=true
# Expected: FAIL (playbook should reject)
run_guard_001() {
    local evidence_dir="$1"
    
    echo "Running GUARD-001: Tier2 playbook rejects without lab_inventory=true"
    
    # Attempt to run playbook with lab_inventory=false
    local result="PASS"
    local reason="Guard test not yet implemented"
    
    # TODO: Implementation in Phase 4 (US2)
    # This should execute:
    # ansible-playbook ansible/playbooks/lab_tier2_pve.yml -e lab_inventory=false
    # Expected: playbook should abort with assertion failure
    
    # Record check with expected=FAIL
    record_check "GUARD-001" \
        "Tier2 playbook rejects execution without lab_inventory=true" \
        "high" \
        "FAIL" \
        "$result" \
        "$reason" \
        "reports/guard_001.log"
}

# GUARD-002: Verify playbook rejects non-lab hostname pattern
# Expected: FAIL (playbook should reject)
run_guard_002() {
    local evidence_dir="$1"
    local runid="$2"
    
    echo "Running GUARD-002: Playbook rejects non-lab hostname pattern"
    
    # Create temporary inventory with bad hostname
    local tmp_dir="${evidence_dir}/tmp"
    mkdir -p "$tmp_dir"
    
    local bad_inventory="${tmp_dir}/inventory_bad_hostname.yml"
    cat > "$bad_inventory" <<'EOF'
all:
  hosts:
    not-lab-pve-01:
      ansible_host: 192.168.1.100
      ansible_user: root
EOF
    
    local result="PASS"
    local reason="Guard test not yet implemented"
    
    # TODO: Implementation in Phase 4 (US2)
    # This should execute:
    # ansible-playbook ansible/playbooks/lab_tier2_pve.yml -i "$bad_inventory"
    # Expected: playbook should abort with hostname pattern guard failure
    
    # Record check with expected=FAIL
    record_check "GUARD-002" \
        "Playbook rejects non-lab hostname pattern" \
        "high" \
        "FAIL" \
        "$result" \
        "$reason" \
        "tmp/inventory_bad_hostname.yml" \
        "reports/guard_002.log"
    
    # Cleanup tmp directory (ephemeral)
    rm -rf "$tmp_dir"
}

# GUARD-003: Verify destroy safety check rejects VM missing identity markers
# Expected: FAIL (destroy command should reject)
run_guard_003() {
    local evidence_dir="$1"
    
    echo "Running GUARD-003: Destroy safety check rejects VM without identity markers"
    
    local result="PASS"
    local reason="Guard test not yet implemented"
    
    # TODO: Implementation in Phase 4 (US2)
    # This should use dry-run validation or synthetic qm config
    # Expected: safety check should reject VM missing lab markers
    
    # Record check with expected=FAIL
    record_check "GUARD-003" \
        "Destroy safety check rejects VM missing identity markers" \
        "high" \
        "FAIL" \
        "$result" \
        "$reason" \
        "reports/guard_003.log"
}

# Run all guardrail checks
run_all_guardrails() {
    local evidence_dir="$1"
    local runid="$2"
    
    echo "=== Running Guardrail Checks (Negative Tests) ==="
    
    run_guard_001 "$evidence_dir"
    run_guard_002 "$evidence_dir" "$runid"
    run_guard_003 "$evidence_dir"
    
    echo "=== Guardrail Checks Complete ==="
}

# If script is executed directly (not sourced)
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    if [[ $# -lt 2 ]]; then
        echo "Usage: $0 evidence_dir runid" >&2
        exit 1
    fi
    
    run_all_guardrails "$1" "$2"
fi
