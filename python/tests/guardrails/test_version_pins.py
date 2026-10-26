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


MONITORING_VARS = [
    "prometheus_version",
    "grafana_version",
    "telegraf_version",
    "alertmanager_version",
    "blackbox_exporter_version",
]

ALL_VARS = ["node_exporter_version", "alloy_version"]


_YAML_TEXT_CACHE: dict[Path, list[str]] = {}


def _ansible_yaml_files(repo_root: Path) -> dict[Path, list[str]]:
    """Read every YAML file under ansible/ once (skip vendored geerlingguy.* roles)."""
    if not _YAML_TEXT_CACHE:
        ansible_dir = repo_root / "ansible"
        for f in sorted(set(ansible_dir.rglob("*.yml")) | set(ansible_dir.rglob("*.yaml"))):
            if "geerlingguy." in str(f.relative_to(repo_root)):
                continue
            try:
                _YAML_TEXT_CACHE[f] = f.read_text().splitlines()
            except (UnicodeDecodeError, OSError):
                continue
    return _YAML_TEXT_CACHE


def _scan_yaml_for_var(repo_root: Path, var: str) -> list[Path]:
    """Find all files under ansible/ that assign `var`."""
    pattern = re.compile(rf"^\s*{re.escape(var)}:\s")
    return [
        f
        for f, lines in _ansible_yaml_files(repo_root).items()
        if any(pattern.match(line) for line in lines if not line.lstrip().startswith("#"))
    ]


def test_monitoring_pins_assigned_once() -> None:
    """FR-005, SC-004: each monitoring pin is assigned exactly once under ansible/."""
    repo_root = _find_repo_root(Path(__file__).resolve())

    for var in MONITORING_VARS + ALL_VARS:
        matches = _scan_yaml_for_var(repo_root, var)
        assert len(matches) == 1, (
            f"{var} must be assigned exactly once under ansible/, found in: "
            f"{[str(m.relative_to(repo_root)) for m in matches]}"
        )

    monitoring_vars_file = repo_root / "ansible/group_vars/monitoring/vars.yml"
    for var in MONITORING_VARS:
        matches = _scan_yaml_for_var(repo_root, var)
        assert monitoring_vars_file in matches, (
            f"{var} must be in ansible/group_vars/monitoring/vars.yml"
        )

    all_vars_file = repo_root / "ansible/group_vars/all/vars.yml"
    for var in ALL_VARS:
        matches = _scan_yaml_for_var(repo_root, var)
        assert all_vars_file in matches, (
            f"{var} must be in ansible/group_vars/all/vars.yml"
        )


def test_monitoring_role_defaults_have_no_versions() -> None:
    """FR-005, research R-04: role defaults must not define any *_version key."""
    repo_root = _find_repo_root(Path(__file__).resolve())

    for role in ("monitoring_stack", "node_exporter"):
        defaults_path = repo_root / f"ansible/roles/{role}/defaults/main.yml"
        data = yaml.safe_load(defaults_path.read_text())
        version_keys = [k for k in data if k.endswith("_version")]
        assert not version_keys, (
            f"ansible/roles/{role}/defaults/main.yml must not define version keys, "
            f"found: {version_keys}"
        )


def test_every_pin_has_a_source() -> None:
    """FR-014, FR-017, data-model §2: every pin in a versions block has exactly one entry."""
    repo_root = _find_repo_root(Path(__file__).resolve())

    collected: dict[str, Path] = {}

    monitoring_vars = yaml.safe_load(
        (repo_root / "ansible/group_vars/monitoring/vars.yml").read_text()
    )
    for key in monitoring_vars:
        if key.endswith("_version"):
            collected[key] = repo_root / "ansible/group_vars/monitoring/vars.yml"

    all_vars = yaml.safe_load(
        (repo_root / "ansible/group_vars/all/vars.yml").read_text()
    )
    if "node_exporter_version" in all_vars:
        collected["node_exporter_version"] = repo_root / "ansible/group_vars/all/vars.yml"
    if "alloy_version" in all_vars:
        collected["alloy_version"] = repo_root / "ansible/group_vars/all/vars.yml"

    services_text = (repo_root / "ansible/group_vars/services/vars.yml").read_text()
    lines = services_text.splitlines()
    in_block = False
    for line in lines:
        if line.strip() == "# Service versions":
            in_block = True
            continue
        if in_block:
            if line.strip() == "":
                break
            m = re.match(r"^([a-z0-9_]+):", line)
            if m:
                collected[m.group(1)] = repo_root / "ansible/group_vars/services/vars.yml"

    sources_path = repo_root / "ansible/version-sources.yml"
    assert sources_path.exists(), "ansible/version-sources.yml must exist"
    sources = yaml.safe_load(sources_path.read_text())
    pins = sources.get("pins", [])

    pin_vars = {p["variable"] for p in pins}
    for var in collected:
        entries = [p for p in pins if p["variable"] == var]
        assert len(entries) == 1, (
            f"{var} must have exactly one entry in version-sources.yml, found {len(entries)}"
        )
    for var in pin_vars:
        assert var in collected, (
            f"version-sources.yml has entry for {var} but it is not in a versions block"
        )

    for p in pins:
        f = repo_root / p["file"]
        assert f.exists(), f"file {p['file']} does not exist"
        content = f.read_text()
        assert re.search(rf"^\s*{re.escape(p['variable'])}:\s", content, re.MULTILINE), (
            f"{p['variable']} not found in {p['file']}"
        )
        policy = p["policy"]
        assert policy in ("lts", "latest", "support-only", "unchecked"), (
            f"{p['variable']}: invalid policy {policy!r}"
        )
        if policy in ("lts", "latest"):
            assert "github" in p, f"{p['variable']}: lts/latest requires github"
        if policy in ("lts", "support-only"):
            assert "endoflife" in p, f"{p['variable']}: lts/support-only requires endoflife"
        if policy == "unchecked":
            assert isinstance(p.get("reason"), str) and p["reason"], (
                f"{p['variable']}: unchecked requires non-empty reason"
            )


def test_version_currency_workflow() -> None:
    """FR-013, FR-013a, contract §2: the scheduled workflow exists with correct structure."""
    repo_root = _find_repo_root(Path(__file__).resolve())
    wf_path = repo_root / ".github/workflows/version-currency.yml"
    assert wf_path.exists(), ".github/workflows/version-currency.yml must exist"

    data = yaml.safe_load(wf_path.read_text())

    on = data.get("on", data.get(True))
    assert on is not None, "workflow must have an 'on' trigger"
    schedule = on.get("schedule", [])
    assert len(schedule) >= 1, "workflow must have a schedule trigger"
    assert schedule[0].get("cron") == "0 6 * * 1", (
        f"schedule cron must be '0 6 * * 1', got {schedule[0].get('cron')!r}"
    )

    dispatch = on.get("workflow_dispatch", {})
    inputs = dispatch.get("inputs", {})
    dry_run = inputs.get("dry_run", {})
    assert dry_run.get("type") == "boolean", (
        f"workflow_dispatch.inputs.dry_run.type must be 'boolean', got {dry_run.get('type')!r}"
    )

    jobs = data.get("jobs", {})
    assert len(jobs) == 1, f"workflow must have exactly one job, found {len(jobs)}"
    job = list(jobs.values())[0]

    runs_on = job.get("runs-on", "")
    if isinstance(runs_on, list):
        runs_on = " ".join(runs_on)
    assert "self-hosted" in runs_on, (
        f"job must run on self-hosted runner, got runs-on={runs_on!r}"
    )
    assert job.get("timeout-minutes") == 10, (
        f"job timeout-minutes must be 10, got {job.get('timeout-minutes')!r}"
    )

    perms = data.get("permissions", job.get("permissions", {}))
    assert perms == {"contents": "read"}, (
        f"permissions must be {{'contents': 'read'}}, got {perms!r}"
    )


def test_monitoring_validates_before_compose_up() -> None:
    """FR-008, research R-05: validation runs before the stack restarts, once."""
    repo_root = _find_repo_root(Path(__file__).resolve())

    compose = yaml.safe_load(
        (repo_root / "ansible/roles/monitoring_stack/tasks/compose_stack.yml").read_text()
    )

    validate_idx = None
    start_idx = None
    for i, task in enumerate(compose):
        name = task.get("name", "")
        if "include_tasks" in str(task) and "validate_alerts" in str(task):
            validate_idx = i
        if name == "Start monitoring stack":
            start_idx = i

    assert validate_idx is not None, (
        "compose_stack.yml must include validate_alerts.yml"
    )
    assert start_idx is not None, (
        "compose_stack.yml must have a 'Start monitoring stack' task"
    )
    assert validate_idx < start_idx, (
        f"validate_alerts (index {validate_idx}) must come before "
        f"'Start monitoring stack' (index {start_idx})"
    )

    validate_text = (
        repo_root / "ansible/roles/monitoring_stack/tasks/validate_alerts.yml"
    ).read_text()
    for expected in ("promtool", "check config", "amtool", "check-config"):
        assert expected in validate_text, (
            f"validate_alerts.yml must contain {expected!r}"
        )

    main_text = (
        repo_root / "ansible/roles/monitoring_stack/tasks/main.yml"
    ).read_text()
    assert "validate_alerts" not in main_text, (
        "main.yml must not include validate_alerts.yml directly (it runs once via compose_stack.yml)"
    )
