#!/usr/bin/env python3
"""Score and report from mutmut 3.8 CICD stats and .meta files (spec 087).

Reads mutmut-cicd-stats.json and every src/homelab_proxmox_orchestrator/**/*.py.meta
under the mutants dir. Writes report.json (schema 1, contracts/published-results.md)
and survivors.txt. Prints counts, score line, and top 10 survivor modules.

Status map copied from data-model.md, referencing mutmut 3.8.0's mutmut/stats.py.

Exit: 0 = pass, 1 = below gate, 2 = no results or incomplete run.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# mutmut 3.8.0 exit codes (mutmut/stats.py):
# 0=survived, 1=killed, 3=killed, 5=no_tests, 33=no_tests,
# 35=suspicious, 36=timeout, None=not_checked
STATUS_BY_EXIT_CODE = {
    1: "killed",
    3: "killed",
    0: "survived",
    5: "no_tests",
    33: "no_tests",
    36: "timeout",
    35: "suspicious",
}


def _status_for(exit_code: int | None) -> str:
    if exit_code is None:
        return "not_checked"
    return STATUS_BY_EXIT_CODE.get(exit_code, "unknown")


def _module_from_meta_path(meta_path: Path, src_root: Path) -> str:
    rel = meta_path.relative_to(src_root)
    parts = list(rel.parts)
    stem = parts[-1].removesuffix(".meta")
    if stem.endswith(".py"):
        stem = stem[:-3]
    parts[-1] = stem
    return ".".join(parts)


def _read_meta(meta_path: Path) -> dict:
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _count_not_checked(mutants_dir: Path) -> int:
    """Count mutants with no verdict (exit code null in .meta).

    mutmut-cicd-stats.json omits not_checked, so a partial run would otherwise
    score only the mutants that happened to finish.
    """
    src_root = mutants_dir / "src" / "homelab_proxmox_orchestrator"
    n = 0
    for meta_path in src_root.rglob("*.py.meta"):
        n += sum(1 for ec in _read_meta(meta_path).get("exit_code_by_key", {}).values() if ec is None)
    return n


def _build_report(
    mutants_dir: Path,
    *,
    floor: float,
    margin: float,
    commit: str,
    mutmut_version: str,
) -> dict:
    stats_path = mutants_dir / "mutmut-cicd-stats.json"
    stats = json.loads(stats_path.read_text(encoding="utf-8"))

    src_root = mutants_dir / "src" / "homelab_proxmox_orchestrator"
    module_counts: dict[str, dict[str, int]] = {}
    for meta_path in sorted(src_root.rglob("*.py.meta")):
        meta = _read_meta(meta_path)
        exit_codes = meta.get("exit_code_by_key", {})
        module = _module_from_meta_path(meta_path, src_root)
        counts = module_counts.setdefault(module, {"killed": 0, "survived": 0, "no_tests": 0})
        for ec in exit_codes.values():
            status = _status_for(ec)
            if status in counts:
                counts[status] += 1

    survivors_by_module = [
        {
            "module": m,
            "survived": c["survived"],
            "killed": c["killed"],
            "no_tests": c["no_tests"],
        }
        for m, c in sorted(
            module_counts.items(),
            key=lambda x: (-x[1]["survived"], x[0]),
        )
    ]

    killed = stats.get("killed", 0)
    survived = stats.get("survived", 0)
    denom = killed + survived
    score = round(100.0 * killed / denom, 2) if denom else 100.0
    gate = floor - margin
    passed = score >= gate

    return {
        "schema": 1,
        "commit": commit,
        "finished_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mutmut_version": mutmut_version,
        "counts": {
            "killed": killed,
            "survived": survived,
            "no_tests": stats.get("no_tests", 0),
            "timeout": stats.get("timeout", 0),
            "suspicious": stats.get("suspicious", 0),
            "skipped": stats.get("skipped", 0),
            "segfault": stats.get("segfault", 0),
            "total": stats.get("total", 0),
        },
        "score": score,
        "floor": floor,
        "margin": margin,
        "gate": gate,
        "passed": passed,
        "survivors_by_module": survivors_by_module,
    }


def _write_outputs(mutants_dir: Path, report: dict) -> None:
    (mutants_dir / "report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    lines = [f"{m['survived']}  {m['module']}" for m in report["survivors_by_module"]]
    (mutants_dir / "survivors.txt").write_text("\n".join(lines) + "\n" if lines else "", encoding="utf-8")


def _print_summary(report: dict) -> None:
    c = report["counts"]
    print(f">> killed={c['killed']} survived={c['survived']} no_tests={c['no_tests']} timeout={c['timeout']} suspicious={c['suspicious']} total={c['total']}")
    print(f">> mutation score: {report['score']:.2f}%  (floor {report['floor']:.2f}% - margin {report['margin']:.2f} = gate {report['gate']:.2f}%)")
    top10 = report["survivors_by_module"][:10]
    if top10:
        print(">> top survivor modules:")
        for m in top10:
            print(f"   {m['survived']:>4}  {m['module']}")

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"\n## Mutation gate\n\n")
            f.write(f"| Metric | Value |\n|---|---|\n")
            f.write(f"| Score | {report['score']:.2f}% |\n")
            f.write(f"| Floor | {report['floor']:.2f}% |\n")
            f.write(f"| Margin | {report['margin']:.2f} |\n")
            f.write(f"| Gate | {report['gate']:.2f}% |\n")
            f.write(f"| Killed | {c['killed']} |\n")
            f.write(f"| Survived | {c['survived']} |\n")
            f.write(f"| No tests | {c['no_tests']} |\n")
            f.write(f"| Total | {c['total']} |\n")
            if top10:
                f.write(f"\n### Top survivor modules\n\n")
                f.write(f"| Survived | Module |\n|---|---|\n")
                for m in top10:
                    f.write(f"| {m['survived']} | {m['module']} |\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mutmut 3.8 score and report")
    parser.add_argument("--mutants-dir", default="mutants")
    parser.add_argument("--floor", type=float, required=True)
    parser.add_argument("--margin", type=float, default=1.0)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--mutmut-version", required=True)
    args = parser.parse_args(argv)

    mutants_dir = Path(args.mutants_dir)
    stats_path = mutants_dir / "mutmut-cicd-stats.json"
    if not stats_path.is_file():
        print("::error::mutmut produced no results (run failed)", file=sys.stderr)
        return 2

    stats = json.loads(stats_path.read_text(encoding="utf-8"))
    if stats.get("total", 0) == 0:
        print("::error::mutmut produced no results (run failed)", file=sys.stderr)
        return 2

    not_checked = _count_not_checked(mutants_dir)
    interrupted = stats.get("check_was_interrupted_by_user", 0)
    if not_checked or interrupted:
        print(
            f"::error::mutmut run incomplete ({not_checked} not checked, {interrupted} interrupted)",
            file=sys.stderr,
        )
        return 2

    report = _build_report(
        mutants_dir,
        floor=args.floor,
        margin=args.margin,
        commit=args.commit,
        mutmut_version=args.mutmut_version,
    )
    _write_outputs(mutants_dir, report)
    _print_summary(report)

    if not report["passed"]:
        print(f"::error::Mutation score {report['score']:.2f}% is below the gate {report['gate']:.2f}%")
        return 1
    print(">> mutation gate PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
