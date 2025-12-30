#!/bin/bash
set -e

# Get the directory of this script
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$(dirname "$(dirname "$DIR")")"

# Default arguments
PROFILE="lan"
INVENTORY=""
ARGS=()

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --profile)
      PROFILE="$2"
      shift 2
      ;;
    --inventory)
      INVENTORY="$2"
      shift 2
      ;;
    *)
      ARGS+=("$1")
      shift
      ;;
  esac
done

# Ensure artifacts directory exists
HISTORY_DIR="$REPO_ROOT/artifacts/healthcheck/history"
mkdir -p "$HISTORY_DIR"

# Source .env if present
if [ -f "$DIR/.env" ]; then
  source "$DIR/.env"
fi

# Timestamp for history
TS=$(date +%Y%m%d-%H%M%S)
OUTPUT_FILE="$HISTORY_DIR/${TS}.json"

# Build command args
CMD_ARGS=("--profile" "$PROFILE" "--output-json" "$OUTPUT_FILE")
if [ -n "$INVENTORY" ]; then
  CMD_ARGS+=("--inventory" "$INVENTORY")
fi

# Run the python script
echo "Running healthchecks (Profile: $PROFILE)..."
cd "$REPO_ROOT"
set +e
"$DIR/healthcheck.py" "${CMD_ARGS[@]}" "${ARGS[@]}"
EXIT_CODE=$?
set -e

# Update latest link
ln -sf "$OUTPUT_FILE" "$HISTORY_DIR/latest.json"

# Rotate history (keep last 50)
cd "$HISTORY_DIR"
ls -t *.json | grep -v "latest.json" | tail -n +51 | xargs -I {} rm -- {} 2>/dev/null || true

exit $EXIT_CODE
