"""LAB plan guards (067): capacity margin, bind-mount policy, bridge invariant, destroy guard."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
LIBS = [ROOT / "scripts/lab/lib/ct_conflicts.sh", ROOT / "scripts/lab/lib/lab_run.sh"]
SCRATCH = "/var/lib/homelab-proxmox/lab-scratch"


def _bash(call: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    sources = "; ".join(f'source "{p}"' for p in LIBS)
    return subprocess.run(
        ["bash", "-c", f"{sources}; {call}"],
        env={**os.environ, **(env or {})},
        capture_output=True,
        text=True,
        check=False,
    )


def _plan(tmp_path: Path, *, memory=2048, bridge="vmbr99", volume=None, actions=("create",)) -> Path:
    after = {"hostname": "lab-ntfy", "memory": memory, "network": [{"bridge": bridge, "ip": "10.99.0.222/24"}]}
    if volume:
        after["mountpoint"] = [{"volume": volume}]
    path = tmp_path / "plan.json"
    path.write_text(json.dumps({"resource_changes": [
        {"address": "module.ntfy_lxc.proxmox_lxc.this", "type": "proxmox_lxc",
         "change": {"actions": list(actions), "after": after}}]}))
    return path


def _meminfo(tmp_path: Path, avail_mib: int) -> Path:
    path = tmp_path / "meminfo"
    path.write_text(f"MemTotal: 99999999 kB\nMemAvailable: {avail_mib * 1024} kB\n")
    return path


def test_capacity_ok_writes_the_report(tmp_path):
    report = tmp_path / "capacity.json"
    proc = _bash(f'lab_capacity_check "{_plan(tmp_path)}" "{report}"', {"MEMINFO_PATH": str(_meminfo(tmp_path, 10000))})
    assert proc.returncode == 0, proc.stderr
    assert json.loads(report.read_text()) == {
        "mem_available_mib": 10000, "copy_memory_mib": 2048, "margin_mib": 6144, "ok": True}


def test_capacity_refuses_below_the_margin_with_both_figures(tmp_path):
    report = tmp_path / "capacity.json"
    proc = _bash(f'lab_capacity_check "{_plan(tmp_path)}" "{report}"', {"MEMINFO_PATH": str(_meminfo(tmp_path, 8000))})
    assert proc.returncode != 0
    assert "lab copy needs 2048 MiB; host has 8000 MiB available; at least 6144 MiB must stay free" in proc.stderr
    assert json.loads(report.read_text())["ok"] is False


def test_capacity_margin_is_overridable(tmp_path):
    proc = _bash(
        f'lab_capacity_check "{_plan(tmp_path)}" "{tmp_path / "c.json"}"',
        {"MEMINFO_PATH": str(_meminfo(tmp_path, 10000)), "LAB_MEMORY_MARGIN_MIB": "999999"},
    )
    assert proc.returncode != 0


def test_lab_bind_policy_allows_only_scratch(tmp_path):
    env = {"SCRATCH_ROOT": SCRATCH}
    ok = _bash(f'bind_mount_policy_check lab "{_plan(tmp_path, volume=SCRATCH + "/run-1/data")}" "{tmp_path / "r"}"', env)
    assert ok.returncode == 0, ok.stderr
    bad = _bash(f'bind_mount_policy_check lab "{_plan(tmp_path, volume="/mnt/nas/video")}" "{tmp_path / "r"}"', env)
    assert bad.returncode != 0
    assert f"bind-mount policy (lab): /mnt/nas/video is not under {SCRATCH}/" in bad.stderr


def test_prod_bind_policy_keeps_only_nas(tmp_path):
    ok = _bash(f'bind_mount_policy_check prod "{_plan(tmp_path, bridge="vmbr0", volume="/mnt/nas/video")}" "{tmp_path / "r"}"')
    assert ok.returncode == 0, ok.stderr
    bad = _bash(f'bind_mount_policy_check prod "{_plan(tmp_path, bridge="vmbr0", volume=SCRATCH + "/x")}" "{tmp_path / "r"}"')
    assert bad.returncode != 0


@pytest.mark.parametrize(
    ("env", "bridge", "rc"),
    [("lab", "vmbr99", 0), ("lab", "vmbr0", 1), ("prod", "vmbr0", 0), ("prod", "vmbr99", 1)],
)
def test_bridge_invariant(tmp_path, env, bridge, rc):
    assert _bash(f'lab_bridge_invariant {env} "{_plan(tmp_path, bridge=bridge)}"').returncode == rc


def _state(tmp_path: Path, *, hostname="lab-ntfy", bridge="vmbr99", ip="10.99.0.222/24", rtype="proxmox_lxc") -> Path:
    path = tmp_path / "terraform.tfstate"
    path.write_text(json.dumps({"resources": [{"module": "module.ntfy_lxc", "type": rtype, "name": "this", "instances": [
        {"attributes": {"id": "pve/lxc/130", "hostname": hostname, "network": [{"bridge": bridge, "ip": ip}]}}]}]}))
    return path


def test_destroy_guard_accepts_a_lab_copy(tmp_path):
    assert _bash(f'lab_destroy_guard "{_state(tmp_path)}"').returncode == 0


@pytest.mark.parametrize(
    "kwargs",
    [{"hostname": "ntfy"}, {"bridge": "vmbr0"}, {"ip": "192.168.1.222/24"}, {"ip": "10.99.0.10/24"}, {"rtype": "null_resource"}],
)
def test_destroy_guard_refuses_anything_that_is_not_a_lab_copy(tmp_path, kwargs):
    proc = _bash(f'lab_destroy_guard "{_state(tmp_path, **kwargs)}"')
    assert proc.returncode != 0
    assert "refusing to destroy: lab state" in proc.stderr
    assert "contains a resource that is not a lab copy (module.ntfy_lxc." in proc.stderr
