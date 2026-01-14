#!/usr/bin/env bash
set -euo pipefail

cmd="${1:-}"
shift || true

ENVIRONMENT=""
SERVICE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --environment) ENVIRONMENT="${2:-}"; shift 2;;
    --service) SERVICE="${2:-}"; shift 2;;
    *) shift;;
  esac
done

: "${ARTIFACT_ROOT:?ARTIFACT_ROOT is required}"
: "${ARTIFACT_RUNS_DIR:?ARTIFACT_RUNS_DIR is required}"

if [[ -z "$ENVIRONMENT" || -z "$SERVICE" ]]; then
  echo "missing required args" >&2
  exit 2
fi

run_id="${ENVIRONMENT}-${SERVICE}-${cmd}-TESTRUN"
run_dir="${ARTIFACT_ROOT}/${ARTIFACT_RUNS_DIR}/${run_id}"
mkdir -p "${run_dir}/reports/plan" "${run_dir}/logs"

# Minimal evidence files used by existing repo validators.
cat >"${run_dir}/evidence_manifest.json" <<EOF
{"profile_id":"service-deploy","schema_version":"1.0.0"}
EOF

cat >"${run_dir}/provenance.json" <<EOF
{"environment":"${ENVIRONMENT}","service":"${SERVICE}","action":"${cmd}"}
EOF

# Provide a minimal plan-ui-summary.json so later summary tasks have something to consume.
cat >"${run_dir}/plan-ui-summary.json" <<EOF
{"schema_version":"1.0.0","run_id":"${run_id}","environment":"${ENVIRONMENT}","service":"${SERVICE}","destructive":false,"confirmation_token_required":null,"counts":{"create":0,"update":0,"replace":0,"destroy":0},"resources_total":0,"resources_shown":0,"truncated":false,"resources":[],"evidence":{"pve_runs_dir":"${ARTIFACT_ROOT}/${ARTIFACT_RUNS_DIR}","pve_run_id_dir":"${run_dir}"}}
EOF

cat >"${run_dir}/blast-radius.json" <<EOF
{"destructive":false,"counts":{"create":0,"update":0,"replace":0,"destroy":0}}
EOF

cat >"${run_dir}/reports/plan/plan.json" <<EOF
{"resource_changes":[]}
EOF

echo "fake ${cmd} ok"
