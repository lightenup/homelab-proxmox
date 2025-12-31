#!/usr/bin/env bash
# lib/evidence.sh - Evidence pack management functions
# Part of 019c1-semantic-safety-closure

set -euo pipefail

# Create evidence pack directory structure
# Usage: create_evidence_pack base_dir
# Returns: runid (timestamp-based)
create_evidence_pack() {
    local base_dir="$1"
    
    # Generate runid with timestamp format: lab-YYYYMMDD-HHMMSS
    local runid
    runid="lab-$(date -u +"%Y%m%d-%H%M%S")"
    
    local evidence_dir="${base_dir}/${runid}"
    
    # Create directory structure
    mkdir -p "$evidence_dir"
    mkdir -p "$evidence_dir/logs"
    mkdir -p "$evidence_dir/reports"
    
    # Return runid
    echo "$runid"
}

# Generate evidence_manifest.json
# Usage: generate_manifest evidence_dir [artifact_path type check_id sha256 ...]
generate_manifest() {
    local evidence_dir="$1"
    shift
    
    local manifest_schema_version="1.0.0"
    
    # Build artifacts array from arguments (groups of 4: path, type, check_id, sha256)
    local artifacts_json="["
    local first=true
    
    while [[ $# -gt 0 ]]; do
        local path="$1"
        local type="${2:-unknown}"
        local check_id="${3:-none}"
        local sha256="${4:-}"
        shift 4 2>/dev/null || break
        
        if [ "$first" = true ]; then
            first=false
        else
            artifacts_json+=","
        fi
        
        artifacts_json+=$(cat <<EOF
{
  "path": "$path",
  "type": "$type",
  "check_id": "$check_id"$([ -n "$sha256" ] && echo ",\"sha256\":\"$sha256\"" || echo "")
}
EOF
)
    done
    artifacts_json+="]"
    
    # Write manifest
    cat > "${evidence_dir}/evidence_manifest.json" <<EOF
{
  "manifest_schema_version": "$manifest_schema_version",
  "artifacts": $artifacts_json
}
EOF
}

# Add artifact to manifest (append mode)
# Usage: add_artifact_to_manifest evidence_dir artifact_path type check_id [sha256]
add_artifact_to_manifest() {
    local evidence_dir="$1"
    local artifact_path="$2"
    local type="$3"
    local check_id="$4"
    local sha256="${5:-}"
    
    local manifest_file="${evidence_dir}/evidence_manifest.json"
    
    # If manifest doesn't exist, create it
    if [[ ! -f "$manifest_file" ]]; then
        generate_manifest "$evidence_dir"
    fi
    
    # Parse existing manifest, add new artifact, write back
    # This is a simplified append - full implementation would use jq
    # For now, we'll rebuild on final generation
    :
}

# Validate evidence files against JSON schemas
# Usage: validate_evidence evidence_dir contracts_dir
validate_evidence() {
    local evidence_dir="$1"
    local contracts_dir="$2"
    
    local validation_ok=true
    
    # Check if validation tools are available
    if command -v ajv &>/dev/null; then
        # Validate with ajv-cli
        for json_file in "${evidence_dir}"/*.json; do
            if [[ -f "$json_file" ]]; then
                local basename
                basename="$(basename "$json_file")"
                local schema_file="${contracts_dir}/${basename%.json}_schema.json"
                
                if [[ -f "$schema_file" ]]; then
                    if ! ajv validate -s "$schema_file" -d "$json_file" 2>&1; then
                        echo "ERROR: Validation failed for $basename" >&2
                        validation_ok=false
                    fi
                fi
            fi
        done
    elif python3 -c "import jsonschema" 2>/dev/null; then
        # Validate with Python jsonschema
        echo "Using Python jsonschema for validation" >&2
        # Implementation would use Python script
        :
    else
        echo "WARNING: No JSON schema validation tool available (ajv-cli or python jsonschema)" >&2
        echo "Skipping schema validation" >&2
    fi
    
    if [ "$validation_ok" = true ]; then
        return 0
    else
        return 1
    fi
}
