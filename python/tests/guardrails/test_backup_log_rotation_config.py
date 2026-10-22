from __future__ import annotations

import subprocess
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


def _scan_function(repo_root: Path) -> str:
    script = (repo_root / "ansible/roles/proxmox_backup/templates/proxmox-config-backup.sh.j2").read_text()
    start = script.index("scan_plaintext_secrets() {")
    end = script.index("\n}\n", start) + 3
    return script[start:end]


def _run_scan(repo_root: Path, tmp_path: Path, files: dict[str, str]) -> subprocess.CompletedProcess[str]:
    for name, content in files.items():
        (tmp_path / name).write_text(content)
    return subprocess.run(
        ["bash", "-c", f'{_scan_function(repo_root)}\nscan_plaintext_secrets "$1"', "scan", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_pve_backup_secret_scan_ignores_non_secrets(tmp_path: Path) -> None:
    """Spec 089 T034: null/boolean values, public keys and references are not secrets."""
    repo_root = _find_repo_root(Path(__file__).resolve())
    result = _run_scan(repo_root, tmp_path, {
        "terraform.tfstate": (
            '{"keyctl": false, "password": null, "ssh_public_keys": "ssh-ed25519 AAAAC3Nza u@h",'
            ' "token_ttl": 3600, "api_key": ""}\n'
        ),
        "vars.yml": (
            'db_password: "{{ vault_db_password }}"\n'
            "tailscale_auth_key: !vault |\n"
            'age_public_key: "age19c6zxca9h88ru2szv0hqvahml6e0a524gu20t7juwhsvnjg6pyes4gn4k6"\n'
        ),
    })
    assert result.returncode == 0, f"false positives: {result.stdout}"
    assert result.stdout == ""


def test_pve_backup_secret_scan_catches_literal_secret_without_logging_it(tmp_path: Path) -> None:
    """Spec 089 T034: a literal value fails the scan; only file and key are printed."""
    repo_root = _find_repo_root(Path(__file__).resolve())
    result = _run_scan(repo_root, tmp_path, {
        "terraform.tfstate": '{"password": "hunter2-real", "keyctl": false}\n',
        "x.tfvars": 'api_token = "pve!ci=0f1e2d"\n',
    })
    assert result.returncode == 1
    assert "terraform.tfstate: password" in result.stdout
    assert "x.tfvars: api_token" in result.stdout
    assert "hunter2-real" not in result.stdout + result.stderr
    assert "0f1e2d" not in result.stdout + result.stderr


def test_pve_backup_notifies_through_ntfy_not_mail() -> None:
    """Spec 089 T035: mail hangs under ProtectSystem=strict; failures go to ntfy, bounded."""
    repo_root = _find_repo_root(Path(__file__).resolve())
    script = (repo_root / "ansible/roles/proxmox_backup/templates/proxmox-config-backup.sh.j2").read_text()
    conf = (repo_root / "ansible/roles/proxmox_backup/templates/proxmox-backup.conf.j2").read_text()

    assert "| mail " not in script, "the backup script must not call mail"
    assert "SMTP_HOST" not in conf and "EMAIL_TO" not in conf
    assert "--max-time" in script, "the ntfy publish must have a timeout"
    assert "?auth=" not in script, "the token must not go in the URL (082 publisher contract)"

    ntfy_users = yaml.safe_load((repo_root / "ansible/roles/ntfy/defaults/main.yml").read_text())["ntfy_users"]
    pve_vars = (repo_root / "ansible/group_vars/proxmox_hosts/vars.yml").read_text()
    entry = next(u for u in ntfy_users if u["name"] == "pve_backup")
    assert f'proxmox_backup_ntfy_topic: "{entry["topic"]}"' in pve_vars


def test_immich_restore_drill_uses_the_service_images() -> None:
    """Spec 089 T036: the drill restores into the same database and cache images as the service."""
    repo_root = _find_repo_root(Path(__file__).resolve())
    service = (repo_root / "ansible/roles/immich/templates/docker-compose.yml.j2").read_text()
    restore = (repo_root / "ansible/roles/immich_backup/templates/docker-compose.restore.yml.j2").read_text()
    for var in ("immich_postgres_image", "immich_redis_image"):
        assert f"image: {{{{ {var} }}}}" in service, f"service compose must use {var}"
        assert f"image: {{{{ {var} }}}}" in restore, f"restore compose must use {var}"
