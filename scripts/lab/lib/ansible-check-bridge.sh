#!/usr/bin/env bash
# ansible-check-bridge.sh - Bridge between Ansible and harness check recording
#
# Usage from Ansible:
#   shell: /path/to/ansible-check-bridge.sh record_check CHECK_ID "Title" severity expected result "reason" [evidence_refs...]
#   environment:
#     EVIDENCE_DIR: /path/to/evidence/pack
#     RUNID: lab-20250101-120000

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/checks.sh"
source "${SCRIPT_DIR}/jsonl.sh"

# Usage: record_check_from_ansible CHECK_ID TITLE SEVERITY EXPECTED RESULT REASON [EVIDENCE_REFS...]
record_check_from_ansible() {
    local check_id="$1"
    local title="$2"
    local severity="$3"
    local expected="$4"
    local result="$5"
    local reason="$6"
    shift 6
    local evidence_refs=("$@")

    # Force source to ansible for this bridge
    export CURRENT_SOURCE="ansible"

    # Record check using harness library
    record_check "$check_id" "$title" "$severity" "$expected" "$result" "$reason" "${evidence_refs[@]}"

    # Emit JSONL event if RUNID is set
    if [[ -n "${RUNID:-}" ]]; then
        emit_check_complete "$RUNID" "$check_id" "$result" "$reason"
    fi

    echo "Recorded check: $check_id = $result"
}

# Usage: emit_check_start_from_ansible CHECK_ID TITLE
emit_check_start_from_ansible() {
    local check_id="$1"
    local title="$2"

    if [[ -n "${RUNID:-}" ]]; then
        emit_check_start "$RUNID" "$check_id" "$title"
    fi

    echo "Started check: $check_id"
}

# Main command dispatcher
case "${1:-}" in
    record_check)
        shift
        record_check_from_ansible "$@"
        ;;
    emit_start)
        shift
        emit_check_start_from_ansible "$@"
        ;;
    *)
        echo "Usage: $0 {record_check|emit_start} args..." >&2
        exit 1
        ;;
esac
