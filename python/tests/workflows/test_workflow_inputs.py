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


def _load_yaml(path: Path) -> dict:
    obj = yaml.load(path.read_text(encoding="utf-8"), Loader=_Yaml12SafeLoader)
    assert isinstance(obj, dict)
    return obj


def _workflow_dispatch_inputs(doc: dict) -> dict:
    on = doc.get("on")
    assert isinstance(on, dict)
    wd = on.get("workflow_dispatch")
    assert isinstance(wd, dict)
    inputs = wd.get("inputs")
    assert isinstance(inputs, dict)
    return inputs


def _assert_input(inputs: dict, name: str, *, type_: str) -> None:
    assert name in inputs, f"Missing workflow_dispatch input: {name}"
    spec = inputs[name]
    assert isinstance(spec, dict)
    assert spec.get("type") == type_, f"Input {name} type expected {type_}, got {spec.get('type')}"


def test_lxc_deploy_lab_inputs_contract():
    path = Path(".github/workflows/lxc-deploy-lab.yml")
    doc = _load_yaml(path)
    inputs = _workflow_dispatch_inputs(doc)

    _assert_input(inputs, "service", type_="choice")
    _assert_input(inputs, "apply", type_="boolean")
    _assert_input(inputs, "confirm_destructive", type_="boolean")


def test_lxc_apply_prod_inputs_contract():
    path = Path(".github/workflows/lxc-apply-prod.yml")
    doc = _load_yaml(path)
    inputs = _workflow_dispatch_inputs(doc)

    _assert_input(inputs, "promotion_run_id", type_="string")
    _assert_input(inputs, "allow_override_failed_lab_gate", type_="boolean")
    _assert_input(inputs, "confirm_apply_prod", type_="string")
