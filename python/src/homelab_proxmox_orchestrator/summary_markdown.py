from __future__ import annotations

from typing import Any

from .bounds import truncate_text


def render_markdown_from_plan_ui_summary(obj: dict[str, Any]) -> str:
    run_id = obj.get("run_id")
    env = obj.get("environment")
    service = obj.get("service")
    destructive = obj.get("destructive")
    counts = obj.get("counts") or {}
    resources = obj.get("resources") or []
    truncated = obj.get("truncated")
    resources_total = obj.get("resources_total")
    resources_shown = obj.get("resources_shown")
    required_token = obj.get("confirmation_token_required")
    evidence = obj.get("evidence") or {}

    lines: list[str] = []
    lines.append("## Plan Summary")
    lines.append(f"- Run: `{run_id}`")
    lines.append(f"- Environment: `{env}`")
    lines.append(f"- Service: `{service}`")
    lines.append("")

    lines.append("### Counts")
    lines.append(f"- create: **{counts.get('create', 0)}**")
    lines.append(f"- update: **{counts.get('update', 0)}**")
    lines.append(f"- replace: **{counts.get('replace', 0)}**")
    lines.append(f"- destroy: **{counts.get('destroy', 0)}**")
    lines.append("")

    lines.append("### Safety")
    lines.append(f"- destructive: **{str(bool(destructive)).lower()}**")
    if required_token:
        lines.append(f"- confirmation token required: `{required_token}`")
    else:
        lines.append("- confirmation token required: (none)")
    lines.append("")

    lines.append("### Resources (bounded)")
    if not resources:
        lines.append("- (no changes)")
    else:
        for r in resources:
            if not isinstance(r, dict):
                continue
            addr = r.get("address")
            cls = r.get("class")
            actions = r.get("actions")
            lines.append(f"- `{addr}` ({cls}: {actions})")

    if truncated:
        try:
            remaining = max(0, int(resources_total or 0) - int(resources_shown or 0))
        except Exception:
            remaining = 0
        lines.append(f"- …and **{remaining}** more")
    lines.append("")

    lines.append("### Evidence")
    lines.append(f"- PVE runs dir: `{evidence.get('pve_runs_dir')}`")
    lines.append(f"- PVE run dir: `{evidence.get('pve_run_id_dir')}`")
    lines.append("")

    lines.append("### Next steps")
    if required_token:
        lines.append(
            f"- If apply is blocked due to destructive changes, re-run with the required token: `{required_token}`"
        )
    else:
        lines.append("- If a later stage fails, open the evidence pack referenced above for details")

    lines.append(
        "- If you see missing tfvars / secrets errors, verify the tfvars material exists on PVE under `/var/lib/homelab-proxmox/tfvars` (do not print secrets in logs)"
    )
    lines.append(
        "- If PROD apply reports missing planfile, re-run the promotion so the PROD plan stage can regenerate the saved plan"
    )

    return "\n".join(lines) + "\n"


def render_markdown_from_rebuild_summary(obj: dict[str, Any]) -> str:
    run_id = obj.get("run_id")
    profile_id = obj.get("profile_id")
    suite_profile = obj.get("suite_profile")
    status = obj.get("status")
    duration = obj.get("duration_seconds")
    verification = obj.get("verification") or {}

    lines: list[str] = []
    lines.append("## Evidence Summary")
    lines.append(f"- Run: `{run_id}`")
    lines.append(f"- Profile: `{profile_id}`")
    lines.append(f"- Suite: `{suite_profile}`")
    lines.append(f"- Status: `{status}`")
    lines.append(f"- Duration (s): `{duration}`")
    lines.append("")

    lines.append("### Verification")
    lines.append(f"- status: `{verification.get('status')}`")
    rp = verification.get("report_path")
    if rp:
        lines.append(f"- report: `{rp}`")
    else:
        lines.append("- report: (none)")

    return "\n".join(lines) + "\n"


def render_markdown(*, kind: str, obj: dict[str, Any], max_bytes: int = 32_000, max_lines: int = 200) -> str:
    if kind == "plan-ui":
        md = render_markdown_from_plan_ui_summary(obj)
    elif kind == "rebuild-summary":
        md = render_markdown_from_rebuild_summary(obj)
    else:
        raise ValueError(f"Unsupported summary kind: {kind}")

    md, _ = truncate_text(md, max_bytes=max_bytes, max_lines=max_lines)
    return md
