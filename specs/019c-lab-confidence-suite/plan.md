# Plan: Lab Harness Confidence Suite

**Feature**: `019c-lab-confidence-suite`
**Status**: Planned

## Phase 1: Harness Core & Evidence (Refactor)

**Objective**: Update `pve-lab` to use Profiles and generate structured Evidence Packs.

- [ ] **Profile Support**:
    - Update CLI to accept `--profile`.
    - Map legacy flags (`--tier`, `--tier2-mode`) to profiles.
    - Define profiles: `bootstrap`, `hypervisor-control-plane`, `hypervisor-nested-workload`.
- [ ] **Evidence Pack**:
    - Implement `generate_evidence_manifest`.
    - Implement `write_checks_json`.
    - Ensure `collect_artifacts` populates the pack correctly using subdirectories (`logs/`, `config/`, `validation/`).
    - Rename "Artifact Rotation" to "Evidence Retention Policy".

## Phase 2: Ansible Validation Logic

**Objective**: Centralize assertions and implement the Nested Workload profile.

- [ ] **Validation Role**:
    - Create `roles/lab_validation` (or similar pattern) to handle checks.
    - Ensure it outputs to `checks.json` on the controller.
- [ ] **Profile: Hypervisor Control Plane**:
    - Update `lab_tier2_pve.yml` to use the new validation logic.
    - Ensure all hardening checks (019b1) are preserved and reported in `checks.json`.
- [ ] **Profile: Hypervisor Nested Workload**:
    - Extend playbook to support nested VM creation (using `qm` inside the lab VM).
    - Deploy a mini-service (e.g., Python http.server or netcat) inside the nested VM.
    - Verify connectivity from Lab VM -> Nested VM.

## Phase 3: Confidence & Safety Suites

**Objective**: Build the meta-tests that verify the harness itself.

- [ ] **Safety Suite**:
    - Implement negative tests (e.g., run against wrong inventory, missing tags).
    - Verify `EXPECTED_FAIL` results.
- [ ] **Confidence Suite**:
    - Create a command (e.g., `pve-lab suite`) that runs:
        1. Safety Suite.
        2. `bootstrap` profile.
        3. `hypervisor-control-plane` profile.
        4. `hypervisor-nested-workload` profile (if supported).
        5. Verifies cleanup.

## Phase 4: Documentation & Cleanup

**Objective**: Finalize docs and remove ambiguity.

- [ ] **Docs Update**:
    - Update `docs/architecture/019-proxmox-lab-harness.md` with Glossary and Profile definitions.
    - Document Evidence Pack structure.
- [ ] **Tier 3 Definition**:
    - Add "Tier 3" (Rebuild Fidelity) definition to docs (deferred implementation).
