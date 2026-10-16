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
      echo "Usage: ntfy.sh [--profile lan|tailscale] [--output-json <path>]"
      exit 0
      ;;
    *)
      echo "ERROR: Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

cd "$REPO_ROOT"

cmd=("$SCRIPT_DIR/healthcheck.py" --profile "$PROFILE" --host ntfy --no-notify --json)
if [[ -n "$OUTPUT_JSON" ]]; then
  cmd+=(--output-json "$OUTPUT_JSON")
fi

"${cmd[@]}"
