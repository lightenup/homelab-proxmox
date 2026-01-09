#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple


SCHEMA_VERSION = "1.0.0"


def _err(errors: List[str], msg: str) -> None:
    errors.append(msg)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate(obj: Any) -> List[str]:
    errors: List[str] = []
    if not isinstance(obj, dict):
        return ["$ must be an object"]

    if obj.get("schema_version") != SCHEMA_VERSION:
        _err(errors, f"$.schema_version must be '{SCHEMA_VERSION}'")

    run_id = obj.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        _err(errors, "$.run_id must be a non-empty string")

    env = obj.get("environment")
    if env not in ("lab", "prod"):
        _err(errors, "$.environment must be 'lab' or 'prod'")

    service = obj.get("service")
    if not isinstance(service, str) or not service:
        _err(errors, "$.service must be a non-empty string")

    destructive = obj.get("destructive")
    if not isinstance(destructive, bool):
        _err(errors, "$.destructive must be boolean")

    token = obj.get("confirmation_token_required")
    if token is not None and not isinstance(token, str):
        _err(errors, "$.confirmation_token_required must be string or null")

    counts = obj.get("counts")
    if not isinstance(counts, dict):
        _err(errors, "$.counts must be an object")
    else:
        for k in ("create", "update", "replace", "destroy"):
            v = counts.get(k)
            if not _is_int(v) or v < 0:
                _err(errors, f"$.counts.{k} must be integer >= 0")

    for k in ("resources_total", "resources_shown"):
        v = obj.get(k)
        if not _is_int(v) or v < 0:
            _err(errors, f"$.{k} must be integer >= 0")

    truncated = obj.get("truncated")
    if not isinstance(truncated, bool):
        _err(errors, "$.truncated must be boolean")

    resources = obj.get("resources")
    if not isinstance(resources, list):
        _err(errors, "$.resources must be an array")
    else:
        for i, r in enumerate(resources):
            if not isinstance(r, dict):
                _err(errors, f"$.resources[{i}] must be object")
                continue
            addr = r.get("address")
            if not isinstance(addr, str) or not addr:
                _err(errors, f"$.resources[{i}].address must be non-empty string")
            actions = r.get("actions")
            if not isinstance(actions, list) or not all(isinstance(a, str) for a in actions):
                _err(errors, f"$.resources[{i}].actions must be string array")
            cls = r.get("class")
            if cls not in ("create", "update", "replace", "destroy", "read", "other"):
                _err(errors, f"$.resources[{i}].class invalid")

    evidence = obj.get("evidence")
    if not isinstance(evidence, dict):
        _err(errors, "$.evidence must be object")
    else:
        for k in ("pve_runs_dir", "pve_run_id_dir"):
            v = evidence.get(k)
            if not isinstance(v, str) or not v:
                _err(errors, f"$.evidence.{k} must be non-empty string")

    return errors


def main() -> int:
    p = argparse.ArgumentParser(description="Validate a Plan UI Summary JSON (Spec 025)")
    p.add_argument("path", help="Path to plan UI summary JSON")
    args = p.parse_args()

    path = Path(args.path)
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"ERROR: failed to read/parse JSON: {e}", file=sys.stderr)
        return 2

    errors = validate(obj)
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
