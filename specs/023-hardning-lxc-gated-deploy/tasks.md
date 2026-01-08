# Tasks: Hardening Gated LXC Deploy (023)

**Input**: Design documents from `specs/023-hardning-lxc-gated-deploy/`

- `spec.md` (requirements + constraints)
- `plan.md` (phased implementation plan)

## Format

Every task MUST follow:

- `- [ ] T### [P?] [US#?] Description with file path`

---

## Phase 0: Foundational (Blocking Prerequisites)

**⚠️ CRITICAL**: This phase blocks all user story work.

- [X] T001 Define canonical service allowlist mapping in `scripts/lab/service-scope-allowlist.json` (JSON object mapping service -> allowed address prefixes) and load it from `scripts/lab/pve-service-deploy`
- [X] T002 Implement profile-specific evidence requirements for `profile_id=service-deploy` in `scripts/lab/verify_evidence.py` (enforce required inputs like plan txt/json, blast-radius, preflight, and healthcheck; and ensure the verifier produces `reports/verify.json` rather than requiring it as a pre-existing input)
- [X] T003 [P] Add new check IDs for service-deploy gating/evidence (blast radius, mount validation, state-backup proof) in `scripts/lab/checks.d/catalog.json`
- [X] T004 [P] Extend/refresh evidence fixtures to cover new required artifacts in `scripts/lab/fixtures/evidence-packs/` (add one valid + one invalid fixture)

**Checkpoint**: Offline verification (`scripts/lab/ci-verify.sh`) can enforce Spec 023 evidence requirements.

---

## Phase 1: User Story 1 — Orchestrator Policy + Evidence (Priority: P1) 🎯 MVP

**Goal**: The PVE orchestrator enforces full-plan-only, service scoping, and “no host-path bind mounts”, and emits blast-radius + evidence artifacts.

**Independent Test**:
- Running `./scripts/lab/pve-service-deploy plan --environment lab --service jellyfin`:
  - fails if any `-target` is attempted
  - fails if plan changes resources outside the service allowlist
  - fails if plan includes host-path bind mounts (`mpX` sourcing from raw host paths)
  - produces evidence that passes `./scripts/lab/ci-verify.sh <pack>`

### Implementation

- [X] T005 [US1] Enforce “no `-target`” by detecting target usage and failing with actionable remediation in `scripts/lab/pve-service-deploy`
- [X] T006 [US1] Standardize Terraform state path at `/var/lib/homelab-proxmox/state/services/<service>/terraform.tfstate` in `scripts/lab/pve-service-deploy`
- [X] T007 [US1] Implement post-apply state backup to Synology (LAB and PROD) using `scripts/backup_tfstate.sh` (updated to accept a state path) and capture proof into evidence in `scripts/lab/pve-service-deploy`
- [X] T008 [US1] Define + implement deterministic RUN_ID format (e.g. `${ENV}-${SERVICE}-${GIT_SHA:0:8}-${UTC_TS}`) in `scripts/lab/pve-service-deploy`
- [X] T009 [US1] Extend plan evidence output to always include plan text + plan json in `scripts/lab/pve-service-deploy`
- [X] T010 [US1] Implement enhanced service scope guard by parsing `terraform show -json` and failing on out-of-scope resources in `scripts/lab/pve-service-deploy`
- [X] T011 [US1] Implement bind-mount policy guard by scanning plan json for `mp0/mp1/...` and failing if any mountpoint source begins with `/` (host filesystem path) in `scripts/lab/pve-service-deploy`
- [X] T012 [US1] Compute blast-radius summary (create/update/replace/destroy + resource list) and emit `blast-radius.json` in `scripts/lab/pve-service-deploy`
- [X] T013 [US1] Emit preflight results (including guard failures) in `preflight.txt` and reference them via checks in `scripts/lab/pve-service-deploy`
- [X] T027 [US1] Implement LAB idempotency verification in `scripts/lab/pve-service-deploy apply` (perform a second apply and fail if it is not a no-op; record the result into evidence)

**Checkpoint**: Plan runs are policy-safe and produce enforceable evidence.

---

## Phase 2: User Story 2 — Workflow Destructive Gating (Priority: P2)

**Goal**: GitHub Actions requires explicit confirmations when blast radius is destructive (replace/destroy), and never permits `-target`.

**Independent Test**:
- LAB dispatch with a destructive plan fails unless `confirm_destructive=apply-lab-destructive`.
- PROD dispatch fails unless `confirm=deploy-prod` and, when destructive, `confirm_destructive=deploy-prod-destructive`.

### Implementation

- [X] T014 [US2] Add `confirm_destructive` workflow input and wire it through job env/steps in `.github/workflows/lxc-deploy.yml`
- [X] T015 [US2] Update workflow gating logic to require destructive confirm strings based on emitted evidence (`blast-radius.json`) in `.github/workflows/lxc-deploy.yml`
- [X] T016 [US2] Ensure workflow never passes `-target` and fails fast if any target-like input is present in `.github/workflows/lxc-deploy.yml`
- [X] T017 [US2] Ensure evidence is fetched and verified offline before marking plan/apply success in `.github/workflows/lxc-deploy.yml`
- [X] T018 [US2] Ensure least-privilege smoke checks remain mandatory for plan/apply jobs (non-root remote user; deny sudo shell escalation) in `.github/workflows/lxc-deploy.yml`

**Checkpoint**: Destructive changes require explicit operator intent.

---

## Phase 3: User Story 3 — In-Guest Shared NFS Mount + Jellyfin Health Evidence (Priority: P3)

**Goal**: Shared media NFS is mounted inside containers at `/media/video` (read-only) via Ansible, and healthchecks prove it.

**Independent Test**:
- After LAB apply, `/media/video` is mounted RO inside the Jellyfin container and the healthcheck passes.

### Implementation

- [X] T019 [P] [US3] Create shared NFS mount role scaffold in `ansible/roles/shared_nfs_mount/{tasks,defaults,handlers}/`
- [X] T020 [US3] Implement NFS client install + fstab/systemd automount for `192.168.1.109:/volume1/video` → `/media/video` (RO) in `ansible/roles/shared_nfs_mount/tasks/main.yml`
- [X] T021 [P] [US3] Add role defaults (server/export/options) in `ansible/roles/shared_nfs_mount/defaults/main.yml`
- [X] T022 [US3] Wire `shared_nfs_mount` into Jellyfin playbook/role in `ansible/playbooks/jellyfin.yml` and/or `ansible/roles/jellyfin/tasks/main.yml`
- [X] T023 [US3] Extend healthcheck to validate `/media/video` exists and is mounted read-only, and write output to evidence in `scripts/healthcheck/jellyfin.sh` and `scripts/lab/pve-service-deploy`
- [X] T024 [US3] Capture `findmnt`/`mount` evidence from inside the container (or via Ansible) into the evidence pack in `scripts/lab/pve-service-deploy`
- [X] T029 [US3] Emit `reports/assertions.workload.json` for mount validation using `ansible/roles/assertion_utils/tasks/generate_report.yml` (requires `evidence_dir`, `run_id`, `profile_id`, and `phase=workload`)

**Checkpoint**: Media mount no longer depends on host-path binds or root tokens.

---

## Phase 4: Polish & Cross-Cutting Concerns

- [X] T025 [P] Update runbook to reflect Spec 023 behavior (no host binds, destructive gating, evidence contents, state backup) in `docs/operations/lxc-deploy-ci.md`
- [X] T026 [P] Add/refresh operator notes on shared media mounts and ownership expectations in `docs/operations/jellyfin-media-mount.md`

---

## Dependencies & Execution Order

- Phase 2 blocks everything (verifier + catalog + fixtures).
- US1 (Phase 3) should be implemented before US2/US3 so workflow and Ansible changes can rely on the new evidence artifacts.

## Parallel Opportunities

- T003 + T004 can be done in parallel with each other.
- US3 role scaffolding (T019, T021) can be parallelized.
- Docs tasks (T025–T026) can be done in parallel with implementation once behavior stabilizes.
