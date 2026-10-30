"""LAB rig workflow, playbook, proxmox-apply guard and the confidence-suite held-rig guard
(spec 095 T062/T071, research R-015/R-016).

The rig (10.99.0.10) is reachable only from `pve`, is kept between jobs, and would be destroyed by
a `proxmox-apply` harness run (CLEANUP-PRE-001) or by Prod 1's confidence suite (`pve-lab
confidence`, same CLEANUP-PRE-001). These tests pin the controls that make that safe: the teardown
barrier, the shared concurrency group, both held-rig refusals, a stable SSH key, the vault read on
`pve` (never from GitHub secrets), and the tier-2 kept harness.
"""
from __future__ import annotations

from pathlib import Path
import re
import subprocess

import pytest
import yaml

LAB_RIG = Path(".github/workflows/lab-rig.yml")
PROXMOX_APPLY = Path(".github/workflows/proxmox-apply.yml")
LXC_PROMOTE_PROD = Path(".github/workflows/lxc-promote-prod.yml")
PLAYBOOK = Path("ansible/playbooks/hermes_lab_rig.yml")

CONFIRM_WORD = "destroy-lab-rig"
RIG_KEY = "/home/ci/.ssh/lab_rig_ed25519"
PVE_VAULT_PASS = "/var/lib/homelab-proxmox/vault/.ansible_vault_pass"


def _load(path: Path) -> dict:
    doc = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    assert isinstance(doc, dict), path
    return doc


def _steps(doc: dict) -> list[dict]:
    return [step for job in doc["jobs"].values() for step in job.get("steps", [])]


def _job_steps(doc: dict, job_name: str) -> list[dict]:
    """Steps of a single named job — `lxc-promote-prod.yml` has several jobs that each have
    their own "Sync repo to PVE" step, so index-based ordering checks must not flatten them."""
    return doc["jobs"][job_name].get("steps", [])


def _runs(doc: dict) -> str:
    return "\n".join(step.get("run", "") for step in _steps(doc))


def _index(steps: list[dict], needle: str) -> int:
    for i, step in enumerate(steps):
        if needle in step.get("run", "") or needle in step.get("name", ""):
            return i
    raise AssertionError(f"no step contains {needle!r}")


# --- lab-rig.yml -------------------------------------------------------------------------------


def test_lab_rig_is_dispatch_only_with_action_and_confirm_inputs():
    doc = _load(LAB_RIG)
    assert set(doc["on"]) == {"workflow_dispatch"}
    inputs = doc["on"]["workflow_dispatch"]["inputs"]
    assert inputs["action"]["type"] == "choice"
    assert set(inputs["action"]["options"]) == {"up", "deploy", "status", "down"}
    assert inputs["action"].get("default") == "status"
    assert inputs["confirm"]["type"] == "string"


@pytest.mark.parametrize("path", [LAB_RIG, PROXMOX_APPLY], ids=lambda p: p.name)
def test_rig_workflows_share_the_pve_lab_concurrency_group(path: Path):
    concurrency = _load(path)["concurrency"]
    assert concurrency["group"] == "pve-lab"
    assert concurrency["cancel-in-progress"] == "false"


def test_down_is_barred_before_anything_runs():
    doc = _load(LAB_RIG)
    steps = _steps(doc)
    barrier = _index(steps, CONFIRM_WORD)
    assert barrier == 0, "the confirm check must be the first step"
    script = steps[barrier]["run"]
    assert "exit 1" in script
    assert "pve-lab down" in _runs(doc)
    assert _index(steps, "pve-lab down") > barrier


def test_free_text_input_never_interpolated_into_scripts():
    # `confirm` is free text: reach it through env, never `${{ }}` inside a run block (injection).
    runs = _runs(_load(LAB_RIG))
    assert not re.search(r"\$\{\{\s*(inputs|github\.event\.inputs)\.confirm", runs)


def test_up_runs_the_kept_tier2_harness_never_bare_up():
    runs = _runs(_load(LAB_RIG))
    assert "pve-lab run --profile hypervisor-control-plane --keep" in runs
    assert not re.search(r"pve-lab up\b", runs), "`pve-lab up` always clones tier 1 (R-015)"


def test_up_refuses_when_a_rig_already_exists():
    # `pve-lab run` starts with CLEANUP-PRE-001, which would destroy a rig mid-gate.
    runs = _runs(_load(LAB_RIG))
    assert re.search(r"rig_exists\(\) \{\s*scripts/lab/pve-lab status \| grep -q 'Found Lab VM'", runs)
    up = runs[re.search(r"^\s*up\)$", runs, re.M).end() : re.search(r"^\s*deploy\)$", runs, re.M).start()]
    assert up.index("if rig_exists") < up.index("pve-lab run")


def test_remote_script_cannot_be_swallowed_by_a_child_reading_stdin():
    runs = _runs(_load(LAB_RIG))
    assert "bash -s" in runs
    assert re.search(r'^main "\$@" </dev/null$', runs, re.M)


def test_up_probes_ntfy_and_the_llm_router_from_the_rig():
    runs = _runs(_load(LAB_RIG))
    assert "https://ntfy.{{ caddy_base_domain }}/v1/health" in runs
    assert "http://{{ llm_router_ip }}:{{ llm_router_port }}/health/liveliness" in runs


def test_rig_uses_a_stable_ssh_key_and_the_pve_vault_file():
    doc = _load(LAB_RIG)
    runs = _runs(doc)
    assert f"PROVISION_SSH_KEY={RIG_KEY}" in runs
    assert PVE_VAULT_PASS in runs
    text = LAB_RIG.read_text(encoding="utf-8")
    assert "secrets.ANSIBLE_VAULT_PASSWORD" not in text, "vault stays on pve (R-015)"


def test_deploy_runs_the_lab_playbook_against_the_lab_inventory():
    runs = _runs(_load(LAB_RIG))
    assert "playbooks/hermes_lab_rig.yml" in runs
    assert "-i inventories/lab/hosts.yml" in runs
    assert "deploy_environment=lab" in runs


def test_every_run_block_parses_as_bash():
    for path in (LAB_RIG, PROXMOX_APPLY):
        for step in _steps(_load(path)):
            script = step.get("run")
            if not script:
                continue
            # GitHub expressions are substituted before bash sees the script.
            script = re.sub(r"\$\{\{[^}]*\}\}", "x", script)
            result = subprocess.run(["bash", "-n"], input=script, text=True, capture_output=True)
            assert result.returncode == 0, f"{path} / {step.get('name')}: {result.stderr}"


# --- proxmox-apply.yml -------------------------------------------------------------------------


def test_proxmox_apply_refuses_while_a_rig_is_kept():
    steps = _steps(_load(PROXMOX_APPLY))
    guard = _index(steps, "Found Lab VM")
    assert "pve-lab status" in steps[guard]["run"]
    assert "exit 1" in steps[guard]["run"]
    assert _index(steps, "Sync repo to PVE") < guard < _index(steps, "pve-lab rebuild")


# --- lxc-promote-prod.yml confidence_suite job (spec 095 T071, research R-016 condition 3) -----


def test_confidence_suite_refuses_while_a_rig_is_kept():
    """`pve-lab confidence` -> `pve-lab run` -> CLEANUP-PRE-001 destroys any lab VM, so Prod 1's
    best-effort confidence suite needs the same held-rig guard as proxmox-apply.yml, in the same
    job, before the suite runs."""
    doc = _load(LXC_PROMOTE_PROD)
    steps = _job_steps(doc, "confidence_suite")
    guard = _index(steps, "Found Lab VM")
    assert "pve-lab status" in steps[guard]["run"]
    assert "exit 1" in steps[guard]["run"]
    assert _index(steps, "Sync repo to PVE") < guard < _index(steps, "Run confidence suite on PVE")


def test_confidence_suite_guard_matches_the_proxmox_apply_guard_text():
    """Same command and message in both places (T071): one control, not two to keep in sync."""
    apply_steps = _steps(_load(PROXMOX_APPLY))
    suite_steps = _job_steps(_load(LXC_PROMOTE_PROD), "confidence_suite")
    apply_guard = apply_steps[_index(apply_steps, "Found Lab VM")]["run"]
    suite_guard = suite_steps[_index(suite_steps, "Found Lab VM")]["run"]
    assert apply_guard.strip() == suite_guard.strip()


def test_confidence_suite_guard_step_parses_as_bash():
    steps = _job_steps(_load(LXC_PROMOTE_PROD), "confidence_suite")
    script = steps[_index(steps, "Found Lab VM")]["run"]
    script = re.sub(r"\$\{\{[^}]*\}\}", "x", script)
    result = subprocess.run(["bash", "-n"], input=script, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


# --- hermes_lab_rig.yml ----------------------------------------------------------------------


def test_playbook_targets_lab_with_docker_and_hermes_only():
    plays = yaml.safe_load(PLAYBOOK.read_text(encoding="utf-8"))
    assert all(play["hosts"] == "lab" for play in plays)
    roles = [r if isinstance(r, str) else r["role"] for play in plays for r in play.get("roles", [])]
    assert roles == ["geerlingguy.docker", "hermes"]
    vars_files = [f for play in plays for f in play.get("vars_files", [])]
    assert any(f.endswith("group_vars/services/vars.yml") for f in vars_files)
    assert any(f.endswith("group_vars/services/vault.yml") for f in vars_files)


def test_playbook_asserts_lab_rig_and_lab_environment_first():
    plays = yaml.safe_load(PLAYBOOK.read_text(encoding="utf-8"))
    first = plays[0]
    tasks = first.get("pre_tasks") or first.get("tasks") or []
    asserts = [t for t in tasks if "ansible.builtin.assert" in t]
    assert asserts, "the first play must assert before any role runs"
    that = " ".join(asserts[0]["ansible.builtin.assert"]["that"])
    assert "lab_inventory" in that
    assert "deploy_environment" in that and "'lab'" in that
    assert "lab-pve-" in that


def test_rig_vm_gets_a_public_nameserver():
    # The host resolver is Tailscale MagicDNS, unreachable from the isolated vmbr99; without an
    # explicit nameserver the nested VM's cloud-init apt-get update hangs (067 regression).
    text = Path("scripts/lab/pve-lab").read_text(encoding="utf-8")
    assert 'LAB_NAMESERVER="1.1.1.1"' in text
    assert "--nameserver $LAB_NAMESERVER" in text
