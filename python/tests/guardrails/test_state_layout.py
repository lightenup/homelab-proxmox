"""Terraform state layout (067): state/{prod,lab}/<svc>, local to pve, no NAS switch."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LIB = ROOT / "scripts/lab/lib/state.sh"


def _bash(tmp_path: Path, call: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", f'source "{LIB}"; {call}'],
        env={"PATH": "/usr/bin:/bin", "STATE_ROOT": str(tmp_path)},
        capture_output=True,
        text=True,
        check=False,
    )


def test_prod_root(tmp_path):
    proc = _bash(tmp_path, "resolve_state_root prod")
    assert proc.stdout.strip() == f"{tmp_path}/prod"


def test_lab_service_path(tmp_path):
    proc = _bash(tmp_path, "get_service_state_path lab ntfy")
    assert proc.stdout.strip() == f"{tmp_path}/lab/ntfy/terraform.tfstate"


def test_unknown_environment_fails(tmp_path):
    proc = _bash(tmp_path, "resolve_state_root staging")
    assert proc.returncode != 0
    assert "Unknown environment" in proc.stderr


def test_verify_state_access_needs_a_writable_root(tmp_path):
    (tmp_path / "prod").mkdir()
    assert _bash(tmp_path, "verify_state_access prod").returncode == 0
    assert _bash(tmp_path, "verify_state_access lab").returncode != 0


def test_no_nas_state_leftovers():
    needles = ("USE_NAS_STATE", "infra_state", "state/services")
    offenders = []
    for base in ("scripts", "ansible", ".github"):
        for path in (ROOT / base).rglob("*"):
            # migrate-state-067 is the one-off that reads the old layout (deleted in T066).
            if not path.is_file() or path.suffix == ".pyc" or path.name == "migrate-state-067":
                continue
            try:
                text = path.read_text()
            except UnicodeDecodeError:
                continue
            offenders += [f"{path.relative_to(ROOT)}: {n}" for n in needles if n in text]
    assert not offenders, "\n".join(offenders)
