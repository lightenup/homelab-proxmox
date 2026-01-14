from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


@dataclass(frozen=True)
class PlanIdentity:
    plan_run_id: str
    plan_created_at: str
    planfile_hash: Optional[str] = None

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "plan_run_id": self.plan_run_id,
            "plan_created_at": self.plan_created_at,
            "planfile_hash": self.planfile_hash,
        }


def identity_path_for_run(run_dir: Path) -> Path:
    return run_dir / "reports" / "plan" / "plan-identity.json"


def write_plan_identity(run_dir: Path, identity: PlanIdentity) -> Path:
    path = identity_path_for_run(run_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(identity.to_json_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_plan_identity(path: str | Path) -> PlanIdentity:
    p = Path(path)
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        raise ValueError(f"Failed to read/parse plan identity JSON: {p}: {e}") from e

    return PlanIdentity(
        plan_run_id=doc["plan_run_id"],
        plan_created_at=doc["plan_created_at"],
        planfile_hash=doc.get("planfile_hash"),
    )
