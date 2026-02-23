# Task Breakdown: TFvars Template Separation

**Input**: Design documents from `/specs/038-tfvars-template-separation/`
**Branch**: `038-tfvars-template-separation`
**Date**: 2026-02-23

## Summary

- **Total tasks**: 16
- **Estimated complexity**: Medium
- **Parallel tracks**: 3 independent tracks identified
  - Track A (Provisioner): T001 → T002 → T004 → T004a → T005 → T006 → T009 → T010 → T011
  - Track B (Schema + Downstream): T003 + T004b (schema then evidence consumers)
  - Track C (Examples): T007 + T008 (fully independent, different files)
  - Track D (Tests): T012 (starts after T001–T003, T007–T008 complete)
  - Gate: T013 (verification, last)

## File Manifest

**New files**:
- `terraform/environments/prod.tfvars.template`
- `terraform/environments/lab.tfvars.template`
- `python/tests/orchestrator/test_tfvars_template.py`
- `scripts/lab/fixtures/evidence-packs/service-deploy-valid/reports/lab-tfvars/validation.json`
- `scripts/lab/fixtures/evidence-packs/service-deploy-valid/reports/lab-tfvars/lab.tfvars.sha256`

**Modified files**:
- `terraform/environments/prod.tfvars.example`
- `terraform/environments/lab.tfvars.example`
- `scripts/lab/lib/tfvars.sh`
- `scripts/lab/pve-service-deploy` (remove prod-only guard, wire lab provisioning)
- `scripts/lab/contracts/evidence-tfvars-proof.schema.json`
- `scripts/lab/profiles.d/service-deploy.json` (env-parameterized evidence paths)
- `scripts/lab/verify_evidence.py` (env-parameterized evidence validation)
- `scripts/lab/fixtures/evidence-packs/service-deploy-valid/reports/prod-tfvars/validation.json` (extended with new fields)
- `scripts/lab/fixtures/evidence-packs/service-deploy-valid/reports/prod-tfvars/prod.tfvars.sha256`

## Tasks

---

## Phase 2: Foundational (Parallel Prerequisites)

**Purpose**: Configuration files and schema extension that must exist before provisioner work begins. All three tasks are parallel-safe (no shared files, no mutual dependencies).

**⚠️ CRITICAL**: T004 (provisioner lookup) cannot begin until T001 and T002 are complete.

---

### Task T001: Create prod CI template file

- **Type**: create
- **File**: `terraform/environments/prod.tfvars.template`
- **Plan step**: Step 1
- **Depends on**: None
- **Parallel-safe**: Yes
- **Description**: Create `terraform/environments/prod.tfvars.template` with real non-secret infrastructure values (from the current `prod.tfvars.example` prod network: `192.168.1.x`), the literal token ID `terraform@pve!terraform-token`, and exactly one `__INJECT_TOKEN_SECRET__` sentinel marker in the `proxmox_api_token_secret` field. Add a header comment: `# CI template — real non-secret values. Do not copy for local use; see prod.tfvars.example instead.`
- **Acceptance**: `grep -c '__INJECT_TOKEN_SECRET__' terraform/environments/prod.tfvars.template` returns `1`. File exists and contains the literal string `terraform@pve!terraform-token`.
- **Traces to**: FR-001, FR-002, FR-011, D-003
- [ ] T001 [P] Create CI template for prod in `terraform/environments/prod.tfvars.template`

---

### Task T002: Create lab CI template file

- **Type**: create
- **File**: `terraform/environments/lab.tfvars.template`
- **Plan step**: Step 1
- **Depends on**: None
- **Parallel-safe**: Yes
- **Description**: Create `terraform/environments/lab.tfvars.template` with real non-secret infrastructure values (lab network: `192.168.1.x` — same subnet as prod; the old `192.168.20.x` was a bug fixed during nextcloud deploy), the literal token ID `terraform@pve!terraform-token`, and exactly one `__INJECT_TOKEN_SECRET__` sentinel marker. Add a header comment: `# CI template — real non-secret values. Do not copy for local use; see lab.tfvars.example instead.` Lab template is consumed by the provisioner (T004a wires lab into the same codepath as prod).
- **Acceptance**: `grep -c '__INJECT_TOKEN_SECRET__' terraform/environments/lab.tfvars.template` returns `1`. File exists and contains `192.168.1` (lab network) for service IPs. `grep -c '192.168.20' terraform/environments/lab.tfvars.template` returns `0`.
- **Traces to**: FR-001, FR-002, FR-011, D-005
- [ ] T002 [P] Create CI template for lab in `terraform/environments/lab.tfvars.template`

---

### Task T003: Extend evidence JSON schema with drift and warnings fields

- **Type**: modify
- **File**: `scripts/lab/contracts/evidence-tfvars-proof.schema.json`
- **Plan step**: Step 9
- **Depends on**: None
- **Parallel-safe**: Yes
- **Description**: Add two optional properties to `scripts/lab/contracts/evidence-tfvars-proof.schema.json`. `drift_results` is an object with `provisioning_gaps` (array of strings) and `manual_additions` (array of strings). `change_warnings` is an array of objects each with required string properties `key`, `old_value`, `new_value`. Both fields must be absent from the `required` array (backward compatibility, A-002). Update the `additionalProperties` handling if needed to permit the new fields. Add an example to `examples[]` showing both new fields populated.
- **Acceptance**: `python3 -c "import json; json.load(open('scripts/lab/contracts/evidence-tfvars-proof.schema.json'))"` exits 0. Schema contains `"drift_results"` and `"change_warnings"` in `properties`. Neither appears in `required`.
- **Traces to**: FR-012, A-002
- [ ] T003 [P] Extend evidence schema in `scripts/lab/contracts/evidence-tfvars-proof.schema.json`

---

## Phase 3: User Story 1 — CI Provisioner Uses Dedicated Templates (Priority: P1) 🎯 MVP

**Goal**: The automated provisioner sources configuration from `.tfvars.template` files and injects secrets via sentinel replacement — eliminating placeholder leakage into rendered output.

**Independent Test**: Run the provisioner with `PROD_TFVARS_TEMPLATE` pointing to a test template containing `__INJECT_TOKEN_SECRET__` and verify the rendered output contains the injected secret value with no sentinel markers remaining.

---

### Task T004: Update provisioner template lookup to three-tier chain

- **Type**: modify
- **File**: `scripts/lab/lib/tfvars.sh`
- **Plan step**: Step 3
- **Depends on**: T001, T002
- **Parallel-safe**: No (modifies `_tfvars_provision_prod_and_write_proof()` — same function as T005–T011)
- **Description**: In `_tfvars_provision_prod_and_write_proof()` in `scripts/lab/lib/tfvars.sh`, replace the current `candidates` array (`prod.tfvars`, `prod.tfvars.example`) with the new three-tier lookup: (1) `PROD_TFVARS_TEMPLATE` env var (existing override path), (2) `${repo_root}/terraform/environments/prod.tfvars.template`, (3) `${repo_root}/terraform/environments/prod.tfvars.example`. When the env var points to a nonexistent file, fall back to file-system discovery (current behaviour) and document the fallback in evidence via `template_source`. Remove `prod.tfvars` (rendered file) from the candidates list — it must no longer be a template source.
- **Acceptance**: When `terraform/environments/prod.tfvars.template` exists, the provisioner selects it over `prod.tfvars.example`. When only `prod.tfvars.example` exists (template deleted), the provisioner falls back to it without error. Verified by inspecting the `template_source` field in the resulting `validation.json`.
- **Traces to**: FR-004, D-002, SC-006
- [ ] T004 [US1] Update template lookup chain in `scripts/lab/lib/tfvars.sh`

---

### Task T004a: Rename provisioner to environment-agnostic and wire lab

- **Type**: modify
- **Files**: `scripts/lab/lib/tfvars.sh`, `scripts/lab/pve-service-deploy`
- **Plan step**: N/A (spec Goal 6 — lab/prod parity)
- **Depends on**: T004
- **Parallel-safe**: No (modifies the provisioner function and its call sites)
- **Description**: Three changes:
  1. **Rename function**: In `scripts/lab/lib/tfvars.sh`, rename `_tfvars_provision_prod_and_write_proof()` to `_tfvars_provision_and_write_proof()`. Add a third parameter `environment` (`lab` or `prod`). Replace all hardcoded `prod` references inside the function: `prod.tfvars` → `${environment}.tfvars`, evidence subdir `prod-tfvars` → `${environment}-tfvars`, and the rendered path `${tfvars_dir%/}/prod.tfvars` → `${tfvars_dir%/}/${environment}.tfvars`. The template lookup (from T004) now uses `${environment}.tfvars.template` → `${environment}.tfvars.example`.
  2. **Remove prod-only guard**: In `scripts/lab/pve-service-deploy`, `cmd_plan()` (around line 803) and `cmd_apply()` (around line 1132) both have `if [[ "${ENVIRONMENT}" == "prod" ]]; then ... _tfvars_provision_prod_and_write_proof ... fi`. Remove the `if` guard so both lab and prod go through the provisioner. Update the function call to `_tfvars_provision_and_write_proof "${EVIDENCE_ROOT}/reports" "${tfvars_dir}" "${ENVIRONMENT}"`.
  3. **Update TFVARS_PATH assignment**: After provisioning, set `TFVARS_PATH="${tfvars_dir%/}/${ENVIRONMENT}.tfvars"` instead of hardcoded `prod.tfvars`.
- **Acceptance**: `grep -c '_tfvars_provision_prod_and_write_proof' scripts/lab/lib/tfvars.sh scripts/lab/pve-service-deploy` returns `0` (old name gone). `grep -c '_tfvars_provision_and_write_proof' scripts/lab/pve-service-deploy` returns at least `2` (one in cmd_plan, one in cmd_apply). `grep -c 'ENVIRONMENT.*==.*prod.*_tfvars_provision' scripts/lab/pve-service-deploy` returns `0` (no prod-only guard). Lab runs produce evidence under `reports/lab-tfvars/`.
- **Traces to**: Goal 6, D-005
- [ ] T004a Rename provisioner and wire lab into same codepath

---

### Task T004b: Update downstream evidence consumers for env-parameterized paths

- **Type**: modify
- **Files**: `scripts/lab/profiles.d/service-deploy.json`, `scripts/lab/verify_evidence.py`, fixture files under `scripts/lab/fixtures/evidence-packs/service-deploy-valid/reports/`
- **Plan step**: N/A (spec Goal 6 — evidence parity)
- **Depends on**: T003, T004a
- **Parallel-safe**: No (modifies evidence verification pipeline)
- **Description**: Three files hardcode `prod-tfvars/` paths and need updating:
  1. **`scripts/lab/profiles.d/service-deploy.json`**: The 3 entries referencing `reports/prod-tfvars/provisioning.txt`, `reports/prod-tfvars/validation.json`, and `reports/prod-tfvars/prod.tfvars.sha256` are currently prod-only conditional artifacts. Update them to use environment-parameterized paths or make them conditional on environment (if the profile format supports it). If not, add corresponding `lab-tfvars/` entries for lab runs.
  2. **`scripts/lab/verify_evidence.py`**: The 4 references to `reports/prod-tfvars/` (lines ~328-360) hardcode the prod path. Parameterize using the run's environment (extractable from the evidence pack metadata or run ID prefix). When environment is `lab`, look for `reports/lab-tfvars/validation.json` and `reports/lab-tfvars/lab.tfvars.sha256`.
  3. **Fixture files**: Create lab counterparts under `scripts/lab/fixtures/evidence-packs/service-deploy-valid/reports/lab-tfvars/` (`validation.json` and `lab.tfvars.sha256`) matching the same schema. Update existing `prod-tfvars/validation.json` fixture to include the new `drift_results` and `change_warnings` fields (from T003 schema extension).
- **Acceptance**: `grep -c 'prod-tfvars' scripts/lab/verify_evidence.py` returns `0` (no more hardcoded prod path). Lab evidence packs with `reports/lab-tfvars/` pass verification. Prod evidence packs with `reports/prod-tfvars/` still pass verification (backward compat). `python3 -m pytest python/tests/ -ra` passes (existing verify_evidence tests).
- **Traces to**: Goal 6, FR-012, D-005
- [ ] T004b Update evidence consumers for env-parameterized artifact paths

---

### Task T005: Implement sentinel-based injection

- **Type**: modify
- **File**: `scripts/lab/lib/tfvars.sh`
- **Plan step**: Step 4
- **Depends on**: T004a
- **Parallel-safe**: No (same function as T004/T004a, T006–T011)
- **Description**: In `_tfvars_provision_and_write_proof()`, replace the current `sed` field-name pattern match for `proxmox_api_token_secret` with sentinel replacement. When `token_secret` is non-empty, use `sed -i.bak '/^[[:space:]]*#/! s|__INJECT_TOKEN_SECRET__|${secret_escaped}|g'` on the temp file (with `.bak` cleanup for macOS/BSD portability). Retain the existing token ID enforcement (`proxmox_api_token_id` sed replacement) unchanged. When processing a `.tfvars.example` fallback (no sentinels), the injection is a no-op — the existing sed-based field replacement is preserved as fallback for backward compatibility.
- **Acceptance**: Given `PROXMOX_API_TOKEN_SECRET=test123` and a template containing `proxmox_api_token_secret = "__INJECT_TOKEN_SECRET__"` and a comment line `# __INJECT_TOKEN_SECRET__ example`, the rendered tmp file contains the injected value in the value field and the comment is unchanged (sentinel preserved in comment, replaced in value).
- **Traces to**: FR-005, D-001, D-003
- [ ] T005 [US1] Implement sentinel injection in `scripts/lab/lib/tfvars.sh`

**Checkpoint**: At this point, US-1 core flow (template discovery + sentinel injection) is functional.

---

## Phase 4: User Story 2 — Post-Injection Sentinel Validation (Priority: P1)

**Goal**: The provisioner catches un-injected sentinels before writing any rendered file, ensuring placeholder values never reach a deployment.

**Independent Test**: Set `PROXMOX_API_TOKEN_SECRET=""` (unset) and run the provisioner against a template containing `__INJECT_TOKEN_SECRET__`. Verify exit code is non-zero and `validation.json` contains an error string matching `"Un-injected sentinel: __INJECT_TOKEN_SECRET__"`.

---

### Task T006: Add post-injection sentinel validation

- **Type**: modify
- **File**: `scripts/lab/lib/tfvars.sh`
- **Plan step**: Step 5
- **Depends on**: T005
- **Parallel-safe**: No (same function)
- **Description**: In `_tfvars_provision_and_write_proof()`, after sentinel injection and token ID enforcement, scan the temp file for remaining `__INJECT_[A-Z_]+__` patterns on non-comment lines. Use `grep -E '__INJECT_[A-Z_]+__'` filtered through `grep -v '^[[:space:]]*#'`. For each remaining sentinel found, append an error to the `errors` array: `"Un-injected sentinel: __INJECT_TOKEN_SECRET__ (source: PROXMOX_API_TOKEN_SECRET not set)"`. This check runs BEFORE the existing token ID and secret validations. When processing a `.tfvars.example` fallback (no sentinels), `grep` finds nothing — the check is benign.
- **Acceptance**: Given a template with `proxmox_api_token_secret = "__INJECT_TOKEN_SECRET__"` and `PROXMOX_API_TOKEN_SECRET` unset, the provisioner exits with code 1 and the written `validation.json` contains `"Un-injected sentinel: __INJECT_TOKEN_SECRET__"` in `validation_errors`.
- **Traces to**: FR-006, US-2, SC-002
- [ ] T006 [US2] Add post-injection sentinel validation in `scripts/lab/lib/tfvars.sh`

**Checkpoint**: At this point, US-1 and US-2 (P1 stories) are complete. Zero sentinel leakage is now guaranteed.

---

## Phase 5: User Story 3 — Documentation Examples Are Safe to Copy (Priority: P2)

**Goal**: Both `.tfvars.example` files contain only safe generic placeholders and instructional comments — no real IP addresses, real SSH keys, or sentinel markers.

**Independent Test**: `grep -cE '192\.168\.|AAAAC3NzaC1|__INJECT_' terraform/environments/prod.tfvars.example` returns `0`. An operator can open the file and understand all placeholder fields without consulting external docs.

> ⚠️ **Constraint**: The `service_mountpoints` block structure and mount path values (e.g., `/mnt/nas/homelab_immich`, `/mnt/nas/video`, `/mnt/nas/photo`) MUST be preserved. Existing behavioral equivalence tests in `python/tests/orchestrator/test_tfvars_mountpoints.py` (`test_behavioral_equivalence_jellyfin`, `test_behavioral_equivalence_immich`) assert specific mount paths from `prod.tfvars.example`. Only IP addresses, SSH public keys, and token fields require placeholder substitution.

---

### Task T007: Revert prod.tfvars.example to safe documentation placeholders

- **Type**: modify
- **File**: `terraform/environments/prod.tfvars.example`
- **Plan step**: Step 2
- **Depends on**: T001 (real values must have a home in the template before being removed from example)
- **Parallel-safe**: Yes (modifies a different file from Phases 3–4)
- **Description**: Edit `terraform/environments/prod.tfvars.example` to replace: (a) all IP address values → `<pve-api-url>`, `<gateway-ip>`, `<service-ip>/24` (with instructional comments); (b) the SSH public key → `<your-ssh-public-key>`; (c) `proxmox_api_token_id` value → `<token-id>` (with comment showing expected format `terraform@pve!terraform-token`); (d) `proxmox_api_token_secret` value → `<your-token-secret>`. Add a header comment: `# Documentation example — copy to prod.tfvars and replace placeholders. See prod.tfvars.template for CI use.` Preserve the `service_mountpoints` block structure and all mount path values intact (required by existing tests).
- **Acceptance**: `grep -cE '192\.168\.|AAAAC3NzaC1|__INJECT_' terraform/environments/prod.tfvars.example` returns `0`. `grep -c 'service_mountpoints' terraform/environments/prod.tfvars.example` returns `1` (block preserved). `PYTHONPATH=python/src python3 -m pytest python/tests/orchestrator/test_tfvars_mountpoints.py -v` passes.
- **Traces to**: FR-003, FR-011, A-005, US-3, SC-003
- [ ] T007 [P] [US3] Revert prod example to safe placeholders in `terraform/environments/prod.tfvars.example`

---

### Task T008: Revert lab.tfvars.example to safe documentation placeholders

- **Type**: modify
- **File**: `terraform/environments/lab.tfvars.example`
- **Plan step**: Step 2
- **Depends on**: T002 (real values must have a home in the lab template before removal from example)
- **Parallel-safe**: Yes (modifies a different file from Phases 3–4 and T007)
- **Description**: Edit `terraform/environments/lab.tfvars.example` applying the same placeholder substitutions as T007: IP addresses → placeholders with instructional comments, SSH public key → `<your-ssh-public-key>`, token ID → `<token-id>`, token secret → `<your-token-secret>`. Add a header comment: `# Documentation example — copy to lab.tfvars and replace placeholders. See lab.tfvars.template for CI use.` Preserve the `service_mountpoints` block structure.
- **Acceptance**: `grep -cE '192\.168\.|AAAAC3NzaC1|__INJECT_' terraform/environments/lab.tfvars.example` returns `0`. `grep -c 'service_mountpoints' terraform/environments/lab.tfvars.example` returns `1` (block preserved).
- **Traces to**: FR-003, FR-011, A-005, US-3, SC-003
- [ ] T008 [P] [US3] Revert lab example to safe placeholders in `terraform/environments/lab.tfvars.example`

**Checkpoint**: US-3 complete. Example files are now safe to copy for new operators.

---

## Phase 6: User Story 4 — Key-Set Drift Detection (Priority: P2)

**Goal**: The provisioner detects when the template and rendered file have different sets of top-level configuration keys, and records findings in the validation evidence.

**Independent Test**: Manually add a key to the template that doesn't exist in a rendered file, run the provisioner, and verify `validation.json` contains `"provisioning_gaps": ["<added-key>"]`.

---

### Task T009: Implement key-set drift detection

- **Type**: modify
- **File**: `scripts/lab/lib/tfvars.sh`
- **Plan step**: Step 6
- **Depends on**: T006
- **Parallel-safe**: No (same function as T004–T006, T010–T011)
- **Description**: Add a helper function `_tfvars_extract_top_level_keys()` that takes a file path and echoes one key per line. It extracts lines matching `^[[:space:]]*[a-zA-Z_][a-zA-Z0-9_]*[[:space:]]*=` that are NOT comment lines. Use `grep` + `awk -F'[[:space:]]*=' '{print $1}' | tr -d '[:space:]'`. In `_tfvars_provision_and_write_proof()`, after injection and validation: if a rendered file already exists at `rendered_path`, call `_tfvars_extract_top_level_keys` on both the temp file and the existing rendered file, then compare the two key sets using bash logic. Build `drift_results_json` as a JSON string: `{"provisioning_gaps":[...], "manual_additions":[...]}`. Provisioning gaps = keys in template missing from rendered. Manual additions = keys in rendered missing from template. Drift findings are informational only — do not add to `errors` array or affect `validation_status`.
- **Acceptance**: Given a template with keys `A,B,C` and a rendered file with keys `A,B,D`, the resulting `validation.json` contains `"provisioning_gaps":["C"]` and `"manual_additions":["D"]`. Given identical key sets, both arrays are empty. Given no existing rendered file, `drift_results` is absent or both arrays empty.
- **Traces to**: FR-008, FR-012, US-4, D-006, SC-004
- [ ] T009 [US4] Implement drift detection helper and logic in `scripts/lab/lib/tfvars.sh`

---

## Phase 7: User Story 5 — Non-Secret Value Change Warnings (Priority: P3)

**Goal**: When the provisioner overwrites non-secret values that differ from the existing rendered file, it records the before/after values in the validation evidence for auditability.

**Independent Test**: Manually edit a non-secret field (e.g., `network_gateway`) in an existing rendered file, run the provisioner, verify `validation.json` contains a `change_warnings` entry with `key`, `old_value`, and `new_value`.

---

### Task T010: Add non-secret value change warnings

- **Type**: modify
- **File**: `scripts/lab/lib/tfvars.sh`
- **Plan step**: Step 7
- **Depends on**: T009
- **Parallel-safe**: No (same function)
- **Description**: In `_tfvars_provision_and_write_proof()`, after drift detection: if a rendered file exists at `rendered_path`, extract simple key-value pairs from both the existing rendered file and the temp file (post-injection). Use `awk` to parse lines matching `^[[:space:]]*([a-zA-Z_][a-zA-Z0-9_]*)[[:space:]]*=[[:space:]]*"([^"]*)"` (single-line string assignments only). Skip the `proxmox_api_token_secret` key (secret). For each key where values differ, build a JSON object `{"key":"...","old_value":"...","new_value":"..."}` and append to `change_warnings_json` array. Warnings are informational only — do not add to `errors` array. If no rendered file exists (first render), `change_warnings_json` is `[]`. Also write warnings to `provisioning.txt` in human-readable format (`changed: <key>: old="..." -> new="..."`).
- **Acceptance**: Given a rendered file containing `network_gateway = "192.168.1.99"` and a template with `network_gateway = "192.168.1.1"`, the resulting `validation.json` contains a `change_warnings` entry with `"key":"network_gateway"`, `"old_value":"192.168.1.99"`, `"new_value":"192.168.1.1"`. Given identical non-secret values, `change_warnings` is `[]`. Given no existing rendered file, `change_warnings` is `[]`.
- **Traces to**: FR-009, FR-010, FR-012, US-5, D-004, SC-005
- [ ] T010 [US5] Add non-secret value change warnings in `scripts/lab/lib/tfvars.sh`

---

### Task T011: Update _tfvars_write_validation_json for drift and warnings

- **Type**: modify
- **File**: `scripts/lab/lib/tfvars.sh`
- **Plan step**: Step 8
- **Depends on**: T009, T010
- **Parallel-safe**: No (same function)
- **Description**: Modify `_tfvars_write_validation_json()` to accept two additional parameters: `drift_results_json` (JSON object string or `""`) and `change_warnings_json` (JSON array string or `""`). When non-empty, include them as `"drift_results": <value>` and `"change_warnings": <value>` in the output JSON. When empty, write `"drift_results": {}` and `"change_warnings": []` as defaults. Update ALL call sites of `_tfvars_write_validation_json()` (the happy path and the early-exit error path for missing template) to pass the new parameters — use empty strings for the error path.
- **Acceptance**: `python3 -c "import json; d=json.load(open('validation.json')); assert 'drift_results' in d and 'change_warnings' in d"` succeeds on a sample output produced by the provisioner. The early-exit path (missing template) still writes a valid JSON file (with empty drift/warnings defaults). `shellcheck scripts/lab/lib/tfvars.sh` exits 0.
- **Traces to**: FR-012, US-4, US-5, SC-004, SC-005
- [ ] T011 [US5] Update `_tfvars_write_validation_json` signature and call sites in `scripts/lab/lib/tfvars.sh`

**Checkpoint**: US-4 and US-5 complete. Evidence artifact now includes drift results and change warnings.

---

## Phase 8: Tests — Evidence-Artifact Contract Tests

**Purpose**: Pytest contract tests validate sentinel detection, evidence format, drift reporting, and file content correctness using inline string fixtures plus committed file reads.

---

### Task T012: Create evidence-artifact contract test module

- **Type**: create
- **File**: `python/tests/orchestrator/test_tfvars_template.py`
- **Plan step**: Step 10
- **Depends on**: T001, T002, T003, T007, T008
- **Parallel-safe**: Yes (new file, no conflicts with other in-progress tasks)
- **Description**: Create `python/tests/orchestrator/test_tfvars_template.py` following the inline string fixture pattern from `test_deploy_readiness.py` and `test_tfvars_mountpoints.py`. Implement exactly 8 test functions:
  1. `test_sentinel_detection_in_template`: Given a CI template string, verify `__INJECT_TOKEN_SECRET__` appears exactly once in a non-comment value position.
  2. `test_sentinel_detection_after_injection`: Given a rendered string (sentinels replaced), verify no `__INJECT_[A-Z_]+__` patterns remain in non-comment positions.
  3. `test_sentinel_ignored_in_comments`: Given content with a sentinel only in a comment line (`# __INJECT_TOKEN_SECRET__`), verify the sentinel is NOT detected in value positions (grep on non-comment lines returns empty).
  4. `test_evidence_format_with_drift`: Given a `validation.json` content string with `drift_results`, verify required top-level fields present and `drift_results.provisioning_gaps` / `drift_results.manual_additions` are lists.
  5. `test_evidence_format_with_change_warnings`: Given a `validation.json` string with `change_warnings`, verify each entry has `key`, `old_value`, `new_value` string fields.
  6. `test_evidence_format_backward_compatible`: Given a `validation.json` string WITHOUT `drift_results` or `change_warnings` (old format), verify it still passes basic field checks (`timestamp`, `validation_status`, `token_id`, `secret_present` all present).
  7. `test_example_file_no_real_values`: Read `terraform/environments/prod.tfvars.example` and verify it contains no `192.168.` patterns, no `AAAAC3NzaC1` (SSH key prefix), and no `__INJECT_` patterns.
  8. `test_template_file_has_sentinel`: Read `terraform/environments/prod.tfvars.template` and verify it contains exactly one `__INJECT_TOKEN_SECRET__` occurrence and the literal string `terraform@pve!terraform-token`.
- **Acceptance**: `PYTHONPATH=python/src python3 -m pytest python/tests/orchestrator/test_tfvars_template.py -v` exits 0 with exactly 8 tests collected and 0 failures.
- **Traces to**: FR-001, FR-002, FR-003, FR-006, FR-008, FR-009, FR-012, SC-002
- [ ] T012 [P] Create `python/tests/orchestrator/test_tfvars_template.py` with 8 contract tests

---

## Phase 9: Polish & Verification

**Purpose**: Final gate confirming zero regressions and all acceptance criteria met end-to-end.

---

### Task T013: Run full verification suite

- **Type**: test
- **File**: N/A (no new files — runs existing commands)
- **Plan step**: Step 11
- **Depends on**: T001–T012, T004a, T004b (all tasks)
- **Parallel-safe**: No (final gate)
- **Description**: Execute all seven verification checks in order: (1) Full pytest suite; (2) ShellCheck on tfvars.sh; (3) Template sentinel count check; (4) Example file clean check; (5) Mount-point behavioral equivalence tests; (6) No hardcoded `prod-tfvars` in evidence consumers; (7) No `192.168.20` in lab template.
- **Acceptance**: All seven checks exit 0 with zero failures:
  1. `PYTHONPATH=python/src python3 -m pytest python/tests/ -ra` — 0 failures (includes T012 tests and existing suites)
  2. `shellcheck scripts/lab/lib/tfvars.sh` — 0 errors/warnings
  3. `grep -c '__INJECT_TOKEN_SECRET__' terraform/environments/prod.tfvars.template` returns `1`
  4. `grep -cE '192\.168\.|AAAAC3NzaC1|__INJECT_' terraform/environments/prod.tfvars.example` returns `0`
  5. `PYTHONPATH=python/src python3 -m pytest python/tests/orchestrator/test_tfvars_mountpoints.py -v` — 0 failures (behavioral equivalence preserved)
  6. `grep -c 'prod-tfvars' scripts/lab/verify_evidence.py` returns `0` (env-parameterized, not hardcoded)
  7. `grep -c '192.168.20' terraform/environments/lab.tfvars.template` returns `0` (correct subnet)
- **Traces to**: SC-002, SC-006
- [ ] T013 Run full verification suite (all 5 checks)

---

## Dependency Graph

```
T001 (prod template)   ─────────────────────────────────────────┐
T002 (lab template)    ─────────────────────────────────────────┤
                                                                 ↓
                                            T004 (lookup chain) → T004a (rename + wire lab)
                                                                        ↓
                                                              T005 (injection) → T006 (validation)
                                                                                        ↓
                                                                                T009 (drift detection)
                                                                                        ↓
                                                                                T010 (change warnings)
                                                                                        ↓
                                                                                T011 (evidence writing)

T003 (schema) ──────────────────────────────┐
T004a (rename + wire lab) ──────────────────┼──→ T004b (evidence consumers)
                                            │
T007 (prod example)    ─────────────────────┤
T008 (lab example)     ─────────────────────┤
T001 (prod template)   ─────────────────────┼──→ T012 (tests) ──┐
T002 (lab template)    ─────────────────────┘                   ↓
T004b, T012, T011 ──────────────────────────────────────────────→ T013 (verify)
```

## Implementation Order

1. **T001, T002, T003** — Run in parallel (all independent, no shared files)
2. **T007, T008** — Run in parallel with T001–T003 or immediately after (different files)
3. **T004** — After T001 and T002 complete (provisioner needs templates to exist)
4. **T004a** — After T004 (rename function, remove prod-only guard, wire lab)
5. **T004b** — After T004a and T003 (update evidence consumers for env-parameterized paths)
6. **T005** — After T004a (same function, sequential)
7. **T006** — After T005 (same function, sequential)
8. **T009** — After T006 (same function, sequential)
9. **T010** — After T009 (same function, sequential)
10. **T011** — After T009 and T010 (same function, sequential)
11. **T012** — After T001–T003, T007–T008 (reads committed template + example files, uses inline fixtures for bash logic)
12. **T013** — After all tasks complete (verification gate)

## Parallel Example: Fastest Execution Path

```bash
# Simultaneous (no dependencies):
Task: "T001 — Create terraform/environments/prod.tfvars.template"
Task: "T002 — Create terraform/environments/lab.tfvars.template"
Task: "T003 — Extend scripts/lab/contracts/evidence-tfvars-proof.schema.json"
Task: "T007 — Revert terraform/environments/prod.tfvars.example"
Task: "T008 — Revert terraform/environments/lab.tfvars.example"

# After T001 + T002 complete:
Task: "T004 — Update provisioner template lookup in scripts/lab/lib/tfvars.sh"

# After T004:
Task: "T004a — Rename provisioner, remove prod guard, wire lab"

# After T004a + T003:
Task: "T004b — Update evidence consumers (profiles, verifier, fixtures)"

# Sequential provisioner chain (T005 → T011, after T004a):
Task: "T005 → T006 → T009 → T010 → T011 (all in scripts/lab/lib/tfvars.sh)"

# After T001–T003, T007–T008 complete (independent of T004–T011):
Task: "T012 — Create python/tests/orchestrator/test_tfvars_template.py"

# Final gate:
Task: "T013 — Run full verification suite"
```

## Implementation Strategy

### MVP First (P1 Stories Only)

1. Complete T001, T002 (template files — prerequisite for provisioner)
2. Complete T004, T004a (provisioner lookup + rename + wire lab)
3. Complete T005 (sentinel injection)
4. Complete T006 (post-injection validation — safety net)
5. **STOP and VALIDATE**: P1 stories done. Run `PYTHONPATH=python/src python3 -m pytest python/tests/ -ra` and `shellcheck scripts/lab/lib/tfvars.sh`.
6. Deliver P1 increment — production incidents blocked at this point.

### Incremental Delivery

1. T001–T003 + T004–T004a–T005–T006 → P1 MVP (zero sentinel leakage guaranteed, lab parity)
2. T004b → Evidence consumer updates (env-parameterized paths, fixtures)
3. T007–T008 → P2 US-3 (safe documentation examples)
4. T009 → P2 US-4 (drift detection)
5. T010–T011 → P3 US-5 (change warnings + complete evidence writing)
6. T012 → Evidence contract tests (validates all stories via pytest)
7. T013 → Full verification gate

## Constitution Check (pre-implementation)

| Principle | Status | Note |
|-----------|--------|------|
| I. Spec-Driven Workflow | ✅ PASS | All 16 tasks trace to plan.md steps and spec FRs/Goals |
| II. Secrets Policy | ✅ PASS | Sentinels are placeholders; no secrets in committed files |
| III. Separation of Concerns | ✅ PASS | Provisioner layer only — no Terraform or Ansible changes |
| IV. Dual-Provisioning Parity | ✅ PASS | Provisioner changes apply identically in CI and laptop |
| Token Privilege Tiers | ✅ PASS | Token ID literal in template (non-secret), secret via env var only |
| Test-Driven Changes | ✅ PASS | T012 creates pytest contract tests; T013 runs ShellCheck |
