from __future__ import annotations

import json
from pathlib import Path

from homelab_proxmox_orchestrator.inventory import render_inventory_yaml, update_inventory


def test_render_inventory_strips_cidr_and_sets_defaults() -> None:
    yaml_text = render_inventory_yaml(
        services={
            "immich": "10.0.0.10/24",
            "ntfy": "10.0.0.11/24",
        },
        ssh_private_key_file=None,
    )

    assert "immich" in yaml_text
    assert "10.0.0.10" in yaml_text
    assert "/24" not in yaml_text
    assert "ansible_user: ansible" in yaml_text
    assert "ansible_become: true" in yaml_text


def test_update_inventory_writes_expected_file_from_env_json(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path
    (repo_root / "ansible" / "inventories" / "generated").mkdir(parents=True, exist_ok=True)

    inv = {"services": {"svc": "192.168.50.5/32"}}
    monkeypatch.setenv("ANSIBLE_INVENTORY_JSON", json.dumps(inv))

    out = update_inventory(repo_root=repo_root)
    assert out == repo_root / "ansible" / "inventories" / "generated" / "hosts.yml"

    text = out.read_text(encoding="utf-8")
    assert "svc" in text
    assert "192.168.50.5" in text
    assert "/32" not in text

    # The generated inventory must expose a host_vars symlink (mirroring prod) so that
    # a per-service deploy loads ansible/host_vars/<service>.yml (e.g. fail2ban_jails).
    link = out.parent / "host_vars"
    assert link.is_symlink()
    assert link.readlink() == Path("../../host_vars")


def test_update_inventory_host_vars_symlink_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path
    (repo_root / "ansible" / "inventories" / "generated").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ANSIBLE_INVENTORY_JSON", json.dumps({"services": {"svc": "10.0.0.9/24"}}))

    first = update_inventory(repo_root=repo_root)
    # Running twice must not raise (symlink already present).
    update_inventory(repo_root=repo_root)
    link = first.parent / "host_vars"
    assert link.is_symlink()
    assert link.readlink() == Path("../../host_vars")
