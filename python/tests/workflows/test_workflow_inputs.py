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


ALLOWED_NIGHTLY_INPUTS = {"min_score"}

NIGHTLY_WORKFLOW = Path(".github/workflows/nightly-deeper-verification.yml")


def _nightly_doc() -> dict:
    return _load_yaml(NIGHTLY_WORKFLOW)


def _nightly_steps(doc: dict) -> list[dict]:
    job = doc["jobs"]["deeper"]
    return job["steps"]


def test_nightly_inputs_contract():
    doc = _nightly_doc()
    inputs = _workflow_dispatch_inputs(doc)
    assert set(inputs.keys()) == ALLOWED_NIGHTLY_INPUTS, (
        f"Nightly inputs must be exactly {ALLOWED_NIGHTLY_INPUTS}, got {set(inputs.keys())}"
    )


def test_nightly_mutmut3_wiring():
    doc = _nightly_doc()
    raw = NIGHTLY_WORKFLOW.read_text(encoding="utf-8")

    # (a) no .mutmut-cache or mutmut-cache
    assert ".mutmut-cache" not in raw, "Nightly workflow must not reference .mutmut-cache"
    assert "mutmut-cache" not in raw, "Nightly workflow must not reference mutmut-cache"

    steps = _nightly_steps(doc)

    # (b) a step whose run contains scripts/ci/mutmut-threshold.sh
    assert any(
        "scripts/ci/mutmut-threshold.sh" in (s.get("run") or "")
        for s in steps
    ), "Nightly must have a step running scripts/ci/mutmut-threshold.sh"

    # (c) a step whose run contains mv -T and /mnt/nas/homelab_ci/mutmut
    assert any(
        "mv -T" in (s.get("run") or "") and "/mnt/nas/homelab_ci/mutmut" in (s.get("run") or "")
        for s in steps
    ), "Nightly must have a step with mv -T and /mnt/nas/homelab_ci/mutmut"

    # (d) no step named Upload artifacts, Install Ansible Galaxy deps,
    #     Setup Python (GitHub-hosted only) or Debug runner + mounts
    forbidden_names = {
        "Upload artifacts",
        "Install Ansible Galaxy deps",
        "Setup Python (GitHub-hosted only)",
        "Debug runner + mounts",
    }
    step_names = {s.get("name", "") for s in steps}
    for name in forbidden_names:
        assert name not in step_names, f"Nightly must not have step: {name}"

    # (e) deeper.timeout-minutes == 30
    job = doc["jobs"]["deeper"]
    assert job.get("timeout-minutes") == 30, (
        f"deeper.timeout-minutes must be 30, got {job.get('timeout-minutes')}"
    )

    # (f) Validate min_score step with regex, preceding Run mutation gate on PVE
    validate_idx = None
    gate_idx = None
    for i, s in enumerate(steps):
        run = s.get("run") or ""
        if "^[0-9]{1,3}(\\.[0-9]+)?$" in run:
            validate_idx = i
        if "Run mutation gate on PVE" == s.get("name", ""):
            gate_idx = i
    assert validate_idx is not None, "Nightly must have a Validate min_score step"
    assert gate_idx is not None, "Nightly must have a Run mutation gate on PVE step"
    assert validate_idx < gate_idx, "Validate min_score must precede Run mutation gate on PVE"
