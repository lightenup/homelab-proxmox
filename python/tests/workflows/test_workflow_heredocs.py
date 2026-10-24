"""Heredocs in workflow `run:` blocks must survive YAML's block-scalar dedent (spec 087).

YAML strips only the block's common indent. A heredoc whose body and closing delimiter are indented
further (to line up with the surrounding `if`) keeps that indent, so bash never sees the delimiter
("here-document ... delimited by end-of-file") and an embedded Python body raises IndentationError.
Neither yamllint nor `act -n` catches this; it broke three times in spec 087 before CI did.
"""
from __future__ import annotations

from pathlib import Path
import re

import pytest
import yaml

WORKFLOWS = sorted(Path(".github/workflows").glob("*.yml"))

# `<<DELIM`, `<< 'DELIM'`, `<<-"DELIM"`; not here-strings (`<<<`).
_OPENER = re.compile(r"(?<!<)<<(-?)\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")
# Command feeding the heredoc to Python: `python3 - <<'X'`, `python3 << X`, `.venv/bin/python - <<X`.
_PYTHON_STDIN = re.compile(r"python[0-9.]*(?:\s+-)?\s*(?:<<|$)")


def heredoc_problems(script: str) -> list[str]:
    """Return a description of every heredoc in `script` that bash or Python would reject."""
    lines = script.splitlines()
    problems: list[str] = []
    for i, line in enumerate(lines):
        if line.lstrip().startswith("#"):
            continue
        for m in _OPENER.finditer(line):
            strip_tabs, _, delim = m.groups()
            body_end = None
            for j in range(i + 1, len(lines)):
                candidate = lines[j].lstrip("\t") if strip_tabs else lines[j]
                if candidate == delim:
                    body_end = j
                    break
            if body_end is None:
                problems.append(f"line {i + 1}: heredoc {delim!r} has no closing line at column 0")
                continue
            body = [b for b in lines[i + 1 : body_end] if b.strip()]
            if _PYTHON_STDIN.search(line[: m.start()] + "<<") and body and body[0][0] in " \t":
                problems.append(f"line {i + 1}: Python heredoc {delim!r} body is indented")
    return problems


def _run_blocks(path: Path) -> list[tuple[str, str]]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    blocks = []
    for job_name, job in (doc.get("jobs") or {}).items():
        for step in job.get("steps") or []:
            if isinstance(step.get("run"), str):
                blocks.append((f"{job_name} / {step.get('name', step.get('id', '?'))}", step["run"]))
    return blocks


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_workflow_heredocs_are_well_formed(path: Path):
    failures = [
        f"{where}: {problem}"
        for where, script in _run_blocks(path)
        for problem in heredoc_problems(script)
    ]
    assert not failures, f"{path}:\n" + "\n".join(failures)


def test_detects_indented_closer():
    # The original spec 087 bug, after YAML dedent.
    script = "if [ -f r.json ]; then\n  python3 << 'PYEOF' >> out\n  import json\n  PYEOF\nfi\n"
    assert heredoc_problems(script) == ["line 2: heredoc 'PYEOF' has no closing line at column 0"]


def test_detects_indented_python_body():
    script = "python3 - <<'PYEOF'\n  import json\nPYEOF\n"
    assert heredoc_problems(script) == ["line 1: Python heredoc 'PYEOF' body is indented"]


def test_accepts_well_formed_heredocs():
    script = (
        "if [ -f r.json ]; then\n"
        "  python3 - <<'PYEOF' >> out\n"
        "import json\n"
        "if True:\n"
        "    print(1)\n"
        "PYEOF\n"
        "fi\n"
        "ssh host bash -s <<'EOF'\n"
        "  set -e\n"  # non-Python bodies may be indented
        "EOF\n"
        "cat <<-EOF\n"
        "\tEOF\n"  # <<- strips leading tabs from the closer
        "x=$(cat <<<\"here-string\")\n"
    )
    assert heredoc_problems(script) == []
