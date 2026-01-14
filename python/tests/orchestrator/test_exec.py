from pathlib import Path

from homelab_proxmox_orchestrator.exec import run_checked


def test_exec_captures_output():
    res = run_checked(["python3", "-c", "print('hi')"])
    assert res.returncode == 0
    assert "hi" in res.stdout


def test_exec_can_be_bounded():
    fixture = Path("python/tests/orchestrator/fixtures/emit_many_lines.py")
    res = run_checked(["python3", str(fixture)], max_stdout_bytes=200, max_stderr_bytes=200)
    assert res.returncode == 0
    assert len(res.stdout.encode("utf-8")) <= 200
    assert len(res.stderr.encode("utf-8")) <= 200
