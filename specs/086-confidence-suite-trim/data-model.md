# Data Model: Confidence Suite Trim

## Confidence-suite path list (`scripts/ci/confidence-suite-paths.txt`)

- **Format**: UTF-8 text, one POSIX ERE per line. Lines starting with `#` (after optional whitespace) and blank lines are ignored.
- **Semantics**:
  - Each pattern is matched against the repo-relative paths from `git diff --name-only <base> <sha>`.
  - Any match means `run=true`.
  - Patterns should be anchored with `^`.
- **Consumers**:
  - the `confidence_gate` job in `.github/workflows/lxc-promote-prod.yml`
  - `python/tests/workflows/test_confidence_gate_paths.py`
- **Validation**:
  - The cleaned list must be non-empty. The gate treats empty as `run=true`, and the test asserts it's non-empty.
  - Every dependency found by the drift guard must match some pattern (spec FR-003).
  - The list must contain patterns matching the list file itself and the promote workflow.

## Gate decision (unchanged from 063)

The output is `run` = `"true"` | `"false"`, decided by the first rule that applies:

1. Forced: `run_confidence_suite=true` → true.
2. No SHA → true.
3. Base: the last verified commit → diff. Otherwise fall back to the merge-base, with its fail-safes.
4. **Changed in 086**: path list missing or empty → true.
5. **Changed in 086**: `diff | grep -qEf <cleaned list>` → true, otherwise false.
