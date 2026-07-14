# Phase 1 Data Model: Path-gate the Promote confidence suite

This feature has **no persistent data store**. The "entities" are ephemeral GitHub Actions job
outputs and the existing promotion-metadata JSON, whose *shape is unchanged* — only the values
flowing through it change. Documented here for the contract in `contracts/` and for the gate-math
audit.

## Entity: Gate decision (`confidence_gate.outputs.run`)

| Field | Type | Values | Meaning |
|-------|------|--------|---------|
| `run` | string | `"true"` \| `"false"` | Whether the confidence suite must run for this promote. |

**Derivation rules** (FR-001..003, FR-007):
- `run = "true"` if the diff `git diff --name-only <merge-base(main,sha)> <sha>` matches any
  provisioning path (see contract), **OR** `run_confidence_suite == true` was explicitly passed.
- `run = "true"` (fail-safe) if the base or diff cannot be computed (empty SHA, missing
  `origin/main`, `merge-base`/`diff` failure).
- `run = "false"` only when the diff resolved cleanly, matched no provisioning path, **and** the
  operator did not force the suite.

**Lifetime**: single workflow run. Not persisted.

## Entity: Suite job result (`confidence_suite.result`)

GitHub-provided job status consumed by `summarize_before_approval`. Relevant values:

| Value | Meaning here | Maps to |
|-------|--------------|---------|
| `success` | Suite ran and passed | `suite_ok=true`, `suite_sha_ok` from job output |
| `failure` | Suite ran and failed | `suite_ok=false` ⇒ `lab_gate_failed=true` (unchanged) |
| `skipped` | Gate said skip (or operator opted out) | **`suite_ok=true` and `suite_sha_ok=true`** (new) |

**Critical rule (FR-005, Decision 5)**: a `skipped` result maps to pass on **both** the
`lab_gate_failed` axis and the `sha_all_ok` axis, because a skipped job emits *empty* outputs for
`ok` and `sha_ok`, and downstream apply hard-blocks on `sha_all_ok != "true"`.

## Entity: Promotion metadata JSON (`prod-promotion-metadata`)

Shape **unchanged**. Fields whose values are affected by this feature:

| Field | Before | After (skipped suite) |
|-------|--------|-----------------------|
| `suite_run_id` | suite RUN_ID | empty (no suite ran) |
| `suite_ok` | `true`/`false` | `true` (skip treated as pass) |
| `lab_gate_failed` | `true` if lab or suite not ok | `false` when suite skipped and lab ok |
| `sha_all_ok` | requires suite sha_ok | `true` when suite skipped (sha_ok treated true) |

`lxc-apply-prod.yml` reads `lab_gate_failed`, `sha_all_ok`, `service`, `ref`, `checked_sha`,
`prod_plan_destructive`. None of these change type or presence ⇒ **no apply-side edit** required.

## State transitions

```
Promote dispatched
      │
      ▼
confidence_gate ──run=false──▶ confidence_suite: SKIPPED ──▶ compute_gate: suite_ok=true, suite_sha_ok=true
      │                                                              │
   run=true                                                          ▼
      │                                              lab_gate_failed=false, sha_all_ok=(lab&plan) ✅
      ▼
confidence_suite: RUNS
      ├─ success ─▶ compute_gate: suite_ok=true  ─▶ lab_gate_failed=false
      └─ failure ─▶ compute_gate: suite_ok=false ─▶ lab_gate_failed=true ─▶ apply blocked unless override
```

No other state is introduced.
