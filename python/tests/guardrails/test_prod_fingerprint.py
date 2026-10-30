"""Production fingerprint (067, R-009, SC-001): prove a LAB run left production untouched."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LIB = ROOT / "scripts/lab/lib/fingerprint.sh"
CT_LIB = ROOT / "scripts/lab/lib/ct_conflicts.sh"


def _cfg(hostname: str, bridge: str, ip: str, extra: str = "") -> str:
    return f"hostname: {hostname}\nnet0: name=eth0,bridge={bridge},gw=192.168.1.1,ip={ip}/24,type=veth\n{extra}"


class Host:
    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.bin = tmp / "bin"
        self.cts = tmp / "cts"
        self.docker = tmp / "docker"
        self.status = tmp / "status"
        self.state = tmp / "state"
        self.tfvars = tmp / "tfvars"
        for d in (self.bin, self.cts, self.docker, self.status, self.state / "prod/ntfy", self.tfvars):
            d.mkdir(parents=True)
        (self.state / "prod/ntfy/terraform.tfstate").write_text('{"serial": 1}\n')
        (self.tfvars / "prod.tfvars").write_text('storage_pool = "local-lvm"\n')
        (self.bin / "sudo").write_text('#!/bin/sh\n[ "$1" = "-n" ] && shift\nexec "$@"\n')
        (self.bin / "pct").write_text(
            "#!/bin/sh\n"
            'case "$1" in\n'
            f'  list) echo "VMID Status Lock Name"; for f in "{self.cts}"/*; do v=$(basename $f); '
            f's=$(cat "{self.status}/$v" 2>/dev/null || echo running); echo "$v $s x"; done ;;\n'
            f'  config) cat "{self.cts}/$2" 2>/dev/null || exit 2 ;;\n'
            f'  exec) v="$2"; [ -f "{self.docker}/$v.fail" ] && exit 1; cat "{self.docker}/$v" 2>/dev/null || echo __NODOCKER__ ;;\n'
            "  *) exit 2 ;;\n"
            "esac\n"
        )
        for f in self.bin.iterdir():
            f.chmod(0o755)

    def ct(self, vmid, hostname, bridge="vmbr0", ip="192.168.1.222", extra="", docker=None):
        (self.cts / str(vmid)).write_text(_cfg(hostname, bridge, ip, extra))
        if docker is not None:
            (self.docker / str(vmid)).write_text(docker)

    def fingerprint(self, phase: str, name: str) -> tuple[subprocess.CompletedProcess[str], Path]:
        out = self.tmp / name
        env = {
            **os.environ,
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "STATE_ROOT": str(self.state),
            "TFVARS_DIR": str(self.tfvars),
        }
        proc = subprocess.run(
            ["bash", "-c", f'source "{CT_LIB}"; source "{LIB}"; prod_fingerprint "{out}" {phase}'],
            env=env, capture_output=True, text=True, check=False,
        )
        return proc, out

    def diff(self, before: Path, after: Path) -> tuple[subprocess.CompletedProcess[str], Path]:
        diff = self.tmp / "diff.txt"
        proc = subprocess.run(
            ["bash", "-c", f'source "{LIB}"; fingerprint_diff "{before}" "{after}" "{diff}"'],
            capture_output=True, text=True, check=False,
        )
        return proc, diff


def _host(tmp_path: Path) -> Host:
    h = Host(tmp_path)
    h.ct(111, "ntfy", docker="abc123 2026-10-29 ntfy\n")
    h.ct(112, "homeassistant", ip="192.168.1.212", docker="def456 2026-10-28 ha\n")
    return h


def test_schema_and_contents(tmp_path):
    h = _host(tmp_path)
    proc, out = h.fingerprint("before", "a.json")
    assert proc.returncode == 0, proc.stderr
    fp = json.loads(out.read_text())
    assert fp["schema_version"] == "1.0.0" and fp["phase"] == "before"
    assert fp["states"]["ntfy"].startswith("sha256:")
    assert fp["tfvars_prod"].startswith("sha256:")
    ids = {c["vmid"]: c for c in fp["containers"]}
    assert set(ids) == {111, 112}
    assert ids[111]["hostname"] == "ntfy" and ids[111]["status"] == "running"
    assert ids[111]["workload"] == ["abc123 2026-10-29 ntfy"]
    assert any("bridge=vmbr0" in n for n in ids[111]["net"])


def test_lab_copies_are_excluded_and_lock_lines_are_stripped(tmp_path):
    h = _host(tmp_path)
    h.ct(130, "lab-ntfy", bridge="vmbr99", ip="10.99.0.222")
    proc, a = h.fingerprint("before", "a.json")
    assert 130 not in {c["vmid"] for c in json.loads(a.read_text())["containers"]}
    h.ct(111, "ntfy", extra="lock: backup\n", docker="abc123 2026-10-29 ntfy\n")
    _, b = h.fingerprint("after", "b.json")
    p, diff = h.diff(a, b)
    assert p.returncode == 0 and not diff.exists()


def test_identical_inputs_exit_zero_with_no_diff_file(tmp_path):
    h = _host(tmp_path)
    _, a = h.fingerprint("before", "a.json")
    _, b = h.fingerprint("after", "b.json")
    p, diff = h.diff(a, b)
    assert p.returncode == 0
    assert not diff.exists()


def _changed(h: Host, mutate) -> str:
    _, a = h.fingerprint("before", "a.json")
    mutate()
    _, b = h.fingerprint("after", "b.json")
    p, diff = h.diff(a, b)
    assert p.returncode != 0
    return diff.read_text()


def test_changed_state_checksum_is_reported(tmp_path):
    h = _host(tmp_path)
    text = _changed(h, lambda: (h.state / "prod/ntfy/terraform.tfstate").write_text('{"serial": 2}\n'))
    assert "ntfy" in text and "states" in text


def test_changed_net0_is_reported(tmp_path):
    h = _host(tmp_path)
    text = _changed(h, lambda: h.ct(111, "ntfy", ip="192.168.1.99", docker="abc123 2026-10-29 ntfy\n"))
    assert "111" in text and "192.168.1.99" in text


def test_new_vmid_is_reported(tmp_path):
    h = _host(tmp_path)
    assert "113" in _changed(h, lambda: h.ct(113, "stray"))


def test_missing_vmid_is_reported(tmp_path):
    h = _host(tmp_path)
    assert "112" in _changed(h, lambda: (h.cts / "112").unlink())


def test_status_change_is_reported(tmp_path):
    h = _host(tmp_path)
    assert "stopped" in _changed(h, lambda: (h.status / "111").write_text("stopped\n"))


def test_changed_workload_identity_is_reported(tmp_path):
    h = _host(tmp_path)
    text = _changed(h, lambda: (h.docker / "111").write_text("zzz999 2026-10-30 ntfy\n"))
    assert "zzz999" in text


def test_pct_exec_failure_records_unreadable_and_fails_the_comparison(tmp_path):
    h = _host(tmp_path)
    _, a = h.fingerprint("before", "a.json")
    (h.docker / "111.fail").write_text("")
    proc, b = h.fingerprint("after", "b.json")
    assert json.loads(b.read_text())["containers"][0]["workload"] == ["unreadable"]
    p, _ = h.diff(a, b)
    assert p.returncode != 0
    # unreadable on both sides must still fail: it proves nothing
    _, c = h.fingerprint("after", "c.json")
    p, _ = h.diff(b, c)
    assert p.returncode != 0
