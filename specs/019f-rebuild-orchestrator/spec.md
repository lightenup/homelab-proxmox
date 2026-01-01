# Feature Specification: Rebuild Orchestrator & Baseline Proof (019f)

**Feature Branch**: `019f-rebuild-orchestrator`
**Created**: 2025-12-31
**Status**: Draft
**Input**: User description: “Converge on a useful end-to-end rebuild test. Provide a single command that validates (and optionally repairs) host + template prerequisites, runs the full confidence suite, and produces governance-grade evidence.”

---

## 1. Overview

We have strong suite execution (019c/019d1) and governance-grade evidence validation (019e/019e1). The remaining gap is **a useful, repeatable “complete rebuild” test**: after a clean Proxmox reinstall or network reconfiguration, we need one workflow that:

1. Proves the **Proxmox host baseline** is correct (network/storage/ssh/nesting readiness).
2. Proves **required templates** exist and are correct (cloud-init user/key, tags, VMID policy).
3. Runs the **full suite** (`hypervisor-nested-workload`) to validate the lab can host nested workloads.
4. Self-verifies the generated evidence pack using `verify-evidence`.

This feature introduces a **Rebuild Orchestrator** (`pve-lab rebuild`) and a **Baseline Check layer** (HOST-*/TPL-* checks) integrated into the existing Profile/Check/Evidence governance model.

---

## 2. Core Concepts *(mandatory)*

### Concept: Rebuild Orchestrator

A top-level workflow command that validates a “baseline contract”, optionally remediates safe prerequisites, then runs a profile suite and governance verification.

### Concept: Baseline Contract

A set of host + template invariants required before suite execution. These invariants are expressed as catalog-governed checks and produce deterministic evidence artifacts.

### Concept: Rebuild Profile

A profile whose execution includes baseline checks + optional remediation + suite execution, producing a single Evidence Pack.

---

## 3. User Scenarios & Testing *(mandatory)*

### User Story 1 — Single Command Rebuild Validation (Priority: P1)

As an operator, I want a single command that validates the host baseline and templates, then runs the full nested workload suite, producing a governance-grade evidence pack.

**Independent Test**: Run `pve-lab rebuild --profile rebuild-hypervisor-nested-workload` on a fresh host (or after host rebuild).

**Acceptance Scenarios**:

1. **Given** a correctly configured host and templates, **When** I run `pve-lab rebuild --profile rebuild-hypervisor-nested-workload`, **Then** baseline checks PASS, suite runs, evidence self-verifies PASS.
2. **Given** a host missing a required baseline invariant, **When** I run rebuild, **Then** it fails fast on blocker baseline checks, and the evidence pack includes baseline evidence and verify report.
3. **Given** rebuild completes successfully, **When** I inspect `checks.json`, **Then** it contains HOST-* + TPL-* + suite checks, with no duplicates and catalog compliance.

---

### User Story 2 — Dry Run vs Apply Remediation (Priority: P1)

As an operator, I want rebuild to be safe-by-default (validate only), and require explicit `--apply` for any remediation.

**Independent Test**: Run rebuild with and without `--apply`.

**Acceptance Scenarios**:

1. **Given** missing templates, **When** I run `pve-lab rebuild` without `--apply`, **Then** it FAILs with remediation hints and does not change the Proxmox host state.
2. **Given** missing templates, **When** I run `pve-lab rebuild --apply`, **Then** it creates/fixes templates (within safety guardrails) and proceeds to suite run.
3. **Given** `--dry-run` is used (or default), **When** remediation is needed, **Then** checks FAIL and reasons include exact commands or actions required.

---

### User Story 3 — Baseline Proof Is Evidence-Governed (Priority: P1)

As a maintainer, I want baseline checks to be catalog-governed and verifiable, so results are comparable across rebuilds.

**Independent Test**: Generate two rebuild evidence packs and diff them.

**Acceptance Scenarios**:

1. **Given** two rebuild runs using the same rebuild profile, **When** I diff evidence packs, **Then** the diff is meaningful and stable (catalog titles, same check IDs).
2. **Given** baseline evidence is missing, **When** I run verify-evidence, **Then** it FAILs with strict error codes and remediation.
3. **Given** a baseline check is `ansible`-owned, **When** verifying, **Then** ownership provenance rules apply (assertion report presence and content).

---

### User Story 4 — Rebuild Can Be Used to Validate “Complete Rebuild Process” (Priority: P1)

As an operator, after reinstalling Proxmox or reconfiguring networking, I want rebuild to tell me exactly what’s missing before I run the expensive nested suite.

**Independent Test**: Run rebuild after intentionally breaking bridge config or removing template.

**Acceptance Scenarios**:

1. **Given** bridge missing or gateway IP wrong, **When** rebuild runs, **Then** it fails on HOST-002 with evidence of actual bridge config.
2. **Given** template missing, **When** rebuild runs, **Then** it fails on TPL-001/TPL-002 and suggests remediation or `--apply`.
3. **Given** nested virtualization is disabled, **When** rebuild runs, **Then** it fails on HOST-004 (or NEST-001 in suite, depending on design) with a clear remediation hint.

---

### Edge Cases

* **Partial apply**: If remediation succeeds for templates but suite fails, evidence is still collected and self-verified (verification may FAIL depending on spec strictness; rebuild exits non-zero).
* **Interrupted rebuild**: Evidence pack is left in place; cleanup checks behave consistently with `--keep`.
* **Unsafe environment**: If host is not the configured lab Proxmox host, rebuild aborts before changes (guardrail checks fail with blocker severity).

---

## 4. Requirements *(mandatory)*

### 4.1 CLI & Orchestration

* **FR-001**: `pve-lab` MUST add a new command: `rebuild`.
* **FR-002**: `pve-lab rebuild` MUST accept:

  * `--profile <profile_id>` (required; default MAY be `rebuild-hypervisor-nested-workload`)
  * `--apply` (enables remediation; default false)
  * `--dry-run` (forces validate-only; default true unless `--apply`)
  * `--keep` (keep lab VM resources from suite stage only)
  * `--no-verify` (skip auto-verification gate; default false)
* **FR-003**: Rebuild MUST generate an Evidence Pack under `artifacts/019-lab/<runid>/` using the existing evidence system.
* **FR-004**: Rebuild MUST include baseline phases before suite execution:

  * `baseline-host`
  * `baseline-templates`
  * then `suite` (delegates to existing suite implementation)
* **FR-005**: If any **blocker** baseline check FAILs, rebuild MUST abort before suite execution.

### 4.2 Profiles

* **FR-006**: System MUST define a new profile:

  * `rebuild-hypervisor-nested-workload`
* **FR-007**: Profile MUST declare:

  * `profile_id`, `display_name`, `safety_level`, `expected_duration_minutes`
  * prerequisites and expected checks
  * mapping to underlying suite profile `hypervisor-nested-workload`
* **FR-008**: Profile MUST be stored in `scripts/lab/profiles.d/` as first-class configuration entity.

### 4.3 Baseline Checks (Catalog-Governed)

* **FR-009**: Repo MUST extend `scripts/lab/checks.d/catalog.json` to include new baseline checks:

  * `HOST-001`..`HOST-004` (or more, see catalog section)
  * `TPL-001`..`TPL-006` (or more, see catalog section)
* **FR-010**: Baseline checks MUST be emitted into `checks.json` with:

  * `check_id`, `result`, `expected`, `reason`, `source`, `phase`, `evidence_refs`
  * and must pass `verify-evidence` strictness rules (019e1)

### 4.4 Host Baseline Contract

* **FR-011 (HOST-001)**: Rebuild MUST verify SSH connectivity to the Proxmox host defined by harness configuration (`PROXMOX_HOST`, `SSH_USER`).
* **FR-012 (HOST-002)**: Rebuild MUST verify required bridge exists and includes expected gateway IP:

  * bridge: e.g., `vmbr99`
  * gateway: e.g., `10.99.0.1`
* **FR-013 (HOST-003)**: Rebuild MUST verify required storage backend exists (e.g., `local-lvm` or configured storage).
* **FR-014 (HOST-004)**: Rebuild MUST verify nested virtualization readiness on the host (Intel or AMD nested enabled).
  * Severity: `high` (non-blocking for basic lab, but required for nested workloads).

### 4.5 Template Baseline Contract

* **FR-015 (TPL-001/TPL-002)**: Rebuild MUST verify required templates exist:

  * base template VMID (e.g., `LAB_TEMPLATE_VMID=9001`)
  * tier2 template VMID (e.g., `LAB_TEMPLATE_VMID_TIER2=9002`)
* **FR-016 (TPL-003)**: Rebuild MUST verify templates are marked as templates (`qm config <vmid>` indicates template state).
* **FR-017 (TPL-004)**: Rebuild MUST verify templates contain required safety identity markers:

  * `ManagedBy=<val>` (as per harness policy)
* **FR-018 (TPL-005)**: Rebuild MUST verify cloud-init user and SSH key are configured (e.g., `ciuser ansible`, sshkeys present).
* **FR-019 (TPL-006)**: Rebuild MUST verify template metadata conforms to naming policy (e.g., name starts with `lab-tpl-` or matches configured template name).
* **FR-020**: Template baseline checks MUST store evidence under `reports/templates/` and reference it from `checks.json`.

### 4.6 Remediation (Apply Mode)

* **FR-021**: Without `--apply`, rebuild MUST NOT create/modify templates or host config.
* **FR-022**: With `--apply`, rebuild MAY remediate only template prerequisites (safe scope), not host networking (unless explicitly allowed).
* **FR-023**: Remediation actions MUST be guarded by existing safety checks:

  * VMID range policy (9000–9099)
  * ManagedBy identity marker requirements
  * “target is lab environment” gate
* **FR-024**: Remediation actions MUST be logged to `logs/events.jsonl` and `reports/` evidence files.
* **FR-025**: After remediation, rebuild MUST re-run the baseline check(s) before proceeding.

### 4.7 Evidence & Self-Verification

* **FR-026**: Rebuild MUST run `verify-evidence` automatically after pack finalization unless `--no-verify`.
* **FR-027**: Rebuild MUST write verification output into `reports/verify.json`.
* **FR-028**: Rebuild MUST record verification result in `summary.json`:

  * `summary.verification.status`
  * `summary.verification.report_path`
* **FR-029**: Rebuild MUST ensure no duplicate check IDs are emitted. If collision occurs, fail with `SUITE-DEDUP-001` semantics.

### 4.8 Offline Testability

* **FR-030**: Repo MUST include offline fixtures for rebuild verification:

  * `valid-rebuild-pack/`
  * `invalid-rebuild-missing-template-evidence/`
  * `invalid-rebuild-host-bridge-mismatch/`
* **FR-031**: `scripts/lab/ci-verify.sh` MUST include these fixtures (still usable locally even without CI).

---

## 5. Success Criteria *(mandatory)*

* **SC-001**: `pve-lab rebuild --profile rebuild-hypervisor-nested-workload` produces a governance-valid evidence pack and auto-verifies PASS on a correctly configured host.
* **SC-002**: Running rebuild in validate-only mode on a broken host produces FAIL with clear remediation and baseline evidence artifacts.
* **SC-003**: Running rebuild with `--apply` remediates missing templates safely and then runs the suite.
* **SC-004**: Evidence packs from rebuild runs are diffable and stable across runs (catalog titles, stable IDs, no duplicates).
* **SC-005**: 5 consecutive rebuild runs complete end-to-end with PASS on a known-good environment.
* **SC-006**: Offline fixture gate validates rebuild fixtures using `verify-evidence` without requiring a Proxmox host.

---

## 6. Check Catalog Additions *(mandatory starter set)*

### Host Baseline Checks

* **HOST-001**: Proxmox host reachable via SSH
* **HOST-002**: Required bridge exists and has expected gateway IP
* **HOST-003**: Required storage backend exists
* **HOST-004**: Host nested virtualization enabled (kvm_intel/kvm_amd nested=Y/1)

### Template Baseline Checks

* **TPL-001**: Base template exists (VMID 9001)
* **TPL-002**: Tier2 template exists (VMID 9002)
* **TPL-003**: Templates are marked as templates
* **TPL-004**: Templates have identity markers (ManagedBy tag policy)
* **TPL-005**: Templates have cloud-init user and SSH key configured
* **TPL-006**: Template metadata conforms to naming policy (e.g., template name prefix)

> **Catalog ownership**: These checks are `owner: harness` by default (unless you explicitly move some to Ansible).
> **Phase**: `baseline-host` and `baseline-templates` MUST be added as allowed phases OR mapped to existing `bootstrap` phase (recommended: introduce phases explicitly and update verifier accordingly).

---

## 7. Evidence Pack Additions *(mandatory)*

Rebuild MUST store baseline evidence in deterministic paths:

```
reports/
  host/
    HOST-001-ssh.txt
    HOST-002-bridge.txt
    HOST-003-storage.txt
    HOST-004-nested.txt
  templates/
    TPL-001-qm-status-9001.txt
    TPL-002-qm-status-9002.txt
    TPL-003-qm-config-9001.txt
    TPL-003-qm-config-9002.txt
    TPL-004-tags-9001.txt
    TPL-004-tags-9002.txt
    TPL-005-cloudinit-9001.txt
    TPL-005-cloudinit-9002.txt
```

Each check MUST reference its file(s) via `evidence_refs`.

---

## 8. Implementation Guidance *(non-binding)*

### Recommended command flow (conceptual)

1. Create evidence pack + start JSONL events
2. Run baseline host checks (abort on blocker)
3. Run baseline template checks
4. If failures and `--apply`:

   * create/fix templates using the existing template creation script logic (or shared function)
   * re-run template checks
5. Run `pve-lab suite hypervisor-nested-workload` as delegated operation
6. Finalize pack (manifest + summary)
7. Auto-verify evidence pack

### Safety Recommendations

* Template remediation should only operate on:

  * VMIDs in allowed set (9001, 9002) and/or in reserved range with identity tags
  * never touch unknown VMs
* Always record remediation commands and outputs in evidence.

---

## 9. Dependencies & Constraints

**Dependencies**:

* 019c1: profiles/checks/evidence packs
* 019d: assertion alignment
* 019d1: correctness & dedup
* 019e/019e1: evidence governance and strictness + auto-verify patterns

**Constraints**:

* Must remain non-destructive to production
* Validate-only by default; remediation only with `--apply`
* No new external dependencies (Python stdlib only for verifiers)
* Must preserve existing suite profiles and evidence governance contracts

---

## 10. Deliverables

### Code Artifacts

* `scripts/lab/pve-lab` updated with `rebuild` command
* New profile: `scripts/lab/profiles.d/rebuild-hypervisor-nested-workload.json` (or `.sh`/`.yaml` depending on existing format)
* Baseline orchestration functions (new lib suggested):

  * `scripts/lab/lib/rebuild.sh` (or equivalent)
* Catalog updates: `scripts/lab/checks.d/catalog.json` add HOST-/TPL- checks

### Fixture Evidence Packs (offline)

* `scripts/lab/fixtures/evidence-packs/valid-rebuild-pack/`
* `scripts/lab/fixtures/evidence-packs/invalid-rebuild-host-bridge-mismatch/`
* `scripts/lab/fixtures/evidence-packs/invalid-rebuild-missing-template-evidence/`

### Documentation

* `docs/operations.md` updates:

  * usage: `pve-lab rebuild`
  * dry-run vs apply
  * interpreting baseline failures
  * recommended rebuild workflow after Proxmox reinstall

---
