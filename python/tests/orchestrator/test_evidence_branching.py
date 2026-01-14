from __future__ import annotations

from pathlib import Path

import pytest

from homelab_proxmox_orchestrator.evidence import EvidenceError, resolve_pack


def test_resolve_pack_rejects_file_path(tmp_path: Path):
    p = tmp_path / "file.txt"
    p.write_text("x", encoding="utf-8")

    with pytest.raises(EvidenceError, match=r"not a directory"):
        resolve_pack(p)
