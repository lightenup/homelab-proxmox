#!/usr/bin/env bash
set -euo pipefail

# List Hetzner Object Storage bucket contents
# Usage: ./hetzner_list.sh [path]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load environment variables if .env exists
if [ -f "${SCRIPT_DIR}/.env" ]; then
  # shellcheck disable=SC1091
  source "${SCRIPT_DIR}/.env"
fi

# Validate required variables
: "${RCLONE_REMOTE_NAME:?Environment variable RCLONE_REMOTE_NAME is required}"
: "${HETZNER_S3_BUCKET:?Environment variable HETZNER_S3_BUCKET is required}"

# Optional: Use rclone config from script directory if specified
if [ -n "${RCLONE_CONFIG_PATH:-}" ]; then
  export RCLONE_CONFIG="${RCLONE_CONFIG_PATH}"
fi

# Path within bucket (optional, defaults to root)
BUCKET_PATH="${1:-}"

echo "=== Hetzner Object Storage Bucket Listing ==="
echo "Remote: ${RCLONE_REMOTE_NAME}"
echo "Bucket: ${HETZNER_S3_BUCKET}"
echo "Path: ${BUCKET_PATH:-/}"
echo ""

# Execute rclone list
echo "Listing contents..."
rclone ls "${RCLONE_REMOTE_NAME}:${HETZNER_S3_BUCKET}/${BUCKET_PATH}" --max-depth 2

EXIT_CODE=$?
echo ""

if [ ${EXIT_CODE} -eq 0 ]; then
  echo "✓ List complete"
else
  echo "✗ List failed with exit code ${EXIT_CODE}"
  echo ""
  echo "Troubleshooting:"
  echo "  - Check credentials in .env match Bitwarden"
  echo "  - Verify endpoint: ${HETZNER_S3_ENDPOINT:-not set}"
  echo "  - Verify bucket exists: ${HETZNER_S3_BUCKET}"
  echo "  - Test network: curl -I ${HETZNER_S3_ENDPOINT:-https://nbg1.your-objectstorage.com}"
fi

exit ${EXIT_CODE}
