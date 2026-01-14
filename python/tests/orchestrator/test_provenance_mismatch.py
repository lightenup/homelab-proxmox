import json
import subprocess
from pathlib import Path


def _call_apply(*, evidence_root: Path, plan_run_id: str, source_ref: str | None = None):
    argv = [
        "python3",
        "-m",
        "homelab_proxmox_orchestrator.cli",
        "apply",
        "--environment",
        "lab",
        "--service",
        "adguard",
        "--evidence-root",
        str(evidence_root),
        "--runner-script-path",
        "python/tests/orchestrator/fixtures/fake_pve_service_deploy.sh",
        "--from-plan-run-id",
        plan_run_id,
    ]
    if source_ref is not None:
        argv += ["--source-ref", source_ref]

    return subprocess.run(
        argv,
        text=True,
        capture_output=True,
        env={"PYTHONPATH": "python/src"},
    )


def test_unknown_plan_id_fails_fast(tmp_path):
    p = _call_apply(evidence_root=tmp_path, plan_run_id="does-not-exist", source_ref="abc")
    assert p.returncode == 2

    doc = json.loads(p.stdout)
    assert doc["status"] == "failed"
    assert "Plan run not found" in "\n".join(doc["summary"]["errors"])


def test_missing_identity_file_fails_fast(tmp_path):
    plan_run_id = "lab-adguard-PLAN123"
    plan_dir = tmp_path / "runs" / plan_run_id
    plan_dir.mkdir(parents=True)
    (plan_dir / "provenance.json").write_text(
        json.dumps(
            {
                "environment": "lab",
                "service": "adguard",
                "action": "plan",
                "source_ref": "abc",
                "started_at": "2026-01-01T00:00:00Z",
                "finished_at": "2026-01-01T00:00:01Z",
                "status": "succeeded",
                "exit_code": 0,
            }
        ),
        encoding="utf-8",
    )

    p = _call_apply(evidence_root=tmp_path, plan_run_id=plan_run_id, source_ref="abc")
    assert p.returncode == 2

    doc = json.loads(p.stdout)
    assert doc["status"] == "failed"
    assert "Plan identity file missing" in "\n".join(doc["summary"]["errors"])


def test_service_mismatch_fails_fast(tmp_path):
    plan_run_id = "lab-immich-PLAN123"
    plan_dir = tmp_path / "runs" / plan_run_id
    (plan_dir / "reports" / "plan").mkdir(parents=True)

    (plan_dir / "reports" / "plan" / "plan-identity.json").write_text(
        json.dumps(
            {
                "plan_run_id": plan_run_id,
                "plan_created_at": "2026-01-01T00:00:01Z",
                "planfile_hash": None,
            }
        ),
        encoding="utf-8",
    )
    (plan_dir / "provenance.json").write_text(
        json.dumps(
            {
                "environment": "lab",
                "service": "immich",
                "action": "plan",
                "source_ref": "abc",
                "started_at": "2026-01-01T00:00:00Z",
                "finished_at": "2026-01-01T00:00:01Z",
                "status": "succeeded",
                "exit_code": 0,
            }
        ),
        encoding="utf-8",
    )

    p = _call_apply(evidence_root=tmp_path, plan_run_id=plan_run_id, source_ref="abc")
    assert p.returncode == 2

    doc = json.loads(p.stdout)
    assert doc["status"] == "failed"
    assert "does not match requested apply" in "\n".join(doc["summary"]["errors"])


def test_source_ref_mismatch_fails_fast(tmp_path):
    plan_run_id = "lab-adguard-PLAN123"
    plan_dir = tmp_path / "runs" / plan_run_id
    (plan_dir / "reports" / "plan").mkdir(parents=True)

    (plan_dir / "reports" / "plan" / "plan-identity.json").write_text(
        json.dumps(
            {
                "plan_run_id": plan_run_id,
                "plan_created_at": "2026-01-01T00:00:01Z",
                "planfile_hash": None,
            }
        ),
        encoding="utf-8",
    )
    (plan_dir / "provenance.json").write_text(
        json.dumps(
            {
                "environment": "lab",
                "service": "adguard",
                "action": "plan",
                "source_ref": "abc",
                "started_at": "2026-01-01T00:00:00Z",
                "finished_at": "2026-01-01T00:00:01Z",
                "status": "succeeded",
                "exit_code": 0,
            }
        ),
        encoding="utf-8",
    )

    p = _call_apply(evidence_root=tmp_path, plan_run_id=plan_run_id, source_ref="def")
    assert p.returncode == 2

    doc = json.loads(p.stdout)
    assert doc["status"] == "failed"
    assert "source_ref does not match" in "\n".join(doc["summary"]["errors"])
