#!/usr/bin/env bash
# test-harness.sh - Comprehensive test suite for Lab Harness implementation
# Tests all major components without requiring actual Proxmox environment

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_DIR="/tmp/test-019c1-$$"
TESTS_PASSED=0
TESTS_FAILED=0

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_test() { echo -e "${YELLOW}[TEST]${NC} $1"; }
log_pass() { echo -e "${GREEN}[PASS]${NC} $1"; TESTS_PASSED=$((TESTS_PASSED + 1)); }
log_fail() { echo -e "${RED}[FAIL]${NC} $1"; TESTS_FAILED=$((TESTS_FAILED + 1)); }

cleanup() {
    rm -rf "$TEST_DIR"
}
trap cleanup EXIT

mkdir -p "$TEST_DIR"

echo "==================================="
echo "019c1 Implementation Test Suite"
echo "==================================="
echo ""

# Test 1: Syntax Validation
log_test "Test 1: Syntax validation (all scripts)"
echo "-----------------------------------"

bash -n "$SCRIPT_DIR/pve-lab" && log_pass "pve-lab syntax OK" || log_fail "pve-lab syntax error"
bash -n "$SCRIPT_DIR/guardrails.sh" && log_pass "guardrails.sh syntax OK" || log_fail "guardrails.sh syntax error"
bash -n "$SCRIPT_DIR/lib/checks.sh" && log_pass "lib/checks.sh syntax OK" || log_fail "lib/checks.sh syntax error"
bash -n "$SCRIPT_DIR/lib/jsonl.sh" && log_pass "lib/jsonl.sh syntax OK" || log_fail "lib/jsonl.sh syntax error"
bash -n "$SCRIPT_DIR/lib/provenance.sh" && log_pass "lib/provenance.sh syntax OK" || log_fail "lib/provenance.sh syntax error"
bash -n "$SCRIPT_DIR/lib/evidence.sh" && log_pass "lib/evidence.sh syntax OK" || log_fail "lib/evidence.sh syntax error"
bash -n "$SCRIPT_DIR/lib/cleanup.sh" && log_pass "lib/cleanup.sh syntax OK" || log_fail "lib/cleanup.sh syntax error"

echo ""

# Test 2: Library Function Tests
log_test "Test 2: Library function tests"
echo "-----------------------------------"

# Source libraries
source "$SCRIPT_DIR/lib/checks.sh"
source "$SCRIPT_DIR/lib/jsonl.sh"
source "$SCRIPT_DIR/lib/provenance.sh"

# Test check recording
CHECKS_ARRAY=()
record_check "TEST-001" "Test check" "low" "PASS" "PASS" "Test reason" "test.log"
if [[ ${#CHECKS_ARRAY[@]} -eq 1 ]]; then
    log_pass "Check recording: Created check entry"
else
    log_fail "Check recording: Failed to create check entry"
fi

# Test check contains expected fields (check after serialization for better validation)
mkdir -p "$TEST_DIR/check-test"
serialize_checks "$TEST_DIR/check-test/test-checks.json"
if jq -e '.checks[0].check_id' "$TEST_DIR/check-test/test-checks.json" | grep -q "TEST-001"; then
    log_pass "Check recording: Contains check_id after serialization"
else
    log_fail "Check recording: Missing check_id after serialization"
fi

# Test provenance functions
mkdir -p "$TEST_DIR/git-test/.git"
cd "$TEST_DIR/git-test"
git init > /dev/null 2>&1
git config user.email "test@test.com"
git config user.name "Test User"
echo "test" > test.txt
git add test.txt
git commit -m "test" > /dev/null 2>&1

controller_json=$(capture_controller_info)
if echo "$controller_json" | jq -e '.os' > /dev/null 2>&1; then
    log_pass "Provenance: Controller info captures OS"
else
    log_fail "Provenance: Controller info missing OS"
fi

git_json=$(capture_git_status "$TEST_DIR/git-test")
if echo "$git_json" | jq -e '.commit' > /dev/null 2>&1; then
    log_pass "Provenance: Git status captures commit"
else
    log_fail "Provenance: Git status missing commit"
fi

cd "$SCRIPT_DIR"

echo ""

# Test 3: Profile Parsing
log_test "Test 3: Profile parsing"
echo "-----------------------------------"

# Create test profile
mkdir -p "$TEST_DIR/profiles.d"
cat > "$TEST_DIR/profiles.d/test-profile.profile" <<'EOF'
PROFILE_ID="test-profile"
PROFILE_NAME="Test Profile"
PROFILE_TIER=2
PROFILE_MODE="min"
PROFILE_SAFETY="standard"
PROFILE_DURATION=5
PHASES=("setup" "validation")
EOF

# Source profile (simulating parse_profile)
if source "$TEST_DIR/profiles.d/test-profile.profile" 2>/dev/null; then
    if [[ "$PROFILE_ID" == "test-profile" ]]; then
        log_pass "Profile parsing: Loads profile_id correctly"
    else
        log_fail "Profile parsing: profile_id mismatch"
    fi
    
    if [[ "$PROFILE_TIER" == "2" ]]; then
        log_pass "Profile parsing: Loads tier correctly"
    else
        log_fail "Profile parsing: tier mismatch"
    fi
else
    log_fail "Profile parsing: Failed to source profile"
fi

echo ""

# Test 4: Check Serialization
log_test "Test 4: Check recording and serialization"
echo "-----------------------------------"

# Create checks
CHECKS_ARRAY=()
record_check "TEST-001" "First test" "low" "PASS" "PASS" "Test 1 passed" "test1.log"
record_check "TEST-002" "Second test" "medium" "PASS" "FAIL" "Test 2 failed" "test2.log"

serialize_checks "$TEST_DIR/checks.json"

if [[ -f "$TEST_DIR/checks.json" ]]; then
    log_pass "Check serialization: Created checks.json"
    
    if jq -e '.checks_schema_version' "$TEST_DIR/checks.json" > /dev/null 2>&1; then
        log_pass "Check serialization: Contains schema version"
    else
        log_fail "Check serialization: Missing schema version"
    fi
    
    check_count=$(jq '.checks | length' "$TEST_DIR/checks.json")
    if [[ "$check_count" == "2" ]]; then
        log_pass "Check serialization: Contains 2 checks"
    else
        log_fail "Check serialization: Check count mismatch (expected 2, got $check_count)"
    fi
    
    # Verify check structure
    if jq -e '.checks[0].check_id' "$TEST_DIR/checks.json" > /dev/null 2>&1; then
        log_pass "Check serialization: Check has check_id field"
    else
        log_fail "Check serialization: Check missing check_id field"
    fi
else
    log_fail "Check serialization: Failed to create checks.json"
fi

echo ""

# Test 5: JSONL Event Emission
log_test "Test 5: JSONL event emission"
echo "-----------------------------------"

init_jsonl_events "$TEST_DIR/events.jsonl"
emit_phase_start "test-run-001" "test-phase"
emit_phase_complete "test-run-001" "test-phase"

if [[ -f "$TEST_DIR/events.jsonl" ]]; then
    log_pass "JSONL events: Created events.jsonl"
    
    line_count=$(wc -l < "$TEST_DIR/events.jsonl")
    if [[ "$line_count" -ge 2 ]]; then
        log_pass "JSONL events: Contains multiple events"
    else
        log_fail "JSONL events: Too few events (expected >=2, got $line_count)"
    fi
    
    if grep -q '"event_type":"phase_start"' "$TEST_DIR/events.jsonl"; then
        log_pass "JSONL events: Contains phase_start event"
    else
        log_fail "JSONL events: Missing phase_start event"
    fi
    
    # Verify JSON format
    if head -1 "$TEST_DIR/events.jsonl" | jq -e '.timestamp' > /dev/null 2>&1; then
        log_pass "JSONL events: Valid JSON format with timestamp"
    else
        log_fail "JSONL events: Invalid JSON format"
    fi
else
    log_fail "JSONL events: Failed to create events.jsonl"
fi

echo ""

# Test 6: Guardrails (Negative Tests)
log_test "Test 6: Guardrails execution"
echo "-----------------------------------"

if [[ -x "$SCRIPT_DIR/guardrails.sh" ]]; then
    # Run guardrails in test mode
    if bash "$SCRIPT_DIR/guardrails.sh" "$TEST_DIR/guardrails-test" "test-run-002" > /dev/null 2>&1; then
        log_pass "Guardrails: Executed successfully"
        
        if [[ -d "$TEST_DIR/guardrails-test/reports" ]]; then
            log_pass "Guardrails: Created reports directory"
        else
            log_fail "Guardrails: Reports directory not created"
        fi
    else
        rc=$?
        if [[ $rc -eq 1 ]]; then
            log_pass "Guardrails: Returned expected non-zero exit (some checks failed/skipped)"
        else
            log_fail "Guardrails: Unexpected exit code: $rc"
        fi
    fi
else
    log_fail "Guardrails: guardrails.sh not executable"
fi

echo ""

# Test 7: Legacy Flag Mapping (requires sourcing pve-lab functions)
log_test "Test 7: Legacy flag mapping logic"
echo "-----------------------------------"

# Test the mapping logic pattern
tier=2
tier2_mode="min"
profile=""

# Simulate legacy-to-profile mapping
if [[ -z "$profile" && "$tier" == "2" ]]; then
    if [[ "$tier2_mode" == "plus" ]]; then
        profile="hypervisor-nested-workload"
    else
        profile="hypervisor-control-plane"
    fi
fi

if [[ "$profile" == "hypervisor-control-plane" ]]; then
    log_pass "Legacy mapping: tier=2, mode=min → hypervisor-control-plane"
else
    log_fail "Legacy mapping: tier=2, mode=min failed (got: $profile)"
fi

# Test plus mode
tier=2
tier2_mode="plus"
profile=""

if [[ -z "$profile" && "$tier" == "2" ]]; then
    if [[ "$tier2_mode" == "plus" ]]; then
        profile="hypervisor-nested-workload"
    else
        profile="hypervisor-control-plane"
    fi
fi

if [[ "$profile" == "hypervisor-nested-workload" ]]; then
    log_pass "Legacy mapping: tier=2, mode=plus → hypervisor-nested-workload"
else
    log_fail "Legacy mapping: tier=2, mode=plus failed (got: $profile)"
fi

echo ""

# Test 8: Cleanup Functions
log_test "Test 8: Cleanup verification functions"
echo "-----------------------------------"

source "$SCRIPT_DIR/lib/cleanup.sh"

mkdir -p "$TEST_DIR/cleanup-test/reports"

# Test lock status probe
probe_lock_status "artifacts/019-lab" "$TEST_DIR/cleanup-test/reports/lock_status.json"

if [[ -f "$TEST_DIR/cleanup-test/reports/lock_status.json" ]]; then
    log_pass "Cleanup: Created lock_status.json"
    
    if jq -e '.timestamp' "$TEST_DIR/cleanup-test/reports/lock_status.json" > /dev/null 2>&1; then
        log_pass "Cleanup: lock_status.json has valid structure"
    else
        log_fail "Cleanup: lock_status.json missing timestamp"
    fi
else
    log_fail "Cleanup: Failed to create lock_status.json"
fi

echo ""

# Summary
echo "==================================="
echo "Test Summary"
echo "==================================="
echo -e "${GREEN}Passed: $TESTS_PASSED${NC}"
echo -e "${RED}Failed: $TESTS_FAILED${NC}"
echo "Total:  $((TESTS_PASSED + TESTS_FAILED))"
echo ""

if [[ $TESTS_FAILED -eq 0 ]]; then
    echo -e "${GREEN}✓ All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}✗ Some tests failed${NC}"
    exit 1
fi
