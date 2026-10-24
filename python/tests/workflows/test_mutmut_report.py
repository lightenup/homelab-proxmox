"""FR-010: score and report from mutmut 3.8 CICD stats and .meta files (spec 087)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import sys

import pytest

SCRIPT = Path("scripts/ci/mutmut_report.py")

STATUS_MAP = {
    1: "killed",
    3: "killed",
    0: "survived",
    5: "no_tests",
    33: "no_tests",
    36: "timeout",
    None: "not_checked",
    35: "suspicious",
}


def _load_script():
    assert SCRIPT.is_file(), f"Missing script: {SCRIPT}"
    spec = importlib.util.spec_from_file_location("mutmut_report", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_meta(exit_codes: dict[str, int | None]) -> dict:
    return {
        "exit_code_by_key": exit_codes,
        "hash_by_function_name": {},
        "type_check_error_by_key": {},
        "durations_by_key": {},
    }


@pytest.fixture
def mutants_dir(tmp_path: Path) -> Path:
    d = tmp_path / "mutants"
    src = d / "src" / "homelab_proxmox_orchestrator"
    src.mkdir(parents=True)
    stats = {
        "killed": 3,
        "survived": 2,
        "no_tests": 2,
        "timeout": 0,
        "suspicious": 0,
        "skipped": 0,
        "segfault": 0,
        "total": 7,
    }
    (d / "mutmut-cicd-stats.json").write_text(json.dumps(stats))
    (src / "alpha.py.meta").write_text(
        json.dumps(_make_meta({"f1": 1, "f2": 0, "f3": 5}))
    )
    pkg = src / "pkg"
    pkg.mkdir()
    (pkg / "beta.py.meta").write_text(
        json.dumps(_make_meta({"g1": 3, "g2": 33, "g3": 0}))
    )
    return d


def test_status_mapping():
    mod = _load_script()
    for exit_code, expected in STATUS_MAP.items():
        assert mod._status_for(exit_code) == expected, (
            f"exit code {exit_code} should map to {expected}"
        )


def test_score_formula(mutants_dir: Path):
    mod = _load_script()
    result = mod._build_report(
        mutants_dir,
        floor=50.0,
        margin=1.0,
        commit="abc123",
        mutmut_version="3.8.0",
    )
    assert result["score"] == 60.0, "3 killed / (3+2 survived) = 60.0"


def test_score_100_when_no_killed_or_survived(tmp_path: Path):
    mod = _load_script()
    d = tmp_path / "mutants"
    src = d / "src" / "homelab_proxmox_orchestrator"
    src.mkdir(parents=True)
    stats = {
        "killed": 0,
        "survived": 0,
        "no_tests": 5,
        "timeout": 0,
        "suspicious": 0,
        "skipped": 0,
        "segfault": 0,
        "total": 5,
    }
    (d / "mutmut-cicd-stats.json").write_text(json.dumps(stats))
    (src / "a.py.meta").write_text(
        json.dumps(_make_meta({"x": 5, "y": 33, "z": 5, "w": 33, "v": 5}))
    )
    result = mod._build_report(d, floor=0.0, margin=0.0, commit="abc", mutmut_version="3.8.0")
    assert result["score"] == 100.0


def test_passed_includes_equal_case(mutants_dir: Path):
    mod = _load_script()
    result = mod._build_report(
        mutants_dir, floor=60.0, margin=0.0, commit="abc", mutmut_version="3.8.0"
    )
    assert result["score"] == 60.0
    assert result["passed"] is True, "score == gate must pass"


def test_passed_false_below_gate(mutants_dir: Path):
    mod = _load_script()
    result = mod._build_report(
        mutants_dir, floor=80.0, margin=1.0, commit="abc", mutmut_version="3.8.0"
    )
    assert result["score"] == 60.0
    assert result["gate"] == 79.0
    assert result["passed"] is False


def test_survivors_by_module_order(mutants_dir: Path):
    mod = _load_script()
    result = mod._build_report(
        mutants_dir, floor=50.0, margin=1.0, commit="abc", mutmut_version="3.8.0"
    )
    modules = [m["module"] for m in result["survivors_by_module"]]
    assert modules == ["alpha", "pkg.beta"], (
        f"Expected alpha and pkg.beta (1 survived each), got {modules}"
    )
    assert result["survivors_by_module"][0]["survived"] == 1
    assert result["survivors_by_module"][1]["survived"] == 1


def test_report_json_fields(mutants_dir: Path):
    mod = _load_script()
    result = mod._build_report(
        mutants_dir, floor=50.0, margin=1.0, commit="abc123", mutmut_version="3.8.0"
    )
    assert result["schema"] == 1
    assert result["commit"] == "abc123"
    assert re.match(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$", result["finished_at"])
    assert result["mutmut_version"] == "3.8.0"
    assert result["floor"] == 50.0
    assert result["margin"] == 1.0
    assert result["gate"] == 49.0
    assert result["counts"]["killed"] == 3
    assert result["counts"]["survived"] == 2
    assert result["counts"]["no_tests"] == 2
    assert result["counts"]["total"] == 7


def test_survivors_txt(mutants_dir: Path):
    mod = _load_script()
    mod._write_outputs(
        mutants_dir,
        mod._build_report(
            mutants_dir, floor=50.0, margin=1.0, commit="abc", mutmut_version="3.8.0"
        ),
    )
    lines = (mutants_dir / "survivors.txt").read_text().splitlines()
    assert lines == ["1  alpha", "1  pkg.beta"]


def test_exit_code_pass(mutants_dir: Path, capsys):
    mod = _load_script()
    rc = mod.main(
        ["--mutants-dir", str(mutants_dir), "--floor", "50.0", "--margin", "1.0",
         "--commit", "abc", "--mutmut-version", "3.8.0"]
    )
    assert rc == 0


def test_exit_code_below_gate(mutants_dir: Path, capsys):
    mod = _load_script()
    rc = mod.main(
        ["--mutants-dir", str(mutants_dir), "--floor", "99.0", "--margin", "1.0",
         "--commit", "abc", "--mutmut-version", "3.8.0"]
    )
    assert rc == 1
    captured = capsys.readouterr()
    assert "::error::" in captured.out


def test_exit_code_missing_stats(tmp_path: Path, capsys):
    mod = _load_script()
    rc = mod.main(
        ["--mutants-dir", str(tmp_path / "nonexistent"), "--floor", "50.0", "--margin", "1.0",
         "--commit", "abc", "--mutmut-version", "3.8.0"]
    )
    assert rc == 2
    captured = capsys.readouterr()
    assert "mutmut produced no results" in captured.err


def test_exit_code_zero_total(tmp_path: Path, capsys):
    mod = _load_script()
    d = tmp_path / "mutants"
    d.mkdir()
    (d / "mutmut-cicd-stats.json").write_text(json.dumps({"total": 0}))
    rc = mod.main(
        ["--mutants-dir", str(d), "--floor", "50.0", "--margin", "1.0",
         "--commit", "abc", "--mutmut-version", "3.8.0"]
    )
    assert rc == 2
