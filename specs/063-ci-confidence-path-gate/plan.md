# Implementation Plan: Path-gate the Promote confidence suite

**Branch**: `063-ci-confidence-path-gate` | **Date**: 2026-07-14 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/063-ci-confidence-path-gate/spec.md`

## Summary

Add a cheap `confidence_gate` job to `.github/workflows/lxc-promote-prod.yml` that diffs the promoted
SHA against its merge-base with `main` and decides whether the ~20-minute `confidence_suite` needs to
run. Gate the suite with `needs: [confidence_gate]` + an `if:` that also honours the existing
`run_confidence_suite` operator override. Then fix the downstream gate math in
`summarize_before_approval` so a **skipped** suite (not just a passed one) maps to
`lab_gate_failed=false` **and** keeps `sha_all_ok=true`, so `Prod 2 - LXC Apply` proceeds without an
override. Reuse the exact gate→conditional-job→`if: always()` shape already proven in
`.github/workflows/mutation.yml`. No change to the suite itself, the LAB apply, the PROD plan, or the
destructive gate.

## Technical Context

**Language/Version**: GitHub Actions workflow YAML; Bash (POSIX/`bash`) in `run:` steps; `git` for
diff/merge-base. No new language.
**Primary Dependencies**: `actions/checkout@v4` (with `fetch-depth: 0` for merge-base), `git`,
GitHub Actions `needs`/`if`/`always()` semantics. No new actions or tools.
**Storage**: N/A — no persistent data. Decision lives only in a job output for the run's lifetime.
Promotion metadata JSON (`prod-promotion-metadata`) is unchanged in shape.
**Testing**: `act -l` and `act -n -W .github/workflows/lxc-promote-prod.yml workflow_dispatch` for
parse/dry-run validation (constitution "Local Workflow Testing"); acceptance is by running the five
scenarios in the spec's Verification section against real promotes.
**Target Platform**: `ubuntu-latest` GitHub-hosted runner for the cheap gate job; existing
`[self-hosted]` runner for the suite (unchanged).
**Project Type**: Single repo, CI/pipeline change — no `src/` structure. Touches
`.github/workflows/` only.
**Performance Goals**: Fast-path promote (non-provisioning diff) completes in **< 4 min** (was
~22 min); gate job itself adds only seconds.
**Constraints**: Fail-safe (any diff/base failure ⇒ run the suite); conservative path list (prefer
false-run over false-skip); a *skipped* suite must never leave a required-style gate pending or
falsely block apply.
**Scale/Scope**: Two files at most — `lxc-promote-prod.yml` (definite) and `lxc-apply-prod.yml`
(audit-only; expected no change, see research). One new job + one edited job + one gate-math step.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Spec-Driven Workflow** — PASS. Work is driven from `specs/063-ci-confidence-path-gate/`;
  implementation will reference `tasks.md`. Behaviour change (gate semantics) is captured in the spec
  and mirrored in-workflow via a comment pointing back at this spec.
- **II. Secrets Policy** — PASS. No secrets touched. The gate job runs on GitHub-hosted `ubuntu`
  with `contents: read` only and needs no vault/token access.
- **III. Separation of Concerns** — PASS. Pure CI orchestration; no Terraform/Ansible responsibility
  mixing. The suite, LAB apply, and PROD plan are untouched.
- **IV. Code Economy (YAGNI)** — PASS. Reuses the existing `mutation.yml` pattern rather than
  inventing a new abstraction. Path list is inlined in the gate step (single consumer), not extracted
  into a shared file. No new scripts, roles, or modules. Adds exactly one job.
- **V. Dual-Provisioning Parity** — PASS with note. The gate is a diff computation that a developer
  can reproduce locally (`git diff --name-only $(git merge-base main <sha>) <sha>`); the existing
  `run_confidence_suite=false` input already offers the manual equivalent. No CI-only capability is
  introduced. `act` dry-run is the local validation path.
- **CI/CD Expectations** — PASS. No new destructive automation; barriers (approval-equivalent manual
  apply, override, destructive plan gate) are unchanged.

**Result**: No violations. Complexity Tracking table not required.

## Project Structure

### Documentation (this feature)

```text
specs/063-ci-confidence-path-gate/
├── plan.md              # This file
├── research.md          # Phase 0 output — gate placement, skip=pass math, fail-safe, path list
├── data-model.md        # Phase 1 output — gate decision + metadata field semantics (no DB)
├── quickstart.md        # Phase 1 output — how to validate the five acceptance scenarios
├── contracts/
│   └── confidence-gate.md   # Job I/O contract + provisioning path list + downstream gate mapping
├── checklists/
│   └── requirements.md  # Spec quality checklist (from /speckit.specify)
└── tasks.md             # Phase 2 output (/speckit.tasks — NOT created here)
```

### Source Code (repository root)

```text
.github/workflows/
├── lxc-promote-prod.yml   # EDIT: add confidence_gate job; gate confidence_suite via needs+if;
│                          #       fix compute_gate to map skipped suite → ok + sha_ok
├── lxc-apply-prod.yml     # AUDIT ONLY: confirm skipped-suite path is unblocked (expected no edit)
└── mutation.yml           # REFERENCE ONLY: the gate→conditional→result pattern being reused
```

**Structure Decision**: This is a CI/pipeline feature. There is no application source tree; the unit
of change is the GitHub Actions workflow. All edits are confined to `.github/workflows/`, with the
authoritative behavioural change in `lxc-promote-prod.yml`. `lxc-apply-prod.yml` is read to confirm
the skipped-suite outcome flows through `lab_gate_failed=false` + `sha_all_ok=true` without needing
an override; research shows the fix belongs in the promote workflow's `compute_gate` step, so apply
is expected to need no change.

## Complexity Tracking

> No constitution violations — table intentionally omitted.
