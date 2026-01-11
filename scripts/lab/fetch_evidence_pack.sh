#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  scripts/lab/fetch_evidence_pack.sh --environment <lab|prod> --run-id <RUN_ID> [--out-root <dir>]

Fetches an evidence pack from the Proxmox host and extracts it under:
  <out-root>/evidence/<environment>/<RUN_ID>/

Defaults (override via env vars):
  PROXMOX_HOST=pve
  SSH_USER=ci
  SSH_OPTS="-o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=no -o CheckHostIP=no -o UserKnownHostsFile=/dev/null -o GlobalKnownHostsFile=/dev/null"
  ARTIFACT_ROOT=/var/lib/homelab-proxmox/artifacts
  ARTIFACT_RUNS_DIR=service-deploy-runs

Options:
  --environment   Required. Used only for local extraction path grouping.
  --run-id        Required. Evidence pack directory name on PVE.
  --out-root      Optional. Defaults to repo root (.).
  -h, --help      Show this help.

Output:
  Prints the local evidence directory path to stdout.
USAGE
}

environment=""
run_id=""
out_root="."

while [[ $# -gt 0 ]]; do
  case "$1" in
    --environment)
      environment="${2:-}"; shift 2 ;;
    --run-id)
      run_id="${2:-}"; shift 2 ;;
    --out-root)
      out_root="${2:-}"; shift 2 ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      echo "ERROR: Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ -z "$environment" || -z "$run_id" ]]; then
  echo "ERROR: --environment and --run-id are required" >&2
  usage
  exit 2
fi

case "$environment" in
  lab|prod) ;;
  *)
    echo "ERROR: --environment must be 'lab' or 'prod'" >&2
    exit 2
    ;;
esac

PROXMOX_HOST="${PROXMOX_HOST:-pve}"
SSH_USER="${SSH_USER:-ci}"
SSH_OPTS="${SSH_OPTS:--o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=no -o CheckHostIP=no -o UserKnownHostsFile=/dev/null -o GlobalKnownHostsFile=/dev/null}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/var/lib/homelab-proxmox/artifacts}"
ARTIFACT_RUNS_DIR="${ARTIFACT_RUNS_DIR:-service-deploy-runs}"

ssh_target="${SSH_USER}@${PROXMOX_HOST}"
remote_runs_dir="${ARTIFACT_ROOT}/${ARTIFACT_RUNS_DIR}"
remote_tar="/tmp/service-deploy-${environment}-${run_id}.tgz"

local_out_root="${out_root%/}"
local_evidence_root="${local_out_root}/evidence/${environment}"
local_tar="${local_evidence_root}/service-deploy-${environment}-${run_id}.tgz"
local_evidence_dir="${local_evidence_root}/${run_id}"

mkdir -p "$local_evidence_root"

cleanup_remote() {
  ssh $SSH_OPTS "$ssh_target" "rm -f '$remote_tar'" >/dev/null 2>&1 || true
}
trap cleanup_remote EXIT

# Create a tarball on PVE and pull it down.
ssh $SSH_OPTS "$ssh_target" "set -euo pipefail; test -d '$remote_runs_dir/$run_id'; tar czf '$remote_tar' -C '$remote_runs_dir' '$run_id'"
scp $SSH_OPTS "${ssh_target}:${remote_tar}" "$local_tar" >/dev/null

# Extract into evidence/<env>/
tar xzf "$local_tar" -C "$local_evidence_root"

if [[ ! -d "$local_evidence_dir" ]]; then
  echo "ERROR: Evidence extract did not produce expected dir: $local_evidence_dir" >&2
  exit 1
fi

echo "$local_evidence_dir"
