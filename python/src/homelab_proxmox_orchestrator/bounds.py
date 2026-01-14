from __future__ import annotations

import re


_DEFAULT_MAX_BYTES = 32_000
_DEFAULT_MAX_LINES = 200


def truncate_text(text: str, *, max_bytes: int = _DEFAULT_MAX_BYTES, max_lines: int = _DEFAULT_MAX_LINES) -> tuple[str, bool]:
    """Return (possibly truncated text, truncated?).

    Bounding is done by lines first, then bytes (UTF-8). This keeps results stable
    and prevents huge outputs from flowing into summaries/logs.
    """

    if not text:
        return "", False

    lines = text.splitlines(keepends=True)
    truncated = False

    if max_lines >= 0 and len(lines) > max_lines:
        lines = lines[:max_lines]
    joined = "".join(lines)

    raw = joined.encode("utf-8", errors="replace")
    if max_bytes >= 0 and len(raw) > max_bytes:
        raw = raw[:max_bytes]
        joined = raw.decode("utf-8", errors="replace")
        truncated = True

    if joined != text:
        truncated = True

    return joined, truncated


_REDACTION_RULES: list[tuple[re.Pattern[str], str]] = [
    # KEY=VALUE / key: value patterns (very common in logs)
    (re.compile(r"(?im)^(\s*[^\n#]*?(password|passwd|token|secret|api[_-]?key)\s*[:=]\s*)([^\n]+)$"), r"\1[REDACTED]"),
    # SSH private key blocks
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL), "[REDACTED_PRIVATE_KEY]"),
]


def redact_secrets(text: str) -> str:
    """Best-effort redaction for obviously sensitive material.

    This is intentionally conservative and pattern-based; it is not a guarantee.
    The goal is to avoid accidental secret echoing in summaries.
    """

    if not text:
        return ""

    out = text
    for pattern, repl in _REDACTION_RULES:
        out = pattern.sub(repl, out)

    return out
