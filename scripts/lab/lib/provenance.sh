#!/usr/bin/env bash
# lib/provenance.sh - Provenance capture (git, versions, environment)

set -euo pipefail

# Capture controller environment (OS, bash, ansible versions)
capture_controller_info() {
    local os_info
    os_info="$(uname -s) $(uname -r)"
    
    local bash_version="${BASH_VERSION}"
    
    local ansible_version
    if command -v ansible &>/dev/null; then
        ansible_version="$(ansible --version | head -n1 | awk '{print $2}')"
    else
        ansible_version="not installed"
    fi
    
    cat <<EOF
{
  "os": "$os_info",
  "bash_version": "$bash_version",
  "ansible_version": "$ansible_version"
}
EOF
}

# Capture git status (commit, branch, dirty status)
capture_git_status() {
    local git_dir="${1:-.}"
    
    pushd "$git_dir" >/dev/null
    
    local git_commit
    if [[ -n "${GIT_SHA:-}" && "${GIT_SHA}" =~ ^[0-9a-fA-F]{7,64}$ ]]; then
        git_commit="${GIT_SHA}"
    else
        git_commit="$(git rev-parse HEAD 2>/dev/null || echo 'unknown')"
    fi
    
    local git_branch
    # Allow CI to override branch name as well (useful when git metadata is missing).
    if [[ -n "${GIT_REF_NAME:-}" ]]; then
        git_branch="${GIT_REF_NAME}"
    else
        git_branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'unknown')"
    fi
    
    local git_dirty="false"
    if ! git diff-index --quiet HEAD -- 2>/dev/null; then
        git_dirty="true"
    fi
    
    popd >/dev/null
    
    cat <<EOF
{
  "commit": "$git_commit",
  "branch": "$git_branch",
  "dirty": $git_dirty
}
EOF
}

# Emit git dirty warning if working tree is dirty
check_git_dirty() {
    local git_dir="${1:-.}"
    
    pushd "$git_dir" >/dev/null
    
    if ! git diff-index --quiet HEAD -- 2>/dev/null; then
        echo "⚠️  WARNING: Git working tree is dirty (uncommitted changes detected)" >&2
        echo "   This may affect reproducibility of results" >&2
        echo "" >&2
    fi
    
    popd >/dev/null
}

# Capture target environment (pveversion, kernel, distro via SSH)
# Usage: capture_target_info ssh_target
capture_target_info() {
    local ssh_target="$1"
    
    local pveversion
    
    local kernel
    
    local distro
        if is_local_proxmox; then
            pveversion="$(host_exec "pveversion 2>/dev/null | grep 'pve-manager' | awk '{print \$2}'" || echo 'unknown')"
            kernel="$(host_exec "uname -r" || echo 'unknown')"
            distro="$(host_exec "cat /etc/os-release 2>/dev/null | grep '^PRETTY_NAME=' | cut -d= -f2 | tr -d '\"'" || echo 'unknown')"
        else
            pveversion="$(ssh $SSH_OPTS "$ssh_target" "pveversion 2>/dev/null | grep 'pve-manager' | awk '{print \$2}'" || echo 'unknown')"
            kernel="$(ssh $SSH_OPTS "$ssh_target" "uname -r" || echo 'unknown')"
            distro="$(ssh $SSH_OPTS "$ssh_target" "cat /etc/os-release 2>/dev/null | grep '^PRETTY_NAME=' | cut -d= -f2 | tr -d '\"'" || echo 'unknown')"
        fi
    
    cat <<EOF
{
  "pveversion": "$pveversion",
  "kernel": "$kernel",
  "distro": "$distro"
}
EOF
}

# Generate complete provenance.json
# Usage: generate_provenance output_file profile_id ssh_target [param_key=value ...]
generate_provenance() {
    local output_file="$1"
    local profile_id="$2"
    local ssh_target="$3"
    shift 3
    
    # Capture components
    local controller_json
    controller_json="$(capture_controller_info)"
    
    local git_json
    git_json="$(capture_git_status)"
    
    local target_json
    target_json="$(capture_target_info "$ssh_target")"
    
    # Build parameters JSON from key=value pairs
    local params_json="{"
    local first=true
    for kv in "$@"; do
        if [[ "$kv" =~ ^([^=]+)=(.*)$ ]]; then
            local key="${BASH_REMATCH[1]}"
            local value="${BASH_REMATCH[2]}"
            if [ "$first" = true ]; then
                first=false
            else
                params_json+=","
            fi
            params_json+="\"$key\":\"$value\""
        fi
    done
    params_json+="}"
    
    # Write provenance file
    cat > "$output_file" <<EOF
{
  "provenance_schema_version": "1.0.0",
  "controller": $controller_json,
  "git": $git_json,
  "target": $target_json,
  "profile": "$profile_id",
  "parameters": $params_json
}
EOF
}
