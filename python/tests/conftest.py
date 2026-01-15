from __future__ import annotations

from pathlib import Path
import sys

# Make python/tests importable for local test helpers (e.g., task_smoke helpers).
_tests_dir = Path(__file__).resolve().parent
if str(_tests_dir) not in sys.path:
    sys.path.insert(0, str(_tests_dir))

# Make python/src importable regardless of where pytest resolves rootdir.
_repo_root = _tests_dir.parent.parent
_python_src = _repo_root / "python" / "src"
if _python_src.exists() and str(_python_src) not in sys.path:
    sys.path.insert(0, str(_python_src))
