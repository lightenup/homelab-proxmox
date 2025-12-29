#!/bin/bash
set -e

# Get the directory of this script
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$(dirname "$(dirname "$DIR")")"

# Default arguments
PROFILE="lan"
ARGS=()

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --profile)
      PROFILE="$2"
      shift 2
      ;;
    *)
      ARGS+=("$1")
      shift
      ;;
  esac
done

# Ensure artifacts directory exists
mkdir -p "$REPO_ROOT/artifacts/healthcheck"

# Run the python script
echo "Running healthchecks (Profile: $PROFILE)..."
cd "$REPO_ROOT"
"$DIR/healthcheck.py" \
  --profile "$PROFILE" \
  --output-json "$REPO_ROOT/artifacts/healthcheck/latest.json" \
  "${ARGS[@]}"
