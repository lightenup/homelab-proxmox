from __future__ import annotations

from pathlib import Path

import pytest

from homelab_proxmox_orchestrator.evidence import EvidenceError
from homelab_proxmox_orchestrator.summary_from_evidence import load_summary_input


def test_summary_loader_raises_when_no_supported_files(tmp_path: Path):
    pack = tmp_path / "pack"
    pack.mkdir()

    with pytest.raises(EvidenceError, match=r"no supported summary input"):
        load_summary_input(pack)


def test_summary_loader_prefers_plan_ui_when_both_present(tmp_path: Path):
    pack = tmp_path / "pack"
    pack.mkdir()
    (pack / "plan-ui-summary.json").write_text("{}", encoding="utf-8")
    (pack / "summary.json").write_text("{}", encoding="utf-8")

    inp = load_summary_input(pack)
    assert inp.kind == "plan-ui"
    assert inp.path.name == "plan-ui-summary.json"
