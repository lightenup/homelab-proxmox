# Tasks: Pipeline Promotion UX

**Input**: Design documents from `/specs/024-pipeline-promotion-ux/`

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., [US1])
- Each task includes an exact file path

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create shared contracts needed by offline verification.

- [ ] T001 [P] Copy evidence schema `specs/024-pipeline-promotion-ux/contracts/evidence-lab-snapshot.schema.json` to `scripts/lab/contracts/evidence-lab-snapshot.schema.json`
- [ ] T002 [P] Copy evidence schema `specs/024-pipeline-promotion-ux/contracts/evidence-tfvars-proof.schema.json` to `scripts/lab/contracts/evidence-tfvars-proof.schema.json`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Evidence profile + offline verification + baseline snapshot generation required by all workflows.

- [ ] T003 Update evidence profile in `scripts/lab/profiles.d/service-deploy.json` to require `reports/lab-snapshot.json` for all runs and `reports/prod-tfvars/*` for PROD runs
- [ ] T004 [P] Implement baseline snapshot generator in `scripts/lab/lib/snapshot.sh` to emit required fields (`generated_at`, `environment`, `containers`, `services`, `errors`) matching `scripts/lab/contracts/evidence-lab-snapshot.schema.json`
- [ ] T005 Integrate snapshot generation into `scripts/lab/pve-service-deploy` so every run writes `reports/lab-snapshot.json` into the evidence pack
- [ ] T006 Update schema validation in `scripts/lab/verify_evidence.py` to validate `reports/lab-snapshot.json` against `scripts/lab/contracts/evidence-lab-snapshot.schema.json`
- [ ] T007 Update schema validation in `scripts/lab/verify_evidence.py` to validate `reports/prod-tfvars/validation.json` against `scripts/lab/contracts/evidence-tfvars-proof.schema.json` (PROD-only)
- [ ] T008 Update CI wrapper in `scripts/lab/ci-verify.sh` to enforce the updated profile + schema validations
- [ ] T009 [P] Update fixture pack `scripts/lab/fixtures/evidence-packs/service-deploy-valid/reports/lab-snapshot.json` to a schema-valid baseline snapshot
- [ ] T010 [P] Add baseline PROD tfvars proof fixtures under `scripts/lab/fixtures/evidence-packs/service-deploy-valid/reports/prod-tfvars/` (schema-valid placeholders)

**Checkpoint**: Offline evidence verification updated and fixtures pass.

---

## Phase 3: User Story 1 - Run a LAB deploy with clean inputs (Priority: P1) 🎯 MVP

**Goal**: LAB deploy workflow has bounded inputs and always produces an evidence pack plus a snapshot artifact.

**Independent Test**: Dispatch the LAB workflow (plan-only), verify the run completes, and download artifact containing an evidence pack with `reports/lab-snapshot.json` that passes offline verification.

### Implementation

- [ ] T011 [P] [US1] Create workflow `.github/workflows/lxc-deploy-lab.yml` with `workflow_dispatch` inputs matching `specs/024-pipeline-promotion-ux/contracts/workflow-lab-deploy.schema.json`
- [ ] T012 [P] [US1] Add allowlist runtime validation step in `.github/workflows/lxc-deploy-lab.yml` using `scripts/lab/service-scope-allowlist.json`
- [ ] T013 [US1] Wire `.github/workflows/lxc-deploy-lab.yml` to run `scripts/lab/pve-service-deploy` in LAB mode with plan-only/apply based on the `apply` input
- [ ] T014 [US1] Implement LAB destructive confirmation handling in `.github/workflows/lxc-deploy-lab.yml` using `confirm_destructive` (`apply-lab-destructive`) before applying
- [ ] T015 [US1] Upload LAB evidence pack + snapshot artifact in `.github/workflows/lxc-deploy-lab.yml` (artifact names include service + run id)

**Checkpoint**: US1 delivers a clean LAB workflow with artifacts.

---

## Phase 4: User Story 2 - Promote a service from LAB to PROD with approval (Priority: P1)

**Goal**: Promotion is enforced in a single workflow run: LAB apply must succeed before PROD can run, and PROD requires approval.

**Independent Test**: Dispatch promote workflow, confirm LAB stage completes, confirm PROD is blocked behind approval, then approve and confirm PROD stage completes with evidence.

### Implementation

- [ ] T016 [P] [US2] Create workflow `.github/workflows/lxc-promote.yml` with `workflow_dispatch` inputs matching `specs/024-pipeline-promotion-ux/contracts/workflow-promote.schema.json`
- [ ] T017 [P] [US2] Add allowlist runtime validation step in `.github/workflows/lxc-promote.yml` using `scripts/lab/service-scope-allowlist.json`
- [ ] T018 [US2] Implement job graph (LAB plan/apply → approval gate → PROD plan/apply) in `.github/workflows/lxc-promote.yml`
- [ ] T019 [US2] Add production approval gate to PROD stage in `.github/workflows/lxc-promote.yml` (protected `prod` environment)
- [ ] T020 [US2] Implement destructive confirmation handling for LAB and PROD in `.github/workflows/lxc-promote.yml` using `confirm_destructive_lab` and `confirm_destructive_prod`
- [ ] T021 [US2] Upload separate LAB and PROD evidence artifacts in `.github/workflows/lxc-promote.yml` (include stage + service + run id)

**Checkpoint**: US2 enforces LAB→approval→PROD promotion.

---

## Phase 5: User Story 3 - Avoid PROD failures caused by missing/invalid prod tfvars (Priority: P1)

**Goal**: PROD stage provisions and validates `prod.tfvars` automatically and records redacted proof in evidence.

**Independent Test**: Start with missing/invalid tfvars on the Proxmox host, run promote workflow, and confirm the PROD stage fails early with clear evidence OR succeeds and produces a valid tfvars proof.

### Implementation

- [ ] T022 [P] [US3] Implement tfvars provisioning helpers in `scripts/lab/lib/tfvars.sh` (render, validate, and write redacted proof)
- [ ] T023 [US3] Integrate tfvars provisioning/validation into `scripts/lab/pve-service-deploy` for PROD runs and write `reports/prod-tfvars/provisioning.txt`, `reports/prod-tfvars/validation.json`, and `reports/prod-tfvars/prod.tfvars.sha256`
- [ ] T024 [US3] Ensure secrets are never logged by `scripts/lab/pve-service-deploy` and `scripts/lab/lib/tfvars.sh` (only `token_id` and booleans/hashes appear in evidence)
- [ ] T025 [US3] Enforce token id validation (`terraform@pve!terraform-token`) in `scripts/lab/lib/tfvars.sh` and fail before Terraform if invalid
- [ ] T026 [US3] Update verifier logic in `scripts/lab/verify_evidence.py` to treat missing/invalid PROD tfvars evidence as a hard failure for PROD runs
- [ ] T027 [P] [US3] Update fixture pack `scripts/lab/fixtures/evidence-packs/service-deploy-valid/reports/prod-tfvars/validation.json` to include a passing example matching schema

**Checkpoint**: PROD tfvars drift no longer blocks deploys.

---

## Phase 6: User Story 4 - Hotfix on main with explicit override (Priority: P2)

**Goal**: Main-branch hotfix runs are possible but require explicit override and approvals; prerequisite checks no longer hard-require feature branches.

**Independent Test**: Trigger promote workflow from `main` without override (must fail), then with override (must proceed to LAB and still require PROD approval).

### Implementation

- [ ] T028 [P] [US4] Remove feature-branch-only assumptions in prerequisite checks by updating `scripts/lab/guardrails.sh` and any relevant checks in `scripts/lab/checks.d/`
- [ ] T029 [US4] Enforce hotfix override gating in `.github/workflows/lxc-promote.yml` when running from `main` (fail early unless `hotfix_override` is true)
- [ ] T030 [US4] Record hotfix mode in evidence metadata by updating `scripts/lab/pve-service-deploy` (e.g., include branch + hotfix flag in `provenance.json` or run metadata)
- [ ] T031 [US4] Update operator instructions in `specs/024-pipeline-promotion-ux/quickstart.md` to document hotfix override behavior and safety constraints

**Checkpoint**: Hotfix path exists without weakening safety.

---

## Phase 7: User Story 5 - View “what’s in LAB” quickly (Priority: P2)

**Goal**: Snapshot artifact provides quick visibility into LAB container state, evidence pointers, and mount checks.

**Independent Test**: Run a plan-only LAB workflow and confirm the downloaded snapshot includes `latest_evidence` and mount checks when applicable.

### Implementation (Enhancements)

- [ ] T032 [US5] Populate `latest_evidence` in `scripts/lab/lib/snapshot.sh` by scanning the evidence pack directory and finding the latest run id per service
- [ ] T033 [US5] Implement `mount_checks` in `scripts/lab/lib/snapshot.sh` by checking `/proc/mounts` inside target containers (at minimum validate `/media/video` mounted RO when declared)
- [ ] T034 [P] [US5] Update fixture pack `scripts/lab/fixtures/evidence-packs/service-deploy-valid/reports/lab-snapshot.json` to include `latest_evidence` and `mount_checks` examples

**Checkpoint**: Operators can quickly see LAB state from artifacts.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, migration, and consistency checks.

- [ ] T035 [P] Update workflow documentation in `README.md` to reference `.github/workflows/lxc-deploy-lab.yml` and `.github/workflows/lxc-promote.yml` and explain the production approval gate
- [ ] T036 [P] Add a deprecation notice to `.github/workflows/lxc-deploy.yml` pointing operators to the new workflows
- [ ] T037 Validate docs and schemas stay in sync by reviewing `specs/024-pipeline-promotion-ux/quickstart.md` against the implemented workflow inputs

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies
- **Foundational (Phase 2)**: Depends on Phase 1; blocks all user stories
- **User Stories (Phases 3–7)**: Depend on Phase 2; proceed in priority order (P1 → P2)
- **Polish (Phase 8)**: Depends on all desired user stories

### User Story Dependencies

- **[US1] (P1)**: Depends on Phase 2 snapshot + offline verification updates
- **[US2] (P1)**: Depends on Phase 2 and benefits from [US1] patterns (input validation + artifact upload)
- **[US3] (P1)**: Depends on [US2] PROD stage and Phase 2 PROD evidence profile enforcement
- **[US4] (P2)**: Depends on [US2] promote workflow
- **[US5] (P2)**: Depends on Phase 2 baseline snapshot; adds richer visibility

---

## Parallel Execution Examples (by Story)

### [US1]

- Parallelizable tasks: T011, T012

### [US2]

- Parallelizable tasks: T016, T017

### [US3]

- Parallelizable tasks: T022, T027

### [US5]

- Parallelizable tasks: T034

---

## Implementation Strategy

### Suggested MVP

- Implement **Phase 1–3** (through [US1]) first.
- Validate: plan-only LAB run produces evidence pack + snapshot and passes offline verification.

### Then Promote

- Add **[US2]** to enforce promotion flow.
- Add **[US3]** to eliminate PROD tfvars manual steps.

### Finally

- Add **[US4]** hotfix override and **[US5]** richer snapshots + mount checks.
