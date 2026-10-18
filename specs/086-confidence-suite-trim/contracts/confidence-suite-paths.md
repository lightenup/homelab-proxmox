# Contract: confidence gate path matching (086)

This supersedes the "Provisioning-relevant paths" regex in
`specs/063-ci-confidence-path-gate/contracts/confidence-gate.md`. All other parts of that contract stay in force.

## `confidence_gate` → `decide` step, path-match section

```bash
# Paths the confidence suite reads — specs/086-confidence-suite-trim (prefer false-run over false-skip).
patterns="$(mktemp)"
grep -vE '^[[:space:]]*(#|$)' scripts/ci/confidence-suite-paths.txt >"${patterns}" 2>/dev/null || true
if [[ ! -s "${patterns}" ]]; then
  decide true "confidence-suite path list missing or empty"
fi
if printf '%s\n' "${diff}" | grep -qEf "${patterns}"; then
  decide true "confidence-suite paths changed"
else
  decide false "no confidence-suite paths changed"
fi
```

## `cmd_confidence_suite` (scripts/lab/pve-lab)

The steps run in this order, and any failure exits 1:
1. evidence pack setup
2. `cmd_safety_suite`
3. `cmd_run --profile hypervisor-nested-workload`

The evidence pack layout, the `RUN_ID=` emission and exit codes are unchanged.
