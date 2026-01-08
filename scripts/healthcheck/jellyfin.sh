#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

PROFILE="lan"
OUTPUT_JSON=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile)
      PROFILE="${2:-lan}"
      shift 2
      ;;
    --output-json)
      OUTPUT_JSON="${2:-}"
      shift 2
      ;;
    -h|--help)
      echo "Usage: jellyfin.sh [--profile lan|tailscale] [--output-json <path>]"
      exit 0
      ;;
    *)
      echo "ERROR: Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

cd "$REPO_ROOT"

# Optional in-guest mount validation (used by the gated deploy orchestrator).
# If these env vars are not provided, we skip mount validation to preserve
# local/manual usage of the healthcheck wrapper.
if [[ -n "${HC_SSH_TARGET:-}" && -n "${HC_SSH_KEY_FILE:-}" ]]; then
  echo "[mount-check] validating /media/video is mounted read-only"

  if [[ ! -f "${HC_SSH_KEY_FILE}" ]]; then
    echo "[mount-check] FAIL: HC_SSH_KEY_FILE does not exist: ${HC_SSH_KEY_FILE}" >&2
    exit 2
  fi

  ssh_args=()
  if [[ -n "${HC_SSH_COMMON_ARGS:-}" ]]; then
    # shellcheck disable=SC2206
    ssh_args=( ${HC_SSH_COMMON_ARGS} )
  fi

  mount_opts="$(ssh -i "${HC_SSH_KEY_FILE}" "${ssh_args[@]}" "${HC_SSH_TARGET}" 'findmnt -n -o OPTIONS --target /media/video' 2>/dev/null || true)"
  if [[ -z "${mount_opts}" ]]; then
    echo "[mount-check] FAIL: /media/video is not mounted (findmnt returned empty)" >&2
    exit 3
  fi
  if [[ ",${mount_opts}," != *",ro,"* ]]; then
    echo "[mount-check] FAIL: /media/video is not read-only (options=${mount_opts})" >&2
    exit 4
  fi
  echo "[mount-check] PASS: /media/video mounted ro (options=${mount_opts})"
else
  echo "[mount-check] SKIP: missing HC_SSH_TARGET/HC_SSH_KEY_FILE"
fi

cmd=("$SCRIPT_DIR/healthcheck.py" --profile "$PROFILE" --host jellyfin --no-notify --json)
if [[ -n "$OUTPUT_JSON" ]]; then
  cmd+=(--output-json "$OUTPUT_JSON")
fi

"${cmd[@]}"
