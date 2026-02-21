#!/usr/bin/env bash
# lib/rebuild_state.sh - Simple rebuild state machine helpers

set -euo pipefail

rebuild_state_path() {
    echo "${REBUILD_STATE_PATH:-${STATE_PATH:-${ARTIFACT_DIR:-}/state.json}}"
}

rebuild_state_init() {
    local run_id="$1"
    local environment="$2"
    local mode="$3"
    shift 3
    local phases=("$@")
    local state_path
    state_path="$(rebuild_state_path)"

    mkdir -p "$(dirname "$state_path")"

    local now
    now="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

    local phases_json
    phases_json=$(printf '%s\n' "${phases[@]}" | jq -R '{name: ., status: "pending", started_at: null, ended_at: null, notes: ""}' | jq -s '.')

    cat > "$state_path" <<JSON
{
  "run_id": "$run_id",
  "environment": "$environment",
  "mode": "$mode",
  "status": "pending",
  "created_at": "$now",
  "updated_at": "$now",
  "phases": $phases_json
}
JSON
}

rebuild_state_set_status() {
    local status="$1"
    local state_path
    state_path="$(rebuild_state_path)"
    local now
    now="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

    tmpfile=$(mktemp)
    jq --arg status "$status" --arg now "$now" '.status=$status | .updated_at=$now' "$state_path" > "$tmpfile"
    mv "$tmpfile" "$state_path"
}

rebuild_state_update_phase() {
    local phase_name="$1"
    local phase_status="$2"
    local notes="${3:-}"

    local state_path
    state_path="$(rebuild_state_path)"
    local now
    now="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

    tmpfile=$(mktemp)
    jq --arg phase "$phase_name" --arg status "$phase_status" --arg notes "$notes" --arg now "$now" '
      .updated_at=$now
      | .phases = (.phases | map(if .name == $phase then
            .status = $status
          | .notes = $notes
          | .started_at = (if $status == "running" then $now else .started_at end)
          | .ended_at = (if ($status == "completed" or $status == "failed") then $now else .ended_at end)
        else . end))
    ' "$state_path" > "$tmpfile"
    mv "$tmpfile" "$state_path"
}
