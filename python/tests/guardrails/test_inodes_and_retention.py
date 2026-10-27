"""Guard tests: inode and /tmp alerts, and LogRetentionStalled after a Loki restart.

RCA 2026-10-27: pve's /tmp (tmpfs, 1,048,576 inodes) filled with leaked pytest dirs and a CI
run failed with ENOSPC. No rule watched inodes anywhere, and DiskSpace* exclude every tmpfs.
Separately, LogRetentionStalled read the compactor's last-run metric as 0 after every Loki
restart and only its 30-minute `for:` kept it from paging.
"""

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
INFRA = ROOT / "ansible/roles/monitoring_stack/files/prometheus/alerts/infrastructure_alerts.yml"
PIPELINE = ROOT / "ansible/roles/monitoring_stack/templates/log_pipeline_alerts.yml.j2"


def _infra_rules() -> dict[str, dict]:
    return {r["alert"]: r for g in yaml.safe_load(INFRA.read_text())["groups"] for r in g["rules"]}


def _flat(expr: str) -> str:
    return " ".join(expr.split())


def test_inode_alerts_exist_and_include_tmpfs():
    rules = _infra_rules()
    for name, threshold, severity in (("FilesystemInodesWarning", "85", "warning"),
                                      ("FilesystemInodesCritical", "95", "critical")):
        r = rules[name]
        expr = _flat(r["expr"])
        assert "node_filesystem_files_free" in expr and "node_filesystem_files" in expr
        assert f"> {threshold}" in expr
        assert "tmpfs" not in expr.split("fstype!~")[1].split('"')[1], "tmpfs must be watched for inodes"
        assert r["labels"]["severity"] == severity
        assert r["labels"]["component"] == "infrastructure"


def test_tmp_tmpfs_space_is_watched():
    r = _infra_rules()["TmpSpaceWarning"]
    expr = _flat(r["expr"])
    assert 'mountpoint="/tmp"' in expr and 'fstype="tmpfs"' in expr
    assert "node_filesystem_avail_bytes" in expr


def test_disk_space_rules_still_exclude_tmpfs():
    # /run, /dev/shm and friends are tiny tmpfs mounts; bytes there are not a disk problem.
    for name in ("DiskSpaceWarning", "DiskSpaceCritical"):
        assert 'fstype!~"tmpfs|overlay"' in _infra_rules()[name]["expr"]


def _retention_expr() -> str:
    text = PIPELINE.read_text()
    block = text.split("- alert: LogRetentionStalled", 1)[1].split("- alert:", 1)[0]
    return _flat(block.split("expr: |", 1)[1].split("for:", 1)[0])


def test_retention_stalled_ignores_the_zero_after_a_restart():
    expr = _retention_expr()
    metric = "loki_compactor_apply_retention_last_successful_run_timestamp_seconds"
    assert re.search(rf"{metric} > 0", expr), "a zero (never ran since restart) is not 2 h stale"


def test_retention_stalled_still_fires_if_the_compactor_never_runs_after_a_restart():
    expr = _retention_expr()
    assert "== 0" in expr
    assert 'process_start_time_seconds{job="loki"}' in expr
    assert "> 7200" in expr.split("== 0", 1)[1]
