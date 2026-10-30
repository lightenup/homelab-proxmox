"""The standalone LAB workflows are gone and nothing claims LAB changes production (067)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
STALE = ("lxc-deploy-lab", "lxc-promote-lab", "LXC Deploy (LAB)", "LXC Promote (LAB)")


def test_standalone_lab_workflows_are_deleted():
    for name in ("lxc-deploy-lab.yml", "lxc-promote-lab.yml"):
        assert not (ROOT / ".github/workflows" / name).exists(), name


def test_nothing_outside_specs_and_the_backlog_references_them():
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    hits = []
    for rel in files:
        if rel.startswith(("specs/", "docs/backlog/", ".specify/features/")) or rel == "python/tests/guardrails/test_removed_lab_workflows.py":
            continue
        path = ROOT / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if any(s in text for s in STALE):
            hits.append(rel)
    assert not hits, hits


def test_no_workflow_job_says_lab_changes_prod():
    for path in (ROOT / ".github/workflows").glob("*.yml"):
        for job_id, job in (yaml.safe_load(path.read_text()).get("jobs") or {}).items():
            assert "changes prod" not in str(job.get("name", "")).lower(), f"{path.name}:{job_id}"
