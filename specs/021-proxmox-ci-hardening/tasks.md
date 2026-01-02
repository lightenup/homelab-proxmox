# Tasks: Proxmox CI hardening

**Input**: Design documents from /specs/021-proxmox-ci-hardening/
**Prerequisites**: plan.md (required), spec.md (required); research.md, data-model.md, contracts/ (not present)

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish shared config and artifact location used by all stories

- [x] T001 [P] Create artifact root helper with constant /var/lib/homelab-proxmox/artifacts and mkdir -p logic in scripts/lab/lib/artifacts.sh

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Baseline checks and outputs required before any story

- [x] T002 [P] Add dependency preflight (jq, ssh, rsync) with clear errors in scripts/lab/checks.d/deps.sh
- [x] T003 Wire pve-lab to invoke dependency preflight before rebuild/apply/verify in scripts/lab/pve-lab
- [x] T004 [P] Ensure checks.json writer uses artifact helper and fails fast on missing jq in scripts/lab/lib/check_record.sh
- [x] T004a [P] Add sudo -n helper (central wrapper) and refactor privileged calls in scripts/lab/pve-lab and scripts/lab/lib/* to use it (covers FR-006)
- [x] T004b Add a timing guard in dependency preflight to log duration and fail if required tools are not validated within 60s to satisfy SC-005

**Checkpoint**: Foundation ready – user stories may proceed

---

## Phase 3: User Story 1 - Pipeline runs as ci on pi-ci (Priority: P1) 🎯 MVP

**Goal**: proxmox-apply runs on pi-ci via ci@pve only, rsync excludes artifacts, rebuild/apply/verify succeeds without root-owned outputs

**Independent Test**: Run proxmox-apply on pi-ci; confirm all SSH/rsync use ci@pve, artifacts untouched, rebuild/apply/verify passes, no root SSH in logs

### Implementation

- [x] T005 [US1] Update .github/workflows/proxmox-apply.yml to use ci@pve for ssh/rsync, exclude /var/lib/homelab-proxmox/artifacts, remove root usage, and run scripts/lab/pve-lab rebuild --apply --verify as ci
- [x] T006 [P] [US1] Route pve-lab log/lock/evidence paths through artifact helper to avoid sudo-owned files in scripts/lab/pve-lab
- [x] T007 [P] [US1] Add rsync-safe artifact bootstrap ensuring /var/lib/homelab-proxmox/artifacts exists and is ci-owned before deploy in scripts/lab/guardrails.sh
- [x] T008 [US1] Add post-deploy validation step to run scripts/lab/ci-verify.sh fixtures/evidence-packs/valid in .github/workflows/proxmox-apply.yml

**Checkpoint**: User Story 1 independently testable via proxmox-apply on pi-ci

---

## Phase 4: User Story 2 - Least-privilege sudo guardrails (Priority: P2)

**Goal**: ci has constrained sudoers with smoke checks proving allowed commands succeed and blocked commands fail

**Independent Test**: Run sudo -n true and sudo -n qm --version (pass) and sudo -n bash (deny) from pipeline after deploy

### Implementation

- [x] T009 [P] [US2] Create sudoers policy template with Cmnd_Alias for qm/pct/pvesh/pveversion (+ minimal service controls), Defaults:ci !requiretty, NOPASSWD, in scripts/lab/profiles.d/ci-sudoers.conf
- [x] T010 [US2] Add installer/apply logic to deploy sudoers template to /etc/sudoers.d/ci-homelab with visudo -c validation in scripts/lab/pve-lab
- [x] T011 [P] [US2] Add workflow smoke checks for sudo -n true, sudo -n qm --version success, and sudo -n bash failure in .github/workflows/proxmox-apply.yml

**Checkpoint**: User Story 2 validated via smoke checks

---

## Phase 5: User Story 3 - Deterministic provisioning with evidence (Priority: P3)

**Goal**: Provisioning either reaches SSH within extended timeout or emits evidence bundle (qm status/config, cloud-init, network probes, logs)

**Independent Test**: Trigger rebuild; verify success within timeout or evidence bundle produced under /var/lib/homelab-proxmox/artifacts

### Implementation

- [x] T012 [P] [US3] Parameterize provisioning SSH wait timeout (>=5m default) and SSH user/key inputs in scripts/lab/lib/rebuild.sh
- [x] T013 [P] [US3] Implement evidence collection helper capturing qm status/config, cloud-init files, network probes, and logs into artifact path in scripts/lab/lib/evidence.sh
- [x] T014 [US3] Integrate evidence collection on provisioning timeout and attach outputs to artifacts in scripts/lab/pve-lab

**Checkpoint**: User Story 3 emits success or actionable evidence

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Documentation and alignment across tooling

- [x] T015 [P] Document pi-ci workflow, artifact path, sudoers policy, and runbook in docs/operations/proxmox-ci.md
- [x] T016 [P] Add quickstart steps for rerunning proxmox-apply and reviewing evidence bundles in specs/021-proxmox-ci-hardening/quickstart.md
- [x] T017 Update docs/operations.md to reinforce ci-only Ansible/Terraform usage and Proxmox API token guidance
- [x] T018 Add validation step (lint or scripted check) ensuring Ansible uses remote_user=ci with become -n and Terraform uses non-root Proxmox API token; document required roles/secret wiring in docs/operations/proxmox-ci.md

---

## Dependencies & Execution Order

- Phase order: Setup → Foundational → US1 (P1) → US2 (P2) → US3 (P3) → Polish.
- US1 depends on Foundational; US2 depends on US1 (workflow base) and Foundational; US3 depends on Foundational (preflight) and can run after US1 for shared paths.
- Polish follows all stories.

## Parallel Execution Examples

- Within US1: T006 and T007 can proceed in parallel after T005 is staged.
- Within US2: T009 and T011 can run in parallel; T010 follows T009.
- Within US3: T012 and T013 can run in parallel; T014 follows both.

## Implementation Strategy

- MVP: Complete Setup → Foundational → US1; validate proxmox-apply green on pi-ci.
- Incremental: After MVP, apply US2 (sudo guardrails + smoke checks), then US3 (timeout + evidence). Finish with Polish docs.
- Always validate with scripts/lab/ci-verify.sh fixtures/evidence-packs/valid and a proxmox-apply run on pi-ci after each story.
