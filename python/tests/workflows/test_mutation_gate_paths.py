"""FR-006, research R9: the mutation gate's path list (spec 087).

Modelled on test_confidence_gate_paths.py: same YAML loader, same "cleaned patterns"
helper. Unlike the confidence suite, this list has excludes (`!`-prefixed lines,
applied first) as well as includes, so `_decide` mirrors both.
"""
from __future__ import annotations

from pathlib import Path
import re

import pytest
import yaml


class _Yaml12SafeLoader(yaml.SafeLoader):
    pass


for first_char, resolvers in list(_Yaml12SafeLoader.yaml_implicit_resolvers.items()):
    _Yaml12SafeLoader.yaml_implicit_resolvers[first_char] = [
        (tag, regexp) for (tag, regexp) in resolvers if tag != "tag:yaml.org,2002:bool"
    ]

_Yaml12SafeLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:true|false)$", re.IGNORECASE),
    list("tTfF"),
)


def _load_yaml(path: Path) -> dict:
    obj = yaml.load(path.read_text(encoding="utf-8"), Loader=_Yaml12SafeLoader)
    assert isinstance(obj, dict)
    return obj


PATHS_FILE = Path("scripts/ci/mutation-gate-paths.txt")
WORKFLOW = Path(".github/workflows/mutation.yml")


def _cleaned_lines() -> list[str]:
    """Non-comment, non-blank lines from the mutation gate path list, in file order."""
    assert PATHS_FILE.is_file(), f"Missing path list: {PATHS_FILE}"
    return [
        line.strip()
        for line in PATHS_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def _includes_and_excludes() -> tuple[list[re.Pattern], list[re.Pattern]]:
    includes: list[re.Pattern] = []
    excludes: list[re.Pattern] = []
    for line in _cleaned_lines():
        if line.startswith("!"):
            excludes.append(re.compile(line[1:]))
        else:
            includes.append(re.compile(line))
    return includes, excludes


def _decide(paths: list[str]) -> bool:
    """Mirror the workflow's `Detect mutation-relevant changes` step.

    Drop paths matching any exclude, then run if any remaining path matches an include.
    An empty include list means "run" (fail open, research R9 / PR #277 review R1).
    """
    includes, excludes = _includes_and_excludes()
    if not includes:
        return True
    remaining = [p for p in paths if not any(rx.search(p) for rx in excludes)]
    return any(rx.search(p) for p in remaining for rx in includes if rx.search(p))


def test_path_list_is_non_empty():
    includes, _ = _includes_and_excludes()
    assert includes, "The cleaned mutation-gate include list must be non-empty"


@pytest.mark.parametrize(
    "path",
    [
        "python/src/homelab_proxmox_orchestrator/cli.py",
        "python/tests/orchestrator/test_cli.py",
        "python/tests/conftest.py",
        "python/pytest.ini",
        "python/mutmut-threshold.txt",
        "python/requirements-nightly.lock.txt",
        "python/requirements-test.txt",
        "setup.cfg",
        "src",
        "scripts/ci/mutmut-threshold.sh",
        "scripts/ci/mutmut_report.py",
        "scripts/ci/mutation-gate-paths.txt",
        ".github/workflows/mutation.yml",
    ],
)
def test_gate_runs_when_path_changes(path: str):
    assert _decide([path]), f"Path SHOULD trigger the mutation gate: {path}"


@pytest.mark.parametrize(
    "path",
    [
        "python/tests/guardrails/test_service_backup.py",
        "python/tests/workflows/test_confidence_gate_paths.py",
        ".github/workflows/ci.yml",
        "docs/operations/mutation-testing.md",
        "ansible/roles/ntfy/defaults/main.yml",
    ],
)
def test_gate_skips_when_path_changes(path: str):
    assert not _decide([path]), f"Path should NOT trigger the mutation gate: {path}"


def test_excludes_beat_includes_for_guardrails_and_workflows_tests():
    # python/tests/ is included wholesale, but tests/guardrails and tests/workflows are
    # excluded: a change there alone must not trigger the gate even though it is under
    # the broader python/tests/ include.
    assert _decide(["python/tests/orchestrator/test_cli.py"])
    assert not _decide(["python/tests/guardrails/test_service_backup.py"])
    assert not _decide(["python/tests/workflows/test_mutation_gate_paths.py"])


def test_mixed_diff_runs_if_any_remaining_path_matches():
    # A diff touching both an excluded-only path and an included path must still run.
    assert _decide(
        [
            "python/tests/guardrails/test_service_backup.py",
            "python/src/homelab_proxmox_orchestrator/cli.py",
        ]
    )


def test_workflow_is_wired_to_path_list():
    raw = WORKFLOW.read_text(encoding="utf-8")
    assert "scripts/ci/mutation-gate-paths.txt" in raw, (
        "mutation.yml must read scripts/ci/mutation-gate-paths.txt"
    )
    assert "grep -qEf" in raw, (
        "mutation.yml must match the diff against the include list with grep -qEf"
    )
    assert "grep -qE '^python/'" not in raw, (
        "mutation.yml must no longer inline the old '^python/' check"
    )


# ---------------------------------------------------------------------------
# Coverage (research R9): every python/tests/ subdirectory except guardrails,
# workflows and __pycache__ must have at least one test_*.py path that runs the
# gate. A new test directory is then covered by default, which prefers a false
# run over a false skip.
# ---------------------------------------------------------------------------

_EXEMPT_TEST_DIRS = {"guardrails", "workflows", "__pycache__"}


def test_every_test_subdirectory_is_covered():
    tests_root = Path("python/tests")
    subdirs = sorted(
        d.name for d in tests_root.iterdir() if d.is_dir() and d.name not in _EXEMPT_TEST_DIRS
    )
    assert subdirs, "No python/tests/ subdirectories found (fixture path may be wrong)"
    for name in subdirs:
        sample = next(iter(sorted((tests_root / name).glob("test_*.py"))), None)
        assert sample is not None, f"No test_*.py file found directly under python/tests/{name}/"
        assert _decide([str(sample)]), (
            f"python/tests/{name}/{sample.name} is not covered by the mutation gate path list"
        )
