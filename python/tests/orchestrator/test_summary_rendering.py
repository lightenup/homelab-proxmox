from __future__ import annotations

from homelab_proxmox_orchestrator.summary_from_evidence import load_summary_input
from homelab_proxmox_orchestrator.summary_markdown import (
    render_markdown,
    render_markdown_from_plan_ui_summary,
)


def test_summary_loader_picks_rebuild_summary_for_valid_fixture():
    inp = load_summary_input("scripts/lab/fixtures/evidence-packs/valid")
    assert inp.kind == "rebuild-summary"


def test_plan_ui_renderer_includes_token_and_truncation_line():
    obj = {
        "run_id": "r1",
        "environment": "lab",
        "service": "ntfy",
        "destructive": True,
        "confirmation_token_required": "TOKEN123",
        "counts": {"create": 1, "update": 2, "replace": 3, "destroy": 4},
        "resources": [
            {"address": "x", "class": "create", "actions": ["create"]},
        ],
        "truncated": True,
        "resources_total": 10,
        "resources_shown": 1,
        "evidence": {"pve_runs_dir": "/runs", "pve_run_id_dir": "/runs/r1"},
    }

    md = render_markdown_from_plan_ui_summary(obj)
    assert "confirmation token required: `TOKEN123`" in md
    assert "…and **9** more" in md


def test_render_markdown_bounds_output_lines():
    obj = {
        "run_id": "r1",
        "environment": "lab",
        "service": "ntfy",
        "destructive": False,
        "confirmation_token_required": None,
        "counts": {"create": 0, "update": 0, "replace": 0, "destroy": 0},
        "resources": [],
        "truncated": False,
        "resources_total": 0,
        "resources_shown": 0,
        "evidence": {"pve_runs_dir": "/runs", "pve_run_id_dir": "/runs/r1"},
    }

    md = render_markdown(kind="plan-ui", obj=obj, max_lines=3, max_bytes=10_000)
    assert len(md.splitlines()) <= 3
