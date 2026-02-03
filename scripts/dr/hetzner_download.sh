#!/usr/bin/env bash
set -euo pipefail

# Download backup from Hetzner Object Storage
# Usage: ./hetzner_download.sh <source_path> [target_dir]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check prerequisites
if ! command -v rclone &> /dev/null; then
  echo "Error: rclone is not installed"
  echo ""
  echo "Install rclone:"
  echo "  macOS:   brew install rclone"
  echo "  Linux:   sudo apt install rclone  # or dnf install rclone"
  echo "  Windows: choco install rclone"
  echo ""
  echo "See: https://rclone.org/install/"
  exit 1
fi

# Preserve command-line DOWNLOAD_DRY_RUN if already set
CLI_DRY_RUN="${DOWNLOAD_DRY_RUN:-}"

# Load environment variables if .env exists
if [ -f "${SCRIPT_DIR}/.env" ]; then
  # shellcheck disable=SC1091
  source "${SCRIPT_DIR}/.env"
fi

# Restore command-line override if it was set
if [ -n "${CLI_DRY_RUN}" ]; then
  DOWNLOAD_DRY_RUN="${CLI_DRY_RUN}"
fi

# Show usage if no arguments
if [ $# -eq 0 ]; then
  echo "Usage: $0 <source_path> [target_dir]"
  echo ""
  echo "Examples:"
  echo "  $0 \"DiskStation413j_1.hbk/_Syno_TaskConfig\" ~/dr-restore/test"
  echo "  DOWNLOAD_DRY_RUN=false $0 \"DiskStation413j_1.hbk/Config\" ~/dr-restore/metadata/"
  exit 1
fi

# Validate required variables
: "${RCLONE_REMOTE_NAME:?Environment variable RCLONE_REMOTE_NAME is required}"
: "${HETZNER_S3_BUCKET:?Environment variable HETZNER_S3_BUCKET is required}"
: "${DOWNLOAD_TARGET_DIR:?Environment variable DOWNLOAD_TARGET_DIR is required}"

# Arguments
SOURCE_PATH="${1}"
TARGET_DIR="${2:-${DOWNLOAD_TARGET_DIR}}"

# Dry-run mode (default true for safety)
DRY_RUN="${DOWNLOAD_DRY_RUN:-true}"

# Optional: Use rclone config from script directory if specified
if [ -n "${RCLONE_CONFIG_PATH:-}" ]; then
  export RCLONE_CONFIG="${RCLONE_CONFIG_PATH}"
fi

# Create target directory
mkdir -p "${TARGET_DIR}"

echo "=== Hetzner Object Storage Download ==="
echo "Remote: ${RCLONE_REMOTE_NAME}"
echo "Bucket: ${HETZNER_S3_BUCKET}"
echo "Source: ${SOURCE_PATH}"
echo "Target: ${TARGET_DIR}"
echo "Dry-run: ${DRY_RUN}"
echo ""

# Build rclone command
# IMPORTANT: Using copyto to preserve full directory structure
# For Pool bucket downloads, we need nested subdirectories intact
# Example: "Pool/0/1" should create target/Pool/0/1/, not target/1/

# Determine if we need to preserve the full path structure
# For Pool downloads, preserve structure; otherwise flatten as before
if [[ "${SOURCE_PATH}" == *"Pool/"* ]]; then
  # Pool downloads: preserve full nested structure
  # Use the backup root as target and let rclone recreate the path
  ACTUAL_TARGET="${TARGET_DIR%DiskStation413j_1.hbk*}DiskStation413j_1.hbk"
  RCLONE_ARGS=(
    "copy"
    "${RCLONE_REMOTE_NAME}:${HETZNER_S3_BUCKET}/${SOURCE_PATH}"
    "${ACTUAL_TARGET}/${SOURCE_PATH}"
    "--progress"
    "--stats" "10s"
    "--transfers" "4"
    "--checkers" "8"
    "--log-file" "rclone.log"
    "--log-level" "INFO"
  )
  echo "NOTE: Preserving directory structure for Pool download"
  echo "      Target will be: ${ACTUAL_TARGET}/${SOURCE_PATH}/"
  echo ""
else
  # Non-Pool downloads: use target directory directly (original behavior)
  RCLONE_ARGS=(
    "copy"
    "${RCLONE_REMOTE_NAME}:${HETZNER_S3_BUCKET}/${SOURCE_PATH}"
    "${TARGET_DIR}"
    "--progress"
    "--stats" "10s"
    "--transfers" "4"
    "--checkers" "8"
    "--log-file" "rclone.log"
    "--log-level" "INFO"
  )
fi

# Add dry-run flag if enabled
if [ "${DRY_RUN}" = "true" ]; then
  RCLONE_ARGS+=("--dry-run")
  echo "⚠️  DRY RUN MODE: No files will be downloaded"
  echo "   Set DOWNLOAD_DRY_RUN=false to execute actual download"
  echo ""
fi

# Execute download
echo "Executing: rclone ${RCLONE_ARGS[*]}"
echo ""

START_TIME=$(date +%s)
rclone "${RCLONE_ARGS[@]}"
EXIT_CODE=$?
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

echo ""
if [ ${EXIT_CODE} -eq 0 ]; then
  if [ "${DRY_RUN}" = "true" ]; then
    echo "✓ Dry-run complete (duration: ${DURATION}s)"
    echo ""
    echo "To execute actual download, run:"
    echo "  DOWNLOAD_DRY_RUN=false $0 \"${SOURCE_PATH}\" \"${TARGET_DIR}\""
  else
    echo "✓ Download complete (duration: ${DURATION}s)"
    echo "Files saved to: ${TARGET_DIR}"
    echo ""
    echo "Verify download:"
    echo "  ls -lh ${TARGET_DIR}"
  fi
else
  echo "✗ Download failed with exit code ${EXIT_CODE}"
  echo ""
  echo "Troubleshooting:"
  echo "  - Check network connection"
  echo "  - Verify credentials in .env"
  echo "  - Ensure sufficient disk space: df -h ${TARGET_DIR}"
  echo "  - Check source path exists: ./hetzner_list.sh ${SOURCE_PATH}"
fi

exit ${EXIT_CODE}
