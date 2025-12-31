#!/usr/bin/env bash
# lib/checks.sh - Check recording and management functions
# Part of 019c1-semantic-safety-closure

set -euo pipefail

# Global array to accumulate checks
declare -a CHECKS_ARRAY=()

# Global array to track seen check IDs (for deduplication)
declare -a SEEN_CHECK_IDS=()

# Check recorder function - records a check result
# Usage: record_check check_id title severity expected result reason [evidence_refs...]
record_check() {
    local check_id="$1"
    local title="$2"
    local severity="$3"
    local expected="$4"
    local result="$5"
    local reason="$6"
    shift 6
    local evidence_refs=("$@")

    # DEDUP LOGIC: Check for duplicates (unless it's the dedup check itself)
    if [[ "$check_id" != "SUITE-DEDUP-001" ]]; then
        local is_duplicate=false
        for seen_id in "${SEEN_CHECK_IDS[@]:-}"; do
            if [[ "$seen_id" == "$check_id" ]]; then
                is_duplicate=true
                break
            fi
        done

        if [[ "$is_duplicate" == "true" ]]; then
            # Check if we already emitted the dedup error
            local dedup_emitted=false
            for s in "${SEEN_CHECK_IDS[@]:-}"; do
                if [[ "$s" == "SUITE-DEDUP-001" ]]; then
                    dedup_emitted=true
                    break
                fi
            done

            if [[ "$dedup_emitted" == "false" ]]; then
                # Recursive call to record the blocker
                record_check "SUITE-DEDUP-001" \
                    "Duplicate Check ID Detected" \
                    "blocker" \
                    "PASS" \
                    "FAIL" \
                    "Check ID '$check_id' was emitted multiple times. First collision detected." \
                    "collision_id:$check_id"
            fi
            # Do not record the duplicate check
            return 0
        fi
        # Mark as seen
        SEEN_CHECK_IDS+=("$check_id")
    fi
    
    local timestamp
    timestamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    
    # Get context from environment or defaults
    local source="${CURRENT_SOURCE:-harness}"
    local phase="${CURRENT_PHASE:-unknown}"

    # Build JSON object for this check
    local check_json
    check_json=$(cat <<EOF
{
  "check_id": "$check_id",
  "title": "$title",
  "severity": "$severity",
  "source": "$source",
  "phase": "$phase",
  "expected": "$expected",
  "result": "$result",
  "reason": "$reason",
  "evidence_refs": $(printf '%s\n' "${evidence_refs[@]:-}" | jq -R . | jq -s .),
  "timestamp": "$timestamp"
}
EOF
)
    
    # Append to checks array
    CHECKS_ARRAY+=("$check_json")
}

# Serialize checks to checks.json
# Usage: serialize_checks output_file
serialize_checks() {
    local output_file="$1"
    local checks_schema_version="1.0.0"
    
    # Build checks array JSON
    local checks_json="["
    local first=true
    for check in "${CHECKS_ARRAY[@]}"; do
        if [ "$first" = true ]; then
            first=false
        else
            checks_json+=","
        fi
        checks_json+="$check"
    done
    checks_json+="]"
    
    # Build final document with schema version
    cat > "$output_file" <<EOF
{
  "checks_schema_version": "$checks_schema_version",
  "checks": $checks_json
}
EOF
}

# Profile loader function - sources a .profile file and validates required fields
# Usage: load_profile profile_name
load_profile() {
    local profile_name="$1"
    local profile_file="${PROFILES_DIR:-scripts/lab/profiles.d}/${profile_name}.profile"
    
    if [[ ! -f "$profile_file" ]]; then
        echo "ERROR: Profile file not found: $profile_file" >&2
        return 1
    fi
    
    # Source the profile file
    # shellcheck source=/dev/null
    source "$profile_file"
    
    # Validate required fields
    local required_fields=(
        "PROFILE_ID"
        "DISPLAY_NAME"
        "SAFETY_LEVEL"
        "TIER"
        "MODE"
        "EXPECTED_DURATION_MINUTES"
    )
    
    for field in "${required_fields[@]}"; do
        if [[ -z "${!field:-}" ]]; then
            echo "ERROR: Profile $profile_name missing required field: $field" >&2
            return 1
        fi
    done
    
    return 0
}

# Validate negative test results
# Usage: validate_negative_test check_id expected result
validate_negative_test() {
    local check_id="$1"
    local expected="$2"
    local result="$3"
    
    # If expected FAIL but got PASS, this is a safety hole (ERROR condition)
    if [[ "$expected" == "FAIL" && "$result" == "PASS" ]]; then
        echo "ERROR: Negative test $check_id failed - expected FAIL but got PASS (safety hole detected)" >&2
        return 1
    fi
    
    # If expected FAIL and got FAIL, this is correct (negative test passed)
    if [[ "$expected" == "FAIL" && "$result" == "FAIL" ]]; then
        return 0
    fi
    
    # Normal validation for non-negative tests
    if [[ "$expected" != "$result" ]]; then
        echo "WARNING: Check $check_id mismatch - expected $expected but got $result" >&2
    fi
    
    return 0
}
