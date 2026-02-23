# Feature Specification: TFvars Template Separation

**Feature Branch**: `038-tfvars-template-separation`
**Created**: 2026-02-23
**Status**: Draft
**Input**: User description: "TFvars template separation"

## Overview

The configuration example files (`.tfvars.example`) currently serve two conflicting roles: human-readable documentation for new operators and live CI templates consumed by the automated provisioner. This dual purpose has caused production incidents where documentation placeholders were injected as real values, destroying running containers and blocking deployments. This feature separates these concerns into distinct file types — safe documentation examples and CI-only templates — and hardens the provisioner to detect and prevent placeholder injection.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — CI Provisioner Uses Dedicated Templates (Priority: P1)

As a CI pipeline operator, I want the automated provisioner to source configuration from dedicated CI templates (not documentation examples), so that placeholder values never reach production deployments.

**Why this priority**: This is the root cause of all three production incidents described in the problem statement. Eliminating the dual-use file prevents the most severe failure mode: placeholder values reaching production.

**Independent Test**: Can be fully tested by running the provisioner against a dedicated CI template and verifying that the rendered output contains only real values. Delivers immediate safety improvement for all CI-triggered deployments.

**Acceptance Scenarios**:

1. **Given** a CI template file exists with sentinel markers for secrets and real values for non-secrets, **When** the provisioner runs with valid environment secrets, **Then** the rendered tfvars file contains no placeholder or sentinel markers and all values match expected production configuration.
2. **Given** only a documentation example file exists (no CI template), **When** the provisioner runs, **Then** the provisioner falls back to the example file for backward compatibility with older branches.
3. **Given** an explicit template path is provided via environment variable, **When** the provisioner runs, **Then** the provisioner uses that path over any file-system discovery.

---

### User Story 2 — Post-Injection Sentinel Validation (Priority: P1)

As a CI pipeline operator, I want the provisioner to fail with a clear error if any sentinel markers remain after injection, so that un-injected placeholders never reach a deployment.

**Why this priority**: This is the safety net that catches misconfiguration before it causes damage. Without it, missing secrets could silently pass through as literal placeholder strings.

**Independent Test**: Can be tested by deliberately omitting a required environment secret and verifying the provisioner exits with a non-zero status and an error message that names the un-injected sentinel.

**Acceptance Scenarios**:

1. **Given** a CI template contains sentinel markers for secrets, **When** a required secret is not provided via environment, **Then** the provisioner fails and the error message lists the specific un-injected sentinel marker.
2. **Given** a CI template contains sentinel markers for secrets, **When** all required secrets are provided, **Then** the provisioner succeeds and no sentinel markers remain in the rendered file.
3. **Given** a rendered tfvars file already exists and no secrets are provided, **When** the provisioner runs, **Then** the existing rendered file is validated but not overwritten (preserving locally-managed secrets).

---

### User Story 3 — Documentation Examples Are Safe to Copy (Priority: P2)

As a new operator setting up a local environment, I want example files to contain only safe placeholder values and human-readable instructions, so that I can copy them as a starting point without risk of accidentally using documentation placeholders in a real deployment.

**Why this priority**: Improves onboarding experience and removes any confusion about which files are "live" versus "documentation." Less urgent than the CI safety improvements because local operators already manage their own files.

**Independent Test**: Can be tested by inspecting example files to verify they contain generic placeholders (e.g., `<pve-host>`, `<your-token-secret>`) and do not contain real infrastructure values like IP addresses or real SSH keys.

**Acceptance Scenarios**:

1. **Given** a documentation example file, **When** an operator reads it, **Then** all secret-adjacent fields contain clearly marked placeholders (not real values) and include instructional comments.
2. **Given** a documentation example file, **When** the CI provisioner runs without a CI template present, **Then** the provisioner still functions (backward compatibility) but the rendered output will require manual correction of placeholder values.

---

### User Story 4 — Key-Set Drift Detection (Priority: P2)

As a homelab operator, I want the provisioner to detect when the CI template and the rendered tfvars file have different sets of configuration keys, so that I am alerted to provisioning gaps or manual additions before they cause deployment failures.

**Why this priority**: Prevents silent configuration drift between what the template defines and what the rendered file contains. Important for ongoing maintenance but less urgent than preventing placeholder injection.

**Independent Test**: Can be tested by adding a key to the template that does not exist in the rendered file, running the drift check, and verifying a warning is reported in the validation evidence.

**Acceptance Scenarios**:

1. **Given** a CI template defines keys A, B, C and the rendered file contains keys A, B, **When** drift detection runs, **Then** the validation evidence reports key C as a provisioning gap (present in template, missing from rendered).
2. **Given** the rendered file contains a key D not present in the CI template, **When** drift detection runs, **Then** the validation evidence reports key D as a manual addition (warning, not failure).
3. **Given** the template and rendered file have identical key sets, **When** drift detection runs, **Then** no drift warnings appear in the validation evidence.

---

### User Story 5 — Non-Secret Value Change Warnings (Priority: P3)

As a homelab operator, I want the provisioner to warn me when a non-secret value in the rendered file differs from the template, so that manual hotfixes I applied directly are auditable and not silently overwritten without notice.

**Why this priority**: This is an auditability improvement. The provisioner still overwrites (template is source of truth), but the warning creates an audit trail. Lower priority because the fix is to backport manual edits to the template in the repo.

**Independent Test**: Can be tested by manually editing a non-secret value (e.g., gateway IP) in the rendered file, running the provisioner, and verifying a warning appears in the evidence artifact listing the changed value.

**Acceptance Scenarios**:

1. **Given** the rendered file has `network_gateway = "192.168.1.99"` and the CI template has `network_gateway = "192.168.1.1"`, **When** the provisioner renders a new file, **Then** the evidence artifact contains a warning naming the key and showing the old and new values.
2. **Given** no rendered file exists yet, **When** the provisioner renders for the first time, **Then** no change warnings are emitted (nothing to compare against).
3. **Given** all non-secret values match between the existing rendered file and the new render, **When** the provisioner runs, **Then** no change warnings appear.

---

### Edge Cases

- What happens when a CI template file is malformed (e.g., missing closing quote, invalid HCL syntax)?
  - The provisioner should fail with a clear error before attempting injection, not produce a corrupted rendered file.
- What happens when the environment variable for the template path points to a file that does not exist?
  - The provisioner should fall back to file-system discovery (same as if the variable were unset) and document the fallback in the evidence artifact.
- What happens when both a `.tfvars.template` and a `.tfvars.example` exist but have conflicting key sets?
  - The `.tfvars.template` takes precedence; the example file is ignored. Drift detection only compares template vs. rendered file, not template vs. example.
- What happens when sentinel markers appear inside comments or string values that are not intended for injection?
  - Sentinels should only be recognized in HCL value positions (right-hand side of `=` assignments). Sentinels inside comments are ignored.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST support a dedicated CI template file type (`.tfvars.template`) that is distinct from documentation example files (`.tfvars.example`). *(US-1, US-3)*
- **FR-002**: CI template files MUST contain real, non-secret configuration values and use unambiguous sentinel markers for values that require runtime injection. *(US-1)*
- **FR-003**: Documentation example files MUST contain only safe, generic placeholders and human-readable instructions — never real infrastructure values (IP addresses, SSH keys, hostnames). *(US-3)*
- **FR-004**: The provisioner MUST prefer CI template files over documentation examples when both exist, following this lookup order: explicit environment variable override > `.tfvars.template` file > `.tfvars.example` file (backward compatibility fallback). *(US-1)*
- **FR-005**: The provisioner MUST inject all sentinel-marked values from the runtime environment during rendering. *(US-1)*
- **FR-006**: The provisioner MUST validate after injection that no sentinel markers remain in the rendered output. If any remain, the provisioner MUST fail with a non-zero exit code and an error message listing each un-injected sentinel. *(US-2)*
- **FR-007**: The provisioner MUST NOT overwrite an existing rendered tfvars file when no secrets are available in the environment. It should validate the existing file instead. *(US-2)*
- **FR-008**: The system MUST compare the key set of the CI template against the rendered file and report discrepancies (provisioning gaps and manual additions) in the validation evidence artifact. *(US-4)*
- **FR-009**: The provisioner MUST detect and warn when non-secret values in an existing rendered file differ from the values in the CI template, recording the old and new values in the evidence artifact. *(US-5)*
- **FR-010**: The provisioner MUST still overwrite the rendered file with template values even when non-secret differences are detected (template is the source of truth). The warning is for auditability only. *(US-5)*
- **FR-011**: Both CI template files and documentation example files MUST exist for each environment (lab and prod). *(US-1, US-3)*
- **FR-012**: The provisioner MUST record the template source used, validation status, drift results, and any warnings in the existing validation evidence artifact. *(US-4, US-5)*

### Key Entities

- **CI Template** (`.tfvars.template`): The authoritative source of non-secret configuration values for a given environment. Contains sentinel markers for runtime-injected secrets. Used exclusively by the CI provisioner.
- **Documentation Example** (`.tfvars.example`): A human-readable starting point for new operators. Contains safe placeholders and instructional comments. Never used by CI when a CI template is available.
- **Rendered File** (`.tfvars`): The final configuration file produced by the provisioner, containing real values for all fields. Gitignored; lives only on the deployment host.
- **Sentinel Marker**: A clearly identifiable placeholder string in a CI template (e.g., `__INJECT_TOKEN_SECRET__`) that the provisioner replaces with a runtime value during rendering.
- **Validation Evidence**: A structured artifact recording the provisioner's actions, validation results, drift findings, and warnings for auditability.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After this feature is deployed, zero CI deployments fail due to documentation placeholder values being injected into production configuration. (Baseline: three incidents in recent history.)
- **SC-002**: The provisioner detects and rejects 100% of un-injected sentinel markers before any rendered file is written — verified by unit tests covering every defined sentinel.
- **SC-003**: A new operator can copy an example file and understand all placeholder fields within 5 minutes, without needing to consult external documentation or ask for help.
- **SC-004**: Key-set drift between the CI template and the rendered file is reported in the validation evidence within the same provisioner run — no separate manual step required.
- **SC-005**: Non-secret value changes between the existing rendered file and the new render are logged with before/after values in the evidence artifact, achieving full auditability of overwrites.
- **SC-006**: Backward compatibility is maintained: branches that lack `.tfvars.template` files continue to work using the `.tfvars.example` fallback, with no provisioner failures.

## Out of Scope

- **Vault or secret management integration**: Moving secrets to a vault, KeyVault, or other secret management system is a separate initiative. This feature only improves how secrets are injected from environment variables.
- **Lab tfvars CI provisioning**: Lab and prod use the same provisioner codepath for evidence parity (Goal 6, D-005). Lab CI templates are created and consumed by the provisioner.
- **Workflow YAML changes**: The provisioner is called from bash scripts, not from workflow step definitions. No GitHub Actions workflow file changes are in scope.
- **HCL syntax validation**: Full HCL parsing or linting of template files is out of scope. Validation is limited to sentinel detection and key-set comparison.
- **Multi-environment provisioning in a single run**: The provisioner renders one environment at a time. Orchestrating multiple environments is unchanged.

## Assumptions

- **A-001**: The current set of values requiring runtime injection via sentinel markers is limited to one: the API token secret (`PROXMOX_API_TOKEN_SECRET`). The API token ID is a non-secret constant (`terraform@pve!terraform-token`) enforced by the provisioner and belongs as a literal value in the CI template. All other configuration values are non-secret and can be committed to the repository in CI template files.
- **A-002**: The existing validation evidence artifact format (`prod-tfvars/validation.json`) can be extended with new fields (drift results, change warnings) without breaking downstream consumers.
- **A-003**: Operators who manage local environments will continue to use `.tfvars` files directly (copied from examples), not CI templates. The template separation does not change the local operator workflow.
- **A-004**: The sentinel marker format (`__INJECT_<NAME>__`) will not conflict with any legitimate HCL values in the configuration files.
- **A-005**: The `.tfvars.example` files currently contain real infrastructure values (IP addresses, SSH keys) that need to be reverted to safe placeholders as part of this feature. This is a one-time migration.
- **A-006**: The provisioner is invoked by `pve-service-deploy` which is used by both CI (GitHub Actions on self-hosted runner) and laptop deployments. Changes to the provisioner automatically maintain dual-provisioning parity (Constitution Principle IV). No separate laptop-specific implementation is required.

## Decision Log

| ID | Decision | Rationale |
|----|----------|-----------|
| D-001 | Use unambiguous sentinel markers instead of pattern matching for secret injection | Pattern matching on field names and whitespace is fragile and has caused past incidents. Sentinels are self-documenting and unambiguous. |
| D-002 | Keep `.tfvars.example` fallback in the provisioner lookup order | Ensures backward compatibility for older branches that have not been updated with `.tfvars.template` files. Avoids breaking CI on branch switches. |
| D-003 | Only inject the token secret via sentinel; all other values — including the token ID (`terraform@pve!terraform-token`) — are literal in the template | The token ID is a non-secret constant enforced by the provisioner and safe to commit. Non-secret values (IPs, mountpoints, gateway) are static configuration that belongs in version control. Only the token secret — sourced from `PROXMOX_API_TOKEN_SECRET` at runtime — needs sentinel injection. |
| D-004 | Warn but still overwrite when non-secret values differ between rendered file and template | The CI template is the source of truth. Manual hotfixes on the rendered file are temporary and should be backported to the template. The warning makes the overwrite auditable without blocking deployments. |
| D-005 | Lab and prod use the same provisioner codepath | Evidence parity between environments. A lab deploy that produces no tfvars validation evidence is less trustworthy than prod. Same function, same artifacts, same guarantees. |
| D-006 | Drift detection compares key sets only (not values) between template and rendered file | Value comparison is handled by the no-clobber warning (FR-009). Key-set comparison catches structural divergence (missing or extra keys) which is a different class of problem. |

## Open Questions

None

## Self-Critique

### Strengths
- The spec cleanly separates the dual-use problem (examples serving as CI templates) into two distinct file types with well-defined roles and a clear fallback chain.
- User stories are independently testable and prioritised by impact: P1 stories (US-1, US-2) address the root cause of production incidents; P2/P3 stories (US-3–US-5) add onboarding and auditability improvements.
- The decision log is thorough — six decisions covering sentinel design, fallback order, overwrite policy, and structural parity between environments.
- Edge cases address practical failure modes (malformed HCL, missing template file, sentinels in comments, conflicting key sets) with concrete expected behaviour.
- Constitution cross-check is comprehensive: Principle II (secrets never committed — sentinels only), Principle III (separation — provisioner layer, not Terraform), Principle IV (dual-provisioning parity — provisioner serves both CI and laptop), and Token Privilege Tiers (rendering is orchestrator-layer, Tier 1 token ID is literal in template) are all honoured.
- Out-of-scope boundaries are tight and justified — no scope creep into vault integration, HCL parsing, or workflow YAML changes.

### Issues Found
- **[severity: medium]** A-001 originally stated two values (token ID and token secret) require runtime injection via sentinels. The provisioner hardcodes the token ID to `terraform@pve!terraform-token` — it is non-secret and constant. Only the token secret requires a sentinel. **Fixed**: A-001 corrected to specify one sentinel value; D-003 updated to match; US-2 AC-2.1 generalised.
- **[severity: medium]** D-003 originally named both "token ID and token secret" as sentinel-injected. This contradicted the constitution's definition of secrets (token ID is not a secret) and misrepresented the provisioner's actual behaviour. **Fixed**: D-003 now correctly identifies only the token secret as sentinel-injected.
- **[severity: low]** Constitution Principle IV (dual-provisioning parity) was not explicitly cross-referenced. While the provisioner inherently serves both CI and laptop, the spec should document this invariant. **Fixed**: Added A-006 confirming parity is maintained through the shared provisioner.
- **[severity: low]** The spec does not mention the root-level `terraform/terraform.tfvars.example` or `terraform/github/github.tfvars.example`. Both are out of scope: the root-level file is a pointer to environment-specific files, and the GitHub file is for a separate Terraform root. No action needed — the scope is correctly bounded to Proxmox environment files.
- **[severity: low]** SC-003 ("within 5 minutes") is subjective and hard to measure precisely. However, it targets a user experience outcome (onboarding clarity) rather than a system metric, so exact measurement is less critical. Acceptable as-is.

### Verdict
ACCEPT — All medium-severity issues have been resolved. The spec is tightly scoped to the dual-use file problem, avoids implementation details, and provides testable acceptance criteria for every functional requirement. The sentinel count is now accurate, the constitution cross-check is explicit, and edge cases cover the practical failure modes observed in this project's recent deployment history.
