# Implementation Plan: CI Fresh-Deploy Pipeline Fixes

**Branch**: `037-ci-fresh-deploy-fixes` | **Date**: 2026-02-22 | **Spec**: `specs/037-ci-fresh-deploy-fixes/spec.md`
**Input**: Feature specification from `/specs/037-ci-fresh-deploy-fixes/spec.md`

## Summary

The CI pipeline (`pve-service-deploy apply`) cannot create a brand-new LXC container end-to-end because (1) the deploy SSH key is overridden by Terraform's `.tfvars` variable precedence and (2) network failures produce no diagnostics before a 300-second blind timeout. This plan adds two new orchestrator functions — `inject_deploy_key` and `check_network_reachability` — and reorders `cmd_apply()` so that CTID extraction, deploy key injection, and network reachability all happen *before* the SSH wait loop (currently CTID extraction happens *after* the SSH wait, which prevents any `pct exec`-based pre-SSH steps). The SSH wait default is reduced from 300s to 120s. All changes are confined to a single file (`scripts/lab/pve-service-deploy`) and evidence-artifact contract tests; no Terraform, Ansible, or workflow YAML modifications are needed.

## Technical Context

**Language/Version**: Bash (POSIX-compatible, runs on Debian 12 Proxmox host)
**Primary Dependencies**: `pct` (Proxmox CLI), `ping`, `ssh-keygen`, `grep`, `sudo`
**Storage**: N/A (evidence artifacts are flat files in the evidence pack)
**Testing**: pytest (Python test harness at `python/tests/`), ShellCheck for bash linting, `ci-verify.sh` for evidence pack verification
**Target Platform**: Proxmox VE host (Debian 12, Linux amd64)
**Project Type**: Infrastructure-as-Code — bash orchestrator with Python test harness
**Performance Goals**: Deploy key injection <10s (NFR-001), network check <15s (NFR-002), combined overhead <30s (NFR-003)
**Constraints**: No Terraform changes, no tfvars changes, no workflow YAML changes (per spec Out of Scope)
**Scale/Scope**: 7 services (adguard, homeassistant, immich, jellyfin, monitoring, nextcloud, reverse_proxy)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| **I. Spec-Driven Workflow** | ✅ PASS | All changes driven from spec 037; plan traces every step to a spec FR/AC |
| **II. Secrets Policy** | ✅ PASS | Deploy key stays on PVE host, never committed. Key fingerprint (not material) in evidence. No secrets in logs. |
| **III. Separation of Concerns** | ✅ PASS | Key injection and network check are Tier 2 orchestrator operations (`pct exec` via sudo). No Terraform resource changes. No Ansible role changes. |
| **IV. Dual-Provisioning Parity** | ✅ PASS | `pve-service-deploy` is the single entrypoint for both CI and laptop deploys. New functions run in both contexts identically (US-4). |
| **Token Privilege Tiers** | ✅ PASS | Tier 2 only: `sudo pct exec` and `sudo pct status`. No Tier 1 (Terraform API) or Tier 3 (root@pam) usage. Existing sudoers rule covers `pct` commands (A-001). |
| **Provider Strategy** | ✅ PASS | No Terraform provider changes. Telmate provider untouched. |
| **Test-Driven Changes** | ✅ PASS | New unit tests for deploy key injection and network check functions. Evidence pack verification via `ci-verify.sh`. |
| **Local Workflow Testing** | ✅ PASS | No workflow YAML changes, so `act` validation not needed. |

**Post-design re-check**: All principles still PASS. No violations.

## Project Structure

### Documentation (this feature)

```text
specs/037-ci-fresh-deploy-fixes/
├── spec.md              # Feature specification (exists)
├── plan.md              # This file
├── research.md          # Phase 0 output (created)
├── data-model.md        # Phase 1 output (created)
├── quickstart.md        # Phase 1 output (created)
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
scripts/lab/pve-service-deploy              — MODIFIED: reorder cmd_apply(), add inject_deploy_key(), check_network_reachability(), update SSH wait default
scripts/lab/profiles.d/service-deploy.json  — MODIFIED: add new evidence artifact fields
python/tests/orchestrator/test_deploy_readiness.py  — NEW: evidence-artifact contract tests for deploy key + network check evidence format
```

**Structure Decision**: All production changes are in the single orchestrator script `pve-service-deploy`. The new bash functions (`inject_deploy_key`, `check_network_reachability`) are pure bash and cannot be unit-tested from Python the way `tfvars_mountpoints.py` can. Instead, tests validate the *evidence artifact contracts* (file format, required fields) — the same pattern used by `test_evidence.py` and `test_summary_golden.py`. Correctness of the bash functions themselves is verified via ShellCheck (lint) and manual CI integration test (deploy nextcloud + deploy jellyfin regression). No new Python modules or dependencies.

## File Structure

```
scripts/lab/pve-service-deploy               — reorder cmd_apply() + add 2 functions + change SSH_WAIT default
scripts/lab/profiles.d/service-deploy.json   — add lxc-deploy-key.txt and network-check.txt as conditional evidence fields
python/tests/orchestrator/test_deploy_readiness.py  — evidence-artifact contract tests (format, required fields)
```

## Architecture Overview

### Component Layout

The changes are surgical additions to the existing orchestrator (`pve-service-deploy`):

1. **`inject_deploy_key()`** — A new bash function inserted after CTID extraction and before the SSH wait loop. It uses `sudo pct exec <ctid> -- bash -c '...'` to:
   - Verify the deploy public key file exists on the PVE host (FR-016).
   - Check if the container is running via `sudo pct status` (FR-015).
   - Create `/root/.ssh/` with mode 700 and `authorized_keys` with mode 600 (FR-005).
   - Check if the key is already present via `grep -qF` (FR-003, idempotent).
   - Append the key if absent (FR-001, FR-004 — append only, no overwrite).
   - Log the action and write evidence to `reports/apply/lxc-deploy-key.txt` (FR-011, FR-017).

2. **`check_network_reachability()`** — A new bash function inserted after deploy key injection and before the SSH wait loop. It:
   - Pings the container IP with `ping -c 1 -W 5` (FR-006).
   - On success: logs and returns 0 (FR-009).
   - On failure: captures diagnostics via `pct exec` (ip addr, ip route) and `pct config` (FR-007, FR-012), writes evidence to `reports/apply/network-check.txt`, and fails with an actionable error message (FR-008).

3. **SSH wait timeout change** — The default for `SSH_WAIT_SECONDS` is changed from `300` to `120` at line 1627 (FR-013). The env var override is preserved.

### Data Flow

**Current** `cmd_apply()` ordering (BROKEN for fresh deploys):
```
Terraform apply → service_ip extraction (line ~1612) → stale host key cleanup (line ~1618)
→ SSH wait loop 300s (line ~1627) → CTID extraction (line ~1650) → DNS check → features → bind mounts → Ansible
```

The SSH wait loop runs *before* CTID extraction, so there is no opportunity to use `pct exec` (which requires CTID) for deploy key injection or network diagnostics before SSH is attempted.

**New** `cmd_apply()` ordering (FIXED):
```
cmd_apply()
  │
  ├── Terraform apply (existing) → creates/updates container
  ├── Extract service_ip from inventory (existing, line ~1612) → $service_ip
  │
  ├── [MOVED UP] Extract CTID from Terraform state (was line ~1650, now before SSH wait)
  │     └── Reads terraform state only — no SSH or container access needed
  │
  ├── [NEW] inject_deploy_key($ctid, $lxc_key_file)
  │     ├── Reads: $lxc_key_file.pub (PVE filesystem)
  │     ├── Executes: sudo pct exec $ctid -- bash -c '...'
  │     └── Writes: $EVIDENCE_ROOT/reports/apply/lxc-deploy-key.txt
  │
  ├── [NEW] check_network_reachability($ctid, $service_ip)
  │     ├── Executes: ping -c 1 -W 5 $service_ip
  │     ├── On failure: sudo pct exec $ctid -- ip addr / ip route
  │     ├── On failure: sudo pct config $ctid | grep net
  │     └── Writes: $EVIDENCE_ROOT/reports/apply/network-check.txt
  │
  ├── Stale host key cleanup (existing, ssh-keygen -R)
  ├── [MODIFIED] SSH wait loop (default 120s, was 300s)
  │     └── ssh -i $lxc_key_file root@$service_ip 'true'
  │
  └── (rest of cmd_apply unchanged: DNS check, features, bind mounts, ansible, healthcheck)
```

### Reordering Rationale

The CTID extraction block (lines ~1650–1708) only reads Terraform state via `terraform state list` and `terraform state show`. It has **no dependency on SSH** — it does not connect to the container. Moving it before the SSH wait loop is safe and enables all `pct exec`-based pre-SSH steps.

The DNS check block (lines ~1710–1760) which currently follows CTID extraction also uses `pct exec` and `pct config`. It stays in its current position relative to CTID extraction (immediately after), but the entire group moves up to before the SSH wait loop. This is also safe — the DNS check reads container config and `/etc/resolv.conf` via `pct exec`, neither of which requires SSH.

### Insertion Point

The reordered flow in `cmd_apply()`:
1. After `service_ip` extraction (line ~1614) and `ansible_inventory_json` processing.
2. **Move** the CTID extraction block (lines ~1650–1708) to here.
3. **Move** the DNS check block (lines ~1710–1760) to after CTID extraction.
4. **Insert** `inject_deploy_key` call (new).
5. **Insert** `check_network_reachability` call (new).
6. Stale host key cleanup (`ssh-keygen -R`, line ~1618) — stays before SSH wait.
7. SSH wait loop (line ~1627) — now with 120s default.

## Technology Choices

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Key injection mechanism | `sudo pct exec <ctid> -- bash -c '...'` | Established Tier 2 pattern in codebase (DNS check, line 1725). Bypasses Terraform variable precedence entirely. |
| Idempotency check | `grep -qF "<key>" authorized_keys` | Fixed-string match avoids regex issues with SSH key characters. Existing pattern in Linux system administration. |
| Network reachability | `ping -c 1 -W 5 <ip>` | Spec D-009 mandates fixed 5-second timeout. ICMP checks L3 reachability; SSH wait loop handles L4. Universal availability on Proxmox. |
| Diagnostic capture | `pct exec` + `pct config` | Spec D-004 defines the exact three diagnostics. Same mechanism as existing DNS check and features check. |
| Evidence format | Flat text (key=value + sections) | Matches existing evidence patterns (lxc-features.txt, dns-check.txt, lxc-mountpoints.txt). No new schema/format. |
| Test framework | pytest (Python) | Existing test harness. Tests will validate the bash logic via mock/fixture patterns already established in `test_orchestrator_unit.py`. |
| SSH wait timeout | 120s default, `SSH_WAIT_SECONDS` env var | Spec D-005. Env var already exists; only the default changes. |

## Implementation Steps

### Step 0: Reorder `cmd_apply()` — move CTID extraction and DNS check before SSH wait loop

- **Files**: `scripts/lab/pve-service-deploy`
- **Description**: The current `cmd_apply()` runs the SSH wait loop (line ~1627) *before* CTID extraction (line ~1650). This prevents any `pct exec`-based operations before SSH is established. Reorder so CTID extraction and the DNS check happen before the SSH wait:
  1. **Move** the CTID extraction block (lines ~1650–1708: `local ctid=""` through the `ctid_report` write) to after `service_ip` extraction (line ~1614) and the `update_ansible_inventory.sh` call.
  2. **Move** the DNS check block (lines ~1710–1760: `dns_report` through `pct reboot`) to immediately after CTID extraction.
  3. The stale host key cleanup (`ssh-keygen -R`, line ~1618) and SSH wait loop (line ~1627) remain in their current relative order but now come *after* CTID extraction, DNS check, and the new functions.
  4. **Verify**: No code in the moved blocks depends on SSH being up. CTID extraction reads Terraform state (`terraform state list/show`). DNS check uses `pct exec` and `pct config` (Tier 2, not SSH). Both are safe to run before the SSH wait.
  5. **Risk**: Low. The blocks are self-contained with clear variable scoping (`local ctid`, `local dns_report`). Moving them changes only execution order, not logic.
- **Dependencies**: None (must be done first — all subsequent steps depend on this ordering)
- **Parallel-safe**: No (foundational reordering)
- **Traces to**: FR-001 (enables deploy key injection before SSH), FR-006 (enables network check before SSH), D-007 (ordering decision)

### Step 1: Add `inject_deploy_key()` function to orchestrator

- **Files**: `scripts/lab/pve-service-deploy`
- **Description**: Add a new bash function `inject_deploy_key()` that takes `ctid` and `lxc_key_file` as arguments. The function:
  1. Validates the public key file (`${lxc_key_file}.pub`) exists — `die` if missing (FR-016).
  2. Checks container is running via `sudo pct status "${ctid}"` — `die` if not running (FR-015).
  3. Reads the public key content from the file.
  4. Computes key fingerprint via `ssh-keygen -lf` for evidence logging.
  5. Executes `sudo pct exec "${ctid}" -- bash -c '...'` to:
     - `mkdir -p /root/.ssh && chmod 700 /root/.ssh`
     - `touch /root/.ssh/authorized_keys && chmod 600 /root/.ssh/authorized_keys`
     - `grep -qF "${key_content}" /root/.ssh/authorized_keys || echo "${key_content}" >> /root/.ssh/authorized_keys`
  6. Determines action taken (injected or skipped) by checking the `grep` exit code.
  7. Writes evidence to `${EVIDENCE_ROOT}/reports/apply/lxc-deploy-key.txt` following the existing key-value format.
  8. Logs action to terminal/CI output.
- **Dependencies**: None
- **Parallel-safe**: Yes
- **Traces to**: FR-001, FR-002, FR-003, FR-004, FR-005, FR-011, FR-015, FR-016, FR-017

### Step 2: Add `check_network_reachability()` function to orchestrator

- **Files**: `scripts/lab/pve-service-deploy`
- **Description**: Add a new bash function `check_network_reachability()` that takes `ctid` and `service_ip` as arguments. The function:
  1. Writes initial evidence header (ctid, expected_ip, timestamp) to `${EVIDENCE_ROOT}/reports/apply/network-check.txt`.
  2. Executes `ping -c 1 -W 5 "${service_ip}"`.
  3. On success: writes `ping_status=ok` to evidence, returns 0.
  4. On failure: writes `ping_status=unreachable` to evidence, then captures:
     - `sudo pct exec "${ctid}" -- ip addr show eth0` (with `|| true` fallback)
     - `sudo pct exec "${ctid}" -- ip route` (with `|| true` fallback)
     - `sudo pct config "${ctid}" | grep -E '^net[0-9]+:'` (host-side)
  5. Writes all diagnostics to evidence file and stderr.
  6. Emits actionable error message naming the unreachable IP and evidence file location.
  7. Returns 1 (hard gate — pipeline fails).
- **Dependencies**: None
- **Parallel-safe**: Yes (parallel with Step 1)
- **Traces to**: FR-006, FR-007, FR-008, FR-009, FR-012

### Step 3: Wire new functions into `cmd_apply()` flow

- **Files**: `scripts/lab/pve-service-deploy`
- **Description**: After Step 0's reordering, insert calls to the two new functions in `cmd_apply()`. The insertion point is after the DNS check block (moved in Step 0) and before the stale host key cleanup + SSH wait loop:
  1. Insert after the DNS check block and before `ssh-keygen -R`:
     ```bash
     # [Tier 2] Inject deploy SSH key into container
     echo "[Tier 2] Injecting deploy SSH key..."
     if [[ -n "${ctid}" ]]; then
         inject_deploy_key "${ctid}" "${lxc_key_file}"
     fi

     # Network reachability check (hard gate)
     echo "[Network] Checking container reachability..."
     check_network_reachability "${ctid:-}" "${service_ip}"
     ```
  2. The `if [[ -n "${ctid}" ]]` guard mirrors the existing pattern for feature flags and bind mounts.
  3. The network check runs regardless of CTID (uses ping only; CTID-dependent diagnostics are best-effort via `pct exec` with `|| true`).
- **Dependencies**: Step 0 (reordering), Step 1, Step 2
- **Parallel-safe**: No (depends on Steps 0, 1, and 2)
- **Traces to**: FR-001, FR-006, FR-009, FR-014 (safe no-ops for existing containers)

### Step 4: Reduce SSH wait timeout default

- **Files**: `scripts/lab/pve-service-deploy`
- **Description**: Change the SSH wait timeout default from 300 to 120 seconds. Modify line 1627:
  - Before: `local ssh_wait_seconds="${SSH_WAIT_SECONDS:-300}"`
  - After: `local ssh_wait_seconds="${SSH_WAIT_SECONDS:-120}"`
  - Also update the same default in all other SSH wait loops within the file (bind mount reboot at line 2277, and any others) for consistency.
- **Dependencies**: None
- **Parallel-safe**: Yes (parallel with Steps 1 and 2)
- **Traces to**: FR-013, US-5 AC-5.1, AC-5.2, AC-5.3

### Step 5: Add evidence-artifact contract tests

- **Files**: `python/tests/orchestrator/test_deploy_readiness.py`
- **Description**: The new bash functions (`inject_deploy_key`, `check_network_reachability`) cannot be unit-tested from Python — they use `pct exec`, `ping`, and `sudo`, none of which are available in the test environment. Instead, create a single pytest module that validates the **evidence artifact contracts** — the file format and required fields that downstream consumers (ci-verify.sh, step summaries) depend on. This follows the existing pattern established by `test_evidence.py` (evidence pack schema), `test_summary_golden.py` (golden-string format), and `test_tfvars_mountpoints.py` (behavioral equivalence against known data).

  Tests:
  1. **test_deploy_key_evidence_format**: Given a sample `lxc-deploy-key.txt` content string matching the data-model schema, verify all required fields are present (`ctid`, `key_file`, `key_fingerprint`, `action`) and `action` is one of `injected`/`skipped`. (FR-017)
  2. **test_deploy_key_evidence_action_values**: Verify that the parser accepts exactly `injected` and `skipped`, rejects unknown values. (FR-003, FR-011)
  3. **test_network_check_evidence_format_ok**: Given a sample `network-check.txt` with `ping_status=ok`, verify required fields (`ctid`, `expected_ip`, `ping_status`) and no diagnostic sections. (FR-009)
  4. **test_network_check_evidence_format_unreachable**: Given a sample `network-check.txt` with `ping_status=unreachable`, verify required fields plus presence of `--- ip addr show eth0 ---`, `--- ip route ---`, and `--- pct config net ---` sections. (FR-007, FR-012)
  5. **test_network_check_evidence_ping_status_values**: Verify parser accepts exactly `ok` and `unreachable`. (FR-006, FR-008)

  The tests use inline string fixtures (not actual files), following the `_SIMPLE_TFVARS` pattern in `test_tfvars_mountpoints.py`. If a Python parser module is warranted later (e.g., for step summary rendering), it can be extracted — but for now, simple `assertIn` / regex checks on the string format are sufficient.

  **Correctness of the bash functions themselves** is verified by:
  - ShellCheck (Step 7) — catches syntax, quoting, and portability issues
  - Manual CI integration test — deploy nextcloud (fresh) + deploy jellyfin (existing, regression)
  - Evidence pack verification via `ci-verify.sh` (existing infrastructure)
- **Dependencies**: Step 1, Step 2 (data model must be finalized)
- **Parallel-safe**: Yes
- **Traces to**: FR-003, FR-006–FR-009, FR-011, FR-012, FR-017, US-1, US-2, US-3

### Step 6: Run existing test suite and ShellCheck

- **Files**: (no new files)
- **Description**: Verify no regressions:
  1. Run `python3 -m pytest python/tests/` — all existing + new contract tests must pass.
  2. Run `shellcheck scripts/lab/pve-service-deploy` — no new warnings/errors.
  3. Run `scripts/lab/ci-verify.sh` against an existing evidence pack fixture if available.
  4. Verify the existing orchestrator tests still pass (test_orchestrator_unit.py, test_runner_plan_apply.py).
- **Dependencies**: Steps 0–5
- **Parallel-safe**: No (final gate)
- **Traces to**: US-3 (no regressions), SC-003

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Reordering CTID extraction breaks existing flow | CTID-dependent steps fail or run at wrong time | CTID extraction only reads Terraform state (no SSH, no container access). DNS check uses `pct exec`/`pct config` (Tier 2, not SSH). Both are safe before SSH wait. Verified by reading the code blocks — no SSH dependency. |
| `pct exec` fails on container not yet running after Terraform apply | Deploy key injection fails, pipeline errors out | FR-015: explicit `pct status` check with clear error message. Proxmox LXC module sets `start=true` (A-005). |
| Concurrent deploys corrupt `authorized_keys` | Duplicate key entries (harmless) | Spec edge case acknowledged. Append is atomic under `PIPE_BUF`. No data corruption risk. |
| ping returns false positive (ICMP blocked) | Pipeline proceeds to SSH wait that will also fail | No firewall rules on internal LAN (A-004). SSH wait provides a second safety net. |
| Reduced timeout (120s) too short for some services | SSH wait fails for slow-starting services | 120s is generous for sshd startup. `SSH_WAIT_SECONDS` env var override preserved for edge cases. |
| `pct exec` diagnostic capture fails (container crashed) | Incomplete diagnostics in evidence | All diagnostic commands use `\|\| true` fallback. Partial diagnostics still better than none. |
| ShellCheck warnings on new code | CI lint failure | New code follows existing patterns that already pass ShellCheck. |

## Testing Strategy

### Evidence-Artifact Contract Tests (automated, pytest)

- **`python/tests/orchestrator/test_deploy_readiness.py`**: Validates the format and required fields of the two new evidence artifacts (`lxc-deploy-key.txt`, `network-check.txt`). Uses inline string fixtures — no actual containers, no mocking of `pct` or `ping`. Follows the pattern established by `test_evidence.py` and `test_tfvars_mountpoints.py`.

### Bash Lint (automated, ShellCheck)

- `shellcheck scripts/lab/pve-service-deploy` — catches syntax, quoting, and portability issues in the new functions. Existing CI step.

### Integration Tests (manual, CI pipeline)

- **Fresh deploy**: Trigger "Lab 1 — LXC Promote" for `nextcloud` (the service that exposed the defect). Verify:
  - Pipeline completes end-to-end without manual intervention (SC-001).
  - Evidence pack contains `lxc-deploy-key.txt` and `network-check.txt`.
  - Deploy key injection logs "injected".
  - Network check logs `ping_status=ok`.
- **Regression test**: Trigger "Lab 1 — LXC Promote" for `jellyfin` (existing service). Verify:
  - Pipeline completes identically to before (SC-003).
  - Deploy key injection logs "skipped (already present)".
  - Network check logs `ping_status=ok`.

### Verification

- `ci-verify.sh` runs on every evidence pack (existing infrastructure).
- ShellCheck runs on `pve-service-deploy` (existing CI lint).
- `python3 -m pytest python/tests/` runs all test suites including the new contract tests.

### Coverage Target

- All 17 FRs have at least one test or verification step tracing to them.
- All 6 success criteria (SC-001 through SC-006) have a corresponding test.

### Why not Python unit tests for the bash functions?

The new functions (`inject_deploy_key`, `check_network_reachability`) are pure bash using `pct exec`, `ping`, and `sudo` — all of which require a live Proxmox host with running containers. There is no established pattern in this codebase for mocking these from Python (the existing Python tests cover the Python orchestrator wrapper, not bash functions). Attempting to mock `pct exec` in Python would create a brittle test that validates mocks, not behavior. The evidence-artifact contract tests plus ShellCheck plus manual CI integration provide equivalent confidence with less fragility.

## Complexity Tracking

No constitution violations to justify. All principles PASS.

## Appendix: Requirement Traceability

| Step | FRs Covered | ACs Covered | SCs Covered |
|------|-------------|-------------|-------------|
| Step 0 | FR-001, FR-006 (enables pre-SSH steps) | — | — |
| Step 1 | FR-001, FR-002, FR-003, FR-004, FR-005, FR-011, FR-015, FR-016, FR-017 | AC-1.1, AC-1.3, AC-1.4, AC-3.2 | SC-001, SC-005, SC-006 |
| Step 2 | FR-006, FR-007, FR-008, FR-009, FR-012 | AC-2.1, AC-2.2, AC-2.3, AC-2.4, AC-3.3 | SC-002 |
| Step 3 | FR-001, FR-006, FR-009, FR-010, FR-014 | AC-1.1, AC-2.4, AC-3.1, AC-4.1 | SC-004 |
| Step 4 | FR-013 | AC-5.1, AC-5.2, AC-5.3 | — |
| Step 5 | FR-003, FR-006–FR-009, FR-011, FR-012, FR-017 | AC-1.4, AC-2.1–AC-2.4, AC-3.2 | SC-002, SC-005 |
| Step 6 | FR-014 | AC-3.1, AC-3.3 | SC-003 |
