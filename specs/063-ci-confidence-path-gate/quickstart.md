# Quickstart: Validate the path-gated confidence suite

How to verify the feature against the five acceptance scenarios in the spec. Assumes the edits from
`contracts/confidence-gate.md` are applied to `.github/workflows/lxc-promote-prod.yml`.

## 0. Static / local checks (before any promote)

```bash
# Workflow still parses and the dispatch event is recognised.
act -l
act -n -W .github/workflows/lxc-promote-prod.yml workflow_dispatch
```

If `act`/Docker is unavailable, note it in the PR (constitution "Local Workflow Testing").

Replay recent promote diffs against the path list (SC-003) — should print nothing (⇒ would skip):

```bash
# Example: a fail2ban/monitoring-style change base
git diff --name-only "$(git merge-base origin/main <recent-sha>)" <recent-sha> \
  | grep -E '^terraform/|^scripts/lab/|^ansible/playbooks/lab_.*\.ya?ml$|^ansible/inventories/|^ansible/roles/lxc_base/' \
  || echo "no provisioning paths → suite would SKIP"
```

## 1. Fast path (SC-001, User Story 1)

- Promote a branch whose only change is under `ansible/roles/**` (a service role), `host_vars`,
  templates, or `docs/**`.
- **Expect**: `confidence_gate` outputs `run=false`; `confidence_suite` job shows **skipped**; total
  Promote run ≈ 2 min (< 4 min).
- Then run `Prod 2 - LXC Apply` for that promotion **without** `allow_override_failed_lab_gate`.
- **Expect**: apply proceeds — no override needed. Confirms `lab_gate_failed=false` **and**
  `sha_all_ok=true` in the metadata.

## 2. Full path (SC-002, User Story 2)

- Promote a branch touching `terraform/**` (or `scripts/lab/**`).
- **Expect**: `confidence_gate` outputs `run=true`; `confidence_suite` runs (~20 min) and gates as
  today.

## 3. Failed-suite path (SC-004, User Story 2 #2)

- Force a suite failure on a provisioning change.
- **Expect**: `lab_gate_failed=true`; `Prod 2 - LXC Apply` is blocked; re-running apply with
  `allow_override_failed_lab_gate=true` unblocks it (unchanged behaviour).

## 4. Override input (User Story 3)

- With a docs-only change, dispatch Promote with `run_confidence_suite=true`.
- **Expect**: `confidence_gate` outputs `run=true` despite the path gate; suite runs.

## 5. Fail-safe (User Story 2, edge case)

- Simulate an unresolvable base (e.g. a detached SHA with no merge-base to `origin/main`).
- **Expect**: gate falls through to `run=true`; suite runs rather than skips.

## Regression guardrails (SC-004)

- Destructive PROD plan gate: unchanged — a destructive plan still surfaces its warning and apply
  still requires `confirm_apply_prod=deploy-prod`.
- Failed-suite override path: unchanged — see scenario 3.
- `lxc-apply-prod.yml`: confirm no edits were required (diff should show only
  `lxc-promote-prod.yml`).
