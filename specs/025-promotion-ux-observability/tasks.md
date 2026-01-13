---
description: "Task list for feature implementation"
---

# Tasks: Promotion UX Observability

**Input**: Design documents in `specs/025-promotion-ux-observability/`  
**Prerequisites**: `plan.md` (required), `spec.md` (required), `research.md`, `data-model.md`, `contracts/`

**Tests**: No new automated tests were explicitly requested in the spec. Tasks focus on workflow parsing validation (`act -l`) and evidence verification (`scripts/lab/ci-verify.sh`).

## Format: `- [ ] T### [P?] [US?] Description with file path`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[US#]**: User story label (US1..US5)

---

## Phase 1: Setup (Shared Infrastructure)

- [x] T001 Define constants for destructive confirmation tokens in scripts/lab/lib/promotion_tokens.sh
- [x] T002 [P] Add bounded plan UI summary generator in scripts/lab/plan_ui_summary.py
- [x] T003 [P] Add GitHub Actions summary renderer wrapper in scripts/lab/render_github_summary.sh
- [x] T004 [P] Add GitHub Actions annotation helper in scripts/lab/render_github_annotations.sh
- [x] T005 Wire summary generator into existing offline verifier doc references in specs/025-promotion-ux-observability/quickstart.md

---

## Phase 2: Foundational (Blocking Prerequisites)

- [x] T006 Add contract validation helper for plan UI summary JSON in scripts/lab/validate_plan_ui_summary.py
- [x] T007 [P] Add plan summary schema version constant and emit `schema_version` in scripts/lab/plan_ui_summary.py
- [x] T008 [P] Add safe evidence path resolver (env/service/run_id) in scripts/lab/lib/evidence_paths.sh
- [x] T009 Update scripts/lab/ci-verify.sh to optionally validate generated plan UI summary JSON in evidence packs
- [x] T010 Document new summary/annotation conventions in specs/025-promotion-ux-observability/quickstart.md

**Checkpoint**: Summary generation utilities exist; workflow can call them.

---

## Phase 3: User Story 1 - See Plan Before Approving PROD (Priority: P1) 🎯 MVP

**Goal**: Ensure PROD approval happens only after a successful PROD plan and visible plan summary.

**Independent Test**: Dispatch `.github/workflows/lxc-promote.yml` and confirm job order is: Plan(LAB) → Apply(LAB) → Plan(PROD) → Approval(PROD) → Apply(PROD), with PROD summary posted before approval.

- [x] T011 [US1] Reorder jobs in .github/workflows/lxc-promote.yml so `plan_prod` runs before `approve_prod`
- [x] T012 [US1] Ensure `approve_prod` depends on `plan_prod` (not `apply_lab`) in .github/workflows/lxc-promote.yml
- [x] T013 [US1] Add a required “PROD plan summary present” step before requesting approval in .github/workflows/lxc-promote.yml
- [x] T014 [US1] Update job outputs/needs wiring for PROD plan RUN_ID propagation in .github/workflows/lxc-promote.yml

---

## Phase 4: User Story 2 - Destructive Changes Are Blocked by Explicit Confirms (Priority: P1)

**Goal**: Replace boolean destructive confirms with explicit token strings; enforce only when destructive.

**Independent Test**: Make a run with `blast-radius.json.destructive=true` and confirm LAB apply is blocked unless token is exactly `apply-lab-destructive`.

- [x] T015 [US2] Change workflow_dispatch inputs from booleans to strings in .github/workflows/lxc-promote.yml (confirm_destructive_lab/prod)
- [x] T016 [US2] Align workflow input defaults/enums with specs/025-promotion-ux-observability/contracts/workflow-promote.schema.json
- [x] T017 [US2] Update LAB destructive gate to require `apply-lab-destructive` when destructive in .github/workflows/lxc-promote.yml
- [x] T018 [US2] (Historical) PROD destructive gate token requirement removed later to keep apply workflow clean.
- [x] T019 [US2] Ensure non-destructive plans do not require tokens in .github/workflows/lxc-promote.yml
- [x] T020 [US2] Add failure annotations for missing/incorrect destructive tokens in .github/workflows/lxc-promote.yml

---

## Phase 5: User Story 3 - Understand Changes Without Downloading Artifacts (Priority: P1)

**Goal**: Publish bounded plan summaries in run UI for LAB and PROD.

**Independent Test**: Dispatch promotion; confirm both plan jobs include counts + truncated resource list + evidence pointers in `$GITHUB_STEP_SUMMARY`.

- [x] T021 [US3] Generate plan UI summary JSON from evidence `blast-radius.json` in plan jobs in .github/workflows/lxc-promote.yml
- [x] T022 [US3] Render LAB plan summary markdown to `$GITHUB_STEP_SUMMARY` in .github/workflows/lxc-promote.yml
- [x] T023 [US3] Render PROD plan summary markdown to `$GITHUB_STEP_SUMMARY` in .github/workflows/lxc-promote.yml
- [x] T024 [US3] Include evidence pointers (PVE runs dir + run id dir) in summaries per specs/025-promotion-ux-observability/contracts/plan-ui-summary.schema.json
- [x] T025 [US3] Ensure resource list is bounded/truncated (N limit) in scripts/lab/plan_ui_summary.py
- [x] T026 [US3] Upload the generated UI summary JSON alongside evidence artifacts in .github/workflows/lxc-promote.yml

---

## Phase 6: User Story 4 - Failures Are Obvious and Actionable (Priority: P2)

**Goal**: Failures produce concise annotations and short “next steps” guidance.

**Independent Test**: Force a plan failure; confirm workflow emits `::error` annotations and a short summary pointing to evidence paths.

- [x] T027 [US4] Add always-run “summarize outcome” steps for LAB plan/apply jobs in .github/workflows/lxc-promote.yml
- [x] T028 [US4] Add always-run “summarize outcome” steps for PROD plan/apply jobs in .github/workflows/lxc-promote.yml
- [x] T029 [US4] Refactor existing PROD plan failure summarizer to use scripts/lab/render_github_annotations.sh in .github/workflows/lxc-promote.yml
- [x] T030 [US4] Ensure summaries never print secrets and avoid workflow-command injection in scripts/lab/render_github_annotations.sh
- [x] T031 [US4] Add next-step guidance for common failure modes (missing tfvars, missing planfile, token missing) in scripts/lab/render_github_summary.sh
- [x] T032 [US4] Surface LAB state-backup outcome (success/failure) in LAB apply job summary in .github/workflows/lxc-promote.yml
- [x] T033 [US4] Emit a non-fatal warning annotation when LAB state backup fails (apply continues) in .github/workflows/lxc-promote.yml
- [x] T045 [US4] Append bounded evidence excerpts (preflight/summary) to `$GITHUB_STEP_SUMMARY` on failures in .github/workflows/lxc-promote.yml (scripts/lab/render_failure_evidence.sh)

---

## Phase 7: User Story 5 - Production Apply Uses the Exact Planned Changes (Priority: P2)

**Goal**: PROD apply consumes the exact planfile bytes produced by Plan(PROD); no re-plan drift.

**Independent Test**: A successful PROD plan produces a RUN_ID; PROD apply references that RUN_ID and uses `reports/plan/plan.tfplan`. If missing, apply fails immediately with guidance.

- [x] T034 [US5] Add `apply --from-plan-run-id <RUN_ID>` support to scripts/lab/pve-service-deploy
- [x] T035 [P] [US5] Add metadata verification (service/env match) for referenced plan RUN_ID in scripts/lab/pve-service-deploy
- [x] T036 [P] [US5] Add planfile existence check for `reports/plan/plan.tfplan` in scripts/lab/pve-service-deploy
- [x] T037 [US5] Implement Terraform apply-from-planfile path (no `terraform plan`) in scripts/lab/pve-service-deploy
- [x] T038 [US5] Record plan provenance fields (plan_source_run_id, plan_sha256) in evidence provenance in scripts/lab/pve-service-deploy
- [x] T039 [US5] Pass the PROD plan RUN_ID output into PROD apply invocation in .github/workflows/lxc-promote.yml
- [x] T040 [US5] Fail-fast in PROD apply job if plan RUN_ID output is missing/empty in .github/workflows/lxc-promote.yml

---

## Phase 8: Polish & Cross-Cutting Concerns

- [x] T041 [P] Update specs/025-promotion-ux-observability/quickstart.md to include the new string token inputs and example values
- [x] T042 [P] Update specs/025-promotion-ux-observability/contracts/workflow-promote.schema.json examples if workflow inputs change
- [x] T043 Ensure `.github/workflows/lxc-promote.yml` parses with `act -l` (no execution) and note any limitations in specs/025-promotion-ux-observability/quickstart.md
- [x] T044 Validate destructive classification includes replace OR destroy (per FR-005) by cross-checking plan actions vs `blast-radius.json.destructive` in scripts/lab/ci-verify.sh

---

## Dependencies & Execution Order

### User Story Completion Order

- **US1 (P1)**: Workflow sequencing (PROD plan before approval)
- **US2 (P1)**: Destructive token gating
- **US3 (P1)**: Plan UI summaries
- **US4 (P2)**: Failure annotations + next steps
- **US5 (P2)**: Apply-from-saved-plan enforcement

Recommended order for safest incremental delivery:

1) Phase 1–2 (shared summary tooling)
2) US1 (ordering)
3) US2 (token gating)
4) US3 (summaries)
5) US5 (apply-from-plan)
6) US4 (failure UX) + Polish

### Parallel Opportunities

- **Phase 1**: T002–T004 can be parallel (new scripts in different files)
- **Phase 2**: T007–T008 can be parallel
- **US5**: T033–T034 can be parallel
- **US5**: T035–T036 can be parallel
- **Polish**: T041–T043 can be parallel

---

## Parallel Example: User Story 3 (UI Summaries)

Task: "Implement markdown rendering in scripts/lab/render_github_summary.sh"
Task: "Implement JSON summary builder in scripts/lab/plan_ui_summary.py"

---

## Implementation Strategy (MVP First)

- MVP scope: **US1 + US2** (PROD plan before approval + destructive token gating)
- Next: **US3** (summaries) to improve operator speed
- Then: **US5** (apply-from-planfile) to lock integrity
- Finally: **US4** (failure UX) + polish
