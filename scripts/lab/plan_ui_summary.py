#!/usr/bin/env python3
import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


SCHEMA_VERSION = "1.0.0"


def _is_replace(actions: List[str]) -> bool:
    return ("create" in actions) and ("delete" in actions)


def _classify(actions: List[str]) -> str:
    if actions == ["create"]:
        return "create"
    if actions == ["update"]:
        return "update"
    if actions == ["delete"]:
        return "destroy"
    if _is_replace(actions):
        return "replace"
    if actions == ["read"]:
        return "read"
    return "other"


def _severity(resource_class: str) -> int:
    # Lower is more severe / should be shown first.
    if resource_class == "destroy":
        return 0
    if resource_class == "replace":
        return 1
    if resource_class == "update":
        return 2
    if resource_class == "create":
        return 3
    return 4


def _token_required(environment: str, destructive: bool) -> Optional[str]:
    if not destructive:
        return None

    if environment == "lab":
        return "apply-lab-destructive"
    if environment == "prod":
        return "deploy-prod-destructive"

    raise ValueError(f"Invalid environment: {environment!r}")


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=False)
        f.write("\n")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate bounded plan UI summary JSON from blast-radius.json")
    p.add_argument("--blast-radius", required=True, help="Path to blast-radius.json")
    p.add_argument("--output", required=True, help="Path to write plan UI summary JSON")
    p.add_argument("--limit", type=int, default=50, help="Max number of resources to include")
    p.add_argument("--run-id", default="", help="Override run_id if blast-radius.json does not include it")
    p.add_argument("--environment", default="", help="Override environment (lab|prod) if blast-radius.json does not include it")
    p.add_argument("--service", default="", help="Override service if blast-radius.json does not include it")
    p.add_argument(
        "--pve-runs-dir",
        default="/var/lib/homelab-proxmox/artifacts/service-deploy-runs",
        help="PVE runs directory used for evidence pointers",
    )
    return p.parse_args()


def main() -> int:
    args = _parse_args()

    blast_path = Path(args.blast_radius)
    out_path = Path(args.output)

    if args.limit <= 0:
        raise SystemExit("--limit must be > 0")

    blast = _load_json(blast_path)

    run_id = str(blast.get("run_id", "") or args.run_id or "")
    environment = str(blast.get("environment", "") or args.environment or "")
    service = str(blast.get("service", "") or args.service or "")

    if not run_id:
        raise SystemExit("missing run_id (provide via blast-radius.json or --run-id)")
    if environment not in ("lab", "prod"):
        raise SystemExit("missing/invalid environment (provide via blast-radius.json or --environment lab|prod)")
    if not service:
        raise SystemExit("missing service (provide via blast-radius.json or --service)")

    counts = blast.get("counts")
    if not isinstance(counts, dict):
        # Back-compat for legacy fixture shape.
        counts = {
            "create": blast.get("create", 0),
            "update": blast.get("update", 0),
            "replace": blast.get("replace", 0),
            "destroy": blast.get("destroy", 0),
        }

    destructive = bool(blast.get("destructive", False))

    resources_raw = blast.get("resources") or []
    resources: List[Dict[str, Any]] = []
    for item in resources_raw:
        address = item.get("address")
        actions = item.get("actions")
        if not isinstance(address, str) or not address:
            continue
        if not isinstance(actions, list) or not all(isinstance(a, str) for a in actions):
            continue
        # Filter no-op changes from UI summary.
        if actions == ["no-op"]:
            continue

        resource_class = _classify(actions)
        resources.append({"address": address, "actions": actions, "class": resource_class})

    resources.sort(key=lambda r: (_severity(str(r["class"])), str(r["address"])))

    resources_total = len(resources)
    resources_shown = min(resources_total, int(args.limit))
    shown = resources[:resources_shown]

    summary = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "environment": environment,
        "service": service,
        "destructive": destructive,
        "confirmation_token_required": _token_required(environment, destructive),
        "counts": {
            "create": int(counts.get("create", 0)),
            "update": int(counts.get("update", 0)),
            "replace": int(counts.get("replace", 0)),
            "destroy": int(counts.get("destroy", 0)),
        },
        "resources_total": resources_total,
        "resources_shown": resources_shown,
        "truncated": resources_shown < resources_total,
        "resources": shown,
        "evidence": {
            "pve_runs_dir": str(args.pve_runs_dir),
            "pve_run_id_dir": f"{str(args.pve_runs_dir).rstrip('/')}/{run_id}",
        },
    }

    _write_json(out_path, summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
