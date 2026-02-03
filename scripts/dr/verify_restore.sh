#!/usr/bin/env bash
set -euo pipefail

# Verify restored backup integrity
# Usage: ./verify_restore.sh <restore_path>

if [ $# -eq 0 ]; then
  echo "Usage: $0 <restore_path>"
  echo ""
  echo "Example:"
  echo "  $0 ~/dr-restore/extracted"
  exit 1
fi

RESTORE_PATH="${1}"

if [ ! -d "${RESTORE_PATH}" ]; then
  echo "Error: Restore path does not exist: ${RESTORE_PATH}"
  exit 1
fi

echo "=== Backup Restore Verification ==="
echo "Path: ${RESTORE_PATH}"
echo ""
echo "Note: macOS can verify directly from the NAS mount (e.g. /Volumes/nas/homelab_dr_test/...)."
echo ""

# Count total files
echo "[1/4] Counting files..."
FILE_COUNT=$(find "${RESTORE_PATH}" -type f | wc -l | tr -d ' ')
echo "      Total files: ${FILE_COUNT}"

# Count photo files specifically
PHOTO_COUNT=$(find "${RESTORE_PATH}" -type f \( \
  -iname "*.jpg" -o \
  -iname "*.jpeg" -o \
  -iname "*.png" -o \
  -iname "*.heic" -o \
  -iname "*.heif" -o \
  -iname "*.raw" -o \
  -iname "*.cr2" -o \
  -iname "*.nef" -o \
  -iname "*.arw" \
\) | wc -l | tr -d ' ')
echo "      Photo files: ${PHOTO_COUNT}"
echo ""

# Sample hash verification (all photos in this case, since it's 10-20 photos)
echo "[2/4] Generating SHA256 hashes for all photos..."
HASH_COUNT=0
while IFS= read -r -d '' file; do
  HASH=$(shasum -a 256 "${file}" | awk '{print $1}')
  echo "      ${file##*/}: ${HASH}"
  HASH_COUNT=$((HASH_COUNT + 1))
done < <(find "${RESTORE_PATH}" -type f \( \
  -iname "*.jpg" -o \
  -iname "*.jpeg" -o \
  -iname "*.png" -o \
  -iname "*.heic" -o \
  -iname "*.heif" -o \
  -iname "*.raw" -o \
  -iname "*.cr2" -o \
  -iname "*.nef" -o \
  -iname "*.arw" \
\) -print0)

echo ""
echo "      Hashes generated: ${HASH_COUNT}"
echo ""

# Check for zero-byte files (corruption indicator)
echo "[3/4] Checking for corrupted files (0 bytes)..."
ZERO_BYTE_COUNT=$(find "${RESTORE_PATH}" -type f -size 0 | wc -l | tr -d ' ')
if [ "${ZERO_BYTE_COUNT}" -gt 0 ]; then
  echo "      ⚠️  WARNING: ${ZERO_BYTE_COUNT} zero-byte files found!"
  echo "      List of zero-byte files:"
  find "${RESTORE_PATH}" -type f -size 0 -print0 | while IFS= read -r -d '' file; do
    echo "        ${file}"
  done
else
  echo "      ✓ No zero-byte files detected"
fi
echo ""

# Summary
echo "[4/4] Verification Summary"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Total files:     ${FILE_COUNT}"
echo "Photo files:     ${PHOTO_COUNT}"
echo "Hashes checked:  ${HASH_COUNT}"
echo "Corrupted files: ${ZERO_BYTE_COUNT}"
echo ""

if [ "${ZERO_BYTE_COUNT}" -gt 0 ]; then
  echo "Status: ⚠️  WARNING - Corruption detected"
  echo ""
  echo "Next steps:"
  echo "  1. Investigate zero-byte files"
  echo "  2. Re-download Pool chunk if corruption suspected"
  echo "  3. Check backup integrity at source"
  exit 1
else
  echo "Status: ✓ PASS - No obvious corruption"
  echo ""
  echo "Next steps:"
  echo "  1. Manually open 3-5 photos in image viewer"
  echo "  2. Verify images display correctly"
  echo "  3. Check EXIF data: exiftool <photo>.jpg"
  echo "  4. Document results in drill report"
fi

echo ""
echo "Verification complete."
