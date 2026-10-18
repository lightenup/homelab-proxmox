from __future__ import annotations

from pathlib import Path
import re

import pytest
import yaml


class _Yaml12SafeLoader(yaml.SafeLoader):
    pass


for first_char, resolvers in list(_Yaml12SafeLoader.yaml_implicit_resolvers.items()):
    _Yaml12SafeLoader.yaml_implicit_resolvers[first_char] = [
        (tag, regexp) for (tag, regexp) in resolvers if tag != "tag:yaml.org,2002:bool"
    ]

_Yaml12SafeLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:true|false)$", re.IGNORECASE),
    list("tTfF"),
)


def _load_yaml(path: Path) -> dict:
    obj = yaml.load(path.read_text(encoding="utf-8"), Loader=_Yaml12SafeLoader)
    assert isinstance(obj, dict)
    return obj


PATHS_FILE = Path("scripts/ci/confidence-suite-paths.txt")
WORKFLOW = Path(".github/workflows/lxc-promote-prod.yml")


def _cleaned_patterns() -> list[str]:
    """Load the confidence-suite path list, skipping '#' and blank lines."""
    assert PATHS_FILE.is_file(), f"Missing path list: {PATHS_FILE}"
    patterns = [
        line
        for line in PATHS_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    return patterns


def _compiled_patterns() -> list[re.Pattern]:
    patterns = _cleaned_patterns()
    assert patterns, "The cleaned confidence-suite path list must be non-empty"
    return [re.compile(p) for p in patterns]


def _is_covered(path: str) -> bool:
    return any(rx.search(path) for rx in _compiled_patterns())


def _decide_run_text() -> str:
    doc = _load_yaml(WORKFLOW)
    job = doc["jobs"]["confidence_gate"]
    for step in job["steps"]:
        if step.get("id") == "decide":
            assert isinstance(step.get("run"), str)
            return step["run"]
    raise AssertionError("confidence_gate has no step with id 'decide'")


def test_path_list_is_non_empty():
    assert _cleaned_patterns(), "The cleaned confidence-suite path list must be non-empty"


def test_path_list_covers_itself_and_workflow():
    patterns = _compiled_patterns()
    assert any(rx.search("scripts/ci/confidence-suite-paths.txt") for rx in patterns), (
        "The path list must contain a pattern matching the list file itself"
    )
    assert any(rx.search(".github/workflows/lxc-promote-prod.yml") for rx in patterns), (
        "The path list must contain a pattern matching the promote workflow"
    )


@pytest.mark.parametrize(
    "path",
    [
        "ansible/inventories/prod/hosts.yml",
        "terraform/modules/lxc_service/main.tf",
        "ansible/roles/lxc_base/tasks/main.yml",
        "scripts/lab/pve-service-deploy",
        "ansible/group_vars/services/vars.yml",
        "docs/backlog/backlog.md",
    ],
)
def test_gate_skips_when_unrelated_path_changes(path: str):
    assert not _is_covered(path), f"Path should NOT trigger the suite: {path}"


@pytest.mark.parametrize(
    "path",
    [
        "ansible/playbooks/lab_tier2_pve.yml",
        "scripts/lab/lib/checks.sh",
        "ansible/group_vars/all/vars.yml",
        "ansible/roles/assertion_utils/tasks/main.yml",
        "ansible/ansible.cfg",
        "ansible/inventories/lab/hosts.yml",
        "scripts/ci/confidence-suite-paths.txt",
        ".github/workflows/lxc-promote-prod.yml",
    ],
)
def test_gate_runs_when_suite_path_changes(path: str):
    assert _is_covered(path), f"Path SHOULD trigger the suite: {path}"


def test_gate_is_wired_to_path_list():
    run_text = _decide_run_text()
    assert "scripts/ci/confidence-suite-paths.txt" in run_text, (
        "The decide step must read scripts/ci/confidence-suite-paths.txt"
    )
    assert "grep -qEf" in run_text, (
        "The decide step must match the diff against the path list with `grep -qEf`"
    )
    assert re.search(
        r'if \[\[ ! -s "\$\{patterns\}" \]\]; then\s+decide true ', run_text
    ), "The decide step must fail safe (run) when the path list is missing or empty (FR-005)"
    assert "^ansible/roles/lxc_base/" not in run_text, (
        "The decide step must no longer inline the 063 lxc_base path"
    )


# ---------------------------------------------------------------------------
# Drift guard (US3, research R4): every dependency the suite reads must be
# covered by the path list. A new source/include/group-var that the list does
# not cover fails PR CI, naming the uncovered path.
# ---------------------------------------------------------------------------

# (?:source|bash) "${VAR}/tail" — only variable-free tails count (R4).
_BASH_SOURCE_RE = re.compile(r'(?:source|bash)\s+"\$\{(LIB_DIR|SCRIPT_DIR|REPO_ROOT)\}/([^"$]+)"')

_BASH_FILES = [
    ("scripts/lab/pve-lab", "scripts/lab"),
    ("scripts/lab/guardrails.sh", "scripts/lab"),
    # rebuild.sh is sourced by pve-lab, so its LIB_DIR/SCRIPT_DIR are pve-lab's.
    ("scripts/lab/lib/rebuild.sh", "scripts/lab"),
]

_ROLE_TASK_KEYS = {
    "include_role",
    "import_role",
    "ansible.builtin.include_role",
    "ansible.builtin.import_role",
}


def _resolve_bash_ref(var: str, tail: str, script_dir: str) -> str:
    """Resolve a sourced path tail to a repo-relative path."""
    if var == "LIB_DIR":
        base = f"{script_dir}/lib"
    elif var == "SCRIPT_DIR":
        base = script_dir
    else:  # REPO_ROOT
        base = ""
    return f"{base}/{tail}" if base else tail


def _assert_covered(path: str) -> None:
    assert _is_covered(path), f"Uncovered confidence-suite dependency: {path}"


def test_bash_sourced_files_are_covered():
    for rel_path, script_dir in _BASH_FILES:
        text = Path(rel_path).read_text(encoding="utf-8")
        refs = _BASH_SOURCE_RE.findall(text)
        assert refs, f"No source/bash references found in {rel_path} (extractor may be wrong)"
        for var, tail in refs:
            _assert_covered(_resolve_bash_ref(var, tail, script_dir))


def _playbook_roles(node: object) -> set[str]:
    """Role names from play-level `roles:` and include_role/import_role tasks, at any depth."""
    roles: set[str] = set()
    if isinstance(node, list):
        for item in node:
            roles |= _playbook_roles(item)
    elif isinstance(node, dict):
        play_roles = node.get("roles")
        for entry in play_roles if isinstance(play_roles, list) else []:
            name = entry.get("role", entry.get("name")) if isinstance(entry, dict) else entry
            if isinstance(name, str):
                roles.add(name)
        for key, value in node.items():
            if key in _ROLE_TASK_KEYS and isinstance(value, dict) and isinstance(value.get("name"), str):
                roles.add(value["name"])
            else:
                roles |= _playbook_roles(value)
    return roles


def test_playbook_role_extractor_handles_play_roles_and_late_name():
    plays = yaml.safe_load(
        """
- hosts: lab
  roles:
    - play_role
    - role: dict_role
  tasks:
    - block:
        - include_role:
            tasks_from: report
            name: late_name_role
"""
    )
    assert _playbook_roles(plays) == {"play_role", "dict_role", "late_name_role"}


def test_ansible_roles_are_covered():
    roles: set[str] = set()
    for playbook in sorted(Path("ansible/playbooks").glob("lab_*.yml")):
        roles |= _playbook_roles(yaml.load(playbook.read_text(encoding="utf-8"), Loader=_Yaml12SafeLoader))
    assert roles, "No roles found in ansible/playbooks/lab_*.yml (extractor may be wrong)"
    for role in roles:
        # Collection roles (names with dots) are ignored.
        if "." in role:
            continue
        _assert_covered(f"ansible/roles/{role}/tasks/main.yml")


def _inventory_groups() -> list[str]:
    doc = _load_yaml(Path("ansible/inventories/lab/hosts.yml"))

    groups: list[str] = []

    def walk(node: dict) -> None:
        for key, value in node.items():
            if not isinstance(value, dict):
                continue
            if "children" in value or "hosts" in value:
                groups.append(key)
                walk(value.get("children", {}) or {})

    walk(doc)
    if "all" not in groups:
        groups.insert(0, "all")
    return groups


def test_group_vars_are_covered():
    for group in _inventory_groups():
        gdir = Path("ansible/group_vars") / group
        if gdir.is_dir():
            _assert_covered(f"ansible/group_vars/{group}/vars.yml")


def test_bash_extractor_reports_uncovered_path():
    # Negative case: a synthetic source of a lib file the list does not cover must
    # be reported as uncovered by the coverage helper.
    var, tail = _BASH_SOURCE_RE.search('source "${LIB_DIR}/newlib.sh"').group(1, 2)
    assert (var, tail) == ("LIB_DIR", "newlib.sh")
    uncovered = _resolve_bash_ref(var, tail, "scripts/lab")
    assert uncovered == "scripts/lab/lib/newlib.sh"
    assert not _is_covered(uncovered), (
        f"Expected {uncovered} to be uncovered by the path list"
    )
