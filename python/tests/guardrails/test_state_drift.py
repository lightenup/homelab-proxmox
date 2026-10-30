"""Nightly state-drift check (067, contracts/state-drift-metrics.md).

Drives scripts/lab/state-drift-check with a fake `sudo`/`pct`, a fake state/prod tree and a
temp textfile directory.
"""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts/lab/state-drift-check"


def _cfg(hostname: str, bridge: str, ip: str) -> str:
    gw = "10.99.0.1" if bridge == "vmbr99" else "192.168.1.1"
    return f"hostname: {hostname}\nnet0: name=eth0,bridge={bridge},gw={gw},ip={ip}/24,type=veth\n"


class Env:
    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.bin = tmp / "bin"
        self.cts = tmp / "cts"
        self.state = tmp / "state"
        self.artifacts = tmp / "artifacts"
        self.textfile = tmp / "textfile"
        self.scratch = tmp / "scratch"
        self.ignore = tmp / "ignore.txt"
        self.pct_log = tmp / "pct.log"
        for d in (self.bin, self.cts, self.state / "prod", self.state / "lab", self.textfile, self.scratch):
            d.mkdir(parents=True)
        self.ignore.write_text("# <vmid> <reason>\n")
        (self.bin / "sudo").write_text('#!/bin/sh\n[ "$1" = "-n" ] && shift\nexec "$@"\n')
        (self.bin / "pct").write_text(
            "#!/bin/sh\n"
            f'echo "$@" >> "{self.pct_log}"\n'
            'case "$1" in\n'
            f'  list) echo "VMID Status Lock Name"; for f in "{self.cts}"/*; do [ -e "$f" ] && echo "$(basename $f) running x"; done ;;\n'
            f'  config) cat "{self.cts}/$2" 2>/dev/null || exit 2 ;;\n'
            f'  stop) exit 0 ;;\n'
            f'  destroy) rm -f "{self.cts}/$2" ;;\n'
            "  *) exit 2 ;;\n"
            "esac\n"
        )
        for f in self.bin.iterdir():
            f.chmod(0o755)

    def ct(self, vmid: int, hostname: str, bridge: str = "vmbr0", ip: str = "192.168.1.50") -> None:
        (self.cts / str(vmid)).write_text(_cfg(hostname, bridge, ip))

    def tracked(self, service: str, vmid: int, env: str = "prod") -> None:
        d = self.state / env / service
        d.mkdir(parents=True, exist_ok=True)
        (d / "terraform.tfstate").write_text(
            json.dumps(
                {
                    "version": 4,
                    "resources": [
                        {
                            "type": "proxmox_lxc",
                            "instances": [{"attributes": {"id": f"pve/lxc/{vmid}", "vmid": None, "hostname": service}}],
                        }
                    ],
                }
            )
        )

    def run(self) -> subprocess.CompletedProcess[str]:
        env = {
            **os.environ,
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "STATE_ROOT": str(self.state),
            "ARTIFACT_ROOT": str(self.artifacts),
            "TEXTFILE_DIR": str(self.textfile),
            "SCRATCH_ROOT": str(self.scratch),
            "DRIFT_IGNORE_FILE": str(self.ignore),
        }
        return subprocess.run([str(SCRIPT)], env=env, capture_output=True, text=True, check=False)

    def report(self) -> dict:
        return json.loads((self.artifacts / "state-drift/latest.json").read_text())

    def prom(self) -> str:
        return (self.textfile / "state_drift.prom").read_text()


def _env(tmp_path: Path) -> Env:
    e = Env(tmp_path)
    e.ct(100, "jellyfin", ip="192.168.1.215")
    e.tracked("jellyfin", 100)
    return e


def test_clean_host_reports_zero_everywhere(tmp_path):
    e = _env(tmp_path)
    proc = e.run()
    assert proc.returncode == 0, proc.stderr
    assert e.report()["ok"] is True
    prom = e.prom()
    for kind in ("untracked", "double_tracked", "lab_leftover"):
        assert f'homelab_state_drift_containers{{kind="{kind}"}} 0' in prom
    assert "homelab_state_drift_last_success_timestamp_seconds " in prom


def test_untracked_container_is_reported_with_vmid_and_hostname(tmp_path):
    e = _env(tmp_path)
    e.ct(104, "drift-test", bridge="vmbr0", ip="192.168.1.212")
    assert e.run().returncode == 0
    assert e.report()["untracked"] == [{"vmid": 104, "hostname": "drift-test"}]
    assert 'homelab_state_drift_containers{kind="untracked"} 1' in e.prom()


def test_vmid_in_two_states_is_double_tracked(tmp_path):
    e = _env(tmp_path)
    e.tracked("immich", 100)
    assert e.run().returncode == 0
    assert e.report()["double_tracked"] == [{"vmid": 100, "states": ["immich", "jellyfin"]}]
    assert 'homelab_state_drift_containers{kind="double_tracked"} 1' in e.prom()


def test_lab_copy_is_swept_and_counted(tmp_path):
    e = _env(tmp_path)
    e.ct(130, "lab-ntfy", bridge="vmbr99", ip="10.99.0.222")
    (e.scratch / "run-1" / "data").mkdir(parents=True)
    (e.state / "lab/ntfy").mkdir()
    assert e.run().returncode == 0
    assert e.report()["lab_leftover"] == [{"vmid": 130, "hostname": "lab-ntfy", "swept": True}]
    assert 'homelab_state_drift_containers{kind="lab_leftover"} 1' in e.prom()
    assert not (e.cts / "130").exists()
    assert "destroy 130" in e.pct_log.read_text()
    assert not any(e.scratch.iterdir())
    assert not (e.state / "lab/ntfy").exists()
    # A swept lab copy is not also reported as untracked.
    assert e.report()["untracked"] == []


def test_production_container_is_never_destroyed(tmp_path):
    e = _env(tmp_path)
    e.ct(104, "drift-test")
    e.run()
    assert "destroy" not in e.pct_log.read_text()


def test_ignore_list_entry_is_not_counted(tmp_path):
    e = _env(tmp_path)
    e.ct(104, "drift-test")
    e.ignore.write_text("# <vmid> <reason>\n104 hand-made test CT, kept on purpose\n")
    assert e.run().returncode == 0
    assert e.report()["untracked"] == []
    assert 'homelab_state_drift_containers{kind="untracked"} 0' in e.prom()


def test_lock_held_exits_zero_and_leaves_the_timestamp_alone(tmp_path):
    e = _env(tmp_path)
    assert e.run().returncode == 0
    before = e.prom()
    e.ct(104, "drift-test")
    with open(e.state / "lab/.lock", "w") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        proc = e.run()
    assert proc.returncode == 0
    assert e.prom() == before
    assert e.report()["untracked"] == []


def test_unreadable_container_list_fails_without_touching_the_metrics(tmp_path):
    e = _env(tmp_path)
    assert e.run().returncode == 0
    before = e.prom()
    (e.bin / "pct").write_text("#!/bin/sh\nexit 1\n")
    proc = e.run()
    assert proc.returncode != 0
    assert e.prom() == before


def test_textfile_is_written_by_rename(tmp_path):
    text = SCRIPT.read_text()
    assert "os.replace(tmp" in text
    e = _env(tmp_path)
    assert e.run().returncode == 0
    assert [p.name for p in e.textfile.iterdir()] == ["state_drift.prom"]
