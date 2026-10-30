"""LAB run contract (067): evidence verification and orchestrator wiring.

The live end-to-end run (quickstart section 2) is the proof that the steps work against Proxmox;
these tests pin the parts that must not silently regress.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
LAB = ROOT / "scripts" / "lab"
FIXTURE = LAB / "fixtures" / "evidence-packs" / "service-deploy-valid"
DEPLOY = (LAB / "pve-service-deploy").read_text()


def _verify(pack: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["python3", str(LAB / "verify_evidence.py"), str(pack)], capture_output=True, text=True)


@pytest.fixture
def pack(tmp_path: Path) -> Path:
    dst = tmp_path / "service-deploy-valid"
    shutil.copytree(FIXTURE, dst)
    return dst


def test_valid_lab_pack_passes(pack):
    assert _verify(pack).returncode == 0


@pytest.mark.parametrize("name", ["fingerprint.before.json", "fingerprint.after.json", "teardown.json"])
def test_missing_lab_evidence_fails(pack, name):
    (pack / "reports" / "lab" / name).unlink()
    proc = _verify(pack)
    assert proc.returncode != 0
    assert name in proc.stdout + proc.stderr


def test_teardown_not_ok_fails(pack):
    path = pack / "reports" / "lab" / "teardown.json"
    path.write_text(json.dumps({**json.loads(path.read_text()), "ok": False}))
    proc = _verify(pack)
    assert proc.returncode != 0
    assert "LAB-001" in proc.stdout + proc.stderr


def test_fingerprint_diff_fails(pack):
    (pack / "reports" / "lab" / "fingerprint.diff.txt").write_text("container 101: status running -> stopped\n")
    proc = _verify(pack)
    assert proc.returncode != 0
    assert "LAB-002" in proc.stdout + proc.stderr


def test_prod_pack_does_not_need_lab_evidence(pack):
    shutil.rmtree(pack / "reports" / "lab")
    prov = pack / "provenance.json"
    prov.write_text(json.dumps({**json.loads(prov.read_text()), "environment": "prod"}))
    proc = _verify(pack)
    assert "reports/lab/" not in proc.stdout + proc.stderr


def test_orchestrator_script_parses():
    assert subprocess.run(["bash", "-n", str(LAB / "pve-service-deploy")]).returncode == 0


def test_plan_and_apply_both_start_a_lab_run_and_teardown_is_an_exit_trap():
    assert "lab_begin plan" in DEPLOY and "lab_begin apply" in DEPLOY
    assert "trap lab_finish EXIT" in DEPLOY
    # verification waits for teardown and the production fingerprint
    assert 'LAB_DEFER_VERIFY:-}" == "1" ]] && return 0' in DEPLOY


def test_lab_never_backs_up_state_or_reads_a_lab_tfvars_file():
    assert 'if [[ "${ENVIRONMENT}" == "lab" ]]; then\n        echo "skipped: LAB state is ephemeral' in DEPLOY
    assert "_tfvars_lab_provision_and_write_proof" in DEPLOY
    assert not (ROOT / "terraform/environments/lab.tfvars.template").exists()


def test_stable_refusal_messages_exist_in_the_scripts():
    text = DEPLOY + (LAB / "lib/lab_run.sh").read_text()
    for needle in (
        "another LAB run holds",
        "at least ${margin} MiB must stay free",
        "refusing to destroy: lab state",
        "bind-mount policy (",
        "production changed during LAB run; see reports/lab/fingerprint.diff.txt",
        "lab isolation broken:",
        "lab inventory resolves",
    ):
        assert needle in text or needle.replace("${margin}", "{margin}") in text, needle
