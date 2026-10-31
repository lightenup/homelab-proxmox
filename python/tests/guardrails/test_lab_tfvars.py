"""Lab tfvars are derived from prod tfvars (067, R-002): lab address space, scratch mounts, prefix."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
LIB = ROOT / "scripts/lab/lib/tfvars.sh"
PROD_TEMPLATE = ROOT / "terraform/environments/prod.tfvars.template"
SCRATCH = "/var/lib/homelab-proxmox/lab-scratch/run-1"


def _derive(tmp_path: Path, prod_text: str) -> tuple[subprocess.CompletedProcess[str], Path]:
    prod = tmp_path / "prod.tfvars"
    prod.write_text(prod_text)
    out = tmp_path / "lab.tfvars"
    proc = subprocess.run(
        ["bash", "-c", f'source "{LIB}"; _tfvars_derive_lab "{prod}" "{out}" "{SCRATCH}"'],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc, out


@pytest.fixture
def derived(tmp_path):
    proc, out = _derive(tmp_path, PROD_TEMPLATE.read_text())
    assert proc.returncode == 0, proc.stderr
    return out.read_text()


def test_network_and_prefix(derived):
    assert re.search(r'^services_bridge\s*=\s*"vmbr99"', derived, re.M)
    assert re.search(r'^network_gateway\s*=\s*"10\.99\.0\.1"', derived, re.M)
    assert re.search(r'^hostname_prefix\s*=\s*"lab-"', derived, re.M)


def test_every_service_ip_mirrors_into_the_lab_range(derived):
    block = re.search(r"service_ips\s*=\s*\{(.*?)\n\}", derived, re.S).group(1)
    ips = re.findall(r'"(\d+\.\d+\.\d+\.\d+)/24"', block)
    assert len(ips) == 13
    for ip in ips:
        assert ip.startswith("10.99.0."), ip
        assert 200 <= int(ip.rsplit(".", 1)[1]) <= 254
    assert "192.168.1." not in block
    assert "10.99.0.222/24" in block  # ntfy: .222 mirrors


def test_every_mount_volume_is_scratch_and_readonly_is_kept(derived):
    mounts = re.search(r"service_mountpoints\s*=\s*\{(.*?)\n\}\n", derived, re.S).group(1)
    volumes = re.findall(r'volume\s*=\s*"([^"]+)"', mounts)
    assert len(volumes) == 9
    assert all(v.startswith(SCRATCH + "/") for v in volumes), volumes
    assert "/mnt/nas" not in mounts
    assert mounts.count("readonly = true") == 2
    assert f'volume   = "{SCRATCH}/external_photo"' in mounts


def test_credentials_and_host_api_are_carried_over_unchanged(derived):
    assert 'proxmox_api_token_secret = "__INJECT_TOKEN_SECRET__"' in derived
    assert 'proxmox_api_url = "https://192.168.1.112:8006/api2/json"' in derived
    assert "ssh-ed25519" in derived


@pytest.mark.parametrize("last_octet", [1, 10, 11, 100, 199, 255])
def test_reserved_or_out_of_range_mirror_is_refused(tmp_path, last_octet):
    text = PROD_TEMPLATE.read_text().replace("192.168.1.222/24", f"192.168.1.{last_octet}/24")
    proc, out = _derive(tmp_path, text)
    assert proc.returncode != 0
    assert "10.99.0." in proc.stderr and "200" in proc.stderr
    assert not out.exists()


def test_a_prod_address_outside_the_lan_is_refused(tmp_path):
    text = PROD_TEMPLATE.read_text().replace("192.168.1.222/24", "172.16.0.5/24")
    proc, _ = _derive(tmp_path, text)
    assert proc.returncode != 0
