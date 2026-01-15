from __future__ import annotations

import json
from pathlib import Path

from homelab_proxmox_orchestrator.inventory import render_inventory_yaml, update_inventory


def test_render_inventory_strips_cidr_and_sets_defaults() -> None:
    yaml_text = render_inventory_yaml(
        services={
            "immich": "10.0.0.10/24",
            "adguard": "10.0.0.11/24",
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
