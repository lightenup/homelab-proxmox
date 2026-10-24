from __future__ import annotations

# T035 demo (SC-001): a comment-only change under python/tests/guardrails/ must not trigger
# the mutation gate. This line is reverted/removed before merge.
from collections.abc import Iterable
from pathlib import Path


# Avoid embedding the forbidden substring literally in this file.
_NEEDLE = "scripts/" + "deprecated/"


def _find_repo_root(start: Path) -> Path:
    current = start
    for _ in range(20):
        if (current / ".git").exists() and (current / "python").exists():
            return current
        if (current / "Taskfile.yml").exists() and (current / "python").exists():
            return current
        current = current.parent
    raise RuntimeError("Unable to locate repository root")


def _iter_candidate_files(repo_root: Path) -> Iterable[Path]:
    include_roots = [
        repo_root / "README.md",
        repo_root / "docs",
        repo_root / "ansible",
        repo_root / "terraform",
        repo_root / ".github",
        repo_root / "scripts",
        repo_root / "python",
    ]

    excluded_dirs = {
        repo_root / ".git",
        repo_root / ".venv",
        repo_root / "venv",
        repo_root / "node_modules",
        repo_root / "dist",
        repo_root / "build",
        repo_root / ".pytest_cache",
        repo_root / ".mutmut-cache",
        repo_root / "scripts" / "deprecated",
        repo_root / "python" / ".venv",
        repo_root / "python" / ".pytest_cache",
        repo_root / "python" / ".mutmut-cache",
        repo_root / "python" / "__pycache__",
        repo_root / "python" / "tests" / "__pycache__",
    }

    allowed_suffixes = {
        ".md",
        ".txt",
        ".yml",
        ".yaml",
        ".tf",
        ".tfvars",
        ".sh",
        ".py",
        ".cfg",
        ".ini",
        ".json",
    }

    for root in include_roots:
        if root.is_file():
            yield root
            continue
        if not root.exists():
            continue

        for path in root.rglob("*"):
            if any(path == ex or ex in path.parents for ex in excluded_dirs):
                continue
            if path.is_dir():
                continue
            if path.suffix and path.suffix not in allowed_suffixes:
                continue
            # skip very large files (likely binaries or vendored)
            try:
                if path.stat().st_size > 2_000_000:
                    continue
            except OSError:
                continue
            yield path


def test_no_repo_references_to_scripts_deprecated() -> None:
    repo_root = _find_repo_root(Path(__file__).resolve())

    offenders: list[str] = []
    for path in _iter_candidate_files(repo_root):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        if _NEEDLE in text:
            offenders.append(str(path.relative_to(repo_root)))

    assert not offenders, (
        "Found references to deprecated scripts folder (must not be referenced by code/CI/IaC/operator docs):\n"
        + "\n".join(f"- {p}" for p in sorted(offenders))
    )
