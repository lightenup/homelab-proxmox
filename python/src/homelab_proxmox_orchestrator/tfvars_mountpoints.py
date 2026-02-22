from __future__ import annotations

import re


def _strip_comments(line: str) -> str:
    if "#" in line:
        return line.split("#", 1)[0]
    return line


def parse_service_host_path_mounts(tfvars_text: str, service: str) -> list[dict]:
    """Parse service_mountpoints from tfvars text, return host-path mounts for service.

    Scans the service_mountpoints HCL map for the named service and returns all
    mount entries whose volume starts with "/" (host-path bind mounts).

    Returns a list of {"mp": str, "volume": str, "readonly": bool}.
    readonly defaults to False when the readonly key is absent from the entry.
    Returns [] if the service has no host-path mounts or is not present.

    Adapted from _extract_service_mountpoints() in scripts/lifecycle/remove_checks.py,
    extended to capture mp and readonly fields.
    """
    mounts: list[dict] = []
    in_map = False
    in_service = False
    depth = 0
    service_depth = 0
    current_mount: dict | None = None
    current_mount_depth = 0

    for raw_line in tfvars_text.splitlines():
        line = _strip_comments(raw_line).rstrip()
        if not line.strip():
            continue

        if not in_map:
            if re.match(r"^\s*service_mountpoints\s*=\s*{\s*$", line):
                in_map = True
                depth = 1
            continue

        depth += line.count("{")
        depth -= line.count("}")

        if depth <= 0:
            in_map = False
            in_service = False
            current_mount = None
            continue

        if not in_service:
            if re.match(rf"^\s*{re.escape(service)}\s*=\s*{{\s*$", line):
                in_service = True
                service_depth = depth
            continue

        if current_mount is None and depth < service_depth:
            in_service = False
            continue

        if current_mount is None:
            if re.match(r"^\s*[A-Za-z0-9_-]+\s*=\s*{\s*$", line):
                current_mount = {}
                current_mount_depth = depth
            continue

        # Inside a mount entry
        if depth < current_mount_depth:
            if "mp" in current_mount and "volume" in current_mount:
                if current_mount["volume"].startswith("/"):
                    if "readonly" not in current_mount:
                        current_mount["readonly"] = False
                    mounts.append(current_mount)
            current_mount = None
            if depth < service_depth:
                in_service = False
            continue

        mp_match = re.match(r'^\s*mp\s*=\s*"([^"]+)"\s*$', line)
        if mp_match:
            current_mount["mp"] = mp_match.group(1)
            continue

        vol_match = re.match(r'^\s*volume\s*=\s*"([^"]+)"\s*$', line)
        if vol_match:
            current_mount["volume"] = vol_match.group(1)
            continue

        ro_match = re.match(r"^\s*readonly\s*=\s*(true|false)\s*$", line)
        if ro_match:
            current_mount["readonly"] = ro_match.group(1) == "true"
            continue

    # Handle EOF while inside a mount entry
    if current_mount is not None and "mp" in current_mount and "volume" in current_mount:
        if current_mount["volume"].startswith("/"):
            if "readonly" not in current_mount:
                current_mount["readonly"] = False
            mounts.append(current_mount)

    return mounts


def validate_bind_mount_allowlist(
    mounts: list[dict],
    allowed_prefixes: tuple[str, ...] = ("/mnt/nas/",),
) -> tuple[list[dict], list[dict]]:
    """Validate mount volumes against an allowlist of permitted host-path prefixes.

    Uses directory-boundary prefix matching: a trailing "/" on each prefix ensures
    /mnt/nasty-trick is NOT treated as a child of /mnt/nas/.

    Returns (allowed, rejected) tuple of mount lists.
    """
    allowed: list[dict] = []
    rejected: list[dict] = []

    for mount in mounts:
        volume = mount.get("volume", "")
        is_allowed = any(volume.startswith(prefix) for prefix in allowed_prefixes)
        if is_allowed:
            allowed.append(mount)
        else:
            rejected.append(mount)

    return allowed, rejected


def format_pct_set_arg(mount: dict) -> str:
    """Format a mount dict as a pct set bind-mount argument string.

    Returns the argument string passed to `pct set -mp<N>`, e.g.:
      "/mnt/nas/video,mp=/media/video,ro=1"   (readonly=True)
      "/mnt/nas/homelab_immich,mp=/mnt/immich" (readonly=False)
    """
    volume = mount["volume"]
    mp = mount["mp"]
    readonly = mount.get("readonly", False)

    arg = f"{volume},mp={mp}"
    if readonly:
        arg += ",ro=1"
    return arg


def format_step_summary(mount_results: list[dict]) -> str:
    """Render a markdown step summary table for bind mount operations.

    Each element of mount_results must contain:
      - volume: str   (host path)
      - mp: str       (container path)
      - readonly: bool
      - result: "applied" | "skipped" | "failed"

    Returns a markdown string containing:
      - A table with columns: Host Path | Container Path | Permission | Result
      - An optional reboot state line (when any mounts were applied)
      - An overall summary line

    Suitable for appending to $GITHUB_STEP_SUMMARY or printing to terminal.
    """
    lines: list[str] = []
    lines.append("| Host Path | Container Path | Permission | Result |")
    lines.append("|-----------|----------------|------------|--------|")

    applied_count = 0
    skipped_count = 0
    failed_count = 0

    for result in mount_results:
        host_path = result["volume"]
        container_path = result["mp"]
        permission = "ro" if result.get("readonly", False) else "rw"
        result_str = result["result"]

        lines.append(f"| {host_path} | {container_path} | {permission} | {result_str} |")

        if result_str == "applied":
            applied_count += 1
        elif result_str == "skipped":
            skipped_count += 1
        elif result_str == "failed":
            failed_count += 1

    lines.append("")

    if applied_count > 0:
        lines.append("**Container reboot**: stopped → mounts applied → started")

    overall = "success" if failed_count == 0 else "failure"
    lines.append(
        f"**Overall**: {overall} ({applied_count} applied, {skipped_count} skipped, {failed_count} failed)"
    )

    return "\n".join(lines) + "\n"
