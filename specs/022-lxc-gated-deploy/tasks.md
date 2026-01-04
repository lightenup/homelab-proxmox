# Tasks: Gated LXC Deploy (Least Privilege)

**Input**: Design documents from `specs/022-lxc-gated-deploy/`

- `spec.md` (user stories + acceptance)
- `plan.md` (tech + repo constraints)
- `research.md` (key decisions)
- `data-model.md` (inputs/artifacts)
- `contracts/` (workflow input + evidence schemas)
- `quickstart.md` (manual validation flow)

## Format

Every task MUST follow:

- `- [ ] T### [P?] [US#?] Description with file path`

---

## Phase 1: Setup (Shared Infrastructure)

- [x] T001 [P] Create new workflow skeleton in `.github/workflows/lxc-deploy.yml`
- [x] T002 [P] Add operator docs for workflow usage + required secrets in `docs/operations/lxc-deploy-ci.md`
- [x] T003 [P] Create service deploy orchestrator entrypoint script in `scripts/lab/pve-service-deploy`

---

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ CRITICAL**: This phase blocks all user stories.

- [x] T004 Implement workflow input parsing/validation (env/service/confirm) and safe defaults in `scripts/lab/pve-service-deploy`
- [x] T005 [P] Implement evidence pack initialization using existing libs in `scripts/lab/pve-service-deploy` (source `scripts/lab/lib/{artifacts,evidence,provenance}.sh`)
- [x] T006 [P] Implement Terraform plan scope guard using an explicit allowlist of Terraform address prefixes for the target service only; fail if any planned change is outside allowlist in `scripts/lab/pve-service-deploy`
- [x] T007 Implement offline verification hook for produced evidence in `scripts/lab/pve-service-deploy` (reuse `scripts/lab/ci-verify.sh`)
- [x] T008 [P] Add environment tfvars *examples* (no secrets) in `terraform/environments/lab.tfvars.example` and `terraform/environments/prod.tfvars.example`, and update `terraform/terraform.tfvars.example` to direct operators to the new convention

---

## Phase 3: User Story 1 — Plan LXC Deployment Without Changes (Priority: P1) 🎯 MVP

**Goal**: Provide a non-destructive plan/preflight that reports create/update/no-op intent and produces deterministic plan artifacts.

**Independent Test**:
- Run workflow plan for `environment=lab` and confirm:
  - no Proxmox state changes are made
  - a plan artifact + human summary are produced
  - plan is rejected if it attempts to change anything outside the target service LXC scope

### Implementation

- [x] T009 [P] [US1] Add baseline service (Jellyfin) LXC module instantiation in `terraform/main.tf`
- [x] T010 [P] [US1] Add baseline service (Jellyfin) host to Terraform Ansible inventory output in `terraform/outputs.tf`
- [x] T011 [P] [US1] Add baseline service (Jellyfin) IP placeholders and sizing guidance in `terraform/environments/lab.tfvars.example`
- [x] T012 [P] [US1] Add baseline service (Jellyfin) IP placeholders and sizing guidance in `terraform/environments/prod.tfvars.example`
- [x] T013 [US1] Implement `plan` subcommand to run `terraform init/validate/plan -detailed-exitcode` and write plan artifacts under `/var/lib/homelab-proxmox/artifacts/service-deploy-runs/<run_id>` in `scripts/lab/pve-service-deploy`
- [x] T014 [US1] Implement human-readable intent summary (create/update/no-op/blocked) in `scripts/lab/pve-service-deploy` and write to evidence path `reports/plan/summary.txt`
- [x] T015 [US1] Enforce allowlist scope guard by inspecting `terraform show -json` output and failing if any resource change address is outside allowlist in `scripts/lab/pve-service-deploy`
- [x] T016 [US1] Wire up a `plan` job that runs on `pull_request` (only when `github.event.pull_request.head.repo.full_name == github.repository`) and on `workflow_dispatch` in `.github/workflows/lxc-deploy.yml`
- [x] T017 [US1] Fetch evidence from PVE and run offline verification in `.github/workflows/lxc-deploy.yml`

**Checkpoint**: A PR/dispatch plan run produces verified, reviewable artifacts and cannot mutate Proxmox.

---

## Phase 4: User Story 2 — Apply to Lab With Evidence (Priority: P2)

**Goal**: Apply to LAB to create/configure the target service LXC idempotently (baseline example: Jellyfin) and produce an offline-verifiable evidence bundle.

**Independent Test**:
- Run LAB apply twice:
  - first run creates/configures the container
  - second run converges without recreating
  - evidence verification passes offline

### Implementation

- [x] T018 [P] [US2] Create Jellyfin Ansible role scaffolding in `ansible/roles/jellyfin/` (`tasks/`, `handlers/`, `defaults/`, `templates/`)
- [x] T019 [US2] Implement idempotent Jellyfin install/config tasks in `ansible/roles/jellyfin/tasks/main.yml`
- [x] T020 [P] [US2] Add Jellyfin host variables in `ansible/host_vars/jellyfin.yml`
- [x] T021 [P] [US2] Add Jellyfin playbook entrypoint in `ansible/playbooks/jellyfin.yml`
- [x] T022 [US2] Implement `apply` subcommand to run Terraform apply + Ansible playbook + evidence capture in `scripts/lab/pve-service-deploy` (depends on T013)
- [x] T023 [P] [US2] Add Jellyfin healthcheck script in `scripts/healthcheck/jellyfin.sh`
- [x] T024 [US2] Integrate Jellyfin healthcheck into evidence bundle in `scripts/lab/pve-service-deploy`
- [x] T025 [US2] Add LAB auto-apply job to `.github/workflows/lxc-deploy.yml` (gated by input `environment=lab`)
- [x] T026 [US2] Add LAB idempotency verification step (second apply + assert no changes/no recreate) in `.github/workflows/lxc-deploy.yml`

**Checkpoint**: LAB apply is idempotent and produces a verified evidence bundle.

---

## Phase 5: User Story 3 — Apply to Production With Explicit Approval (Priority: P3)

**Goal**: Prevent accidental PROD apply via approval gate + explicit confirmation input; when allowed, deploy with least privilege and verified evidence.

**Independent Test**:
- Attempt PROD apply without approval/confirm (must not proceed)
- Run PROD apply with approval + correct confirm string (must proceed and verify)

### Implementation

- [x] T027 [US3] Add PROD gating (GitHub Environment + confirm input check) to `.github/workflows/lxc-deploy.yml`
- [x] T028 [US3] Add concurrency grouping per env/service to prevent overlapping applies in `.github/workflows/lxc-deploy.yml`
- [x] T029 [US3] Ensure workflow cannot run PROD apply on `push` (only `workflow_dispatch`) in `.github/workflows/lxc-deploy.yml`
- [x] T030 [P] [US3] Document PROD Environment setup steps and confirm-string semantics in `docs/operations/lxc-deploy-ci.md`

**Checkpoint**: PROD apply is blocked by default and only runs under explicit, auditable intent.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [x] T031 [P] Add a valid fixture evidence pack for service deploy in `scripts/lab/fixtures/evidence-packs/service-deploy-valid/`
- [x] T032 Add least-privilege smoke checks: assert `whoami != root`, capture `sudo -l`, require non-interactive sudo only (`sudo -n`) if used, and deny shell escalation in `.github/workflows/lxc-deploy.yml`
- [x] T033 [P] Link the new workflow docs from `docs/operations/proxmox-ci.md`
- [x] T034 [P] Run `quickstart.md` validation and update `specs/022-lxc-gated-deploy/quickstart.md` if any steps diverge

---

## Dependencies & Execution Order

### Phase Dependencies

- Phase 1 (Setup) → Phase 2 (Foundational) → Phase 3 (US1) → Phase 4 (US2) → Phase 5 (US3) → Phase 6 (Polish)

### User Story Dependencies

- **US1 (P1)**: Depends on Phase 2.
- **US2 (P2)**: Depends on US1 plan/apply scaffolding (`scripts/lab/pve-service-deploy`) and Phase 2.
- **US3 (P3)**: Depends on US2 apply job wiring and Phase 2.

---

## Parallel Execution Examples

### User Story 1

Run in parallel after Phase 2:

- T009 (terraform baseline service module) + T010 (terraform outputs) + T011/T012 (tfvars examples)

### User Story 2

Run in parallel after US1 plan exists:

- T018 (role scaffolding) + T020 (host_vars) + T021 (playbook) + T023 (healthcheck)

### User Story 3

Run in parallel:

- T030 (docs) while T027–T029 update workflow gating

---

## Implementation Strategy

### MVP (Stop After US1)

- Complete Phases 1–3.
- Validate plan/preflight in LAB.
- Stop and review the artifacts + scope guard before any apply automation.

### Incremental Delivery

- Add US2 (LAB apply) once US1 is stable.
- Add US3 (PROD gating) only after LAB apply is proven idempotent and evidence verification is reliable.
