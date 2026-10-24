import json
import os
import subprocess
import sys
from pathlib import Path

import homelab_proxmox_orchestrator

_PKG_ROOT = str(Path(homelab_proxmox_orchestrator.__file__).resolve().parents[1])
# Inherit the parent environment: mutmut 3 selects the mutant via MUTANT_UNDER_TEST,
# so replacing the environment would make the child run the unmutated code.
_SUBPROCESS_ENV = {**os.environ, "PYTHONPATH": _PKG_ROOT}


def test_cli_plan_parses_and_emits_json(tmp_path):
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()

    # Runner is not implemented yet; this test will start failing until US1 is done.
    p = subprocess.run(
        [
            sys.executable,
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
        env=_SUBPROCESS_ENV,
    )

    assert p.stdout.strip(), p.stderr
    doc = json.loads(p.stdout)
    assert doc["service"] == "ntfy"
    assert doc["environment"] == "lab"
    assert doc["action"] == "plan"
    assert "summary" in doc
    assert "evidence" in doc
