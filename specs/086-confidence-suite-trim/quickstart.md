# Quickstart: validating 086

## 1. Local checks (dev box)

```bash
bash scripts/ci/python-tests.sh                 # includes test_confidence_gate_paths.py
.venv/bin/pre-commit run --all-files
bash -n scripts/lab/pve-lab
```

## 2. Replay the gate over history

Run this from the repo root on the feature branch:

```bash
pat=$(mktemp); grep -vE '^[[:space:]]*(#|$)' scripts/ci/confidence-suite-paths.txt >"$pat"
git diff --name-only ecf4ebf1 c80273d5 | grep -Ef "$pat"     # expect: no output (prod-inventory-only promote)
git show --name-only --format= fab0723 | grep -Ef "$pat"     # expect: ansible/group_vars/all/vars.yml
```

## 3. Lab run (forced)

Trigger `Prod 1 - LXC Promote` with:
- `ref=086-confidence-suite-trim`
- `service=ntfy` (any service will do)
- `run_confidence_suite=true`

Expected results:
- The gate summary reads `run=true (forced by run_confidence_suite)`.
- The `Confidence suite (best-effort)` job takes **≤ 10 min**. Its log shows the safety step and then only `Profile Selected: hypervisor-nested-workload`.
- The evidence pack verifies, and the summary shows `suite_ok=true`.
- **Don't approve** the PROD apply environment.

## 4. Skip path

After the PR is merged, promote `main` for any service with no lab-path changes since the last verified commit. Expected results:
- `Confidence gate: run=false (no confidence-suite paths changed)`
- The suite job is skipped.
- The metadata shows `lab_gate_failed=false`.
