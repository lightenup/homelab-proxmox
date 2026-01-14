from __future__ import annotations

import argparse
import json
import sys

from .models import EvidencePointer, RunResponse, RunSummary
from .orchestrator import RunRequest, run
from .summary_from_evidence import load_summary_input
from .summary_markdown import render_markdown


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="homelab-proxmox-orchestrator")
    sub = p.add_subparsers(dest="command", required=True)

    def add_common_run_args(cmd: argparse.ArgumentParser) -> None:
        cmd.add_argument("--environment", choices=["lab", "prod"], required=True)
        cmd.add_argument("--service", required=True)
        cmd.add_argument("--source-ref")
        cmd.add_argument("--evidence-root", required=True)
        cmd.add_argument("--runner-script-path")
        cmd.add_argument("--from-plan-run-id")
        cmd.add_argument(
            "--require-source-ref-match",
            default=True,
            action=argparse.BooleanOptionalAction,
            help="Require source-ref match when using --from-plan-run-id (default: true)",
        )

    plan = sub.add_parser("plan", help="Run a plan")
    add_common_run_args(plan)

    apply = sub.add_parser("apply", help="Run an apply")
    add_common_run_args(apply)

    verify = sub.add_parser("verify", help="Run a verify")
    add_common_run_args(verify)

    # Back-compat helper for callers who prefer a single entry point.
    run_cmd = sub.add_parser("run", help="Run plan/apply/verify")
    run_cmd.add_argument("action", choices=["plan", "apply", "verify"])
    add_common_run_args(run_cmd)

    summary = sub.add_parser("summary", help="Render bounded markdown summary from evidence pack")
    summary.add_argument("--evidence-pack", required=True)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command in {"plan", "apply", "verify"}:
        action = str(args.command)
    elif args.command == "run":
        action = str(args.action)
    else:
        action = ""

    if args.command in {"plan", "apply", "verify", "run"}:
        try:
            resp = run(
                RunRequest(
                    service=str(args.service),
                    environment=str(args.environment),
                    action=action,  # type: ignore[arg-type]
                    source_ref=(str(args.source_ref) if args.source_ref else None),
                    evidence_root=str(args.evidence_root),
                    runner_script_path=(
                        str(args.runner_script_path) if args.runner_script_path else None
                    ),
                    from_plan_run_id=(
                        str(args.from_plan_run_id) if args.from_plan_run_id else None
                    ),
                    require_source_ref_match=bool(args.require_source_ref_match),
                )
            )
        except Exception as e:
            resp = RunResponse(
                run_id="",
                service=str(getattr(args, "service", "")),
                environment=str(getattr(args, "environment", "lab")),
                action=action or "plan",  # type: ignore[arg-type]
                status="failed",
                exit_code=2,
                summary=RunSummary(
                    title="Runner error",
                    bounded=True,
                    highlights=[],
                    warnings=[],
                    errors=[str(e)],
                    next_steps=["Fix inputs and re-run"],
                ),
                evidence=[EvidencePointer(label="repo", location=".")],
            )

        json.dump(resp.to_json_dict(), sys.stdout)
        sys.stdout.write("\n")
        return int(resp.exit_code or 0)

    if args.command == "summary":
        summary_input = load_summary_input(args.evidence_pack)
        md = render_markdown(kind=summary_input.kind, obj=summary_input.obj)
        sys.stdout.write(md)
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
