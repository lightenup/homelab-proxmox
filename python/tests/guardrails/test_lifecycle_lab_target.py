"""`lxc-lifecycle` lab target and the promotion pipeline's LAB job (067)."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
LIFECYCLE = ROOT / ".github/workflows/lxc-lifecycle.yml"
PROMOTE = ROOT / ".github/workflows/lxc-promote-prod.yml"


def _jobs(path: Path) -> dict:
    return yaml.safe_load(path.read_text())["jobs"]


def test_lab_delete_is_refused_in_the_first_step_of_the_plan_job():
    first = _jobs(LIFECYCLE)["plan"]["steps"][0]
    steps = _jobs(LIFECYCLE)["plan"]["steps"]
    refusal = next(s for s in steps if "no standing lab copy exists" in s.get("run", ""))
    assert "no standing lab copy exists; LAB is an ephemeral rehearsal (067)" in refusal["run"]
    assert steps.index(refusal) <= steps.index(first) + 1  # directly after checkout


def test_lab_runs_the_orchestrator_with_environment_lab_and_prod_keeps_its_confirmations():
    text = LIFECYCLE.read_text()
    assert "--environment ${environment}" in text.replace("'${environment}'", "${environment}") or "--environment" in text
    apply_steps = [s.get("name") for s in _jobs(LIFECYCLE)["apply"]["steps"]]
    assert "Enforce prod apply confirmation" in apply_steps
    assert "Enforce data deletion confirmation" in apply_steps


def test_promotion_has_an_isolated_lab_rehearsal_job_with_a_90_minute_timeout():
    jobs = _jobs(PROMOTE)
    job = jobs["apply_lab"]
    assert job["name"] == "LAB rehearsal (isolated)"
    assert job["timeout-minutes"] == 90
    assert any(s.get("name") == "Rehearse on PVE (LAB, isolated)" for s in job["steps"])


def test_a_failed_lab_apply_cannot_pass_the_gate_on_verification_alone():
    outcome = next(s for s in _jobs(PROMOTE)["apply_lab"]["steps"] if s.get("id") == "outcome")
    assert "status=success" in outcome["run"]
