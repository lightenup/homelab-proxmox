#!/usr/bin/env bash
# lib/jsonl.sh - JSONL event emission to stderr

set -euo pipefail

# Global variable for events file
EVENTS_FILE=""

# Initialize JSONL event logging
# Usage: init_jsonl_events events_file_path
init_jsonl_events() {
    EVENTS_FILE="$1"
    mkdir -p "$(dirname "$EVENTS_FILE")"
    : > "$EVENTS_FILE"  # Create empty file
}

# Emit a JSONL event to stderr and capture to events.jsonl
# Usage: emit_event event_type runid [key=value ...]
emit_event() {
    local event_type="$1"
    local runid="$2"
    shift 2
    
    local timestamp
    timestamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    
    # Build event data JSON from key=value pairs
    local event_data="{"
    local first=true
    for kv in "$@"; do
        if [[ "$kv" =~ ^([^=]+)=(.*)$ ]]; then
            local key="${BASH_REMATCH[1]}"
            local value="${BASH_REMATCH[2]}"
            if [ "$first" = true ]; then
                first=false
            else
                event_data+=","
            fi
            event_data+="\"$key\":\"$value\""
        fi
    done
    event_data+="}"
    
    # Build complete event
    local event_json
    event_json=$(cat <<EOF
{"timestamp":"$timestamp","event_type":"$event_type","runid":"$runid","data":$event_data}
EOF
)
    
    # Emit to stderr
    echo "$event_json" >&2
    
    # Append to events file if initialized
    if [[ -n "$EVENTS_FILE" && -f "$EVENTS_FILE" ]]; then
        echo "$event_json" >> "$EVENTS_FILE"
    fi
}

# Convenience functions for common event types
emit_check_start() {
    local runid="$1"
    local check_id="$2"
    local title="$3"
    emit_event "check_start" "$runid" "check_id=$check_id" "title=$title"
}

emit_check_complete() {
    local runid="$1"
    local check_id="$2"
    local result="$3"
    emit_event "check_complete" "$runid" "check_id=$check_id" "result=$result"
}

emit_phase_start() {
    local runid="$1"
    local phase="$2"
    emit_event "phase_start" "$runid" "phase=$phase"
}

emit_phase_complete() {
    local runid="$1"
    local phase="$2"
    emit_event "phase_complete" "$runid" "phase=$phase"
}

emit_error() {
    local runid="$1"
    local message="$2"
    emit_event "error" "$runid" "message=$message"
}

emit_warning() {
    local runid="$1"
    local message="$2"
    emit_event "warning" "$runid" "message=$message"
}
