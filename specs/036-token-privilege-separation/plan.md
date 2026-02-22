# Implementation Plan: Proxmox Token Privilege Separation

**Branch**: `036-token-privilege-separation` | **Date**: 2026-02-22 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/036-token-privilege-separation/spec.md`

## Summary

Replace the hardcoded per-service bind-mount blocks in the orchestrator (`pve-service-deploy`) with a generic, data-driven mechanism that reads host-path mount definitions from the existing `service_mountpoints` tfvars variable, validates them against an allowlist, applies them idempotently via `pct set`, and produces evidence and step summaries. Formalise the three-tier privilege model in the constitution and operations documentation.

## Technical Context

**Language/Version**: Bash 5.x (orchestrator), HCL/Terraform 1.6.x (infrastructure), Python 3.x (shared module called from orchestrator)
**Primary Dependencies**: Proxmox `pct` CLI, Terraform (Telmate provider 2.9.x), jq, python3
**Storage**: N/A (no database; config in tfvars, state in local terraform.tfstate)
**Testing**: shellcheck (bash lint), terraform validate, existing CI pipeline (`ci.yml`), Python pytest (existing `python/tests/`)
**Target Platform**: Proxmox VE host (Debian Linux), developer laptop (macOS) — dual-provisioning
**Project Type**: Infrastructure-as-Code (IaC) + orchestration scripts
**Performance Goals**: Post-create bind mount step completes within 60 seconds per container (NFR-001)
**Constraints**: No new external dependencies; no root@pam in normal path; no remote state
**Scale/Scope**: 7 services, ~2300-line orchestrator, 6 per-service Terraform roots

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked post-design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| **I. Spec-Driven Workflow** | ✅ PASS | Work driven from `specs/036-token-privilege-separation/`. All tasks trace to spec requirements. |
| **II. Secrets Policy** | ✅ PASS | No secrets introduced. Existing token references unchanged. `readonly` is a boolean flag, not a secret. |
| **III. Separation of Concerns** | ✅ PASS | Terraform owns container existence/sizing. Orchestrator owns post-create config (bind mounts, features). Ansible owns in-guest configuration. No mixing. |
| **IV. Dual-Provisioning Parity** | ✅ PASS | `pve-service-deploy` runs identically from CI and laptop. Step summary output adapts to context (`$GITHUB_STEP_SUMMARY` vs terminal). FR-009 explicitly requires this. |
| **Provider Strategy** | ✅ PASS | Telmate provider retained. bpg migration explicitly out of scope. |
| **State Management** | ✅ PASS | Local state on PVE retained. Remote state explicitly out of scope. |
| **No root@pam in normal path** | ✅ PASS | Tier 1 (terraform@pve) for Terraform, Tier 2 (sudo pct) for orchestrator. Tier 3 (root@pam) is manual-only. CI guardrail (`ci-validate-iac.sh`) continues to enforce this. |
| **Test-Driven Changes** | ✅ PASS | Plan includes unit tests for tfvars parser, shellcheck for bash changes, and existing CI pipeline validates end-to-end. |

**Gate result**: ALL PASS. No violations.

## Project Structure

### Documentation (this feature)

```text
specs/036-token-privilege-separation/
├── spec.md                       # Feature specification
├── plan.md                       # This file
├── research.md                   # Phase 0 research output
├── data-model.md                 # Phase 1 data model
├── quickstart.md                 # Phase 1 quickstart
└── checklists/
    └── requirements.md           # Specification quality checklist
```

### Source Code (files created or modified)

```text
# MODIFIED — Orchestrator (core changes)
scripts/lab/pve-service-deploy                     — Replace hardcoded bind-mount blocks with generic data-driven function; add tier labels; add step summary; add orchestrator-stage allowlist validation

# MODIFIED — Terraform type definitions (add readonly field)
terraform/variables.tf                             — Add readonly = optional(bool) to service_mountpoints object type
terraform/modules/lxc_service/variables.tf         — Add readonly = optional(bool) to mountpoints object type
terraform/services/jellyfin/variables.tf           — Add readonly = optional(bool) to service_mountpoints object type
terraform/services/immich/variables.tf             — Add readonly = optional(bool) to service_mountpoints object type
terraform/services/nextcloud/variables.tf          — Add readonly = optional(bool) to service_mountpoints object type
terraform/services/homeassistant/variables.tf      — Add readonly = optional(bool) to service_mountpoints object type
terraform/services/monitoring/variables.tf         — Add readonly = optional(bool) to service_mountpoints object type
terraform/services/reverse_proxy/variables.tf      — Add readonly = optional(bool) to service_mountpoints object type

# MODIFIED — Per-service Terraform roots (filter host-path mounts)
terraform/services/jellyfin/main.tf                — Add locals to filter host-path mounts; pass only storage-backed to module
terraform/services/immich/main.tf                  — Same filter pattern
terraform/services/nextcloud/main.tf               — Same filter pattern
terraform/services/homeassistant/main.tf           — Same filter pattern (no mounts currently, but defensive)
terraform/services/monitoring/main.tf              — Same filter pattern
terraform/services/reverse_proxy/main.tf           — Same filter pattern

# MODIFIED — Terraform root module (filter host-path mounts, for backward compat)
terraform/main.tf                                  — Add locals to filter host-path mounts in root module service definitions

# MODIFIED — Tfvars examples (add readonly attribute + nextcloud mount)
terraform/environments/lab.tfvars.example          — Add readonly attribute to jellyfin video mount; add nextcloud mount
terraform/environments/prod.tfvars.example         — Add readonly attribute to jellyfin + immich photo mounts; add nextcloud mount

# MODIFIED — Documentation
.specify/memory/constitution.md                    — Add Token Privilege Tiers subsection under Access Control
docs/operations/golden-paths-service-lifecycle.md  — Add bind-mount onboarding checklist to "Add a New Service" section
docs/operations/rebuild-orchestrator.md            — Reference three-tier model

# MODIFIED — Evidence profile (add bind mount evidence field)
scripts/lab/profiles.d/service-deploy.json         — Add lxc-mountpoints.txt as conditional evidence field

# NEW — Python test for tfvars mountpoint parser
python/tests/orchestrator/test_tfvars_mountpoints.py — Unit tests for the inline tfvars parser logic
```

## Implementation Steps

### Step 1: Add `readonly` field to `service_mountpoints` type definition

- **Files**:
  - `terraform/variables.tf`
  - `terraform/modules/lxc_service/variables.tf`
  - `terraform/services/jellyfin/variables.tf`
  - `terraform/services/immich/variables.tf`
  - `terraform/services/nextcloud/variables.tf`
  - `terraform/services/homeassistant/variables.tf`
  - `terraform/services/monitoring/variables.tf`
  - `terraform/services/reverse_proxy/variables.tf`
- **Description**: Add `readonly = optional(bool)` to the object type in the `service_mountpoints` variable (root + per-service) and the `mountpoints` variable in the LXC module. This is an additive, backward-compatible change — existing tfvars without `readonly` will default to `null` (treated as `false` by the orchestrator).
- **Traces to**: FR-008 (data shape), US-7 (onboarding)
- **Dependencies**: None
- **Parallel-safe**: Yes
- **Done-condition**: `terraform validate` passes in all per-service roots and root module. `terraform plan` against existing state proposes zero changes.

### Step 2: Filter host-path mounts in per-service Terraform roots

- **Files**:
  - `terraform/services/jellyfin/main.tf`
  - `terraform/services/immich/main.tf`
  - `terraform/services/nextcloud/main.tf`
  - `terraform/services/homeassistant/main.tf`
  - `terraform/services/monitoring/main.tf`
  - `terraform/services/reverse_proxy/main.tf`
  - `terraform/main.tf` (root module — same pattern for backward compat)
- **Description**: Add a `locals {}` block that filters `service_mountpoints` into two sets: `storage_mounts` (volume does NOT start with `/`) passed to the module, and `host_path_mounts` (volume starts with `/`) excluded from the module. Replace `mountpoints = values(lookup(var.service_mountpoints, "service", {}))` with `mountpoints = values(local.storage_mounts)`. The `host_path_mounts` local is not referenced by Terraform — it exists only for documentation/clarity. The orchestrator reads tfvars directly (see Step 4).
- **Traces to**: FR-003 (no host-path in Terraform mountpoint blocks), FR-004 (existing containers unchanged — `lifecycle { ignore_changes }` preserved), US-2 (no regression on existing services), SC-002, D-006
- **Dependencies**: Step 1
- **Parallel-safe**: Yes (across services; not across files sharing a module)
- **Done-condition**: `terraform validate` passes. `terraform plan` against existing state proposes zero changes (because `lifecycle { ignore_changes = [mountpoint] }` prevents drift — FR-004). For services with ONLY host-path mounts, the module receives an empty list — this must not error.

### Step 3: Fix tfvars examples to match PVE reality, add `readonly`, add nextcloud mount

- **Files**:
  - `terraform/environments/lab.tfvars.example`
  - `terraform/environments/prod.tfvars.example`
- **Description**: **CRITICAL DATA FIX**: PVE verification (2026-02-22) revealed that the Jellyfin tfvars `mp` value is wrong. The hardcoded orchestrator code and the live PVE container use `mp=/media/video`, but the tfvars example says `mp="/mnt/media/video"`. This must be corrected **before** switching to data-driven mounts or the Jellyfin service will break.
  Verified PVE state:
  - Jellyfin mp0: `/mnt/nas/video,mp=/media/video,ro=1` (only 1 mount; no mp1)
  - Immich mp0: `/mnt/nas/homelab_immich,mp=/mnt/immich` (rw)
  - Immich mp1: `/mnt/nas/photo,mp=/mnt/immich-external/photo,ro=1`
  Changes:
  - **Fix** Jellyfin `mp` from `/mnt/media/video` to `/media/video` in both lab and prod examples
  - **Add** `readonly = true` to Jellyfin video mount (matches live `ro=1`)
  - **Add** `readonly = true` to Immich external_photo mount in prod (matches live `ro=1`)
  - **Add** Nextcloud mount entry to both examples
  - **Note**: The hardcoded Jellyfin code had an mp1 photo block, but PVE shows Jellyfin has no mp1. The `findmnt` guard prevented it from being applied. This mp1 block is intentionally NOT carried forward into the tfvars -- it was dead code.
- **Traces to**: FR-021 (tfvars examples), US-2 (no regression), US-7 AC-7.3
- **Dependencies**: Step 1
- **Parallel-safe**: Yes
- **Done-condition**: Jellyfin `mp` is `/media/video` (not `/mnt/media/video`). Both example files contain at least one service entry with `readonly = true`. `terraform validate` passes when examples are used as tfvars (modulo secrets).

### Step 4: Implement generic bind-mount function in orchestrator

- **Files**: `scripts/lab/pve-service-deploy`
- **Description**: This is the core implementation step. Replace the hardcoded Jellyfin and Immich bind-mount blocks (~200 lines, currently under `if [[ "${SERVICE}" == "jellyfin" ]]` and `if [[ "${SERVICE}" == "immich" ]]`) with a single generic function `apply_host_path_bind_mounts()` that:
  1. **Reads mount definitions** from the resolved tfvars file by calling the shared Python module: `python3 -c "from homelab_proxmox_orchestrator.tfvars_mountpoints import parse_service_host_path_mounts; ..."` with `PYTHONPATH` set to `python/src`. This ensures the orchestrator uses the exact same code that the unit tests validate (no inline heredoc duplication). The module is adapted from `scripts/lifecycle/remove_checks.py::_extract_service_mountpoints()` extended to capture `mp`, `volume`, and `readonly` fields. Outputs JSON array of `{mp, volume, readonly}` for host-path entries (volume starts with `/`).
  2. **Validates allowlist** (FR-005, FR-006, FR-007): For each mount, check `volume` starts with an allowed prefix (`/mnt/nas/`) with exact directory-boundary matching (trailing `/`). Reject with actionable error per FR-018.
  3. **Checks existing mounts** (FR-012): Parse `pct config <CTID>` for existing `mp<N>:` lines. Compare volume+mp to detect already-applied mounts. Result: `skipped`.
  4. **Selects next available mp index** (FR-013): Find max existing `mp<N>` index from `pct config` using POSIX-compatible parsing: `awk -F: '/^mp[0-9]/ { sub(/^mp/, "", $1); print $1 }' | sort -n | tail -1`. Do NOT use GNU awk `match()` with capture groups -- it breaks on macOS BSD awk (dual-provisioning parity, Constitution IV). Use N+1.
  5. **Applies mount** via `sudo pct set <CTID> -mp<N> "<volume>,mp=<mp>[,ro=1]"`. Result: `applied`.
  6. **Handles partial failure**: If a mount fails, record `failed` result with cause+remediation per FR-018. Continue processing remaining mounts. Exit with non-zero code if any mount failed.
  7. **Handles container reboot** (FR-011): If ANY mounts were newly applied, stop → apply → start (using `pct reboot`) followed by SSH wait. Summary includes state transition line.
  8. **Produces evidence** (FR-002): Write `reports/apply/lxc-mountpoints.txt` (keeping the existing file name used by the hardcoded blocks) with before/after `pct config` output, matching existing `lxc-features.txt` pattern. Also write stderr to `reports/apply/lxc-mountpoints.stderr.txt` (matching existing pattern).
  9. **Empty list handling**: If no host-path mounts for the service, log "no bind mounts to apply" and return success.
- **Traces to**: FR-001, FR-002, FR-005, FR-006, FR-007, FR-008, FR-011, FR-012, FR-013, FR-016 (features handling unchanged — only bind-mount blocks replaced), FR-018, US-1, US-3, US-4, SC-001, SC-003, SC-004, SC-009, SC-010
- **Dependencies**: Steps 1–3
- **Parallel-safe**: No (single file)
- **Done-condition**: shellcheck passes on modified script. The hardcoded Jellyfin/Immich blocks are removed. The generic function handles all services. Existing Jellyfin/Immich mount behavior is preserved (same host paths, same ro/rw flags). The existing `pct set -features` block is NOT modified (FR-016).

### Step 5: Add step summary output to orchestrator

- **Files**: `scripts/lab/pve-service-deploy`
- **Description**: After the bind-mount function completes, emit a structured step summary listing ALL configured mounts for the service (FR-017). Format: markdown table with columns: Host Path, Container Path, Permission, Result. Include overall status and container reboot line if applicable. Write to `$GITHUB_STEP_SUMMARY` when the variable is set (CI context), otherwise print to terminal (laptop context). The summary is emitted regardless of whether mounts exist (empty table for services without mounts is acceptable — or a single "No bind mounts configured" line).
- **Traces to**: FR-017, US-1 (AC-1.4), US-3 (AC-3.1), US-7 (AC-7.2), SC-008
- **Dependencies**: Step 4
- **Parallel-safe**: No (same file as Step 4)
- **Done-condition**: Running the deploy for a service with mounts produces a markdown summary. Running for a service without mounts produces a "no bind mounts" line. In CI context, `$GITHUB_STEP_SUMMARY` is appended to.

### Step 6: Add tier labels to orchestrator output

- **Files**: `scripts/lab/pve-service-deploy`
- **Description**: Add `echo "[Tier 1] Creating container via Terraform..."` before the terraform plan/apply phase in both `cmd_plan()` and `cmd_apply()`. Add `echo "[Tier 2] Applying bind mounts via pct set..."` and `echo "[Tier 2] Applying feature flags via pct set..."` before the respective post-create blocks in `cmd_apply()`.
- **Traces to**: FR-019, US-1, US-3
- **Dependencies**: Step 4 (should be applied after the main refactor to avoid merge conflicts)
- **Parallel-safe**: No (same file)
- **Done-condition**: Running the deploy script produces `[Tier 1]` and `[Tier 2]` labels in stdout.

### Step 7: Update constitution with three-tier token model

- **Files**: `.specify/memory/constitution.md`
- **Description**: Add a new subsection `### Token Privilege Tiers` under `## Access Control`. Include the three-tier table from the spec overview, the three invariant rules, and a note that this is enforced by `ci-validate-iac.sh` (Tier 1 only) and the orchestrator bind-mount allowlist (Tier 2). Increment the constitution version to 1.3.0.
- **Traces to**: FR-014, US-5 (AC-5.1, AC-5.3), SC-006
- **Dependencies**: None
- **Parallel-safe**: Yes
- **Done-condition**: Searching the constitution for "token" or "privilege" returns the three-tier model section. Version is 1.3.0.

### Step 8: Update operations documentation

- **Files**:
  - `docs/operations/golden-paths-service-lifecycle.md`
  - `docs/operations/rebuild-orchestrator.md`
- **Description**:
  - In `golden-paths-service-lifecycle.md`, add a new subsection "### Bind Mount Configuration" inside "## 1. Add a New Service" with a step-by-step checklist: (a) determine required host paths, (b) declare in `service_mountpoints` tfvars with worked example including `readonly`, (c) verify via deploy pipeline step summary. Per FR-020 and US-7.
  - In `rebuild-orchestrator.md`, add a brief reference to the three-tier model and a link to the constitution section. Per FR-015.
- **Traces to**: FR-015, FR-020, US-5 (AC-5.2), US-7 (AC-7.1, AC-7.2)
- **Dependencies**: Step 7 (constitution must exist first for cross-reference)
- **Parallel-safe**: Yes (different files)
- **Done-condition**: Searching golden paths for "bind mount" returns the new checklist. Searching operations docs for "token" or "privilege" returns a reference to the three-tier model.

### Step 9: Add bind mount evidence to service-deploy profile

- **Files**: `scripts/lab/profiles.d/service-deploy.json`
- **Description**: Add `reports/apply/lxc-mountpoints.txt` as a conditional evidence field (condition: service has host-path bind mounts). This keeps the existing file name already used by the hardcoded blocks, avoiding breakage in any downstream references. This ensures the offline verifier (`ci-verify.sh`) can validate the evidence pack structure.
- **Traces to**: FR-002, SC-005
- **Dependencies**: Step 4
- **Parallel-safe**: Yes
- **Done-condition**: The JSON profile contains the `lxc-mountpoints.txt` field. `ci-verify.sh` on an evidence pack with the file passes; without the file also passes (conditional field).

### Step 10: Write Python unit tests for tfvars mountpoint parser

- **Files**:
  - `python/src/homelab_proxmox_orchestrator/tfvars_mountpoints.py` (shared module)
  - `python/tests/orchestrator/test_tfvars_mountpoints.py` (tests)
- **Description**: Create the shared Python module and write unit tests. The module is called directly by the orchestrator (no inline heredoc duplication -- the orchestrator runs `python3 -c "from homelab_proxmox_orchestrator.tfvars_mountpoints import ..."` with PYTHONPATH). Test cases:
  - Service with host-path mounts → returns correct list with mp, volume, readonly
  - Service with no mounts → returns empty list
  - Service with storage-backed mounts only (volume like `local-lvm:...`) → returns empty list (host-path filter)
  - Mount with `readonly = true` → readonly field is True in output
  - Mount without `readonly` → readonly field defaults to False
  - Allowlist validation: `/mnt/nas/nextcloud` → allowed; `/mnt/nasty-trick` → rejected; `/etc/shadow` → rejected
  - Directory-boundary prefix matching (trailing `/`)
  - Multiple mounts for one service → all returned
  - **Behavioral equivalence test (CRITICAL)**: Parse the actual `prod.tfvars.example` and verify the parser produces the exact `pct set` argument strings that match PVE live state:
    - Jellyfin → `[{"mp": "/media/video", "volume": "/mnt/nas/video", "readonly": true}]` (generates `pct set -mp0 "/mnt/nas/video,mp=/media/video,ro=1"`)
    - Immich → `[{"mp": "/mnt/immich", "volume": "/mnt/nas/homelab_immich", "readonly": false}, {"mp": "/mnt/immich-external/photo", "volume": "/mnt/nas/photo", "readonly": true}]`
    These are verified against the live PVE container configs captured on 2026-02-22.
  - **Step summary format test**: Validate that given a list of mount results, the summary renderer produces a valid markdown table with correct columns (Host Path | Container Path | Permission | Result) and result states (`applied`, `skipped`, `failed`). Use a golden-string comparison, following the existing `test_summary_golden.py` pattern.
- **Traces to**: FR-005, FR-007, FR-008, FR-017, US-2 (behavioral equivalence), Constitution (Test-Driven Changes)
- **Dependencies**: Step 4 (parser logic must be defined)
- **Parallel-safe**: Yes
- **Done-condition**: `python3 -m pytest python/tests/orchestrator/test_tfvars_mountpoints.py` passes with all test cases green. The behavioral equivalence test passes against `prod.tfvars.example`.

### Step 11: Verify CI guardrail for root@pam

- **Files**: (no changes — verification only)
- **Description**: Run `scripts/lab/ci-validate-iac.sh` to confirm it still passes with the current codebase (no root@pam references in Terraform files). This is a verification step, not an implementation step. FR-010 requires the existing guardrail to remain intact.
- **Traces to**: FR-010, US-6
- **Dependencies**: Steps 1–3 (Terraform changes must be complete)
- **Parallel-safe**: Yes
- **Done-condition**: `bash scripts/lab/ci-validate-iac.sh` exits with code 0.

### Step 12: Run full CI validation suite

- **Files**: (no changes — verification only)
- **Description**: Run the complete CI validation suite locally to ensure no regressions:
  1. `bash scripts/lab/ci-validate-iac.sh` (IaC posture)
  2. `bash scripts/ci/terraform-validate.sh` (terraform fmt + validate)
  3. `bash scripts/ci/python-tests.sh` (Python test suite)
  4. shellcheck on `scripts/lab/pve-service-deploy`
- **Traces to**: SC-002, SC-007, Constitution (Test-Driven Changes)
- **Dependencies**: All previous steps
- **Parallel-safe**: Yes (read-only operations)
- **Done-condition**: All four commands exit with code 0.

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Existing Jellyfin/Immich mounts break after removing hardcoded blocks | High — services lose NAS access | **Behavioral equivalence test** (Step 10) verifies parser output against PVE live state captured 2026-02-22. tfvars `mp` path for Jellyfin corrected from `/mnt/media/video` to `/media/video` (Step 3). `lifecycle { ignore_changes }` prevents Terraform drift. |
| tfvars data doesn't match PVE reality | High — wrong mount paths applied | **PVE verification done** (2026-02-22): Jellyfin mp0=`/media/video` (not `/mnt/media/video`), Jellyfin has no mp1 (hardcoded mp1 photo block was dead code), Immich mp0+mp1 match tfvars. Step 3 fixes the Jellyfin discrepancy. |
| Python module vs orchestrator logic divergence | Medium — tests pass but deploy breaks | **Eliminated**: orchestrator calls the Python module directly via `python3 -c "from homelab_proxmox_orchestrator..."` instead of duplicating logic in an inline heredoc (Step 4). Same code path for tests and production. |
| Terraform plan shows unexpected changes after filtering host-path mounts | Medium — plan instability | `lifecycle { ignore_changes = [mountpoint] }` prevents drift for existing containers. For new containers, the plan should show only storage-backed mounts (or no mounts). Verify with `terraform plan` after Step 2. |
| macOS awk incompatibility breaks mount index detection | Medium — laptop deploy fails | **Fixed in plan**: Step 4 specifies POSIX-compatible `awk -F:` parsing instead of GNU `match()` with capture groups. No `grep -P` either. |
| Step summary in GITHUB_STEP_SUMMARY exceeds size limit | Low — CI display issue | Homelab services have 1–3 mounts each. Summary is compact markdown table. No risk of exceeding GitHub's 1MB limit. |

## Testing Strategy

### Automated (run before merge)

- **Behavioral equivalence test** (CRITICAL): `test_tfvars_mountpoints.py` includes a test that parses `prod.tfvars.example` and asserts the output matches the exact `pct set` argument strings observed on PVE (2026-02-22). This catches data mismatches like the Jellyfin `/mnt/media/video` vs `/media/video` bug before it reaches production.
- **Unit tests**: `python/tests/orchestrator/test_tfvars_mountpoints.py` — parser, allowlist, directory-boundary matching, readonly defaults, empty/missing service. Covers FR-005, FR-007, FR-008.
- **Step summary format test**: Golden-string test for the markdown table renderer (columns, result states, reboot line). Follows existing `test_summary_golden.py` pattern. Covers FR-017.
- **Lint/format**: shellcheck on `scripts/lab/pve-service-deploy`, terraform fmt/validate on all `.tf` files, Python linting via pre-commit.
- **Existing CI pipeline**: `scripts/lab/ci-validate-iac.sh` (root@pam guardrail), `scripts/ci/terraform-validate.sh` (terraform validation), `scripts/ci/python-tests.sh` (full Python test suite including the new tests).

### Manual verification (on PVE or via `act`)

- Deploy a service with bind mounts (e.g., Nextcloud in lab) and verify:
  - Container created without host-path mountpoints in Terraform plan
  - Orchestrator applies mounts via `pct set`
  - Evidence artifact (`lxc-mountpoints.txt`) contains before/after config
  - Step summary shows correct mount results
  - Re-running deploy shows mounts as `skipped` (idempotent)
  - Deploying with disallowed path is rejected
- **Regression**: `terraform plan` against all existing services shows zero proposed changes.

### Coverage

- 100% of the new Python parser module (parser + allowlist + summary renderer).
- Orchestrator bash changes verified via shellcheck + behavioral equivalence test + manual/integration testing.
- The orchestrator calls the Python module directly (no inline heredoc), so unit tests cover the actual production code path.

## Complexity Tracking

No constitution violations to justify. All principles PASS.

## File Manifest

| Action | File | Purpose |
|--------|------|---------|
| MODIFY | `scripts/lab/pve-service-deploy` | Core: generic bind-mount function, tier labels, step summary |
| MODIFY | `terraform/variables.tf` | Add `readonly = optional(bool)` |
| MODIFY | `terraform/modules/lxc_service/variables.tf` | Add `readonly = optional(bool)` |
| MODIFY | `terraform/services/jellyfin/variables.tf` | Add `readonly = optional(bool)` |
| MODIFY | `terraform/services/immich/variables.tf` | Add `readonly = optional(bool)` |
| MODIFY | `terraform/services/nextcloud/variables.tf` | Add `readonly = optional(bool)` |
| MODIFY | `terraform/services/homeassistant/variables.tf` | Add `readonly = optional(bool)` |
| MODIFY | `terraform/services/monitoring/variables.tf` | Add `readonly = optional(bool)` |
| MODIFY | `terraform/services/reverse_proxy/variables.tf` | Add `readonly = optional(bool)` |
| MODIFY | `terraform/services/jellyfin/main.tf` | Filter host-path mounts |
| MODIFY | `terraform/services/immich/main.tf` | Filter host-path mounts |
| MODIFY | `terraform/services/nextcloud/main.tf` | Filter host-path mounts |
| MODIFY | `terraform/services/homeassistant/main.tf` | Filter host-path mounts |
| MODIFY | `terraform/services/monitoring/main.tf` | Filter host-path mounts |
| MODIFY | `terraform/services/reverse_proxy/main.tf` | Filter host-path mounts |
| MODIFY | `terraform/main.tf` | Filter host-path mounts in root module |
| MODIFY | `terraform/environments/lab.tfvars.example` | Add `readonly`, nextcloud mount |
| MODIFY | `terraform/environments/prod.tfvars.example` | Add `readonly`, nextcloud mount |
| MODIFY | `.specify/memory/constitution.md` | Three-tier token model |
| MODIFY | `docs/operations/golden-paths-service-lifecycle.md` | Bind-mount onboarding checklist |
| MODIFY | `docs/operations/rebuild-orchestrator.md` | Three-tier model reference |
| MODIFY | `scripts/lab/profiles.d/service-deploy.json` | Bind mount evidence field (`lxc-mountpoints.txt`) |
| CREATE | `python/src/homelab_proxmox_orchestrator/tfvars_mountpoints.py` | Shared parser module |
| CREATE | `python/tests/orchestrator/test_tfvars_mountpoints.py` | Unit tests for parser |
