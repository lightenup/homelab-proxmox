from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from .exec import run_checked
from .models import Action, Environment
from .plan_identity import PlanIdentity, identity_path_for_run, load_plan_identity, write_plan_identity
from .provenance import ProvenanceRecord, load_provenance, write_provenance


@dataclass(frozen=True)
class RunRequest:
    service: str
    environment: Environment
    action: Action
    source_ref: Optional[str] = None
    evidence_root: Optional[str] = None
    runner_script_path: Optional[str] = None
    from_plan_run_id: Optional[str] = None
    require_source_ref_match: bool = True


def _default_path_env() -> str:
    # Keep conservative defaults for macOS/Linux when env is sanitized.
    return "/usr/bin:/bin:/usr/sbin:/sbin"


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _runs_dir(evidence_root: Path, runs_dir_name: str) -> Path:
    return evidence_root / runs_dir_name


def _resolve_plan_run_dir(evidence_root: Path, runs_dir_name: str, plan_run_id: str) -> Path:
    return _runs_dir(evidence_root, runs_dir_name) / plan_run_id


def _enforce_apply_associated_plan(request: RunRequest, evidence_root: Path, runs_dir_name: str) -> None:
    if request.action != "apply" or not request.from_plan_run_id:
        return

    plan_run_dir = _resolve_plan_run_dir(evidence_root, runs_dir_name, request.from_plan_run_id)
    if not plan_run_dir.exists() or not plan_run_dir.is_dir():
        raise ValueError(
            "Plan run not found for --from-plan-run-id. "
            f"Expected directory: {plan_run_dir}"
        )

    plan_identity_path = identity_path_for_run(plan_run_dir)
    if not plan_identity_path.exists():
        raise ValueError(
            "Plan identity file missing for --from-plan-run-id. "
            f"Expected file: {plan_identity_path}"
        )

    plan_identity = load_plan_identity(plan_identity_path)
    if plan_identity.plan_run_id != request.from_plan_run_id:
        raise ValueError(
            "Plan identity mismatch: plan_run_id in plan-identity.json does not match "
            "--from-plan-run-id."
        )

    plan_provenance_path = plan_run_dir / "provenance.json"
    if not plan_provenance_path.exists():
        raise ValueError(
            "Plan provenance file missing for --from-plan-run-id. "
            f"Expected file: {plan_provenance_path}"
        )

    plan_prov = load_provenance(plan_provenance_path)
    if plan_prov.action != "plan":
        raise ValueError(
            "Referenced run is not a plan run. "
            f"Expected action=plan, got action={plan_prov.action}"
        )
    if plan_prov.environment != request.environment or plan_prov.service != request.service:
        raise ValueError(
            "Plan provenance does not match requested apply. "
            f"Expected service={request.service}, environment={request.environment}. "
            f"Got service={plan_prov.service}, environment={plan_prov.environment}"
        )

    if request.require_source_ref_match:
        if plan_prov.source_ref != request.source_ref:
            raise ValueError(
                "Plan source_ref does not match requested apply source_ref. "
                f"Expected source_ref={request.source_ref!r}, got source_ref={plan_prov.source_ref!r}. "
                "Re-run plan with the intended source-ref and pass its run id to apply."
            )


def _find_latest_run_dir(evidence_root: Path, runs_dir_name: str) -> Path | None:
    runs_dir = evidence_root / runs_dir_name
    if not runs_dir.exists() or not runs_dir.is_dir():
        return None
    candidates = [p for p in runs_dir.iterdir() if p.is_dir()]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def run(request: RunRequest):
    """Execute a plan/apply/verify run and return a bounded RunResponse.

    Initial MVP is a thin wrapper around an underlying bash entrypoint.
    """

    from .models import EvidencePointer, RunResponse, RunSummary

    if not request.service:
        raise ValueError("--service is required")
    if request.environment not in ("lab", "prod"):
        raise ValueError("--environment must be 'lab' or 'prod'")
    if request.action not in ("plan", "apply", "verify"):
        raise ValueError("action must be plan|apply|verify")
    if not request.evidence_root:
        raise ValueError("--evidence-root is required")

    evidence_root = Path(request.evidence_root).expanduser().resolve()
    evidence_root.mkdir(parents=True, exist_ok=True)
    if not evidence_root.is_dir():
        raise ValueError(f"evidence root is not a directory: {evidence_root}")

    runner_script = Path(
        request.runner_script_path or "scripts/lab/pve-service-deploy"
    ).expanduser()
    if not runner_script.exists():
        raise ValueError(f"runner script not found: {runner_script}")

    base_env = dict(os.environ)
    if not base_env.get("PATH"):
        base_env["PATH"] = _default_path_env()
    # Minimal env used by the US1 fake deploy script fixture.
    base_env.setdefault("ARTIFACT_ROOT", str(evidence_root))
    base_env.setdefault("ARTIFACT_RUNS_DIR", "runs")

    _enforce_apply_associated_plan(request, evidence_root, base_env["ARTIFACT_RUNS_DIR"])

    argv = [
        str(runner_script),
        request.action,
        "--environment",
        request.environment,
        "--service",
        request.service,
    ]

    started_at = _utc_now_iso()
    result = run_checked(argv, env=base_env)
    finished_at = _utc_now_iso()

    status = "succeeded" if result.returncode == 0 else "failed"
    latest_run_dir = _find_latest_run_dir(evidence_root, base_env["ARTIFACT_RUNS_DIR"])
    run_id = latest_run_dir.name if latest_run_dir else ""

    if latest_run_dir is not None:
        write_provenance(
            latest_run_dir,
            ProvenanceRecord(
                environment=request.environment,
                service=request.service,
                action=request.action,
                source_ref=request.source_ref,
                started_at=started_at,
                finished_at=finished_at,
                status=status,  # type: ignore[arg-type]
                exit_code=result.returncode,
                from_plan_run_id=request.from_plan_run_id,
            ),
        )

        if request.action == "plan":
            write_plan_identity(
                latest_run_dir,
                PlanIdentity(
                    plan_run_id=run_id,
                    plan_created_at=finished_at,
                    planfile_hash=None,
                ),
            )

    highlights = [f"runner: {runner_script}"]
    if latest_run_dir:
        highlights.append(f"evidence: {latest_run_dir}")

    errors: list[str] = []
    if result.returncode != 0:
        if result.stderr.strip():
            errors.append(result.stderr.strip())
        else:
            errors.append("Underlying runner script failed")

    warnings: list[str] = []
    if latest_run_dir is None:
        warnings.append("No evidence pack directory detected under evidence root")

    evidence_pointers = [
        EvidencePointer(label="evidence-root", location=str(evidence_root)),
    ]
    if latest_run_dir:
        evidence_pointers.append(EvidencePointer(label="run", location=str(latest_run_dir)))

    resp = RunResponse(
        run_id=run_id,
        service=request.service,
        environment=request.environment,
        action=request.action,
        status=status,  # type: ignore[arg-type]
        exit_code=result.returncode,
        summary=RunSummary(
            title=f"{request.action} {status}",
            bounded=True,
            highlights=highlights,
            warnings=warnings,
            errors=errors,
            next_steps=[],
        ),
        evidence=evidence_pointers,
    )
    return resp
