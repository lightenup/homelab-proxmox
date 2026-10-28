"""PVE config backup collects the per-service Terraform state on the host (backlog 096).

Until 2026-10-28 the backup copied only the NAS infra_state and the legacy repo state, so the
seven services whose state lives as plain directories under /var/lib/homelab-proxmox/state/services
had no backup. These tests run the real collect_iac_artifacts() from the template.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ROLE = ROOT / "ansible/roles/proxmox_backup"
SCRIPT = ROLE / "templates/proxmox-config-backup.sh.j2"


def _function(name: str) -> str:
    text = SCRIPT.read_text()
    match = re.search(rf"^{name}\(\) {{\n.*?^}}\n", text, re.M | re.S)
    assert match, f"{name}() not found in {SCRIPT.name}"
    assert "{{" not in match.group(0), f"{name}() must not contain Jinja (tested unrendered)"
    return match.group(0)


def _collect(tmp_path: Path, state_root: Path) -> subprocess.CompletedProcess[str]:
    harness = tmp_path / "harness.sh"
    harness.write_text(
        "set -euo pipefail\n"
        "log_info() { echo \"INFO: $*\"; }\n"
        "log_warning() { echo \"WARNING: $*\" >&2; }\n"
        "log_error() { echo \"ERROR: $*\" >&2; }\n"
        + _function("scan_plaintext_secrets")
        + _function("collect_iac_artifacts")
        + "collect_iac_artifacts\n"
    )
    return subprocess.run(
        ["bash", str(harness)],
        env={"PATH": "/usr/bin:/bin", "STAGING_DIR": str(tmp_path / "staging"), "LOCAL_STATE_ROOT": str(state_root)},
        capture_output=True,
        text=True,
        check=False,
    )


def _state_root(tmp_path: Path) -> Path:
    root = tmp_path / "services"
    (root / "hermes").mkdir(parents=True)
    (root / "hermes/terraform.tfstate").write_text('{"version": 4, "resources": []}\n')
    (root / "hermes/terraform.tfstate.backup").write_text('{"version": 4}\n')
    nas = tmp_path / "nas/homeassistant"
    nas.mkdir(parents=True)
    (nas / "terraform.tfstate").write_text('{"version": 4}\n')
    (root / "homeassistant").symlink_to(nas)
    return root


def test_copies_plain_state_dirs_and_skips_nas_symlinks(tmp_path: Path) -> None:
    proc = _collect(tmp_path, _state_root(tmp_path))
    assert proc.returncode == 0, proc.stderr
    local = tmp_path / "staging/iac-artifacts/local-state"
    assert (local / "hermes/terraform.tfstate").is_file()
    assert (local / "hermes/terraform.tfstate.backup").is_file()
    assert not (local / "homeassistant").exists(), "symlinked (NAS) state is collected elsewhere"


def test_collected_state_goes_through_the_secret_scan(tmp_path: Path) -> None:
    root = _state_root(tmp_path)
    (root / "hermes/terraform.tfstate").write_text('{"password": "hunter2-literal"}\n')
    proc = _collect(tmp_path, root)
    assert proc.returncode == 4
    assert "local-state/hermes/terraform.tfstate: password" in proc.stderr
    assert "hunter2-literal" not in proc.stdout + proc.stderr


def test_missing_state_root_only_warns(tmp_path: Path) -> None:
    proc = _collect(tmp_path, tmp_path / "does-not-exist")
    assert proc.returncode == 0, proc.stderr
    assert "Local state root not found" in proc.stderr


def test_role_wires_the_state_root_into_the_config() -> None:
    assert 'proxmox_backup_local_state_root: "/var/lib/homelab-proxmox/state/services"' in (
        ROLE / "defaults/main.yml"
    ).read_text()
    assert 'LOCAL_STATE_ROOT="{{ proxmox_backup_local_state_root }}"' in (
        ROLE / "templates/proxmox-backup.conf.j2"
    ).read_text()
