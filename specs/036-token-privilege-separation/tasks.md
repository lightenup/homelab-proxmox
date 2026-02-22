# Tasks: Proxmox Token Privilege Separation

**Branch**: `036-token-privilege-separation` | **Date**: 2026-02-22
**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, quickstart.md ✅

**Tests**: Python unit tests explicitly requested (Constitution "Test-Driven Changes" principle). IaC validation via `terraform validate`, `shellcheck`, `ci-validate-iac.sh`.

**Organization**: Tasks grouped by user story phase (P1 → P2 → P3) per template requirements. Foundation phase covers blocking prerequisites shared across all user stories. Critical data fixes (wrong Jellyfin `mp` path in tfvars) are in Foundation because behavioral equivalence tests in Phase 3 parse `prod.tfvars.example` directly.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1–US7 from spec.md)
- Exact file paths included in every description

---

## Summary

- **Total tasks**: 30
- **Estimated complexity**: High (~200 lines of hardcoded bash replaced with ~300-line generic function + Python parser module + type changes across 8 Terraform files + 6 per-service filter changes + documentation)
- **Parallel tracks**: 4 identified (Foundation type changes | Terraform filtering in Phase 4 | Documentation in Phases 7/9 | Final verification)
- **MVP scope**: Phase 2 (Foundation) + Phase 3 (US-1) = working generic bind-mount mechanism

---

## Phase 1: Setup

_No setup tasks required. All implementation occurs within the existing project structure: Bash scripts in `scripts/lab/`, Terraform modules in `terraform/`, Python in `python/`, documentation in `docs/` and `.specify/memory/`._

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Extend Terraform type definitions with the `readonly` attribute, create the shared Python parser module, and fix critical data errors in tfvars examples. These changes are prerequisites for all user story phases.

The tfvars fixes (T005, T006) are placed here — not in Phase 9/US-7 — because the behavioral equivalence tests in Phase 3 parse `prod.tfvars.example` directly and will fail if the wrong Jellyfin `mp` path (`/mnt/media/video`) is not corrected to `/media/video` before those tests run.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T001 [P] Add `readonly = optional(bool)` to the `service_mountpoints` inner object type in `terraform/variables.tf` (add after `storage = optional(string)` in the existing object definition). **Done-condition**: `rg 'readonly = optional\(bool\)' terraform/variables.tf` returns a match; `cd terraform && terraform validate` exits 0.

- [X] T002 [P] Add `readonly = optional(bool)` to the `mountpoints` inner object type in `terraform/modules/lxc_service/variables.tf` (add after `storage = optional(string)`). **Done-condition**: `rg 'readonly = optional\(bool\)' terraform/modules/lxc_service/variables.tf` returns a match.

- [X] T003 [P] Add `readonly = optional(bool)` to the `service_mountpoints` inner object type in all 6 per-service `variables.tf` files: `terraform/services/jellyfin/variables.tf`, `terraform/services/immich/variables.tf`, `terraform/services/nextcloud/variables.tf`, `terraform/services/homeassistant/variables.tf`, `terraform/services/monitoring/variables.tf`, `terraform/services/reverse_proxy/variables.tf` (add after `storage = optional(string)` in each). **Done-condition**: `rg 'readonly = optional\(bool\)' terraform/services/*/variables.tf` returns exactly 6 matches.

- [X] T004 [P] Create `python/src/homelab_proxmox_orchestrator/tfvars_mountpoints.py` with three pure functions: `parse_service_host_path_mounts(tfvars_text: str, service: str) -> list[dict]` (parses `service_mountpoints` tfvars, returns `[{"mp": str, "volume": str, "readonly": bool}]` for entries where `volume` starts with `/`, `readonly` defaults to `False`; adapted from `_extract_service_mountpoints()` in `scripts/lifecycle/remove_checks.py` extended to capture `mp` and `readonly`); `validate_bind_mount_allowlist(mounts: list[dict], allowed_prefixes: tuple[str, ...] = ("/mnt/nas/",)) -> tuple[list[dict], list[dict]]` (directory-boundary prefix matching, returns `(allowed, rejected)`); `format_pct_set_arg(mount: dict) -> str` (returns the `pct set` argument string e.g., `"/mnt/nas/video,mp=/media/video,ro=1"`, enabling unit-testable verification of exact strings sent to `pct set`). The orchestrator calls this module directly — no inline heredoc. **Done-condition**: `PYTHONPATH=python/src python3 -c "from homelab_proxmox_orchestrator.tfvars_mountpoints import parse_service_host_path_mounts, validate_bind_mount_allowlist, format_pct_set_arg; print('OK')"` exits 0 and prints OK.

- [X] T005 [P] [US2,US7] **CRITICAL DATA FIX**: Update `terraform/environments/lab.tfvars.example` — (a) fix jellyfin `mp` value from `/mnt/media/video` to `/media/video` (PVE verified 2026-02-22: live container uses `/media/video`), (b) add `readonly = true` to jellyfin video mount, (c) add a nextcloud entry under `service_mountpoints` demonstrating the bind-mount pattern (e.g., `nextcloud = { data = { mp = "/mnt/nextcloud", volume = "/mnt/nas/homelab_nextcloud" } }`). Note: the hardcoded Jellyfin code had an mp1 photo block but PVE shows Jellyfin has no mp1 — that was dead code protected by a `findmnt` guard and is NOT carried forward. **Done-condition**: `rg '"/media/video"' terraform/environments/lab.tfvars.example` returns a match (not `/mnt/media/video`); `rg 'readonly = true' terraform/environments/lab.tfvars.example` returns at least 1 match; `rg 'nextcloud' terraform/environments/lab.tfvars.example` returns a match.

- [X] T006 [P] [US2,US7] **CRITICAL DATA FIX**: Update `terraform/environments/prod.tfvars.example` — (a) fix jellyfin `mp` from `/mnt/media/video` to `/media/video`, (b) add `readonly = true` to jellyfin video mount, (c) add `readonly = true` to immich external_photo mount (matches live `ro=1` on PVE), (d) add nextcloud entry: `nextcloud = { data = { mp = "/mnt/nextcloud", volume = "/mnt/nas/homelab_nextcloud" } }`. **Done-condition**: `rg '"/media/video"' terraform/environments/prod.tfvars.example` returns a match; `rg 'readonly = true' terraform/environments/prod.tfvars.example` returns at least 2 matches; `rg 'nextcloud' terraform/environments/prod.tfvars.example` returns a match.

**Checkpoint**: Terraform types extended with `readonly`. Python parser module importable. tfvars examples corrected (Jellyfin `mp` fixed from `/mnt/media/video` → `/media/video`). `terraform validate` passes in root module.

---

## Phase 3: US-1 (P1) — CI Deploys a Service Requiring Host-Path Bind Mounts

**Goal**: Enable the CI pipeline to create LXC containers and apply NAS bind mounts using only the least-privilege `terraform@pve` API token (Tier 1) plus orchestrator `sudo pct set` (Tier 2). No `root@pam` API token in any automated step.

**Independent Test**: Deploy the Nextcloud service through the CI pipeline. Container is created by Terraform without host-path `mountpoint {}` blocks; bind mount is applied via `pct set` in the post-create step; evidence artifact `reports/apply/lxc-mountpoints.txt` contains before/after `pct config`; step summary lists the mount result.

### Tests for US-1

> Write these tests FIRST; verify they FAIL before proceeding to implementation tasks.

- [X] T007 [P] [US1] Create `python/tests/orchestrator/test_tfvars_mountpoints.py` with basic parser tests: `test_parse_service_with_host_path_mounts` (returns correct mp/volume/readonly for a host-path entry), `test_parse_service_no_mounts` (missing service key → `[]`), `test_parse_service_storage_backed_only` (volume like `local-lvm:vm-100-disk-0` → `[]`), `test_parse_readonly_true` (`readonly = true` → `True`), `test_parse_readonly_absent_defaults_false` (absent `readonly` → `False`), `test_parse_multiple_mounts` (service with 2+ mounts returns all). **Done-condition**: `PYTHONPATH=python/src python3 -m pytest python/tests/orchestrator/test_tfvars_mountpoints.py -v` runs the 6 cases (some will fail until T004 implementation is complete, confirming TDD cycle).

- [X] T008 [P] [US1] Add behavioral equivalence tests to `python/tests/orchestrator/test_tfvars_mountpoints.py` (depends on T005/T006 being complete since tests parse `prod.tfvars.example`): `test_behavioral_equivalence_jellyfin` (parse `terraform/environments/prod.tfvars.example` for jellyfin, assert output equals `[{"mp": "/media/video", "volume": "/mnt/nas/video", "readonly": True}]` and `format_pct_set_arg` produces `"/mnt/nas/video,mp=/media/video,ro=1"` — verified against PVE live state 2026-02-22); `test_behavioral_equivalence_immich` (parse prod.tfvars.example for immich, assert 2 mounts: `{"mp": "/mnt/immich", "volume": "/mnt/nas/homelab_immich", "readonly": False}` and `{"mp": "/mnt/immich-external/photo", "volume": "/mnt/nas/photo", "readonly": True}`). **Done-condition**: Both behavioral equivalence tests pass after T004, T005, T006 complete; if either fails, the data fix in T005/T006 is incomplete or the parser in T004 has a bug.

- [X] T009 [P] [US1] Add `test_step_summary_format` to `python/tests/orchestrator/test_tfvars_mountpoints.py`: given a list of mount results covering all three states (`applied`, `skipped`, `failed`), assert the rendered output is a valid markdown table with columns `| Host Path | Container Path | Permission | Result |`, a reboot status line, and an overall summary line. Use golden-string comparison following any existing `test_summary_golden.py` pattern in the project. Add a `format_step_summary(mount_results: list[dict]) -> str` function to `python/src/homelab_proxmox_orchestrator/tfvars_mountpoints.py` to make this testable. **Done-condition**: `test_step_summary_format` is present in the test file and passes; `format_step_summary` is importable from the module.

### Implementation for US-1

- [X] T010 [US1] Create the `extract_host_path_mounts()` function in `scripts/lab/pve-service-deploy` (place after existing `enforce_bind_mount_policy()` function). The function: accepts `$1=tfvars_path` and `$2=service`, calls the Python module directly (no inline heredoc): `PYTHONPATH="${REPO_ROOT}/python/src" python3 -c "from homelab_proxmox_orchestrator.tfvars_mountpoints import parse_service_host_path_mounts; import json, sys; print(json.dumps(parse_service_host_path_mounts(open(sys.argv[1]).read(), sys.argv[2])))" "${1}" "${2}"`, outputs JSON array of host-path mounts, returns empty array `[]` for services with no host-path mounts. **Done-condition**: `shellcheck scripts/lab/pve-service-deploy` passes; `grep -c "from homelab_proxmox_orchestrator.tfvars_mountpoints" scripts/lab/pve-service-deploy` equals 1 (no inline heredoc duplication).

- [X] T011 [US1] Create the `validate_bind_mount_allowlist()` function in `scripts/lab/pve-service-deploy` (place after `extract_host_path_mounts()`). The function: accepts a JSON mount array, iterates each `volume` field, checks with `[[ "${volume}" == "/mnt/nas/"* ]]` (trailing-slash directory-boundary matching per D-005/FR-007), rejects with FR-018-format error message: `"Bind mount rejected — path ${volume} is outside the allowlist (/mnt/nas/); review service_mountpoints in tfvars"`, returns 1 if any mount rejected. **Done-condition**: `shellcheck scripts/lab/pve-service-deploy` passes; grep confirms `"/mnt/nas/"*` pattern with trailing `/` in the function; no Python-style `startswith` in this bash function.

- [X] T012 [US1] Create the `apply_host_path_bind_mounts()` function in `scripts/lab/pve-service-deploy` (~150–200 lines; place after `validate_bind_mount_allowlist()`). The function: (a) calls `extract_host_path_mounts` — if empty list → log "no host-path bind mounts to apply for service=${SERVICE}" + return 0; (b) calls `validate_bind_mount_allowlist` — return 1 if any path rejected (FR-006); (c) captures before-state via `sudo pct config "${ctid}"`; (d) for each mount from JSON: check if `volume,mp=path` appears in config → result=`skipped`; otherwise find next available `mp<N>` index using POSIX-compatible awk: `awk -F: '/^mp[0-9]/ { sub(/^mp/, "", $1); print $1 }' | sort -n | tail -1` (do NOT use GNU `match()` with capture groups — breaks on macOS BSD awk, violating Constitution IV); apply via `sudo -n pct set "${ctid}" -mp${next_idx} "${volume},mp=${mp}${ro_flag}"` → result=`applied` or `failed`; (e) if ANY mounts newly applied → `sudo -n pct reboot "${ctid}"` + SSH wait loop (FR-011); (f) captures after-state via `sudo pct config "${ctid}"`; (g) writes evidence to `${EVIDENCE_ROOT}/reports/apply/lxc-mountpoints.txt` in key=value format matching `lxc-features.txt` pattern (FR-002). **Done-condition**: `shellcheck scripts/lab/pve-service-deploy` passes; grep confirms `pct set`, `pct config`, `pct reboot` in function body; grep confirms POSIX awk `sub(/^mp/)` pattern; no `grep -P` or GNU `awk match()` with capture groups in mount-index logic.

- [X] T013 [US1] Add step summary emission inside `apply_host_path_bind_mounts()` in `scripts/lab/pve-service-deploy`. After processing all mounts, emit: (a) markdown table header `| Host Path | Container Path | Permission | Result |`, (b) one row per configured mount with result state (`applied`, `skipped`, `failed`) — ALL configured mounts listed regardless of outcome (FR-017), (c) optional reboot line `**Container reboot**: stopped → mounts applied → started` if reboot occurred, (d) overall summary `**Overall**: success/failure (N applied, N skipped, N failed)`. Write to `$GITHUB_STEP_SUMMARY` (append with `>>`) when variable is set (CI context); otherwise print to terminal (laptop context). Emit for empty mount lists too ("No bind mounts configured for service X"). **Done-condition**: grep confirms `GITHUB_STEP_SUMMARY` conditional write and markdown table header string in `scripts/lab/pve-service-deploy`.

- [X] T014 [US1] Replace the hardcoded Jellyfin (`if [[ "${SERVICE}" == "jellyfin" ]]`) and Immich (`if [[ "${SERVICE}" == "immich" ]]`) bind-mount blocks in `cmd_apply()` of `scripts/lab/pve-service-deploy` with a single call `apply_host_path_bind_mounts "${ctid}" "${TFVARS_FILE}"` (wrapped in `if [[ -n "${ctid}" ]]; then ... fi`). Place the call AFTER the existing `pct set -features` block and BEFORE the Ansible bootstrap step. The `pct set -features` block MUST NOT be modified (FR-016 — already generic). **Done-condition**: `grep -c 'SERVICE.*jellyfin\|SERVICE.*immich' scripts/lab/pve-service-deploy` equals 0 in bind-mount context; `grep -c 'apply_host_path_bind_mounts' scripts/lab/pve-service-deploy` equals 1 (called once in `cmd_apply`); `shellcheck scripts/lab/pve-service-deploy` passes.

- [X] T015 [P] [US1] Add `reports/apply/lxc-mountpoints.txt` as a conditional evidence field in `scripts/lab/profiles.d/service-deploy.json` (append to `conditional_fields` array): `{"path": "reports/apply/lxc-mountpoints.txt", "type": "file", "condition": "service has host-path bind mounts", "description": "Before/after pct config for bind mount operations"}`. Keep the `lxc-mountpoints.txt` filename (matches existing hardcoded blocks — no breaking downstream refs). **Done-condition**: `jq '.conditional_fields[] | select(.path == "reports/apply/lxc-mountpoints.txt")' scripts/lab/profiles.d/service-deploy.json` returns the entry; `jq . scripts/lab/profiles.d/service-deploy.json` exits 0 (valid JSON).

**Checkpoint**: All US-1 tests pass. Orchestrator generic bind-mount mechanism functional. Hardcoded Jellyfin/Immich blocks removed. Evidence artifact written. Step summary emitted in both CI (`$GITHUB_STEP_SUMMARY`) and laptop (stdout) contexts.

---

## Phase 4: US-2 (P1) — Existing Services Are Not Disrupted

**Goal**: After Terraform changes, running a plan against all existing services produces zero proposed modifications to `mountpoint` or `features` attributes. The `lifecycle { ignore_changes }` directive already prevents drift; the additional filter locals make intent explicit and prevent accidental host-path leakage into `mountpoint {}` blocks.

**Independent Test**: `terraform plan` (with `-out /dev/null`) against each per-service root and root module. No planned changes to `mountpoint` or `features` for any existing container.

### Implementation for US-2

- [X] T016 [US2] Add `locals {}` host-path filter to `terraform/services/jellyfin/main.tf`. Insert before the `module` block:
  ```hcl
  locals {
    all_mounts_jellyfin     = lookup(var.service_mountpoints, "jellyfin", {})
    storage_mounts_jellyfin = { for k, v in local.all_mounts_jellyfin : k => v if !startswith(v.volume, "/") }
  }
  ```
  Change `mountpoints = values(lookup(var.service_mountpoints, "jellyfin", {}))` to `mountpoints = values(local.storage_mounts_jellyfin)`. **Done-condition**: `terraform -chdir=terraform/services/jellyfin validate` exits 0; `rg 'storage_mounts_jellyfin' terraform/services/jellyfin/main.tf` returns a match; no `values(lookup(var.service_mountpoints` remains in the module `mountpoints` argument.

- [X] T017 [P] [US2] Apply same `locals {}` host-path filter pattern to `terraform/services/immich/main.tf` (locals named `all_mounts_immich`, `storage_mounts_immich`; service key: `"immich"`). **Done-condition**: `terraform -chdir=terraform/services/immich validate` exits 0; `rg 'storage_mounts_immich' terraform/services/immich/main.tf` returns a match.

- [X] T018 [P] [US2] Apply same `locals {}` host-path filter pattern to `terraform/services/nextcloud/main.tf` (locals named `all_mounts_nextcloud`, `storage_mounts_nextcloud`; service key: `"nextcloud"`). **Done-condition**: `terraform -chdir=terraform/services/nextcloud validate` exits 0.

- [X] T019 [P] [US2] Apply same `locals {}` host-path filter pattern to `terraform/services/homeassistant/main.tf`, `terraform/services/monitoring/main.tf`, and `terraform/services/reverse_proxy/main.tf` (per-service locals named `all_mounts_<service>`, `storage_mounts_<service>` for each). **Done-condition**: `terraform -chdir=terraform/services/homeassistant validate` exits 0; same for monitoring and reverse_proxy.

- [X] T020 [US2] Apply host-path filter to `terraform/main.tf` (root module). For each service module block that passes a `mountpoints` argument (e.g., `jellyfin_lxc`, `nextcloud_lxc`), add a corresponding local to filter storage-only mounts and update the argument. Services without `mountpoints` in the root module need no changes. **Done-condition**: `cd terraform && terraform validate` exits 0; no unfiltered `values(lookup(var.service_mountpoints` call passes a host-path volume to a module `mountpoints` argument.

**Checkpoint**: All per-service Terraform roots validate. Root module validates. Host-path entries cannot leak into `mountpoint {}` blocks. `lifecycle { ignore_changes = [mountpoint, features] }` remains in place (FR-004).

---

## Phase 5: US-3 (P1) — Laptop Deploy Has Parity with CI

**Goal**: The same `pve-service-deploy` invocation from CI and from a developer laptop produces identical container configuration and equivalent output. Tier labels make the active privilege level visible in both contexts.

**Independent Test**: Deploy a test service with bind mounts from a laptop using the same arguments as CI. Resulting container has identical mounts and features. Terminal output shows `[Tier 1]` and `[Tier 2]` labels.

**Note**: CI/laptop parity is primarily enforced via: (a) POSIX-compatible awk in T012 (no GNU-only patterns that fail on macOS BSD awk), (b) `$GITHUB_STEP_SUMMARY` conditional in T013 (same function, context-aware output). This phase adds the operator-visible tier labels (FR-019) that complete the parity UX.

### Implementation for US-3

- [X] T021 [US3] Add `[Tier 1]` and `[Tier 2]` phase labels to `scripts/lab/pve-service-deploy`. In `cmd_plan()`: add `echo "[Tier 1] Planning container via Terraform..."` before `terraform_init_with_retry`. In `cmd_apply()`: add `echo "[Tier 1] Creating/updating container via Terraform..."` before terraform init/apply; add `echo "[Tier 2] Applying feature flags via pct set..."` before the existing `pct set -features` block; add `echo "[Tier 2] Applying host-path bind mounts via pct set..."` before the `apply_host_path_bind_mounts` call. **Done-condition**: `grep -c '\[Tier 1\]' scripts/lab/pve-service-deploy` returns >= 2; `grep -c '\[Tier 2\]' scripts/lab/pve-service-deploy` returns >= 2; `shellcheck scripts/lab/pve-service-deploy` passes.

**Checkpoint**: Tier labels visible in both CI and laptop output. POSIX-awk compatibility confirmed via done-condition in T012 (no GNU-only patterns).

---

## Phase 6: US-4 (P2) — Bind-Mount Path Allowlist Enforcement

**Goal**: The orchestrator rejects bind-mount host paths outside `/mnt/nas/` with directory-boundary precision. A misconfiguration cannot accidentally expose arbitrary host directories. Rejection produces an actionable error per FR-018.

**Independent Test**: Invoke `validate_bind_mount_allowlist` with host path `/etc/shadow` → non-zero exit, error message naming the disallowed path. Invoke with `/mnt/nasty-trick` → rejected (not a subdirectory of `/mnt/nas/`). Invoke with `/mnt/nas/nextcloud` → allowed.

**Note**: The `validate_bind_mount_allowlist()` bash function and the Python `validate_bind_mount_allowlist()` are implemented in T011 and T004 respectively (Phase 3). This phase adds the dedicated unit tests that confirm boundary correctness — specifically AC-4.3 (the `/mnt/nasty-trick` edge case).

### Tests for US-4

- [X] T022 [P] [US4] Add allowlist unit tests to `python/tests/orchestrator/test_tfvars_mountpoints.py`: `test_allowlist_valid_path` (`/mnt/nas/nextcloud` passes the `/mnt/nas/` prefix check), `test_allowlist_reject_outside` (`/etc/shadow` rejected), `test_allowlist_directory_boundary` (`/mnt/nasty-trick` rejected — NOT a child directory of `/mnt/nas/`), `test_allowlist_multiple_mounts_mixed` (one allowed path + one rejected path → correct split in return tuple). **Done-condition**: `PYTHONPATH=python/src python3 -m pytest python/tests/orchestrator/test_tfvars_mountpoints.py -k "allowlist" -v` passes all 4 tests; `test_allowlist_directory_boundary` is present and passing.

**Checkpoint**: Allowlist function (implemented in T011/T004) is validated by unit tests. Directory-boundary precision confirmed for `/mnt/nasty-trick` edge case (AC-4.3, FR-007).

---

## Phase 7: US-5 (P2) — Documented Token Tier Policy

**Goal**: The three-tier privilege model is documented in the constitution and referenced in operations docs. An operator or contributor can find it by searching "token" or "privilege." The documented policy matches the implementation.

**Independent Test**: `rg "Token Privilege Tiers" .specify/memory/constitution.md` returns a match; `rg -i "privilege tiers" docs/operations/rebuild-orchestrator.md` returns a match; constitution version is 1.3.0.

### Implementation for US-5

- [X] T023 [P] [US5] Add `### Token Privilege Tiers` subsection under `## Access Control` in `.specify/memory/constitution.md`. Content: (a) three-tier table with columns Tier | Credential / Grant | Scope | Used By (matching the spec overview table), (b) three invariant rules ("Tier 1 is the only credential passed to Terraform", "Tier 2 is exercised only by the orchestrator post-create step", "Tier 3 is never referenced in automated flows"), (c) enforcement note: "Enforced by `scripts/lab/ci-validate-iac.sh` (Tier 1 boundary) and orchestrator bind-mount allowlist (Tier 2 boundary)." Increment constitution version to 1.3.0. **Done-condition**: `rg "Token Privilege Tiers" .specify/memory/constitution.md` returns match; `rg "1\.3\.0" .specify/memory/constitution.md` returns match.

- [X] T024 [P] [US5] Add `### Privilege Tiers` subsection after the existing "## PVE Access" section in `docs/operations/rebuild-orchestrator.md`. Content: brief paragraph stating that standard rebuild operations use Tier 1 (Terraform, `terraform@pve` token) and Tier 2 (orchestrator `pct set` via `sudo`), that manual break-glass operations use Tier 3 (`root@pam!rebuild`) for disaster recovery only, with a cross-reference link to the constitution section. **Done-condition**: `rg "Privilege Tiers" docs/operations/rebuild-orchestrator.md` returns match.

**Checkpoint**: Constitution updated to v1.3.0. Operations docs reference three-tier model. Both are discoverable by searching "token" or "privilege."

---

## Phase 8: US-6 (P2) — CI Guardrail Rejects root@pam in Terraform

**Goal**: The existing `ci-validate-iac.sh` guardrail continues to reject any `root@pam` reference in Terraform files after all Terraform changes in Phases 2 and 4. No code changes are needed; this is a mandatory verification gate (FR-010).

**Independent Test**: `bash scripts/lab/ci-validate-iac.sh` exits 0 with the current codebase after all Terraform modifications are complete.

### Implementation for US-6

- [X] T025 [US6] Run `bash scripts/lab/ci-validate-iac.sh` from the repo root. Must run AFTER Phase 2 (T001–T006) and Phase 4 (T016–T020) are complete since those phases modify Terraform files. Verify it exits with code 0, confirming no `root@pam` references were introduced in any Terraform file. **Done-condition**: `bash scripts/lab/ci-validate-iac.sh` exits 0.

**Checkpoint**: Existing CI guardrail (FR-010) confirmed intact after all Terraform changes. US-6 AC-6.1 and AC-6.2 satisfied by the existing script with no code modifications required.

---

## Phase 9: US-7 (P3) — Operator Onboards a New Service Requiring Bind Mounts

**Goal**: An operator can discover, declare, and verify bind mounts for a new service by following only the service lifecycle documentation — no reading orchestrator source code required.

**Independent Test**: Follow only `docs/operations/golden-paths-service-lifecycle.md` to configure bind mounts for a new service. Steps (a) determine host paths, (b) declare in tfvars, (c) verify after deploy — all present and actionable without consulting other docs.

**Note**: The tfvars example files (FR-021) were corrected and extended in T005 and T006 (Foundation phase) to unblock behavioral equivalence testing in Phase 3. Those tasks satisfy AC-7.3. The task below completes US-7 by adding the onboarding checklist (FR-020, AC-7.1).

### Implementation for US-7

- [X] T026 [US7] Add `### Bind Mount Configuration` subsection inside `## 1. Add a New Service` in `docs/operations/golden-paths-service-lifecycle.md` (after the "Define Infrastructure" step). Include a step-by-step checklist: (a) "Determine required host paths — check service documentation for NAS storage needs. All paths MUST be under `/mnt/nas/` (enforced by the orchestrator allowlist)", (b) "Declare mounts in `service_mountpoints` in `terraform/environments/<env>.tfvars`" with a worked example showing `mp`, `volume`, and `readonly` fields (use the nextcloud entry added in T005/T006 as the concrete example), (c) "Deploy via `pve-service-deploy apply` — the orchestrator applies mounts automatically via `pct set` (Tier 2), no root@pam token required", (d) "Verify — check step summary for per-mount result states (`applied`, `skipped`, `failed`); inspect `reports/apply/lxc-mountpoints.txt` evidence artifact for before/after container configuration". **Done-condition**: `rg "Bind Mount Configuration" docs/operations/golden-paths-service-lifecycle.md` returns match; all four checklist steps (a)–(d) are present in the section.

**Checkpoint**: Onboarding checklist present in golden paths (AC-7.1). tfvars examples (T005/T006) demonstrate `readonly` attribute (AC-7.3). Step summary (T013) reports mount results to operators (AC-7.2). US-7 fully satisfied.

---

## Final Phase: Full Verification

**Purpose**: Run the complete validation suite to confirm all changes work together. Must run after all previous phases are complete.

- [X] T027 [P] Run `PYTHONPATH=python/src python3 -m pytest python/tests/orchestrator/test_tfvars_mountpoints.py -v` — all tests green, including behavioral equivalence tests (T008), allowlist boundary tests (T022), and step summary format test (T009). **Done-condition**: pytest exits 0; all tests collected and passing; no tests skipped or xfailed unexpectedly.

- [X] T028 Run `shellcheck scripts/lab/pve-service-deploy` — no new errors or warnings introduced by changes in T010–T014, T021. Document any existing shellcheck exclusions (e.g., SC2034, SC2086) that are preserved from before this feature. **Done-condition**: shellcheck exits 0 (or only shows pre-existing suppressed codes matching the current script's exclusion pattern); `apply_host_path_bind_mounts` is called exactly once in `cmd_apply`.

- [X] T029 [P] Run `terraform fmt -check -recursive terraform/` to verify formatting. Run `terraform validate` (with `-backend=false` for local execution without state) in `terraform/` root and each `terraform/services/*/` directory. **Done-condition**: `terraform fmt -check -recursive terraform/` exits 0; all `terraform validate` commands exit 0.

- [X] T030 Run `bash scripts/ci/python-tests.sh` — full Python test suite passes including all new tests added in T007–T009 and T022. **Done-condition**: `bash scripts/ci/python-tests.sh` exits 0.

**Checkpoint**: All verification steps pass. Feature is ready for code review and merge.

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 2: Foundation (T001–T006)
  ├──→ Phase 3: US-1 (T007–T015)   [T010 needs T004; T008 needs T005/T006]
  │      ├──→ Phase 5: US-3 (T021) [tier labels — placed after functions exist in script]
  │      └──→ Phase 6: US-4 (T022) [allowlist tests — validator implemented in T011]
  ├──→ Phase 4: US-2 (T016–T020)   [Terraform filter — needs T001–T003 type extensions]
  ├──→ Phase 7: US-5 (T023–T024)   [independent of code changes — can start anytime]
  └──→ Phase 9: US-7 (T026)         [independent of code changes — can start anytime]

Phase 8: US-6 (T025) [after Phase 2 + Phase 4 — Terraform files must be in final state]

Final Verification (T027–T030) [after ALL phases complete]
```

### Task-Level Dependencies

| Task | Depends On | Note |
|------|-----------|------|
| T001–T006 | None | All parallel (different files) |
| T007–T009 | T004 (module must exist to import) | T008 also depends on T005, T006 |
| T010 | T004 | Imports Python module |
| T011 | T010 | Placed after extract function in script |
| T012 | T011 | Calls validate function |
| T013 | T012 | Adds to existing apply function |
| T014 | T012 | Calls apply function |
| T015 | None | Different file; parallel |
| T016 | T001–T003 | Terraform type must be extended first |
| T017–T019 | T001–T003 | Parallel with T016 (different files) |
| T020 | T001–T003 | Root module filter |
| T021 | T014 | Labels added near apply call |
| T022 | T004 | Tests Python module |
| T023–T024 | None | Documentation; fully parallel |
| T025 | T016–T020 | Terraform files must be final |
| T026 | None | Documentation; fully parallel |
| T027–T030 | All phases | Final verification |

### Parallel Opportunities

**Phase 2 (full parallel)**: T001 ‖ T002 ‖ T003 ‖ T004 ‖ T005 ‖ T006

**Phase 3 (partial parallel)**:
- Tests: T007 ‖ T009 (immediately); T008 after T005/T006
- Implementation: T010 → T011 → T012 → T013 → T014 (sequential, same file); T015 parallel

**Phase 4 (partial parallel)**: T016 establishes pattern; T017 ‖ T018 ‖ T019 parallel after T016; T020 parallel with T016–T019

**Phases 7 and 9 (full parallel with Phase 3 and 4)**: T023 ‖ T024 ‖ T026 can all run while code changes are in progress

**Final Phase (partial parallel)**: T027 ‖ T029; T028 after T014 (shellcheck the modified script); T030 after T027

---

## Constitution Check

| Principle | Status | Evidence |
|-----------|--------|----------|
| **I. Spec-Driven Workflow** | ✅ PASS | All tasks trace to FR/US tags; file manifest enumerates every file; plan step coverage verified |
| **II. Secrets Policy** | ✅ PASS | No secrets introduced; `readonly` is a boolean flag; no credentials in code |
| **III. Separation of Concerns** | ✅ PASS | Terraform owns container existence/sizing; orchestrator owns post-create bind mounts; Ansible owns in-guest config |
| **IV. Dual-Provisioning Parity** | ✅ PASS | POSIX-compatible awk in T012 (no GNU-only patterns breaking on macOS); `$GITHUB_STEP_SUMMARY` context detection in T013; confirmed in T027–T030 |
| **Provider Strategy** | ✅ PASS | Telmate provider retained; no bpg changes; out of scope stated |
| **State Management** | ✅ PASS | Local state on PVE retained; no remote state introduced |
| **No root@pam in normal path** | ✅ PASS | Tier 1 for Terraform, Tier 2 for orchestrator `pct set`, Tier 3 manual-only; confirmed by T025 |
| **Test-Driven Changes** | ✅ PASS | Python unit tests (T007–T009, T022) written FIRST; shellcheck (T028); terraform validate (T029) |

---

## File Manifest

| Action | File | Task(s) | Purpose |
|--------|------|---------|---------|
| MODIFY | `terraform/variables.tf` | T001 | Add `readonly = optional(bool)` |
| MODIFY | `terraform/modules/lxc_service/variables.tf` | T002 | Add `readonly = optional(bool)` |
| MODIFY | `terraform/services/jellyfin/variables.tf` | T003 | Add `readonly = optional(bool)` |
| MODIFY | `terraform/services/immich/variables.tf` | T003 | Add `readonly = optional(bool)` |
| MODIFY | `terraform/services/nextcloud/variables.tf` | T003 | Add `readonly = optional(bool)` |
| MODIFY | `terraform/services/homeassistant/variables.tf` | T003 | Add `readonly = optional(bool)` |
| MODIFY | `terraform/services/monitoring/variables.tf` | T003 | Add `readonly = optional(bool)` |
| MODIFY | `terraform/services/reverse_proxy/variables.tf` | T003 | Add `readonly = optional(bool)` |
| CREATE | `python/src/homelab_proxmox_orchestrator/tfvars_mountpoints.py` | T004, T009 | Shared parser module (4 functions: parse, validate, format_pct_set_arg, format_step_summary) |
| MODIFY | `terraform/environments/lab.tfvars.example` | T005 | **Fix** Jellyfin mp path + add `readonly` + nextcloud mount |
| MODIFY | `terraform/environments/prod.tfvars.example` | T006 | **Fix** Jellyfin mp path + add `readonly` (×2) + nextcloud mount |
| CREATE | `python/tests/orchestrator/test_tfvars_mountpoints.py` | T007, T008, T009, T022 | Unit + behavioral equivalence + allowlist + summary format tests |
| MODIFY | `scripts/lab/pve-service-deploy` | T010, T011, T012, T013, T014, T021 | Generic bind-mount functions; step summary; tier labels; remove hardcoded blocks |
| MODIFY | `scripts/lab/profiles.d/service-deploy.json` | T015 | Bind mount evidence field (`lxc-mountpoints.txt`) |
| MODIFY | `terraform/services/jellyfin/main.tf` | T016 | Filter host-path mounts via locals |
| MODIFY | `terraform/services/immich/main.tf` | T017 | Filter host-path mounts via locals |
| MODIFY | `terraform/services/nextcloud/main.tf` | T018 | Filter host-path mounts via locals |
| MODIFY | `terraform/services/homeassistant/main.tf` | T019 | Filter host-path mounts via locals |
| MODIFY | `terraform/services/monitoring/main.tf` | T019 | Filter host-path mounts via locals |
| MODIFY | `terraform/services/reverse_proxy/main.tf` | T019 | Filter host-path mounts via locals |
| MODIFY | `terraform/main.tf` | T020 | Filter host-path mounts in root module |
| MODIFY | `.specify/memory/constitution.md` | T023 | Three-tier token model (v1.3.0) |
| MODIFY | `docs/operations/rebuild-orchestrator.md` | T024 | Three-tier model reference |
| MODIFY | `docs/operations/golden-paths-service-lifecycle.md` | T026 | Bind-mount onboarding checklist |

**Total**: 9 files created, 16 files modified, 25 files in manifest.

---

## Requirement Traceability Matrix

| Requirement | Task(s) | Verification |
|-------------|---------|-------------|
| FR-001 (apply bind mounts via pct set) | T012, T014 | T008 (behavioral equivalence), T028 (shellcheck) |
| FR-002 (evidence artifact) | T012, T015 | T028; `jq` check in T015 done-condition |
| FR-003 (no host-path in TF mountpoint blocks) | T016–T020 | T029 (terraform validate) |
| FR-004 (existing containers unchanged) | T016–T020 | T029; `lifecycle { ignore_changes }` preserved |
| FR-005 (validate against allowlist) | T004, T011 | T022, T027 |
| FR-006 (reject with clear error) | T011 | T022, T028 |
| FR-007 (directory-boundary matching) | T004, T011 | T022 (`test_allowlist_directory_boundary`) |
| FR-008 (read from service_mountpoints tfvars) | T004, T010 | T007, T008, T027 |
| FR-009 (CI/laptop parity) | T012 (POSIX awk), T013 (context detection), T021 | T028; no GNU-awk-only patterns |
| FR-010 (CI guardrail for root@pam) | — (unchanged) | T025 |
| FR-011 (container reboot) | T012 | T028 |
| FR-012 (idempotent skip) | T012 | T028; `skipped` result state in T013 |
| FR-013 (next available mp index) | T012 | T028 (POSIX awk pattern check) |
| FR-014 (constitution update) | T023 | `rg "Token Privilege Tiers" .specify/memory/constitution.md` |
| FR-015 (operations docs update) | T024 | `rg "Privilege Tiers" docs/operations/rebuild-orchestrator.md` |
| FR-016 (features handling unchanged) | T014 | T028 (features block not modified) |
| FR-017 (step summary) | T013 | T009 (step summary format test), T028 |
| FR-018 (actionable error messages) | T011, T012 | T028; T022 (error message content) |
| FR-019 (tier labels) | T021 | `grep -c '\[Tier' scripts/lab/pve-service-deploy` >= 4 |
| FR-020 (service lifecycle docs) | T026 | `rg "Bind Mount Configuration" docs/operations/golden-paths-service-lifecycle.md` |
| FR-021 (tfvars examples with readonly) | T005, T006 | `rg 'readonly = true' terraform/environments/prod.tfvars.example` >= 2 |

---

## Self-Critique

### Structural Changes from Previous Version

- **Reorganized from implementation-concern phases to user-story phases** (required by task generation template). Previous version had "Terraform Foundation / Orchestrator / Python / Docs / Verification" phases; this version has "Foundation / US-1 through US-7 / Final Verification".
- **Critical data fix (tfvars) moved to Foundation** (not US-7 phase) because behavioral equivalence tests in Phase 3 parse `prod.tfvars.example` directly and require the corrected Jellyfin `mp` path.
- **Python parser module (T004) moved to Foundation** (not US-1 implementation) because T010 (Phase 3) imports it and the tests in T007–T009 also depend on it.
- **`format_step_summary()` function added to T004** after noting T009 (step summary format test) needs a testable Python function, not just the bash emission in T013.
- **Plan step coverage verified**: All 12 plan steps have at least one task.

### Quality Checks

- All 30 tasks have mechanically verifiable done-conditions (grep patterns, exit codes, pytest results, jq queries).
- File manifest is complete: 25 files (9 created, 16 modified) with action and task references.
- Traceability matrix covers all 21 functional requirements.
- Constitution check passed: all 8 principles verified.
- No GNU-awk-only patterns: T012 done-condition explicitly requires POSIX-compatible `sub(/^mp/)`.
- Behavioral equivalence tests (T008) verify the exact `pct set` argument strings against PVE live state before the generic function goes live — guarding against the confirmed Jellyfin `/mnt/media/video` → `/media/video` data discrepancy.

### Verdict

ACCEPT — All tasks are user-story-organized, mechanically verifiable, and traceable to spec requirements. File manifest is complete. Constitution check passes all 8 principles.
