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

verify_blast_radius_consistency() {
    local pack_path="$1"

    if [[ ! -f "$pack_path/blast-radius.json" || ! -f "$pack_path/reports/plan/plan.json" ]]; then
        return 0
    fi

    python3 - "$pack_path" <<'PY'
import json
import os
import sys

pack = sys.argv[1]
plan_path = os.path.join(pack, "reports", "plan", "plan.json")
blast_path = os.path.join(pack, "blast-radius.json")

with open(plan_path, "r", encoding="utf-8") as f:
    plan = json.load(f)

with open(blast_path, "r", encoding="utf-8") as f:
    blast = json.load(f)

resource_changes = plan.get("resource_changes") or []

def actions_of(rc):
    change = rc.get("change") or {}
    actions = change.get("actions")
    return actions if isinstance(actions, list) else []

create = 0
update = 0
replace = 0
destroy = 0

for rc in resource_changes:
    acts = actions_of(rc)
    if acts == ["create"]:
        create += 1
    elif acts == ["update"]:
        update += 1
    elif acts == ["delete"]:
        destroy += 1
    else:
        if "create" in acts and "delete" in acts:
            replace += 1

expected_counts = {
    "create": create,
    "update": update,
    "replace": replace,
    "destroy": destroy,
}
expected_destructive = (replace + destroy) > 0

blast_counts = blast.get("counts")
if not isinstance(blast_counts, dict):
    # Legacy shape: counts are top-level keys.
    blast_counts = {}
    for k in ("create", "update", "replace", "destroy"):
        v = blast.get(k)
        if isinstance(v, int):
            blast_counts[k] = v
blast_destructive = bool(blast.get("destructive"))

errors = []
for k, v in expected_counts.items():
    # Only compare counts if blast-radius.json provides that key.
    if k in blast_counts:
        bv = blast_counts.get(k)
        if bv != v:
            errors.append(f"counts.{k} expected={v} actual={bv}")

if blast_destructive != expected_destructive:
    errors.append(f"destructive expected={expected_destructive} actual={blast_destructive}")

if errors:
    msg = "Blast radius mismatch: " + "; ".join(errors)
    print(msg, file=sys.stderr)
    raise SystemExit(2)
PY
}

# If invoked with an explicit evidence pack path, verify just that pack.
if [[ $# -ge 1 ]]; then
    PACK_PATH="$1"

    if [[ ! -d "$PACK_PATH" ]]; then
        echo "FAIL: Evidence pack path is not a directory: $PACK_PATH" >&2
        exit 2
    fi

    echo "Verifying evidence pack: $PACK_PATH"

    if ! python3 "${SCRIPT_DIR}/verify_evidence.py" "$PACK_PATH"; then
        echo "FAIL: Evidence pack verification failed" >&2
        exit 1
    fi

    if [[ -f "$PACK_PATH/plan-ui-summary.json" ]]; then
        if ! python3 "${SCRIPT_DIR}/validate_plan_ui_summary.py" "$PACK_PATH/plan-ui-summary.json"; then
            echo "FAIL: plan-ui-summary.json is invalid" >&2
            exit 1
        fi
    fi

    if ! verify_blast_radius_consistency "$PACK_PATH"; then
        echo "FAIL: blast-radius.json is inconsistent with reports/plan/plan.json" >&2
        exit 1
    fi

    echo "PASS: Evidence pack verified"
    exit 0
fi

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

    # Optional: validate plan UI summary JSON if present.
    if [[ $rc -eq 0 && -f "$tmp_fixture/plan-ui-summary.json" ]]; then
        set +e
        python3 "${SCRIPT_DIR}/validate_plan_ui_summary.py" "$tmp_fixture/plan-ui-summary.json" >/dev/null 2>&1
        local summary_rc=$?
        set -e
        if [[ $summary_rc -ne 0 ]]; then
            rc=1
        fi
    fi

    # Optional: validate blast-radius.json is consistent with plan.json when present.
    if [[ $rc -eq 0 ]]; then
        set +e
        verify_blast_radius_consistency "$tmp_fixture" >/dev/null 2>&1
        local br_rc=$?
        set -e
        if [[ $br_rc -ne 0 ]]; then
            rc=1
        fi
    fi

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
