from __future__ import annotations

from pathlib import Path
import re

import yaml

WORKFLOW = Path(".github/workflows/nightly-deeper-verification.yml")


def _job() -> dict:
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return doc["jobs"]["deeper"]


def test_scheduled_run_goes_to_pve() -> None:
    """Input defaults only apply to workflow_dispatch, so a schedule run must not read the input."""
    expr = _job()["env"]["RUN_ON_PVE"]
    assert "github.event_name == 'schedule'" in expr
    assert "inputs.run_on_pve" in expr


def test_steps_do_not_read_the_input_directly() -> None:
    """Every PVE guard reads RUN_ON_PVE; `inputs.run_on_pve` is empty on a schedule run."""
    for step in _job()["steps"]:
        guard = str(step.get("if", ""))
        assert "inputs.run_on_pve" not in guard, f"{step.get('name')}: guard reads the input"


def test_pve_and_non_pve_steps_are_exclusive() -> None:
    """Each mutmut step pair is guarded by RUN_ON_PVE being true and not true, respectively."""
    guards = [str(s.get("if", "")) for s in _job()["steps"]]
    assert sum("env.RUN_ON_PVE == 'true'" in g for g in guards) >= 4
    assert sum("env.RUN_ON_PVE != 'true'" in g for g in guards) == 2
    assert not any(re.search(r"inputs\.run_on_pve", g) for g in guards)
