# Contract: `confidence_gate` job and downstream gate mapping

The "interface" this feature exposes is a GitHub Actions job contract inside
`.github/workflows/lxc-promote-prod.yml`. This document is the authoritative spec for that job's I/O,
the provisioning path list, and how a skipped suite maps through the existing gate math.

## Job: `confidence_gate`

**Runs on**: `ubuntu-latest` (GitHub-hosted). **Permissions**: `contents: read`. No secrets.

**Inputs (from workflow context)**:
- `needs.setup.outputs.checked_sha` — the promoted SHA the whole pipeline pins to.
- `github.event.inputs.run_confidence_suite` — operator force-run flag (boolean input).

**Steps**:
1. `actions/checkout@v4` with `fetch-depth: 0` (merge-base needs full history).
2. Compute decision (Bash). Pseudocode:

   ```bash
   set -euo pipefail
   SHA="${{ needs.setup.outputs.checked_sha }}"
   FORCE="${{ github.event.inputs.run_confidence_suite }}"

   # Operator force-run wins (FR-003).
   if [ "${FORCE}" = "true" ]; then
     echo "run=true" >>"$GITHUB_OUTPUT"; exit 0
   fi

   # Fail-safe: no SHA ⇒ run (FR-007).
   if [ -z "${SHA}" ]; then echo "run=true" >>"$GITHUB_OUTPUT"; exit 0; fi

   base="$(git merge-base origin/main "${SHA}" 2>/dev/null || true)"
   if [ -z "${base}" ]; then echo "run=true" >>"$GITHUB_OUTPUT"; exit 0; fi

   diff="$(git diff --name-only "${base}" "${SHA}" 2>/dev/null || true)"
   if [ -z "${diff}" ]; then echo "run=true" >>"$GITHUB_OUTPUT"; exit 0; fi

   # Provisioning-relevant paths — see specs/063-ci-confidence-path-gate/spec.md
   # Keep conservative: prefer false-run over false-skip.
   if printf '%s\n' "${diff}" | grep -qE \
     '^terraform/|^scripts/lab/|^ansible/playbooks/lab_.*\.ya?ml$|^ansible/inventories/|^ansible/roles/lxc_base/'; then
     echo "run=true" >>"$GITHUB_OUTPUT"
   else
     echo "run=false" >>"$GITHUB_OUTPUT"
   fi
   ```

   > `scripts/lab/profiles.d/` and the `lxc_service` module are already covered by `^scripts/lab/`
   > and `^terraform/` respectively; no separate regex branch needed.

> **Superseded**: this inline "Provisioning-relevant paths" regex is replaced by the
> `scripts/ci/confidence-suite-paths.txt` path list read with `grep -qEf`. See
> `specs/086-confidence-suite-trim/contracts/confidence-suite-paths.md`. All other parts of
> this contract stay in force.

**Outputs**:
- `run` — `"true"` | `"false"` (see data-model derivation rules).

## Job edit: `confidence_suite`

- Add `confidence_gate` to `needs` (currently `needs: [setup, apply_lab]`).
- Replace the `if:` with: `if: ${{ needs.confidence_gate.outputs.run == 'true' }}`.
  (The override is already folded into `confidence_gate.outputs.run`, so the suite reads a single
  source of truth — FR-004.)

## Input edit: `run_confidence_suite`

- **Default** flips `true` → `false`.
- **Description** → `"Force-run the confidence suite even if the path gate would skip it (best-effort)"`.
- Rationale: with the old default `true`, folding the override into the gate would force the suite on
  every promote and nothing would skip. Flipping the default makes path-gating the default while
  preserving an explicit force-on. Accepted minor behaviour change (spec Assumptions).

## Gate-math edit: `summarize_before_approval.compute_gate`

Map a **skipped** suite to pass on both axes (FR-005, Decision 5):

```bash
suite_result="${{ needs.confidence_suite.result }}"   # success | failure | skipped
suite_ok="${{ needs.confidence_suite.outputs.ok }}"
suite_sha_ok="${{ needs.confidence_suite.outputs.sha_ok }}"

if [ "${suite_result}" = "skipped" ]; then
  suite_ok="true"
  suite_sha_ok="true"
fi
# ...existing lab_gate_failed and sha_all_ok computation unchanged, now fed corrected values.
```

**Invariants preserved**:
- `failure` ⇒ `suite_ok=false` ⇒ `lab_gate_failed=true` ⇒ apply blocked unless override (FR-006).
- `success` ⇒ unchanged behaviour.
- `skipped` ⇒ `lab_gate_failed=false` **and** `sha_all_ok` unaffected by the (empty) suite outputs.

## Downstream: `lxc-apply-prod.yml`

**No change.** It consumes `lab_gate_failed` and `sha_all_ok` from the metadata JSON; both now carry
correct values for a skipped suite. Audit confirms the two enforce steps:
- "Enforce SHA alignment requirement": blocks on `sha_all_ok != 'true'` — satisfied (now `true`).
- "Enforce override semantics": blocks on `lab_gate_failed == 'true' && override != 'true'` —
  satisfied (now `false`, no override needed). (FR-005)

## Acceptance mapping

| Spec item | Enforced by |
|-----------|-------------|
| FR-001 | `confidence_gate` job + merge-base diff step |
| FR-002 | path-list `grep -qE` regex |
| FR-003 | force-run clause folded into gate; input default flip |
| FR-004 | `confidence_suite` `needs`+`if` |
| FR-005 | `compute_gate` skip→(ok=true, sha_ok=true); apply unchanged |
| FR-006 | `compute_gate` failure path unchanged |
| FR-007 | fail-safe branches (empty SHA / base / diff ⇒ run=true) |
| FR-008 | no edits to suite body, LAB apply, PROD plan, destructive gate |
