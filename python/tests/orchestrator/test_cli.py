import json
import subprocess


def test_cli_plan_parses_and_emits_json(tmp_path):
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()

    # Runner is not implemented yet; this test will start failing until US1 is done.
    p = subprocess.run(
        [
            "python3",
            "-m",
            "homelab_proxmox_orchestrator.cli",
            "plan",
            "--environment",
            "lab",
            "--service",
            "ntfy",
            "--evidence-root",
            str(evidence_root),
            "--runner-script-path",
            "python/tests/orchestrator/fixtures/fake_pve_service_deploy.sh",
        ],
        text=True,
        capture_output=True,
        env={"PYTHONPATH": "python/src"},
    )

    assert p.stdout.strip(), p.stderr
    doc = json.loads(p.stdout)
    assert doc["service"] == "ntfy"
    assert doc["environment"] == "lab"
    assert doc["action"] == "plan"
    assert "summary" in doc
    assert "evidence" in doc
