# Feature Specification: Lab Harness Semantic & Safety Closure

**Feature Branch**: `019c1-semantic-safety-closure`  
**Created**: December 31, 2025  
**Status**: Draft  
**Depends On**: 019a (lab foundation), 019b (tier2 PVE), 019b1 (hardening), 019c (confidence suite)

## Overview

Harden the Lab Harness Confidence Suite by making **semantics first-class** and producing **provable evidence** (machine-readable + human-readable) for every run, including guardrail/negative cases and cleanup proof.

**Problem**: Current implementation works but uses vague terminology ("tier2", "plus", "bundle"), making it difficult for humans to understand what was validated and preventing automation from reasoning about results. Safety is assumed rather than proven.

**Solution**: Establish stable semantic concepts (Profiles, Checks, Evidence Packs) with machine-readable artifacts that prove validation results, safety guardrails, and cleanup.

## Clarifications

### Session 2025-12-31

- Q: When multiple checks fail during a suite run, should execution continue through all checks or stop at the first failure? → A: Continue executing all checks unless a blocker-severity check fails, then abort immediately
- Q: When capturing provenance data, how should the system handle a dirty working tree (uncommitted changes in the harness git repository)? → A: Record git commit + dirty status indicator, warn in console but allow execution
- Q: When check IDs are defined in namespaces (PVE-###, NET-###, etc.), should the system support check versioning if behavior changes over time? → A: Check IDs are immutable; if behavior changes, create new check with incremented number
- Q: What performance target should the suite meet for the `hypervisor-nested-workload` profile execution time (end-to-end including VM provisioning)? → A: 10 minutes maximum
- Q: Should the suite emit structured logs (JSON Lines format) during execution for real-time monitoring and parsing, or only produce final artifacts at completion? → A: Emit JSONL progress events to stderr during execution, plus final artifacts

## Core Concepts *(mandatory definitions)*

### Concept: Profile

A named validation intent that declares:
- Prerequisites (host capabilities, resources)
- Execution steps (playbooks, scripts)
- Expected checks (with pass/fail criteria)
- Evidence collection requirements

**Examples**:
- `hypervisor-control-plane` (formerly "tier2-min"): PVE install + API verification
- `hypervisor-nested-workload` (formerly "tier2-plus"): Control plane + nested VM/LXC validation

**Properties**:
- `profile_id`: Stable identifier (kebab-case) - **PRIMARY SEMANTIC KEY**
- `display_name`: Human-readable name
- `safety_level`: `standard` | `strict` - **PRIMARY SEMANTIC KEY**
- `tier`: Numeric tier (legacy-derived field for backward compatibility, not primary semantics)
- `mode`: Mode within tier (legacy-derived field for backward compatibility, not primary semantics)
- `expected_duration_minutes`: Target execution time (informational)
- `prerequisites`: Host capability checks
- `checks`: List of check_ids this profile expects to run

### Concept: Check

A stable validation unit with consistent structure:

**Properties**:
- `check_id`: Stable identifier (e.g., `PVE-001`, `GUARD-001`, `CLEANUP-001`)
- `title`: Human-readable description
- `severity`: `blocker` | `high` | `medium` | `low`
- `expected`: `PASS` | `FAIL` (supports negative tests)
- `result`: `PASS` | `FAIL` | `SKIP` | `ERROR`
- `reason`: Human-readable explanation of result
- `evidence_refs`: Array of file paths in evidence pack
- `timestamp`: ISO 8601 timestamp

**Check ID Namespaces**:
- `PVE-###`: Proxmox VE installation/configuration checks
- `NET-###`: Network configuration/connectivity checks
- `NEST-###`: Nested virtualization capability checks
- `WORK-###`: Workload (VM/LXC) deployment checks
- `GUARD-###`: Safety guardrail checks (negative tests)
- `CLEANUP-###`: Cleanup verification checks

**Check ID Immutability**: Once assigned, a check_id is permanent and its validation intent must not change. If validation behavior needs to evolve, allocate a new check ID with the next available number in the namespace. This ensures historical evidence packs remain comparable.

### Concept: Evidence Pack

A structured directory per run containing:

**Required Files**:
- `evidence_manifest.json`: Inventory of all artifacts (includes `manifest_schema_version` for evolution tracking)
- `checks.json`: Canonical checklist results (includes `checks_schema_version` for evolution tracking)
- `provenance.json`: Run context (inputs, versions, commit)
- `summary.json`: High-level run results (references other files)
- Raw logs and outputs (existing structure)

**Structured Event Stream**:
- Real-time JSONL events emitted to stderr during execution
- Events include: check_start, check_complete, phase_start, phase_complete, error
- Captured to `logs/events.jsonl` in evidence pack for replay/analysis
- Note: `logs/commands.jsonl` (if present) is reserved for command execution timing records from earlier features

**Directory Structure**:
```
artifacts/019-lab/<runid>/
├── evidence_manifest.json
├── checks.json
├── provenance.json
├── summary.json
├── logs/
│   ├── run.log              # Main execution log
│   ├── bootstrap.log        # Bootstrap phase output
│   ├── tier2.log            # Tier2 phase output
│   ├── events.jsonl         # Real-time progress events (NEW)
│   └── commands.jsonl       # Command timing records (existing, if present)
└── reports/
    ├── validation.json
    ├── pveversion.txt
    └── systemctl-status.txt
```


## User Scenarios & Testing *(mandatory)*

### User Story 1 - Profile-Driven Confidence Run (Priority: P1)

As an operator, I run `pve-lab suite hypervisor-nested-workload` and receive:
1. A readable checklist in console output showing pass/fail for each check
2. An evidence pack with machine-readable artifacts I can archive and compare

**Why this priority**: Core functionality that delivers immediate value - operators can validate their lab environment and have proof of results.

**Independent Test**: Run `pve-lab suite hypervisor-nested-workload`, verify console shows check results, verify `artifacts/019-lab/<runid>/checks.json` contains all expected checks with stable IDs.

**Acceptance Scenarios**:

1. **Given** a lab harness with valid configuration, **When** I run `pve-lab suite hypervisor-nested-workload`, **Then** console output shows a compact checklist with check titles and PASS/FAIL status
2. **Given** a completed suite run, **When** I examine `artifacts/019-lab/<runid>/checks.json`, **Then** all checks have stable `check_id`, `expected`, `result`, and `evidence_refs` fields
3. **Given** a successful run, **When** I check `summary.json`, **Then** it references `profile: "hypervisor-nested-workload"` and links to `checks.json`
4. **Given** two runs of the same profile, **When** I compare their `checks.json`, **Then** check_ids are identical and comparable
5. **Given** a suite run in progress, **When** observing stderr, **Then** structured JSONL events appear in real-time showing check progress

---

### User Story 2 - Guardrail Proof via Negative Tests (Priority: P2)

As an operator, I can prove the harness refuses unsafe operations by examining evidence that shows deliberate negative tests passed (i.e., expected failures occurred).

**Why this priority**: Demonstrates safety without requiring manual testing of dangerous scenarios. Critical for compliance and confidence.

**Independent Test**: Run suite, verify `checks.json` contains checks with `expected: "FAIL"` and `result: "FAIL"` for guardrail tests (e.g., `GUARD-001` through `GUARD-003`).

**Acceptance Scenarios**:

1. **Given** a suite run, **When** harness attempts to apply tier2 playbook without `lab_inventory=true`, **Then** check `GUARD-001` has `expected: FAIL`, `result: FAIL`, and reason explains inventory guard
2. **Given** a suite run, **When** harness attempts to target non-lab hostname, **Then** check `GUARD-002` has `expected: FAIL`, `result: FAIL`, and reason explains hostname pattern guard
3. **Given** a suite run, **When** harness attempts to destroy VM missing identity markers, **Then** check `GUARD-003` has `expected: FAIL`, `result: FAIL`, and reason explains safety tag requirement
4. **Given** all negative tests, **When** examining evidence, **Then** no production resources were impacted (provable via evidence_manifest)

---

### User Story 3 - Cleanup Proof (Priority: P2)

As an operator, I can verify that suite runs clean up after themselves by examining cleanup checks in the evidence pack.

**Why this priority**: Prevents resource leaks and ensures repeatability. Essential for CI/CD and unattended runs.

**Independent Test**: Run suite without `--keep`, verify `CLEANUP-001` and `CLEANUP-002` checks show `result: PASS` proving no lab VMs remain and no locks remain.

**Acceptance Scenarios**:

1. **Given** a suite run completes without `--keep`, **When** examining `checks.json`, **Then** check `CLEANUP-001` ("No lab VMs remain") has `result: PASS` with evidence_ref to VM inventory
2. **Given** a suite run completes without `--keep`, **When** examining `checks.json`, **Then** check `CLEANUP-002` ("No active locks remain") has `result: PASS` with evidence_ref to lock status
3. **Given** a suite run with `--keep` flag, **When** examining `checks.json`, **Then** cleanup checks have `result: SKIP` with reason "kept by operator"
4. **Given** cleanup evidence, **When** operator reviews artifacts, **Then** VM inventory files prove no VMs in 9000-9099 range with lab identity markers remain

---

### User Story 4 - Provenance and Repeatability (Priority: P3)

As an operator, I can understand the exact context of any historical run by examining `provenance.json`, enabling reproducibility and debugging.

**Why this priority**: Enables troubleshooting, compliance audits, and reproducible builds. Important for production readiness.

**Independent Test**: Run suite, verify `provenance.json` contains controller info, target info, harness git commit, selected profile, and all input parameters.

**Acceptance Scenarios**:

1. **Given** a completed suite run, **When** examining `provenance.json`, **Then** it contains controller OS, bash version, ansible version, git commit, and git dirty status (true/false)
2. **Given** a completed suite run, **When** examining `provenance.json`, **Then** it contains target pveversion, kernel, and Debian version
3. **Given** a suite run with uncommitted changes in harness repo, **When** execution starts, **Then** console displays warning about dirty git status but execution proceeds
3. **Given** two runs with different outcomes, **When** comparing provenance files, **Then** I can identify environmental differences that may explain divergent results
4. **Given** a historical evidence pack, **When** reviewing provenance, **Then** I can reproduce the exact environment and parameters used

---

### User Story 5 - Legacy Compatibility (Priority: P3)

As an operator already using `--tier` and `--tier2-mode` flags, I can continue using them while they're transparently mapped to profiles.

**Why this priority**: Maintains backward compatibility during transition period. Prevents breaking existing scripts.

**Independent Test**: Run `pve-lab run --tier 2 --tier2-mode plus`, verify it executes `hypervisor-nested-workload` profile and logs profile name in summary.

**Acceptance Scenarios**:

1. **Given** legacy command `pve-lab run --tier 2`, **When** executed, **Then** it maps to profile `hypervisor-control-plane` and logs this in summary.json
2. **Given** legacy command `pve-lab run --tier 2 --tier2-mode plus`, **When** executed, **Then** it maps to profile `hypervisor-nested-workload`
3. **Given** any legacy command, **When** reviewing console output, **Then** a deprecation notice shows the equivalent profile-based command
4. **Given** documentation, **When** reviewing harness usage, **Then** profiles are documented as the primary interface with legacy flags as aliases

---

### Edge Cases

- **What happens when a check produces unexpected result (expected PASS, got FAIL)?** Check is marked as FAIL and reason explains the discrepancy. Suite continues executing remaining checks to maximize diagnostic information, unless the failed check has severity `blocker`, in which case suite aborts immediately.
- **What happens when negative test doesn't fail as expected (expected FAIL, got PASS)?** This is an ERROR condition indicating a safety hole. Check marked ERROR, suite aborts immediately regardless of severity, reason explains guardrail breach.
- **What happens when evidence artifact is missing?** Check referencing it is marked SKIP or ERROR depending on severity, reason explains missing artifact.
- **What happens when suite is interrupted (Ctrl+C, kill)?** Evidence pack marked incomplete, cleanup checks marked SKIP with reason "interrupted", partial evidence retained for debugging.
- **What happens when running suite against wrong environment (prod)?** Preflight checks detect non-lab environment, suite aborts before any operations, check `ENV-001` fails with clear explanation.
- **What happens when a check becomes obsolete?** The check ID is retired and removed from active profiles, but the ID remains reserved and must not be reused. Historical evidence packs referencing the obsolete check remain valid for their time period.



## Suite Execution Semantics *(canonical rules)*

### Abort vs Continue Behavior

**Default**: Suite continues executing all checks to maximize diagnostic information.

**Abort conditions** (suite stops immediately):
1. Any check with `severity: blocker` and `result: FAIL`
2. Negative test with unexpected success: `expected: FAIL` but `result: PASS` → marked as `ERROR` and suite aborts (indicates safety hole)

**Continue conditions** (suite proceeds to next check):
- Checks with `severity` lower than `blocker` that fail → recorded as FAIL, execution continues
- Checks that SKIP → recorded, execution continues
- Negative tests that fail as expected → recorded as PASS (guardrail worked), execution continues

---

## Requirements *(mandatory)*

### Functional Requirements

#### Profile System
- **FR-001**: System MUST define profiles as first-class configuration entities with stable IDs
- **FR-002**: Each profile MUST declare its tier, mode, safety_level, prerequisites, and expected checks
- **FR-003**: System MUST provide `pve-lab suite <profile>` command as primary interface
- **FR-004**: System MUST map legacy flags (`--tier`, `--tier2-mode`) to profile selections
- **FR-005**: System MUST log deprecation warnings when legacy flags are used
- **FR-006**: System MUST record selected profile in `summary.json` for every run

#### Check System
- **FR-007**: Every suite run MUST produce `checks.json` with stable check_ids
- **FR-013a**: Checks with severity lower than `blocker` that fail MUST be recorded but MUST NOT abort the suite; execution continues to maximize diagnostic information
- **FR-008**: Each check MUST include: check_id, title, severity, expected, result, reason, evidence_refs, timestamp
- **FR-009**: Check IDs MUST follow namespace convention (PVE-###, NET-###, etc.) and never be reused for different purposes
- **FR-009a**: Check IDs are immutable; if validation behavior must change, a new check ID MUST be allocated with the next sequential number in the namespace
- **FR-009b**: When a check becomes obsolete, it MAY be removed from active profiles but its ID MUST NOT be reused
- **FR-010**: System MUST support negative tests with `expected: FAIL`
- **FR-011**: System MUST distinguish between expected failures (negative tests) and unexpected failures
- **FR-012**: Console output MUST display compact checklist summary showing check titles and results
- **FR-013**: Suite execution MUST follow abort/continue semantics defined in "Suite Execution Semantics" section

#### Evidence Pack System
- **FR-014**: Every suite run MUST create an evidence pack directory at `artifacts/019-lab/<runid>/`
- **FR-015**: Evidence pack MUST include: `evidence_manifest.json`, `checks.json`, `provenance.json`, `summary.json`
- **FR-016**: `evidence_manifest.json` MUST list all produced artifacts with path, type, producing check_id, and optional sha256
- **FR-017**: `provenance.json` MUST capture controller info, target info, harness git commit, git dirty status, selected profile, and all parameters
- **FR-017a**: When git working tree is dirty, system MUST emit console warning about potential reproducibility issues but MUST allow execution to proceed
- **FR-018**: Evidence pack MUST be generated even if suite fails (partial evidence for debugging)
- **FR-019**: Evidence pack directory name MUST include timestamp in format `lab-YYYYMMDD-HHMMSS`

#### Structured Event Stream (Observability)
- **FR-019a**: Suite MUST emit structured JSONL events to stderr during execution for real-time monitoring
- **FR-019b**: Event types MUST include: `check_start`, `check_complete`, `phase_start`, `phase_complete`, `error`, `warning`
- **FR-019c**: Each JSONL event MUST include: `timestamp` (ISO 8601), `event_type`, `runid`, and event-specific data
- **FR-019d**: JSONL event stream MUST be captured to `logs/events.jsonl` in evidence pack
- **FR-019e**: Stdout MUST remain reserved for human-readable summary output; structured events use stderr only

#### Negative Tests (Guardrail Proof)
- **FR-020**: Suite MUST include check `GUARD-001` that attempts tier2 playbook without `lab_inventory=true` and expects failure
- **FR-021**: Suite MUST include check `GUARD-002` that attempts to target non-lab hostname pattern and expects failure. Implementation: Generate temporary inventory file `artifacts/<runid>/tmp/inventory_bad_hostname.yml` with host named `not-lab-pve-01` pointing to lab VM IP, then attempt playbook execution with this inventory to prove hostname guard blocks it.
- **FR-022**: Suite MUST include check `GUARD-003` that proves destroy command would reject VM missing identity markers. Implementation: Use dry-run validation or feed synthetic `qm config` output to safety-check parser to prove refusal without creating/destroying actual VMs.
- **FR-023**: All negative tests MUST execute in isolated manner that cannot impact production (use validation-only modes, temporary inventories, or synthetic inputs)
- **FR-024**: If negative test produces unexpected success, system MUST mark as ERROR and abort suite

#### Cleanup Proof
- **FR-025**: Suite MUST include check `CLEANUP-001` that verifies no VMs in 9000-9099 range with lab markers remain after run
- **FR-026**: Suite MUST include check `CLEANUP-002` that verifies no processes hold locks after run. Note: Lock files may exist; requirement is that no process actively holds the lock (verify with `flock -n` test or equivalent).
- **FR-027**: When `--keep` flag is used, cleanup checks MUST be marked SKIP with reason "kept by operator"
- **FR-028**: Cleanup checks MUST reference evidence artifacts (VM inventory, lock status probe results) in their evidence_refs- **FR-028a**: All `evidence_refs` in checks MUST use paths relative to evidence pack root (e.g., "reports/systemctl-status.txt", not absolute paths)
- **FR-028b**: Every file referenced in any check's `evidence_refs` MUST be listed in `evidence_manifest.json`
#### Assertions and Error Messages
- **FR-029**: All Ansible guards MUST use `assert` module with clear `fail_msg` and `success_msg`
- **FR-030**: All harness preflight checks MUST print check_id, title, and clear failure reason on abort
- **FR-031**: Error messages MUST include one-line remediation hint where applicable

#### Terminology and Documentation
- **FR-032**: Documentation MUST use "Profile" as primary concept, not "tier/mode"
- **FR-033**: Terms "tier2-min" and "tier2-plus" MUST be marked as deprecated aliases
- **FR-034**: Term "bundle" MUST be replaced with "Evidence Pack" throughout
- **FR-035**: All vague references MUST be replaced with specific concept names (Profile, Check, Evidence Pack)

#### Non-Functional Requirements
- **NFR-001**: Profile `hypervisor-nested-workload` MUST complete end-to-end execution (including VM provisioning, all checks, and cleanup) within 10 minutes under normal conditions
- **NFR-002**: Performance degradation beyond target SHOULD be logged in provenance with environmental factors (slow disk, network latency) when detectable

### Key Entities

- **Profile**: Named validation intent with declared prerequisites, steps, and checks
  - Attributes: profile_id, display_name, tier, mode, safety_level, prerequisites, checks
  
- **Check**: Validation unit with stable identity and clear pass/fail criteria
  - Attributes: check_id, title, severity, expected, result, reason, evidence_refs, timestamp
  
- **Evidence Pack**: Structured directory containing run artifacts and provenance
  - Contains: evidence_manifest.json, checks.json, provenance.json, summary.json, logs/, reports/
  
- **Provenance**: Run context including environment, versions, parameters
  - Attributes: controller (os, bash_version, ansible_version, git_commit, git_dirty), target (pveversion, kernel, distro), profile, parameters



## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every suite run produces `checks.json` with stable check_ids that enable comparison across runs
- **SC-002**: Console output includes readable checklist summary with <2 lines per check
- **SC-003**: Negative tests execute safely and are recorded as expected failures (expected=FAIL, result=FAIL) with 100% success rate
- **SC-004**: Cleanup proof checks pass (result=PASS) for 100% of successful runs without `--keep` flag
- **SC-005**: `provenance.json` captures all environment details needed to reproduce run results
- **SC-006**: Legacy commands (`--tier`, `--tier2-mode`) continue to work and map correctly to profiles
- **SC-007**: Evidence packs are generated for 100% of runs (including failures and interruptions)
- **SC-008**: Documentation clearly explains Profiles, Checks, and Evidence Packs with examples of each artifact format
- **SC-009**: Profile `hypervisor-nested-workload` completes within 10 minutes for 95% of runs under normal lab conditions

## Check Catalog *(Starter Set)*

This catalog defines the initial set of checks. New checks may be added following the namespace conventions.

### PVE Installation Checks
- **PVE-001**: Proxmox VE packages installed (pve-manager, pve-kernel)
- **PVE-002**: PVE services running (pveproxy, pvedaemon, pve-cluster)
- **PVE-003**: pmxcfs mounted at /etc/pve
- **PVE-004**: pvesh API reachable
- **PVE-005**: pveversion reports expected version

### Network Checks
- **NET-001**: DNS resolution working (can resolve deb.debian.org)
- **NET-002**: Internet connectivity working (can reach https://deb.debian.org)
- **NET-003**: vmbr0 bridge configured with expected IP
- **NET-004**: Lab VM reachable via ProxyJump SSH

### Nested Virtualization Checks
- **NEST-001**: Host KVM module supports nesting (kvm_intel or kvm_amd)
- **NEST-002**: Guest /dev/kvm exists and is accessible
- **NEST-003**: Nested VM can be created and started
- **NEST-004**: Nested LXC can be created and started

### Workload Checks
- **WORK-001**: LXC template downloaded successfully
- **WORK-002**: Storage configured correctly (local dir + local-lvm)
- **WORK-003**: Nested LXC network connectivity verified
- **WORK-004**: Service reachability from lab VM to nested LXC verified

### Guardrail Checks (Negative Tests)
- **GUARD-001**: Tier2 playbook rejects execution without lab_inventory=true (expected FAIL) - Implementation: override via `-e lab_inventory=false`
- **GUARD-002**: Playbook rejects non-lab hostname pattern (expected FAIL) - Implementation: temporary inventory with non-lab hostname
- **GUARD-003**: Destroy safety check would reject VM missing identity markers (expected FAIL) - Implementation: dry-run validation with synthetic config

### Cleanup Checks
- **CLEANUP-001**: No lab VMs remain in range after run
- **CLEANUP-002**: No active locks remain after run

### Environment Checks
- **ENV-001**: Target is lab environment (not production)
- **ENV-002**: Required resources available (memory, CPU)

## Implementation Guidance

### Phase 1: Core Structures
1. Define Profile data structure in `pve-lab` script
2. Create initial profiles: `hypervisor-control-plane`, `hypervisor-nested-workload`
3. Implement Check data structure and accumulator
4. Create evidence pack directory structure with manifest

### Phase 2: Check Integration
1. Instrument existing validations to emit checks
2. Add check recorder function that appends to checks array
3. Serialize checks to `checks.json` at run end
4. Add console output formatter for check summary

### Phase 3: Negative Tests
1. Create safe negative test harness (isolated execution)
2. Implement GUARD-001, GUARD-002, GUARD-003 tests
3. Add expected vs actual result validation
4. Add ERROR condition for guardrail breaches

### Phase 4: Cleanup Proof
1. Implement post-run VM inventory check
2. Implement post-run lock status check
3. Add cleanup checks to suite execution
4. Handle `--keep` flag in cleanup logic

### Phase 5: Provenance & Manifest
1. Collect controller environment (versions, commit)
2. Collect target environment (pveversion, kernel)
3. Generate `provenance.json`
4. Generate `evidence_manifest.json` listing all artifacts

### Phase 6: Legacy Compatibility
1. Map `--tier` and `--tier2-mode` to profiles
2. Add deprecation warnings
3. Update documentation with migration guide
4. Update summary.json schema to include profile

## Dependencies & Constraints

**Dependencies**:
- 019a: Lab foundation (VM lifecycle, tier 1)
- 019b: Tier 2 PVE installation on Debian 13
- 019b1: Hardening (noninteractive apt, artifacts rotation)
- 019c: Confidence suite with working nested workload validation

**Constraints**:
- MUST remain non-destructive to production (all negative tests isolated)
- MUST not require external services (no dashboards, no cloud dependencies)
- MUST keep execution time reasonable (prefer correctness over speed)
- MUST reuse existing mechanisms where possible (minimal duplication)
- MUST maintain backward compatibility with legacy flags during transition

## Deliverables

### Code Artifacts
- Updated `scripts/lab/pve-lab` with profile system and check recording
- Profile definitions in `scripts/lab/profiles.d/` (or inline)
- Negative test harness in `scripts/lab/guardrails.sh`
- Updated Ansible playbooks with readable assertions

### Evidence Artifacts (per run)
- `artifacts/019-lab/<runid>/checks.json`
- `artifacts/019-lab/<runid>/evidence_manifest.json`
- `artifacts/019-lab/<runid>/provenance.json`
- Updated `artifacts/019-lab/<runid>/summary.json` schema
- `artifacts/019-lab/<runid>/logs/events.jsonl` (real-time progress events)

### Documentation
- Updated `docs/architecture/019-proxmox-lab-harness.md` with:
  - Profile definitions and examples
  - Check catalog with sample outputs
  - Evidence pack structure with sample files
  - Migration guide from legacy flags to profiles
- Example console output showing check summary
- Example JSON artifacts with annotations

