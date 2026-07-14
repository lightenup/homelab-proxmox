# Feature Specification: Path-gate the Promote confidence suite

**Feature Branch**: `063-ci-confidence-path-gate`
**Created**: 2026-07-14
**Status**: Delivered — implemented via [specs/063-ci-confidence-path-gate/](../../specs/063-ci-confidence-path-gate/)
**Input**: The `Prod 1 - LXC Promote` pipeline spends ~20 of its ~22 minutes on the best-effort
"Confidence suite", which validates the lab hypervisor/provisioning stack and is **identical for
every service and every change** (a function of the git SHA, not the diff). Make it run only when a
change can actually affect what it tests, so promotes of role/template/host_vars/docs changes drop
from ~22 min to ~2 min — without weakening the gate for provisioning changes.

## Summary

The Promote workflow (`.github/workflows/lxc-promote-prod.yml`) runs, in order: Setup (~10s),
Plan (PROD) (~30s), **Apply (LAB)** (~1 min, service-specific), **Confidence suite** (~20 min,
generic), Summary. The confidence suite runs `scripts/lab/pve-lab confidence` → a safety suite plus
three fixed lab profiles (`bootstrap` → `lab_bootstrap.yml`, `hypervisor-control-plane` /
`hypervisor-nested-workload` → `lab_tier2_pve.yml`) that provision and verify the nested-hypervisor
stack on `lab-pve-01`. That work is unrelated to *which* service is promoted and to changes that
only touch Ansible service roles, Jinja templates, `host_vars`, monitoring config, or docs.

The suite is a **real gate**: its outcome flows into the promotion metadata's `lab_gate_failed`, and
`Prod 2 - LXC Apply` refuses to run unless it passed (or `allow_override_failed_lab_gate=true`). So it
must keep running — and keep gating — for changes that can affect provisioning. The goal is *targeting*,
not removal: skip the suite when the promoted diff cannot affect the provisioning stack, and treat a
**skipped** suite as a pass (not a failure) so no override is needed.

This mirrors an existing pattern in the repo: `.github/workflows/mutation.yml` uses a cheap `gate`
job (diff base→head, look for `python/**`) → heavy self-hosted job (conditional) → always-running
`result` job that reports the required status. Reuse that shape here.

**Non-goal / explicitly out of scope**: adding runners or parallelising the suite. The lab is a
single `lab-pve-01` host guarded by `flock` (`LOCK_WAIT_SECONDS=300`), so confidence suites cannot
run concurrently on the hardware regardless of runner count. (Per-SHA reuse across concurrent
multi-service promotes is a worthwhile follow-up but is tracked separately from this item.)

## User Scenarios & Testing

### User Story 1 - A role/template-only promote is fast (P1)

Promoting a service after a change that only touches `ansible/roles/**`, `ansible/host_vars/**`,
`ansible/templates/**`, monitoring config, or `docs/**` completes without the 20-minute suite.

**Acceptance**:
1. **Given** a commit whose diff vs the compared base touches none of the provisioning-relevant
   paths, **When** `Prod 1 - LXC Promote` runs, **Then** the confidence-suite job is **skipped**
   and the run completes in ≈2 min.
2. **Given** that skipped suite, **When** `Prod 2 - LXC Apply` is triggered for that promotion,
   **Then** it proceeds **without** requiring `allow_override_failed_lab_gate` (skipped ≠ failed).

### User Story 2 - A provisioning change still runs the full gate (P1)

**Acceptance**:
1. **Given** a commit that touches `terraform/**`, `scripts/lab/**`, `ansible/playbooks/lab_*.yml`,
   `scripts/lab/profiles.d/**`, or the `lxc_service` / `lxc_base` roles, **When** Promote runs,
   **Then** the confidence suite runs exactly as today and gates the prod apply.
2. **Given** the suite **fails** on such a change, **When** `Prod 2 - LXC Apply` is triggered,
   **Then** it is blocked unless `allow_override_failed_lab_gate=true` (unchanged behaviour).

### User Story 3 - The manual override input still works (P2)

**Acceptance**:
1. **Given** `run_confidence_suite=false` at trigger time, **When** Promote runs, **Then** the suite
   is skipped (as today) and this is reported as skipped, not failed.
2. **Given** `run_confidence_suite=true` (default), **When** the path gate would otherwise skip,
   **Then** the operator's explicit request still forces the suite to run.

### Edge Cases

- **Promote is `workflow_dispatch`, not `pull_request`** — there is no `pull_request.base/head`. The
  gate must derive the diff as `git diff --name-only $(git merge-base main <checked_sha>) <checked_sha>`
  (or an equivalent base), and **fail safe → run the suite** if the base/diff can't be determined.
- **Force-promote of a non-main ref / detached SHA** — must still resolve a sane base; when in doubt,
  run the suite.
- **Path list drift** — if a new provisioning-relevant directory is added later and not in the gate
  list, the suite would wrongly skip. Keep the list conservative (prefer false-run over false-skip)
  and colocate it with a comment pointing at this spec.
- **`skipped` vs `failed` in the gate math** — audit every place that reads `confidence_suite.outputs.ok`
  / `lab_gate_failed` (`summarize_before_approval` in promote; the gate step in apply) so a *skipped*
  suite yields `ok=true`/`lab_gate_failed=false`, not a blocking failure.

## Requirements

- **FR-001** Add a cheap `confidence_gate` job (ubuntu-latest) to `lxc-promote-prod.yml` that outputs
  `run` = true/false by diffing the promoted SHA against its merge-base with `main`.
- **FR-002** `run` MUST be true when the diff touches any provisioning-relevant path. Initial list:
  `terraform/**`, `scripts/lab/**`, `ansible/playbooks/lab_*.yml`, `ansible/inventories/**`,
  `scripts/lab/profiles.d/**`, `ansible/roles/lxc_base/**`, and the `lxc_service` Terraform module.
- **FR-003** `run` MUST be true whenever `run_confidence_suite=true` is explicitly passed (operator
  override wins), and false only when both the path gate says skip **and** the input isn't forcing it.
- **FR-004** The `confidence_suite` job MUST gain `needs: [confidence_gate]` and an `if:` that runs it
  only when `run == true`; otherwise it is skipped.
- **FR-005** A **skipped** suite MUST be treated as a pass by downstream gate logic: promote metadata
  records `lab_gate_failed=false`, and `Prod 2 - LXC Apply` proceeds without override.
- **FR-006** A **failed** suite MUST behave exactly as today (blocks prod apply unless overridden).
- **FR-007** The gate MUST fail safe: any inability to compute the diff/base ⇒ run the suite.
- **FR-008** No change to what the suite itself does, to the destructive-plan gate, or to the LAB
  apply job (which stays unconditional and service-specific).

## Success Criteria

- **SC-001** A promote of a role/template/host_vars/docs-only change completes in **< 4 min**
  (was ~22 min) and its prod apply needs no override.
- **SC-002** A promote of a `terraform/**` or `scripts/lab/**` change still runs the full ~20-min
  suite and gates prod apply.
- **SC-003** All three of today's fail2ban/monitoring-style promotes would be fast under the new gate
  (verified by replaying their diffs against the path list).
- **SC-004** Zero regressions in the destructive-plan gate and the failed-suite override path.

## Research & decisions

**Where the time goes** (measured, recent runs): Promote ≈ 22 min; Confidence suite ≈ 20 min (91%);
everything else (Setup + Plan + Apply-LAB + Summary) ≈ 2 min. Prod Apply ≈ 1.5 min. CI `Validate`
≈ 10s. `mutation` is already path-gated to `python/**`.

**Why the suite is generic**: `cmd_confidence_suite` in `scripts/lab/pve-lab` runs a fixed safety
suite + `--profile bootstrap|hypervisor-control-plane|hypervisor-nested-workload`; these exercise the
lab hypervisor/nested-VM provisioning, independent of the promoted service. Confirmed by reading the
job and the `pve-lab confidence` code path.

**Why it's still valuable**: it's not best-effort-only — `summarize_before_approval` records its
outcome into `prod-promotion-metadata` (`lab_gate_failed`), and `lxc-apply-prod.yml` blocks on that
unless `allow_override_failed_lab_gate`. So provisioning changes genuinely get an end-to-end lab
gate before prod. The problem is only that it runs unconditionally.

**Pattern to reuse**: `.github/workflows/mutation.yml` — `gate` (diff for `python/**`) → conditional
heavy job → `result` job with `if: always()` that maps skip→pass, fail→fail. The comment there warns
against a top-level `paths:` filter (would leave a required check permanently *pending*); the
gate→result split is what makes "skip cleanly" work. Apply the same to the confidence suite.

**Alternative considered — per-SHA reuse**: cache a passing confidence result keyed by `GIT_SHA` and
reuse it for subsequent promotes of the same commit (turns 3×20 min into 1×20 min on multi-service
days). Higher value on batch days but more moving parts (evidence lookup, staleness). Defer to a
follow-up; path-gating is the low-risk high-leverage first step and already makes most promotes fast.

**Zero-code interim (already available today)**: pass `run_confidence_suite=false` when promoting a
change that can't affect provisioning. This spec makes that decision automatic and safe.

## Verification (acceptance)

1. **Fast path** — promote a branch whose only change is an `ansible/roles/**` file; confirm the
   `confidence_suite` job is skipped, total run ≈ 2 min, and `Prod 2 - LXC Apply` proceeds without
   `allow_override_failed_lab_gate`.
2. **Full path** — promote a branch touching `terraform/**`; confirm the suite runs (~20 min) and
   gates apply as today.
3. **Failed-suite path** — force a suite failure on a provisioning change; confirm prod apply is
   blocked and the override still unblocks it.
4. **Override input** — with a docs-only change, pass `run_confidence_suite=true`; confirm the suite
   runs despite the path gate saying skip.
5. **Fail-safe** — simulate an unresolvable base (e.g. detached SHA with no merge-base); confirm the
   suite runs rather than skips.

## Dependencies

- None on other backlog items. Touches only `.github/workflows/lxc-promote-prod.yml` (and possibly
  `lxc-apply-prod.yml` gate math). No Terraform, Ansible, or service/data changes.
- Related follow-up (separate item): **per-SHA confidence reuse** for batch multi-service promotes.
