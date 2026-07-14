# Phase 0 Research: Path-gate the Promote confidence suite

All Technical Context items resolved below. No open NEEDS CLARIFICATION.

## Decision 1 — Reuse the `mutation.yml` gate → conditional → always-result shape

**Decision**: Add a `confidence_gate` job (GitHub-hosted `ubuntu-latest`) that outputs `run`, make
`confidence_suite` depend on it with an `if:`, and rely on the **existing**
`summarize_before_approval` job (already `needs: [... confidence_suite ...]` with `if: always()`) as
the "result" job that maps skip→pass.

**Rationale**: `.github/workflows/mutation.yml` already proves this exact pattern in-repo:
`gate` (diff `python/**`) → `mutation` (`if: needs.gate.outputs.run == 'true'`) → `result`
(`if: always()`, `case needs.mutation.result`). Its comment explicitly warns that a top-level
`paths:` filter would leave a required check permanently *pending* — the gate→conditional split is
what makes "skip cleanly" work. Promote already has an `if: always()` aggregation job
(`summarize_before_approval`), so we do not need a new result job — we only need to teach its
`compute_gate` step to read `skipped` as pass.

**Alternatives considered**:
- *Top-level `paths:` filter on the workflow* — rejected: promote is `workflow_dispatch` (no PR
  paths context) and a filtered required check hangs pending.
- *Skip logic inside the suite's first step* — rejected: still burns a self-hosted runner slot and
  the `flock` wait, and muddies "skipped vs failed".
- *A brand-new `result` job* — rejected (YAGNI): `summarize_before_approval` already aggregates all
  upstream job outcomes with `if: always()`.

## Decision 2 — Diff base is `git merge-base main <checked_sha>`, computed on a full-history checkout

**Decision**: In the gate job, `actions/checkout@v4` with `fetch-depth: 0`, then
`base="$(git merge-base origin/main "$SHA")"` and `git diff --name-only "$base" "$SHA"`. `SHA` is the
same `checked_sha` the rest of the pipeline pins to (from `setup`'s `capture_sha`, i.e.
`git rev-parse HEAD` of the promoted `ref`).

**Rationale**: Promote is `workflow_dispatch` with an arbitrary `ref` input, so there is no
`pull_request.base/head` (the edge case the spec calls out). Merge-base against `main` yields the set
of paths the promoted commit introduces relative to the mainline, which is exactly "can this change
affect provisioning". `fetch-depth: 0` is required for `merge-base` to have both histories.

**Alternatives considered**:
- *`HEAD~1` / single-parent diff* — rejected: wrong for multi-commit branches and merge commits.
- *Reuse `setup`'s checkout* — rejected: `setup` does not fetch full history; the gate needs its own
  `fetch-depth: 0` checkout (cheap on `ubuntu-latest`).

## Decision 3 — Fail-safe: any inability to resolve base/diff ⇒ `run=true`

**Decision**: The gate step defaults `run=true` and only sets `run=false` when it has both a resolved
merge-base and a clean diff that matches none of the provisioning paths. Empty `SHA`, missing
`origin/main`, a `merge-base` failure, or an empty/failed diff all fall through to `run=true`.

**Rationale**: FR-007 + the spec edge cases (detached SHA, non-main ref, unresolvable base). False
-run costs ~20 min once; false-skip ships an unvalidated provisioning change to prod — asymmetric
risk, so bias to run. Mirrors `mutation.yml`'s "non-PR dispatch: run by default".

## Decision 4 — Operator override precedence (`run_confidence_suite`)

**Decision**: The `confidence_suite` `if:` becomes an OR: run when the operator forces it **or** the
gate says run. Concretely, keep the existing `run_confidence_suite == true/'true'` clause and OR it
with `needs.confidence_gate.outputs.run == 'true'`. When `run_confidence_suite=false` is passed, the
suite is skipped regardless of the gate (operator explicitly opted out).

**Rationale**: FR-003. `run_confidence_suite=true` is the default, so the common path is
"gate decides"; an explicit `false` is the existing manual escape hatch and must still win as a skip.
The gate job itself does not need to read the input — precedence lives entirely in the suite's `if:`
expression, keeping the gate job a pure path computation.

**Truth table** (suite runs?):

| `run_confidence_suite` | gate `run` | Suite runs? |
|------------------------|------------|-------------|
| `true` (default)       | `true`     | ✅ yes       |
| `true` (default)       | `false`    | ✅ yes (override forces) |
| `false`                | `true`     | ❌ no (operator opted out) |
| `false`                | `false`    | ❌ no        |

> Note: with the default `true`, the gate can never *cause* a skip on its own — the override clause
> dominates. The gate's skip only takes effect when the operator leaves `run_confidence_suite` at a
> value that doesn't force the suite. **Action for design**: the intended UX is that the *gate* is
> the primary decision and the input is an override in **both** directions. To achieve "gate skips
> non-provisioning promotes by default", the suite `if:` must treat the input as a tri-state:
> force-on only when explicitly toggled by the operator away from the gate. See Decision 4a.

## Decision 4a — Making the gate the default decision without breaking the override

**Decision**: Change the suite `if:` to: run when
`needs.confidence_gate.outputs.run == 'true' || github.event.inputs.run_confidence_suite == 'true'`
**only if** we also flip the input's default to `false` so "true" is a deliberate force. To avoid
changing the input's default (which would surprise operators who rely on `true`), instead have the
**gate job** fold the override in: gate outputs `run=true` when the diff matches **or**
`run_confidence_suite=true` was explicitly set, and the suite `if:` reads solely
`needs.confidence_gate.outputs.run == 'true'`.

**Chosen approach**: Fold the override into the gate (FR-003 wording: "`run` MUST be true whenever
`run_confidence_suite=true` is explicitly passed"). The gate job reads both the diff **and** the
input; the suite `if:` depends only on `needs.confidence_gate.outputs.run`. This keeps a single
source of truth for the decision and matches FR-003/FR-004 verbatim.

**Consequence for the default**: FR-003 says `run` is false "only when both the path gate says skip
**and** the input isn't forcing it". With the current input default of `true`, the override would
force every run and nothing would ever skip. Therefore the input default MUST change to `false`
("auto — let the path gate decide") OR the semantics must read `true` as "force". **Resolution**:
flip the input default to `false` and update its description to "Force-run the confidence suite even
if the path gate would skip it (best-effort)". This is the minimal change that makes path-gating the
default while preserving an explicit force-on. `run_confidence_suite=false`/unset ⇒ gate decides;
`=true` ⇒ always run. (An explicit force-**off** is no longer needed because the gate already skips
non-provisioning diffs; provisioning diffs that an operator wants to skip can use the existing
override-on-apply path — noted as an accepted minor behaviour change in the spec's Assumptions.)

## Decision 5 — Skipped suite must map to pass in BOTH `lab_gate_failed` and `sha_all_ok`

**Decision**: In `summarize_before_approval.compute_gate`, treat a skipped `confidence_suite` as a
pass on two axes:
1. `suite_ok`: if `needs.confidence_suite.result == 'skipped'`, set `suite_ok=true` (so
   `lab_gate_failed` stays false).
2. `suite_sha_ok`: if skipped, treat as `true` (so `sha_all_ok` stays true).

**Rationale**: This is the spec's "audit every place" edge case, and it is subtler than it looks.
When a job is skipped, **all** its outputs are empty strings, not just its `ok`. Today:
- `lab_gate_failed=true` if `suite_ok != 'true'` → empty ⇒ would wrongly fail the gate.
- `sha_all_ok=true` only if `suite_sha_ok == 'true'` → empty ⇒ `sha_all_ok=false`.

And `lxc-apply-prod.yml` **hard-blocks** on `sha_all_ok != 'true'` (line ~171, "Enforce SHA
alignment requirement") with no override. So a skipped suite would block prod apply *even with*
`allow_override_failed_lab_gate=true`. Both axes must therefore map skip→true. The fix is entirely in
promote's `compute_gate` using `needs.confidence_suite.result`; the metadata JSON keeps the same
fields, so `lxc-apply-prod.yml` needs **no change** (confirmed by reading its `meta`/enforce steps).

**Alternatives considered**:
- *Emit outputs from the skipped job* — impossible; skipped jobs don't run steps.
- *Change apply's SHA-alignment enforcement* — rejected: broader blast radius and FR-008 says leave
  apply's gates alone; fixing it at the source (promote) is cleaner and keeps apply untouched.

## Decision 6 — Provisioning-relevant path list (conservative)

**Decision**: Gate `run=true` when `git diff --name-only <base> <sha>` matches any of:

```
^terraform/
^scripts/lab/
^ansible/playbooks/lab_.*\.ya?ml$
^ansible/inventories/
^scripts/lab/profiles\.d/
^ansible/roles/lxc_base/
```

The `lxc_service` Terraform module lives under `terraform/modules/lxc_service/`, so `^terraform/`
already covers it. Inline this list in the gate step with a comment: `# Provisioning-relevant paths
— see specs/063-ci-confidence-path-gate/spec.md (keep conservative: prefer false-run over
false-skip).`

**Rationale**: FR-002 list, verified against the repo layout. `scripts/lab/profiles.d/` is a subset
of `scripts/lab/` (already covered) but is listed explicitly for readability/intent and future-proof
if `scripts/lab/` is ever narrowed. Keeping the whole of `terraform/` in scope is deliberately broad
(YAGNI-compatible: one regex, no per-module enumeration) and satisfies "prefer false-run".

**Validation for SC-003**: replay recent fail2ban/monitoring promote diffs against this list — they
touch `ansible/roles/**` (service roles, not `lxc_base`), `ansible/host_vars/**`, templates, and
`docs/**`, none of which match ⇒ they skip. Confirm during implementation/quickstart.

## Decision 7 — Local validation approach

**Decision**: Validate the workflow parses and the dispatch event is recognised with `act -l` and
`act -n -W .github/workflows/lxc-promote-prod.yml workflow_dispatch`. If Docker/`act` is unavailable,
document that in the PR per the constitution and rely on the five acceptance-scenario promotes.

**Rationale**: Constitution "Local Workflow Testing" mandates `act` validation when feasible for
workflow edits. Full behavioural acceptance needs real self-hosted promotes (the suite + `flock` +
evidence packs can't run under `act`), so `act` is a syntax/parse gate, not a functional one.
