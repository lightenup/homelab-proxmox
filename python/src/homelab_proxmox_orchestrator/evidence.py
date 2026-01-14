from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class EvidencePack:
    path: Path


class EvidenceError(RuntimeError):
    pass


def resolve_pack(path: str | Path) -> EvidencePack:
    p = Path(path).expanduser()
    if not p.exists():
        raise EvidenceError(f"Evidence pack not found: {p}")
    if not p.is_dir():
        raise EvidenceError(f"Evidence pack path is not a directory: {p}")
    return EvidencePack(path=p)


def load_json(path: str | Path) -> Any:
    p = Path(path)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        raise EvidenceError(f"Failed to read/parse JSON: {p}: {e}") from e


def require_files(pack: EvidencePack, required: Iterable[str]) -> list[str]:
    missing: list[str] = []
    for rel in required:
        if not (pack.path / rel).exists():
            missing.append(rel)
    return missing


def ensure_required_files(pack: EvidencePack, required: Iterable[str]) -> None:
    missing = require_files(pack, required)
    if missing:
        joined = ", ".join(missing)
        raise EvidenceError(f"Evidence pack missing required files: {joined}")


def find_first_existing(pack: EvidencePack, candidates: Iterable[str]) -> Path | None:
    for rel in candidates:
        p = pack.path / rel
        if p.exists():
            return p
    return None
