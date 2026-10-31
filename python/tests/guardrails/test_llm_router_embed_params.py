"""Guard test: the gateway passes `dimensions` through to the embed deployment (spec 097).

The memory server sets HINDSIGHT_API_EMBEDDINGS_OPENAI_DIMENSIONS, so it sends `dimensions` on
every embedding request. LiteLLM v1.83.3 refuses that for an openai/ model (400
UnsupportedParamsError), whatever drop_params says; allowed_openai_params on the deployment
passes it through (reproduced 2026-10-31, first PROD deploy probe). These two settings must move
together.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, Undefined

ROOT = Path(__file__).resolve().parents[3]
VARS = yaml.safe_load((ROOT / "ansible/group_vars/services/vars.yml").read_text())


class _Stub(Undefined):
    def __str__(self) -> str:
        return f"STUB_{self._undefined_name}"

    def __iter__(self):
        return iter(())


def _model_list() -> list[dict]:
    env = Environment(loader=FileSystemLoader(str(ROOT / "ansible/roles/llm_router/templates")), undefined=_Stub)
    env.filters["to_json"] = json.dumps
    rendered = env.get_template("config.yaml.j2").render(llm_router_aliases=VARS["llm_router_aliases"])
    return yaml.safe_load(rendered)["model_list"]


def test_embed_deployment_passes_dimensions_through():
    embed = [m for m in _model_list() if m["model_name"] == "hermes-embed"]
    assert embed and all(m["litellm_params"].get("allowed_openai_params") == ["dimensions"] for m in embed)


def test_no_other_deployment_widens_its_parameters():
    others = [m for m in _model_list() if m["model_name"] != "hermes-embed"]
    assert others and all("allowed_openai_params" not in m["litellm_params"] for m in others)


def test_memory_server_still_sends_dimensions():
    env_template = (ROOT / "ansible/roles/memory/templates/server.env.j2").read_text()
    assert "HINDSIGHT_API_EMBEDDINGS_OPENAI_DIMENSIONS=1024" in env_template
