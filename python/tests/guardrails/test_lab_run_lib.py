"""Behaviour of the LAB run building blocks (scripts/lab/lib/lab_run.sh), with a fake pct."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LIBS = [ROOT / "scripts/lab/lib/ct_conflicts.sh", ROOT / "scripts/lab/lib/lab_run.sh"]


class Host:
    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.bin, self.cts = tmp / "bin", tmp / "cts"
        self.state, self.scratch = tmp / "state", tmp / "scratch"
        self.log = tmp / "pct.log"
        self.reachable = tmp / "reachable"
        for d in (self.bin, self.cts, self.state / "lab", self.scratch):
            d.mkdir(parents=True)
        (self.bin / "sudo").write_text('#!/bin/sh\n[ "$1" = "-n" ] && shift\nexec "$@"\n')
        (self.bin / "pct").write_text(
            "#!/bin/sh\n"
            f'echo "$@" >> "{self.log}"\n'
            'case "$1" in\n'
            f'  list) echo "VMID Status Lock Name"; for f in "{self.cts}"/*; do [ -e "$f" ] && echo "$(basename $f) running x"; done ;;\n'
            f'  config) cat "{self.cts}/$2" 2>/dev/null || exit 2 ;;\n'
            "  stop) exit 0 ;;\n"
            f'  destroy) [ -f "{tmp}/destroy-fails" ] && exit 1; rm -f "{self.cts}/$2" ;;\n'
            # exec <vmid> -- timeout 3 bash -c </dev/tcp/H/P> : reachable iff "H:P" is listed
            '  exec) target=$(echo "$*" | grep -o "tcp/[^>]*" | sed "s#tcp/##; s#/#:#"); '
            f'grep -qx "$target" "{self.reachable}" ;;\n'
            "  *) exit 2 ;;\n"
            "esac\n"
        )
        (self.bin / "chown").write_text("#!/bin/sh\nexit 0\n")  # sudo chown 100000:100000 needs root
        for f in self.bin.iterdir():
            f.chmod(0o755)
        self.reachable.write_text("")

    def ct(self, vmid, hostname, bridge="vmbr99", ip="10.99.0.222"):
        (self.cts / str(vmid)).write_text(
            f"hostname: {hostname}\nnet0: name=eth0,bridge={bridge},gw=10.99.0.1,ip={ip}/24,type=veth\n")

    def run(self, call: str) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, "PATH": f"{self.bin}:{os.environ['PATH']}",
               "STATE_ROOT": str(self.state), "SCRATCH_ROOT": str(self.scratch)}
        sources = "; ".join(f'source "{p}"' for p in LIBS)
        return subprocess.run(["bash", "-c", f"{sources}; {call}"], env=env, capture_output=True, text=True, check=False)


def test_sweep_removes_lab_copies_scratch_and_state_but_never_production(tmp_path):
    h = Host(tmp_path)
    h.ct(130, "lab-ntfy")
    h.ct(111, "ntfy", bridge="vmbr0", ip="192.168.1.222")
    (h.scratch / "old-run/data").mkdir(parents=True)
    (h.state / "lab/ntfy").mkdir()
    proc = h.run(f'lab_lock_acquire && lab_sweep "{tmp_path}/sweep.json"')
    assert proc.returncode == 0, proc.stderr
    assert not (h.cts / "130").exists() and (h.cts / "111").exists()
    assert not any(h.scratch.iterdir())
    assert not (h.state / "lab/ntfy").exists()
    assert json.loads((tmp_path / "sweep.json").read_text())["ok"] is True


def test_lock_held_by_another_run_is_refused(tmp_path):
    h = Host(tmp_path)
    holder = subprocess.Popen(["bash", "-c", f'exec 8>"{h.state}/lab/.lock"; flock -n 8; sleep 5'])
    try:
        import time
        time.sleep(0.5)
        proc = h.run("lab_lock_acquire")
    finally:
        holder.kill()
    assert proc.returncode != 0
    assert f"lab: another LAB run holds {h.state}/lab/.lock" in proc.stderr


def test_scratch_dirs_follow_the_service_mount_keys(tmp_path):
    h = Host(tmp_path)
    tfvars = tmp_path / "lab.tfvars"
    tfvars.write_text(
        'service_mountpoints = {\n  immich = {\n    library = {\n      mp = "/mnt/immich"\n      volume = "/x/library"\n    }\n'
        '    external_photo = {\n      mp = "/p"\n      volume = "/x/external_photo"\n      readonly = true\n    }\n  }\n'
        '  jellyfin = {\n    video = {\n      mp = "/v"\n      volume = "/x/video"\n    }\n  }\n}\n')
    proc = h.run(f'lab_scratch_create run-1 immich "{tfvars}" "{tmp_path}/scratch.json"')
    assert proc.returncode == 0, proc.stderr
    assert sorted(p.name for p in (h.scratch / "run-1").iterdir()) == ["external_photo", "library"]
    assert set(json.loads((tmp_path / "scratch.json").read_text())) == {"library", "external_photo"}


def test_service_without_mounts_writes_no_scratch_report(tmp_path):
    h = Host(tmp_path)
    tfvars = tmp_path / "lab.tfvars"
    tfvars.write_text("service_mountpoints = {\n}\n")
    assert h.run(f'lab_scratch_create run-1 ntfy "{tfvars}" "{tmp_path}/scratch.json"').returncode == 0
    assert not (tmp_path / "scratch.json").exists()


def _lab_state(h: Host) -> None:
    d = h.state / "lab/ntfy"
    d.mkdir(parents=True)
    (d / "terraform.tfstate").write_text(json.dumps({"resources": [{"module": "module.ntfy_lxc", "type": "proxmox_lxc", "name": "this", "instances": [
        {"attributes": {"id": "pve/lxc/130", "hostname": "lab-ntfy", "network": [{"bridge": "vmbr99", "ip": "10.99.0.222/24"}]}}]}]}))
    h.ct(130, "lab-ntfy")
    (h.scratch / "run-1/data").mkdir(parents=True)


def test_teardown_falls_back_to_pct_and_removes_everything(tmp_path):
    h = Host(tmp_path)
    _lab_state(h)
    proc = h.run(f'lab_teardown ntfy run-1 "{tmp_path}/lab.tfvars" "{tmp_path}/teardown.json" false')
    assert proc.returncode == 0, proc.stderr
    report = json.loads((tmp_path / "teardown.json").read_text())
    assert report == {"destroyed_by": "pct", "vmid": "130", "scratch_removed": True, "lab_state_removed": True, "ok": True}
    assert not (h.cts / "130").exists() and not (h.scratch / "run-1").exists() and not (h.state / "lab/ntfy").exists()


def test_teardown_reports_failure_when_the_container_survives(tmp_path):
    h = Host(tmp_path)
    _lab_state(h)
    (tmp_path / "destroy-fails").write_text("")
    proc = h.run(f'lab_teardown ntfy run-1 "{tmp_path}/lab.tfvars" "{tmp_path}/teardown.json" false')
    assert proc.returncode != 0
    assert json.loads((tmp_path / "teardown.json").read_text())["ok"] is False
    assert (h.state / "lab/ntfy/terraform.tfstate").exists(), "keep the state so the next sweep can find it"


def test_teardown_refuses_a_state_that_holds_production(tmp_path):
    h = Host(tmp_path)
    _lab_state(h)
    state = h.state / "lab/ntfy/terraform.tfstate"
    state.write_text(state.read_text().replace("lab-ntfy", "ntfy"))
    proc = h.run(f'lab_teardown ntfy run-1 "{tmp_path}/lab.tfvars" "{tmp_path}/teardown.json" false')
    assert proc.returncode != 0
    assert "refusing to destroy" in proc.stderr
    assert (h.cts / "130").exists()


def test_isolation_probe_passes_when_only_the_internet_is_reachable(tmp_path):
    h = Host(tmp_path)
    h.reachable.write_text("deb.debian.org:443\n")
    proc = h.run(f'lab_isolation_probe 130 "{tmp_path}/isolation.json"')
    assert proc.returncode == 0, proc.stderr
    results = json.loads((tmp_path / "isolation.json").read_text())
    assert len(results) == 6 and all(r["ok"] for r in results)


def test_isolation_probe_fails_when_a_production_target_is_reachable(tmp_path):
    h = Host(tmp_path)
    h.reachable.write_text("deb.debian.org:443\n192.168.1.214:9090\n")
    proc = h.run(f'lab_isolation_probe 130 "{tmp_path}/isolation.json"')
    assert proc.returncode != 0
    assert "lab isolation broken: 192.168.1.214:9090 reachable from lab copy" in proc.stderr


def test_isolation_probe_fails_when_the_internet_is_unreachable(tmp_path):
    h = Host(tmp_path)
    proc = h.run(f'lab_isolation_probe 130 "{tmp_path}/isolation.json"')
    assert proc.returncode != 0
    assert "internet is unreachable" in proc.stderr


def test_inventory_guard_refuses_a_host_outside_the_lab_net(tmp_path):
    h = Host(tmp_path)
    inv = tmp_path / "inv.json"
    inv.write_text(json.dumps({"_meta": {"hostvars": {"ntfy": {"ansible_host": "10.99.0.222"}, "monitoring": {"ansible_host": "192.168.1.214"}}}}))
    proc = h.run(f'lab_inventory_guard "{inv}" "{tmp_path}/guard.txt"')
    assert proc.returncode != 0
    assert "lab inventory resolves monitoring to 192.168.1.214, outside 10.99.0.0/24" in proc.stderr
    inv.write_text(json.dumps({"_meta": {"hostvars": {"ntfy": {"ansible_host": "10.99.0.222"}}}}))
    assert h.run(f'lab_inventory_guard "{inv}" "{tmp_path}/guard.txt"').returncode == 0
