# Research: TFvars Template Separation

**Date**: 2026-02-23 | **Branch**: `038-tfvars-template-separation`

## R-001: Sentinel Marker Format and Injection Mechanism

**Decision**: Use `__INJECT_TOKEN_SECRET__` as the sentinel marker, replaced via `sed` restricted to non-comment lines.

**Rationale**:
- The sentinel format `__INJECT_<NAME>__` is self-documenting and unambiguous — it cannot be confused with any legitimate HCL value (D-001).
- Only one sentinel is needed: `__INJECT_TOKEN_SECRET__`, mapped to the `PROXMOX_API_TOKEN_SECRET` environment variable (A-001).
- The token ID (`terraform@pve!terraform-token`) is a non-secret constant, enforced by the provisioner as a literal value — not a sentinel (D-003).
- Replacement uses `sed` with a guard to skip comment lines (`/^[[:space:]]*#/!`), satisfying the edge case that sentinels inside comments should be ignored.
- Post-injection validation uses `grep` on non-comment lines to detect any remaining `__INJECT_[A-Z_]+__` patterns, failing with a clear error listing each un-injected sentinel (FR-006).

**Alternatives considered**:
- **Pattern matching on field name** (current approach): Fragile — uses `sed` to match `proxmox_api_token_secret = ...` and replace the entire line. Has caused incidents when the pattern doesn't match due to whitespace variations. Rejected in favor of sentinels.
- **envsubst-style `${VAR}` syntax**: Rejected — conflicts with HCL/shell variable syntax and could cause accidental substitution. Sentinel format `__INJECT_*__` has no ambiguity with HCL.
- **jq/HCL-aware parser**: Out of scope per spec ("Full HCL parsing or linting of template files is out of scope"). Sentinels work with simple text processing.

**Source**: Spec D-001, A-001, D-003, edge case definition.

## R-002: Template Lookup Order and Backward Compatibility

**Decision**: Three-tier lookup: explicit env var > `.tfvars.template` > `.tfvars.example` (fallback).

**Rationale**:
- `PROD_TFVARS_TEMPLATE` env var allows CI to override the template path for special cases (FR-004 AC-1.3).
- `.tfvars.template` is the primary CI template — contains real non-secret values + sentinel markers (FR-001).
- `.tfvars.example` is the backward-compatibility fallback for branches that haven't been updated yet (D-002, SC-006).
- The current candidate `${REPO_ROOT}/terraform/environments/prod.tfvars` (a gitignored rendered file) is removed from the lookup chain. With `.tfvars.template` as the explicit CI template, there is no reason to use a local rendered copy as a template source. This eliminates confusion about which file serves which role.
- The "validate existing" path (no secret available, rendered file exists at `${TFVARS_DIR}/prod.tfvars`) is preserved unchanged — it validates the external rendered file without overwriting it (FR-007).

**Alternatives considered**:
- **Keep `prod.tfvars` in lookup chain**: Rejected — the purpose of this feature is to separate template from rendered file. Having a gitignored rendered file as a template candidate defeats the separation.
- **Require `.tfvars.template` (no fallback)**: Rejected — breaks backward compatibility for older branches (D-002, SC-006).

**Source**: Spec FR-004, D-002, SC-006.

## R-003: Key-Set Drift Detection Approach

**Decision**: Extract top-level HCL keys via `awk`/`grep` and compare sets using bash associative arrays.

**Rationale**:
- HCL tfvars files use `key = value` syntax for top-level assignments. Extracting keys is straightforward with `grep -E '^[[:space:]]*[a-zA-Z_]' | awk -F'[[:space:]]*=' '{print $1}'`.
- Nested keys (inside maps like `service_mountpoints = { ... }`) are not compared individually — the top-level key `service_mountpoints` is what matters for drift detection. Deep comparison of nested structures would require HCL parsing, which is out of scope.
- The drift report identifies:
  - **Provisioning gaps**: Keys in template but missing from rendered file.
  - **Manual additions**: Keys in rendered file but not in template.
- Results are written to the validation evidence JSON under a `drift_results` field (FR-008, FR-012).
- When template and rendered key sets match, no warnings are emitted (US-4 AC-3).

**Alternatives considered**:
- **HCL parser (e.g., python-hcl2)**: Full HCL parsing is out of scope per spec. Top-level key extraction via text processing is sufficient for drift detection (D-006).
- **Deep value comparison for nested structures**: Rejected — value comparison is a separate concern handled by FR-009 (non-secret value change warnings), and only applies to simple key-value pairs, not complex maps.

**Source**: Spec FR-008, D-006, edge case (conflicting key sets).

## R-004: Non-Secret Value Change Detection

**Decision**: Compare simple (non-nested, non-secret) values between existing rendered file and template using `awk` extraction, and log differences as warnings in evidence.

**Rationale**:
- Only simple values (string or number on a single line) are compared. Complex values (maps, lists) are skipped — their internal structure changes are impractical to diff without HCL parsing.
- The token secret value is excluded from comparison (it's a secret and handled separately).
- When differences are found, the provisioner logs warnings with key name, old value, and new value to the evidence artifact (FR-009, FR-012).
- The provisioner still overwrites with template values — template is source of truth (FR-010, D-004).
- When no existing rendered file exists (first render), no change warnings are emitted (US-5 AC-2).
- When all non-secret values match, no change warnings appear (US-5 AC-3).

**Alternatives considered**:
- **Block overwrites when differences detected**: Rejected — template is source of truth (D-004). Warnings are for auditability, not blocking.
- **Interactive confirmation**: Not possible — provisioner runs non-interactively in CI. Warnings in evidence provide the audit trail.

**Source**: Spec FR-009, FR-010, D-004, US-5.

## R-005: Documentation Example File Content

**Decision**: Replace all real infrastructure values in `.tfvars.example` files with clearly marked generic placeholders and add instructional comments.

**Rationale**:
- Current `.tfvars.example` files contain real IP addresses (192.168.1.112, 192.168.1.1, 192.168.1.211–216), real SSH public keys, and real infrastructure details. This violates the documentation-example role defined by the spec (FR-003).
- Placeholder format: `<descriptive-name>` (e.g., `<pve-api-url>`, `<gateway-ip>`, `<your-ssh-public-key>`). This format is human-readable and clearly distinct from real values.
- Each placeholder includes a comment explaining what value to use and where to find it.
- The token secret placeholder is `<your-token-secret>` (not the sentinel format), making it clear this is documentation, not a CI template.
- The token ID placeholder is `<token-id>` (e.g., `terraform@pve!terraform-token`) — this is a non-secret value but is still replaced with a placeholder in the documentation example so operators understand they need to configure it.

**Alternatives considered**:
- **Keep real IPs in examples**: Rejected — spec FR-003 requires safe placeholders only. Real IPs in documentation examples caused confusion about which files are "live."
- **Use sentinel format in examples**: Rejected — sentinels are for CI templates only. Documentation examples should use human-readable placeholders.

**Source**: Spec FR-003, A-005, US-3.

## R-006: Evidence Schema Extension

**Decision**: Extend `evidence-tfvars-proof.schema.json` with optional `drift_results` and `change_warnings` fields. Maintain backward compatibility by making new fields optional.

**Rationale**:
- A-002 states the validation evidence format can be extended without breaking downstream consumers.
- New fields are optional (not in `required`), so older evidence packs that lack them remain valid.
- `drift_results` is an object with `provisioning_gaps` (array of key names) and `manual_additions` (array of key names).
- `change_warnings` is an array of objects, each with `key`, `old_value`, and `new_value`.
- The existing `validation_errors` field continues to capture fatal errors (sentinel validation failures, missing secret, wrong token ID).
- The `template_source` field now distinguishes between `.tfvars.template` and `.tfvars.example` sources, making the lookup path auditable.

**Alternatives considered**:
- **Separate evidence file for drift**: Rejected — the spec says drift results should be in the validation evidence artifact (FR-012). A single file is simpler to consume.
- **Break the existing schema**: Rejected — new fields are additive and optional, preserving backward compatibility (A-002).

**Source**: Spec FR-012, A-002.

## Open Questions

None — all unknowns resolved.
