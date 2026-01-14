from pathlib import Path

from homelab_proxmox_orchestrator.evidence import (
    EvidenceError,
    ensure_required_files,
    find_first_existing,
    load_json,
    resolve_pack,
)


def test_resolve_pack_accepts_valid_fixture():
    pack = resolve_pack(Path("scripts/lab/fixtures/evidence-packs/valid"))
    assert pack.path.is_dir()


def test_resolve_pack_rejects_missing_path():
    try:
        resolve_pack(Path("scripts/lab/fixtures/evidence-packs/does-not-exist"))
    except EvidenceError as e:
        assert "not found" in str(e).lower()
    else:
        raise AssertionError("Expected EvidenceError")


def test_load_json_rejects_invalid_json(tmp_path: Path):
    p = tmp_path / "bad.json"
    p.write_text("{not-json}", encoding="utf-8")
    try:
        load_json(p)
    except EvidenceError as e:
        assert "parse" in str(e).lower()
    else:
        raise AssertionError("Expected EvidenceError")


def test_ensure_required_files_raises_for_missing(tmp_path: Path):
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    pack = resolve_pack(pack_dir)

    try:
        ensure_required_files(pack, ["a.json", "b.json"])
    except EvidenceError as e:
        msg = str(e)
        assert "missing required files" in msg.lower()
        assert "a.json" in msg
        assert "b.json" in msg
    else:
        raise AssertionError("Expected EvidenceError")


def test_find_first_existing_returns_none_if_no_candidates(tmp_path: Path):
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    pack = resolve_pack(pack_dir)
    assert find_first_existing(pack, ["x.json", "y.json"]) is None


def test_find_first_existing_returns_first_match(tmp_path: Path):
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    (pack_dir / "b.json").write_text("{}", encoding="utf-8")
    pack = resolve_pack(pack_dir)
    found = find_first_existing(pack, ["a.json", "b.json", "c.json"])
    assert found is not None
    assert found.name == "b.json"
