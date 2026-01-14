from __future__ import annotations

from dataclasses import dataclass
from subprocess import CompletedProcess, run
from typing import Optional

from .bounds import redact_secrets, truncate_text


@dataclass(frozen=True)
class ExecResult:
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str


def run_checked(
    argv: list[str],
    *,
    cwd: Optional[str] = None,
    env: Optional[dict[str, str]] = None,
    max_stdout_bytes: int = 32_000,
    max_stderr_bytes: int = 32_000,
    max_stdout_lines: int = 200,
    max_stderr_lines: int = 200,
) -> ExecResult:
    """Run a subprocess and capture bounded stdout/stderr.

    Bounding + redaction are best-effort guardrails to avoid huge outputs and
    accidental secret leakage in summaries.
    """

    cp: CompletedProcess[str] = run(
        argv,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    stdout = redact_secrets(cp.stdout or "")
    stderr = redact_secrets(cp.stderr or "")

    stdout, _ = truncate_text(stdout, max_bytes=max_stdout_bytes, max_lines=max_stdout_lines)
    stderr, _ = truncate_text(stderr, max_bytes=max_stderr_bytes, max_lines=max_stderr_lines)

    return ExecResult(argv=list(argv), returncode=int(cp.returncode), stdout=stdout, stderr=stderr)
