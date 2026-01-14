from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .models import Action, Environment, Status


@dataclass(frozen=True)
class ProvenanceRecord:
    environment: Environment
    service: str
    action: Action
    source_ref: Optional[str]
    started_at: str
    finished_at: Optional[str]
    status: Status
    exit_code: Optional[int]
    from_plan_run_id: Optional[str] = None

    def to_json_dict(self) -> dict[str, Any]:
        doc: dict[str, Any] = {
            "environment": self.environment,
            "service": self.service,
            "action": self.action,
            "source_ref": self.source_ref,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "exit_code": self.exit_code,
        }
        if self.from_plan_run_id is not None:
            doc["from_plan_run_id"] = self.from_plan_run_id
        return doc


def write_provenance(run_dir: Path, record: ProvenanceRecord) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "provenance.json"
    path.write_text(json.dumps(record.to_json_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_provenance(path: str | Path) -> ProvenanceRecord:
    p = Path(path)
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        raise ValueError(f"Failed to read/parse provenance JSON: {p}: {e}") from e

    return ProvenanceRecord(
        environment=doc["environment"],
        service=doc["service"],
        action=doc["action"],
        source_ref=doc.get("source_ref"),
        started_at=doc["started_at"],
        finished_at=doc.get("finished_at"),
        status=doc["status"],
        exit_code=doc.get("exit_code"),
        from_plan_run_id=doc.get("from_plan_run_id"),
    )
