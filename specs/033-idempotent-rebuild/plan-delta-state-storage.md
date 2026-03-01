# Implementation Plan: Idempotent Rebuild - State Storage & Services Execution (Delta)

**Branch**: `033-idempotent-rebuild` | **Date**: 2026-02-09 | **Spec**: [specs/033-idempotent-rebuild/spec-delta-state-storage.md](specs/033-idempotent-rebuild/spec-delta-state-storage.md)

**Parent Plan**: [plan.md](./plan.md) (original 033 implementation - 80% complete)

**Input**: Delta specification addressing gaps in laptop-based rebuild execution

## Summary

Complete the idempotent rebuild orchestrator by migrating Terraform state and Ansible inventory to NAS-backed storage, refactoring services phase for laptop-based execution, and adding automatic mount remediation. This enables full end-to-end rebuilds from developer laptops without PVE-local repo dependencies while maintaining zero regression for existing GH Actions workflows.

**Delta Scope**: 16 tasks (D-001 to D-016) addressing state storage, laptop-based services deployment, mount auto-remediation, and restore documentation updates.

> **Naming note**: This design doc references `static` as an environment name.
> During implementation, `static` was renamed to `prod` — the NAS directories are
> `infra_state/lab/` and `infra_state/prod/`, and the code accepts `lab|prod`.

## Technical Context

**Language/Version**: Bash (rebuild orchestrator), Python 3.x (inventory generation), Terraform 1.5.7+, Ansible 2.x
**Primary Dependencies**:
- Existing: telmate/proxmox (Terraform provider), ansible.posix.mount (NFS mounts)
- New: NAS-backed state storage, environment-aware path resolution

**Storage Architecture**:
- **Before**: State at `/var/lib/homelab-proxmox/state/services/<service>/terraform.tfstate` (PVE filesystem, inaccessible from laptop)
- **After**: State at `/mnt/nas/homelab_ci/infra_state/<env>/<service>/terraform.tfstate` (NAS NFS, accessible from PVE + laptop)
- **Laptop Mount**: `/Volumes/nas/homelab_ci` (autofs, nfsvers=3, resvport)
- **PVE Mount**: `/mnt/nas/homelab_ci` (ansible.posix.mount, already deployed)

**Testing**: Incremental validation at each phase, GH Actions regression testing, laptop end-to-end rebuild

**Target Platform**: macOS laptop (primary) + Linux PVE host (remote target) + GH Actions runner (CI/CD)

**Project Type**: Infrastructure automation enhancement (delta to feature 033)

**Performance Goals**: NFS state access <500ms per operation (acceptable for <5 services)

**Constraints**:
- Zero regression for 9+ GH Actions workflows
- Environment isolation (lab ≠ static/prod state)
- Backward compatibility via symlinks (30-day transition)
- tfvars remain on PVE filesystem (secrets policy)

**Scale/Scope**:
- Services: 6 (immich, monitoring, reverse_proxy, homeassistant, jellyfin, adguard)
- Environments: 2 (lab, static/prod)
- State files: ~12 total (<2MB combined)

## Constitution Check

*GATE: Delta changes must not violate existing constitution compliance.*

- **Spec-Driven Workflow**: PASS (delta spec at specs/033-idempotent-rebuild/spec-delta-state-storage.md)
- **Secrets Policy**: PASS (tfvars remain on PVE, state files contain no credentials)
- **Separation of Concerns**: PASS (Terraform for resources, Ansible for config, state storage is infrastructure)
- **Provider Strategy**: PASS (no new providers, telmate/proxmox unchanged)
- **State Management**: ENHANCED (moving from PVE filesystem to NAS improves DR and multi-client access)
- **Storage Baseline**: PASS (leverages existing homelab_ci NFS share)

**Gate Result**: PASS

## Project Structure

### Modified Files

```text
scripts/lab/
├── pve-service-deploy                  # Update STATE_PATH_DEFAULT_ROOT (line 34)
├── guardrails.sh                       # Update STATE_ROOT (line 14)
└── lib/
    ├── rebuild.sh                      # Refactor services & mounts phases
    ├── snapshot.sh                     # Update state_root parameter (line 137)
    └── state.sh (NEW)                  # State path resolution helpers

ansible/
├── group_vars/proxmox_hosts/vars.yml   # Add state_root_path variable
└── roles/
    ├── proxmox_backup/
    │   └── templates/
    │       └── proxmox-config-backup.sh.j2  # Update IaC collection (line 231+)
    └── proxmox_state_symlinks/ (NEW)
        ├── tasks/main.yml              # Create/remove symlinks
        └── README.md                   # Migration instructions

docs/
├── operations/
│   └── rebuild-orchestrator.md         # Add state architecture section
└── runbooks/
    └── laptop-nfs-setup.md (NEW)       # macOS autofs configuration

specs/033-idempotent-rebuild/
├── quickstart.md                       # Update with NFS mount prerequisites
└── migration-checklist.md (NEW)       # Phase 1-4 execution steps
```

### Directory Structure (NAS)

```text
/mnt/nas/homelab_ci/infra_state/        # Created by Phase 1 (Ansible task)
├── lab/
│   ├── immich/
│   │   └── terraform.tfstate
│   ├── monitoring/
│   │   └── terraform.tfstate
│   ├── reverse_proxy/
│   │   └── terraform.tfstate
│   └── ansible/
│       └── inventories/
│           └── generated/
│               └── hosts.yml
└── static/                             # Production environment
    ├── immich/
    │   └── terraform.tfstate
    ├── monitoring/
    │   └── terraform.tfstate
    └── ansible/
        └── inventories/
            └── generated/
                └── hosts.yml
```

## Complexity Tracking

**Justification for Increased Scope**:
- Delta adds 3 new functional areas after original 033 foundation complete
- 80% code reuse (modify existing functions, not rewrite)
- Migration strategy reduces risk (symlinks preserve legacy behavior)
- Testability at each phase enables rapid validation/rollback

**Complexity Metrics**:
- Modified functions: 8 (state path resolution, services phase, mount phase, backup collection)
- New files: 5 (state.sh, laptop docs, migration checklist, Ansible role, tests)
- Lines of code estimate: ~400 new, ~200 modified
- Test scenarios: 15 (per success criteria SC-005 to SC-010)
- Total tasks: 16 (D-001 to D-016)

## Phase 0: Setup & Validation

**Purpose**: Prepare infrastructure and validate prerequisites before code changes

### Task D-001: Create NAS State Directory Structure

**File**: Ansible task or manual script
**Purpose**: Create `/mnt/nas/homelab_ci/infra_state/<env>/<service>/` directories

**Implementation**:
```yaml
# ansible/roles/proxmox_state_dirs/tasks/main.yml
- name: Ensure homelab_ci NFS mount exists
  ansible.builtin.stat:
    path: /mnt/nas/homelab_ci
  register: nas_mount
  failed_when: not nas_mount.stat.exists or not nas_mount.stat.isdir

- name: Create infra_state root
  ansible.builtin.file:
    path: /mnt/nas/homelab_ci/infra_state
    state: directory
    mode: '0755'
    owner: root
    group: root

- name: Create environment directories
  ansible.builtin.file:
    path: "/mnt/nas/homelab_ci/infra_state/{{ item }}"
    state: directory
    mode: '0755'
  loop:
    - lab
    - static

- name: Create service state directories
  ansible.builtin.file:
    path: "/mnt/nas/homelab_ci/infra_state/{{ item.env }}/{{ item.service }}"
    state: directory
    mode: '0755'
  loop:
    - { env: 'lab', service: 'immich' }
    - { env: 'lab', service: 'monitoring' }
    - { env: 'lab', service: 'reverse_proxy' }
    - { env: 'lab', service: 'homeassistant' }
    - { env: 'lab', service: 'jellyfin' }
    - { env: 'lab', service: 'adguard' }
    - { env: 'static', service: 'immich' }
    - { env: 'static', service: 'monitoring' }
    - { env: 'static', service: 'reverse_proxy' }

- name: Create Ansible inventory directories
  ansible.builtin.file:
    path: "/mnt/nas/homelab_ci/infra_state/{{ item }}/ansible/inventories/generated"
    state: directory
    mode: '0755'
  loop:
    - lab
    - static
```

**Acceptance Test**:
```bash
# Run on PVE
ssh pve "ls -ld /mnt/nas/homelab_ci/infra_state/{lab,static}/{immich,monitoring}/terraform.tfstate 2>/dev/null | wc -l"
# Expected: 6 (3 services × 2 envs, directories exist but state files don't yet)

# Verify permissions
ssh pve "stat -c '%a %U' /mnt/nas/homelab_ci/infra_state/lab/immich"
# Expected: 755 root
```

### Task D-002: Document Laptop NFS Mount Setup

**File**: `docs/runbooks/laptop-nfs-setup.md` (new)
**Purpose**: Provide macOS autofs configuration for `/Volumes/nas/homelab_ci`

**Content** (reference existing DR drill docs):
```markdown
# Laptop NFS Mount Setup for Rebuild Orchestrator

## Prerequisites

- macOS with sudo access
- Network connectivity to NAS (192.168.1.109)
- NFS client enabled (default on macOS)

## Configuration Steps

### 1. Create autofs map

Edit `/etc/auto_nfs` (create if doesn't exist):

```bash
sudo tee /etc/auto_nfs <<'EOF'
/Volumes/nas/homelab_ci  -fstype=nfs,rw,nfsvers=3,resvport  192.168.1.109:/volume1/homelab_ci
EOF
```

### 2. Register map in auto_master

Edit `/etc/auto_master`, add line:

```
/-    auto_nfs          -nobrowse
```

### 3. Reload automount

```bash
sudo automount -vc
```

### 4. Verify mount

```bash
ls -la /Volumes/nas/homelab_ci
# Should show NAS contents without explicit mount command
```

## Troubleshooting

**Mount not appearing**: Check firewall allows NFS (port 2049)
**Permission denied**: Verify NAS export allows your laptop IP
**Stale mount**: `sudo umount -f /Volumes/nas/homelab_ci && sudo automount -vc`
```

**Acceptance Test**:
```bash
# On macOS laptop
ls /Volumes/nas/homelab_ci/infra_state/
# Expected: Directories visible (lab, static)
```

### Task D-003: Validate Existing State Files

**Purpose**: Document current state locations and sizes for migration

**Script**:
```bash
#!/usr/bin/env bash
# scripts/lab/validate-existing-state.sh

echo "Existing State Inventory"
echo "========================"
echo ""

for env in lab static; do
  echo "Environment: $env"
  for svc in immich monitoring reverse_proxy homeassistant jellyfin adguard; do
    old_path="/var/lib/homelab-proxmox/state/services/${svc}/terraform.tfstate"
    if [[ -f "$old_path" ]]; then
      size=$(stat -c '%s' "$old_path" 2>/dev/null || stat -f '%z' "$old_path")
      mtime=$(stat -c '%y' "$old_path" 2>/dev/null || stat -f '%Sm' "$old_path")
      echo "  ✓ ${svc}: ${size} bytes, modified ${mtime}"
    else
      echo "  ✗ ${svc}: NOT FOUND"
    fi
  done
  echo ""
done
```

**Acceptance Test**: Review output, confirm which services have existing state to migrate

---

## Phase 1: State Path Abstraction (Additive, Feature-Gated)

**Purpose**: Add NAS state support without breaking existing behavior

### Task D-004: Create State Path Resolution Library

**File**: `scripts/lab/lib/state.sh` (new)
**Purpose**: Centralize environment-aware state path logic

**Implementation**:
```bash
#!/usr/bin/env bash
# scripts/lab/lib/state.sh
# State path resolution for NAS-backed storage

# Resolve state root based on platform and environment
resolve_state_root() {
  local env="${ENVIRONMENT:?ENVIRONMENT must be set}"

  # Validate environment
  case "$env" in
    lab|static) ;;
    *)
      echo "ERROR: Unknown environment '$env'. Must be 'lab' or 'static'." >&2
      return 1
      ;;
  esac

  # Platform-specific NAS mount points
  local nas_base
  if [[ "$(uname)" == "Darwin" ]]; then
    nas_base="/Volumes/nas/homelab_ci"
  else
    nas_base="/mnt/nas/homelab_ci"
  fi

  # Check if NAS-backed state enabled
  if [[ "${USE_NAS_STATE:-}" == "true" ]]; then
    local state_root="${nas_base}/infra_state/${env}"

    # Verify NAS mount accessible
    if [[ ! -d "$nas_base" ]]; then
      echo "ERROR: NAS mount not found at $nas_base" >&2
      echo "  On PVE: Ensure /mnt/nas/homelab_ci mounted (ansible/roles/proxmox_mounts)" >&2
      echo "  On macOS: Run setup from docs/runbooks/laptop-nfs-setup.md" >&2
      return 1
    fi

    # Verify state root exists
    if [[ ! -d "$state_root" ]]; then
      echo "ERROR: State root not found at $state_root" >&2
      echo "  Run: ansible-playbook ansible/playbooks/setup_nas_state_dirs.yml" >&2
      return 1
    fi

    echo "$state_root"
  else
    # Legacy path (existing behavior)
    echo "/var/lib/homelab-proxmox/state/services"
  fi
}

# Get state file path for a specific service
get_service_state_path() {
  local service="${1:?Service name required}"
  local state_root

  state_root="$(resolve_state_root)" || return 1

  if [[ "${USE_NAS_STATE:-}" == "true" ]]; then
    # NAS: <root>/<environment>/<service>/terraform.tfstate
    echo "${state_root}/${service}/terraform.tfstate"
  else
    # Legacy: <root>/<service>/terraform.tfstate
    echo "${state_root}/${service}/terraform.tfstate"
  fi
}

# Get Ansible inventory path for environment
get_inventory_path() {
  local env="${ENVIRONMENT:?ENVIRONMENT must be set}"
  local state_root

  state_root="$(resolve_state_root)" || return 1

  if [[ "${USE_NAS_STATE:-}" == "true" ]]; then
    # NAS: <root>/ansible/inventories/generated/hosts.yml
    echo "${state_root}/ansible/inventories/generated/hosts.yml"
  else
    # Legacy: Repo-local generated inventory
    echo "${REPO_ROOT}/ansible/inventories/generated/hosts.yml"
  fi
}

# Verify state path accessible (fail-fast)
verify_state_access() {
  local state_root
  state_root="$(resolve_state_root)" || return 1

  # Test write access
  local test_file="${state_root}/.state-access-test-$$"
  if ! touch "$test_file" 2>/dev/null; then
    echo "ERROR: Cannot write to state root: $state_root" >&2
    echo "  Check NFS mount permissions" >&2
    return 1
  fi
  rm -f "$test_file"

  return 0
}
```

**Acceptance Test**:
```bash
# Test on PVE (legacy mode)
ENVIRONMENT=lab bash -c 'source scripts/lab/lib/state.sh && resolve_state_root'
# Expected: /var/lib/homelab-proxmox/state/services

# Test on PVE (NAS mode)
ENVIRONMENT=lab USE_NAS_STATE=true bash -c 'source scripts/lab/lib/state.sh && resolve_state_root'
# Expected: /mnt/nas/homelab_ci/infra_state/lab

# Test on macOS (NAS mode, requires mount)
ENVIRONMENT=lab USE_NAS_STATE=true bash -c 'source scripts/lab/lib/state.sh && resolve_state_root'
# Expected: /Volumes/nas/homelab_ci/infra_state/lab

# Test get_service_state_path
ENVIRONMENT=lab USE_NAS_STATE=true bash -c 'source scripts/lab/lib/state.sh && get_service_state_path immich'
# Expected: /mnt/nas/homelab_ci/infra_state/lab/immich/terraform.tfstate (or /Volumes on macOS)

# Test environment validation
ENVIRONMENT=invalid USE_NAS_STATE=true bash -c 'source scripts/lab/lib/state.sh && resolve_state_root'; echo "Exit: $?"
# Expected: ERROR message, Exit: 1
```

### Task D-005: Update pve-service-deploy to Use State Library

**File**: `scripts/lab/pve-service-deploy` (modify)
**Lines**: 34 (constantimport), 439-459 (ensure_state_path function)

**Changes**:
1. Source new state library
2. Update STATE_PATH_DEFAULT_ROOT to use resolve_state_root
3. Modify ensure_state_path to support NAS paths

**Implementation**:
```bash
# At top of file (after other lib/ imports)
# shellcheck source=lib/state.sh
source "${LIB_DIR}/state.sh"

# Replace constant (line 34)
# OLD:
# STATE_PATH_DEFAULT_ROOT="/var/lib/homelab-proxmox/state/services"

# NEW:
# State root is resolved dynamically via lib/state.sh (respects USE_NAS_STATE and ENVIRONMENT)
# Legacy default preserved when USE_NAS_STATE not set
STATE_PATH_DEFAULT_ROOT="${STATE_PATH_DEFAULT_ROOT:-}"

# Update ensure_state_path function (lines 439-459)
ensure_state_path() {
    local service="${1:?ensure_state_path requires a service name}"

    # Use new state library if available
    if command -v get_service_state_path >/dev/null 2>&1; then
        local state_path
        state_path="$(get_service_state_path "$service")" || return 1

        mkdir -p "$(dirname "$state_path")"

        # Safety: No automatic state seeding (explicitly opt-in as before)
        if [[ "${SEED_STATE_FROM_REPO:-}" == "1" ]]; then
            if [[ "${ENVIRONMENT:-}" != "prod" ]]; then
                die "Refusing to seed state from repo for non-prod environment"
            fi
            if [[ ! -f "${state_path}" && -f "${REPO_ROOT}/terraform/terraform.tfstate" ]]; then
                cp "${REPO_ROOT}/terraform/terraform.tfstate" "${state_path}"
            fi
        fi

        echo "${state_path}"
    else
        # Fallback to legacy behavior
        local dir="${STATE_PATH_DEFAULT_ROOT}/${service}"
        local state_path="${dir}/terraform.tfstate"
        mkdir -p "${dir}"
        echo "${state_path}"
    fi
}
```

**Acceptance Test**:
```bash
# Test legacy mode (backward compat)
unset USE_NAS_STATE
ENVIRONMENT=lab scripts/lab/pve-service-deploy plan --environment lab --service immich --dry-run
# Expected: Uses /var/lib/homelab-proxmox/state/services/immich/terraform.tfstate

# Test NAS mode
USE_NAS_STATE=true ENVIRONMENT=lab scripts/lab/pve-service-deploy plan --environment lab --service immich --dry-run
# Expected: Uses /mnt/nas/homelab_ci/infra_state/lab/immich/terraform.tfstate
```

### Task D-006: Update Supporting Scripts

**Files**:
- `scripts/lab/lib/snapshot.sh` (line 137)
- `scripts/lab/guardrails.sh` (line 14)

**Changes**:

**snapshot.sh**:
```bash
# Line 137: Update state_root parameter default
write_lab_snapshot() {
    local output_file="${1:?write_lab_snapshot requires output_file}"
    local environment="${2:?write_lab_snapshot requires environment}"
    local state_root

    # Use state library if available
    if command -v resolve_state_root >/dev/null 2>&1; then
        state_root="$(resolve_state_root)" || return 1
    else
        state_root="${3:-/var/lib/homelab-proxmox/state/services}"
    fi

    # ... rest of function unchanged
}
```

**guardrails.sh**:
```bash
# Line 14: Update STATE_ROOT
# Source state library
LIB_DIR="${SCRIPT_DIR}/lib"
source "${LIB_DIR}/state.sh"

# OLD:
# STATE_ROOT="/var/lib/homelab-proxmox/state"

# NEW:
if [[ "${USE_NAS_STATE:-}" == "true" ]]; then
    STATE_ROOT="$(resolve_state_root 2>/dev/null || echo '/var/lib/homelab-proxmox/state')"
else
    STATE_ROOT="/var/lib/homelab-proxmox/state"
fi
```

**Acceptance Test**: Run existing scripts, verify no behavioral change when USE_NAS_STATE unset

---

## Phase 2: Backward Compatibility (Symlinks)

**Purpose**: Enable transparent NAS state access for GH Actions workflows

### Task D-007: Create Ansible Role for State Symlinks

**File**: `ansible/roles/proxmox_state_symlinks/tasks/main.yml` (new)

**Implementation**:
```yaml
---
- name: Check if legacy state directory exists
  ansible.builtin.stat:
    path: /var/lib/homelab-proxmox/state/services
  register: legacy_state

- name: Create symlinks for backward compatibility
  when: legacy_state.stat.exists
  block:
    - name: Get list of services with state files
      ansible.builtin.find:
        paths: /var/lib/homelab-proxmox/state/services
        file_type: directory
        recurse: no
      register: service_dirs

    - name: Create symlinks per service (lab environment)
      ansible.builtin.file:
        src: "/mnt/nas/homelab_ci/infra_state/lab/{{ item.path | basename }}"
        dest: "{{ item.path }}"
        state: link
        force: yes
      loop: "{{ service_dirs.files }}"
      loop_control:
        label: "{{ item.path | basename }}"
      when:
        - proxmox_state_symlinks_enabled | default(false)
        - item.path | basename in proxmox_state_services | default([])

- name: Document symlink status
  ansible.builtin.debug:
    msg: |
      State symlinks status:
      - Enabled: {{ proxmox_state_symlinks_enabled | default(false) }}
      - Services: {{ proxmox_state_services | default([]) | join(', ') }}
      - Legacy path: /var/lib/homelab-proxmox/state/services/<service>
      - Target: /mnt/nas/homelab_ci/infra_state/lab/<service>
```

**Variables** (`ansible/group_vars/proxmox_hosts/vars.yml`):
```yaml
# State symlinks for backward compatibility
# Set to true after NAS state directories populated
proxmox_state_symlinks_enabled: false

# Services to symlink (prevents symlinking inactive services)
proxmox_state_services:
  - immich
  - monitoring
  - reverse_proxy
  - homeassistant
  - jellyfin
  - adguard
```

**Acceptance Test**:
```bash
# Deploy symlinks
ansible-playbook -i ansible/inventories/static/hosts.yml ansible/playbooks/proxmox_state_symlinks.yml -e proxmox_state_symlinks_enabled=true

# Verify on PVE
ssh pve "ls -l /var/lib/homelab-proxmox/state/services/immich"
# Expected: lrwxrwxrwx ... /var/lib/homelab-proxmox/state/services/immich -> /mnt/nas/homelab_ci/infra_state/lab/immich

# Test legacy path access
ssh pve "cat /var/lib/homelab-proxmox/state/services/immich/terraform.tfstate | jq -r .version"
# Expected: State file readable via symlink
```

### Task D-008: One-Time State Migration

**File**: `scripts/lab/migrate-state-to-nas.sh` (new, manual execution)

**Purpose**: Copy existing state files from PVE filesystem to NAS

**Implementation**:
```bash
#!/usr/bin/env bash
set -euo pipefail

ENVIRONMENT="${ENVIRONMENT:-lab}"
DRY_RUN="${DRY_RUN:-true}"

echo "State Migration to NAS"
echo "======================"
echo "Environment: $ENVIRONMENT"
echo "Dry Run: $DRY_RUN"
echo ""

LEGACY_ROOT="/var/lib/homelab-proxmox/state/services"
NAS_ROOT="/mnt/nas/homelab_ci/infra_state/${ENVIRONMENT}"

if [[ ! -d "$NAS_ROOT" ]]; then
  echo "ERROR: NAS state root not found: $NAS_ROOT"
  echo "Run: ansible-playbook ansible/playbooks/setup_nas_state_dirs.yml"
  exit 1
fi

for service_dir in "${LEGACY_ROOT}"/*; do
  [[ -d "$service_dir" ]] || continue

  service="$(basename "$service_dir")"
  legacy_state="${service_dir}/terraform.tfstate"
  nas_state="${NAS_ROOT}/${service}/terraform.tfstate"

  if [[ ! -f "$legacy_state" ]]; then
    echo "⊘ ${service}: No state file to migrate"
    continue
  fi

  if [[ -f "$nas_state" ]]; then
    echo "⚠ ${service}: NAS state exists, comparing..."
    if diff "$legacy_state" "$nas_state" >/dev/null 2>&1; then
      echo "  ✓ Identical, skipping"
    else
      echo "  ✗ DIFFERS! Manual review required"
      echo "    Legacy: $legacy_state"
      echo "    NAS: $nas_state"
    fi
    continue
  fi

  size=$(stat -c '%s' "$legacy_state" 2>/dev/null || stat -f '%z' "$legacy_state")

  if [[ "$DRY_RUN" == "true" ]]; then
    echo "➜ ${service}: Would copy ${size} bytes"
    echo "    From: $legacy_state"
    echo "    To: $nas_state"
  else
    echo "➜ ${service}: Copying ${size} bytes..."
    mkdir -p "$(dirname "$nas_state")"
    cp -a "$legacy_state" "$nas_state"
    echo "  ✓ Complete"
  fi
done

echo ""
if [[ "$DRY_RUN" == "true" ]]; then
  echo "Dry run complete. To execute migration:"
  echo "  DRY_RUN=false ENVIRONMENT=${ENVIRONMENT} $0"
else
  echo "Migration complete!"
  echo "Next steps:"
  echo "  1. Verify: ls -l ${NAS_ROOT}/*/terraform.tfstate"
  echo "  2. Test: USE_NAS_STATE=true task rebuild:plan -- --phase mounts"
  echo "  3. Deploy symlinks: ansible-playbook -e proxmox_state_symlinks_enabled=true ..."
fi
```

**Acceptance Test**:
```bash
# Dry run
DRY_RUN=true ENVIRONMENT=lab bash scripts/lab/migrate-state-to-nas.sh
# Expected: Lists services and sizes, no actual copy

# Execute migration
DRY_RUN=false ENVIRONMENT=lab bash scripts/lab/migrate-state-to-nas.sh

# Verify
ls -lh /mnt/nas/homelab_ci/infra_state/lab/*/terraform.tfstate
# Expected: State files present, same size as legacy location
```

---

## Phase 3: Services Phase Refactor (Laptop-First Execution)

**Purpose**: Enable Terraform execution from laptop via PVE API

### Task D-009: Refactor rebuild_phase_services()

**File**: `scripts/lab/lib/rebuild.sh` (lines 982-1040)

**Current Implementation** (SSH delegation):
```bash
rebuild_phase_services() {
    # OLD: SSH to PVE and run pve-service-deploy there
    host_exec "cd ${REMOTE_REPO_ROOT} && scripts/lab/pve-service-deploy ..."
}
```

**New Implementation** (laptop-based):
```bash
rebuild_phase_services() {
    local evidence_dir="${ARTIFACT_DIR}/reports/services"
    mkdir -p "$evidence_dir"

    # Load allowlist
    local allowlist_path="${REBUILD_SERVICE_ALLOWLIST_PATH:-${REPO_ROOT}/scripts/lab/service-scope-allowlist.json}"
    if [[ ! -f "$allowlist_path" ]]; then
        record_check "SRV-001" "Service allowlist present" "high" "PASS" "FAIL" "Allowlist missing" "reports/services"
        return 1
    fi

    # Source state library
    source "${REPO_ROOT}/scripts/lab/lib/state.sh"

    # Enable NAS state for laptop execution
    export USE_NAS_STATE=true
    export ENVIRONMENT="${REBUILD_ENVIRONMENT}"

    # Verify state access before starting
    if ! verify_state_access; then
        record_check "SRV-002" "State storage accessible" "blocker" "PASS" "FAIL" "Cannot access NAS state" "reports/services"
        return 1
    fi

    record_check "SRV-002" "State storage accessible" "low" "PASS" "PASS" "NAS state verified" "reports/services"

    # Iterate services
    local -a services
    mapfile -t services < <(jq -r 'keys[]' "$allowlist_path")
    local failed=0
    local idx=0

    for service in "${services[@]}"; do
        idx=$((idx + 1))
        local check_id="SRV-$(printf '%03d' "$idx")"
        local log_file="${evidence_dir}/${service}.log"

        local tf_dir="${REPO_ROOT}/terraform/services/${service}"
        if [[ ! -d "$tf_dir" ]]; then
            record_check "$check_id" "Service ${service} directory" "high" "PASS" "FAIL" "Terraform dir missing: $tf_dir" "reports/services/${service}.log"
            failed=1
            continue
        fi

        # Get state file path
        local state_file
        state_file="$(get_service_state_path "$service")" || {
            record_check "$check_id" "Service ${service} state path" "high" "PASS" "FAIL" "State path resolution failed" "reports/services/${service}.log"
            failed=1
            continue
        }

        mkdir -p "$(dirname "$state_file")"

        # Execute Terraform from laptop
        log_info "Processing service: ${service} (mode: ${REBUILD_MODE})"

        (
            cd "$tf_dir"

            # Initialize
            if ! terraform init -input=false -no-color >> "$log_file" 2>&1; then
                echo "Terraform init failed for $service" >> "$log_file"
                exit 1
            fi

            # Plan or Apply
            if [[ "${REBUILD_MODE}" == "plan" ]]; then
                terraform plan -state="$state_file" -input=false -no-color >> "$log_file" 2>&1
            else
                # Apply mode requires confirmation (already validated in preflight)
                terraform apply -state="$state_file" -input=false -auto-approve -no-color >> "$log_file" 2>&1
            fi
        )

        if [[ $? -eq 0 ]]; then
            record_check "$check_id" "Service rebuild (${service})" "high" "PASS" "PASS" "Service ${service} ${REBUILD_MODE} succeeded" "reports/services/${service}.log"
        else
            record_check "$check_id" "Service rebuild (${service})" "high" "PASS" "FAIL" "Service ${service} ${REBUILD_MODE} failed" "reports/services/${service}.log"
            failed=1
        fi
    done

    return $failed
}
```

**Key Changes**:
1. Removed `host_exec` SSH delegation
2. Added state library sourcing and `USE_NAS_STATE=true`
3. State path resolution via `get_service_state_path()`
4. Terraform runs in subshell from `terraform/services/<service>/`
5. Uses `-state=<path>` flag for explicit state file location

**Acceptance Test**:
```bash
# Test services phase from laptop (plan mode)
USE_NAS_STATE=true task rebuild:plan -- --phase services

# Expected output:
# [INFO] Processing service: immich (mode: plan)
# [INFO] Processing service: monitoring (mode: plan)
# <terraform plan output for each service>
# Check SRV-001: PASS (allowlist present)
# Check SRV-002: PASS (state accessible)
# Check SRV-003: PASS (immich plan succeeded)
# ...

# Verify state files updated
ls -lh /Volumes/nas/homelab_ci/infra_state/lab/*/terraform.tfstate
# Expected: Modification times recent
```

### Task D-010: Add Terraform Provider Variables

**Files**: Per-service terraform/services/<service>/providers.tf

**Issue**: Terraform variables (pm_api_url, pm_api_token_id, pm_api_token_secret) need values

**Options**:
1. **Environment variables** (recommended): Export TF_VAR_pm_api_url etc. in rebuild.sh
2. **tfvars file**: Pass `-var-file` with credentials (requires tfvars accessible from laptop)
3. **.terraformrc**: Provider credentials in Terraform CLI config

**Recommended Implementation** (environment variables):

```bash
# In rebuild_phase_services(), before Terraform execution:

# Load Proxmox credentials
export TF_VAR_pm_api_url="${PROXMOX_API_URL:-https://192.168.1.112:8006/api2/json}"
export TF_VAR_pm_api_token_id="${PROXMOX_API_TOKEN_ID:?PROXMOX_API_TOKEN_ID required}"
export TF_VAR_pm_api_token_secret="${PROXMOX_API_TOKEN_SECRET:?PROXMOX_API_TOKEN_SECRET required}"

# Note: These should be set by operator before running rebuild
# Example: export PROXMOX_API_TOKEN_ID="root@pam!rebuild"
#          export PROXMOX_API_TOKEN_SECRET="<from Bitwarden>"
```

**Acceptance Test**:
```bash
# Export credentials
export PROXMOX_API_TOKEN_ID="root@pam!rebuild"
export PROXMOX_API_TOKEN_SECRET="<secret>"

# Test single service
cd terraform/services/immich
terraform init
terraform plan -state=/Volumes/nas/homelab_ci/infra_state/lab/immich/terraform.tfstate

# Expected: Plan succeeds, connects to PVE API
```

---

## Phase 4: Mount Auto-Remediation

**Purpose**: Automatically fix missing NAS mounts during rebuild

### Task D-011: Update rebuild_phase_mounts()

**File**: `scripts/lab/lib/rebuild.sh` (lines 841-850)

**Current Implementation**:
```bash
rebuild_phase_mounts() {
    local failed=0
    if ! run_rebuild_host_mount_checks; then
        failed=1
    fi
    if ! run_rebuild_immich_bind_mount_checks; then
        failed=1
    fi
    return $failed
}
```

**New Implementation** (with remediation):
```bash
rebuild_phase_mounts() {
    local failed=0
    local remediation_attempted=0

    # First pass: validation
    log_info "Validating host NFS mounts..."
    if ! run_rebuild_host_mount_checks; then
        log_warn "Host mount checks failed - attempting automatic remediation"

        # Invoke Ansible mount role
        record_check "MNT-REMEDIATE-001" "Invoking mount remediation" "medium" "PASS" "INFO" "Running task ansible:mounts" "reports/mounts/remediation.log"

        local remediation_log="${ARTIFACT_DIR}/reports/mounts/remediation.log"
        mkdir -p "$(dirname "$remediation_log")"

        if (cd "${REPO_ROOT}" && task ansible:mounts) >> "$remediation_log" 2>&1; then
            log_info "Mount remediation completed - re-validating"
            remediation_attempted=1

            # Re-run validation
            if ! run_rebuild_host_mount_checks; then
                record_check "MNT-REMEDIATE-002" "Mount remediation verification" "blocker" "PASS" "FAIL" "Mounts still failing after remediation" "reports/mounts/remediation.log"
                failed=1
            else
                record_check "MNT-REMEDIATE-002" "Mount remediation verification" "medium" "PASS" "PASS" "Mounts fixed by remediation" "reports/mounts/remediation.log"
            fi
        else
            record_check "MNT-REMEDIATE-001" "Mount remediation" "blocker" "PASS" "FAIL" "Ansible mount role failed" "reports/mounts/remediation.log"
            failed=1
        fi
    fi

    # Immich bind mount checks (no auto-remediation, different failure mode)
    log_info "Validating Immich LXC bind mounts..."
    if ! run_rebuild_immich_bind_mount_checks; then
        if [[ $remediation_attempted -eq 1 ]]; then
            log_warn "Immich bind mount check failed after host mount remediation"
            log_warn "This may indicate LXC config issue (not auto-remediatable)"
        fi
        failed=1
    fi

    return $failed
}
```

**Key Changes**:
1. Attempt `task ansible:mounts` when host checks fail
2. Re-validate after remediation
3. Record remediation evidence
4. Distinguish between host mounts (remediatable) and LXC bind mounts (config issue)

**Acceptance Test**:
```bash
# Manually break a mount
ssh pve "umount /mnt/nas/homelab_immich"

# Run rebuild
task rebuild:plan -- --phase mounts

# Expected:
# [WARN] Host mount checks failed - attempting automatic remediation
# [INFO] Running task ansible:mounts
# <ansible output>
# [INFO] Mount remediation completed - re-validating
# [PASS] MNT-001: Host mount /mnt/nas/homelab_immich exists
# [PASS] MNT-REMEDIATE-002: Mount remediation verification

# Verify mount restored
ssh pve "mount | grep homelab_immich"
# Expected: Mount present
```

---

## Phase 5: Backup Integration

**Purpose**: Include NAS state files in nightly Proxmox backups

### Task D-012: Update Backup Script IaC Collection

**File**: `ansible/roles/proxmox_backup/templates/proxmox-config-backup.sh.j2` (lines 216-260)

**Current Implementation** (collect from REPO_PATH):
```bash
collect_iac_artifacts() {
  if [[ -z "${REPO_PATH:-}" ]]; then
    log_info "Skipping IaC artifacts (REPO_PATH not defined)"
    return 0
  fi

  # ... collects from ${REPO_PATH}/terraform/terraform.tfstate
}
```

**New Implementation** (collect from NAS + legacy):
```bash
collect_iac_artifacts() {
  log_info "Collecting IaC artifacts"

  local dest="${STAGING_DIR}/iac-artifacts"
  mkdir -p "$dest"

  # Collect NAS-backed state (primary source)
  local nas_state_root="/mnt/nas/homelab_ci/infra_state"
  if [[ -d "$nas_state_root" ]]; then
    log_info "Collecting NAS-backed state from: $nas_state_root"
    mkdir -p "$dest/nas-state"

    # Copy all environment state directories
    for env_dir in "${nas_state_root}"/*; do
      [[ -d "$env_dir" ]] || continue
      env_name="$(basename "$env_dir")"

      log_info "  Environment: $env_name"
      mkdir -p "$dest/nas-state/${env_name}"

      # Terraform state files per service
      for service_dir in "${env_dir}"/*; do
        [[ -d "$service_dir" ]] || continue
        service_name="$(basename "$service_dir")"

        if [[ -f "${service_dir}/terraform.tfstate" ]]; then
          mkdir -p "$dest/nas-state/${env_name}/${service_name}"
          cp -a "${service_dir}/terraform.tfstate" "$dest/nas-state/${env_name}/${service_name}/" 2>/dev/null || true
          cp -a "${service_dir}/terraform.tfstate.backup" "$dest/nas-state/${env_name}/${service_name}/" 2>/dev/null || true
        fi
      done

      # Ansible inventory
      local inventory_file="${env_dir}/ansible/inventories/generated/hosts.yml"
      if [[ -f "$inventory_file" ]]; then
        mkdir -p "$dest/nas-state/${env_name}/ansible/inventories/generated"
        cp -a "$inventory_file" "$dest/nas-state/${env_name}/ansible/inventories/generated/"
      fi
    done
  else
    log_warning "NAS state root not found: $nas_state_root (NFS mount issue?)"
  fi

  # Legacy REPO_PATH collection (transitional, can be removed after migration complete)
  if [[ -n "${REPO_PATH:-}" && -d "$REPO_PATH" ]]; then
    log_info "Collecting legacy repo artifacts from: $REPO_PATH"
    mkdir -p "$dest/legacy"

    # Terraform state (old location)
    if [[ -d "${REPO_PATH}/terraform" ]]; then
      mkdir -p "$dest/legacy/terraform"
      cp -a "${REPO_PATH}/terraform/terraform.tfstate" "$dest/legacy/terraform/" 2>/dev/null || true
      cp -a "${REPO_PATH}/terraform/terraform.tfstate.backup" "$dest/legacy/terraform/" 2>/dev/null || true
    fi

    # Ansible inventory (old location)
    if [[ -f "${REPO_PATH}/ansible/inventories/generated/hosts.yml" ]]; then
      mkdir -p "$dest/legacy/ansible/inventories/generated"
      cp -a "${REPO_PATH}/ansible/inventories/generated/hosts.yml" "$dest/legacy/ansible/inventories/generated/"
    fi
  fi

  log_info "IaC artifacts collected: $(du -sh "$dest" | cut -f1)"
}
```

**Key Changes**:
1. Primary collection from `/mnt/nas/homelab_ci/infra_state/`
2. Per-environment directory structure preserved
3. Both `.tfstate` and `.tfstate.backup` collected
4. Ansible inventory included
5. Legacy REPO_PATH collection retained during transition

**Acceptance Test**:
```bash
# Trigger backup manually
ssh pve "sudo /usr/local/bin/proxmox-config-backup.sh"

# Extract and verify
cd /mnt/nas-backup
latest=$(ls -t proxmox-backup-*.tar.zst.age | head -1)
age -d -i ~/.ssh/proxmox-backup-age.key "$latest" | tar -I zstd -tf - | grep iac-artifacts

# Expected output includes:
# iac-artifacts/nas-state/lab/immich/terraform.tfstate
# iac-artifacts/nas-state/lab/monitoring/terraform.tfstate
# iac-artifacts/nas-state/static/immich/terraform.tfstate
# iac-artifacts/nas-state/lab/ansible/inventories/generated/hosts.yml
# iac-artifacts/nas-state/static/ansible/inventories/generated/hosts.yml
```

---

## Phase 6: Documentation & Testing

### Task D-013: Update Documentation

**Files**:
1. `specs/033-idempotent-rebuild/quickstart.md` - Add NFS prerequisites
2. `docs/operations/rebuild-orchestrator.md` - Add state architecture section
3. `docs/runbooks/laptop-nfs-setup.md` - Created in D-002
4. `specs/033-idempotent-rebuild/migration-checklist.md` - New

**quickstart.md additions**:
```markdown
## Prerequisites

### Laptop Setup (macOS)

1. **Mount NAS share**: Follow [laptop-nfs-setup.md](../../docs/runbooks/laptop-nfs-setup.md)
   ```bash
   ls /Volumes/nas/homelab_ci/infra_state/
   # Should show: lab/ static/
   ```

2. **Export Proxmox credentials**:
   ```bash
   export PROXMOX_API_TOKEN_ID="root@pam!rebuild"
   export PROXMOX_API_TOKEN_SECRET="<from Bitwarden>"
   ```

3. **Enable NAS state**:
   ```bash
   export USE_NAS_STATE=true
   ```
```

**rebuild-orchestrator.md additions**:
```markdown
## State Architecture

### Storage Locations

**NAS-Backed State** (current):
- Path: `/mnt/nas/homelab_ci/infra_state/<environment>/<service>/terraform.tfstate`
- Environments: `lab`, `static` (production)
- Access:
  - PVE: via `/mnt/nas/homelab_ci` NFS mount
  - Laptop: via `/Volumes/nas/homelab_ci` autofs
  - GH Actions: via symlinks (transitional)

**Legacy State** (deprecated):
- Path: `/var/lib/homelab-proxmox/state/services/<service>/terraform.tfstate`
- Used by: GH Actions workflows (via symlinks during transition)
- Removal: After 30 days of stable operation

### Environment Separation

State files are isolated per environment to prevent cross-environment pollution:
- Lab: `infra_state/lab/<service>/`
- Production: `infra_state/static/<service>/`

The `ENVIRONMENT` variable must be set correctly to access the appropriate state.
```

### Task D-014: GH Actions Regression Testing

**Purpose**: Verify zero regression for existing workflows

**Test Plan**:

1. **Baseline** (before changes):
   ```bash
   # Trigger promote-lab workflow
   gh workflow run lxc-promote-lab.yml -f service=monitoring

   # Verify success
   gh run list --workflow=lxc-promote-lab.yml --limit 1
   ```

2. **After Phase 1** (NAS state support added, not enabled):
   ```bash
   # GH Actions should use legacy paths (no USE_NAS_STATE)
   gh workflow run lxc-promote-lab.yml -f service=monitoring
   # Expected: SUCCESS (no behavior change)
   ```

3. **After Phase 2** (symlinks deployed):
   ```bash
   # GH Actions uses legacy paths, but they're symlinks to NAS
   gh workflow run lxc-promote-lab.yml -f service=monitoring
   # Expected: SUCCESS (transparent NAS access via symlinks)

   # Verify state written to NAS
   ssh pve "ls -l /mnt/nas/homelab_ci/infra_state/lab/monitoring/terraform.tfstate"
   # Expected: File present, recent mtime
   ```

4. **After Phase 3** (services phase refactored):
   ```bash
   # Rebuild from laptop should work
   task rebuild:plan -- --phase services
   # Expected: SUCCESS

   # GH Actions still works (uses legacy paths + symlinks)
   gh workflow run lxc-promote-lab.yml -f service=monitoring
   # Expected: SUCCESS
   ```

**Acceptance Criteria**: All workflows pass at each phase, state files accessible from all contexts

### Task D-015: Create Migration Checklist

**File**: `specs/033-idempotent-rebuild/migration-checklist.md` (new)

**Requirements**: FR-031 (migration plan documentation)

**Content**:
```markdown
# State Migration Checklist

[...checklist content as shown in section below...]
```

**Acceptance Criteria**:
- Checklist covers all 6 phases sequentially
- Each phase has verification steps
- Rollback plan documented
- Dry-run procedures included for risky operations

### Task D-016: Update Backup Restore Procedures

**File**: `docs/operations/backups-proxmox-config-restore.md`

**Requirements**: FR-032 (restore documentation for NAS state)

**Purpose**: Document how to restore NAS-backed Terraform state and Ansible inventory from backup archives during disaster recovery.

**Changes Required**:

Add new section after existing restore procedures:
```markdown
## Restoring IaC State Files

### Prerequisites
- NAS mounted on restored PVE host: `/mnt/nas/homelab_ci`
- Backup archive extracted: `/root/restore-YYYYMMDD/`
- Verify state directories exist: `ls /mnt/nas/homelab_ci/infra_state/{lab,static}/`

### Restore Terraform State

**Lab Environment**:
```bash
# Sync all service state files
rsync -av --checksum \
  /root/restore-YYYYMMDD/iac-artifacts/terraform-state/lab/ \
  /mnt/nas/homelab_ci/infra_state/lab/

# Verify
ls -lh /mnt/nas/homelab_ci/infra_state/lab/*/terraform.tfstate
```

**Static (Production) Environment**:
```bash
# Sync static state separately
rsync -av --checksum \
  /root/restore-YYYYMMDD/iac-artifacts/terraform-state/static/ \
  /mnt/nas/homelab_ci/infra_state/static/

# Verify
ls -lh /mnt/nas/homelab_ci/infra_state/static/*/terraform.tfstate
```

### Restore Ansible Inventory

```bash
# Lab inventory
cp -v /root/restore-YYYYMMDD/iac-artifacts/ansible-inventory/lab-hosts.yml \
  /mnt/nas/homelab_ci/infra_state/lab/ansible/inventories/generated/hosts.yml

# Static inventory
cp -v /root/restore-YYYYMMDD/iac-artifacts/ansible-inventory/static-hosts.yml \
  /mnt/nas/homelab_ci/infra_state/static/ansible/inventories/generated/hosts.yml
```

### Validation

Verify state files are accessible and valid:
```bash
# Check file ownership and permissions
find /mnt/nas/homelab_ci/infra_state/ -type f -ls

# Validate Terraform state format
for env in lab static; do
  for service in immich monitoring; do
    terraform show -json \
      /mnt/nas/homelab_ci/infra_state/$env/$service/terraform.tfstate \
      > /dev/null && echo "$env/$service: OK"
  done
done
```
```

**Test Criteria**:
```bash
# Simulate restore scenario
mkdir -p /tmp/mock-restore/iac-artifacts/{terraform-state/lab/immich,ansible-inventory}
echo '{"version": 4}' > /tmp/mock-restore/iac-artifacts/terraform-state/lab/immich/terraform.tfstate

# Run restore commands (adapted for mock path)
rsync -av --checksum --dry-run \
  /tmp/mock-restore/iac-artifacts/terraform-state/lab/ \
  /tmp/test-nas/infra_state/lab/

# Expected: Shows what would be copied, no errors
```

**Acceptance Criteria**:
- Documentation includes restore procedures for both lab and static environments
- Commands use `/mnt/nas/homelab_ci/infra_state/` paths (not legacy PVE filesystem)
- Validation steps verify state file integrity
- Procedures note environment separation (lab vs static)

---

## Testing Strategy
# State Migration Checklist

## Phase 1: Add NAS State Support (Week 1)

- [ ] D-001: Create NAS directory structure via Ansible
- [ ] D-002: Document laptop NFS setup
- [ ] D-003: Validate existing state files
- [ ] D-004: Create state path library (lib/state.sh)
- [ ] D-005: Update pve-service-deploy
- [ ] D-006: Update supporting scripts (snapshot.sh, guardrails.sh)
- [ ] Test: Verify USE_NAS_STATE=false uses legacy paths
- [ ] Test: Verify USE_NAS_STATE=true uses NAS paths

## Phase 2: Backward Compatibility (Week 2)

- [ ] D-007: Create Ansible role for symlinks
- [ ] D-008: Execute one-time state migration
  - [ ] Dry run: `DRY_RUN=true bash scripts/lab/migrate-state-to-nas.sh`
  - [ ] Execute: `DRY_RUN=false bash scripts/lab/migrate-state-to-nas.sh`
  - [ ] Verify: Compare checksums of legacy vs NAS state files
- [ ] Deploy symlinks: `ansible-playbook -e proxmox_state_symlinks_enabled=true ...`
- [ ] Test: GH Actions promote-lab workflow (should use symlinks transparently)

## Phase 3: Services Phase Refactor (Week 3)

- [ ] D-009: Refactor rebuild_phase_services() in rebuild.sh
- [ ] D-010: Configure Terraform provider variables (export TF_VAR_*)
- [ ] D-011: Update rebuild_phase_mounts() with auto-remediation
- [ ] D-012: Update backup script IaC collection
- [ ] Test: Laptop rebuild with all phases
  ```bash
  export USE_NAS_STATE=true
  export PROXMOX_API_TOKEN_ID="..."
  export PROXMOX_API_TOKEN_SECRET="..."
  task rebuild:plan -- --backup-dir /path/to/backup
  ```
- [ ] Test: Mount auto-remediation (break mount, run rebuild, verify fix)

## Phase 4: Documentation & Cleanup (Week 4)

- [ ] D-013: Update all documentation
- [ ] D-014: GH Actions regression testing (all workflows pass)
- [ ] D-015: Migration checklist (this file)
- [ ] D-016: Update backup restore procedures
- [ ] Monitor: Watch GH Actions for 1 week for unexpected issues
- [ ] Final validation: Full laptop-based rebuild in lab environment

## Phase 5: Symlink Removal (Week 8+)

After 30 days of stable operation with NAS state:

- [ ] Update GH Actions workflows to use USE_NAS_STATE=true
- [ ] Remove symlinks via Ansible: `proxmox_state_symlinks_enabled: false`
- [ ] Archive legacy state directory: `mv /var/lib/homelab-proxmox/state /root/state-legacy-$(date +%Y%m%d)`
- [ ] Final test: All workflows use NAS state directly

## Rollback Plan

If critical issues discovered:

1. Disable NAS state: `unset USE_NAS_STATE` (falls back to legacy paths)
2. Symlinks preserve legacy path access (GH Actions unaffected)
3. Copy NAS state back to legacy location if needed:
   ```bash
   rsync -av /mnt/nas/homelab_ci/infra_state/lab/*/terraform.tfstate /var/lib/homelab-proxmox/state/services/
   ```
4. Investigate, fix, retry
```

---

## Testing Strategy

### Unit Tests (Per Task)

Each task includes acceptance tests (inline above). Summary:

- **D-001**: Directory structure created, permissions correct
- **D-004**: State path resolution works for PVE, macOS, legacy mode
- **D-005**: pve-service-deploy uses state library correctly
- **D-007**: Symlinks created, point to correct NAS paths
- **D-009**: Services phase runs Terraform from laptop
- **D-011**: Mount remediation fixes broken mounts
- **D-012**: Backup includes NAS state files
- **D-016**: Restore documentation includes NAS state procedures

### Integration Tests

**Test Scenario 1: Fresh Rebuild from Laptop**
```bash
# Prerequisites: NAS mounted, credentials exported, USE_NAS_STATE=true
ENVIRONMENT=lab task rebuild:plan -- --backup-dir /path/to/backup

# Expected:
# - Mounts phase: PASS (auto-remediation if needed)
# - Restore phase: PASS (LXC configs restored)
# - IaC phase: PASS (state read from NAS)
# - Services phase: PASS (Terraform runs from laptop, state written to NAS)
# - Verify phase: PASS (inventory updated, healthchecks pass)
```

**Test Scenario 2: GH Actions Workflow (Backward Compatibility)**
```bash
# Trigger via GitHub web UI or gh CLI
gh workflow run lxc-promote-lab.yml -f service=monitoring

# Expected:
# - Workflow succeeds
# - State written via symlinks to NAS
# - No error messages about missing paths
```

**Test Scenario 3: Cross-Platform State Access**
```bash
# From laptop: Create state
ENVIRONMENT=lab USE_NAS_STATE=true task rebuild:plan -- --phase services

# From PVE: Read state (via GH Actions or SSH)
ssh pve "cd /home/ci/homelab-proxmox && ENVIRONMENT=lab ./scripts/lab/pve-service-deploy plan --environment lab --service immich"

# Expected:
# - Both see identical state
# - Terraform detects existing resources (no recreate)
```

### Regression Tests

**Existing GH Actions Workflows** (must all pass):
- lxc-promote-lab.yml
- lxc-promote-prod.yml
- lxc-lifecycle.yml
- proxmox-apply.yml
- (6+ other workflows referencing /var/lib/homelab-proxmox paths)

**Test Matrix**:
| Scenario | Phase | USE_NAS_STATE | Expected Result |
|----------|-------|---------------|-----------------|
| GH Actions (pre-migration) | Any | unset | Legacy paths work |
| GH Actions (post-symlink) | Any | unset | Symlinks → NAS (transparent) |
| Laptop rebuild | All | true | NAS paths direct |
| PVE manual | Any | true | NAS paths direct |
| PVE manual | Any | unset | Legacy paths work |

### Performance Benchmarks

**Baseline** (PVE filesystem state):
```bash
time ssh pve "cd /home/ci/homelab-proxmox && terraform plan"
# Expected: ~10s for immich
```

**NAS-backed** (via NFS):
```bash
time USE_NAS_STATE=true terraform plan -state=/Volumes/nas/homelab_ci/infra_state/lab/immich/terraform.tfstate
# Target: <15s (acceptable 50% overhead for NFS)
```

If NFS performance inadequate:
- Check: `nfsstat -m` for mount options
- Optimize: Add `async,noatime` to mount opts
- Escalate: Consider NFS v4 or tune read-ahead cache

---

## Rollback Plan

### Immediate Rollback (If Critical Issue Found)

1. **Disable NAS state globally**:
   ```bash
   # On PVE: Edit shell profile
   echo "export USE_NAS_STATE=false" >> /etc/profile.d/nas-state-disable.sh

   # In GH Actions: Workflows fall back to legacy paths automatically (no USE_NAS_STATE set)
   ```

2. **Verify legacy paths accessible**:
   - Symlinks remain in place (backward compatible)
   - `/var/lib/homelab-proxmox/state/services/` still works

3. **Sync NAS state back to legacy** (if diverged):
   ```bash
   for env in lab static; do
     for svc in immich monitoring reverse_proxy; do
       nas="/mnt/nas/homelab_ci/infra_state/${env}/${svc}/terraform.tfstate"
       legacy="/var/lib/homelab-proxmox/state/services/${svc}/terraform.tfstate"
       if [[ -f "$nas" ]]; then
         cp -a "$nas" "$legacy"
       fi
     done
   done
   ```

4. **Test GH Actions workflow**: Confirm promote-lab succeeds with legacy state

5. **Investigation window**: Fix issue, add tests, prepare re-deployment

### Partial Rollback (Service-Specific)

If one service has issues with NAS state:

```bash
# Exclude from NAS state (edit lib/state.sh)
get_service_state_path() {
  local service="${1:?}"

  # Blocklist for services staying on legacy
  case "$service" in
    problematic-service)
      echo "/var/lib/homelab-proxmox/state/services/${service}/terraform.tfstate"
      return
      ;;
  esac

  # Normal NAS path resolution
  ...
}
```

### Full Rollback to Original State

If fundamental architecture issue discovered:

1. **Remove symlinks**: `ansible-playbook -e proxmox_state_symlinks_enabled=false ...`
2. **Restore legacy state**: From backup or NAS sync
3. **Revert code changes**: `git revert <commits>`
4. **Document lessons learned**: Add to spec-delta "Risks" section
5. **Re-plan**: Iterate on design before next attempt

---

## Success Criteria Validation

### SC-005: Laptop Completes All Phases

**Test**:
```bash
ENVIRONMENT=lab USE_NAS_STATE=true \
  PROXMOX_API_TOKEN_ID="..." PROXMOX_API_TOKEN_SECRET="..." \
  task rebuild:plan -- --backup-dir /root/restore-YYYYMMDD

# Check evidence
cat artifacts/rebuild-runs/rebuild-$(date +%Y%m%d)*/reports/rebuild-phase-summary.md
```

**Acceptance**: All phases marked "completed", zero "failed" status

### SC-006: State Persists Across Reboots

**Test**:
```bash
# Write state from laptop
ENVIRONMENT=lab USE_NAS_STATE=true task rebuild:plan -- --phase services

# Reboot PVE
ssh pve "sudo reboot"

# Wait for PVE online, verify state still accessible
ssh pve "ls -l /mnt/nas/homelab_ci/infra_state/lab/immich/terraform.tfstate"
```

**Acceptance**: State file accessible, unchanged after reboot

### SC-007: Zero GH Actions Regression

**Test**: Run all GH Actions workflows post-deployment

**Acceptance**: 100% success rate for:
- lxc-promote-lab.yml (at least 3 services)
- lxc-promote-prod.yml (at least 1 service)
- lxc-lifecycle.yml (plan + apply for 1 service)

### SC-008: Auto-Mount Remediation

**Test**:
```bash
# Break mount
ssh pve "sudo umount /mnt/nas/homelab_immich"

# Run rebuild
task rebuild:plan -- --phase mounts

# Verify fix
ssh pve "mount | grep homelab_immich"
```

**Acceptance**: Mount remediation check passes, mount present after rebuild

### SC-009: State in Backups

**Test**:
```bash
# Trigger backup
ssh pve "sudo /usr/local/bin/proxmox-config-backup.sh"

# Extract and verify
age -d -i key proxmox-backup-*.age | tar -I zstd -tf - | grep infra_state
```

**Acceptance**: At least 6 state files present (3 services × 2 envs minimum)

### SC-010: Cross-Environment Isolation

**Test**:
```bash
# Try to access static state with lab environment
ENVIRONMENT=lab USE_NAS_STATE=true bash -c '
  source scripts/lab/lib/state.sh
  get_service_state_path immich
'
# Expected: /mnt/nas/homelab_ci/infra_state/lab/immich/terraform.tfstate (lab, not static)

# Verify static state not accessible from lab context
ENVIRONMENT=lab USE_NAS_STATE=true bash -c '
  source scripts/lab/lib/state.sh
  state_root=$(resolve_state_root)
  ls -ld ${state_root}/../static/
'
# Expected: Directory exists but is isolated (not used by lab)
```

**Acceptance**: Environment variable strictly enforced, no cross-environment leaks

---

## Deliverables

### Code
- [ ] `scripts/lab/lib/state.sh` (new, ~150 lines)
- [ ] `scripts/lab/pve-service-deploy` (modified, ~20 lines changed)
- [ ] `scripts/lab/lib/rebuild.sh` (modified, ~100 lines changed)
- [ ] `scripts/lab/lib/snapshot.sh` (modified, ~10 lines)
- [ ] `scripts/lab/guardrails.sh` (modified, ~5 lines)
- [ ] `scripts/lab/migrate-state-to-nas.sh` (new, ~80 lines)
- [ ] `ansible/roles/proxmox_state_symlinks/` (new role)
- [ ] `ansible/roles/proxmox_state_dirs/` (new role)
- [ ] `ansible/roles/proxmox_backup/templates/proxmox-config-backup.sh.j2` (modified, ~50 lines)

### Documentation
- [ ] `docs/runbooks/laptop-nfs-setup.md` (new)
- [ ] `specs/033-idempotent-rebuild/quickstart.md` (updated)
- [ ] `docs/operations/rebuild-orchestrator.md` (state architecture section)
- [ ] `docs/operations/backups-proxmox-config-restore.md` (NAS state restore procedures)
- [ ] `specs/033-idempotent-rebuild/migration-checklist.md` (new)
- [ ] `specs/033-idempotent-rebuild/plan-delta-state-storage.md` (this file)

### Testing
- [ ] 16 unit test scripts (acceptance tests per task)
- [ ] 3 integration test scenarios
- [ ] 5 GH Actions regression tests
- [ ] Evidence artifacts for all test runs

---

## Timeline Estimate

| Phase | Duration | Dependencies |
|-------|----------|--------------|
| Phase 0: Setup | 1-2 days | None |
| Phase 1: State Library | 2-3 days | Phase 0 complete |
| Phase 2: Symlinks | 1-2 days | Phase 1 complete, state migrated |
| Phase 3: Services Refactor | 3-4 days | Phase 2 complete |
| Phase 4: Documentation | 1-2 days | Phase 3 complete |
| Testing & Validation | 2-3 days | All phases |
| **Total** | **10-16 days** | Sequential execution |

**Optional Parallelization**:
- D-002 (laptop docs) can happen anytime
- D-006 (supporting scripts) can parallel with D-005
- D-013 (documentation) can start during Phase 3

**Production Deployment**:
- Phase 1-2: Low risk, deploy immediately
- Phase 3: Medium risk, test in lab for 1 week before prod
- Phase 4: Documentation only, no deployment risk

---

## Next Steps

1. **Review this plan** with team/stakeholders
2. **Execute Task D-001** (create NAS directories)
3. **Execute Task D-002** (document laptop setup, test on your machine)
4. **Execute Task D-004** (state library), validate with unit tests
5. **Proceed sequentially** through remaining tasks
6. **Update migration checklist** as tasks complete
7. **Capture test evidence** in artifacts/
8. **Write post-mortem** documenting challenges and lessons

---

**Plan Author**: GitHub Copilot + Human Operator
**Date**: 2026-02-09
**Status**: Ready for Implementation
**Estimated Effort**: 10-16 developer-days
**Risk Level**: Medium (mitigated by phased approach + rollback plan)
