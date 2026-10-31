"""Lab overrides (067, R-010): a lab copy only ever resolves lab addresses."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
ANSIBLE = ROOT / "ansible"
OVERRIDES = ANSIBLE / "inventories/lab/lab-overrides.yml"
LAB_HOSTS = ANSIBLE / "inventories/lab/hosts.yml"
PROD_HOSTS = ANSIBLE / "inventories/prod/hosts.yml"
SERVICE_ADDRESS = re.compile(r'^([a-z_]+_ip):\s*"192\.168\.1\.(2\d\d)"', re.M)


def _service_ip_keys() -> dict[str, str]:
    found: dict[str, str] = {}
    for rel in ("group_vars/services/vars.yml", "group_vars/all/vars.yml"):
        for key, last in SERVICE_ADDRESS.findall((ANSIBLE / rel).read_text()):
            found[key] = last
    return found


def test_every_service_address_variable_has_a_lab_mirror():
    overrides = yaml.safe_load(OVERRIDES.read_text())
    keys = _service_ip_keys()
    assert {"ntfy_ip", "reverse_proxy_ip", "monitoring_host_ip", "monitoring_ip"} <= set(keys)
    missing = [k for k in keys if k not in overrides]
    assert not missing, f"lab-overrides.yml lacks: {missing}"
    for key, last in keys.items():
        assert overrides[key] == f"10.99.0.{last}", key


def test_overrides_mark_the_run_as_lab():
    assert yaml.safe_load(OVERRIDES.read_text())["deploy_environment"] == "lab"


def test_lab_inventory_lists_all_services_at_lab_addresses():
    lab = yaml.safe_load(LAB_HOSTS.read_text())
    prod = yaml.safe_load(PROD_HOSTS.read_text())["all"]["children"]["services"]["hosts"]
    services = lab["all"]["children"]["services"]["hosts"]
    assert set(services) == set(prod) and len(services) == 13
    for name, host in services.items():
        last = prod[name]["ansible_host"].rsplit(".", 1)[1]
        assert host["ansible_host"] == f"10.99.0.{last}", name
        assert host["ansible_user"] == "root"
    assert str(lab["all"]["vars"]["lab_inventory"]).lower() == "true"
    assert "lab-pve-01" in lab["all"]["children"]["lab"]["hosts"], "the lab-rig group stays unchanged"
