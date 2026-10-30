"""Lab-copy identity rule (067, data-model): hostname ^lab-, net0 bridge=vmbr99, IP .200-.254."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
LIB = ROOT / "scripts/lab/lib/ct_conflicts.sh"


def _cfg(hostname: str, bridge: str, ip: str) -> str:
    return f"hostname: {hostname}\nnet0: name=eth0,bridge={bridge},gw=10.99.0.1,ip={ip}/24,type=veth\n"


def _bash(tmp_path: Path, configs: dict[str, str], call: str) -> subprocess.CompletedProcess:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    cfg_dir = tmp_path / "configs"
    cfg_dir.mkdir()
    for vmid, text in configs.items():
        (cfg_dir / vmid).write_text(text)
    listing = "VMID       Status     Lock         Name\n" + "".join(
        f"{v}        running                 x\n" for v in configs
    )
    (tmp_path / "pct-list.txt").write_text(listing)
    (bin_dir / "sudo").write_text('#!/bin/sh\n[ "$1" = "-n" ] && shift\nexec "$@"\n')
    (bin_dir / "pct").write_text(
        "#!/bin/sh\n"
        f'case "$1" in\n  list) cat "{tmp_path}/pct-list.txt" ;;\n'
        f'  config) cat "{cfg_dir}/$2" 2>/dev/null || exit 2 ;;\n  *) exit 2 ;;\nesac\n'
    )
    for f in bin_dir.iterdir():
        f.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
    return subprocess.run(
        ["bash", "-c", f'source "{LIB}"; {call}'], env=env, capture_output=True, text=True, check=False
    )


@pytest.mark.parametrize(
    ("hostname", "bridge", "ip", "expected"),
    [
        ("lab-ntfy", "vmbr99", "10.99.0.222", 0),
        ("lab-ntfy", "vmbr0", "10.99.0.222", 1),
        ("ntfy", "vmbr99", "10.99.0.222", 1),
        ("lab-x", "vmbr99", "10.99.0.10", 1),
        ("lab-x", "vmbr99", "10.99.0.199", 1),
        ("lab-x", "vmbr99", "10.99.0.254", 0),
        ("lab-x", "vmbr99", "192.168.1.222", 1),
    ],
)
def test_is_lab_copy(tmp_path, hostname, bridge, ip, expected):
    proc = _bash(tmp_path, {"900": _cfg(hostname, bridge, ip)}, "is_lab_copy 900")
    assert proc.returncode == expected, proc.stderr


def test_list_lab_copies_only_prints_matches(tmp_path):
    configs = {
        "900": _cfg("lab-ntfy", "vmbr99", "10.99.0.222"),
        "100": _cfg("ntfy", "vmbr0", "192.168.1.222"),
        "901": _cfg("lab-rig", "vmbr99", "10.99.0.10"),
    }
    proc = _bash(tmp_path, configs, "list_lab_copies")
    assert proc.returncode == 0
    assert proc.stdout.strip().split("\t") == ["900", "lab-ntfy", "10.99.0.222"]
