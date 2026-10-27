#!/usr/bin/env bash
set -euo pipefail

# Mutation-testing gate for the orchestrator module (mutmut 3).
#
# Always does a fresh full run: deletes mutants/ first, runs mutmut, exports CICD
# stats, then scores and reports via mutmut_report.py. No incremental runs.
#
# Score = 100 * killed / (killed + survived); timeout, suspicious, skipped,
# segfault and no-tests mutants are excluded because they are nondeterministic
# (spec 087 FR-010).
#
# Parity (Constitution V): this runs identically on a laptop, on PVE, and in CI —
# everything is driven by env vars with sensible local defaults. Running it on the
# Mac discards any previously pulled results (mutants/ is deleted first).
#
# Env overrides:
#   MUTMUT_MIN_SCORE     - floor percent; overrides the threshold file
#   MUTMUT_THRESHOLD_FILE- path to the floor file (default python/mutmut-threshold.txt)
#   MUTMUT_SCORE_MARGIN  - tolerance subtracted from the floor (default 1.0)
#   PYTHON_BIN           - python interpreter (default .venv/bin/python, else python3)
#   MUTMUT_COMMIT        - commit SHA recorded in report.json (default git rev-parse HEAD)

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

THRESHOLD_FILE="${MUTMUT_THRESHOLD_FILE:-python/mutmut-threshold.txt}"
MARGIN="${MUTMUT_SCORE_MARGIN:-1.0}"

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" && -x ".venv/bin/python" ]]; then
	PYTHON_BIN=".venv/bin/python"
fi
PYTHON_BIN="${PYTHON_BIN:-python3}"

MUTMUT_COMMIT="${MUTMUT_COMMIT:-$(git rev-parse HEAD 2>/dev/null || echo unknown)}"

# Floor: explicit env wins, otherwise the first non-comment, non-blank line of the file.
if [[ -n "${MUTMUT_MIN_SCORE:-}" ]]; then
	FLOOR="${MUTMUT_MIN_SCORE}"
else
	FLOOR="$(grep -vE '^[[:space:]]*(#|$)' "$THRESHOLD_FILE" | head -n1 | tr -d '[:space:]')"
fi
: "${FLOOR:?could not read floor from $THRESHOLD_FILE}"

echo ">> Running mutmut 3 over python/src/homelab_proxmox_orchestrator (fresh full run)..."
rm -rf mutants

# Per-run TMPDIR, deleted on every exit path (RCA 2026-10-27). mutmut 3 runs each mutant in
# an os.fork() child that ends with os._exit(), so atexit never runs; pytest removes its
# session lock via atexit and keeps any numbered basetemp dir whose lock is under 3 days old.
# Each run on pve left ~1,576 /tmp/pytest-of-ci/pytest-N dirs, and three days of runs hit
# the 1,048,576-inode cap of pve's /tmp tmpfs (a PR gate failed with ENOSPC). Everything
# pytest and mutmut write to the temp dir now lives in this one directory.
MUTMUT_TMPDIR="$(mktemp -d "${TMPDIR:-/tmp}/mutmut-run.XXXXXX")"
cleanup_tmpdir() { rm -rf "$MUTMUT_TMPDIR"; }
trap cleanup_tmpdir EXIT
caller_tmpdir_set="${TMPDIR+set}"
caller_tmpdir="${TMPDIR-}"
export TMPDIR="$MUTMUT_TMPDIR"

# A non-zero exit means mutmut itself failed (e.g. the forced-fail sanity check), not
# that mutants survived; never score a run like that (exit 2 = no valid results).
if ! "$PYTHON_BIN" -m mutmut run; then
	echo "::error::mutmut run failed; not scoring partial results" >&2
	exit 2
fi
if ! "$PYTHON_BIN" -m mutmut export-cicd-stats; then
	echo "::error::mutmut export-cicd-stats failed" >&2
	exit 2
fi

version="$("$PYTHON_BIN" -m mutmut --version | awk '{print $NF}')"

# `exec` replaces this shell, so the EXIT trap would never fire: clean up first, and give
# the report the caller's TMPDIR back.
cleanup_tmpdir
trap - EXIT
if [[ -n "$caller_tmpdir_set" ]]; then export TMPDIR="$caller_tmpdir"; else unset TMPDIR; fi

exec "$PYTHON_BIN" scripts/ci/mutmut_report.py \
	--mutants-dir mutants \
	--floor "$FLOOR" \
	--margin "$MARGIN" \
	--commit "$MUTMUT_COMMIT" \
	--mutmut-version "$version"
