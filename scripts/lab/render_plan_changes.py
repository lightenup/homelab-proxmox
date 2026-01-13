#!/usr/bin/env python3
"""Render a safe, bounded summary of Terraform plan changes.

This script intentionally avoids printing attribute values (which may contain
secrets). It prints resource addresses, actions, and (for updates) changed
attribute *paths* only.

Input is a Terraform plan JSON as produced by:
  terraform show -json <planfile>
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Iterable


def _sym(actions: list[str]) -> str:
    if actions == ["create"]:
        return "+"
    if actions == ["update"]:
        return "~"
    if actions == ["delete"]:
        return "-"
    if "create" in actions and "delete" in actions:
        return "-/+"
    return "/".join(actions) if actions else "?"


def _path_join(prefix: str, seg: str) -> str:
    if not prefix:
        return seg
    if seg.startswith("["):
        return f"{prefix}{seg}"
    return f"{prefix}.{seg}"


def _diff_paths(before: Any, after: Any, prefix: str = "") -> set[str]:
    paths: set[str] = set()

    if type(before) is not type(after):
        if prefix:
            paths.add(prefix)
        else:
            paths.add("<root>")
        return paths

    if isinstance(before, dict):
        keys = set(before.keys()) | set(after.keys())
        for key in keys:
            next_prefix = _path_join(prefix, str(key))
            if key not in before or key not in after:
                paths.add(next_prefix)
                continue
            paths |= _diff_paths(before[key], after[key], next_prefix)
        return paths

    if isinstance(before, list):
        if len(before) != len(after):
            paths.add(prefix or "<root>")
        for index in range(min(len(before), len(after))):
            next_prefix = _path_join(prefix, f"[{index}]")
            paths |= _diff_paths(before[index], after[index], next_prefix)
        return paths

    # Scalars / null
    if before != after:
        paths.add(prefix or "<root>")
    return paths


def _true_paths(node: Any, prefix: str = "") -> set[str]:
    """Return paths for truthy leaves in the after_unknown structure."""
    paths: set[str] = set()

    if node is True:
        paths.add(prefix or "<root>")
        return paths
    if node in (False, None):
        return paths

    if isinstance(node, dict):
        for key, value in node.items():
            paths |= _true_paths(value, _path_join(prefix, str(key)))
        return paths

    if isinstance(node, list):
        for index, value in enumerate(node):
            paths |= _true_paths(value, _path_join(prefix, f"[{index}]"))
        return paths

    return paths


def _iter_resource_changes(plan: dict[str, Any]) -> Iterable[dict[str, Any]]:
    rcs = plan.get("resource_changes")
    if isinstance(rcs, list):
        for rc in rcs:
            if isinstance(rc, dict):
                yield rc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan-json", required=True)
    parser.add_argument("--max-resources", type=int, default=50)
    parser.add_argument("--max-paths", type=int, default=12)
    parser.add_argument("--max-lines", type=int, default=120)
    args = parser.parse_args()

    try:
        with open(args.plan_json, "r", encoding="utf-8") as f:
            plan = json.load(f)
    except FileNotFoundError:
        return 0
    except json.JSONDecodeError:
        print("<invalid plan.json>")
        return 0

    lines_emitted = 0
    resources_emitted = 0

    for rc in _iter_resource_changes(plan):
        if resources_emitted >= args.max_resources or lines_emitted >= args.max_lines:
            break

        address = rc.get("address")
        change = rc.get("change") if isinstance(rc.get("change"), dict) else {}
        actions = change.get("actions") if isinstance(change.get("actions"), list) else []

        if not isinstance(address, str) or not address:
            continue

        header = f"{_sym([str(a) for a in actions])} {address}"
        print(header)
        lines_emitted += 1
        resources_emitted += 1

        if actions == ["update"] and lines_emitted < args.max_lines:
            before = change.get("before")
            after = change.get("after")
            unknown = change.get("after_unknown")

            paths = _diff_paths(before, after)
            paths |= _true_paths(unknown)
            paths.discard("<root>")

            if paths:
                for path in sorted(paths)[: max(0, args.max_paths)]:
                    if lines_emitted >= args.max_lines:
                        break
                    print(f"  - {path}")
                    lines_emitted += 1

                remaining = len(paths) - min(len(paths), max(0, args.max_paths))
                if remaining > 0 and lines_emitted < args.max_lines:
                    print(f"  ... (+{remaining} more paths)")
                    lines_emitted += 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
