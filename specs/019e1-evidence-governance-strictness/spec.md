# Feature Specification: Evidence Governance Strictness & Self-Verification Gate

**Feature Branch**: `019e1-evidence-governance-strictness`
**Created**: 2025-12-31
**Status**: Draft
**Input**: User description: "Make Evidence Packs governance-grade by enforcing catalog SSOT, adding phase/title strictness, and making every suite run self-verify (no CI pipeline required)."

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Catalog SSOT: Titles and Semantics Cannot Drift (Priority: P1)

As a maintainer, I want emitted checks to be consistent with the Check Catalog so that historical comparisons remain meaningful and humans are not misled by drift.

**Why this priority**: Your current state already shows drift (catalog title vs emitted title). Governance must *prevent* this.

**Independent Test**: Create an evidence pack where `checks.json` contains `check_id=ENV-001` with a different `title` than catalog.

**Acceptance Scenarios**:

1. **Given** a pack where `checks.json` contains a `title` that differs from catalog for the same `check_id`, **When** I run `pve-lab verify-evidence <pack>`, **Then** it FAILs with `CAT-005` "Title Mismatch".
2. **Given** a pack where `checks.json` omits `title`, **When** I run verification, **Then** it PASSes and verifier can render title using catalog.
3. **Given** a pack with `check_id` present in catalog, **When** verification runs, **Then** severity/phase/owner are taken from catalog as the authoritative values.

---

### User Story 2 — Phase Must Be Provable (Priority: P1)

As an operator, I want to know which phase produced which validations so that failures can be correctly interpreted and automated gates can reason about state.

**Why this priority**: Phase enforcement in catalog is useless unless phase is represented in emitted evidence.

**Independent Test**: Run suite and inspect `checks.json` for per-check `phase`.

**Acceptance Scenarios**:

1. **Given** a suite run, **When** I examine `checks.json`, **Then** every check entry contains `phase` and it matches catalog for that `check_id`.
2. **Given** a check appears with an incorrect `phase`, **When** I verify evidence, **Then** it FAILs with `CAT-006` "Phase Mismatch".
3. **Given** a check entry missing `phase`, **When** verifying, **Then** it FAILs with `CAT-007` "Phase Missing".

---

### User Story 3 — Ownership Rules Are Mechanically Enforced (Priority: P1)

As a maintainer, I want enforcement that `ansible`-owned checks truly originate from assertion reports so we cannot spoof or misattribute checks.

**Why this priority**: “source” fields are not sufficient; governance must be provable by artifacts.

**Independent Test**: Create a pack where a check is catalog owner `ansible` but `source=harness` or has no assertion report reference.

**Acceptance Scenarios**:

1. **Given** a check with catalog owner `ansible`, **When** verifying, **Then** verifier asserts:

   * `checks.json[].source == "ansible"` AND
   * `evidence_refs` contains `reports/assertions.<phase>.json`
     Otherwise FAIL with `OWN-002`.
2. **Given** a check with catalog owner `harness`, **When** verifying, **Then** `checks.json[].source == "harness"`; otherwise FAIL with `OWN-003`.
3. **Given** `source=ansible`, **When** verifying, **Then** the check_id must be present inside `reports/assertions.<phase>.json`; otherwise FAIL with `OWN-004`.

---

### User Story 4 — Every Suite Run Self-Verifies (No CI Pipeline Required) (Priority: P1)

As a developer without CI, I want suite runs to validate their own evidence packs and fail fast if governance is violated.

**Why this priority**: You don’t have CI yet; the harness must enforce correctness locally.

**Independent Test**: Run `pve-lab suite hypervisor-nested-workload` and observe it triggers verification automatically.

**Acceptance Scenarios**:

1. **Given** a successful suite run, **When** the evidence pack is finalized, **Then** the harness automatically runs `verify-evidence` on the generated pack and records `reports/verify.json`.
2. **Given** suite produces an invalid evidence pack, **When** auto-verify runs, **Then** the suite exits non-zero and prints the first 3 governance errors.
3. **Given** `--no-verify` flag is supplied, **When** suite runs, **Then** verification is skipped and `reports/verify.json` is absent; console warns “verification skipped”.

---

### User Story 5 — Diff Tool Uses Catalog Titles for Human Output (Priority: P2)

As an operator, I want diffs to present stable titles (from catalog) even if packs omit titles, so that diffs remain readable.

**Why this priority**: Catalog is SSOT; diff output should be stable.

**Independent Test**: Diff two packs whose `checks.json` omit `title`.

**Acceptance Scenarios**:

1. **Given** two packs with same profile and check IDs, **When** I run `diff-evidence`, **Then** console output displays catalog titles.
2. **Given** a check is missing from catalog, **When** diff runs, **Then** diff fails (or requires `--allow-unknown-checks`), with `CAT-001`.

---

### Edge Cases

* **Checks.json includes title but wrong** → FAIL (strict SSOT).
* **Checks.json omits title** → PASS; title resolved from catalog for display.
* **Assertion report missing** for ansible check → FAIL unless catalog allows missing evidence.
* **Old packs pre-governance** → verifier should fail with clear remediation (“regenerate pack with contract_version >= X”), unless `--legacy-mode` is used.

---

## Requirements *(mandatory)*

### Evidence Contract

* **FR-001**: Evidence Packs MUST declare `contract_version` in `summary.json` and `evidence_manifest.json`.
* **FR-002**: Evidence verifier MUST validate presence of required files: `checks.json`, `summary.json`, `provenance.json`, `evidence_manifest.json`, `logs/events.jsonl`.
* **FR-003**: Evidence verifier MUST validate that every `evidence_ref` path exists relative to the pack root.
* **FR-004**: Evidence verifier MUST validate check_id uniqueness across the final `checks.json`.

### Check Catalog Governance (SSOT Strictness)

* **FR-005**: Repo MUST include Check Catalog SSOT (`scripts/lab/checks.d/catalog.json`) keyed by `check_id`.
* **FR-005a (Authoritative Catalog Fields)**: Catalog values for `title`, `owner`, `phase`, `severity` MUST be treated as authoritative for governance and display.
* **FR-005b (Title Strictness)**:

  * `checks.json[].title` is OPTIONAL.
  * If present, it MUST match `catalog.title` exactly; otherwise FAIL with `CAT-005`.
* **FR-005c (Phase Required in Checks)**:

  * Every `checks.json` entry MUST include `phase`.
  * `checks.json[].phase` MUST match catalog; otherwise FAIL with `CAT-006`.
* **FR-005d (Severity Handling)**:

  * `checks.json[].severity` MAY be omitted.
  * If present, it MUST match catalog; otherwise FAIL with `CAT-008`.
* **FR-006**: Verifier MUST fail if any emitted `check_id` is missing from catalog (`CAT-001`).

### Ownership Enforcement (Provable Origin)

* **FR-007a**: Every entry in `checks.json` MUST include `source: "ansible"|"harness"`.
* **FR-007b (Source vs Catalog Owner)**:

  * If catalog.owner is `ansible`, then checks.source MUST be `ansible`; else FAIL `OWN-003`.
  * If catalog.owner is `harness`, then checks.source MUST be `harness`; else FAIL `OWN-002`.
* **FR-007c (Ansible Provenance Proof)**:

  * For catalog.owner=`ansible`, `evidence_refs` MUST include `reports/assertions.<phase>.json`.
  * Verifier MUST parse that assertion report and confirm `check_id` appears inside it; else FAIL `OWN-004`.
* **FR-007d (Harness Ownership Guard)**:

  * For catalog.owner=`harness`, `evidence_refs` MUST NOT list `reports/assertions.<phase>.json` as the *primary* evidence (may appear only as supplemental); else FAIL `OWN-005`.

### Harness Self-Verification Gate (No CI Required)

* **FR-008**: `pve-lab suite <profile>` MUST auto-run `pve-lab verify-evidence <pack>` after evidence pack finalization.
* **FR-008a**: Auto-verification MUST generate `reports/verify.json` in the evidence pack.
* **FR-008b**: If auto-verification FAILs, suite MUST exit non-zero and print a compact failure summary.
* **FR-008c**: Harness MUST support `--no-verify` to skip auto-verification (default is verify enabled).
* **FR-008d**: Harness MUST record verification result in `summary.json` (e.g., `summary.verification.status`, `summary.verification.report_path`).

### Diff Tool Catalog-Backed Rendering

* **FR-009**: `diff-evidence` MUST use catalog titles for display when `checks.json` title is missing.
* **FR-010**: Diff tool MUST fail if `profile_id` differs between the two evidence packs.

### Fixture Updates (for Offline Gate)

* **FR-011**: Repository MUST include additional fixtures to cover strictness rules:

  * `invalid-title-mismatch/`
  * `invalid-phase-missing/`
  * `invalid-owner-mismatch/`
  * `invalid-ansible-check-not-in-assertion-report/`
* **FR-012**: `scripts/lab/ci-verify.sh` MUST run verifier against all fixtures (still “offline”, usable locally without CI).

### Implementation Constraints

* **NFR-001**: Verifier MUST use Python stdlib only (json, pathlib, hashlib, argparse).
* **NFR-002**: Verifier errors MUST be structured with stable codes and include remediation.
* **NFR-003**: Auto-verification MUST not require a Proxmox host; it only validates the produced pack structure and catalog compliance.

### Key Entities

* **Evidence Pack**: A directory containing results of a suite run, adhering to the Evidence Contract.
* **Check Catalog**: SSOT for check_id metadata; authoritative for title/owner/phase/severity.
* **Evidence Verifier**: Python tool validating packs against contract + catalog.
* **Self-Verification Gate**: Harness behavior that validates its own output post-run.

---

## Success Criteria *(mandatory)*

* **SC-001**: 10 consecutive `pve-lab suite hypervisor-nested-workload` runs complete and auto-verify PASS.
* **SC-002**: Packs with title mismatch, phase missing, or ownership mismatch are rejected with correct error codes.
* **SC-003**: `checks.json` can omit `title` and `severity` without breaking governance; verifier uses catalog for display and enforcement.
* **SC-004**: Ansible-owned checks are proven to exist in assertion reports (no spoofing).
* **SC-005**: Offline fixture gate validates new strictness fixtures correctly via `ci-verify.sh`.

---

## Notes on Compatibility (Explicit)

* Pre-governance packs may fail due to missing `contract_version`, missing assertion reports, or title drift. This is expected.
* If needed, a separate feature can introduce `--legacy-mode` to downgrade failures to warnings for old packs; **out of scope for this spec**.
