#!/usr/bin/env bash
# sudo.sh - centralized sudo helper enforcing sudo -n and clear failures

set -euo pipefail

sudo_n() {
    if ! command -v sudo >/dev/null 2>&1; then
        echo "ERROR: sudo not installed; cannot escalate" >&2
        return 127
    fi

    if [[ $# -eq 0 ]]; then
        echo "ERROR: sudo_n requires a command" >&2
        return 2
    fi

    if ! sudo -n true 2>/dev/null; then
        echo "ERROR: sudo -n not permitted for current user; update sudoers to allow required commands" >&2
        return 1
    fi

    sudo -n "$@"
}
