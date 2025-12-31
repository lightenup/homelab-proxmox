# Research: Semantic & Safety Closure

**Date**: 2025-12-31  
**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

## Overview

This document resolves technical unknowns and establishes implementation patterns for the semantic & safety closure feature. All decisions are grounded in the existing lab harness codebase (bash + Ansible) with minimal external dependencies.

---

## Research Area 1: Bash JSON Generation Patterns

### Decision: Use jq for all JSON generation

**Rationale**:
- jq is already a dependency (used in existing lab harness)
- Handles escaping, quoting, and encoding correctly
- Produces valid JSON without manual string manipulation
- Supports streaming with `--compact-output` for JSONL

**Pattern**:
```bash
# Single object
jq -n \
  --arg check_id "PVE-001" \
  --arg title "PVE packages installed" \
  --arg result "PASS" \
  '{check_id: $check_id, title: $title, result: $result, timestamp: now | todate}'

# Array accumulation
CHECKS_JSON=$(jq -n '[]')
CHECKS_JSON=$(echo "$CHECKS_JSON" | jq '. + [{"check_id": "PVE-001", "result": "PASS"}]')
```

**Alternatives Considered**:
- **Heredoc with variable substitution**: Fragile with quotes/newlines, no validation
- **printf with manual escaping**: Error-prone, doesn't handle nested structures
- **Python one-liners**: Adds dependency, slower startup for many small calls

---

## Research Area 2: JSONL Emission to stderr

### Decision: Emit JSONL to stderr with timestamped events, tee to commands.jsonl

**Rationale**:
- stderr keeps stdout clean for human-readable summaries
- JSONL (newline-delimited JSON) is streaming-friendly
- Can be piped to monitoring tools: `pve-lab suite 2>&1 | grep ...`
- No blocking or buffering issues

**Pattern**:
```bash
# In lib/jsonl.sh
emit_event() {
    local event_type="$1"
    shift
    jq -n -c \
        --arg type "$event_type" \
        --arg runid "$RUNID" \
        --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        --argjson data "$(jq -n "$@")" \
        '{timestamp: $ts, event_type: $type, runid: $runid, data: $data}' >&2
}

# Usage
emit_event "check_start" --arg check_id "PVE-001" '{check_id: $check_id}'
```

**Capture to file**:
```bash
# In pve-lab main
exec 2> >(tee -a "$EVIDENCE_DIR/logs/commands.jsonl" >&2)
```

**Alternatives Considered**:
- **Separate log file (not stderr)**: Requires operators to know about additional file
- **Stdout**: Would pollute human-readable output
- **TCP/UDP to external service**: Violates "no external dependencies" constraint

---

## Research Area 3: Negative Test Isolation

### Decision: Validation-only mode with expected-failure checks

**Rationale**:
- Ansible `assert` module can validate conditions without applying changes
- Check conditions without triggering guard failures
- Record expected=FAIL, result=FAIL when guard blocks operation
- No actual resources created or destroyed

**Pattern**:
```bash
# In guardrails.sh
run_guard_check() {
    local check_id="$1"
    local guard_var="$2"
    local guard_value="$3"
    
    # Attempt operation with guard variable unset/wrong
    if ansible-playbook playbook.yml -e "${guard_var}=${guard_value}" --check 2>&1 | grep -q "Guard failed"; then
        # Guard correctly blocked operation
        record_check "$check_id" "FAIL" "FAIL" "Guard ${guard_var} correctly blocked"
    else
        # ERROR: guard didn't block
        record_check "$check_id" "FAIL" "PASS" "ERROR: Guard breach - safety hole detected"
        exit 1
    fi
}
```

**Guard Checks**:
- **GUARD-001**: Attempt tier2 playbook with `lab_inventory=false` → assert failure expected
- **GUARD-002**: Attempt playbook against non-lab hostname → assert failure expected  
- **GUARD-003**: Attempt VM destroy without identity markers → validation check expects no matches

**Alternatives Considered**:
- **Mock environment**: Complex setup, doesn't test real guards
- **Separate test inventory**: Still risks production if misconfigured
- **Assert-only playbooks**: Closest to actual validation without side effects (SELECTED)

---

## Research Area 4: Git Provenance Capture

### Decision: Use git commands with fallbacks for non-repo scenarios

**Pattern**:
```bash
# In lib/provenance.sh
capture_git_provenance() {
    local commit dirty branch
    
    if git rev-parse --git-dir >/dev/null 2>&1; then
        commit=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
        branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
        
        # Check for uncommitted changes
        if [[ -n $(git status --porcelain 2>/dev/null) ]]; then
            dirty="true"
            echo "WARNING: Git working tree is dirty - results may not be reproducible" >&2
        else
            dirty="false"
        fi
    else
        commit="not-a-git-repo"
        branch="unknown"
        dirty="false"
    fi
    
    jq -n \
        --arg commit "$commit" \
        --arg branch "$branch" \
        --arg dirty "$dirty" \
        '{git_commit: $commit, git_branch: $branch, git_dirty: ($dirty == "true")}'
}
```

**Alternatives Considered**:
- **Abort on dirty tree**: Too restrictive for development workflows
- **Ignore dirty status**: Loses reproducibility information
- **Capture diff**: Too verbose, sensitive info risk (REJECTED)

---

## Research Area 5: Ansible Check Instrumentation

### Decision: Use `set_fact` with `run_once` to emit check records to controller

**Rationale**:
- Ansible facts can be accessed by controller after playbook completes
- `delegate_to: localhost` writes check records to controller filesystem
- Preserves idempotency (checks are read-only observations)
- No changes to task failure behavior

**Pattern**:
```yaml
# In playbook
- name: Check PVE Services Running
  command: systemctl is-active pveproxy pvedaemon pve-cluster
  register: pve_services
  failed_when: pve_services.rc != 0
  
- name: Record PVE-002 Check
  delegate_to: localhost
  run_once: true
  shell: |
    {{ playbook_dir }}/../scripts/lab/lib/checks.sh record_check \
      "PVE-002" \
      "{{ 'PASS' if pve_services.rc == 0 else 'FAIL' }}" \
      "{{ pve_services.stderr | default('Services active') }}"
```

**Alternative - JSON accumulation**:
```yaml
- name: Emit Check JSON
  delegate_to: localhost
  run_once: true
  copy:
    dest: "{{ evidence_dir }}/checks_partial.json"
    content: |
      {{ {
        'check_id': 'PVE-002',
        'result': 'PASS' if pve_services.rc == 0 else 'FAIL',
        'timestamp': ansible_date_time.iso8601
      } | to_json }}
```

**Alternatives Considered**:
- **Ansible callback plugin**: Complex, requires plugin installation
- **Parse Ansible JSON output**: Fragile, depends on output format
- **Separate validation playbook**: Duplicates logic (REJECTED)

---

## Research Area 6: Check ID Allocation Strategy

### Decision: Reserve ranges within namespaces, document allocations

**Namespace Ranges** (001-099 per namespace):
- **PVE-001 to PVE-099**: Proxmox VE installation/config
- **NET-001 to NET-099**: Network configuration/connectivity
- **NEST-001 to NEST-099**: Nested virtualization
- **WORK-001 to WORK-099**: Workload deployment
- **GUARD-001 to GUARD-099**: Safety guardrails
- **CLEANUP-001 to CLEANUP-099**: Cleanup verification
- **ENV-001 to ENV-099**: Environment preflight

**Allocation Rules**:
1. Allocate sequentially within namespace (PVE-001, PVE-002, ...)
2. Document allocation in `docs/architecture/019-proxmox-lab-harness.md`
3. Never reuse retired check IDs
4. Reserve gaps for future expansion (e.g., skip to PVE-010 for new category)

**Current Allocations** (from spec):
```text
PVE-001: Proxmox VE packages installed
PVE-002: PVE services running
PVE-003: pmxcfs mounted
PVE-004: pvesh API reachable
PVE-005: pveversion reports expected version

NET-001: DNS resolution working
NET-002: Internet connectivity working
NET-003: vmbr0 bridge configured
NET-004: Lab VM reachable via ProxyJump SSH

NEST-001: Host KVM module supports nesting
NEST-002: Guest /dev/kvm exists
NEST-003: Nested VM can be created
NEST-004: Nested LXC can be created

WORK-001: LXC template downloaded
WORK-002: Storage configured correctly
WORK-003: Nested LXC network connectivity
WORK-004: Service reachability verified

GUARD-001: Tier2 playbook rejects execution without lab_inventory=true
GUARD-002: Playbook rejects non-lab hostname
GUARD-003: Destroy command rejects VM missing identity markers

CLEANUP-001: No lab VMs remain in range
CLEANUP-002: No active locks remain

ENV-001: Target is lab environment
ENV-002: Required resources available
```

**Alternatives Considered**:
- **Semantic versioning in ID**: Verbose (PVE-001.v2) (REJECTED per clarification)
- **Hash-based IDs**: Not human-readable (REJECTED)
- **UUID-based**: Too long for console output (REJECTED)

---

## Research Area 7: Profile Schema Format

### Decision: Bash-sourceable config files with `.profile` extension

**Rationale**:
- Simple to parse in bash (`source` command)
- No external parser needed (jq, yq)
- Easy for humans to read/edit
- Can include bash logic if needed (though discouraged)

**Format**:
```bash
# profiles.d/hypervisor-nested-workload.profile
PROFILE_ID="hypervisor-nested-workload"
DISPLAY_NAME="Hypervisor with Nested Workload Validation"
TIER=2
MODE="plus"
SAFETY_LEVEL="strict"
EXPECTED_DURATION_MINUTES=10

# Prerequisites (bash array)
PREREQUISITES=(
    "nested-kvm"
    "min-memory-4g"
)

# Expected checks (bash array)
CHECKS=(
    "PVE-001" "PVE-002" "PVE-003" "PVE-004" "PVE-005"
    "NET-001" "NET-002" "NET-003" "NET-004"
    "NEST-001" "NEST-002" "NEST-003" "NEST-004"
    "WORK-001" "WORK-002" "WORK-003" "WORK-004"
    "GUARD-001" "GUARD-002" "GUARD-003"
    "CLEANUP-001" "CLEANUP-002"
    "ENV-001" "ENV-002"
)

# Execution phases
PHASES=(
    "bootstrap:ansible/playbooks/lab_bootstrap.yml"
    "tier2:ansible/playbooks/lab_tier2_pve.yml"
    "validation:ansible/roles/validation/tasks/main.yml"
    "guardrails:scripts/lab/guardrails.sh"
    "cleanup:scripts/lab/lib/cleanup.sh"
)
```

**Loading Pattern**:
```bash
load_profile() {
    local profile_name="$1"
    local profile_file="$SCRIPT_DIR/profiles.d/${profile_name}.profile"
    
    if [[ ! -f "$profile_file" ]]; then
        echo "ERROR: Profile not found: $profile_name" >&2
        exit 1
    fi
    
    source "$profile_file"
    
    # Validate required fields
    [[ -n "$PROFILE_ID" ]] || { echo "ERROR: PROFILE_ID missing"; exit 1; }
    [[ -n "$DISPLAY_NAME" ]] || { echo "ERROR: DISPLAY_NAME missing"; exit 1; }
    [[ ${#CHECKS[@]} -gt 0 ]] || { echo "ERROR: CHECKS array empty"; exit 1; }
}
```

**Alternatives Considered**:
- **JSON**: Requires jq for parsing, awkward for bash arrays
- **YAML**: Requires yq/python, adds dependency
- **INI format**: No native bash support for arrays
- **Embedded in pve-lab script**: Hard to extend (REJECTED)

---

## Implementation Patterns Summary

### Check Recording Flow
```
1. Playbook task executes → result captured in register
2. Delegate task writes check to controller: lib/checks.sh record_check
3. Check accumulated in global array (in pve-lab script context)
4. At end of suite: serialize array to checks.json via jq
```

### JSONL Event Emission Flow
```
1. Suite starts → emit_event "phase_start" (profile, runid)
2. Before check → emit_event "check_start" (check_id, title)
3. After check → emit_event "check_complete" (check_id, result, duration)
4. Phase completes → emit_event "phase_complete" (phase, status)
5. All events captured to commands.jsonl via stderr tee
```

### Legacy Flag Mapping
```bash
# In pve-lab command handler
if [[ -n "$OPT_TIER" ]]; then
    case "$OPT_TIER" in
        2)
            if [[ "$OPT_TIER2_MODE" == "plus" ]]; then
                PROFILE="hypervisor-nested-workload"
            else
                PROFILE="hypervisor-control-plane"
            fi
            echo "WARNING: --tier and --tier2-mode are deprecated. Use: pve-lab suite $PROFILE" >&2
            ;;
        *)
            echo "ERROR: Unsupported tier: $OPT_TIER" >&2
            exit 1
            ;;
    esac
fi
```

---

## Dependencies & Tools

**Required** (already available):
- bash 5.x
- jq 1.6+
- git 2.x
- ansible 2.x
- ssh, ssh-keygen
- coreutils (date, tee)

**No New Dependencies Required**

---

## Performance Considerations

### JSON Generation Overhead
- jq invocations: ~5-10ms each on modern hardware
- 30 checks × 2 jq calls = ~300-600ms total overhead
- Acceptable within 10-minute target

### JSONL Streaming
- stderr tee has minimal overhead (<1ms per event)
- Async to main execution path
- No blocking on I/O

### Profile Loading
- Bash `source` is fast (<1ms per profile)
- One-time cost at suite start

**Optimization Strategy**: If performance becomes an issue, batch jq calls (single jq invocation with multiple inputs) rather than one per check.

---

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| jq not installed | Check in preflight, clear error message |
| JSON escaping errors | Use jq `--arg` for all user inputs (no direct interpolation) |
| JSONL parsing errors downstream | Validate schema with jq before emission |
| Bash array handling | Quote all array expansions: `"${CHECKS[@]}"` |
| Guardrail test false positives | Triple-check assertions, test in lab first |

---

## Next Steps

With all technical decisions resolved, proceed to Phase 1:
1. **data-model.md**: Define entities with concrete field types
2. **contracts/**: Generate JSON schemas from data model
3. **quickstart.md**: Create usage examples with real commands
4. **Update agent context**: Run update-agent-context.sh

All patterns documented here are ready for implementation.
