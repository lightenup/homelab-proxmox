#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  scripts/lifecycle/terraform_plan_apply.sh plan --environment <lab|prod> --service <slug> [--run-id-file <path>]
  scripts/lifecycle/terraform_plan_apply.sh apply --environment <lab|prod> --service <slug> --from-plan-run-id <RUN_ID> [--confirm <string>] [--run-id-file <path>]

Notes:
  - Intended to run on the Proxmox host where scripts/lab/pve-service-deploy is available.
  - Applies use the same plan by passing --from-plan-run-id.
  - Evidence packs are written under ${ARTIFACT_ROOT:-/var/lib/homelab-proxmox/artifacts}/${ARTIFACT_RUNS_DIR:-service-deploy-runs}.
USAGE
}

if [[ $# -lt 1 ]]; then
  usage
  exit 2
fi

action="$1"
shift

environment=""
service=""
run_id_file=""
confirm=""
from_plan_run_id=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --environment)
      environment="${2:-}"; shift 2 ;;
    --service)
      service="${2:-}"; shift 2 ;;
    --run-id-file)
      run_id_file="${2:-}"; shift 2 ;;
    --confirm)
      confirm="${2:-}"; shift 2 ;;
    --from-plan-run-id)
      from_plan_run_id="${2:-}"; shift 2 ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      echo "ERROR: Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ -z "${environment}" || -z "${service}" ]]; then
  echo "ERROR: --environment and --service are required." >&2
  usage
  exit 2
fi

case "${environment}" in
  lab|prod) ;;
  *) echo "ERROR: --environment must be 'lab' or 'prod'" >&2; exit 2 ;;
 esac

if ! [[ "${service}" =~ ^[a-z0-9][a-z0-9_-]{0,62}$ ]]; then
  echo "ERROR: Invalid service name '${service}'" >&2
  exit 2
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/../.." && pwd)"

deploy_script="${repo_root}/scripts/lab/pve-service-deploy"
if [[ ! -x "${deploy_script}" ]]; then
  echo "ERROR: Missing executable ${deploy_script}" >&2
  exit 1
fi

run_cmd=("${deploy_script}" "${action}" "--environment" "${environment}" "--service" "${service}")

if [[ "${action}" == "apply" ]]; then
  if [[ -z "${from_plan_run_id}" ]]; then
    echo "ERROR: --from-plan-run-id is required for apply to reuse the plan" >&2
    exit 2
  fi
  run_cmd+=("--from-plan-run-id" "${from_plan_run_id}")
  if [[ -n "${confirm}" ]]; then
    run_cmd+=("--confirm" "${confirm}")
  fi
fi

"${run_cmd[@]}"

artifact_root="${ARTIFACT_ROOT:-/var/lib/homelab-proxmox/artifacts}"
artifact_runs_dir="${ARTIFACT_RUNS_DIR:-service-deploy-runs}"

if [[ ! -d "${artifact_root}/${artifact_runs_dir}" ]]; then
  echo "ERROR: Expected artifact root missing: ${artifact_root}/${artifact_runs_dir}" >&2
  exit 1
fi

run_id="$(ls -1td "${artifact_root}/${artifact_runs_dir}/${environment}-${service}-"*/ 2>/dev/null | head -1 | sed 's:/*$::')"
run_id="${run_id##*/}"

if [[ -z "${run_id}" ]]; then
  echo "ERROR: Unable to detect run_id for ${environment}-${service}" >&2
  exit 1
fi

if [[ -n "${run_id_file}" ]]; then
  mkdir -p "$(dirname "${run_id_file}")"
  echo "${run_id}" >"${run_id_file}"
else
  echo "${run_id}"
fi
