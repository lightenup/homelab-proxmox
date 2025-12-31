#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
FIXTURES_DIR="${SCRIPT_DIR}/fixtures"
CATALOG_FILE="${SCRIPT_DIR}/checks.d/catalog.json"

echo "=== CI Verification Gate ==="

# 1. Lint Catalog
echo "Linting Catalog: $CATALOG_FILE"
if ! python3 -c "import json; json.load(open('$CATALOG_FILE'))"; then
    echo "FAIL: Catalog JSON is invalid"
    exit 1
fi
echo "PASS: Catalog JSON is valid"

# 2. Run Fixtures
echo "Running Fixtures..."
FAILED=0

for fixture in "$FIXTURES_DIR"/*; do
    if [[ ! -d "$fixture" ]]; then
        continue
    fi
    
    name=$(basename "$fixture")
    expected_file="$fixture/expected.txt"
    
    if [[ ! -f "$expected_file" ]]; then
        echo "WARN: Skipping $name (no expected.txt)"
        continue
    fi
    
    expected=$(cat "$expected_file" | tr -d '[:space:]')
    
    echo -n "Testing $name... "
    
    set +e
    python3 "${SCRIPT_DIR}/verify_evidence.py" "$fixture" >/dev/null 2>&1
    rc=$?
    set -e
    
    result="FAIL"
    if [[ $rc -eq 0 ]]; then
        result="PASS"
    fi
    
    if [[ "$result" == "$expected" ]]; then
        if [[ "$expected" == "PASS" ]]; then
            echo "OK (Valid pack accepted)"
        else
            echo "OK (Invalid pack rejected)"
        fi
    else
        echo "FAILED (Expected $expected, got $result)"
        FAILED=1
    fi
done

if [[ $FAILED -eq 1 ]]; then
    echo "CI Verification Failed"
    exit 1
else
    echo "CI Verification Passed"
    exit 0
fi
