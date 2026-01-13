# Tasks: Separate LAB + PROD Promotion Pipeline (Spec 026)

**Input**: Design documents from `/specs/026-separate-prod-apply/`

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (`[US1]`, `[US2]`, `[US3]`)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

- [X] T001 [P] Create LAB-only workflow scaffold (workflow_dispatch inputs + service choices) in .github/workflows/lxc-promote-lab.yml
- [X] T002 [P] Create PROD promotion pipeline workflow scaffold (workflow_dispatch inputs: ref + service + allow_override_failed_lab_gate + destructive confirmations) in .github/workflows/lxc-promote-prod.yml
- [X] T003 [P] Align workflow dispatch docs with inputs in specs/026-separate-prod-apply/contracts/workflows.openapi.yml

---

## Phase 2: Foundational (Blocking Prerequisites)

- [X] T004 Create evidence-fetch helper used by promotion workflows in scripts/lab/fetch_evidence_pack.sh (ssh to PVE, tar evidence dir, scp to runner, extract under evidence/<env>/, and return local evidence path)
- [X] T005 [P] Update top-level operator flow docs (LAB promote for iteration; PROD promote pipeline for release) in README.md

---

## Phase 3: User Story 1 - Promote to LAB Without Triggering PROD (Priority: P1)

**Goal**: Run LAB plan/apply without any PROD approval/apply steps.

**Independent Test**: Trigger the LAB workflow for any allowlisted service; confirm the run has no PROD jobs, publishes a bounded summary, and uploads evidence as an artifact.

- [X] T006 [US1] Implement LAB plan/apply jobs (no PROD) in .github/workflows/lxc-promote-lab.yml by porting Plan(LAB)+Apply(LAB) logic from .github/workflows/lxc-promote.yml (allowlist check, rsync to PVE, run pve-service-deploy plan/apply, capture RUN_ID, fetch evidence via scripts/lab/fetch_evidence_pack.sh)
- [X] T007 [US1] Add bounded job summary + offline verify + evidence upload in .github/workflows/lxc-promote-lab.yml (use scripts/lab/ci-verify.sh; on failure append bounded excerpts via scripts/lab/render_failure_evidence.sh; upload evidence artifact)

---

## Phase 4: User Story 2 - Promote to PROD With Interactive Approval After LAB Confidence (Priority: P1)

**Goal**: PROD promotion is an explicitly triggered pipeline that shows LAB + confidence + PROD plan results before a GitHub Environment approval gate.

**Independent Test**: Trigger the PROD promotion pipeline with a `ref`; confirm it checks out that ref, runs LAB deploy + confidence suite (best-effort), generates PROD plan even on LAB/suite failure, publishes LAB+Suite+Plan summaries, then pauses at `environment: prod` and does not execute PROD apply until approved.

- [X] T008 [US2] Implement `ref` checkout and provenance SHA source-of-truth in .github/workflows/lxc-promote-prod.yml (checkout `inputs.ref`, capture checked-out SHA, use it for all strict SHA validations)
- [X] T009 [US2] Implement Apply(LAB) stage in .github/workflows/lxc-promote-prod.yml (rsync to PVE, run scripts/lab/pve-service-deploy apply for lab, capture LAB RUN_ID, fetch evidence via scripts/lab/fetch_evidence_pack.sh)
- [X] T010 [US2] Implement confidence suite stage in .github/workflows/lxc-promote-prod.yml using scripts/lab/pve-lab confidence suite (best-effort even if LAB deploy failed; capture suite run id/output; fetch evidence if applicable)
- [X] T011 [US2] Implement Plan(PROD) stage in .github/workflows/lxc-promote-prod.yml that runs even when LAB deploy or confidence suite fails (use `if: always()`/equivalent; capture PROD plan RUN_ID; fetch plan evidence)
- [X] T012 [US2] Publish combined, bounded run summaries before approval in .github/workflows/lxc-promote-prod.yml (LAB evidence pointer(s), confidence suite evidence pointer(s), PROD plan summary + plan reference; bounded failure excerpts via scripts/lab/render_failure_evidence.sh)
- [X] T013 [US2] Add GitHub Environment approval gate in .github/workflows/lxc-promote-prod.yml using `environment: prod` (approval blocks PROD apply)
- [X] T014 [US2] Enforce gate override semantics in .github/workflows/lxc-promote-prod.yml: if LAB deploy or confidence suite failed then require `inputs.allow_override_failed_lab_gate=true` to proceed to PROD apply (override applies only to PROD apply decision; does not affect LAB execution)
- [X] T015 [US2] Restrict secrets to PROD apply only in .github/workflows/lxc-promote-prod.yml (no secrets in summary jobs; only pass secrets via env to the SSH/apply step)

---

## Phase 5: User Story 3 - PROD Apply Uses a Saved Plan Reference (Priority: P2)

**Goal**: PROD apply uses saved plan bytes from the PROD plan generated earlier in the same run and validates plan provenance strictly (service/env/SHA), failing fast with guidance.

**Independent Test**: Trigger PROD promotion with a `ref`; after approval, confirm PROD apply uses `--from-plan-run-id <prod_plan_run_id>`. Re-run with intentionally mismatched provenance/evidence and confirm the pipeline fails before approval or before apply with clear guidance.

- [X] T016 [US3] Implement PROD apply-from-saved-plan step in .github/workflows/lxc-promote-prod.yml using scripts/lab/pve-service-deploy apply --environment prod --service <service> --from-plan-run-id <prod_plan_run_id>
- [X] T017 [US3] Enforce strict SHA alignment checks in .github/workflows/lxc-promote-prod.yml by validating evidence provenance git_sha for: LAB deploy, confidence suite run, and PROD plan against the checked-out SHA before requesting approval
- [ ] T018 [US3] (Removed) Destructive PROD confirmation token was intentionally removed to keep the apply workflow clean.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T019 Deprecate or remove combined LAB→PROD workflow in .github/workflows/lxc-promote.yml
- [X] T020 Update operator documentation for new flow (LAB promote; PROD promote pipeline with approval) in docs/operations.md
- [X] T021 Document workflow parse validation command in specs/026-separate-prod-apply/quickstart.md (e.g., `act -l` / `act -n -W .github/workflows/lxc-promote-prod.yml workflow_dispatch`)

---

## Phase 7: Operator UX + Provenance Robustness

- [X] T022 [US2] Add a bounded "recent commits" list (SHA + subject) to the PROD promotion run summary in .github/workflows/lxc-promote-prod.yml to make selecting `ref` easier.
- [X] T023 [US3] Ensure service-deploy evidence provenance records the checked-out git SHA even when PVE cannot infer it from git metadata (e.g., `git_sha=unknown`); pass GIT_SHA from .github/workflows/lxc-promote-prod.yml into remote pve-service-deploy plan/apply.

---

## Dependencies & Execution Order

### User Story Dependencies

- **US1**: No dependency on other stories.
- **US2**: Depends on Foundational tasks (Phase 2).
- **US3**: Depends on **US2** (adds apply-from-plan + strict validations + destructive gating).

### Suggested MVP Scope

- MVP = **US1 only** (Phase 3) after completing Phases 1–2.

### Parallel Opportunities

- Phase 1 tasks T001–T003 are parallel (different files).
- Phase 2 task T005 is parallel with T004 (docs vs script).
- After Phase 2, US1 can proceed independently while US2 scaffolding proceeds in parallel.

### Parallel Example: User Story 2

- Implement checkout/ref handling (T008) while implementing evidence fetch helper (T004) and approval/secrets wiring (T013, T015).

## Implementation Strategy

- Implement and validate **US1 (LAB-only)** first.
- Implement **US2** pipeline skeleton end-to-end next (including plan-always-runs + summaries + approval gate).
- Implement **US3** strict validations + apply-from-saved-plan + destructive gating last.
- Finish by deprecating/removing `.github/workflows/lxc-promote.yml` and updating docs.
