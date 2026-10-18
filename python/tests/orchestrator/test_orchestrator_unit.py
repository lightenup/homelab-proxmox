from __future__ import annotations

from pathlib import Path

import pytest

from homelab_proxmox_orchestrator.orchestrator import RunRequest, run
from homelab_proxmox_orchestrator.plan_identity import identity_path_for_run, load_plan_identity
from homelab_proxmox_orchestrator.provenance import load_provenance


def test_orchestrator_plan_writes_provenance_and_identity(tmp_path: Path):
    resp = run(
        RunRequest(
            service="ntfy",
            environment="lab",
            action="plan",
            source_ref="abc",
            evidence_root=str(tmp_path),
            runner_script_path="python/tests/orchestrator/fixtures/fake_pve_service_deploy.sh",
        )
    )

    assert resp.status == "succeeded"
    assert resp.exit_code == 0
    assert resp.run_id == "lab-ntfy-plan-TESTRUN"

    run_dir = tmp_path / "runs" / resp.run_id
    prov = load_provenance(run_dir / "provenance.json")
    assert prov.action == "plan"
    assert prov.environment == "lab"
    assert prov.service == "ntfy"
    assert prov.source_ref == "abc"

    ident = load_plan_identity(identity_path_for_run(run_dir))
    assert ident.plan_run_id == resp.run_id


def test_orchestrator_apply_requires_matching_plan_when_requested(tmp_path: Path):
    plan = run(
        RunRequest(
            service="ntfy",
            environment="lab",
            action="plan",
            source_ref="abc",
            evidence_root=str(tmp_path),
            runner_script_path="python/tests/orchestrator/fixtures/fake_pve_service_deploy.sh",
        )
    )

    apply = run(
        RunRequest(
            service="ntfy",
            environment="lab",
            action="apply",
            source_ref="abc",
            evidence_root=str(tmp_path),
            runner_script_path="python/tests/orchestrator/fixtures/fake_pve_service_deploy.sh",
            from_plan_run_id=plan.run_id,
            require_source_ref_match=True,
        )
    )

    assert apply.status == "succeeded"
    assert apply.exit_code == 0


def test_orchestrator_apply_source_ref_mismatch_raises(tmp_path: Path):
    plan = run(
        RunRequest(
            service="ntfy",
            environment="lab",
            action="plan",
            source_ref="abc",
            evidence_root=str(tmp_path),
            runner_script_path="python/tests/orchestrator/fixtures/fake_pve_service_deploy.sh",
        )
    )

    with pytest.raises(ValueError, match=r"source_ref does not match"):
        run(
            RunRequest(
                service="ntfy",
                environment="lab",
                action="apply",
                source_ref="def",
                evidence_root=str(tmp_path),
                runner_script_path="python/tests/orchestrator/fixtures/fake_pve_service_deploy.sh",
                from_plan_run_id=plan.run_id,
                require_source_ref_match=True,
            )
        )
