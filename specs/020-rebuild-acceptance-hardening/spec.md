# Feature Specification: Rebuild Acceptance Gate Hardening (020)

**Feature Branch**: `020-rebuild-acceptance-hardening`  
**Created**: 2026-01-01  
**Status**: Draft  
**Input**: User description: "Rebuild Acceptance Gate Hardening (Teardown Determinism + Output Hygiene)"

---

## 1. Overview

The rebuild orchestrator (019f) validates host baseline, template baseline, suite execution, and evidence verification in a single pack. Convergence gaps remain: nondeterministic teardown (rc=25 "VM running" errors), confusing verification messaging, Ansible deprecation noise, and optional validation report warnings. This feature hardens rebuild into a strict, readable acceptance gate with deterministic teardown, unambiguous verification output, silent deprecation posture, and governed handling of optional validation artifacts.

---

## 2. Clarifications & Assumptions

* Clarification (2026-01-01): VAL-001 uses phase `validation` (dedicated post-run validation/report fetch phase) rather than `cleanup`.
* Assumption: Governance approach A is chosen for the optional validation report (catalog-governed VAL-001 with `allow_missing_evidence=true`).
* Assumption: Bounded retry defaults for teardown are 3 attempts with short backoff (tunable via existing harness config if present).
* Assumption: Summary mutation uses Python stdlib only (no jq) within existing verify tooling.

---

## 3. Core Concepts

* **Deterministic teardown**: A stop-wait-destroy loop for nested VM/LXC with bounded retries, captured evidence, and catalog-governed TEARDOWN checks that fail on unresolved teardown.
* **Verification mode contract**: A single source of truth flag passed between rebuild and suite to suppress misleading skip warnings while ensuring verify.json + summary fields are produced.
* **Governed optional validation**: Optional validation report fetch is tracked by catalog check VAL-001 with allow-missing semantics instead of emitting warnings.

---

## 4. User Scenarios & Testing *(mandatory)*

### US1 — Deterministic teardown evidence (Priority: P1)

*Why*: Operators need teardown to be quiet, predictable, and evidenced.

**Independent Test**: Create nested VM/LXC, run teardown via rebuild cleanup, inspect TEARDOWN evidence and check results.

**Acceptance Scenarios**

1. **Given** nested VM 100 and LXC 101 exist, **When** teardown runs, **Then** TEARDOWN-001/002 are emitted with PASS and evidence files exist.
2. **Given** VM 100 is still running, **When** destroy returns rc=25, **Then** teardown stops the VM, retries destroy (bounded), and records the sequence without red noise; failure after retries marks TEARDOWN-001 FAIL.

---

### US2 — Verification messaging is unambiguous (Priority: P1)

*Why*: Operators must trust whether verification ran.

**Independent Test**: Run rebuild with verification enabled; review console, verify.json, and summary.json.

**Acceptance Scenarios**

1. **Given** rebuild intends to verify, **When** suite runs, **Then** no "verification skipped" warning appears; events show info-level deferral and rebuild performs verification at end.
2. **Given** verification runs, **When** evidence pack is written, **Then** reports/verify.json exists and summary.verification fields are populated with PASS/FAIL and report path.

---

### US3 — Zero deprecation warnings (Priority: P1)

*Why*: Deprecation noise hides real failures.

**Independent Test**: Run rebuild end-to-end; capture Ansible output; expect zero deprecation warnings from assertion_utils and report generation.

**Acceptance Scenario**

1. **Given** normal rebuild run, **When** Ansible executes assertion_utils tasks, **Then** no deprecation warnings appear in stdout/stderr.

---

### US4 — Optional validation report is governed or quiet (Priority: P2)

*Why*: Optional artifacts should not look like failures.

**Independent Test**: Configure validation fetch to fail; run rebuild; observe VAL-001 status and console output.

**Acceptance Scenario**

1. **Given** validation report endpoint is unavailable, **When** rebuild runs, **Then** VAL-001 records SKIP (allow missing) with reason, no WARN is emitted, and checks.json remains contract-valid.

---

### US5 — Offline fixtures cover new behavior (Priority: P2)

*Why*: Offline gate must catch regressions.

**Independent Test**: Run scripts/lab/ci-verify.sh against new fixtures; expect intended FAIL/PASS outcomes offline.

**Acceptance Scenario**

1. **Given** new fixtures (invalid teardown evidence, missing verification summary), **When** ci-verify executes, **Then** failures surface with clear reasons and no unexpected WARN spam.

---

### Edge Cases

* Retry exhaustion: After max retries, teardown fails TEARDOWN-001/002, rebuild exits non-zero, evidence captures all attempts.
* --no-verify: Mode contract records skip intent; no misleading warnings; summary.verification shows SKIP with reason.
* Interrupted teardown: Partial evidence remains with explicit status; verify flags missing artifacts appropriately.

---

## 5. Requirements *(mandatory)*

### 5.1 Teardown Determinism (DET)

* **DET-001**: Nested VM teardown MUST follow stop → wait-for-not-running (bounded retries) → destroy. If destroy returns rc=25 (running) or equivalent, the workflow MUST issue stop and retry destroy up to the retry limit before failing.
* **DET-002**: Nested LXC teardown MUST follow stop → wait-for-not-running (bounded retries) → destroy with identical retry semantics.
* **DET-003**: Teardown attempts MUST emit evidence files with deterministic names: `reports/cleanup/teardown-vm-100.txt` for VMID 100 and `reports/cleanup/teardown-lxc-101.txt` for CTID 101, capturing commands, exit codes, and timestamps.
* **DET-004**: TEARDOWN-001 (VM) and TEARDOWN-002 (LXC) MUST be recorded in checks.json with `phase=cleanup`, `owner=harness`, `severity=high`, `result` PASS/FAIL, and `evidence_refs` pointing to the teardown evidence; retries exceeding the limit or non-zero final destroy MUST mark FAIL.
* **DET-005**: Teardown tasks MUST avoid expected red output; any non-zero command MUST be either retried (within bounds) or surfaced as FAIL. Success path MUST leave no residual warning lines related to rc=25 or "destroy failed".

### 5.2 Verification Hygiene (VER)

* **VER-001**: Introduce a verification mode contract propagated from rebuild to suite so that inner suite suppresses "verification skipped" warnings when parent intends to verify; log the deferral as info in events.jsonl.
* **VER-002**: verify_evidence.py MUST always write `reports/verify.json` (machine-readable) and MAY also write `reports/verify.txt` for humans; `pve-lab verify-evidence <pack>` MUST emit the same outputs.
* **VER-003**: summary.json MUST include `summary.verification.status` (PASS|FAIL|SKIP), `summary.verification.report_path` (default `reports/verify.json`), and `summary.verification.verifier_version` when available. Mutations MUST use Python stdlib (no jq) and persist in the evidence pack.
* **VER-004**: When `--no-verify` is used, summary.verification.status MUST be SKIP with reason noted, and console output MUST omit misleading warnings.
* **VER-005**: Verification failures MUST propagate non-zero exit codes from rebuild and be reflected in checks.json/summary.json without masking by suite messaging.

### 5.3 Ansible Deprecation Removal (ANS)

* **ANS-001**: roles/assertion_utils MUST replace injected top-level facts with `ansible_facts[...]` usage across tasks and templates to eliminate INJECT_FACTS_AS_VARS deprecation warnings.
* **ANS-002**: generate_report.yml templating MUST avoid deprecated top-level fact access and any constructs that trigger Ansible deprecation output.
* **ANS-003**: A normal rebuild + suite run MUST emit zero Ansible deprecation warnings; presence of any deprecation warning is a spec failure and MUST be treated as a regression.

### 5.4 Optional Validation Governance (VAL)

* **VAL-001**: Add catalog check VAL-001 with `owner=harness`, `phase=validation` (dedicated validation/report-fetch phase), `severity=low`, `allow_missing_evidence=true`, and `title="Optional validation report fetched"`.
* **VAL-002**: If validation report fetch succeeds, VAL-001 MUST be PASS with evidence_ref to `reports/validation.json` (or the fetched artifact). If fetch is unavailable, VAL-001 MUST be SKIP (or PASS with allow-missing) with reason set; no WARN lines are emitted.
* **VAL-003**: Profiles MAY flag VAL-001 as required; only then MAY WARN/FAIL be emitted for missing artifacts. Default rebuild profile treats VAL-001 as optional.

### 5.5 Catalog Updates (CAT)

* **CAT-001**: Update scripts/lab/checks.d/catalog.json to include TEARDOWN-001 and TEARDOWN-002 with phase `cleanup`, severity `high`, owner `harness`, and evidence expectations pointing to deterministic teardown files.
* **CAT-002**: Update catalog.json to include VAL-001 with allow-missing semantics and proper phase/owner/severity metadata aligned to 019e/019e1 governance.

### 5.6 Fixtures & Offline Gate (FIX)

* **FIX-001**: Add fixture `invalid-teardown-missing-evidence` that lacks teardown evidence and fails TEARDOWN-001/002 appropriately.
* **FIX-002**: Add fixture `invalid-summary-missing-verification` (or equivalent) where verify.json/summary.verification fields are absent, expecting offline FAIL.
* **FIX-003**: Update scripts/lab/ci-verify.sh to run new fixtures plus existing ones; ensure outputs remain non-flaky offline.

### 5.7 Non-Functional Constraints (NFR)

* **NFR-001**: No new non-stdlib runtime dependencies are introduced; verification/summary mutation uses Python stdlib only.
* **NFR-002**: No CI pipeline is added; offline verification via ci-verify.sh remains the primary gate.
* **NFR-003**: Evidence pack structure (contract_version) remains compatible with existing verify_evidence.py governance rules.

---

## 6. Success Criteria *(mandatory)*

* **SC-001**: 10 consecutive `pve-lab rebuild --apply --verify` runs produce no rc=25 destroy errors, TEARDOWN-001/002 PASS, verification PASS recorded in summary.verification, and zero deprecation warnings.
* **SC-002**: All new fixtures pass the offline gate via scripts/lab/ci-verify.sh with expected PASS/FAIL outcomes.
* **SC-003**: Optional validation report absence results in VAL-001 SKIP (allow-missing) with no WARN lines in console output.
* **SC-004**: summary.json in every rebuild evidence pack includes populated verification fields and is consistent with verify.json contents.
* **SC-005**: checks.json contains TEARDOWN-001/002 and VAL-001 entries with correct phases/owners/severity and valid evidence_refs.

---

## 7. Implementation Guidance (non-binding)

* Add teardown helpers to scripts/lab/lib/rebuild.sh (or equivalent) implementing stop/wait/destroy with bounded retries and deterministic evidence writes.
* Extend suite/rebuild handshake to carry verification mode (e.g., env var or flag) so the suite logs info-only deferral while rebuild performs verify_evidence.
* Enhance verify_evidence.py to emit verify.json and update summary.json using stdlib JSON handling; ensure idempotent updates when rerun.
* Refactor roles/assertion_utils to use ansible_facts accessors and adjust generate_report templating to remove deprecated constructs; run ansible-lint/check-mode to confirm zero warnings.
* Implement VAL-001 fetch handling with allow-missing semantics; integrate into rebuild flow so optional absence is recorded, not warned.
* Create/update fixtures to reflect teardown evidence presence/absence and verification summary expectations; wire into ci-verify.sh.

---

## 8. Dependencies

* Depends on rebuild orchestrator (019f) behavior, governance verifier (019e/019e1), and existing suite checks (including GUARD-00x, CLEANUP-*).
* Reuses evidence pack schema, profile system, and verify_evidence.py contract_version logic.

---

## 9. Deliverables

* Updated teardown logic (scripts/lab/lib/rebuild.sh or equivalent) with deterministic evidence.
* Updated pve-lab CLI and suite integration for verification mode handling and summary/verifier outputs.
* Updated roles/assertion_utils (and any generate_report components) to remove deprecation warnings.
* Updated verify_evidence.py for verify.json + summary.json alignment using stdlib.
* Updated catalog.json with TEARDOWN-001/002 and VAL-001 entries.
* New/updated fixtures and scripts/lab/ci-verify.sh wiring; documentation updates if needed.

---

## Appendix: Tasks Checklist (summary)

See tasks.md in this feature directory for actionable task breakdown aligned to the above requirements.
