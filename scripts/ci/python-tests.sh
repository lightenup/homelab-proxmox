#!/usr/bin/env bash
set -euo pipefail

# Run Python unit + golden tests with coverage enforcement scoped to orchestrator logic.

export PYTHONPATH="${PYTHONPATH:-python/src}"

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" && -x ".venv/bin/python" ]]; then
	PYTHON_BIN=".venv/bin/python"
fi
PYTHON_BIN="${PYTHON_BIN:-python3}"

"$PYTHON_BIN" -m pytest -c python/pytest.ini --cov-fail-under=80
