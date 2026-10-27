"""Behaviour test: scripts/ci/mutmut-threshold.sh gives each run its own TMPDIR and removes it.

RCA 2026-10-27: mutmut 3.8.0 runs each mutant in an os.fork() child that ends with os._exit()
(mutmut/workers/isolation.py), so atexit never runs. pytest removes its session lock via
atexit (_pytest/pathlib.py register_cleanup_lock_removal) and will not prune a numbered
basetemp dir while its lock is younger than 3 days (LOCK_TIMEOUT). Every mutation run on pve
therefore left ~1,576 /tmp/pytest-of-ci/pytest-N dirs (120-565 inodes each); three days of
runs reached the 1,048,576-inode cap of pve's /tmp tmpfs, and a PR gate failed with ENOSPC.

The script now points TMPDIR at a fresh per-run directory and deletes it on every exit path,
including before the final `exec` of the report (a trap does not fire after exec).

The script runs `rm -rf mutants` relative to its own location, so it is copied into a scratch
repo layout first; `python` is a fake that stands in for mutmut and the report.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path


def _find_repo_root(start: Path) -> Path:
    current = start
    for _ in range(20):
        if (current / ".git").exists() and (current / "python").exists():
            return current
        if (current / "Taskfile.yml").exists() and (current / "python").exists():
            return current
        current = current.parent
    raise RuntimeError("Unable to locate repository root")


SCRIPT = _find_repo_root(Path(__file__).resolve()) / "scripts/ci/mutmut-threshold.sh"

# Fake interpreter. Records the TMPDIR each step saw, litters it like a forked pytest would
# (a numbered dir with a lock that is never removed), and can be told to fail a step.
FAKE_PYTHON = r"""#!/usr/bin/env bash
log="$FAKE_LOG"
case "$*" in
  "-m mutmut run")
    echo "run TMPDIR=${TMPDIR:-unset}" >>"$log"; echo "$TMPDIR" >"$log.rundir"
    mkdir -p "$TMPDIR/pytest-of-ci/pytest-1" && touch "$TMPDIR/pytest-of-ci/pytest-1/.lock"
    [ "${FAKE_FAIL:-}" = run ] && exit 1
    exit 0 ;;
  "-m mutmut export-cicd-stats") [ "${FAKE_FAIL:-}" = export ] && exit 1; exit 0 ;;
  "-m mutmut --version") echo "mutmut 3.8.0" ;;
  scripts/ci/mutmut_report.py*)
    echo "report TMPDIR=${TMPDIR:-unset} rundir_exists=$([ -e "$(cat "$log.rundir")" ] && echo yes || echo no)" >>"$log"
    exit "${FAKE_REPORT_RC:-0}" ;;
  *) echo "unexpected: $*" >>"$log"; exit 99 ;;
esac
"""


def _scratch_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "scripts/ci").mkdir(parents=True)
    (repo / "python").mkdir()
    shutil.copy(SCRIPT, repo / "scripts/ci/mutmut-threshold.sh")
    (repo / "python/mutmut-threshold.txt").write_text("# floor\n80\n")
    fake = repo / "fakepython"
    fake.write_text(FAKE_PYTHON)
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    return repo


def _run(tmp_path: Path, **env_over) -> tuple[subprocess.CompletedProcess, Path, Path]:
    repo = _scratch_repo(tmp_path)
    base = tmp_path / "base-tmp"
    base.mkdir()
    log = tmp_path / "fake.log"
    env = {
        "PATH": os.environ["PATH"],
        "PYTHON_BIN": str(repo / "fakepython"),
        "MUTMUT_COMMIT": "deadbeef",
        "TMPDIR": str(base),
        "FAKE_LOG": str(log),
        **env_over,
    }
    r = subprocess.run(["bash", str(repo / "scripts/ci/mutmut-threshold.sh")], env=env,
                       capture_output=True, text=True, timeout=30, cwd=repo)
    return r, base, log


def _seen(log: Path, step: str) -> str:
    line = next(l for l in log.read_text().splitlines() if l.startswith(step))
    return line.split("TMPDIR=")[1].split()[0]


def test_mutmut_runs_in_a_fresh_per_run_tmpdir_under_the_callers_tmpdir(tmp_path):
    r, base, log = _run(tmp_path)
    assert r.returncode == 0, r.stderr
    run_tmp = _seen(log, "run")
    assert run_tmp != str(base) and Path(run_tmp).parent == base


def test_per_run_tmpdir_is_gone_before_the_report_and_after_the_run(tmp_path):
    r, base, log = _run(tmp_path)
    report = next(l for l in log.read_text().splitlines() if l.startswith("report"))
    assert "rundir_exists=no" in report, "exec skips the EXIT trap: clean up before the report"
    assert _seen(log, "report") == str(base), "the report gets the caller's TMPDIR back"
    assert list(base.iterdir()) == [], "nothing may be left in the caller's TMPDIR"


def test_report_exit_code_is_preserved(tmp_path):
    r, base, _ = _run(tmp_path, FAKE_REPORT_RC="1")
    assert r.returncode == 1
    assert list(base.iterdir()) == []


def test_cleanup_also_happens_when_mutmut_fails(tmp_path):
    for step in ("run", "export"):
        sub = tmp_path / step
        sub.mkdir()
        r, base, _ = _run(sub, FAKE_FAIL=step)
        assert r.returncode == 2, (step, r.stderr)
        assert list(base.iterdir()) == [], f"per-run TMPDIR left behind after a failed {step}"


def test_works_without_a_caller_tmpdir(tmp_path):
    repo = _scratch_repo(tmp_path)
    log = tmp_path / "fake.log"
    env = {"PATH": os.environ["PATH"], "PYTHON_BIN": str(repo / "fakepython"),
           "MUTMUT_COMMIT": "x", "FAKE_LOG": str(log)}
    r = subprocess.run(["bash", str(repo / "scripts/ci/mutmut-threshold.sh")], env=env,
                       capture_output=True, text=True, timeout=30, cwd=repo)
    assert r.returncode == 0, r.stderr
    run_tmp = Path(_seen(log, "run"))
    assert run_tmp.parent == Path("/tmp") and not run_tmp.exists()
