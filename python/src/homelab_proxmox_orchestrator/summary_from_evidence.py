from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from .evidence import EvidenceError, EvidencePack, load_json, resolve_pack

SummaryKind = Literal["plan-ui", "rebuild-summary"]


@dataclass(frozen=True)
class EvidenceSummaryInput:
    kind: SummaryKind
    path: Path
    obj: dict[str, Any]


def load_summary_input(evidence_pack: str | Path) -> EvidenceSummaryInput:
    pack: EvidencePack = resolve_pack(evidence_pack)

    plan_ui = pack.path / "plan-ui-summary.json"
    if plan_ui.exists():
        obj = load_json(plan_ui)
        if not isinstance(obj, dict):
            raise EvidenceError(f"plan-ui-summary.json must be an object: {plan_ui}")
        return EvidenceSummaryInput(kind="plan-ui", path=plan_ui, obj=obj)

    rebuild_summary = pack.path / "summary.json"
    if rebuild_summary.exists():
        obj = load_json(rebuild_summary)
        if not isinstance(obj, dict):
            raise EvidenceError(f"summary.json must be an object: {rebuild_summary}")
        return EvidenceSummaryInput(kind="rebuild-summary", path=rebuild_summary, obj=obj)

    raise EvidenceError(
        f"Evidence pack has no supported summary input (expected plan-ui-summary.json or summary.json): {pack.path}"
    )
