"""Duplicate-LXC guard (scripts/lab/lib/ct_conflicts.sh).

On 2026-10-28 a deploy created VMID 112 with the IP of an untracked VMID 104 (192.168.1.212):
Terraform state was empty, and the old name-only check read the container name from the Lock
column of `pct list`, so it never matched. These tests drive the shell library with a fake
`sudo`/`pct` on PATH.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
LIB = ROOT / "scripts/lab/lib/ct_conflicts.sh"

PCT_LIST = """VMID       Status     Lock         Name
100        running                 jellyfin
104        running                 homeassistant
108        running    backup       proxy
"""
PCT_CONFIG = {
    "100": "hostname: jellyfin\nnet0: name=eth0,bridge=vmbr0,gw=192.168.1.1,ip=192.168.1.215/24,type=veth\n",
    "104": "hostname: homeassistant\nnet0: name=eth0,bridge=vmbr0,gw=192.168.1.1,ip=192.168.1.212/24,type=veth\n",
    "108": "hostname: proxy\nnet0: name=eth0,bridge=vmbr0,gw=192.168.1.1,ip=192.168.1.211/24,type=veth\n",
}


def _lxc(address: str, actions: list[str], hostname: str, ip: str) -> dict:
    return {
        "address": address,
        "type": "proxmox_lxc",
        "change": {"actions": actions, "after": {"hostname": hostname, "network": [{"ip": ip}]}},
    }


def _run(tmp_path: Path, resource_changes: list[dict], pct_list: str = PCT_LIST) -> tuple[int, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "sudo").write_text('#!/bin/sh\n[ "$1" = "-n" ] && shift\nexec "$@"\n')
    configs = tmp_path / "configs"
    configs.mkdir()
    for vmid, text in PCT_CONFIG.items():
        (configs / vmid).write_text(text)
    (tmp_path / "pct-list.txt").write_text(pct_list)
    (bin_dir / "pct").write_text(
        "#!/bin/sh\n"
        f'case "$1" in\n'
        f'  list) cat "{tmp_path}/pct-list.txt" ;;\n'
        f'  config) cat "{configs}/$2" 2>/dev/null || exit 2 ;;\n'
        "  *) exit 2 ;;\n"
        "esac\n"
    )
    for f in bin_dir.iterdir():
        f.chmod(0o755)

    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"resource_changes": resource_changes}))
    report = tmp_path / "report.txt"
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
    proc = subprocess.run(
        ["bash", "-c", f'source "{LIB}"; enforce_no_ct_conflicts "{plan}" "{report}"'],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, report.read_text() if report.exists() else proc.stderr


def test_denies_the_2026_10_28_duplicate(tmp_path: Path) -> None:
    rc, report = _run(
        tmp_path,
        [_lxc("module.homeassistant_lxc.proxmox_lxc.this", ["create"], "homeassistant", "192.168.1.212/24")],
    )
    assert rc == 1
    assert "IP 192.168.1.212 already used by CTID(s) 104" in report
    assert "hostname homeassistant already used by CTID(s) 104" in report


def test_denies_ip_clash_even_when_hostname_differs(tmp_path: Path) -> None:
    rc, report = _run(
        tmp_path, [_lxc("module.reverse_proxy_lxc.proxmox_lxc.this", ["create"], "caddy", "192.168.1.211/24")]
    )
    assert rc == 1
    assert "IP 192.168.1.211 already used by CTID(s) 108" in report


def test_reads_containers_that_hold_a_lock(tmp_path: Path) -> None:
    """The old check broke on the Lock column; a locked CT must still be seen."""
    rc, report = _run(tmp_path, [_lxc("module.x_lxc.proxmox_lxc.this", ["create"], "proxy", "192.168.1.250/24")])
    assert rc == 1
    assert "hostname proxy already used by CTID(s) 108" in report


def test_allows_a_create_with_a_free_hostname_and_ip(tmp_path: Path) -> None:
    rc, report = _run(tmp_path, [_lxc("module.new_lxc.proxmox_lxc.this", ["create"], "new", "192.168.1.230/24")])
    assert rc == 0, report
    assert report.startswith("ALLOW")


@pytest.mark.parametrize("actions", [["no-op"], ["update"], ["delete", "create"], ["create", "delete"]])
def test_ignores_everything_but_a_fresh_create(tmp_path: Path, actions: list[str]) -> None:
    rc, report = _run(
        tmp_path, [_lxc("module.homeassistant_lxc.proxmox_lxc.this", actions, "homeassistant", "192.168.1.212/24")]
    )
    assert rc == 0, report
    assert "plan creates no new LXC" in report


def test_fails_closed_when_pct_lists_nothing(tmp_path: Path) -> None:
    rc, report = _run(
        tmp_path,
        [_lxc("module.new_lxc.proxmox_lxc.this", ["create"], "new", "192.168.1.230/24")],
        pct_list="",
    )
    assert rc == 1
    assert "could not list existing containers" in report


def test_deploy_script_runs_the_guard_in_plan_and_apply() -> None:
    text = (ROOT / "scripts/lab/pve-service-deploy").read_text()
    assert 'source "${LIB_DIR}/ct_conflicts.sh"' in text
    assert text.count("enforce_no_ct_conflicts ") == 2
    assert "$4==s" not in text, "the Lock-column name check must not come back"
