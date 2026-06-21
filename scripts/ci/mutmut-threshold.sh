#!/usr/bin/env bash
set -euo pipefail

# Mutation-testing gate for the orchestrator module.
#
# Runs mutmut and fails if the mutation score drops below the committed floor in
# python/mutmut-threshold.txt. Score = 100 * killed / (killed + survived); timeout,
# suspicious and skipped mutants are excluded because they are nondeterministic.
#
# Parity (Constitution V): this runs identically on a laptop, on PVE, and in CI —
# everything is driven by env vars with sensible local defaults. It relies on the
# .mutmut-cache in the repo root (CI symlinks that to the NAS-hosted shared cache).
#
# Env overrides:
#   MUTMUT_MIN_SCORE     - floor percent; overrides the threshold file
#   MUTMUT_THRESHOLD_FILE- path to the floor file (default python/mutmut-threshold.txt)
#   MUTMUT_SCORE_MARGIN  - tolerance subtracted from the floor (default 1.0)
#   PYTHON_BIN           - python interpreter (default .venv/bin/python, else python3)

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

THRESHOLD_FILE="${MUTMUT_THRESHOLD_FILE:-python/mutmut-threshold.txt}"
MARGIN="${MUTMUT_SCORE_MARGIN:-1.0}"

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" && -x ".venv/bin/python" ]]; then
	PYTHON_BIN=".venv/bin/python"
fi
PYTHON_BIN="${PYTHON_BIN:-python3}"

# Floor: explicit env wins, otherwise the first non-comment, non-blank line of the file.
if [[ -n "${MUTMUT_MIN_SCORE:-}" ]]; then
	FLOOR="${MUTMUT_MIN_SCORE}"
else
	FLOOR="$(grep -vE '^[[:space:]]*(#|$)' "$THRESHOLD_FILE" | head -n1 | tr -d '[:space:]')"
fi
: "${FLOOR:?could not read floor from $THRESHOLD_FILE}"

echo ">> Running mutmut over python/src/homelab_proxmox_orchestrator (uses .mutmut-cache)..."
# A nonzero mutmut exit just means surviving mutants; we compute the score ourselves.
"$PYTHON_BIN" -m mutmut run --CI --no-progress \
	--paths-to-mutate python/src/homelab_proxmox_orchestrator \
	--tests-dir python/tests \
	--runner "env PYTHONPATH=python/src $PYTHON_BIN -m pytest -q -c python/pytest.ini -n auto" || true

# Count a result category. Subshell disables pipefail so a nonzero mutmut exit
# (or an unknown category printing nothing) just yields 0.
count() {
	(set +o pipefail; "$PYTHON_BIN" -m mutmut result-ids "$1" 2>/dev/null | wc -w | tr -d '[:space:]')
}
killed="$(count killed)"
survived="$(count survived)"
timeout="$(count timeout)"
suspicious="$(count suspicious)"

echo ">> killed=$killed survived=$survived timeout=$timeout suspicious=$suspicious"

"$PYTHON_BIN" - "$killed" "$survived" "$FLOOR" "$MARGIN" <<'PY'
import sys

killed, survived, floor, margin = (float(x or 0) for x in sys.argv[1:5])
denom = killed + survived
score = 100.0 * killed / denom if denom else 100.0
gate = floor - margin
print(f">> mutation score: {score:.2f}%  (floor {floor:.2f}% - margin {margin:.2f} = gate {gate:.2f}%)")
if score < gate:
    print(f"::error::Mutation score {score:.2f}% is below the gate {gate:.2f}%")
    sys.exit(1)
print(">> mutation gate PASSED")
PY
