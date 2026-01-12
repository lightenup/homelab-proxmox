#!/usr/bin/env python3
"""Render an approval-friendly Markdown summary from evidence packs.

This is intentionally conservative: it only extracts high-signal, low-risk lines
(counts and recaps) to avoid dumping logs or secrets into the GitHub summary UI.

Inputs are local, already-fetched evidence directories (evidence/<env>/<run_id>/...).
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


_RE_TF_APPLY_COMPLETE = re.compile(r"^Apply complete! Resources: .*\.$")
_RE_TF_NO_CHANGES = re.compile(r"^No changes\. Your infrastructure matches the configuration\.$")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _find_last_matching_line(lines: List[str], pattern: re.Pattern[str]) -> Optional[str]:
    for line in reversed(lines):
        if pattern.match(line.strip()):
            return line.strip()
    return None


def _extract_tf_apply_summary(evidence_dir: Path) -> Optional[str]:
    p = evidence_dir / "reports" / "apply" / "terraform-apply.txt"
    if not p.is_file():
        return None

    lines = _read_text(p).splitlines()

    hit = _find_last_matching_line(lines, _RE_TF_APPLY_COMPLETE)
    if hit:
        return hit

    hit = _find_last_matching_line(lines, _RE_TF_NO_CHANGES)
    if hit:
        return hit

    # Fallback: sometimes terraform prints the plan/apply summary without the exact line.
    for line in reversed(lines):
        s = line.strip()
        if "Apply complete!" in s or s.startswith("Error:"):
            return s

    return None


def _parse_kv_file(path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not path.is_file():
        return out
    for raw in _read_text(path).splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k:
            out[k] = v
    return out


def _extract_play_recap_lines(text: str, limit: int = 10) -> List[str]:
    lines = text.splitlines()
    idx = -1
    for i, line in enumerate(lines):
        if line.strip() == "PLAY RECAP":
            idx = i

    if idx == -1:
        return []

    recap: List[str] = []
    for line in lines[idx + 1 :]:
        s = line.rstrip()
        if not s.strip():
            if recap:
                break
            continue
        # Typical recap lines include ok= changed= failed= ...
        if "ok=" not in s:
            if recap:
                break
            continue
        recap.append(s)
        if len(recap) >= limit:
            break

    return recap


def _extract_ansible_recaps(evidence_dir: Path, service: str) -> Tuple[List[str], List[str]]:
    bootstrap = evidence_dir / "reports" / "apply" / "ansible-bootstrap.txt"
    svc = evidence_dir / "reports" / "apply" / f"ansible-{service}.txt"

    bootstrap_recap: List[str] = []
    service_recap: List[str] = []

    if bootstrap.is_file():
        bootstrap_recap = _extract_play_recap_lines(_read_text(bootstrap))

    if svc.is_file():
        service_recap = _extract_play_recap_lines(_read_text(svc))

    return bootstrap_recap, service_recap


def _blast_counts(evidence_dir: Path) -> Optional[Dict[str, Any]]:
    blast = evidence_dir / "blast-radius.json"
    if not blast.is_file():
        return None

    obj = _load_json(blast)
    counts = obj.get("counts")
    if isinstance(counts, dict):
        return {
            "create": int(counts.get("create", 0)),
            "update": int(counts.get("update", 0)),
            "replace": int(counts.get("replace", 0)),
            "destroy": int(counts.get("destroy", 0)),
            "destructive": bool(obj.get("destructive", False)),
        }

    # Legacy shape
    return {
        "create": int(obj.get("create", 0) or 0),
        "update": int(obj.get("update", 0) or 0),
        "replace": int(obj.get("replace", 0) or 0),
        "destroy": int(obj.get("destroy", 0) or 0),
        "destructive": bool(obj.get("destructive", False)),
    }


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Render Markdown summary of effective Terraform/Ansible changes from evidence packs")
    p.add_argument("--service", required=True)
    p.add_argument("--lab-evidence", default="", help="Path to LAB apply evidence dir (evidence/lab/<run_id>)")
    p.add_argument("--prod-plan-evidence", default="", help="Path to PROD plan evidence dir (evidence/prod/<run_id>)")
    return p.parse_args()


def main() -> int:
    args = _parse_args()

    service = args.service
    lab_dir = Path(args.lab_evidence) if args.lab_evidence else None
    prod_dir = Path(args.prod_plan_evidence) if args.prod_plan_evidence else None

    print("\n### Effective changes (from evidence packs)")

    # LAB apply (actual changes)
    print("\n#### LAB apply (Terraform + Ansible)")
    if not lab_dir or not lab_dir.is_dir():
        print("- Evidence: (missing)")
    else:
        apply_summary = _parse_kv_file(lab_dir / "reports" / "apply" / "summary.txt")
        if apply_summary:
            status = apply_summary.get("status", "")
            reason = apply_summary.get("reason", "")
            hint = apply_summary.get("hint", "")
            if status or reason:
                msg = "- Apply status:"
                if status:
                    msg += f" status={status}"
                if reason:
                    msg += f" reason={reason}"
                print(msg)
            if hint:
                print(f"- Hint: `{hint}`")

        tf_apply = _extract_tf_apply_summary(lab_dir)
        if tf_apply:
            print(f"- Terraform apply: `{tf_apply}`")
        else:
            print("- Terraform apply: (summary not found)")

        b_recap, s_recap = _extract_ansible_recaps(lab_dir, service)

        if b_recap:
            print("- Ansible bootstrap recap:")
            print("```")
            for line in b_recap:
                print(line)
            print("```")
        else:
            print("- Ansible bootstrap recap: (not found)")

        if s_recap:
            print(f"- Ansible {service} recap:")
            print("```")
            for line in s_recap:
                print(line)
            print("```")
        else:
            print(f"- Ansible {service} recap: (not found)")

    # PROD plan (planned changes)
    print("\n#### PROD plan (Terraform)")
    if not prod_dir or not prod_dir.is_dir():
        print("- Evidence: (missing)")
    else:
        counts = _blast_counts(prod_dir)
        if counts:
            print(
                "- Planned changes: "
                f"create={counts['create']} update={counts['update']} replace={counts['replace']} destroy={counts['destroy']} "
                f"(destructive={str(bool(counts['destructive'])).lower()})"
            )
        else:
            print("- Planned changes: (blast-radius.json missing)")

    print("\nNotes:")
    print("- PROD apply is not executed during promotion; only the Terraform plan is produced.")
    print("- This summary intentionally avoids printing full logs to reduce the risk of leaking sensitive output.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
