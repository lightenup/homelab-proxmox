# Quickstart Guide: Semantic & Safety Closure

**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Data Model**: [data-model.md](./data-model.md)

## Overview

This guide provides practical examples for using the profile-based lab harness with semantic checks, structured evidence, and real-time observability.

---

## Basic Usage

### Running a Profile

```bash
# Execute the hypervisor-nested-workload profile
./scripts/lab/pve-lab suite hypervisor-nested-workload

# Keep lab VMs after suite completes (skip cleanup)
./scripts/lab/pve-lab suite hypervisor-nested-workload --keep
```

**Console Output Example**:
```
[2025-12-31 12:30:00] Starting suite: hypervisor-nested-workload
[2025-12-31 12:30:00] Evidence pack: lab-20251231-123456
[2025-12-31 12:30:01] Phase: bootstrap
[2025-12-31 12:31:45] ✓ PVE-001: Proxmox VE packages installed
[2025-12-31 12:31:46] ✓ PVE-002: PVE services running
[2025-12-31 12:32:10] ✓ NET-001: DNS resolution working
[2025-12-31 12:33:00] ✓ NEST-001: Host KVM module supports nesting
[2025-12-31 12:35:23] ✓ GUARD-001: Tier2 playbook rejects execution without lab_inventory
[2025-12-31 12:40:00] Suite completed: SUCCESS (24/24 checks passed)
[2025-12-31 12:40:00] Evidence: artifacts/019-lab/lab-20251231-123456/
```

---

## Examining Evidence

### 1. Check Results (checks.json)

```bash
# View all check results
cat artifacts/019-lab/lab-20251231-123456/checks.json | jq

# Count passed checks
jq '.passed_count' artifacts/019-lab/lab-20251231-123456/checks.json

# Find failed checks
jq '.checks[] | select(.result == "FAIL")' artifacts/019-lab/lab-20251231-123456/checks.json

# View negative tests (guardrails)
jq '.checks[] | select(.expected == "FAIL")' artifacts/019-lab/lab-20251231-123456/checks.json
```

**Sample Output**:
```json
{
  "runid": "lab-20251231-123456",
  "profile": "hypervisor-nested-workload",
  "checks_count": 27,
  "passed_count": 24,
  "failed_count": 0,
  "skipped_count": 0,
  "error_count": 0,
  "checks": [
    {
      "check_id": "PVE-001",
      "title": "Proxmox VE packages installed",
      "severity": "high",
      "expected": "PASS",
      "result": "PASS",
      "reason": "pve-manager and pve-kernel packages found",
      "evidence_refs": ["reports/dpkg-list.txt"],
      "timestamp": "2025-12-31T12:31:45Z",
      "duration_ms": 234
    },
    {
      "check_id": "GUARD-001",
      "title": "Tier2 playbook rejects execution without lab_inventory=true",
      "severity": "blocker",
      "expected": "FAIL",
      "result": "FAIL",
      "reason": "Playbook correctly aborted with assertion: lab_inventory must be true",
      "evidence_refs": ["logs/guard-001-attempt.log"],
      "timestamp": "2025-12-31T12:35:23Z",
      "duration_ms": 145
    }
  ]
}
```

### 2. Provenance (provenance.json)

```bash
# View full provenance
jq '.' artifacts/019-lab/lab-20251231-123456/provenance.json

# Check git commit and dirty status
jq '.controller | {git_commit, git_branch, git_dirty}' artifacts/019-lab/lab-20251231-123456/provenance.json

# View target environment
jq '.target' artifacts/019-lab/lab-20251231-123456/provenance.json
```

**Sample Output**:
```json
{
  "runid": "lab-20251231-123456",
  "timestamp": "2025-12-31T12:30:00Z",
  "controller": {
    "os": "macOS 14.2 (23C64)",
    "bash_version": "5.2.15(1)-release",
    "ansible_version": "2.15.0",
    "jq_version": "1.6",
    "git_commit": "4955d58a1b2c",
    "git_branch": "019c1-semantic-safety-closure",
    "git_dirty": true
  },
  "target": {
    "hostname": "pve-lab-9001.local",
    "pveversion": "proxmox-ve: 8.1.0 (running kernel: 6.5.13-3-pve)",
    "kernel": "6.5.13-3-pve",
    "distro": "Debian 13 (trixie)",
    "architecture": "x86_64"
  },
  "profile": "hypervisor-nested-workload",
  "parameters": {
    "command": "pve-lab suite hypervisor-nested-workload",
    "keep": false,
    "extra_args": []
  }
}
```

### 3. Evidence Manifest (evidence_manifest.json)

```bash
# List all artifacts
jq '.artifacts[].path' artifacts/019-lab/lab-20251231-123456/evidence_manifest.json

# Find artifacts by type
jq '.artifacts[] | select(.type == "log")' artifacts/019-lab/lab-20251231-123456/evidence_manifest.json

# Show artifacts produced by specific check
jq '.artifacts[] | select(.produced_by == "PVE-002")' artifacts/019-lab/lab-20251231-123456/evidence_manifest.json
```

---

## Real-Time Monitoring

### Watch Suite Progress with JSONL Events

```bash
# Stream events to console (stderr -> stdout)
./scripts/lab/pve-lab suite hypervisor-nested-workload 2>&1 | grep '"event_type"'

# Pretty-print events
./scripts/lab/pve-lab suite hypervisor-nested-workload 2>&1 | grep '"event_type"' | jq

# Filter specific event types
./scripts/lab/pve-lab suite hypervisor-nested-workload 2>&1 | jq -c 'select(.event_type == "check_complete")'

# Monitor check results in real-time
./scripts/lab/pve-lab suite hypervisor-nested-workload 2>&1 | \
  jq -c 'select(.event_type == "check_complete") | {check_id: .data.check_id, result: .data.result}'
```

**Sample JSONL Events**:
```jsonl
{"timestamp":"2025-12-31T12:30:00Z","event_type":"suite_start","runid":"lab-20251231-123456","data":{"profile":"hypervisor-nested-workload","expected_duration_minutes":10}}
{"timestamp":"2025-12-31T12:30:01Z","event_type":"phase_start","runid":"lab-20251231-123456","data":{"phase":"bootstrap","type":"playbook","path":"ansible/playbooks/lab_bootstrap.yml"}}
{"timestamp":"2025-12-31T12:31:45Z","event_type":"check_start","runid":"lab-20251231-123456","data":{"check_id":"PVE-001","title":"Proxmox VE packages installed","severity":"high"}}
{"timestamp":"2025-12-31T12:31:45Z","event_type":"check_complete","runid":"lab-20251231-123456","data":{"check_id":"PVE-001","result":"PASS","duration_ms":234}}
{"timestamp":"2025-12-31T12:32:00Z","event_type":"warning","runid":"lab-20251231-123456","data":{"message":"Git working tree is dirty - results may not be reproducible"}}
{"timestamp":"2025-12-31T12:40:00Z","event_type":"suite_complete","runid":"lab-20251231-123456","data":{"status":"SUCCESS","passed_count":24,"failed_count":0}}
```

---

## Comparing Runs

### Compare Two Runs by Check Results

```bash
# Show which checks changed results between runs
jq -s '
  .[0].checks as $run1 |
  .[1].checks as $run2 |
  ($run1 + $run2 | group_by(.check_id) | map({
    check_id: .[0].check_id,
    run1_result: .[0].result,
    run2_result: .[1].result,
    changed: (.[0].result != .[1].result)
  }) | map(select(.changed)))
' \
  artifacts/019-lab/lab-20251231-123456/checks.json \
  artifacts/019-lab/lab-20251231-140000/checks.json
```

**Sample Output**:
```json
[
  {
    "check_id": "NET-001",
    "run1_result": "PASS",
    "run2_result": "FAIL",
    "changed": true
  },
  {
    "check_id": "WORK-003",
    "run1_result": "PASS",
    "run2_result": "SKIP",
    "changed": true
  }
]
```

### Compare Provenance (Environment Differences)

```bash
# Show differences in controller environment
jq -s '[.[].controller] | unique' \
  artifacts/019-lab/lab-20251231-123456/provenance.json \
  artifacts/019-lab/lab-20251231-140000/provenance.json

# Check if git commits differ
jq -s 'if .[0].controller.git_commit == .[1].controller.git_commit then "SAME" else "DIFFERENT" end' \
  artifacts/019-lab/lab-20251231-123456/provenance.json \
  artifacts/019-lab/lab-20251231-140000/provenance.json
```

---

## Legacy Compatibility

### Using Deprecated Flags

```bash
# Old style (deprecated but still works)
./scripts/lab/pve-lab run --tier 2 --tier2-mode plus

# Console shows deprecation warning:
# WARNING: --tier and --tier2-mode are deprecated. Use: pve-lab suite hypervisor-nested-workload

# New style (recommended)
./scripts/lab/pve-lab suite hypervisor-nested-workload
```

**Legacy Flag Mapping**:
| Old Command | Maps To Profile |
|-------------|-----------------|
| `--tier 2` | `hypervisor-control-plane` |
| `--tier 2 --tier2-mode plus` | `hypervisor-nested-workload` |

---

## Profile Discovery

### List Available Profiles

```bash
# List all profiles
ls -1 scripts/lab/profiles.d/*.profile | sed 's/.*\///; s/\.profile$//'

# View profile details
source scripts/lab/profiles.d/hypervisor-nested-workload.profile
echo "Profile: $PROFILE_ID"
echo "Display: $DISPLAY_NAME"
echo "Checks: ${#CHECKS[@]}"
printf "  %s\n" "${CHECKS[@]}"
```

**Expected Output**:
```
hypervisor-control-plane
hypervisor-nested-workload

Profile: hypervisor-nested-workload
Display: Hypervisor with Nested Workload Validation
Checks: 27
  PVE-001
  PVE-002
  NET-001
  NEST-001
  ...
```

---

## Troubleshooting

### View Failed Check Details

```bash
# Show all failed checks with reasons
jq '.checks[] | select(.result == "FAIL") | {check_id, title, reason, evidence_refs}' \
  artifacts/019-lab/lab-20251231-123456/checks.json
```

### Inspect Check Evidence

```bash
# View evidence referenced by a specific check
CHECK_ID="PVE-002"
EVIDENCE_PACK="artifacts/019-lab/lab-20251231-123456"

# Get evidence refs for the check
REFS=$(jq -r ".checks[] | select(.check_id == \"$CHECK_ID\") | .evidence_refs[]" "$EVIDENCE_PACK/checks.json")

# View each evidence file
for ref in $REFS; do
  echo "=== $ref ==="
  cat "$EVIDENCE_PACK/$ref"
done
```

### Replay JSONL Event Stream

```bash
# View entire event stream
jq '.' artifacts/019-lab/lab-20251231-123456/logs/commands.jsonl

# Timeline of check executions
jq -s 'map(select(.event_type == "check_start" or .event_type == "check_complete")) | 
  group_by(.data.check_id) | 
  map({check_id: .[0].data.check_id, events: map({event_type, timestamp})})' \
  artifacts/019-lab/lab-20251231-123456/logs/commands.jsonl
```

---

## Advanced Usage

### Custom Analysis Scripts

```bash
# Calculate total execution time per check namespace
jq -r '.checks[] | "\(.check_id | split("-")[0])\t\(.duration_ms)"' \
  artifacts/019-lab/lab-20251231-123456/checks.json | \
  awk '{ns[$1]+=$2; count[$1]++} END {for (n in ns) print n, ns[n]/count[n] "ms avg"}'
```

**Sample Output**:
```
PVE 245ms avg
NET 189ms avg
NEST 1234ms avg
WORK 890ms avg
GUARD 156ms avg
CLEANUP 67ms avg
```

### Generate Summary Report

```bash
# Create human-readable report
PACK="artifacts/019-lab/lab-20251231-123456"
echo "=== Lab Harness Run Report ==="
jq -r '"Run ID: \(.runid)", "Profile: \(.profile)", "Status: \(.status)", "Duration: \(.duration_seconds)s"' \
  "$PACK/summary.json"
echo ""
echo "=== Check Summary ==="
jq -r '.checks_summary | "Total: \(.total)", "Passed: \(.passed)", "Failed: \(.failed)"' \
  "$PACK/summary.json"
echo ""
echo "=== Environment ==="
jq -r '.controller | "Controller: \(.os)", "Git: \(.git_branch)@\(.git_commit[0:7]) (dirty: \(.git_dirty))"' \
  "$PACK/provenance.json"
jq -r '.target | "Target: \(.hostname)", "PVE: \(.pveversion)"' \
  "$PACK/provenance.json"
```

---

## Next Steps

After running your first suite:
1. Review [data-model.md](./data-model.md) for detailed entity schemas
2. Examine JSON schemas in [contracts/](./contracts/) for validation
3. See [spec.md](./spec.md) for complete requirements and user stories
4. Use `/speckit.tasks` to break down implementation into actionable tasks

## Quick Reference

| Task | Command |
|------|---------|
| Run profile | `./scripts/lab/pve-lab suite <profile>` |
| Keep VMs | `./scripts/lab/pve-lab suite <profile> --keep` |
| View checks | `jq '.checks' artifacts/019-lab/<runid>/checks.json` |
| View provenance | `jq '.' artifacts/019-lab/<runid>/provenance.json` |
| Monitor real-time | `pve-lab suite <profile> 2>&1 \| jq` |
| Compare runs | `jq -s '...' run1/checks.json run2/checks.json` |
| List profiles | `ls scripts/lab/profiles.d/*.profile` |
