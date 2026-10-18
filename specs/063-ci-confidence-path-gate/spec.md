# Feature Specification: Path-gate the Promote confidence suite

**Feature Branch**: `063-ci-confidence-path-gate`
**Created**: 2026-07-14
**Status**: Draft
**Input**: read docs/backlog/063-ci-confidence-suite-path-gate.md

## Summary

The `Prod 1 - LXC Promote` pipeline spends ~20 of its ~22 minutes on a best-effort "Confidence
suite" that validates the lab hypervisor/provisioning stack. That suite is **identical for every
service and every change** — it is a function of the git SHA, not the promoted diff. This feature
makes the suite run only when a change can actually affect what it tests, so promotes of
role/template/host_vars/docs changes drop from ~22 min to ~2 min — **without weakening the gate for
provisioning changes**. A **skipped** suite is treated as a **pass**, so downstream prod-apply needs
no operator override. The goal is *targeting*, not removal.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A role/template-only promote is fast (Priority: P1)

An operator promotes a service after a change that only touches Ansible service roles, `host_vars`,
Jinja templates, monitoring config, or docs. The promote completes without the 20-minute confidence
suite, and the subsequent prod apply proceeds normally.

**Why this priority**: This is the dominant case (most promotes touch only service-level config or
docs) and delivers the ~10× speedup that motivates the feature.

**Independent Test**: Promote a branch whose only change is an `ansible/roles/**` file; confirm the
suite is skipped, the run finishes in ≈2 min, and the prod apply proceeds without override.

**Acceptance Scenarios**:

1. **Given** a commit whose diff vs the compared base touches none of the provisioning-relevant
   paths, **When** `Prod 1 - LXC Promote` runs, **Then** the confidence-suite job is **skipped** and
   the run completes in ≈2 min.
2. **Given** that skipped suite, **When** `Prod 2 - LXC Apply` is triggered for that promotion,
   **Then** it proceeds **without** requiring `allow_override_failed_lab_gate` (skipped ≠ failed).

---

### User Story 2 - A provisioning change still runs the full gate (Priority: P1)

An operator promotes a change that touches the provisioning stack (Terraform, lab scripts/profiles,
lab playbooks, base role). The confidence suite runs exactly as today and gates the prod apply.

**Why this priority**: Preserving the safety gate for provisioning changes is the non-negotiable
constraint; the feature must not weaken it.

**Independent Test**: Promote a branch touching `terraform/**`; confirm the suite runs (~20 min) and
gates prod apply as today, including the failed-suite override path.

**Acceptance Scenarios**:

1. **Given** a commit that touches `terraform/**`, `scripts/lab/**`, `ansible/playbooks/lab_*.yml`,
   `scripts/lab/profiles.d/**`, or the `lxc_service` / `lxc_base` roles, **When** Promote runs,
   **Then** the confidence suite runs exactly as today and gates the prod apply.
2. **Given** the suite **fails** on such a change, **When** `Prod 2 - LXC Apply` is triggered,
   **Then** it is blocked unless `allow_override_failed_lab_gate=true` (unchanged behaviour).

---

### User Story 3 - The manual force-run input still works (Priority: P2)

The path gate becomes the default decision-maker, and the `run_confidence_suite` input is repurposed
as a **force-on override**: leaving it unset (new default `false`) lets the gate decide, while
setting it `true` forces the suite to run even when the gate would otherwise skip.

**Why this priority**: The operator escape hatch must keep working, but it is secondary to the
automatic path-gating behaviour. Note the deliberate behaviour change: the old "`false` ⇒ always
skip" meaning is dropped (see Assumptions) — skipping is now the gate's job.

**Independent Test**: With a docs-only change, pass `run_confidence_suite=true` and confirm the suite
runs despite the path gate saying skip.

**Acceptance Scenarios**:

1. **Given** `run_confidence_suite` left at its default (`false`) at trigger time, **When** Promote
   runs, **Then** the path gate decides: a non-provisioning diff is skipped (reported as skipped, not
   failed) and a provisioning diff runs the suite.
2. **Given** `run_confidence_suite=true`, **When** the path gate would otherwise skip, **Then** the
   operator's explicit request still forces the suite to run.

---

### Edge Cases

- **Promote is `workflow_dispatch`, not `pull_request`** — there is no `pull_request.base/head`. The
  gate must derive the diff from the promoted SHA against its merge-base with `main` (or an
  equivalent base), and **fail safe → run the suite** if the base/diff can't be determined.
- **Force-promote of a non-main ref / detached SHA** — must still resolve a sane base; when in doubt,
  run the suite.
- **Path-list drift** — if a new provisioning-relevant directory is added later and not in the gate
  list, the suite would wrongly skip. Keep the list conservative (prefer false-run over false-skip)
  and colocate it with a comment pointing at this spec.
- **`skipped` vs `failed` in the gate math** — every place that reads the suite outcome
  (`summarize_before_approval` in promote; the gate step in apply) must map a *skipped* suite to
  pass (`lab_gate_failed=false`), not to a blocking failure.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The Promote workflow MUST include a cheap gate job that outputs a `run` = true/false
  decision by diffing the promoted SHA against its merge-base with `main`.
- **FR-002**: `run` MUST be true when the diff touches any provisioning-relevant path. Initial list:
  `terraform/**`, `scripts/lab/**`, `ansible/playbooks/lab_*.yml`, `ansible/inventories/**`,
  `scripts/lab/profiles.d/**`, `ansible/roles/lxc_base/**`, and the `lxc_service` Terraform module.
  *(superseded by 086-confidence-suite-trim)*
- **FR-003**: `run` MUST be true whenever `run_confidence_suite=true` is explicitly passed (operator
  override wins), and false only when both the path gate says skip **and** the input isn't forcing it.
- **FR-004**: The confidence-suite job MUST depend on the gate job and run only when `run == true`;
  otherwise it MUST be skipped.
- **FR-005**: A **skipped** suite MUST be treated as a pass by downstream gate logic: promote
  metadata records `lab_gate_failed=false`, and `Prod 2 - LXC Apply` proceeds without override.
- **FR-006**: A **failed** suite MUST behave exactly as today (blocks prod apply unless overridden).
- **FR-007**: The gate MUST fail safe: any inability to compute the diff/base ⇒ run the suite.
- **FR-009** *(amended 2026-10-18)*: The diff base MUST first be the newest commit the suite
  actually **verified**: a previous promote whose suite job concluded `success` and whose
  `promotion-metadata.json` records `suite_ok=true`, and whose `checked_sha` is an ancestor of the
  promoted SHA. An empty diff from that base means the SHA is already verified, so `run=false`.
  The FR-001 merge-base, with its fail-safes, is the fallback only when no such commit is found.
  The gate writes its decision and reason to the step summary.
- **FR-008**: There MUST be no change to what the suite itself does, to the destructive-plan gate, or
  to the LAB apply job (which stays unconditional and service-specific).
  *(superseded by 086-confidence-suite-trim)*

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A promote of a role/template/host_vars/docs-only change completes in **< 4 min** (was
  ~22 min) and its prod apply needs no override.
- **SC-002**: A promote of a `terraform/**` or `scripts/lab/**` change still runs the full ~20-min
  suite and gates prod apply.
- **SC-003**: All three of the recent fail2ban/monitoring-style promotes would be fast under the new
  gate (verified by replaying their diffs against the path list).
- **SC-004**: Zero regressions in the destructive-plan gate and the failed-suite override path.

- **SC-005** *(amended 2026-10-18)*: Promoting `main` after a role/template-only merge skips the
  suite, and a second service promoted from an already-verified SHA skips it. A merged-but-unpromoted
  provisioning change still forces the suite on the next promote.

### Amendment 2026-10-18: why FR-001's base stopped working

PRs now merge before they promote, so the usual promoted ref is `main` itself. `merge-base origin/main
<sha>` is then the SHA, the diff is empty, and FR-007's fail-safe ran the suite on **every** promote
of `main`. 063 had been silently disabled for the main flow. Measured from run history: the suite
ran 8 times since 063 landed, at about 20 minutes each. Today alone it ran 3 times, twice on the same
commit for two services, and none of those runs had a provisioning change since the previous pass.

First-parent diffing (`<sha>^1..<sha>`) was rejected. It sees only the last merge, so a terraform PR
merged yesterday and promoted behind today's role PR would be skipped: a false skip, which this spec
ranks worse than a false run. Diffing from the last verified commit has no such gap. It also closes a
gap the merge-base had all along for branch promotes, which could not see unverified provisioning
changes already on `main`.

## Assumptions

- The existing `mutation.yml` gate→conditional-job→always-running `result` pattern is the intended
  shape to reuse: a cheap gate that diffs paths, a conditional heavy job, and a final job with
  `if: always()` that maps skip→pass and fail→fail so a required check never stays permanently
  pending. A top-level `paths:` filter is explicitly avoided for that reason.
- The compared base for the diff is the merge-base of the promoted SHA with `main`; a docs/spec-only
  path list is treated as non-provisioning.
- Adding runners or parallelising the suite is **out of scope** — the lab is a single `lab-pve-01`
  host guarded by `flock`, so suites cannot run concurrently regardless of runner count.
- Per-SHA confidence reuse across concurrent multi-service promotes is a **separate follow-up item**,
  not part of this feature.
- **Accepted behaviour change to `run_confidence_suite`**: its default flips from `true` to `false`
  and it is repurposed as a force-**on** override (`true` ⇒ always run; unset/`false` ⇒ the path gate
  decides). The previous meaning where `false` forced an unconditional *skip* is dropped — with
  path-gating, non-provisioning promotes skip automatically, and an operator who wants to skip the
  suite on a *provisioning* change uses the existing failed-lab-gate override at apply time instead.

## Dependencies

- No dependency on other backlog items. Touches only `.github/workflows/lxc-promote-prod.yml` and
  possibly the gate math in `lxc-apply-prod.yml`. No Terraform, Ansible, or service/data changes.
- Related follow-up (separate item): per-SHA confidence reuse for batch multi-service promotes.
