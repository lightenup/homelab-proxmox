# Tasks: Lab Harness Semantic & Safety Closure

**Input**: Design documents from `/specs/019c1-semantic-safety-closure/`  
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `- [ ] [ID] [P?] [Story?] Description with file path`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Setup/Foundational/Polish phases: NO story label
- User Story phases: MUST have story label

**Note on Legacy Files**: Feature 019c1 creates `logs/events.jsonl` for real-time progress events. If `logs/commands.jsonl` exists in evidence packs, it's a legacy artifact from 019a/b (command timing records), not created by 019c1.

---

## Phase 1: Setup (Project Initialization)

**Purpose**: Create directory structure, shared libraries, and JSON schemas

- [X] T001 Create lib/ directory structure at scripts/lab/lib/
- [X] T002 [P] Create profiles.d/ directory at scripts/lab/profiles.d/
- [X] T003 [P] Copy JSON schemas from specs/019c1-semantic-safety-closure/contracts/ to scripts/lab/contracts/
- [X] T004 [P] Create lib/checks.sh with check recording functions
- [X] T005 [P] Create lib/jsonl.sh with JSONL event emission to stderr
- [X] T006 [P] Create lib/provenance.sh with git/version capture functions
- [X] T007 [P] Create lib/evidence.sh with evidence pack management functions
- [X] T008 Create scripts/lab/guardrails.sh as negative test harness
- [X] T008a [P] Create lib/cleanup.sh stub for cleanup check functions (used in Phase 5)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that all user stories depend on

- [ ] T009 Implement check recorder function in lib/checks.sh (record_check, accumulate to array)
- [ ] T010 Implement JSONL emitter in lib/jsonl.sh (emit_event to stderr with tee to events.jsonl)
- [ ] T011 Implement provenance capture in lib/provenance.sh (git commit, dirty status, versions)
- [ ] T012 Implement evidence pack init in lib/evidence.sh (create_evidence_pack with runid)
- [ ] T013 Implement evidence manifest generator in lib/evidence.sh (generate_manifest with schema version)
- [ ] T014 Add suite execution semantics to scripts/lab/pve-lab (abort on blocker FAIL or negative test ERROR)
- [ ] T015 Update scripts/lab/pve-lab to source lib/*.sh files
- [ ] T015a Add ENV-001 preflight check to scripts/lab/pve-lab (verify lab environment via hostname pattern before suite execution)
- [ ] T015b Add ENV-002 preflight check to scripts/lab/pve-lab (verify required resources available: memory, CPU, storage)

---

## Phase 3: User Story 1 - Profile-Driven Confidence Run (P1)

**Story Goal**: Operator runs `pve-lab suite hypervisor-nested-workload` and receives readable checklist + machine-readable evidence pack

**Independent Test**: Run `pve-lab suite hypervisor-nested-workload`, verify console shows check results, verify `artifacts/019-lab/<runid>/checks.json` contains all expected checks with stable IDs

**Implementation Tasks**:

- [ ] T016 [US1] Define Profile data structure as bash-sourceable .profile file format in scripts/lab/profiles.d/ (per research.md decision)
- [ ] T017 [US1] Create profile definition scripts/lab/profiles.d/hypervisor-control-plane.profile
- [ ] T018 [US1] Create profile definition scripts/lab/profiles.d/hypervisor-nested-workload.profile
- [ ] T019 [US1] Add profile loader function to lib/checks.sh (load_profile, validate fields)
- [ ] T020 [US1] Add `pve-lab suite <profile>` command to scripts/lab/pve-lab (load profile, execute phases)
- [ ] T021 [US1] Instrument ansible/playbooks/lab_bootstrap.yml to emit check records for PVE-001 through PVE-005
- [ ] T022 [US1] Instrument ansible/playbooks/lab_tier2_pve.yml to emit check records for NET-001 through NET-004
- [ ] T023 [US1] Add validation role instrumentation to emit NEST-001 through NEST-004 checks
- [ ] T024 [US1] Add workload validation to emit WORK-001 through WORK-004 checks
- [ ] T025 [US1] Implement checks.json serializer in lib/checks.sh (serialize_checks with checks_schema_version)
- [ ] T026 [US1] Add console check summary formatter to scripts/lab/pve-lab (print compact checklist <2 lines per check)
- [ ] T027 [US1] Generate checks.json at suite completion in scripts/lab/pve-lab
- [ ] T028 [US1] Update summary.json generation to include profile reference in scripts/lab/pve-lab
- [ ] T029 [US1] Emit JSONL check_start and check_complete events during execution
- [ ] T030 [US1] Emit JSONL phase_start and phase_complete events during suite execution

---

## Phase 4: User Story 2 - Guardrail Proof via Negative Tests (P2)

**Story Goal**: Prove harness refuses unsafe operations via expected failures (negative tests)

**Independent Test**: Run suite, verify `checks.json` contains checks with `expected: "FAIL"` and `result: "FAIL"` for GUARD-001 through GUARD-003

**Implementation Tasks**:

- [ ] T031 [US2] Implement GUARD-001 in scripts/lab/guardrails.sh (tier2 playbook with lab_inventory=false, expect FAIL)
- [ ] T032 [US2] Implement GUARD-002 in scripts/lab/guardrails.sh (generate temp inventory artifacts/<runid>/tmp/inventory_bad_hostname.yml with non-lab hostname, expect FAIL)
- [ ] T032a [US2] Clean up tmp/ directory after negative tests complete in scripts/lab/guardrails.sh (ephemeral, not included in evidence pack)
- [ ] T033 [US2] Implement GUARD-003 in scripts/lab/guardrails.sh (dry-run destroy validation with synthetic qm config, expect FAIL)
- [ ] T034 [US2] Add expected vs actual result validator in lib/checks.sh (validate_negative_test)
- [ ] T035 [US2] Add ERROR condition handler for guardrail breaches in scripts/lab/pve-lab (unexpected PASS → ERROR + abort)
- [ ] T036 [US2] Record all guardrail checks with expected=FAIL in checks.json
- [ ] T037 [US2] Add guardrails phase to profile definitions (call guardrails.sh)

---

## Phase 5: User Story 3 - Cleanup Proof (P2)

**Story Goal**: Verify suite cleans up resources by examining cleanup checks in evidence pack

**Independent Test**: Run suite without `--keep`, verify CLEANUP-001 and CLEANUP-002 checks show `result: PASS` proving no lab VMs remain and no locks remain

**Implementation Tasks**:

- [ ] T038 [US3] Implement CLEANUP-001 check in lib/cleanup.sh (verify no VMs in 9000-9099 range with lab markers)
- [ ] T039 [US3] Implement VM inventory capture in lib/cleanup.sh (qm list → reports/vm_inventory.json)
- [ ] T040 [US3] Implement CLEANUP-002 check in lib/cleanup.sh (verify no processes hold locks via flock -n test)
- [ ] T041 [US3] Implement lock status probe in lib/cleanup.sh (capture lock state → reports/lock_status.json)
- [ ] T042 [US3] Add cleanup phase to scripts/lab/pve-lab (run cleanup checks unless --keep flag)
- [ ] T043 [US3] Add --keep flag handler in scripts/lab/pve-lab (mark cleanup checks as SKIP with reason)
- [ ] T044 [US3] Ensure all cleanup check evidence_refs use relative paths and are in evidence_manifest.json

---

## Phase 6: User Story 4 - Provenance and Repeatability (P3)

**Story Goal**: Capture exact run context in provenance.json for reproducibility and debugging

**Independent Test**: Run suite, verify `provenance.json` contains controller info, target info, harness git commit, selected profile, and all input parameters

**Implementation Tasks**:

- [ ] T045 [US4] Implement controller environment capture in lib/provenance.sh (os, bash version, ansible version)
- [ ] T046 [US4] Implement git status capture in lib/provenance.sh (commit SHA, branch, dirty status)
- [ ] T047 [US4] Add git dirty warning emitter in scripts/lab/pve-lab (warn if git working tree dirty but allow execution)
- [ ] T048 [US4] Implement target environment capture in lib/provenance.sh (pveversion, kernel, distro via SSH)
- [ ] T049 [US4] Implement parameters capture in lib/provenance.sh (selected profile, --keep flag, etc.)
- [ ] T050 [US4] Generate provenance.json at suite start in scripts/lab/pve-lab
- [ ] T051 [US4] Add provenance reference to summary.json

---

## Phase 7: User Story 5 - Legacy Compatibility (P3)

**Story Goal**: Support existing `--tier` and `--tier2-mode` flags with transparent profile mapping

**Independent Test**: Run `pve-lab run --tier 2 --tier2-mode plus`, verify it executes `hypervisor-nested-workload` profile and logs profile name in summary

**Implementation Tasks**:

- [ ] T052 [US5] Add legacy flag parser to scripts/lab/pve-lab (parse --tier and --tier2-mode)
- [ ] T053 [US5] Implement legacy-to-profile mapper in scripts/lab/pve-lab (tier=2 → hypervisor-control-plane, tier=2 mode=plus → hypervisor-nested-workload)
- [ ] T054 [US5] Add deprecation warning emitter in scripts/lab/pve-lab (show equivalent profile command)
- [ ] T055 [US5] Update summary.json to always include profile field (even for legacy commands)
- [ ] T056 [US5] Ensure legacy commands execute same profiles as modern suite command

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, error messages, schema validation, and terminology updates

- [ ] T057 [P] Add schema validation to lib/evidence.sh (validate checks.json, provenance.json, evidence_manifest.json against contracts/ using ajv-cli or python jsonschema)
- [ ] T058 [P] Update ansible/playbooks/lab_bootstrap.yml assertions to use assert module with fail_msg/success_msg
- [ ] T059 [P] Update ansible/playbooks/lab_tier2_pve.yml assertions to use assert module with fail_msg/success_msg
- [ ] T060 [P] Add clear error messages with remediation hints to all harness preflight checks in scripts/lab/pve-lab
- [ ] T061 [P] Update docs/architecture/019-proxmox-lab-harness.md with Profile definitions and examples
- [ ] T062 [P] Add Check catalog with sample outputs to docs/architecture/019-proxmox-lab-harness.md
- [ ] T063 [P] Add Evidence pack structure with sample files to docs/architecture/019-proxmox-lab-harness.md
- [ ] T064 [P] Add migration guide from legacy flags to profiles in docs/architecture/019-proxmox-lab-harness.md
- [ ] T065 [P] Create example console output showing check summary in docs/architecture/019-proxmox-lab-harness.md
- [ ] T066 [P] Create example JSON artifacts with annotations in docs/architecture/019-proxmox-lab-harness.md
- [ ] T067 [P] Replace all "tier2-min", "tier2-plus", "bundle" references with Profile/Evidence Pack terminology
- [ ] T068 Add performance logging to lib/provenance.sh (detect slow execution, log factors like disk/network)

---

## Dependencies & Parallel Execution

### Dependency Graph (User Story Completion Order)

```
Phase 1: Setup (T001-T008a)
  ↓
Phase 2: Foundational (T009-T015b)
  ↓
Phase 3: US1 (T016-T030) ← MUST complete first (provides core profile + check infrastructure)
  ↓
Phase 4-7 (US2, US3, US4, US5) ← Can be worked in any order after US1
  ↓
Phase 8: Polish (T057-T068) ← Final
```

### Parallel Opportunities Per Story

**User Story 1 (T016-T030)**:
- After T016-T020 (profile system): Can parallelize T021-T024 (different playbooks/roles)
- After T025-T026 (serializers): Can parallelize T027-T030 (different artifacts)

**User Story 2 (T031-T037)**:
- After T034 (validator ready): Can parallelize T031-T033 (different guard checks)

**User Story 3 (T038-T044)**:
- Can parallelize T038-T041 (CLEANUP-001 and CLEANUP-002 are independent)

**User Story 4 (T045-T051)**:
- Can parallelize T045-T046, T048 (controller, git, target captures are independent)

**User Story 5 (T052-T056)**:
- Mostly sequential (parser → mapper → warnings)

**Polish (T057-T068)**:
- Most tasks can run in parallel (different files)

---

## Implementation Strategy

### MVP Scope (Minimum Viable Product)
**Deliver first**: User Story 1 (T001-T030)  
**Why**: Provides core value - profile-driven execution with machine-readable evidence

### Incremental Delivery Order
1. **Phase 1+2**: Setup + Foundational (T001-T015b) - Required infrastructure
2. **Phase 3**: User Story 1 (T016-T030) - MVP: Profile-based suite execution with checks.json
3. **Phase 4**: User Story 2 (T031-T037) - Safety proof via negative tests
4. **Phase 5**: User Story 3 (T038-T044) - Cleanup verification
5. **Phase 6**: User Story 4 (T045-T051) - Provenance capture
6. **Phase 7**: User Story 5 (T052-T056) - Legacy compatibility
7. **Phase 8**: Polish (T057-T068) - Documentation and refinements

### Testing Checkpoints
- **After T030**: Run `pve-lab suite hypervisor-nested-workload`, verify checks.json structure
- **After T037**: Verify all GUARD-* checks have expected=FAIL, result=FAIL
- **After T044**: Run without --keep, verify CLEANUP-* checks show PASS
- **After T051**: Verify provenance.json contains all required fields
- **After T056**: Run legacy command, verify correct profile mapping

---

## Task Count Summary

- **Total Tasks**: 72
- **Phase 1 (Setup)**: 9 tasks (T001-T008a)
- **Phase 2 (Foundational)**: 9 tasks (T009-T015b)
- **Phase 3 (US1 - P1)**: 15 tasks
- **Phase 4 (US2 - P2)**: 8 tasks (T031-T037)
- **Phase 5 (US3 - P2)**: 7 tasks
- **Phase 6 (US4 - P3)**: 7 tasks
- **Phase 7 (US5 - P3)**: 5 tasks
- **Phase 8 (Polish)**: 12 tasks

**Parallelizable Tasks**: 29 tasks marked with [P]

---

## Format Validation

✅ All tasks follow checklist format: `- [ ] [TaskID] [P?] [Story?] Description with file path`  
✅ Task IDs sequential (T001-T068, plus T008a, T015a, T015b, T032a for inserted tasks)  
✅ Story labels present for US phases ([US1]-[US5])  
✅ No story labels for Setup/Foundational/Polish  
✅ File paths specified in descriptions  
✅ Parallel markers [P] applied to independent tasks

---

## Next Steps

1. Review this task breakdown with stakeholders
2. Begin implementation with Phase 1 (T001-T008a)
3. Complete Foundational phase (T009-T015b) before user stories
4. Deliver MVP (Phase 3: US1) first
5. Implement remaining user stories incrementally
6. Complete with Polish phase
