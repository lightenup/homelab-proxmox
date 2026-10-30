from __future__ import annotations

import re
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


ROOT = _find_repo_root(Path(__file__).resolve())
ANSIBLE = ROOT / "ansible"
EXPECTED_SCHEDULES = {
    "nextcloud": "*-*-* 04:00:00",
    "financial-scenario": "*-*-* 04:15:00",
    "immich": "*-*-* 04:30:00",
    "hermes": "*-*-* 04:45:00",
    "homeassistant": "*-*-* 05:15:00",
}


def _service_backups() -> dict:
    data = yaml.safe_load((ANSIBLE / "group_vars/all/vars.yml").read_text())
    assert "service_backups" in data, "service_backups missing from group_vars/all/vars.yml"
    return data["service_backups"]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text()


def test_old_backup_roles_removed() -> None:
    """FR-003, SC-006: the four per-service backup roles and monitoring's own backup are gone."""
    for role in ("financial_scenario_backup", "hermes_backup", "immich_backup", "nextcloud_backup"):
        assert not (ANSIBLE / "roles" / role).exists(), f"role {role} must be removed"
    assert not (ANSIBLE / "roles/monitoring_stack/templates/backup-monitoring.sh.j2").exists()
    assert not (ANSIBLE / "roles/monitoring_stack/tasks/backup_cron.yml").exists()

    for path in ANSIBLE.rglob("*"):
        if not path.is_file() or path.suffix in {".retry"}:
            continue
        text = path.read_text(errors="ignore")
        assert "HermesBackupStale" not in text, f"{path} still names HermesBackupStale"
        assert "hermes_backup_last_success" not in text, f"{path} still names hermes_backup_last_success"


def test_service_backups_map_shape() -> None:
    """FR-005, data-model: one map keyed by backup name drives roles, units and the alert."""
    backups = _service_backups()
    hosts = yaml.safe_load((ANSIBLE / "inventories/prod/hosts.yml").read_text())
    service_hosts = set(hosts["all"]["children"]["services"]["hosts"])

    for key, entry in backups.items():
        assert re.fullmatch(r"[a-z-]+", key), f"key {key!r} must match ^[a-z-]+$"
        assert set(entry) == {"host", "mount", "dir", "schedule"}, f"{key}: wrong fields {sorted(entry)}"
        assert entry["dir"] == entry["mount"] or entry["dir"].startswith(entry["mount"] + "/"), (
            f"{key}: dir must equal mount or be beneath it"
        )
        assert entry["host"] in service_hosts, f"{key}: host {entry['host']} not under services"

    for key, schedule in EXPECTED_SCHEDULES.items():
        assert backups[key]["schedule"] == schedule, f"{key}: schedule must be unchanged"


def test_every_backup_has_a_snapshot_and_a_playbook() -> None:
    """FR-003, FR-007: each key has a snapshot template and exactly one lab-guarded playbook entry."""
    backups = _service_backups()
    for key in backups:
        snapshot = ANSIBLE / "roles/service_backup/templates/snapshot" / f"{key}.sh.j2"
        assert snapshot.exists(), f"missing snapshot template for {key}"
        assert "snapshot()" in snapshot.read_text(), f"{key}: snapshot() not defined"

        found = []
        for playbook in (ANSIBLE / "playbooks").glob("*.yml"):
            plays = yaml.safe_load(playbook.read_text()) or []
            for play in plays:
                for role in play.get("roles", []) or []:
                    if (
                        isinstance(role, dict)
                        and role.get("role") == "service_backup"
                        and role.get("service_backup_name") == key
                    ):
                        found.append((playbook.name, role))
        assert len(found) == 1, f"{key}: expected one playbook entry, found {len(found)}"
        when = str(found[0][1].get("when", ""))
        assert "deploy_environment" in when and "lab" in when, f"{key}: entry must be skipped in lab"

    removed = ("financial_scenario_backup", "hermes_backup", "immich_backup", "nextcloud_backup")
    for playbook in (ANSIBLE / "playbooks").glob("*.yml"):
        text = playbook.read_text()
        for name in removed:
            assert name not in text, f"{playbook.name} still references {name}"


def test_backup_script_order() -> None:
    """FR-004, contract C1: mount check, snapshot, partial write, rename, metric, then prune."""
    text = _read("ansible/roles/service_backup/templates/backup.sh.j2")

    assert len(re.findall(r"^BACKUP_MOUNT=", text, flags=re.M)) == 1
    assert 'findmnt --mountpoint "$BACKUP_MOUNT" --types nfs,nfs4' in text
    assert "set -euo pipefail" in text
    assert "trap " in text

    mount = text.index('findmnt --mountpoint "$BACKUP_MOUNT"')
    snapshot = text.index("\nsnapshot\n")
    partial = text.index("-czf \"$BACKUP_DIR/$BACKUP_NAME.tar.gz.partial\"")
    rename = text.index("\nmv ")
    metric = text.index("backup-success-metric")
    prune = text.index("get_date()")
    assert mount < snapshot < partial < rename < metric < prune, "script steps are out of order"


def test_role_checks_mount_at_deploy() -> None:
    """FR-004: the role refuses a non-NFS destination before creating anything."""
    text = _read("ansible/roles/service_backup/tasks/main.yml")
    tasks = yaml.safe_load(text)
    assert "'0777'" not in text and '"0777"' not in text, "no task may set mode 0777"

    def mentions(task: dict, needle: str) -> bool:
        return needle in yaml.safe_dump(task)

    check = next(
        i for i, t in enumerate(tasks)
        if mentions(t, "findmnt --mountpoint") and mentions(t, "nfs,nfs4")
    )
    creators = [
        i for i, t in enumerate(tasks)
        if mentions(t, "ansible.builtin.file") or mentions(t, "ansible.builtin.template")
    ]
    assert creators and check < min(creators), "mount check must precede every task that creates files"


def test_backup_alert_from_inventory() -> None:
    """FR-013, FR-014, contract C3: BackupStale's expected set comes from the inventory."""
    text = _read("ansible/roles/monitoring_stack/templates/backup_alerts.yml.j2")
    for needle in (
        "alert: BackupStale",
        "129600",
        "absent(backup_last_success_timestamp_seconds",
        "service_backups",
        "proxmox_hosts",
        "deploy_environment",
    ):
        assert needle in text, f"backup_alerts.yml.j2 must contain {needle!r}"
    for key in _service_backups():
        assert f'backup="{key}"' not in text, f"alert must not hard-code {key}"


def test_pve_timer_single_oncalendar() -> None:
    """FR-011: proxmox_backup_time and the schedule branches are mutually exclusive."""
    text = _read("ansible/roles/proxmox_backup/templates/proxmox-backup.timer.j2")
    assert len(re.findall(r"OnCalendar=\*-\*-\* \{\{ proxmox_backup_time \}\}:00", text)) == 1
    assert "{% if proxmox_backup_time is defined %}" in text

    start = text.index("{% if proxmox_backup_time is defined %}")
    else_at = text.index("{% else %}", start)
    end_at = text.rindex("{% endif %}")
    assert start < text.index("proxmox_backup_time }}:00") < else_at, "time branch must be the if-branch"
    assert "proxmox_backup_schedule" in text[else_at:end_at], "schedule branches must be in the else"
    assert "proxmox_backup_schedule" not in text[start:else_at]


def test_pve_backup_reports_success() -> None:
    """FR-012: a verified PVE backup writes the success record, and pve is scraped."""
    script = _read("ansible/roles/proxmox_backup/templates/proxmox-config-backup.sh.j2")
    main = script[script.rindex("main()"):]
    assert "backup-success-metric proxmox" in main
    assert main.index("verify_backup") < main.index("backup-success-metric proxmox")

    playbook = yaml.safe_load(_read("ansible/playbooks/host_proxmox.yml"))
    roles = [r if isinstance(r, str) else r.get("role") for p in playbook for r in p.get("roles", [])]
    assert "node_exporter" in roles, "host_proxmox.yml must apply node_exporter"

    prom = _read("ansible/roles/monitoring_stack/templates/prometheus.yml.j2")
    assert "proxmox_hosts" in prom, "prometheus node-exporter job must scrape proxmox_hosts"


def test_writer_installed_by_node_exporter() -> None:
    """Contract C2: the atomic success-record writer ships with node_exporter."""
    writer = ANSIBLE / "roles/node_exporter/files/backup-success-metric"
    assert writer.exists()
    text = writer.read_text()
    assert ".tmp" in text and "mv " in text
    assert "backup_last_success_timestamp_seconds{backup=" in text

    tasks = yaml.safe_load(_read("ansible/roles/node_exporter/tasks/main.yml"))
    install = [t for t in tasks if "/usr/local/bin/backup-success-metric" in yaml.safe_dump(t)]
    assert install, "node_exporter must install /usr/local/bin/backup-success-metric"
    assert "'0755'" in yaml.safe_dump(install[0]) or "0755" in yaml.safe_dump(install[0])


def test_immich_archive_has_no_env() -> None:
    """FR-008: the Immich archive carries no .env; the drill renders it instead."""
    snapshot = _read("ansible/roles/service_backup/templates/snapshot/immich.sh.j2")
    assert ".env" not in snapshot

    drill = _read("ansible/playbooks/restore-drill.yml")
    assert "roles/immich/templates/.env.j2" in drill
    assert "extracted_folder }}/.env" not in drill


def test_homeassistant_restore_drill_is_isolated_and_proves_the_restore() -> None:
    """The HA drill restores a config with live integrations and automations. Without a network
    a second instance cannot act on the house. It must also tell an onboarded restore from a
    fresh boot, and always tear down (docs/runbooks/homeassistant-backup-restore.md)."""
    compose = yaml.safe_load(
        re.sub(r"\{\{.*?\}\}", "X", _read(
            "ansible/roles/service_backup/templates/restore/homeassistant-compose.yml.j2"))
    )
    service = compose["services"]["homeassistant-restore"]
    assert service["network_mode"] == "none"
    assert "ports" not in service
    assert service["container_name"] != "homeassistant"

    plays = yaml.safe_load(_read("ansible/playbooks/homeassistant-restore-drill.yml"))
    block = next(t for t in plays[0]["tasks"] if "block" in t)
    dumped = yaml.safe_dump(block["block"])
    assert "/api/onboarding" in dumped and "'404'" in dumped
    always = yaml.safe_dump(block["always"])
    assert "state: absent" in always and "homeassistant_restore_dir" in always
    # Extraction and the archive checks sit inside the block, so a bad archive still gets its
    # extracted tokens removed (review on #298).
    outside = [t for t in plays[0]["tasks"] if "block" not in t]
    assert not any("unarchive" in yaml.safe_dump(t) for t in outside)
    assert "ansible.builtin.unarchive" in dumped

    snapshot = _read("ansible/roles/service_backup/templates/snapshot/homeassistant.sh.j2")
    assert '"$WORK_DIR/config"' in snapshot, "the drill reads <top>/config/ (contract C5)"


def test_mount_parent_is_traversable_for_node_exporter() -> None:
    """FR-015: node_exporter must be able to stat the mount, so its parent is not 0700."""
    tasks = yaml.safe_load(_read("ansible/roles/service_backup/tasks/main.yml"))
    task = next(t for t in tasks if "dirname" in yaml.safe_dump(t) and "ansible.builtin.file" in t)
    assert task["ansible.builtin.file"]["mode"] == "0755"
