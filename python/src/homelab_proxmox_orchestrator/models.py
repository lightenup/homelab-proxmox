from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Optional

Environment = Literal["lab", "prod"]
Action = Literal["plan", "apply", "verify"]
Status = Literal["queued", "running", "succeeded", "failed", "canceled"]


@dataclass(frozen=True)
class AutomationRun:
    run_id: str
    service: str
    environment: Environment
    action: Action
    source_ref: Optional[str] = None


@dataclass(frozen=True)
class EvidencePointer:
    label: str
    location: str


@dataclass(frozen=True)
class RunSummary:
    title: str
    bounded: bool
    highlights: list[str]
    warnings: list[str]
    errors: list[str]
    next_steps: list[str]


@dataclass(frozen=True)
class RunResponse:
    run_id: str
    service: str
    environment: Environment
    action: Action
    status: Status
    exit_code: Optional[int]
    summary: RunSummary
    evidence: list[EvidencePointer]

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "runId": self.run_id,
            "service": self.service,
            "environment": self.environment,
            "action": self.action,
            "status": self.status,
            "exitCode": self.exit_code,
            "summary": {
                "title": self.summary.title,
                "bounded": self.summary.bounded,
                "highlights": list(self.summary.highlights),
                "warnings": list(self.summary.warnings),
                "errors": list(self.summary.errors),
                "nextSteps": list(self.summary.next_steps),
            },
            "evidence": [
                {"label": e.label, "location": e.location} for e in self.evidence
            ],
        }
