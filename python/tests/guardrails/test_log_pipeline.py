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
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text()


class _AnsibleYamlLoader(yaml.SafeLoader):
    """SafeLoader that tolerates Ansible's `!unsafe` tag (host_vars alert text).

    Also re-pins the standard YAML 1.1 bool resolver. Some other test modules in this repo
    (e.g. test_taskfile_contract.py) mutate `yaml.SafeLoader.yaml_implicit_resolvers` in place
    at import time rather than on a private copy, which strips bool resolution from the real
    yaml.SafeLoader class for the rest of the pytest session once they are collected. Explicit
    re-registration here shields this file from that cross-test ordering bug.
    """


_AnsibleYamlLoader.add_constructor(
    "!unsafe", lambda loader, node: loader.construct_scalar(node)
)
_AnsibleYamlLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(
        r"""^(?:yes|Yes|YES|no|No|NO
                    |true|True|TRUE|false|False|FALSE
                    |on|On|ON|off|Off|OFF)$""",
        re.X,
    ),
    list("yYnNtTfFoO"),
)


def _safe_load(text: str):
    return yaml.load(text, Loader=_AnsibleYamlLoader)


def _alloy_defaults() -> dict:
    return _safe_load(_read("ansible/roles/alloy/defaults/main.yml"))


# ---------------------------------------------------------------------------
# 1. test_redaction_corpus (FR-005, SC-002, R7)
# ---------------------------------------------------------------------------


def _parse_corpus() -> list[tuple[str, str, str]]:
    rows = []
    for line in (FIXTURES / "redaction_corpus.txt").read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        name, raw, secret = line.split("|", 2)
        rows.append((name, raw, secret))
    return rows


def test_redaction_corpus() -> None:
    """FR-005, SC-002, R7: every alloy_redaction_pattern redacts its secret and nothing else."""
    patterns = _alloy_defaults()["alloy_redaction_patterns"]
    assert patterns, "alloy_redaction_patterns must not be empty"

    names = [p["name"] for p in patterns]
    for p in patterns:
        compiled = re.compile(p["expression"])
        assert compiled.groups == 1, f"{p['name']}: expression must have exactly one capture group"

    corpus = _parse_corpus()
    assert corpus, "redaction corpus must not be empty"

    positive_names = {name for name, _, secret in corpus if name != "control"}
    for name in names:
        assert name in positive_names, f"{name}: no positive corpus line"

    def apply_all(line: str) -> str:
        for p in patterns:
            compiled = re.compile(p["expression"])

            def _sub(m: re.Match) -> str:
                start, end = m.span(1)
                return m.group(0)[: start - m.start()] + "<redacted>" + m.group(0)[end - m.start() :]

            line = compiled.sub(_sub, line)
        return line

    for name, raw, secret in corpus:
        out = apply_all(raw)
        if name == "control":
            assert out == raw, f"control line changed: {raw!r} -> {out!r}"
        else:
            assert secret not in out, f"{name}: secret {secret!r} still present in {out!r}"
            assert "<redacted>" in out, f"{name}: <redacted> missing from {out!r}"


# ---------------------------------------------------------------------------
# 2. test_store_contract (C1, FR-004, FR-006, FR-013)
# ---------------------------------------------------------------------------


def test_store_contract() -> None:
    compose = _read("ansible/roles/monitoring_stack/templates/docker-compose.yml.j2")
    assert "image: grafana/loki:{{ loki_version }}" in compose
    assert "mem_limit:" in compose
    assert "loki_data:" in compose

    # The loki service block must not sit inside a deploy_environment conditional.
    loki_idx = compose.index("  loki:")
    before = compose[:loki_idx]
    # Count open/close of {% if ... deploy_environment ... %} blocks before the loki service.
    opens = len(re.findall(r"{%\s*if[^%]*deploy_environment", before))
    closes = len(re.findall(r"{%\s*endif\s*%}", before))
    assert opens <= closes, "loki service must not be inside a deploy_environment conditional"

    loki_block = compose[loki_idx : compose.index("\n\n", loki_idx) if "\n\n" in compose[loki_idx:] else len(compose)]
    port_lines = [
        line.strip() for line in loki_block.splitlines() if re.search(r'^\s*-\s*"[^"]*:[^"]*"\s*$', line)
    ]
    assert port_lines, "loki service must publish a port"
    for line in port_lines:
        port = re.search(r'"([^"]+)"', line).group(1)
        assert port.startswith("127.0.0.1:"), f"loki port {port!r} must be bound to 127.0.0.1"

    loki_yaml = _read("ansible/roles/monitoring_stack/templates/loki.yaml.j2")
    for needle in (
        "retention_enabled: true",
        "delete_request_store: filesystem",
        "delete_request_cancel_period: 10m",
        "retention_period",
        "reject_old_samples_max_age: 168h",
        "max_line_size_truncate: true",
        "replay_memory_ceiling",
        "schema: v13",
        "store: tsdb",
        "alertmanager_url: http://alertmanager:9093",
        "reporting_enabled: false",
    ):
        assert needle in loki_yaml, f"loki.yaml.j2 missing {needle!r}"

    datasource = _safe_load(
        _read("ansible/roles/monitoring_stack/files/grafana/provisioning/datasources/loki.yml")
    )
    ds = datasource["datasources"][0]
    assert ds["type"] == "loki"
    assert ds["uid"] == "loki"
    assert ds["url"] == "http://loki:3100"

    provision = _read("ansible/roles/monitoring_stack/tasks/grafana_provision.yml")
    assert "datasources/loki.yml" in provision


# ---------------------------------------------------------------------------
# 3. test_store_validation_before_start (C1, C4, R10)
# ---------------------------------------------------------------------------


def test_store_validation_before_start() -> None:
    validate = _read("ansible/roles/monitoring_stack/tasks/validate_alerts.yml")
    assert "-verify-config" in validate
    assert "lokitool rules check" in validate

    for path in ANSIBLE.rglob("*"):
        if not path.is_file() or path.suffix not in {".yml", ".yaml", ".j2"}:
            continue
        text = path.read_text(errors="ignore")
        for m in re.finditer(r"rules lint", text):
            window = text[max(0, m.start() - 40) : m.end() + 80]
            assert "--dry-run" in window, f"{path}: 'rules lint' without --dry-run"

    compose = _safe_load(_read("ansible/roles/monitoring_stack/tasks/compose_stack.yml"))
    validate_idx = next(
        i
        for i, t in enumerate(compose)
        if "include_tasks" in str(t) and "validate_alerts" in str(t)
    )
    start_idx = next(i for i, t in enumerate(compose) if t.get("name") == "Start monitoring stack")
    assert validate_idx < start_idx


# ---------------------------------------------------------------------------
# 4. test_collector_contract (C3, FR-003, FR-010, FR-011)
# ---------------------------------------------------------------------------


def test_collector_contract() -> None:
    main_tasks = _read("ansible/roles/alloy/tasks/main.yml")
    assert "github.com/grafana/alloy/releases/download/v{{ alloy_version }}" in main_tasks
    assert "checksum:" in main_tasks
    assert "SHA256SUMS" in main_tasks
    assert "adm" in main_tasks
    assert "systemd-journal" in main_tasks
    assert "docker inspect" in main_tasks
    assert "max-size" in main_tasks

    config = _read("ansible/roles/alloy/templates/config.alloy.j2")
    write_blocks = re.findall(r'loki\.write\s+"[^"]+"\s*{.*?\n}', config, flags=re.S)
    assert write_blocks, "config.alloy.j2 must define at least one loki.write block"
    for block in write_blocks:
        assert "max_backoff_retries = 0" in block

    assert "wal {" not in config
    assert "stability.level" not in config

    first_replace = config.index("stage.replace")
    first_limit = config.index("stage.limit")
    assert first_limit < first_replace, "stage.limit must come before the first stage.replace"
    assert 'drop = false' in config

    for_loop = config.index("for p in alloy_redaction_patterns")
    assert for_loop < first_replace or "stage.replace" in config[for_loop:]

    assert "3101" not in config or "alloy_relay_port" in config
    assert "listen_port = {{ alloy_relay_port }}" in config

    override = _read("ansible/roles/alloy/templates/alloy-override.conf.j2")
    assert "MemoryMax=" in override
    assert "MemoryHigh=" in override


# ---------------------------------------------------------------------------
# 5. test_collector_production_only (C3, FR-017)
# ---------------------------------------------------------------------------


def test_collector_production_only() -> None:
    lxc_base = _safe_load(_read("ansible/roles/lxc_base/tasks/main.yml"))

    def _include_role(t: dict) -> dict | None:
        return t.get("include_role") or t.get("ansible.builtin.include_role")

    alloy_task = next(t for t in lxc_base if (_include_role(t) or {}).get("name") == "alloy")
    when = str(alloy_task.get("when", ""))
    assert "deploy_environment" in when and "lab" in when

    # A per-service deploy's scoped inventory (scripts/lab/pve-service-deploy) has no
    # 'proxmox_hosts' group at all — only the full prod inventory does. Every reference must
    # default to [] (existing convention: backup_alerts.yml.j2, prometheus.yml.j2), or the
    # bare `groups['proxmox_hosts']` raises "'dict object' has no attribute" on a lone-service
    # apply, failing every non-monitoring, non-pve deploy (found live on market-model).
    for path in (
        ANSIBLE / "roles/alloy/tasks/main.yml",
        ANSIBLE / "roles/alloy/templates/config.alloy.j2",
    ):
        text = path.read_text()
        for m in re.finditer(r"groups\['proxmox_hosts'\]", text):
            window = text[m.end() : m.end() + 20]
            assert window.lstrip().startswith("| default("), (
                f"{path}: groups['proxmox_hosts'] without | default([]) at offset {m.start()}"
            )

    host_proxmox = _safe_load(_read("ansible/playbooks/host_proxmox.yml"))
    roles = host_proxmox[0]["roles"]
    alloy_entries = [
        r for r in roles if isinstance(r, dict) and r.get("role") == "alloy"
    ]
    assert len(alloy_entries) == 1
    when = str(alloy_entries[0].get("when", ""))
    assert "deploy_environment" in when and "lab" in when


# ---------------------------------------------------------------------------
# 6. test_log_rules_declarations (data-model §3, FR-008)
# ---------------------------------------------------------------------------


EXPECTED_LOG_RULE_SERVICES = {"llm-router", "hermes", "nextcloud", "immich", "ntfy"}
REQUIRED_SEVERITIES = {"critical", "warning", "info"}


def test_log_rules_declarations() -> None:
    found_services = set()
    for path in sorted((ANSIBLE / "host_vars").glob("*.yml")):
        data = _safe_load(path.read_text()) or {}
        contract = data.get("monitoring_contract", {})
        rules = contract.get("log_alert_rules")
        if not rules:
            continue
        service = path.stem
        found_services.add(service)
        for rule in rules:
            for field in ("alert", "expr", "for", "severity", "summary", "description", "enabled"):
                assert field in rule, f"{path.name}: log_alert_rules entry missing {field!r}"
            assert rule["severity"] in REQUIRED_SEVERITIES
            if rule["enabled"] is False:
                assert "disabled_reason" in rule, f"{path.name}: disabled rule missing disabled_reason"
            else:
                baseline = rule.get("baseline")
                assert baseline, f"{path.name}: enabled rule missing baseline"
                for field in ("from", "to", "max_15m"):
                    assert field in baseline

    for service in EXPECTED_LOG_RULE_SERVICES:
        assert service in found_services, f"{service}: missing log_alert_rules"
        path = ANSIBLE / "host_vars" / f"{service}.yml"
        data = _safe_load(path.read_text())
        rules = data["monitoring_contract"]["log_alert_rules"]
        assert len(rules) == 1, f"{service}: expected exactly one log_alert_rules entry"


# ---------------------------------------------------------------------------
# 7. test_login_allowlist (data-model §2/§4, FR-009)
# ---------------------------------------------------------------------------


FP_RE = re.compile(r"^SHA256:[A-Za-z0-9+/]{43}$")
VALID_FROM = {"proxmox", "lan", "tailnet"}


def test_login_allowlist() -> None:
    monitoring_vars = _safe_load(_read("ansible/group_vars/monitoring/vars.yml"))
    allowlist = monitoring_vars["ssh_login_allowlist"]
    assert set(allowlist) == {"lxc", "proxmox"}

    for cls, entries in allowlist.items():
        assert entries, f"{cls}: must not be empty"
        for entry in entries:
            assert "name" in entry
            assert entry["users"], f"{cls}/{entry.get('name')}: users must not be empty"
            assert entry["keys"], f"{cls}/{entry.get('name')}: keys must not be empty"
            for key in entry["keys"]:
                assert FP_RE.match(key), f"bad fingerprint shape: {key!r}"
            assert entry["from"], f"{cls}/{entry.get('name')}: from must not be empty"
            assert set(entry["from"]) <= VALID_FROM

    assert monitoring_vars["ssh_sudo_expected"] == {"lxc": "ansible", "proxmox": "ci"}

    all_vars = _safe_load(_read("ansible/group_vars/all/vars.yml"))
    for key in ("lan_cidr", "tailnet_cidr", "monitoring_host_ip", "alloy_http_port"):
        assert key in all_vars, f"group_vars/all/vars.yml missing {key!r}"

    for path in (ANSIBLE / "roles/alloy").rglob("*"):
        if path.is_file():
            text = path.read_text(errors="ignore")
            assert "hostvars['monitoring']" not in text and 'hostvars["monitoring"]' not in text


# ---------------------------------------------------------------------------
# 8. test_rules_file_rendering (C4, FR-017, R3, spec US3 scenario 1)
# ---------------------------------------------------------------------------


def test_rules_file_rendering() -> None:
    compose = _safe_load(_read("ansible/roles/monitoring_stack/tasks/compose_stack.yml"))
    task = next(
        t
        for t in compose
        if isinstance(t.get("ansible.builtin.template"), dict)
        and t["ansible.builtin.template"].get("src") == "log_alerts.yaml.j2"
    )
    assert task["ansible.builtin.template"]["dest"].endswith("/fake/log_alerts.yaml")
    when = str(task.get("when", ""))
    assert "lab" in when

    rules = _read("ansible/roles/monitoring_stack/templates/log_alerts.yaml.j2")
    for needle in (
        "KernelOomKill",
        "SshLoginNotAllowed",
        "SudoByUnexpectedUser",
        "log_estate",
        "log_services",
        "log_alert_rules",
        "enabled",
    ):
        assert needle in rules, f"log_alerts.yaml.j2 missing {needle!r}"

    assert 'port \\d+ ssh2(?:' in rules
    assert 'port \\d+ \\S+(?:' not in rules

    for m in re.finditer(r"sudo_user\s*!=", rules):
        window = rules[max(0, m.start() - 120) : m.start()]
        assert 'sudo_user != ""' in window or rules[m.start() : m.start() + 20].startswith('sudo_user != ""')

    dashboard = _read("ansible/roles/monitoring_stack/files/grafana/dashboards/security-overview.json")
    assert 'port \\\\d+ ssh2(?:' in dashboard
    assert 'port \\\\d+ \\\\S+(?:' not in dashboard
    assert 'sudo_user != \\"\\"' in dashboard

    summary_block = rules[rules.index("log_services") :]
    assert "entry.rule.summary" in summary_block, "log_services must render each rule's summary"

    # Every per-service log_alert_rules summary carries the Explore selector (spec US3
    # scenario 1): Pushover/ntfy show only the summary, so this is how the alert carries the
    # query for the matching lines.
    for path in sorted((ANSIBLE / "host_vars").glob("*.yml")):
        data = _safe_load(path.read_text()) or {}
        for rule in data.get("monitoring_contract", {}).get("log_alert_rules", []) or []:
            assert "{host=" in rule["summary"], f"{path.name}: {rule['alert']} summary missing {{host="


# ---------------------------------------------------------------------------
# 9. test_pipeline_alerts (C5, R12, R14, FR-017)
# ---------------------------------------------------------------------------


PIPELINE_ALERT_NAMES = [
    "LogCollectorDown",
    "LogHostSilent",
    "LogRulesNotLoaded",
    "LogRuleEvaluationFailing",
    "LogRuleNotificationsFailing",
    "LogLinesDiscarded",
    "LogLinesDiscardedSustained",
    "LogCollectorDropping",
    "LogRetentionStalled",
    "HostOomKill",
]


def test_pipeline_alerts() -> None:
    text = _read("ansible/roles/monitoring_stack/templates/log_pipeline_alerts.yml.j2")
    for name in PIPELINE_ALERT_NAMES:
        assert f"alert: {name}" in text, f"log_pipeline_alerts.yml.j2 missing {name}"
    assert text.count("component: logging") >= len(PIPELINE_ALERT_NAMES)

    prom = _read("ansible/roles/monitoring_stack/templates/prometheus.yml.j2")
    assert "job_name: 'loki'" in prom
    assert "job_name: 'alloy'" in prom

    alloy_idx = prom.index("job_name: 'alloy'")
    next_job = prom.find("job_name:", alloy_idx + 1)
    alloy_block = prom[alloy_idx : next_job if next_job != -1 else len(prom)]
    assert "no_down_alert" in alloy_block
    assert "deploy_environment" not in alloy_block

    compose = _safe_load(_read("ansible/roles/monitoring_stack/tasks/compose_stack.yml"))
    task = next(
        t
        for t in compose
        if isinstance(t.get("ansible.builtin.template"), dict)
        and t["ansible.builtin.template"].get("src") == "log_pipeline_alerts.yml.j2"
    )
    when = str(task.get("when", ""))
    assert "lab" in when


# ---------------------------------------------------------------------------
# 10. test_sshd_lxc_only (C7, FR-015)
# ---------------------------------------------------------------------------


def test_sshd_lxc_only() -> None:
    tasks = _safe_load(_read("ansible/roles/lxc_base/tasks/main.yml"))
    copy_idx = next(
        i
        for i, t in enumerate(tasks)
        if isinstance(t.get("ansible.builtin.copy"), dict)
        and t["ansible.builtin.copy"].get("dest") == "/etc/ssh/sshd_config.d/10-homelab-auth.conf"
    )
    content = tasks[copy_idx]["ansible.builtin.copy"]["content"]
    assert "PasswordAuthentication no" in content
    assert "KbdInteractiveAuthentication no" in content

    check_idx = next(
        i
        for i, t in enumerate(tasks)
        if "sshd -t" in str(t.get("ansible.builtin.command", {}).get("cmd", ""))
        or "sshd -t" in str(t.get("command", ""))
    )
    assert check_idx > copy_idx
    assert "deploy_environment" not in str(tasks[check_idx].get("when", ""))

    for rolename in ("proxmox_host", "tailscale_host", "node_exporter", "alloy"):
        role_dir = ANSIBLE / "roles" / rolename
        if not role_dir.exists():
            continue
        for path in role_dir.rglob("*"):
            if path.is_file():
                assert "PasswordAuthentication" not in path.read_text(errors="ignore"), path

    assert "PasswordAuthentication" not in _read("ansible/playbooks/host_proxmox.yml")


# ---------------------------------------------------------------------------
# 11. test_file_logs_declared (C6, R5, R8)
# ---------------------------------------------------------------------------


def test_file_logs_declared() -> None:
    nextcloud = _safe_load(_read("ansible/host_vars/nextcloud.yml"))
    file_logs = nextcloud["alloy_file_logs"]
    entry = next(f for f in file_logs if f["path_glob"] == "/mnt/nextcloud/data/nextcloud.log")
    assert entry["tail_from_end"] is True

    jellyfin = _safe_load(_read("ansible/host_vars/jellyfin.yml"))
    file_logs = jellyfin["alloy_file_logs"]
    assert any(f["path_glob"] == "/var/log/jellyfin/*.log" for f in file_logs)

    for host in ("reverse_proxy", "jellyfin", "proxmox"):
        data = _safe_load(_read(f"ansible/host_vars/{host}.yml"))
        assert data.get("alloy_docker_logs") is False, f"{host}: alloy_docker_logs must be false"

    monitoring_vars = _safe_load(_read("ansible/host_vars/monitoring/vars.yml"))
    assert monitoring_vars.get("alloy_relay") is True
