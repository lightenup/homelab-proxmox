# Implementation Plan: TFvars Template Separation

**Branch**: `038-tfvars-template-separation` | **Date**: 2026-02-23 | **Spec**: `specs/038-tfvars-template-separation/spec.md`
**Input**: Feature specification from `/specs/038-tfvars-template-separation/spec.md`

## Summary

The `.tfvars.example` files currently serve as both human-readable documentation and live CI templates, causing production incidents when documentation placeholders are injected as real values. This plan separates these concerns by introducing dedicated `.tfvars.template` files for CI (containing real non-secret values + sentinel markers for secrets) and reverting `.tfvars.example` files to safe documentation placeholders. The provisioner (`scripts/lab/lib/tfvars.sh`) is reworked to use sentinel-based injection, post-injection validation, key-set drift detection, and non-secret value change warnings — all recorded in the existing validation evidence artifact.

## Technical Context

**Language/Version**: Bash (POSIX-compatible, runs on Debian 12 Proxmox host)
**Primary Dependencies**: `sed`, `awk`, `grep`, `sha256sum`/`shasum` (standard POSIX tools)
**Storage**: N/A (evidence artifacts are flat files in the evidence pack)
**Testing**: pytest (Python test harness at `python/tests/`), ShellCheck for bash linting, `ci-verify.sh` for evidence pack verification
**Target Platform**: Proxmox VE host (Debian 12, Linux amd64) + developer laptops (macOS/Linux)
**Project Type**: Infrastructure-as-Code — bash provisioner with Python test harness
**Performance Goals**: N/A (provisioner runs once per deployment; no latency-critical path)
**Constraints**: No Terraform changes, no Ansible changes, no workflow YAML changes (per spec Out of Scope). No HCL parsing (spec explicitly excludes it).
**Scale/Scope**: 2 environments (lab, prod), 1 sentinel value, 12 top-level tfvars keys

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| **I. Spec-Driven Workflow** | ✅ PASS | All changes driven from spec 038; plan traces every step to a spec FR/AC. Feature directory is `specs/038-tfvars-template-separation/`. |
| **II. Secrets Policy** | ✅ PASS | Sentinel markers (`__INJECT_TOKEN_SECRET__`) are placeholders, not secrets. Real secrets only exist in rendered files (gitignored) and environment variables. Documentation examples contain only safe placeholders. No secrets in committed files. |
| **III. Separation of Concerns** | ✅ PASS | All changes are in the provisioner layer (`scripts/lab/lib/tfvars.sh`) and configuration files (`terraform/environments/`). No Terraform resource changes. No Ansible role changes. The provisioner owns rendering; Terraform owns infrastructure. |
| **IV. Dual-Provisioning Parity** | ✅ PASS | `pve-service-deploy` is the single entrypoint for both CI and laptop deploys. The provisioner changes apply identically in both contexts. Sentinel injection uses environment variables available in both CI (GitHub Actions secret) and laptop (shell export). Per A-006. |
| **Token Privilege Tiers** | ✅ PASS | Tier 1 token ID (`terraform@pve!terraform-token`) remains a literal value enforced by the provisioner. Token secret is Tier 1 (Terraform API credential). No Tier 2 or Tier 3 usage. Provisioner rendering is orchestrator-layer, consistent with the tier model. |
| **Provider Strategy** | ✅ PASS | No Terraform provider changes. Telmate provider untouched. |
| **Test-Driven Changes** | ✅ PASS | New Python evidence-artifact contract tests validate sentinel detection, drift results, and evidence format. ShellCheck validates bash changes. |
| **Local Workflow Testing** | ✅ PASS | No workflow YAML changes, so `act` validation not needed. |

**Post-design re-check**: All principles still PASS. No violations.

## Project Structure

### Documentation (this feature)

```text
specs/038-tfvars-template-separation/
├── spec.md              # Feature specification (exists)
├── plan.md              # This file
├── research.md          # Phase 0 output (created)
├── data-model.md        # Phase 1 output (created)
├── quickstart.md        # Phase 1 output (created)
├── contracts/           # Phase 1 output (created)
│   └── README.md        # Evidence schema extension documentation
├── checklists/
│   └── requirements.md  # Existing checklist
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
terraform/environments/
├── prod.tfvars.template     — NEW: CI template for prod (real values + sentinel)
├── lab.tfvars.template      — NEW: CI template for lab (future use, structural parity)
├── prod.tfvars.example      — MODIFIED: reverted to safe documentation placeholders
├── lab.tfvars.example       — MODIFIED: reverted to safe documentation placeholders
└── lab.tfvars               — UNCHANGED: existing lab tfvars (committed, manually managed)

scripts/lab/
├── lib/tfvars.sh            — MODIFIED: sentinel injection, validation, drift, warnings
└── contracts/evidence-tfvars-proof.schema.json — MODIFIED: extended with drift + warnings fields

python/tests/orchestrator/
└── test_tfvars_template.py  — NEW: evidence-artifact contract tests for sentinel, drift, evidence format
```

**Structure Decision**: All production changes are confined to the provisioner library (`tfvars.sh`) and configuration files (`terraform/environments/`). The new Python test module validates evidence artifact contracts — the same pattern used by `test_deploy_readiness.py` and `test_tfvars_mountpoints.py`. No new Python source modules are needed; the provisioner logic stays in bash.

## File Structure

```
terraform/environments/prod.tfvars.template      — NEW: prod CI template (real values + __INJECT_TOKEN_SECRET__)
terraform/environments/lab.tfvars.template        — NEW: lab CI template (real values + __INJECT_TOKEN_SECRET__, future use)
terraform/environments/prod.tfvars.example        — MODIFIED: safe placeholders, instructional comments
terraform/environments/lab.tfvars.example         — MODIFIED: safe placeholders, instructional comments
scripts/lab/lib/tfvars.sh                         — MODIFIED: sentinel injection, post-injection validation, drift detection, change warnings
scripts/lab/contracts/evidence-tfvars-proof.schema.json — MODIFIED: add drift_results + change_warnings (optional fields)
python/tests/orchestrator/test_tfvars_template.py — NEW: evidence-artifact contract tests
```

## Architecture Overview

### Component Layout

The changes touch three areas:

1. **Configuration files** (`terraform/environments/`): New `.tfvars.template` files are the authoritative CI templates. Existing `.tfvars.example` files are reverted to documentation-only role with safe placeholders.

2. **Provisioner library** (`scripts/lab/lib/tfvars.sh`): The `_tfvars_provision_prod_and_write_proof()` function is extended with:
   - **Template lookup** (three-tier): env var → `.tfvars.template` → `.tfvars.example` (fallback)
   - **Sentinel injection**: Replace `__INJECT_TOKEN_SECRET__` with runtime secret (skip comments)
   - **Post-injection validation**: Scan for remaining `__INJECT_*__` patterns in value positions
   - **Key-set drift detection**: Compare top-level keys between template and rendered file
   - **Non-secret value change warnings**: Compare simple values, log old/new in evidence
   - **Extended evidence**: Write drift results and change warnings to `validation.json`

3. **Tests** (`python/tests/orchestrator/test_tfvars_template.py`): Evidence-artifact contract tests that validate the format and semantics of the extended validation evidence, sentinel detection, and drift reporting. Uses inline string fixtures (same pattern as `test_tfvars_mountpoints.py`).

### Data Flow

**Current** provisioner flow (PROBLEMATIC):
```
Template source: prod.tfvars.example (dual-use: docs AND CI template)
    → Copy to temp file
    → sed: replace proxmox_api_token_id line with hardcoded value
    → sed: replace proxmox_api_token_secret line with env var value
    → Validate: check token ID, check secret non-empty
    → Write validation.json evidence
    → Move to rendered path
```

The sed-based replacement is fragile (depends on exact field name matching and whitespace) and the example file contains real infrastructure values that become the rendered output.

**New** provisioner flow:
```
Template source: prod.tfvars.template (preferred) or prod.tfvars.example (fallback)
    │
    ├── Copy template to temp file
    │
    ├── [Sentinel injection]
    │   └── sed: replace __INJECT_TOKEN_SECRET__ with env var (skip comment lines)
    │
    ├── [Token ID enforcement]
    │   └── sed: ensure proxmox_api_token_id = "terraform@pve!terraform-token"
    │
    ├── [Post-injection sentinel validation]  ← NEW
    │   └── grep: scan non-comment lines for remaining __INJECT_*__ patterns
    │   └── FAIL if any found → list each un-injected sentinel
    │
    ├── [Existing validations]
    │   ├── Check token ID value
    │   └── Check secret non-empty and non-placeholder
    │
    ├── [Key-set drift detection]  ← NEW
    │   ├── Extract top-level keys from template
    │   ├── Extract top-level keys from existing rendered file (if exists)
    │   └── Report provisioning_gaps and manual_additions
    │
    ├── [Non-secret value change warnings]  ← NEW
    │   ├── Compare simple values in existing rendered file vs template
    │   └── Log warnings (key, old_value, new_value)
    │
    ├── Write extended validation.json evidence (with drift + warnings)
    │
    └── Move temp file to rendered path (atomic)
```

### Validate-Only Path (FR-007)

When no secret is available and a rendered file already exists:
```
No secret available + rendered file exists at ${TFVARS_DIR}/prod.tfvars
    → template_path = rendered file (validate only)
    → Skip sentinel injection (no sentinel expected in rendered file)
    → Validate: token ID, secret presence
    → Do NOT overwrite
    → Write evidence (validation only, no drift/change data)
```

This path is preserved unchanged from the current behavior.

## Technology Choices

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Sentinel format | `__INJECT_<NAME>__` | Self-documenting, unambiguous, no conflict with HCL syntax (D-001). |
| Sentinel injection | `sed` with comment-line guard | Existing pattern in provisioner. Guard `/^[[:space:]]*#/!` prevents replacement in comments (spec edge case). |
| Post-injection validation | `grep -E '__INJECT_[A-Z_]+__'` on non-comment lines | Simple, reliable detection of remaining sentinels. No HCL parser needed. |
| Key extraction | `awk` on `key = value` lines | Extracts top-level HCL keys without full HCL parsing. Sufficient for drift detection (D-006). |
| Value comparison | `awk` to extract key-value pairs from simple assignments | Only compares single-line string/number values. Complex structures (maps, lists) are excluded — no HCL parser needed. |
| Evidence format | Extended JSON (`validation.json`) | Backward-compatible extension of existing schema. New fields are optional (A-002). |
| Test framework | pytest (Python) | Existing test harness. Evidence-artifact contract tests follow `test_deploy_readiness.py` pattern. |
| Bash lint | ShellCheck | Existing CI lint for all bash scripts. |

## Implementation Steps

### Step 1: Create CI template files for prod and lab

- **Files**: `terraform/environments/prod.tfvars.template`, `terraform/environments/lab.tfvars.template`
- **Description**: Create dedicated CI template files containing:
  - Real non-secret configuration values for each environment
  - `__INJECT_TOKEN_SECRET__` sentinel for the token secret field
  - Token ID as a literal value (`terraform@pve!terraform-token`)
  - Header comment identifying the file as a CI template
  - The prod template uses values from the current `prod.tfvars.example` (192.168.1.x network)
  - The lab template uses values from the committed `lab.tfvars` (192.168.20.x network)
  - Lab template is created for structural parity (D-005) but is not consumed by the provisioner today (spec Out of Scope)
- **Dependencies**: None
- **Parallel-safe**: Yes
- **Done-condition**: Both files exist, contain `__INJECT_TOKEN_SECRET__` exactly once, and contain no real secret values. `grep -c '__INJECT_TOKEN_SECRET__' terraform/environments/prod.tfvars.template` returns `1`.
- **Traces to**: FR-001, FR-002, FR-011, D-003, D-005

### Step 2: Revert documentation examples to safe placeholders

- **Files**: `terraform/environments/prod.tfvars.example`, `terraform/environments/lab.tfvars.example`
- **Description**: Replace all real infrastructure values with clearly marked generic placeholders:
  - IP addresses → `<pve-api-url>`, `<gateway-ip>`, `<service-ip>/24`
  - SSH public keys → `<your-ssh-public-key>`
  - Token ID → `<token-id>` with comment showing the expected format
  - Token secret → `<your-token-secret>`
  - Add instructional comments explaining each field and where to find real values
  - Add header comment identifying the file as a documentation example
- **Dependencies**: Step 1 (template files must exist first so real values have a home)
- **Parallel-safe**: Yes (parallel with Step 1 since they modify different files)
- **Done-condition**: Neither example file contains any of: `192.168.`, `AAAAC3NzaC1` (SSH key prefix), or `__INJECT_`. `grep -cE '192\.168\.|AAAAC3NzaC1|__INJECT_' terraform/environments/prod.tfvars.example` returns `0`.
- **Traces to**: FR-003, FR-011, A-005, US-3

### Step 3: Update provisioner template lookup to three-tier chain

- **Files**: `scripts/lab/lib/tfvars.sh`
- **Description**: Modify the candidate list in `_tfvars_provision_prod_and_write_proof()`:
  - Replace the current candidates (`prod.tfvars`, `prod.tfvars.example`) with: `prod.tfvars.template`, `prod.tfvars.example`
  - Preserve `PROD_TFVARS_TEMPLATE` env var as the highest-priority override (FR-004 AC-1.3)
  - When the env var points to a nonexistent file, fall back to file-system discovery (spec edge case) and document the fallback in evidence
  - Record the actual template source in the evidence artifact (which file was used)
  - The "validate existing" path (no secret + rendered file exists) remains unchanged
- **Dependencies**: Step 1 (template files must exist for the new lookup to find them)
- **Parallel-safe**: No (modifies the same function as Steps 4–7)
- **Done-condition**: When `prod.tfvars.template` exists, the provisioner selects it over `prod.tfvars.example`. When only `prod.tfvars.example` exists, backward compatibility is maintained.
- **Traces to**: FR-004, D-002, SC-006

### Step 4: Implement sentinel-based injection

- **Files**: `scripts/lab/lib/tfvars.sh`
- **Description**: Replace the current sed-based field-name matching with sentinel replacement:
  - When a secret is available, replace `__INJECT_TOKEN_SECRET__` with the secret value on non-comment lines
  - Use `sed` with address guard: `/^[[:space:]]*#/! s|__INJECT_TOKEN_SECRET__|${secret_escaped}|g`
  - Keep the existing token ID enforcement (hardcoded `proxmox_api_token_id = "terraform@pve!terraform-token"`) via sed — this is unchanged
  - When processing a `.tfvars.example` fallback (no sentinels present), the injection step is a no-op — the existing sed-based field replacement is preserved for backward compatibility
- **Dependencies**: Step 3
- **Parallel-safe**: No (same function)
- **Done-condition**: Given `PROXMOX_API_TOKEN_SECRET=test123` and a template with `__INJECT_TOKEN_SECRET__`, the rendered output contains `test123` and no sentinel markers. Given a comment `# __INJECT_TOKEN_SECRET__ is replaced at runtime`, the comment is unchanged.
- **Traces to**: FR-005, D-001, D-003

### Step 5: Add post-injection sentinel validation

- **Files**: `scripts/lab/lib/tfvars.sh`
- **Description**: After injection, scan the rendered output for remaining sentinel markers:
  - Use `grep -E '__INJECT_[A-Z_]+__'` on non-comment lines (skip lines starting with `#`)
  - If any sentinels remain, add each to the `errors` array and set `validation_status="fail"`
  - Error message format: `"Un-injected sentinel: __INJECT_TOKEN_SECRET__ (source: PROXMOX_API_TOKEN_SECRET not set)"`
  - This check runs AFTER sentinel injection and BEFORE the existing token ID / secret validation
  - When using a `.tfvars.example` fallback (no sentinels), this check is benign (no sentinels to find)
- **Dependencies**: Step 4
- **Parallel-safe**: No (same function)
- **Done-condition**: Given a template with `__INJECT_TOKEN_SECRET__` and no `PROXMOX_API_TOKEN_SECRET` set, the provisioner fails with exit code 1 and `validation_errors` includes `"Un-injected sentinel: __INJECT_TOKEN_SECRET__"`.
- **Traces to**: FR-006, US-2, SC-002

### Step 6: Add key-set drift detection

- **Files**: `scripts/lab/lib/tfvars.sh`
- **Description**: Add a helper function `_tfvars_extract_top_level_keys()` and drift detection logic:
  - Extract top-level HCL keys from a file: lines matching `^[[:space:]]*[a-zA-Z_][a-zA-Z0-9_]*[[:space:]]*=` that are NOT comments. Extract the key name (left of `=`).
  - Compare key sets between the template and the existing rendered file (if it exists)
  - Report `provisioning_gaps` (in template, not in rendered) and `manual_additions` (in rendered, not in template)
  - Write results to the `drift_results` field of `validation.json`
  - If no existing rendered file exists (first render), skip drift detection
  - Drift detection runs AFTER injection and validation, BEFORE writing the final evidence
  - Drift findings are informational (warnings, not failures) — they do not affect `validation_status`
- **Dependencies**: Step 5
- **Parallel-safe**: No (same function)
- **Done-condition**: Given a template with keys A,B,C and a rendered file with keys A,B,D, the evidence contains `"provisioning_gaps": ["C"]` and `"manual_additions": ["D"]`. Given identical key sets, both arrays are empty.
- **Traces to**: FR-008, FR-012, US-4, D-006

### Step 7: Add non-secret value change warnings

- **Files**: `scripts/lab/lib/tfvars.sh`
- **Description**: Add logic to compare non-secret simple values:
  - Extract simple `key = "value"` pairs from both the existing rendered file and the template (after injection)
  - Skip: the `proxmox_api_token_secret` key (secret), keys whose values span multiple lines (complex structures), and comment lines
  - For each key where values differ, record `{key, old_value, new_value}` in `change_warnings`
  - Write results to the `change_warnings` field of `validation.json`
  - If no existing rendered file exists (first render), skip — no changes to warn about
  - Warnings are informational only — the provisioner still overwrites (template is source of truth)
  - Warnings are also written to `provisioning.txt` for human-readable evidence
- **Dependencies**: Step 6
- **Parallel-safe**: No (same function)
- **Done-condition**: Given a rendered file with `network_gateway = "192.168.1.99"` and a template with `network_gateway = "192.168.1.1"`, the evidence contains a change warning naming the key and showing both values. Given no existing rendered file, `change_warnings` is empty.
- **Traces to**: FR-009, FR-010, FR-012, US-5, D-004

### Step 8: Update evidence writing to include new fields

- **Files**: `scripts/lab/lib/tfvars.sh`
- **Description**: Modify `_tfvars_write_validation_json()` to accept and write the new optional fields:
  - Add `drift_results` parameter (JSON object string or empty)
  - Add `change_warnings` parameter (JSON array string or empty)
  - When these fields have data, include them in the output JSON
  - When these fields are empty, either omit them or write empty defaults (`{}` and `[]`)
  - Update all call sites of `_tfvars_write_validation_json()` to pass the new parameters
  - For the error path (missing template), pass empty drift/warning data
- **Dependencies**: Steps 6, 7
- **Parallel-safe**: No (same function)
- **Done-condition**: The generated `validation.json` matches the extended schema. `python3 -c "import json; d=json.load(open('validation.json')); assert 'drift_results' in d"` succeeds on a sample output.
- **Traces to**: FR-012

### Step 9: Extend evidence JSON schema

- **Files**: `scripts/lab/contracts/evidence-tfvars-proof.schema.json`
- **Description**: Add the new optional fields to the JSON Schema:
  - `drift_results`: object with `provisioning_gaps` (array of strings) and `manual_additions` (array of strings)
  - `change_warnings`: array of objects, each with `key`, `old_value`, `new_value` (all strings)
  - Both fields are NOT in `required` — backward compatibility with existing evidence packs
  - Update the schema examples to show the new fields
- **Dependencies**: None
- **Parallel-safe**: Yes
- **Done-condition**: `python3 -c "import json; json.load(open('scripts/lab/contracts/evidence-tfvars-proof.schema.json'))"` succeeds. Schema validates both old-format (no new fields) and new-format (with new fields) evidence.
- **Traces to**: FR-012, A-002

### Step 10: Add Python evidence-artifact contract tests

- **Files**: `python/tests/orchestrator/test_tfvars_template.py`
- **Description**: Create a pytest module with inline string fixtures (same pattern as `test_deploy_readiness.py`). Tests:
  1. **test_sentinel_detection_in_template**: Given a CI template content string, verify sentinel `__INJECT_TOKEN_SECRET__` is present exactly once in a value position (not in comments).
  2. **test_sentinel_detection_after_injection**: Given a rendered content string (sentinels replaced), verify no `__INJECT_*__` patterns remain in value positions.
  3. **test_sentinel_ignored_in_comments**: Given content with a sentinel in a comment, verify the sentinel is NOT detected in value positions.
  4. **test_evidence_format_with_drift**: Given a validation.json content string with drift results, verify required fields present and drift arrays contain expected keys.
  5. **test_evidence_format_with_change_warnings**: Given a validation.json content string with change warnings, verify each warning has `key`, `old_value`, `new_value`.
  6. **test_evidence_format_backward_compatible**: Given a validation.json content string WITHOUT drift/change fields (old format), verify it still passes basic structure checks.
  7. **test_example_file_no_real_values**: Given the content of `prod.tfvars.example`, verify it contains no real IP addresses (192.168.x.x pattern) and no real SSH keys.
  8. **test_template_file_has_sentinel**: Given the content of `prod.tfvars.template`, verify it contains `__INJECT_TOKEN_SECRET__` and real non-secret values.
- **Dependencies**: Steps 1, 2, 9 (need template/example files and schema to exist)
- **Parallel-safe**: Yes
- **Done-condition**: `PYTHONPATH=python/src python3 -m pytest python/tests/orchestrator/test_tfvars_template.py -v` passes with 8 tests, 0 failures.
- **Traces to**: FR-001, FR-002, FR-003, FR-006, FR-008, FR-012, SC-002

### Step 11: Run verification suite

- **Files**: (no new files)
- **Description**: Verify no regressions:
  1. `PYTHONPATH=python/src python3 -m pytest python/tests/ -ra` — all existing + new tests pass
  2. `shellcheck scripts/lab/lib/tfvars.sh` — no new warnings/errors
  3. Verify template files have correct sentinel count: `grep -c '__INJECT_TOKEN_SECRET__' terraform/environments/prod.tfvars.template` returns `1`
  4. Verify example files have no real values: `grep -cE '192\.168\.' terraform/environments/prod.tfvars.example` returns `0`
  5. Verify existing orchestrator tests still pass (test_orchestrator_unit.py, test_tfvars_mountpoints.py)
- **Dependencies**: Steps 1–10
- **Parallel-safe**: No (final gate)
- **Done-condition**: All 5 verification checks pass. Zero test failures.
- **Traces to**: SC-002, SC-006

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Backward compatibility break on branches without `.tfvars.template` | CI pipeline fails on older branches | `.tfvars.example` fallback preserved in lookup chain (D-002). Step 3 explicitly tests this path. |
| Sentinel replacement leaks secret into comments | Secret exposed in version-controlled file | `sed` guard skips comment lines. CI templates are version-controlled; rendered files are gitignored. The guard prevents accidental replacement in comments. |
| sed portability between macOS and Linux | Different `sed -i` syntax | Existing provisioner already handles this with `.bak` extension + cleanup (pattern established in current codebase). |
| Key extraction misses complex HCL structures | Drift detection misses nested key differences | By design: drift detection only covers top-level keys (D-006). Nested structures change infrequently and are compared as opaque blocks. |
| Existing CI fixtures become invalid after schema extension | `ci-verify.sh` rejects old evidence packs | New schema fields are optional (not in `required`). Existing fixtures remain valid. |
| Operators accidentally use `.tfvars.template` as a manual starting point | Sentinel markers end up in local tfvars | Template file header comment explicitly warns "CI template — do not copy for local use. See prod.tfvars.example instead." |

## Testing Strategy

### Evidence-Artifact Contract Tests (automated, pytest)

- **`python/tests/orchestrator/test_tfvars_template.py`**: 8 tests validating sentinel detection, evidence format, drift results, change warnings, backward compatibility, and file content correctness. Uses inline string fixtures and reads actual committed files (template + example).

### File Content Validation (automated, grep)

- Template files contain exactly one sentinel marker
- Example files contain zero real IP addresses, SSH keys, or sentinel markers
- Validates the separation between CI templates and documentation examples

### Bash Lint (automated, ShellCheck)

- `shellcheck scripts/lab/lib/tfvars.sh` — catches syntax, quoting, and portability issues in the modified provisioner.

### Existing Test Suite (automated, pytest)

- All existing tests in `python/tests/` continue to pass — validates no regressions in evidence handling, mountpoint parsing, orchestrator logic, etc.

### Integration Verification (manual, CI pipeline)

- Trigger a PROD plan (`pve-service-deploy plan --environment prod --service <any>`) and verify:
  - The provisioner discovers and uses `prod.tfvars.template`
  - Evidence `validation.json` contains `template_source` pointing to the template file
  - Sentinel injection succeeds when `PROXMOX_API_TOKEN_SECRET` is set
  - Evidence contains `drift_results` and `change_warnings` fields

### Coverage Target

- All 12 FRs have at least one test or verification step tracing to them
- All 6 success criteria (SC-001 through SC-006) have a corresponding test or verification
- Python tests cover the evidence contract; ShellCheck covers the bash implementation; manual CI covers the end-to-end flow

## Complexity Tracking

No constitution violations to justify. All principles PASS.

## Appendix: Requirement Traceability

| Step | FRs Covered | User Stories | SCs Covered |
|------|-------------|--------------|-------------|
| Step 1 | FR-001, FR-002, FR-011 | US-1 | SC-001 |
| Step 2 | FR-003, FR-011 | US-3 | SC-003 |
| Step 3 | FR-004 | US-1 | SC-006 |
| Step 4 | FR-005 | US-1 | SC-001 |
| Step 5 | FR-006 | US-2 | SC-002 |
| Step 6 | FR-008, FR-012 | US-4 | SC-004 |
| Step 7 | FR-009, FR-010, FR-012 | US-5 | SC-005 |
| Step 8 | FR-012 | US-4, US-5 | SC-004, SC-005 |
| Step 9 | FR-012 | US-4, US-5 | — |
| Step 10 | FR-001–FR-003, FR-006, FR-008, FR-012 | US-1–US-5 | SC-002 |
| Step 11 | — | — | SC-002, SC-006 |

### FR Coverage Check

| FR | Steps | Verified By |
|----|-------|-------------|
| FR-001 | 1, 10 | test_template_file_has_sentinel |
| FR-002 | 1, 10 | test_template_file_has_sentinel |
| FR-003 | 2, 10 | test_example_file_no_real_values |
| FR-004 | 3 | Integration test (lookup order) |
| FR-005 | 4 | test_sentinel_detection_after_injection |
| FR-006 | 5, 10 | test_sentinel_detection_after_injection, done-condition Step 5 |
| FR-007 | (preserved) | Existing validate-only path unchanged |
| FR-008 | 6, 10 | test_evidence_format_with_drift |
| FR-009 | 7, 10 | test_evidence_format_with_change_warnings |
| FR-010 | 7 | Done-condition Step 7 (template overwrites) |
| FR-011 | 1, 2 | File existence check Step 11 |
| FR-012 | 6, 7, 8, 9, 10 | test_evidence_format_with_drift, test_evidence_format_with_change_warnings |
