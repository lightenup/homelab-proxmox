from __future__ import annotations

from pathlib import Path
import re

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


def test_taskfile_top10_tasks_exist_contract() -> None:
    path = Path("Taskfile.yml")
    assert path.exists(), "Missing Taskfile.yml at repo root"

    doc = yaml.load(path.read_text(encoding="utf-8"), Loader=_Yaml12SafeLoader)
    assert isinstance(doc, dict)

    tasks = doc.get("tasks")
    assert isinstance(tasks, dict), "Taskfile.yml must define a top-level 'tasks' mapping"

    required = {
        "service:add",
        "service:change",
        "service:remove",
        "inventory:update",
        "healthcheck:run",
        "terraform:validate",
        "terraform:plan",
        "terraform:apply",
        "deploy:lab",
        "summary:render",
    }

    missing = sorted(required - set(tasks.keys()))
    assert not missing, f"Taskfile.yml missing required tasks: {missing}"
