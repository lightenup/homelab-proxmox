#!/usr/bin/env bash
set -euo pipefail

# Regenerate pinned, hashed Python dependency lockfiles using uv.
#
# These lockfiles are used in CI for reproducible installs:
#   - python/requirements-test.lock.txt
#   - python/requirements-nightly.lock.txt
#
# Notes:
# - The inputs remain the human-edited files:
#     python/requirements-test.txt
#     python/requirements-nightly.txt
# - Nightly lock includes BOTH test + nightly requirements.

UV_BIN="${UV_BIN:-uv}"
PY_VERSION="${PY_VERSION:-3.11}"

"$UV_BIN" pip compile \
  --python-version "$PY_VERSION" \
  --universal \
  --generate-hashes \
  python/requirements-test.txt \
  -o python/requirements-test.lock.txt

"$UV_BIN" pip compile \
  --python-version "$PY_VERSION" \
  --universal \
  --generate-hashes \
  python/requirements-test.txt \
  python/requirements-nightly.txt \
  -o python/requirements-nightly.lock.txt

echo "Wrote python/requirements-test.lock.txt and python/requirements-nightly.lock.txt"
