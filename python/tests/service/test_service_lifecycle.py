from __future__ import annotations

from pathlib import Path

import pytest

from homelab_proxmox_orchestrator.service_lifecycle import ServiceConfig, add_service, change_service, remove_service


def test_add_service_creates_file_and_writes_new_schema(tmp_path: Path) -> None:
    repo_root = tmp_path
    out = add_service(repo_root=repo_root, hostname="svc", cfg=ServiceConfig(port="8080", path="/health"))

    assert out == repo_root / "ansible" / "host_vars" / "svc.yml"
    text = out.read_text(encoding="utf-8")
    assert "healthcheck_url:" in text
    assert "port: 8080" in text
    assert "path: /health" in text
    assert "healthcheck_profile: both" in text


def test_change_service_requires_existing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        change_service(repo_root=tmp_path, hostname="missing", cfg=ServiceConfig())


def test_remove_service_strips_healthcheck_keys(tmp_path: Path) -> None:
    repo_root = tmp_path
    host_vars_dir = repo_root / "ansible" / "host_vars"
    host_vars_dir.mkdir(parents=True)

    f = host_vars_dir / "svc.yml"
    f.write_text(
        """---
foo: bar
healthcheck_url:
  scheme: http
  port: 80
  path: /
healthcheck_profile: both
healthcheck_expect_status: 200

baz: qux
""",
        encoding="utf-8",
    )

    out = remove_service(repo_root=repo_root, hostname="svc")
    text = out.read_text(encoding="utf-8")

    assert "healthcheck_url" not in text
    assert "healthcheck_profile" not in text
    assert "healthcheck_expect_status" not in text
    assert "foo: bar" in text
    assert "baz: qux" in text
