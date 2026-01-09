#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
FIXTURES_DIR="${SCRIPT_DIR}/fixtures"
CATALOG_FILE="${SCRIPT_DIR}/checks.d/catalog.json"
SERVICE_DEPLOY_PROFILE_JSON="${SCRIPT_DIR}/profiles.d/service-deploy.json"
SNAPSHOT_SCHEMA="${SCRIPT_DIR}/contracts/evidence-lab-snapshot.schema.json"
TFVARS_SCHEMA="${SCRIPT_DIR}/contracts/evidence-tfvars-proof.schema.json"

echo "=== CI Verification Gate ==="

# 1. Lint Catalog
echo "Linting Catalog: $CATALOG_FILE"
if ! python3 -c "import json; json.load(open('$CATALOG_FILE'))"; then
    echo "FAIL: Catalog JSON is invalid"
    exit 1
fi
echo "PASS: Catalog JSON is valid"

# 1b. Lint Evidence Profile (service-deploy)
echo "Linting Evidence Profile: $SERVICE_DEPLOY_PROFILE_JSON"
if [[ ! -f "$SERVICE_DEPLOY_PROFILE_JSON" ]]; then
    echo "FAIL: Missing evidence profile: $SERVICE_DEPLOY_PROFILE_JSON"
    exit 1
fi
if ! python3 -c "import json; json.load(open('$SERVICE_DEPLOY_PROFILE_JSON'))"; then
    echo "FAIL: Evidence profile JSON is invalid"
    exit 1
fi
echo "PASS: Evidence profile JSON is valid"

# 1c. Ensure schemas exist
for schema in "$SNAPSHOT_SCHEMA" "$TFVARS_SCHEMA"; do
    if [[ ! -f "$schema" ]]; then
        echo "FAIL: Missing schema: $schema"
        exit 1
    fi
done
echo "PASS: Required schemas exist"

# 2. Run Fixtures
echo "Running Fixtures..."
FAILED=0

run_test() {
    local fixture="$1"
    local name=$(basename "$fixture")
    local expected_file="$fixture/expected.txt"
    
    if [[ ! -f "$expected_file" ]]; then
        # echo "WARN: Skipping $name (no expected.txt)"
        return
    fi
    
    local expected
    expected=$(cat "$expected_file" | tr -d '[:space:]')
    
    echo -n "Testing $name... "

    local tmp_root
    tmp_root="$(mktemp -d -t ci-verify-fixture.XXXXXX)"
    trap 'rm -rf "$tmp_root"' RETURN

    local tmp_fixture="$tmp_root/$name"
    cp -R "$fixture" "$tmp_fixture"
    
    set +e
    python3 "${SCRIPT_DIR}/verify_evidence.py" "$tmp_fixture" >/dev/null 2>&1
    local rc=$?
    set -e
    
    local result="FAIL"
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
}

# Scan fixtures dir
for fixture in "$FIXTURES_DIR"/*; do
    if [[ -d "$fixture" ]]; then
        run_test "$fixture"
    fi
done

# Scan evidence-packs dir (explicit sort for deterministic order)
if [[ -d "$FIXTURES_DIR/evidence-packs" ]]; then
    for fixture in $(ls -1 "$FIXTURES_DIR/evidence-packs"); do
        if [[ -d "$FIXTURES_DIR/evidence-packs/$fixture" ]]; then
            run_test "$FIXTURES_DIR/evidence-packs/$fixture"
        fi
    done
fi

if [[ $FAILED -eq 1 ]]; then
    echo "CI Verification Failed"
    exit 1
else
    echo "CI Verification Passed"
    exit 0
fi
