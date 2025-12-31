#!/usr/bin/env bash
# check_record.sh - Ansible action plugin wrapper for check recording
#
# This script is meant to be called as a shell command from Ansible tasks
# It records check results to the harness CHECKS_ARRAY and emits JSONL events
#
# Environment variables (set by pve-lab):
#   HARNESS_LIB_DIR - Path to scripts/lab/lib/
#   EVIDENCE_DIR - Path to evidence pack directory
#   RUNID - Current run ID (e.g., lab-20250101-120000)
#
# Usage from Ansible:
#   - name: Record PVE-001 check
#     shell: "{{ lookup('env', 'HARNESS_LIB_DIR') }}/check_record.sh PVE-001 'Proxmox VE packages installed' high PASS PASS 'pve-manager and pve-kernel packages found'"
#     delegate_to: localhost
#     environment:
#       EVIDENCE_DIR: "{{ evidence_dir }}"
#       RUNID: "{{ runid }}"

set -euo pipefail

# Validation
if [[ -z "${HARNESS_LIB_DIR:-}" ]]; then
    echo "ERROR: HARNESS_LIB_DIR environment variable not set" >&2
    exit 1
fi

if [[ -z "${EVIDENCE_DIR:-}" ]]; then
    echo "ERROR: EVIDENCE_DIR environment variable not set" >&2
    exit 1
fi

if [[ -z "${RUNID:-}" ]]; then
    echo "ERROR: RUNID environment variable not set" >&2
    exit 1
fi

# Source harness libraries
source "${HARNESS_LIB_DIR}/checks.sh"
source "${HARNESS_LIB_DIR}/jsonl.sh"

# Parse arguments
if [[ $# -lt 6 ]]; then
    echo "Usage: $0 CHECK_ID TITLE SEVERITY EXPECTED RESULT REASON [EVIDENCE_REFS...]" >&2
    exit 1
fi

check_id="$1"
title="$2"
severity="$3"
expected="$4"
result="$5"
reason="$6"
shift 6
evidence_refs=("$@")

# Record check
record_check "$check_id" "$title" "$severity" "$expected" "$result" "$reason" "${evidence_refs[@]}"

# Emit completion event
emit_check_complete "$RUNID" "$check_id" "$result" "$reason"

# Output for Ansible (changed=false, JSON format)
cat <<EOF
{
  "changed": false,
  "check_id": "$check_id",
  "result": "$result",
  "msg": "Recorded check $check_id with result $result"
}
EOF
