#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Usage:
  render_github_annotations.sh --level <error|warning|notice> --title <title> --message <message>

Emits a single GitHub Actions workflow command annotation, with proper escaping.
EOF
}

gha_escape() {
    # https://docs.github.com/en/actions/using-workflows/workflow-commands-for-github-actions
    local s="$1"
    s="${s//'%'/'%25'}"
    s="${s//$'\r'/'%0D'}"
    s="${s//$'\n'/'%0A'}"
    echo "$s"
}

LEVEL=""
TITLE=""
MESSAGE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --level)
            LEVEL="${2:-}"
            shift 2
            ;;
        --title)
            TITLE="${2:-}"
            shift 2
            ;;
        --message)
            MESSAGE="${2:-}"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "ERROR: unknown arg: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [[ -z "$LEVEL" || -z "$TITLE" || -z "$MESSAGE" ]]; then
    usage >&2
    exit 2
fi

case "$LEVEL" in
    error|warning|notice) ;;
    *)
        echo "ERROR: invalid --level '$LEVEL'" >&2
        exit 2
        ;;
esac

title_escaped="$(gha_escape "$TITLE")"
message_escaped="$(gha_escape "$MESSAGE")"

echo "::${LEVEL} title=${title_escaped}::${message_escaped}"
