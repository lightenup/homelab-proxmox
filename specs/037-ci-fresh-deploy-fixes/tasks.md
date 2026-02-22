# Tasks: CI Fresh-Deploy Pipeline Fixes

**Input**: Design documents from `/specs/037-ci-fresh-deploy-fixes/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, quickstart.md ✅, contracts/ ✅

**Tests**: Evidence-artifact contract tests are included per plan.md Step 5 (spec FR-017 mandates evidence artifacts following the established Tier 2 evidence-pack pattern).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Summary

- **Total tasks**: 7
- **Estimated complexity**: Medium
- **Parallel tracks**: 2 independent tracks identified (T002 + T003 + T006 after T001; T004 + T005 in parallel after T002 + T003)

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files or logically independent, no dependency on an incomplete task)
- **[Story]**: Which user story this task belongs to (US1–US5)
- Exact file paths are included in all task descriptions

## File Manifest

**Modified**:
- `scripts/lab/pve-service-deploy`

**Created**:
- `python/tests/orchestrator/test_deploy_readiness.py`

---

## Phase 1: Setup (Shared Infrastructure)

*No setup tasks required.* The orchestrator script (`scripts/lab/pve-service-deploy`) and the Python test harness (`python/tests/`) already exist. No new dependencies or project scaffolding are needed.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Reorder `cmd_apply()` so CTID extraction executes *before* the SSH wait loop, enabling `pct exec`-based pre-SSH operations. This is the critical structural change that all user story tasks depend on.

**⚠️ CRITICAL**: No user story implementation can begin until this phase is complete.

- [X] T001 Reorder `cmd_apply()` in `scripts/lab/pve-service-deploy` — move the CTID extraction block (lines ~1650–1708: `local ctid=""` through the `ctid_report` write) and the DNS check block (lines ~1710–1760: `dns_report` through `pct reboot`) to execute after `service_ip` extraction and before the stale host key cleanup + SSH wait loop, as specified in plan.md Step 0; verify neither moved block contains an SSH dependency (CTID extraction reads Terraform state only; DNS check uses `pct exec` and `pct config` — both are Tier 2, not SSH)
  - **Type**: modify | **Plan step**: Step 0 | **Depends on**: None | **Parallel-safe**: No

**Checkpoint**: `shellcheck scripts/lab/pve-service-deploy` exits 0 with no new warnings. In the modified `cmd_apply()`, the CTID extraction block (`local ctid=`) appears before the SSH wait loop line (`ssh_wait_seconds`).

---

## Phase 3: User Story 1 — CI Deploys Fresh Container with Working SSH Access (P1) 🎯 MVP

**Goal**: Inject the orchestrator's deploy SSH key (`id_lxc_deploy.pub`) into the container's `/root/.ssh/authorized_keys` via `pct exec` after Terraform apply and before the SSH wait loop, so that fresh LXC container deploys succeed without manual key injection.

**Independent Test**: Trigger "Lab 1 — LXC Promote" for `nextcloud` (no pre-existing container). The pipeline must complete through the SSH wait step without manual key injection. The evidence pack must contain `reports/apply/lxc-deploy-key.txt` with `action=injected`.

- [X] T002 [US1] Add `inject_deploy_key()` bash function to `scripts/lab/pve-service-deploy` implementing all of the following: (1) validate `${lxc_key_file}.pub` exists or `die` with a named error message per FR-016; (2) check container is running via `sudo pct status "${ctid}"` or `die` per FR-015; (3) read public key content from the file; (4) compute key fingerprint via `ssh-keygen -lf`; (5) capture `authorized_keys_line_count_before` via `pct exec`; (6) run `sudo pct exec "${ctid}" -- bash -c '...'` to `mkdir -p /root/.ssh && chmod 700 /root/.ssh && touch /root/.ssh/authorized_keys && chmod 600 /root/.ssh/authorized_keys` per FR-005; (7) append key idempotently via `grep -qF "${key_content}" /root/.ssh/authorized_keys || echo "${key_content}" >> /root/.ssh/authorized_keys` per FR-003, FR-004; (8) capture `authorized_keys_line_count_after` and determine action (`injected` or `skipped`) from the `grep` exit code; (9) write evidence to `${EVIDENCE_ROOT}/reports/apply/lxc-deploy-key.txt` with fields `ctid`, `key_file`, `key_fingerprint`, `action`, `authorized_keys_line_count_before`, `authorized_keys_line_count_after` per data-model.md FR-017; (10) log action to stdout per FR-011
  - **Type**: modify | **Plan step**: Step 1 | **Depends on**: T001 | **Parallel-safe**: No (same file as T003)

**Checkpoint**: `shellcheck scripts/lab/pve-service-deploy` exits 0. `grep -n "^inject_deploy_key()" scripts/lab/pve-service-deploy` returns a match showing the function definition. Function body contains: `grep -qF` idempotency check, `pct status` running guard, `pct exec` to create `.ssh/` directory with mode 700 and `authorized_keys` with mode 600, and evidence write to `lxc-deploy-key.txt`.

---

## Phase 4: User Story 2 — Network Failures Produce Actionable Diagnostics (P1)

**Goal**: Add a hard-gate network reachability check (`ping -c 1 -W 5`) between deploy key injection and the SSH wait loop. On failure, capture container interface diagnostics via `pct exec` and write them to evidence, then `die` immediately — never proceeding to the SSH wait loop.

**Independent Test**: Deploy a container whose IP is not reachable from PVE. The pipeline must fail within 30 seconds with output showing container interface state and routing table. The evidence pack must contain `reports/apply/network-check.txt` with `ping_status=unreachable` and all three diagnostic section headers.

- [X] T003 [US2] Add `check_network_reachability()` bash function to `scripts/lab/pve-service-deploy` implementing all of the following: (1) write evidence header (`ctid=`, `expected_ip=`, `timestamp=`) to `${EVIDENCE_ROOT}/reports/apply/network-check.txt`; (2) execute `ping -c 1 -W 5 "${service_ip}"`; (3) on success: append `ping_status=ok` to evidence and return 0 per FR-009; (4) on failure: capture `sudo pct exec "${ctid}" -- ip addr show eth0` (with `|| true` fallback), `sudo pct exec "${ctid}" -- ip route` (with `|| true` fallback), and `sudo pct config "${ctid}" | grep -E '^net[0-9]+:'` (host-side); (5) write all diagnostics to evidence file under section headers `--- ip addr show eth0 ---`, `--- ip route ---`, `--- pct config net ---` and to stderr per FR-007, FR-012; (6) emit actionable error message naming the unreachable IP and the evidence file path, return 1 per FR-008; `ping_status=unreachable` is written to evidence on failure
  - **Type**: modify | **Plan step**: Step 2 | **Depends on**: T001 | **Parallel-safe**: No (same file as T002)

**Checkpoint**: `shellcheck scripts/lab/pve-service-deploy` exits 0. `grep -n "^check_network_reachability()" scripts/lab/pve-service-deploy` returns a match. Function body contains: `ping -c 1 -W 5`, `ping_status=ok`, `ping_status=unreachable`, and all three section header strings (`--- ip addr show eth0 ---`, `--- ip route ---`, `--- pct config net ---`).

---

## Phase 5: User Story 3 — Existing Services Are Not Disrupted (P1)

**Goal**: Wire both new functions into `cmd_apply()` at the correct insertion point, and validate the evidence artifact schemas with contract tests — ensuring deploy key injection and network check are safe, idempotent no-ops for existing deployed services.

**Independent Test**: Run `pve-service-deploy apply --environment lab --service jellyfin` (existing service with working SSH). Pipeline completes identically to before this change: `lxc-deploy-key.txt` shows `action=skipped`, `network-check.txt` shows `ping_status=ok`, SSH connectivity unchanged. `python3 -m pytest python/tests/orchestrator/test_deploy_readiness.py -v` passes all 5 tests.

- [X] T004 [US3] Wire `inject_deploy_key "${ctid}" "${lxc_key_file}"` and `check_network_reachability "${ctid:-}" "${service_ip}"` calls into `cmd_apply()` in `scripts/lab/pve-service-deploy`, inserted after the DNS check block (moved per T001) and before the stale host key cleanup (`ssh-keygen -R`) + SSH wait loop; guard the key injection call with `if [[ -n "${ctid}" ]]; then … fi` following the existing feature-flag and bind-mount guard pattern; network reachability check runs unconditionally (uses ping only; CTID-dependent diagnostics in `check_network_reachability` use `|| true` fallback per plan.md Step 3
  - **Type**: modify | **Plan step**: Step 3 | **Depends on**: T001, T002, T003 | **Parallel-safe**: No (same file)

- [X] T005 [P] [US3] Create `python/tests/orchestrator/test_deploy_readiness.py` with 5 pytest test functions using inline string fixtures following the `_SIMPLE_TFVARS` pattern in `test_tfvars_mountpoints.py` — no live containers, no mocking of `pct`/`ping`; tests: `test_deploy_key_evidence_format` (assert all fields `ctid`, `key_file`, `key_fingerprint`, `action`, `authorized_keys_line_count_before`, `authorized_keys_line_count_after` present per data-model.md), `test_deploy_key_evidence_action_values` (assert `action=injected` accepted, `action=skipped` accepted, unknown value rejected), `test_network_check_evidence_format_ok` (assert `ping_status=ok` present, no diagnostic section headers present), `test_network_check_evidence_format_unreachable` (assert `ping_status=unreachable` present and all three section headers `--- ip addr show eth0 ---`, `--- ip route ---`, `--- pct config net ---` present), `test_network_check_evidence_ping_status_values` (assert `ok` and `unreachable` accepted, unknown value rejected) per plan.md Step 5
  - **Type**: create | **Plan step**: Step 5 | **Depends on**: T002, T003 | **Parallel-safe**: Yes (different file)

**Checkpoint**: `shellcheck scripts/lab/pve-service-deploy` exits 0. `grep -n "inject_deploy_key\|check_network_reachability" scripts/lab/pve-service-deploy` shows both function calls in the `cmd_apply()` body (not just definitions). `python3 -m pytest python/tests/orchestrator/test_deploy_readiness.py -v` exits 0 with exactly 5 tests collected and passed.

---

## Phase 6: User Story 4 — Laptop Deploy Has Parity with CI (P2)

**Goal**: Dual-provisioning parity between CI and laptop runs. Since `pve-service-deploy apply` is the single entrypoint for both CI (GitHub Actions runner) and laptop deploys (direct script invocation), parity is inherently achieved by T002–T004: both paths call `inject_deploy_key()` and `check_network_reachability()` identically (FR-010).

**Independent Test**: Run `SSH_WAIT_SECONDS=30 ./scripts/lab/pve-service-deploy apply --environment lab --service jellyfin` from a developer laptop. Deploy key injection log and network check log match the output from a CI run for the same service.

*(No implementation tasks — US4 is fully satisfied by T002, T003, and T004. The dual-provisioning parity is structural: one entrypoint, one code path, identical behaviour in both CI and laptop contexts.)*

---

## Phase 7: User Story 5 — Reduced SSH Wait Timeout (P3)

**Goal**: Reduce the SSH wait loop default from 300 seconds to 120 seconds. With the network reachability pre-check (US2) in place, the SSH wait loop only needs to cover sshd startup time — 120 seconds is generous for Debian LXC. The `SSH_WAIT_SECONDS` env var override is preserved.

**Independent Test**: `grep "SSH_WAIT_SECONDS" scripts/lab/pve-service-deploy` shows `:-120` (not `:-300`) for all SSH wait loop defaults. Running with `SSH_WAIT_SECONDS=60 pve-service-deploy apply …` uses 60 seconds instead, confirming the override is respected.

- [X] T006 [P] [US5] Change the SSH wait loop default in `scripts/lab/pve-service-deploy` from `SSH_WAIT_SECONDS:-300` to `SSH_WAIT_SECONDS:-120`; audit all occurrences of `SSH_WAIT_SECONDS` in the file (including the bind mount reboot wait at line ~2277) and update any that use `:-300` to `:-120`; the env var override pattern must remain intact per FR-013, plan.md Step 4
  - **Type**: modify | **Plan step**: Step 4 | **Depends on**: None | **Parallel-safe**: Yes (independent line change)

**Checkpoint**: `grep "SSH_WAIT_SECONDS" scripts/lab/pve-service-deploy` shows zero occurrences of `:-300`. At least one occurrence of `:-120` is present. `shellcheck scripts/lab/pve-service-deploy` exits 0.

---

## Phase N: Polish & Cross-Cutting Concerns

**Purpose**: Final regression gate — verify no pre-existing tests are broken and no new ShellCheck warnings are introduced by any of the changes above.

- [X] T007 Run the full test suite and ShellCheck against `scripts/lab/pve-service-deploy`: (1) `shellcheck scripts/lab/pve-service-deploy` — exits 0, no new warnings or errors compared to baseline; (2) `python3 -m pytest python/tests/` — all tests pass including new `test_deploy_readiness.py`; (3) confirm `test_orchestrator_unit.py`, `test_runner_plan_apply.py`, and `test_evidence.py` in `python/tests/orchestrator/` still pass with no regressions per plan.md Step 6
  - **Type**: test | **Plan step**: Step 6 | **Depends on**: T004, T005, T006 | **Parallel-safe**: No (final gate)

**Checkpoint**: All three commands exit with code 0. `python3 -m pytest python/tests/ -v` output shows no failures; total collected count is exactly 5 more tests than before this feature (the 5 new tests in `test_deploy_readiness.py`).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundational (Phase 2)**: No dependencies — can start immediately
- **US1 (Phase 3)**: Depends on Phase 2 (T001)
- **US2 (Phase 4)**: Depends on Phase 2 (T001)
- **US3 (Phase 5)**: Depends on US1 (T002) AND US2 (T003)
- **US4 (Phase 6)**: Satisfied by T002–T004; no new dependencies
- **US5 (Phase 7)**: No dependencies — can start anytime (fully independent)
- **Polish (Phase N)**: Depends on T004, T005, T006

### User Story Dependencies

- **US1 (P1)**: Can start after Phase 2 — no dependency on US2
- **US2 (P1)**: Can start after Phase 2 — no dependency on US1
- **US3 (P1)**: Depends on US1 (T002) and US2 (T003) both complete
- **US4 (P2)**: No implementation tasks; satisfied by US1 + US2 + US3
- **US5 (P3)**: No dependencies — independent of all user stories

### Within Each User Story

- Foundational reordering (T001) before any function implementation
- Function definitions (T002, T003) before wiring (T004)
- Wiring (T004) and contract tests (T005) can proceed in parallel
- Lint + test gate (T007) is always last

### Task Dependency Table

| Task | Depends On | Parallel-Safe |
|------|------------|---------------|
| T001 | None | No |
| T002 | T001 | No (same file as T003) |
| T003 | T001 | No (same file as T002) |
| T004 | T001, T002, T003 | No (same file) |
| T005 | T002, T003 | Yes (different file) |
| T006 | None | Yes (independent line change) |
| T007 | T004, T005, T006 | No (final gate) |

---

## Dependency Graph

```
T001 → T002 ─┬→ T004 ─→ T007
              └→ T005 ─→ T007
T001 → T003 ─┤
              └→ T004
              └→ T005
T006 ─────────────────→ T007
```

---

## Implementation Order

1. **T001** — Reorder `cmd_apply()` (no dependencies; foundational for all)
2. **T002, T003, T006** — After T001: write `inject_deploy_key()`, write `check_network_reachability()`, and change SSH timeout (T006 is fully independent and can be done at any point)
3. **T004, T005** — After T002 + T003: wire both calls into `cmd_apply()` (T004) AND create contract tests (T005) in parallel
4. **T007** — Final gate: run ShellCheck + full pytest suite

---

## Parallel Example: US3 (Wire + Contract Tests)

```bash
# After T002 and T003 are complete, launch in parallel:
Task: "Wire inject_deploy_key() and check_network_reachability() calls into cmd_apply() in scripts/lab/pve-service-deploy"
Task: "Create python/tests/orchestrator/test_deploy_readiness.py with 5 contract test functions"
```

---

## Implementation Strategy

### MVP First (US1 + US2 + US3 Core)

1. Complete Phase 2: T001 — Foundational reordering
2. Complete Phase 3: T002 — `inject_deploy_key()` function
3. Complete Phase 4: T003 — `check_network_reachability()` function
4. Complete Phase 5 core: T004 — Wire both into `cmd_apply()`
5. **STOP and VALIDATE**: `shellcheck scripts/lab/pve-service-deploy` passes; trigger CI pipeline for `nextcloud` (SC-001) and `jellyfin` (SC-003)
6. Complete remaining: T005, T006, T007

### Incremental Delivery

1. T001 → Foundation ready (CTID extraction before SSH wait)
2. T002 + T003 → Functions implemented and ShellCheck-clean
3. T004 → Both functions wired in → SC-001 (fresh deploy) and SC-002 (fast network failure) achievable
4. T005 → Evidence contracts verified → SC-003 (no regressions), SC-005 (idempotency)
5. T006 → SSH timeout reduced → SC-002 further improved
6. T007 → Regression gate cleared → ready to merge

### Single-Developer Strategy

Execute tasks sequentially: T001 → T002 → T003 → T004 → T005 → T006 → T007. All tasks touch `scripts/lab/pve-service-deploy` except T005 (`test_deploy_readiness.py`). Run `shellcheck scripts/lab/pve-service-deploy` after each task that modifies the script.

---

## Notes

- The [P] marker on T002, T003, T005, T006 indicates logical independence, not necessarily simultaneous file editing. A single developer should execute them sequentially but they carry no logic dependency on each other.
- `shellcheck` is the primary lint gate for all bash changes; run it after every task that touches `scripts/lab/pve-service-deploy`.
- Evidence artifact field names and allowed values are canonical in `specs/037-ci-fresh-deploy-fixes/data-model.md` — use it as the source of truth when implementing T002, T003, and T005.
- The `EVIDENCE_ROOT` variable is already defined in the orchestrator — follow existing patterns (e.g., `lxc-features.txt`, `lxc-mountpoints.txt`) for evidence file path construction.
- No Terraform files, Ansible roles, GitHub Actions workflow YAML, or `.tfvars` files are modified — the blast radius is strictly limited to the two files in the File Manifest above.
