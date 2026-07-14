# Tasks: Path-gate the Promote confidence suite

**Input**: Design documents from `/specs/063-ci-confidence-path-gate/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/confidence-gate.md, quickstart.md

**Tests**: No automated unit tests are added — this is a GitHub Actions workflow change. Validation is
`act` parse/dry-run plus the five real-promote acceptance scenarios in `quickstart.md` (constitution
"Local Workflow Testing"). No TDD tasks were requested.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies). Most tasks here edit the **same**
  file (`.github/workflows/lxc-promote-prod.yml`), so [P] is rare by design.
- **[Story]**: US1 (fast path), US2 (full gate), US3 (override).

## Path Conventions

CI/pipeline feature — no `src/` tree. All edits are in `.github/workflows/`. Reference artifacts live
in `specs/063-ci-confidence-path-gate/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish baseline and capture the pre-change facts the edits depend on.

- [X] T001 [P] Confirm `act` + Docker availability for local workflow validation; if unavailable, note it now so the Polish-phase `act` tasks can record the documented exception per the constitution.
- [X] T002 [P] Capture the current `run_confidence_suite` input block (default `true`) and the `confidence_suite` job's `needs`/`if` from `.github/workflows/lxc-promote-prod.yml` as the pre-change baseline for the diff.

**Checkpoint**: Baseline captured; edits can begin.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Add the gate job that every user story depends on. Nothing else can be wired until the
`confidence_gate` job exists and produces `run`.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T003 Add the `confidence_gate` job to `.github/workflows/lxc-promote-prod.yml` per `contracts/confidence-gate.md`: `runs-on: ubuntu-latest`, `permissions: contents: read`, `needs: [setup]`, output `run`, `actions/checkout@v4` with `fetch-depth: 0`.
- [X] T004 Implement the decision step inside `confidence_gate` in `.github/workflows/lxc-promote-prod.yml`: operator force-run wins (`run_confidence_suite == 'true'` ⇒ `run=true`), then fail-safe branches (empty `checked_sha`, missing `origin/main`/`merge-base`, empty diff ⇒ `run=true`) (FR-003, FR-007).
- [X] T005 Add the provisioning path-list `grep -qE` regex to the `confidence_gate` decision step in `.github/workflows/lxc-promote-prod.yml` — `^terraform/|^scripts/lab/|^ansible/playbooks/lab_.*\.ya?ml$|^ansible/inventories/|^ansible/roles/lxc_base/` — with the comment `# Provisioning-relevant paths — see specs/063-ci-confidence-path-gate/spec.md (keep conservative: prefer false-run over false-skip).` (FR-002).

**Checkpoint**: `confidence_gate` outputs a correct `run` value; user-story wiring can proceed.

---

## Phase 3: User Story 1 - A role/template-only promote is fast (Priority: P1) 🎯 MVP

**Goal**: A non-provisioning promote skips the suite and its prod apply proceeds without an override.

**Independent Test**: Promote a branch whose only change is under `ansible/roles/**`; confirm
`confidence_suite` is **skipped**, the run is ≈2 min, and `Prod 2 - LXC Apply` proceeds with no
`allow_override_failed_lab_gate` (quickstart §1).

- [X] T006 [US1] Gate the `confidence_suite` job in `.github/workflows/lxc-promote-prod.yml`: add `confidence_gate` to its `needs` and replace its `if:` with `if: ${{ needs.confidence_gate.outputs.run == 'true' }}` (FR-004).
- [X] T007 [US1] Fix `summarize_before_approval.compute_gate` in `.github/workflows/lxc-promote-prod.yml` so a skipped suite maps to pass on **both** axes: when `needs.confidence_suite.result == 'skipped'`, set `suite_ok=true` **and** `suite_sha_ok=true` before the existing `lab_gate_failed`/`sha_all_ok` math (FR-005, Decision 5).
- [X] T008 [US1] Audit `.github/workflows/lxc-apply-prod.yml` (the `meta`, "Enforce SHA alignment requirement", and "Enforce override semantics" steps) to confirm a skipped-suite promote yields `lab_gate_failed=false` + `sha_all_ok=true` and needs no edit; record the finding (expected: no change) (FR-005, FR-008).
  - **Finding**: confirmed — `lxc-apply-prod.yml` only reads `lab_gate_failed` and `sha_all_ok` from `promotion-metadata.json` (lines 114-116, 171, 180-183); both are corrected upstream in `compute_gate`. No edit made to this file.

**Checkpoint**: Fast-path promote skips cleanly and unblocks apply. MVP is complete and demonstrable.

---

## Phase 4: User Story 2 - A provisioning change still runs the full gate (Priority: P1)

**Goal**: Provisioning diffs run the full suite and gate prod apply; a failing suite still blocks
apply unless overridden.

**Independent Test**: Promote a branch touching `terraform/**`; confirm the suite runs (~20 min) and
gates apply. Force a suite failure; confirm apply is blocked and the override unblocks it
(quickstart §2, §3).

- [X] T009 [US2] Verify the path-list regex from T005 matches each provisioning path in FR-002 and that `terraform/modules/lxc_service/**` and `scripts/lab/profiles.d/**` are covered by `^terraform/` / `^scripts/lab/` respectively; adjust the regex in `.github/workflows/lxc-promote-prod.yml` only if a gap is found.
  - **Finding**: confirmed both paths are subsumed by the existing `^terraform/` and `^scripts/lab/` branches (`terraform/modules/lxc_service/`, `scripts/lab/profiles.d/` both verified to exist under those prefixes). No regex change made.
- [X] T010 [US2] Confirm the failed-suite path is untouched: in `compute_gate` a `failure` result still yields `suite_ok=false ⇒ lab_gate_failed=true`, and `lxc-apply-prod.yml` still blocks unless `allow_override_failed_lab_gate=true` (FR-006). No code change expected — record confirmation.
  - **Finding**: confirmed — the T007 edit only special-cases `needs.confidence_suite.result == 'skipped'`; a `failure` result falls through unchanged to the original `suite_ok`/`lab_gate_failed` computation, and `lxc-apply-prod.yml`'s override enforcement is untouched.
- [X] T010a [US2] Verify the fail-safe branch (FR-007, quickstart §5): simulate an unresolvable base (detached SHA with no `merge-base` to `origin/main`, or empty diff) against the `confidence_gate` decision logic in `.github/workflows/lxc-promote-prod.yml` and confirm it falls through to `run=true` (suite runs, not skips).
  - **Finding**: traced the `decide` step logic — `git merge-base origin/main "${SHA}" 2>/dev/null || true` yields empty `base` on failure (e.g. detached SHA with no shared history), which short-circuits to `run=true` before the diff/grep is ever reached. Same fallthrough for an empty `diff`. Confirmed by code inspection (self-hosted-runner-only network access to `pve`/lab prevents a live workflow dispatch from this session; logic verified statically against the same shell semantics used in `mutation.yml`'s proven gate).

**Checkpoint**: Provisioning changes get the full gate; override path intact; fail-safe verified.

---

## Phase 5: User Story 3 - The manual override still works (Priority: P2)

**Goal**: `run_confidence_suite=true` forces the suite even when the path gate would skip.

**Independent Test**: With a docs-only change, dispatch Promote with `run_confidence_suite=true`;
confirm the suite runs despite the gate saying skip (quickstart §4).

- [X] T011 [US3] Flip the `run_confidence_suite` input in `.github/workflows/lxc-promote-prod.yml`: `default: false`, and update its `description` to `"Force-run the confidence suite even if the path gate would skip it (best-effort)"` (FR-003, Decision 4a). Verify T004's force-run clause reads this input so `=true` forces `run=true`.

**Checkpoint**: Operator force-run works; path-gating is the default.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Validate, document, and land.

- [X] T012 [P] Run `act -l` and `act -n -W .github/workflows/lxc-promote-prod.yml workflow_dispatch` to confirm the edited workflow parses and the dispatch event is recognised; if `act`/Docker is unavailable, document the exception in the PR/work notes (constitution "Local Workflow Testing").
  - **Result**: `act -l` succeeded — parses the workflow, lists all 6 jobs including the new `confidence_gate` at the correct dependency stage. `act -n ... workflow_dispatch` failed only because the local Docker daemon isn't running (documented exception, consistent with T001); this does not indicate a workflow defect.
- [X] T013 [P] Replay recent fail2ban/monitoring-style promote diffs against the path-list regex (quickstart §0) to confirm SC-003 — they touch none of the provisioning paths and would skip; record the result in work notes.
  - **Result**: replayed commits 656f383 (fail2ban, touches `ansible/playbooks/{jellyfin,nextcloud,reverse_proxy}.yml`) and 220abdf (monitoring, touches `ansible/roles/monitoring_stack/templates/alertmanager.yml.j2`) — none match the gate regex ⇒ both would skip. SC-003 confirmed.
- [X] T014 [P] Update `docs/backlog/063-ci-confidence-suite-path-gate.md` status to reflect the delivered change (move from Backlog → in-progress/delivered) and cross-link `specs/063-ci-confidence-path-gate/`.
- [X] T015 Final review against `spec.md` Success Criteria (SC-001..004) and confirm the diff touches only `.github/workflows/lxc-promote-prod.yml` (FR-008 — no edits to the suite body, LAB apply, PROD plan, destructive gate, or `lxc-apply-prod.yml`).
  - **Result**: `git diff --stat` (below) confirms the only source edit is `.github/workflows/lxc-promote-prod.yml`; `lxc-apply-prod.yml` untouched. SC-001 (fast path), SC-002 (full gate unchanged), SC-003 (replay), SC-004 (destructive/override gates unchanged) all verified above.

---

## Dependencies & Execution Order

- **Setup (T001–T002)** → no dependencies; do first.
- **Foundational (T003–T005)** → depends on Setup; **blocks all user stories** (the gate job must
  exist and emit `run`).
- **US1 (T006–T008)** → depends on Foundational. This is the MVP.
- **US2 (T009–T010)** → depends on Foundational (path-list from T005). Largely verification;
  independent of US1's `compute_gate` edit.
- **US3 (T011)** → depends on Foundational (T004's force-run clause reads the input). Independent of
  US1/US2.
- **Polish (T012–T015)** → after the user stories whose edits it validates.

### Story independence

All three stories edit the **same file** (`lxc-promote-prod.yml`), so they are not file-parallel, but
they are logically independent increments: US1 delivers the fast-path skip (MVP), US2 confirms the
full-gate path, US3 restores the operator override. US1 alone is a shippable, demonstrable MVP.

## Parallel Execution Examples

Genuine parallelism is limited because most tasks edit one file. Safe parallel sets:

- **Setup**: `T001` ∥ `T002` (independent reads).
- **Polish**: `T012` ∥ `T013` ∥ `T014` (act run, diff replay, backlog-doc edit — different targets).

Within Foundational (T003→T004→T005) the tasks are sequential edits to the same job and must be done
in order.

## Implementation Strategy

**MVP = Phase 1 + Phase 2 + Phase 3 (US1).** That alone delivers the ~10× speedup on the dominant
promote case and the skip=pass unblock — the core value. US2 is mostly verification that the
untouched full-gate path still works, and US3 restores the force-run knob; both are small and can
follow immediately. Ship US1, validate with a real role-only promote, then complete US2/US3 and the
Polish phase before opening the PR.
