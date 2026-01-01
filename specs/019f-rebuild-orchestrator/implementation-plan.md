# Implementation Plan: Rebuild Orchestrator & Baseline Proof (019f)

**Feature Branch**: `019f-rebuild-orchestrator`
**Spec**: [spec.md](spec.md)
**Research**: [research.md](research.md)
**Data Model**: [data-model.md](data-model.md)
**Quickstart**: [quickstart.md](quickstart.md)

## Strategy

We will implement the Rebuild Orchestrator in layers, starting with the data model (Catalog/Profile), then the Harness logic, and finally the specific checks and remediation logic. We will leverage the existing `pve-lab` structure and evidence system.

## Execution Steps

### Step 1: Data Model & Configuration
1.  **Catalog Update**: Add `HOST-*` and `TPL-*` checks to `scripts/lab/checks.d/catalog.json`.
2.  **Profile Creation**: Create `scripts/lab/profiles.d/rebuild-hypervisor-nested-workload.json`.
3.  **Verifier Update**: Ensure `verify_evidence.py` accepts `baseline-host` and `baseline-templates` phases.

### Step 2: Harness Core
1.  **CLI Update**: Modify `scripts/lab/pve-lab` to handle the `rebuild` command and its arguments.
2.  **Orchestrator Logic**: Create `scripts/lab/lib/rebuild.sh` with the high-level flow:
    *   Initialize Evidence Pack.
    *   Run Baseline Host Checks.
    *   Run Baseline Template Checks.
    *   (Optional) Remediate Templates.
    *   Run Suite (delegate).
    *   Finalize & Verify.

### Step 3: Baseline Checks Implementation
1.  **Host Checks**: Implement `HOST-001` through `HOST-004` in `scripts/lab/lib/rebuild.sh` (or dedicated check library).
    *   Use `ssh` for connectivity.
    *   Use `ip` or `brctl` for bridge checks.
    *   Use `pvesm` for storage checks.
    *   Use `cat /sys/module/kvm_*/parameters/nested` for nesting check.
2.  **Template Checks**: Implement `TPL-001` through `TPL-006`.
    *   Use `qm status`, `qm config`, `qm cloudinit dump` (if available) or config parsing.

### Step 4: Remediation Logic
1.  **Template Remediation**: Implement `remediate_templates` in `scripts/lab/lib/rebuild.sh`.
    *   Port logic from existing bootstrap scripts if applicable, or write new idempotent `qm create`/`qm set` logic.
    *   Ensure strict guardrails (VMID range, tags).

### Step 5: Validation & Fixtures
1.  **Fixtures**: Generate sample evidence packs for valid and invalid scenarios.
2.  **CI Integration**: Add fixtures to `ci-verify.sh`.
3.  **Manual Test**: Execute on the lab environment to verify real-world behavior.

## Risk Management

*   **Destructive Actions**: Remediation is the biggest risk. We will strictly gate it behind `--apply` and ensure it only touches specific VMIDs (9001, 9002).
*   **Complexity**: The `rebuild` command adds state management. We will keep the orchestrator linear and simple.
*   **Evidence Integrity**: We must ensure that the "merged" evidence pack (baseline + suite) is valid and passes the strict verifier.

## Verification Plan

1.  **Static Analysis**: `verify_evidence.py` on generated packs.
2.  **Unit/Integration**: `ci-verify.sh` with offline fixtures.
3.  **End-to-End**: `pve-lab rebuild --dry-run` on live host.
