# Research & Decisions: Rebuild Orchestrator (019f)

## Technical Context
The goal is to implement a "Rebuild Orchestrator" that validates host and template baselines before running the full test suite. This ensures a clean state and provides deterministic evidence of the environment's readiness.

## Decisions

### 1. Orchestration Logic Location
- **Decision**: Implement logic in `scripts/lab/lib/rebuild.sh` and source it in `pve-lab`.
- **Rationale**: Follows the existing modular design of `pve-lab` (e.g., `checks.sh`, `evidence.sh`). Keeps the main script clean and maintainable.
- **Alternatives**: 
    - Implement directly in `pve-lab` (too monolithic).
    - Create a separate standalone script (duplicates common logic like logging, config).

### 2. Baseline Checks Storage
- **Decision**: Add baseline checks (`HOST-*`, `TPL-*`) to the existing `scripts/lab/checks.d/catalog.json`.
- **Rationale**: Maintains a single source of truth for all checks. Allows `verify_evidence.py` to validate all checks uniformly.
- **Alternatives**:
    - Separate `baseline_catalog.json` (increases complexity for verifier).

### 3. Offline Validation Strategy
- **Decision**: Create comprehensive offline fixtures in `scripts/lab/fixtures/evidence-packs/` and update `ci-verify.sh` to scan them recursively.
- **Rationale**: Allows testing the verification logic and evidence structure without requiring a live Proxmox host. Essential for CI stability.
- **Alternatives**:
    - Mocking SSH calls in unit tests (too complex for Bash).
    - Only testing on live hardware (slow, flaky, hard to reproduce edge cases).

### 4. Remediation Strategy
- **Decision**: Implement a placeholder `remediate_templates` function for now, to be filled with actual logic later.
- **Rationale**: Focus on the orchestration and validation framework first. Remediation logic (e.g., Packer/Terraform calls) is a separate concern that can be added safely once the harness is proven.

## Unknowns & Clarifications
- **Resolved**: The spec clearly defines the behavior for `--dry-run` vs `--apply`.
- **Resolved**: The spec clearly defines the evidence structure and catalog requirements.
