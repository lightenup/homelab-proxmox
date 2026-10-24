import json
import subprocess
import sys
from pathlib import Path

import homelab_proxmox_orchestrator

_PKG_ROOT = str(Path(homelab_proxmox_orchestrator.__file__).resolve().parents[1])


def _run(action: str, *, evidence_root: str):
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "homelab_proxmox_orchestrator.cli",
            action,
            "--environment",
            "lab",
            "--service",
            "ntfy",
            "--evidence-root",
            evidence_root,
            "--runner-script-path",
            "python/tests/orchestrator/fixtures/fake_pve_service_deploy.sh",
        ],
        text=True,
        capture_output=True,
        env={"PYTHONPATH": _PKG_ROOT},
    )


def test_runner_plan_creates_evidence_and_pointers(tmp_path):
    p = _run("plan", evidence_root=str(tmp_path))
    assert p.returncode == 0, p.stderr

    doc = json.loads(p.stdout)
    assert doc["status"] == "succeeded"
    assert doc["exitCode"] == 0
    assert doc["evidence"], doc


def test_runner_apply_creates_evidence_and_pointers(tmp_path):
    p = _run("apply", evidence_root=str(tmp_path))
    assert p.returncode == 0, p.stderr

    doc = json.loads(p.stdout)
    assert doc["status"] == "succeeded"
    assert doc["exitCode"] == 0
    assert doc["action"] == "apply"
