#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   bash scripts/lab/python.sh [python args...]
#
# Runs repo-local Python code via a uv-managed virtualenv pinned by lockfile.
# Falls back to system python3 if uv is not available.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

LOCKFILE="${REPO_ROOT}/python/requirements-test.lock.txt"
VENV_DIR="${REPO_ROOT}/.venv"
PY_BIN="${VENV_DIR}/bin/python"
LOCK_HASH_FILE="${VENV_DIR}/.requirements-test.lock.sha256"

ensure_venv() {
    if ! command -v uv >/dev/null 2>&1; then
        return 1
    fi

    if [[ ! -x "${PY_BIN}" ]]; then
        uv venv "${VENV_DIR}"
    fi

    if [[ -f "${LOCKFILE}" ]]; then
        local new_hash
        new_hash="$(shasum -a 256 "${LOCKFILE}" | awk '{print $1}')"
        local old_hash=""
        if [[ -f "${LOCK_HASH_FILE}" ]]; then
            old_hash="$(cat "${LOCK_HASH_FILE}" 2>/dev/null || true)"
        fi

        if [[ "${new_hash}" != "${old_hash}" ]]; then
            uv pip sync --python "${PY_BIN}" --require-hashes "${LOCKFILE}"
            printf '%s' "${new_hash}" >"${LOCK_HASH_FILE}"
        fi
    fi

    return 0
}

if [[ -z "${PYTHONPATH:-}" ]]; then
    export PYTHONPATH="${REPO_ROOT}/python/src"
fi

if ensure_venv; then
    exec "${PY_BIN}" "$@"
fi

exec python3 "$@"
