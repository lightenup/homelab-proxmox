from __future__ import annotations

from pathlib import Path

from homelab_proxmox_orchestrator.summary_from_evidence import load_summary_input
from homelab_proxmox_orchestrator.summary_markdown import render_markdown


def test_summary_markdown_matches_golden_valid_fixture():
    pack = Path("scripts/lab/fixtures/evidence-packs/valid")
    inp = load_summary_input(pack)
    md = render_markdown(kind=inp.kind, obj=inp.obj)

    golden = Path("python/tests/orchestrator/golden/valid_evidence_summary.md").read_text(encoding="utf-8")
    assert md == golden
