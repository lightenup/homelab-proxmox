from __future__ import annotations

from pathlib import Path

import yaml


def _find_repo_root(start: Path) -> Path:
    current = start
    for _ in range(20):
        if (current / ".git").exists() and (current / "python").exists():
            return current
        if (current / "Taskfile.yml").exists() and (current / "python").exists():
            return current
        current = current.parent
    raise RuntimeError("Unable to locate repository root")


def test_pve_backup_unit_sandbox() -> None:
    """FR-001, FR-002, contract C1: unit sandbox must allow /run/lock and read /root."""
    repo_root = _find_repo_root(Path(__file__).resolve())
    unit = (repo_root / "ansible/roles/proxmox_backup/templates/proxmox-backup.service.j2").read_text()

    assert "ProtectHome=read-only" in unit, "ProtectHome must be read-only"
    assert "ProtectSystem=strict" in unit, "ProtectSystem must stay strict"
    assert "PrivateTmp=true" in unit, "PrivateTmp must stay true"
    assert "NoNewPrivileges=true" in unit, "NoNewPrivileges must stay true"
    assert "ProtectHome=true" not in unit, "ProtectHome=true must be replaced"

    rw_lines = [
        line for line in unit.splitlines()
        if line.strip().startswith("ReadWritePaths=")
    ]
    assert len(rw_lines) == 1, f"Expected exactly one ReadWritePaths= line, found {len(rw_lines)}"
    expected = "ReadWritePaths={{ proxmox_backup_staging_base }} {{ proxmox_backup_nas_mount_point }} /run/lock"
    assert rw_lines[0].strip() == expected, (
        f"ReadWritePaths must be exactly:\n  {expected}\n  got:\n  {rw_lines[0].strip()}"
    )


def test_pve_backup_deploy_uses_prod_inventory() -> None:
    """FR-003: backup deploy entry points must use inventories/prod/hosts.yml."""
    repo_root = _find_repo_root(Path(__file__).resolve())

    taskfile = (repo_root / "Taskfile.yml").read_text()
    script = (repo_root / "scripts/backup/run_proxmox_backup.sh").read_text()

    for name, content in [("Taskfile.yml", taskfile), ("run_proxmox_backup.sh", script)]:
        for line in content.splitlines():
            if "backup_proxmox.yml" in line:
                assert "inventories/prod/hosts.yml" in line, (
                    f"{name}: backup_proxmox.yml line must use inventories/prod/hosts.yml:\n  {line.strip()}"
                )
                assert "inventories/static" not in line, (
                    f"{name}: backup_proxmox.yml line must not reference inventories/static:\n  {line.strip()}"
                )


def test_pve_backup_doc_states_ci_limitation() -> None:
    """FR-014: docs must state the CI limitation for PVE backup deploy."""
    repo_root = _find_repo_root(Path(__file__).resolve())
    doc = (repo_root / "docs/operations/backups-proxmox-config.md").read_text()
    assert "## Deploy path and CI limitation" in doc, (
        "backups-proxmox-config.md must contain heading '## Deploy path and CI limitation'"
    )


def test_immich_playbook_applies_backup_role() -> None:
    """FR-004: immich.yml must apply immich_backup after immich."""
    repo_root = _find_repo_root(Path(__file__).resolve())
    playbook = yaml.safe_load(
        (repo_root / "ansible/playbooks/immich.yml").read_text()
    )

    target_play = None
    for play in playbook:
        if play.get("name") == "Configure Immich":
            target_play = play
            break

    assert target_play is not None, "Play 'Configure Immich' not found in immich.yml"
    roles = target_play.get("roles", [])
    assert "immich" in roles, "immich role missing"
    assert "immich_backup" in roles, "immich_backup role missing"
    assert roles.index("immich_backup") > roles.index("immich"), (
        "immich_backup must come after immich in the roles list"
    )


def test_immich_backup_role_asserts_nas_mount() -> None:
    """Spec edge case, research R5: first task in immich_backup must assert NAS mount."""
    repo_root = _find_repo_root(Path(__file__).resolve())
    tasks_file = (repo_root / "ansible/roles/immich_backup/tasks/main.yml").read_text()
    tasks = yaml.safe_load(tasks_file)

    assert isinstance(tasks, list) and len(tasks) > 0, "immich_backup/tasks/main.yml must have tasks"
    first = tasks[0]
    assert first.get("ansible.builtin.assert") is not None, (
        f"First task must use ansible.builtin.assert, got: {list(first.keys())}"
    )
    when = first.get("when", "")
    assert "immich_require_nas_mount" in when, (
        f"First task 'when' must mention immich_require_nas_mount, got: {when}"
    )


def test_standalone_immich_backup_playbook_removed() -> None:
    """FR-006: playbooks/backup.yml must be deleted and runbook must not reference it."""
    repo_root = _find_repo_root(Path(__file__).resolve())
    backup_playbook = repo_root / "ansible/playbooks/backup.yml"
    assert not backup_playbook.exists(), "ansible/playbooks/backup.yml must be deleted"

    runbook = (repo_root / "docs/runbooks/immich-backup-restore.md").read_text()
    assert "playbooks/backup.yml" not in runbook, (
        "immich-backup-restore.md must not reference playbooks/backup.yml"
    )


def test_docker_log_rotation_defaults() -> None:
    """FR-008, FR-009, contract C3: docker_daemon_options set once in services group_vars."""
    repo_root = _find_repo_root(Path(__file__).resolve())
    services_vars = yaml.safe_load(
        (repo_root / "ansible/group_vars/services/vars.yml").read_text()
    )

    expected = {"log-driver": "json-file", "log-opts": {"max-size": "10m", "max-file": "3"}}
    actual = services_vars.get("docker_daemon_options")
    assert actual == expected, (
        f"docker_daemon_options must equal {expected}, got: {actual}"
    )

    monitoring_vars_path = repo_root / "ansible/group_vars/monitoring/vars.yml"
    if monitoring_vars_path.exists():
        monitoring_vars = yaml.safe_load(monitoring_vars_path.read_text())
        assert "docker_daemon_options" not in monitoring_vars, (
            "docker_daemon_options must not be defined in monitoring/vars.yml (single definition)"
        )
