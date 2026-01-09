# Research: Pipeline Promotion UX

**Branch**: `024-pipeline-promotion-ux`  
**Date**: 2026-01-09  
**Status**: Complete

This document captures research findings for the Pipeline Promotion UX feature, addressing all technical unknowns identified in Phase 0 of the implementation plan.

---

## R1: GitHub Actions Workflow Dispatch Choice Inputs

### Decision
**Use static hardcoded choice lists with runtime validation against the authoritative allowlist file.**

GitHub Actions workflow_dispatch inputs do not support dynamic choice generation from repository files. Choices must be hardcoded in the workflow YAML at the time of workflow definition.

### Rationale
1. **Limitation**: GitHub Actions does not support reading files at workflow dispatch time to populate choice inputs
2. **Validation approach**: Hardcode choices in workflow but add early validation step that verifies the input against `scripts/lab/service-scope-allowlist.json`
3. **Maintenance**: When services are added/removed, both the workflow YAML and allowlist JSON must be updated (acceptable tradeoff for improved UX)
4. **Benefit**: Operators see a bounded dropdown immediately in the GitHub UI rather than free-text input

### Alternatives Considered
1. **Dynamic choices via GitHub API**: Rejected because workflow_dispatch does not support this; would require separate UI layer
2. **Free-text input with early validation**: Rejected because it loses the UX improvement of bounded choices
3. **Generated workflow YAML via CI**: Rejected as too complex; adds generation step and complicates workflow maintenance

### Implementation Notes
- Hardcode service choices in workflow YAML: `["adguard", "homeassistant", "immich", "jellyfin", "monitoring", "reverse_proxy"]`
- Add validation step at start of each workflow job:
  ```bash
  jq -e --arg svc "$SERVICE" 'has($svc)' scripts/lab/service-scope-allowlist.json
  ```
- If allowlist and workflow choices drift, validation will fail safely (blocking invalid runs)
- Document in README/contribution guide that both files must be kept in sync

---

## R2: GitHub Environment Protection Rules

### Decision
**Use GitHub Environment named `prod` with required reviewers (1+ approvals) and no wait timer.**

GitHub Environments provide built-in approval gates that integrate seamlessly with workflow jobs via the `environment:` keyword.

### Rationale
1. **Native integration**: `environment: prod` on a job automatically pauses workflow until approval granted
2. **Audit trail**: GitHub logs all approvals with reviewer identity and timestamp
3. **Flexible configuration**: Admins can adjust required reviewers and rules without workflow changes
4. **Protection scope**: Environment protection applies only to jobs explicitly tagged with `environment: prod`

### Alternatives Considered
1. **Manual approval via issue comments**: Rejected because it's non-standard and requires custom parsing logic
2. **Third-party approval tools**: Rejected because GitHub native solution is simpler and more maintainable
3. **Wait timer only (no reviewer)**: Rejected because it doesn't provide meaningful approval control

### Implementation Notes
- Configure `prod` environment in repository settings → Environments → New environment
- Set required reviewers: 1 or more team members (recommend: 2 for production)
- No wait timer needed (approvers respond on-demand)
- Jobs requiring approval:
  - `apply_prod` in promote workflow
  - Any job with `environment: prod` keyword
- Approval notifications sent via GitHub email/UI
- In emergency, repository admins can bypass protection (audit log records this)

**Configuration steps**:
1. GitHub repo → Settings → Environments → New environment: `prod`
2. Add required reviewers (team or individuals)
3. Optionally enable deployment branches filter (e.g., only `main` or `024-*` branches)

---

## R3: Bash Templating for tfvars Provisioning

### Decision
**Use Bash heredoc with environment variable substitution, writing to temp file with secure permissions, then moving to final location.**

This approach balances simplicity, security, and auditability without adding external dependencies.

### Rationale
1. **Heredoc clarity**: Template structure visible in script; easy to review and maintain
2. **Variable substitution**: Bash natively expands `${VAR}` in heredocs; no external tool needed
3. **Secret safety**: Pass secrets via SSH stdin to avoid command-line exposure, then write to secure temp file
4. **Idempotency**: Check if existing file matches expected content (via hash comparison) before overwriting

### Alternatives Considered
1. **envsubst**: Rejected because it requires GNU gettext package (not always installed)
2. **jq with template**: Rejected because template would need to be JSON (less readable for HCL/tfvars)
3. **sed/awk replacement**: Rejected because heredoc is clearer and safer for multi-line templates

### Implementation Notes

**Provisioning script** (`scripts/lab/lib/tfvars.sh`):

```bash
provision_prod_tfvars() {
    local token_secret="$1"  # Passed from GitHub Secret
    local tfvars_path="${TFVARS_DIR}/prod.tfvars"
    local temp_tfvars
    temp_tfvars="$(mktemp -t prod.tfvars.XXXXXX)"
    
    # Secure temp file
    chmod 600 "${temp_tfvars}"
    
    # Render template with heredoc
    cat > "${temp_tfvars}" <<EOF
# Production Terraform variables (auto-generated)
# Generated at: $(date -Iseconds)

pm_api_url = "https://pve.lan:8006/api2/json"
pm_api_token_id = "terraform@pve!terraform-token"
pm_api_token_secret = "${token_secret}"
pm_tls_insecure = true
EOF
    
    # Create target directory if missing
    mkdir -p "$(dirname "${tfvars_path}")"
    
    # Move temp to final location
    mv "${temp_tfvars}" "${tfvars_path}"
    chmod 600 "${tfvars_path}"
    
    echo "Provisioned ${tfvars_path}"
}
```

**Secrets handling in workflow**:
```yaml
- name: Provision prod.tfvars
  env:
    PROXMOX_TOKEN_SECRET: ${{ secrets.PROXMOX_TOKEN_SECRET }}
  run: |
    ssh ci@pve 'bash -s' <<'SCRIPT'
      # Read secret from stdin (avoid command line exposure)
      read -r token_secret
      source /home/ci/homelab-proxmox/scripts/lab/lib/tfvars.sh
      provision_prod_tfvars "${token_secret}"
    SCRIPT
    # Pass secret via stdin
    echo "${PROXMOX_TOKEN_SECRET}"
```

---

## R4: tfvars Validation Rules

### Decision
**Validate token ID via regex match, validate secret via non-empty/non-placeholder checks, generate SHA256 hash of full file, and create redacted JSON proof for evidence.**

This ensures prod.tfvars is valid before Terraform runs while keeping secrets out of evidence.

### Rationale
1. **Token ID validation**: Simple string match (`terraform@pve!terraform-token`) catches misconfiguration
2. **Secret validation**: Check non-empty and reject known placeholders (`REPLACEME`, `<secret>`, etc.)
3. **Hash proof**: SHA256 of full file proves content integrity without revealing secrets
4. **Redacted evidence**: JSON includes token ID (non-secret) and boolean flags, but not secret value

### Alternatives Considered
1. **Hash of redacted file**: Rejected because it doesn't prove actual secret was present
2. **Terraform validate**: Rejected because validation would still fail if secret is wrong format
3. **No validation (fail at apply)**: Rejected because it wastes time and doesn't provide clear error

### Implementation Notes

**Validation script** (`scripts/lab/lib/tfvars.sh`):

```bash
validate_prod_tfvars() {
    local tfvars_path="${TFVARS_DIR}/prod.tfvars"
    local validation_status="pass"
    local errors=()
    
    # Check file exists
    if [[ ! -f "${tfvars_path}" ]]; then
        errors+=("File not found: ${tfvars_path}")
        validation_status="fail"
    fi
    
    # Extract token ID and secret using grep/awk
    local token_id
    local token_secret
    token_id=$(grep -E '^pm_api_token_id' "${tfvars_path}" | awk -F'"' '{print $2}')
    token_secret=$(grep -E '^pm_api_token_secret' "${tfvars_path}" | awk -F'"' '{print $2}')
    
    # Validate token ID
    if [[ "${token_id}" != "terraform@pve!terraform-token" ]]; then
        errors+=("Invalid token_id: expected 'terraform@pve!terraform-token', got '${token_id}'")
        validation_status="fail"
    fi
    
    # Validate secret presence (non-empty, not placeholder)
    if [[ -z "${token_secret}" ]]; then
        errors+=("Secret is empty")
        validation_status="fail"
    elif [[ "${token_secret}" =~ ^(REPLACEME|YOUR_SECRET|<secret>|CHANGEME|xxx)$ ]]; then
        errors+=("Secret appears to be a placeholder")
        validation_status="fail"
    fi
    
    # Generate hash
    local file_hash
    file_hash=$(sha256sum "${tfvars_path}" | awk '{print $1}')
    
    # Generate validation proof JSON
    local proof_json
    proof_json=$(jq -n \
        --arg ts "$(date -Iseconds)" \
        --arg status "${validation_status}" \
        --arg token_id "${token_id}" \
        --argjson secret_present "$([[ -n "${token_secret}" && ! "${token_secret}" =~ ^(REPLACEME|YOUR_SECRET|<secret>|CHANGEME|xxx)$ ]] && echo true || echo false)" \
        --arg hash "${file_hash}" \
        --argjson errors "$(printf '%s\n' "${errors[@]}" | jq -R . | jq -s .)" \
        '{
            timestamp: $ts,
            template_source: "heredoc",
            rendered_path: env.TFVARS_DIR + "/prod.tfvars",
            validation_status: $status,
            token_id: $token_id,
            secret_present: $secret_present,
            file_hash: $hash,
            validation_errors: $errors
        }')
    
    echo "${proof_json}"
    
    if [[ "${validation_status}" == "fail" ]]; then
        return 1
    fi
}
```

**Evidence proof files**:
- `reports/prod-tfvars/provisioning.txt`: Human-readable redacted summary
- `reports/prod-tfvars/validation.json`: JSON validation proof (schema in contracts/)
- `reports/prod-tfvars/prod.tfvars.sha256`: Just the hash value (for quick reference)

---

## R5: LAB Snapshot Format

### Decision
**Use JSON schema with required fields (containers, services) and optional fields (latest_evidence, mount_checks), collecting data via `pct` commands and file system checks.**

This provides a lightweight, parseable snapshot that captures essential state without requiring complex integrations.

### Rationale
1. **JSON format**: Easy to parse, generate, and extend; widely supported
2. **Container data via pct**: `pct list` and `pct config` provide VMID, hostname, status, and network config
3. **IPv4 extraction**: Parse LXC config for `net0` and extract IP address
4. **Mount checks**: Read `/proc/mounts` inside container (via `pct exec`) to verify mount paths
5. **Evidence pointers**: Scan artifact directory for latest RUN_ID per service

### Alternatives Considered
1. **Prometheus-style metrics**: Rejected because it's overkill for snapshot use case
2. **YAML format**: Rejected because JSON has better tooling support in Bash (jq)
3. **CSV format**: Rejected because hierarchical data (containers with mounts) doesn't fit tabular format

### Implementation Notes

**Container collection** (`scripts/lab/lib/snapshot.sh`):

```bash
collect_containers() {
    # Output: JSON array of container objects
    pct list | tail -n +2 | while read -r vmid status _ _ _ hostname; do
        # Get IP address from config
        local ipv4=""
        if pct config "${vmid}" | grep -q 'net0'; then
            ipv4=$(pct config "${vmid}" | grep 'net0' | grep -oP 'ip=\K[^/,]+' || echo "")
        fi
        
        jq -n \
            --argjson vmid "${vmid}" \
            --arg hostname "${hostname}" \
            --arg status "${status}" \
            --arg ipv4 "${ipv4}" \
            '{
                vmid: $vmid,
                hostname: $hostname,
                status: $status,
                ipv4: $ipv4
            }'
    done | jq -s .
}
```

**Service evidence pointers**:

```bash
collect_service_evidence() {
    local artifact_root="${ARTIFACT_ROOT}/service-deploy-runs"
    local services=()
    
    # For each service in allowlist
    for service in $(jq -r 'keys[]' scripts/lab/service-scope-allowlist.json); do
        # Find latest run for this service
        local latest_run
        latest_run=$(find "${artifact_root}" -maxdepth 1 -name "*-${service}-*" -type d | sort -r | head -1)
        
        if [[ -n "${latest_run}" ]]; then
            local run_id
            run_id=$(basename "${latest_run}")
            services+=("$(jq -n --arg svc "${service}" --arg run "${run_id}" --arg path "${latest_run}" '{service: $svc, run_id: $run, path: $path}')")
        fi
    done
    
    printf '%s\n' "${services[@]}" | jq -s 'map({(.service): {run_id, path}}) | add'
}
```

**Mount validation**:

```bash
check_mounts() {
    local vmid="$1"
    local expected_mount="/media/video"
    
    # Check if container is running
    if ! pct status "${vmid}" | grep -q running; then
        echo "Container ${vmid} not running, skipping mount check" >&2
        return
    fi
    
    # Check mount via pct exec
    local mount_info
    mount_info=$(pct exec "${vmid}" -- grep "${expected_mount}" /proc/mounts 2>/dev/null || echo "")
    
    if [[ -n "${mount_info}" ]]; then
        local source
        local options
        source=$(echo "${mount_info}" | awk '{print $1}')
        options=$(echo "${mount_info}" | awk '{print $4}')
        
        local read_only=false
        if [[ "${options}" =~ ro ]]; then
            read_only=true
        fi
        
        jq -n \
            --argjson vmid "${vmid}" \
            --arg mount_path "${expected_mount}" \
            --argjson mounted true \
            --argjson read_only "${read_only}" \
            --arg source "${source}" \
            '{
                container_vmid: $vmid,
                mount_path: $mount_path,
                mounted: $mounted,
                read_only: $read_only,
                source: $source
            }'
    else
        jq -n \
            --argjson vmid "${vmid}" \
            --arg mount_path "${expected_mount}" \
            --argjson mounted false \
            '{
                container_vmid: $vmid,
                mount_path: $mount_path,
                mounted: $mounted
            }'
    fi
}
```

**Full snapshot schema**: See `contracts/evidence-lab-snapshot.schema.json` in Phase 1 design.

---

## R6: Evidence Pack Extension Strategy

### Decision
**Add new optional fields to existing evidence profile contract without version bump. Offline verification will validate presence only for runs where environment=prod (tfvars proof) and all runs (LAB snapshot).**

This allows backward compatibility with existing evidence packs while enforcing new requirements going forward.

### Rationale
1. **Additive changes**: New fields are additions, not modifications to existing fields
2. **Conditional validation**: tfvars proof required only when `environment: prod` in metadata
3. **LAB snapshot universal**: Required for all runs going forward; older evidence without it will fail verification (acceptable tradeoff)
4. **No version bump needed**: Contract version 1.0.0 remains valid; additive changes don't break existing verifiers

### Alternatives Considered
1. **Version bump to 2.0.0**: Rejected because it would invalidate all existing evidence packs
2. **Separate evidence profile**: Rejected because it would require duplicating validation rules
3. **Optional validation for all new fields**: Rejected because LAB snapshot is core requirement, not optional

### Implementation Notes

**Evidence profile extension** (`scripts/lab/profiles.d/service-deploy.json`):

Add to `required_fields` array:
```json
{
  "path": "reports/lab-snapshot.json",
  "type": "file",
  "description": "LAB inventory snapshot (required for all runs)"
}
```

Add to `conditional_fields` array:
```json
{
  "path": "reports/prod-tfvars/validation.json",
  "type": "file",
  "condition": "environment == 'prod'",
  "description": "PROD tfvars validation proof (required for PROD runs)"
},
{
  "path": "reports/prod-tfvars/prod.tfvars.sha256",
  "type": "file",
  "condition": "environment == 'prod'",
  "description": "PROD tfvars hash (required for PROD runs)"
}
```

**Verification logic** (`scripts/lab/verify_evidence.py`):

```python
# Check LAB snapshot (universal requirement)
snapshot_path = evidence_dir / "reports" / "lab-snapshot.json"
if not snapshot_path.exists():
    errors.append("Missing required lab-snapshot.json")
else:
    # Validate against schema
    with open(snapshot_path) as f:
        snapshot = json.load(f)
    validate_json_schema(snapshot, "evidence-lab-snapshot.schema.json")

# Check tfvars proof (conditional on environment)
metadata = load_metadata(evidence_dir / "metadata.json")
if metadata.get("environment") == "prod":
    tfvars_proof_path = evidence_dir / "reports" / "prod-tfvars" / "validation.json"
    if not tfvars_proof_path.exists():
        errors.append("Missing required prod-tfvars validation proof for PROD run")
    else:
        with open(tfvars_proof_path) as f:
            proof = json.load(f)
        validate_json_schema(proof, "evidence-tfvars-proof.schema.json")
        
        # Additional validation: status must be "pass"
        if proof.get("validation_status") != "pass":
            errors.append(f"tfvars validation failed: {proof.get('validation_errors')}")
```

---

## R7: Workflow Job Dependency Patterns

### Decision
**Use `needs:` keyword to create linear job dependency chain: `plan_lab` → `apply_lab` → (manual approval via `environment: prod`) → `plan_prod` → `apply_prod`.**

This enforces the LAB→PROD promotion sequence at the workflow level, making it impossible to skip LAB.

### Rationale
1. **Explicit dependencies**: `needs: [plan_lab]` on `apply_lab` ensures plan completes first
2. **Approval gate integration**: `environment: prod` on `plan_prod` pauses workflow after LAB apply
3. **Concurrency control**: `concurrency.group` includes service name to prevent overlapping deploys
4. **Visibility**: Job graph in GitHub Actions UI clearly shows promotion flow

### Alternatives Considered
1. **Single job with multiple steps**: Rejected because approval gates require separate jobs
2. **Matrix strategy for environments**: Rejected because it would allow parallel LAB+PROD (violates requirement)
3. **Separate workflows with API trigger**: Rejected because it complicates auditing and loses single-run context

### Implementation Notes

**Promote workflow job structure**:

```yaml
jobs:
  plan_lab:
    name: Plan (LAB)
    runs-on: [self-hosted]
    outputs:
      run_id: ${{ steps.capture_run_id.outputs.run_id }}
      destructive: ${{ steps.detect_destructive.outputs.destructive }}
    steps:
      - name: Plan LAB
        # ... plan logic

  apply_lab:
    name: Apply (LAB)
    runs-on: [self-hosted]
    needs: [plan_lab]
    steps:
      - name: Destructive gate (LAB)
        run: |
          if [[ "${{ needs.plan_lab.outputs.destructive }}" == "true" ]]; then
            # Validate confirm_destructive_lab input
          fi
      - name: Apply LAB
        # ... apply logic

  plan_prod:
    name: Plan (PROD)
    runs-on: [self-hosted]
    needs: [apply_lab]
    environment: prod  # <-- APPROVAL GATE HERE
    outputs:
      run_id: ${{ steps.capture_run_id.outputs.run_id }}
      destructive: ${{ steps.detect_destructive.outputs.destructive }}
    steps:
      - name: Plan PROD
        # ... plan logic

  apply_prod:
    name: Apply (PROD)
    runs-on: [self-hosted]
    needs: [plan_prod]
    steps:
      - name: Provision prod.tfvars
        # ... tfvars provisioning
      - name: Apply PROD
        # ... apply logic
```

**Concurrency control**:

```yaml
concurrency:
  group: lxc-promote-${{ github.event.inputs.service }}
  cancel-in-progress: false
```

This prevents concurrent promotions of the same service while allowing different services to promote in parallel.

---

## R8: Hotfix Path Design

### Decision
**Require explicit boolean `hotfix_override: true` input combined with `environment: prod` approval gate when `github.ref` is `refs/heads/main`. Feature branches do not require hotfix override.**

This allows hotfixes on main while maintaining approval requirements and creating an audit trail.

### Rationale
1. **Branch detection**: `github.ref == 'refs/heads/main'` identifies main branch runs
2. **Explicit intent**: Boolean input forces operator to acknowledge hotfix mode
3. **Approval preserved**: Even with override, PROD still requires environment approval
4. **Audit trail**: GitHub Actions log shows hotfix_override value and approval events
5. **Feature branch clarity**: Non-main branches don't need override (normal workflow)

### Alternatives Considered
1. **Confirmation string instead of boolean**: Rejected because boolean is clearer in UI
2. **No override on main (block completely)**: Rejected because legitimate hotfixes need a path
3. **Bypass approval for hotfix**: Rejected because it weakens safety controls

### Implementation Notes

**Promote workflow inputs**:

```yaml
on:
  workflow_dispatch:
    inputs:
      service:
        type: choice
        # ...
      hotfix_override:
        description: "Required confirmation for hotfix on main branch"
        type: boolean
        required: false
        default: false
```

**Hotfix gate in apply_prod job**:

```yaml
- name: Hotfix confirmation gate
  run: |
    set -euo pipefail
    
    # Check if on main branch
    if [[ "${{ github.ref }}" == "refs/heads/main" ]]; then
      hotfix_override="${{ github.event.inputs.hotfix_override }}"
      
      # Require explicit override for main branch PROD deploys
      if [[ "${hotfix_override}" != "true" ]]; then
        echo "ERROR: PROD deploy on main requires hotfix_override=true" >&2
        echo "This is a safety gate to prevent accidental hotfixes." >&2
        echo "If this is intentional, rerun workflow with hotfix_override=true" >&2
        exit 1
      fi
      
      echo "⚠️  HOTFIX MODE: Deploying to PROD from main branch"
      echo "Approval gate still required (environment: prod)"
    else
      echo "Running from feature branch: ${{ github.ref }}"
      echo "Hotfix override not required"
    fi
```

**Audit trail**:
- Workflow run shows `hotfix_override` input value in "Run details"
- Job log includes "⚠️ HOTFIX MODE" warning when override used
- Approval event logged with reviewer identity
- Evidence pack includes branch name in metadata

---

## Summary

All research tasks complete. Key decisions:

1. **R1**: Hardcoded workflow choices with runtime validation
2. **R2**: GitHub Environment `prod` with required approvers
3. **R3**: Bash heredoc templating with secure temp files
4. **R4**: Multi-check validation with SHA256 hash and redacted JSON proof
5. **R5**: JSON snapshot with `pct` commands and mount checks
6. **R6**: Additive evidence profile fields (no version bump)
7. **R7**: Linear job dependency chain with approval gate
8. **R8**: Boolean hotfix override with branch detection

**Ready for Phase 1 (Design)**: All technical approaches validated and documented.

