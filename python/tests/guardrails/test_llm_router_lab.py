"""Guard test: the llm-router role runs to the end in the isolated lab (067; found 2026-10-31, 097).

The lab copy cannot resolve the Mac's mDNS name. The hostname assertion must stay on in PROD
and be off in lab, so the LAB stage reaches the key provisioning it exists to rehearse.
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
TASKS = yaml.safe_load((ROOT / "ansible/roles/llm_router/tasks/main.yml").read_text())


def _task(name: str) -> dict:
    return next(t for t in TASKS if t.get("name") == name)


def test_hostname_assertion_is_prod_only():
    when = _task("Assert every local-tier backend hostname resolved")["when"]
    assert when == "(deploy_environment | default('prod')) != 'lab'"


def test_host_mappings_use_resolved_names_only():
    task = _task("Build the container host mappings for the local tier")
    assert "selectattr('rc', 'equalto', 0)" in task["vars"]["resolved"]


def test_lab_records_the_skipped_check():
    task = _task("Record the skipped lab check")
    assert "skipped-checks.txt" in task["ansible.builtin.lineinfile"]["path"]
    assert "(deploy_environment | default('prod')) == 'lab'" in task["when"]


def test_key_provisioning_follows_the_hostname_check():
    names = [t.get("name") for t in TASKS]
    assert names.index("Assert every local-tier backend hostname resolved") < names.index(
        "Include virtual key provisioning (FR-015, FR-010)"
    )
