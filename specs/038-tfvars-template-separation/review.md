# Review: TFvars Template Separation

## Verdict: APPROVED

## Test Results
- **Tests run**: 74
- **Tests passed**: 74
- **Coverage**: 89.85% (required: 80%)
- **Test command**: `scripts/ci/python-tests.sh`

Additional gate results:
- `shellcheck scripts/lab/lib/tfvars.sh` — 0 warnings/errors
- `grep -c '__INJECT_TOKEN_SECRET__' terraform/environments/prod.tfvars.template` → `1` ✅
- `grep -cE '192\.168\.|AAAAC3NzaC1|__INJECT_' terraform/environments/prod.tfvars.example` → `0` ✅
- `grep -c 'prod-tfvars' scripts/lab/verify_evidence.py` → `0` ✅
- `grep -c '192.168.20' terraform/environments/lab.tfvars.template` → `0` ✅

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| US-1 AC-1.1 | Rendered tfvars contains no sentinels when all secrets provided | PASS | `test_sentinel_detection_after_injection`; `tfvars.sh:220-235` sentinel injection + validation |
| US-1 AC-1.2 | Provisioner falls back to `.tfvars.example` when no `.tfvars.template` exists | PASS | `tfvars.sh:144-148`; candidates order: template → example |
| US-1 AC-1.3 | Explicit template path via `PROD_TFVARS_TEMPLATE` env var takes precedence | PASS | `tfvars.sh:131-140`; env var override before file-system discovery |
| US-2 AC-2.1 | Provisioner fails with error naming un-injected sentinel when secret missing | PASS | `tfvars.sh:229-235`; error message: `"Un-injected sentinel: __INJECT_TOKEN_SECRET__"` |
| US-2 AC-2.2 | Provisioner succeeds when all sentinels replaced | PASS | Implicit: sentinel check (grep) finds nothing after injection; all 74 tests pass |
| US-2 AC-2.3 | Existing rendered file validated (not overwritten with data loss) when no secret | PASS | `tfvars.sh:162-166`; template_path set to rendered_path, no placeholder injection |
| US-3 AC-3.1 | Example files contain only safe placeholders and instructional comments | PASS | `test_example_file_no_real_values`; grep confirms zero 192.168.x, SSH keys, sentinels |
| US-3 AC-3.2 | Backward compatibility: provisioner works with example-only branches | PASS | `tfvars.sh:144-148`; fallback preserved; `test_evidence_format_backward_compatible` |
| US-4 AC-4.1 | Keys in template missing from rendered file reported as provisioning_gaps | PASS | `tfvars.sh:285-288`; `test_evidence_format_with_drift` validates structure |
| US-4 AC-4.2 | Keys in rendered file missing from template reported as manual_additions | PASS | `tfvars.sh:290-294`; `test_evidence_format_with_drift` validates |
| US-4 AC-4.3 | No drift warnings when key sets are identical | PASS | `tfvars.sh:299-320`; empty arrays produced; `test_evidence_format_with_drift` |
| US-5 AC-5.1 | Change warning records key, old_value, new_value for differing non-secret | PASS | `tfvars.sh:330-377`; `test_evidence_format_with_change_warnings` validates schema |
| US-5 AC-5.2 | No change warnings on first render (no existing file) | PASS | `tfvars.sh:329`; `change_warnings_json='[]'` initialized; no comparison without existing file |
| US-5 AC-5.3 | No change warnings when non-secret values match | PASS | `tfvars.sh:356-368`; only appends when old_v != new_v |

## Functional Requirements Check

| FR | Description | Status |
|----|-------------|--------|
| FR-001 | `.tfvars.template` distinct file type from `.tfvars.example` | PASS |
| FR-002 | CI templates contain real non-secret values + `__INJECT_TOKEN_SECRET__` sentinel | PASS |
| FR-003 | Example files contain only safe placeholders, no real values | PASS |
| FR-004 | Three-tier lookup: env var > `.tfvars.template` > `.tfvars.example` | PASS |
| FR-005 | Sentinel injection from `PROXMOX_API_TOKEN_SECRET` runtime env | PASS |
| FR-006 | Post-injection validation fails if any `__INJECT_*__` remain | PASS |
| FR-007 | No data-destructive overwrite when no secret + existing rendered file | PASS |
| FR-008 | Key-set drift detection produces `provisioning_gaps` and `manual_additions` | PASS |
| FR-009 | Non-secret change warnings record before/after values | PASS |
| FR-010 | Template overwrites rendered file even when differences detected (template is source of truth) | PASS |
| FR-011 | Both `.tfvars.template` and `.tfvars.example` exist for lab and prod | PASS |
| FR-012 | Evidence artifact records template_source, drift_results, change_warnings | PASS |

## Variable Resolution
- **Scanned**: 7 files (tfvars.sh, pve-service-deploy, prod.tfvars.template, lab.tfvars.template, prod.tfvars.example, lab.tfvars.example, evidence-tfvars-proof.schema.json)
- **Undefined**: none — all bash variables use `:-` default guards (`PROXMOX_API_TOKEN_SECRET:-`, `PROXMOX_TOKEN_SECRET:-`, `PROD_TFVARS_TEMPLATE:-`, `REPO_ROOT:-`, `TFVARS_DIR:-`); `REPO_ROOT` is set in `pve-service-deploy` and accessible since `tfvars.sh` is sourced (same shell scope)

## Task Completion
- **Total**: 15 (header says 16; actual count is 15: T001–T013 + T004a + T004b)
- **Completed**: 15 `[X]`
- **Remaining**: 0 `[ ]`

## Blocking Issues
None

## Observations (non-blocking)

1. **FR-007 letter vs spirit**: The validate-only path (`token_secret=""` + existing rendered file) copies the rendered file to a temp file and then `mv`s it back, technically touching the file's mtime and inode. The spec says "validated but **not overwritten**." The content is identical and no data is lost — the spirit of the requirement (protecting locally-managed secrets from placeholder injection) is fully met. However, the file mtime changes unnecessarily. Low-risk, and the plan explicitly describes this as preserved existing behavior.

2. **`PROD_TFVARS_TEMPLATE` env var name for lab runs**: The override env var is named `PROD_TFVARS_TEMPLATE` even when the provisioner runs in lab mode. This matches the plan's explicit instruction ("Preserve `PROD_TFVARS_TEMPLATE` env var"), but creates a semantic mismatch for operators who might expect `LAB_TFVARS_TEMPLATE` for lab overrides. No functional impact — lab file-system discovery works correctly without the env var.

3. **Task count metadata**: `tasks.md` header states "Total tasks: 16" but the file contains 15 distinct tasks (T001–T013, T004a, T004b). Minor metadata discrepancy with no functional impact.

4. **`prod-tfvars` fixture missing `provisioning.txt`**: `scripts/lab/fixtures/evidence-packs/service-deploy-valid/reports/prod-tfvars/` lacks `provisioning.txt`, which `profiles.d/service-deploy.json` lists as conditional for prod runs. The lab-tfvars fixture correctly includes `provisioning.txt`. No automated test directly validates the `service-deploy-valid` fixture pack against the profile, so no test regression occurs. However, manual use of `verify_evidence.py` against this fixture with `environment=prod` would report a missing conditional field.

## Feedback for Developer
None — APPROVED.
