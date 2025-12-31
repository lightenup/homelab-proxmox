# Implementation Plan: Semantic & Safety Closure

**Branch**: `019c1-semantic-safety-closure` | **Date**: 2025-12-31 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `specs/019c1-semantic-safety-closure/spec.md`

## Summary

Establish first-class semantic concepts (Profiles, Checks, Evidence Packs) for the Lab Harness Confidence Suite. Replace vague terminology ("tier2", "plus") with stable, machine-readable structures that enable automated comparison, guardrail proof, cleanup verification, and full provenance tracking. Implement negative tests to prove safety, structured JSONL event streams for observability, and legacy flag compatibility.

## Technical Context

**Language/Version**: Bash 5.x (existing `pve-lab` script)  
**Primary Dependencies**: jq (JSON processing), git (provenance capture), existing Ansible playbooks  
**Storage**: File-based evidence packs in `artifacts/019-lab/<runid>/`  
**Testing**: Negative test harness (GUARD-* checks), integration validation via suite execution  
**Target Platform**: macOS controller → Proxmox VE 8.x targets (Debian 13 lab VMs)  
**Project Type**: Shell scripting enhancement + JSON schema definitions  
**Performance Goals**: <10 minutes for `hypervisor-nested-workload` profile (95th percentile)  
**Constraints**:
  - Non-destructive to production (all negative tests isolated)
  - No external dependencies (no cloud services, dashboards)
  - Backward compatible with existing `--tier`/`--tier2-mode` flags
  - Check IDs immutable (allocate new IDs for behavior changes, not versioned)
  - Artifact schemas versioned via checks_schema_version and manifest_schema_version fields
**Scale/Scope**: 
  - 2 initial profiles (hypervisor-control-plane, hypervisor-nested-workload)
  - 24+ checks across 6 namespaces
  - 5 JSONL event types
  - ~500 lines new/modified shell code

## Constitution Check

### Spec-Driven Workflow ✅ PASS
- This work is driven from `specs/019c1-semantic-safety-closure/`
- All changes will reference this spec
- Changes documented in spec amendments

### Secrets Policy ✅ PASS
- No secrets involved (lab harness orchestration only)
- Uses existing SSH keys from Terraform/Ansible
- No new credential management

### Separation of Concerns ✅ PASS
- Lab harness orchestrates Terraform (VM provisioning) and Ansible (configuration)
- Does not mix responsibilities
- Observes existing boundaries (scripts/lab/ for orchestration, terraform/ for infra, ansible/ for config)

### Architecture & Boundaries ✅ PASS
- No provider changes
- No networking changes (lab harness operates on existing lab VMs)
- Uses existing SSH access patterns
- Lab environment only (strict hostname/inventory guards prevent production impact)

### Violations: NONE

## Project Structure

### Documentation (this feature)

```text
specs/019c1-semantic-safety-closure/
├── spec.md              # Feature specification (COMPLETE)
├── plan.md              # This file
├── research.md          # Phase 0: Technology decisions and patterns
├── data-model.md        # Phase 1: Profile, Check, Evidence Pack schemas
├── quickstart.md        # Phase 1: Usage examples with CLI commands
└── contracts/           # Phase 1: JSON schemas for artifacts
    ├── profile.schema.json
    ├── check.schema.json
    ├── checks.schema.json
    ├── evidence-manifest.schema.json
    ├── provenance.schema.json
    ├── summary.schema.json
    └── jsonl-event.schema.json
```

### Source Code (repository root)

```text
scripts/lab/
├── pve-lab                    # MODIFIED: Add profile system, check recording, JSONL emission
├── profiles.d/                # NEW: Profile definitions
│   ├── hypervisor-control-plane.profile
│   └── hypervisor-nested-workload.profile
├── lib/                       # NEW: Shared functions
│   ├── checks.sh              # Check recording and accumulation
│   ├── jsonl.sh               # JSONL event emission to stderr
│   ├── provenance.sh          # Provenance capture (git, versions, env)
│   └── evidence.sh            # Evidence pack management
└── guardrails.sh              # NEW: Negative test harness (GUARD-* checks)

ansible/playbooks/
├── lab_bootstrap.yml          # MODIFIED: Emit check records
├── lab_tier2_pve.yml          # MODIFIED: Emit check records, readable assertions
└── roles/validation/          # MODIFIED: Emit structured check results

docs/architecture/
└── 019-proxmox-lab-harness.md # UPDATED: Profile catalog, check catalog, evidence pack examples

artifacts/019-lab/
└── lab-YYYYMMDD-HHMMSS/       # Evidence pack structure (generated per run)
    ├── checks.json            # NEW: Canonical check results (includes checks_schema_version)
    ├── evidence_manifest.json # NEW: Artifact inventory (includes manifest_schema_version)
    ├── provenance.json        # NEW: Run context
    ├── summary.json           # MODIFIED: Add profile reference
    ├── logs/
    │   ├── run.log            # Main execution log
    │   ├── bootstrap.log      # Bootstrap phase output
    │   ├── tier2.log          # Tier2 phase output
    │   ├── events.jsonl       # NEW: Real-time progress events
    │   └── commands.jsonl     # Command timing records (existing, if present)
    └── reports/
        ├── validation.json
        ├── pveversion.txt
        └── systemctl-status.txt
```

**Structure Decision**: Single scripting project with modular functions. Lab harness (`pve-lab`) remains the entrypoint, with new lib/ directory for shared check/provenance/JSONL functions. Profiles defined as declarative files in profiles.d/. Existing Ansible structure preserved with instrumentation additions.

## Phases

### Phase 0: Research & Decisions (OUTPUT: research.md)

**Objective**: Resolve all NEEDS CLARIFICATION items from Technical Context, establish patterns for check recording, JSONL emission, and negative test execution.

**Research Tasks**:
1. **Bash JSON generation patterns**: Determine strategy for emitting valid JSON from bash (heredoc, jq, printf)
2. **JSONL emission to stderr**: Establish pattern for non-blocking structured logging while preserving stdout for summaries. Note: Progress events go to logs/events.jsonl, command timing (if present) to logs/commands.jsonl
3. **Negative test isolation**: Design safe execution pattern for guardrail tests (GUARD-002: temporary inventory with bad hostname; GUARD-003: dry-run validation with synthetic config; no real unsafe VM creation)
4. **Git provenance capture**: Determine commands for detecting dirty working tree, capturing commit SHA, branch name
5. **Ansible check instrumentation**: Identify pattern for emitting check records from playbook tasks without disrupting idempotency
6. **Check ID allocation strategy**: Define numbering scheme within namespaces (PVE-001 to PVE-099, etc.)
7. **Profile schema format**: Choose profile definition format (JSON, YAML, bash-sourceable config)

**Decisions to Document** (in research.md):
- Check recording mechanism (function signature, accumulator pattern)
- JSONL event schema and emission timing
- Profile loading and validation approach
- Negative test execution model
- Legacy flag mapping logic

**Output**: `research.md` with decisions, rationale, alternatives considered, and code patterns for each area.

---

### Phase 1: Design & Contracts (OUTPUT: data-model.md, contracts/, quickstart.md)

**Objective**: Define concrete data structures, JSON schemas, and API surface. Generate usage examples.

#### 1a: Data Model (data-model.md)

**Entities to Define**:

1. **Profile**
   - Fields: profile_id (PRIMARY KEY), display_name, safety_level (PRIMARY KEY), tier (legacy-derived), mode (legacy-derived), expected_duration_minutes, prerequisites, checks
   - Relationships: Profile → [Check IDs]
   - Validation rules: profile_id kebab-case, checks array non-empty
   - State transitions: N/A (declarative)
   - Note: tier/mode are backward compatibility fields; profile_id and safety_level are primary semantics

2. **Check**
   - Fields: check_id (immutable), title, severity, expected, result, reason, evidence_refs (relative paths from evidence pack root), timestamp, duration_ms
   - Relationships: Check → [Evidence Artifacts] (all evidence_refs must be in evidence_manifest.json)
   - Validation rules: check_id matches namespace pattern, result in [PASS, FAIL, SKIP, ERROR]
   - State transitions: (not started) → (executing) → (complete with result)
   - Abort behavior: See "Suite Execution Semantics" section in spec (blocker failures and negative test unexpected passes abort)

3. **Evidence Pack**
   - Fields: runid, profile, start_time, end_time, status, artifact_count
   - Relationships: Evidence Pack → [Artifacts], Evidence Pack → Profile
   - Directory structure as defined in spec (logs/events.jsonl for progress events)
   - Schema versioning: checks.json includes checks_schema_version, evidence_manifest.json includes manifest_schema_version
   - State transitions: (created) → (collecting) → (finalized) / (interrupted)

3a. **Checks Collection** (checks.json structure)
   - Fields: runid, profile, checks_schema_version, counts{total, pass, fail, skip, error}, checks[]
   - Schema evolution tracking via checks_schema_version field

3b. **Evidence Manifest** (evidence_manifest.json structure)
   - Fields: runid, manifest_schema_version, generated_at, artifacts[]
   - Schema evolution tracking via manifest_schema_version field

4. **Provenance**
   - Fields: controller{os, bash_version, ansible_version, git_commit, git_dirty}, target{pveversion, kernel, distro}, profile, parameters
   - Captures immutable context of run

5. **JSONL Event**
   - Fields: timestamp, event_type, runid, event-specific data
   - Event types: check_start, check_complete, phase_start, phase_complete, error, warning

#### 1b: JSON Schemas (contracts/)

Generate JSON Schema files for:
- `profile.schema.json`: Profile definition structure
- `check.schema.json`: Individual check structure
- `checks.schema.json`: Array of checks with metadata
- `evidence-manifest.schema.json`: Artifact inventory structure
- `provenance.schema.json`: Run context structure
- `summary.schema.json`: Enhanced summary with profile reference
- `jsonl-event.schema.json`: Event stream entry structure

Each schema includes:
- Required fields
- Field types and formats
- Enum constraints where applicable
- Examples in description fields

#### 1c: Quickstart Guide (quickstart.md)

**Content**:
1. **Profile-based execution**: `pve-lab suite hypervisor-nested-workload`
2. **Evidence examination**: `cat artifacts/019-lab/lab-20251231-123456/checks.json | jq`
3. **Real-time monitoring**: `tail -f artifacts/019-lab/lab-20251231-123456/logs/events.jsonl | jq`
4. **Legacy compatibility**: `pve-lab run --tier 2 --tier2-mode plus` (with deprecation warning)
5. **Comparing runs**: `jq -s '.[0].checks - .[1].checks' run1/checks.json run2/checks.json`
6. **Provenance inspection**: `jq '.controller.git_commit, .target.pveversion' provenance.json`
7. **Evidence refs validation**: All paths in check.evidence_refs are relative (e.g., "reports/systemctl-status.txt")

Include sample outputs showing:
- Console checklist format
- JSONL event examples
- checks.json structure
- Negative test results (expected=FAIL, result=FAIL)

---

### Phase 1d: Agent Context Update

**Action**: Run `.specify/scripts/bash/update-agent-context.sh copilot` to update Copilot's context file with:
- Profile-based architecture
- Check ID namespaces and immutability rule
- JSONL observability pattern
- Evidence pack structure
- Negative test approach

This ensures Copilot can reference these concepts in future interactions.

---

### Phase 2: Task Breakdown (OUTPUT: tasks.md)

**Note**: Phase 2 is completed by `/speckit.tasks` command, not by `/speckit.plan`. The following is an outline of expected task categories:

#### Task Categories (Preview):

1. **Core Infrastructure** (lib/ functions)
   - Implement check recording (`checks.sh`)
   - Implement JSONL emission (`jsonl.sh`)
   - Implement provenance capture (`provenance.sh`)
   - Implement evidence pack management (`evidence.sh`)

2. **Profile System**
   - Create profile schema and loader
   - Define initial profiles (hypervisor-control-plane, hypervisor-nested-workload)
   - Add profile selection to `pve-lab suite` command

3. **Check Integration**
   - Instrument existing validations to emit checks
   - Add check accumulator to suite execution
   - Serialize checks to checks.json
   - Add console formatter for check summary

4. **Negative Tests**
   - Create guardrails.sh with safe execution harness
   - Implement GUARD-001 (override lab_inventory=false)
   - Implement GUARD-002 (temporary inventory with non-lab hostname)
   - Implement GUARD-003 (dry-run validation with synthetic qm config, no real VM creation)
   - Add expected vs actual result validation
   - Add ERROR condition for guardrail breaches (unexpected PASS aborts)

5. **Cleanup Proof**
   - Implement CLEANUP-001 (VM inventory check: no VMs in 9000-9099 range with lab markers)
   - Implement CLEANUP-002 (lock status check: no processes hold locks, verified with flock -n or equivalent)
   - Handle --keep flag in cleanup logic (mark SKIP with reason)
   - Ensure all evidence_refs use relative paths and are listed in evidence_manifest.json

6. **Artifacts & Provenance**
   - Generate provenance.json (git commit, git dirty status, versions, env)
   - Generate evidence_manifest.json with manifest_schema_version
   - Update summary.json schema to include profile reference
   - Capture events.jsonl (real-time progress events to stderr → logs/events.jsonl)
   - Add checks_schema_version to checks.json

7. **Legacy Compatibility**
   - Map --tier/--tier2-mode to profiles
   - Add deprecation warnings
   - Update documentation

8. **Documentation**
   - Update architecture doc with profile/check catalog
   - Add example artifacts with annotations
   - Create migration guide

## Complexity Tracking

No constitution violations. All changes align with existing architecture and boundaries.

## Gates & Prerequisites

**Before Phase 0 Research**:
- ✅ Constitution check passed
- ✅ Feature spec complete and clarified
- ✅ Dependencies identified (019a, 019b, 019b1, 019c)

**Before Phase 1 Design**:
- ⏳ Research.md complete (all patterns decided)
- ⏳ Example JSON structures validated manually

**Before Phase 2 Tasks**:
- ⏳ data-model.md complete
- ⏳ contracts/ schemas generated and validated
- ⏳ quickstart.md with working examples
- ⏳ Agent context updated

**Before Implementation**:
- ⏳ tasks.md approved
- ⏳ Test plan defined for each task category

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Check ID namespace collision | Low | Medium | Document allocation strategy in research.md, reserve ranges |
| JSONL emission breaks existing log parsing | Low | Low | Use stderr only, preserve stdout format |
| Negative tests impact production | Very Low | Critical | Triple-check hostname/inventory guards, test in lab first |
| Performance regression (>10 min) | Medium | Low | Profile execution, optimize check serialization if needed |
| Legacy flag mapping ambiguity | Low | Low | Document mapping table, emit warnings showing equivalent command |
| Bash JSON generation errors | Medium | Medium | Use jq for all JSON generation, validate schemas in tests |

## Success Criteria Recap

- ✅ Every suite run produces checks.json with stable check_ids
- ✅ Console output includes compact checklist (<2 lines per check)
- ✅ Negative tests execute safely and record as expected failures
- ✅ Cleanup checks pass for 100% of runs without --keep
- ✅ Provenance.json captures reproducible context
- ✅ Legacy commands work and map correctly
- ✅ Evidence packs generated for 100% of runs
- ✅ Documentation explains all concepts with examples
- ✅ hypervisor-nested-workload completes within 10 minutes (95th percentile)

---

**Next Steps**: 
1. Execute Phase 0 research (generate research.md)
2. Execute Phase 1 design (generate data-model.md, contracts/, quickstart.md)
3. Update agent context with new architecture
4. Wait for `/speckit.tasks` command to generate tasks.md
