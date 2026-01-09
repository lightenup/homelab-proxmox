#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  render_failure_evidence.sh --evidence-dir <path> [--max-lines N]

Prints bounded Markdown excerpts from common evidence files (e.g. preflight.txt)
for appending to $GITHUB_STEP_SUMMARY.

This is intended for failure paths only.
EOF
}

evidence_dir=""
max_lines=120

while [[ $# -gt 0 ]]; do
  case "$1" in
    --evidence-dir)
      evidence_dir="${2:-}"
      shift 2
      ;;
    --max-lines)
      max_lines="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: Unknown arg: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "${evidence_dir}" ]]; then
  echo "ERROR: --evidence-dir is required" >&2
  usage >&2
  exit 2
fi

sanitize_markdown_codeblock() {
  # Prevent accidental closing of fenced blocks.
  sed -E 's/\r$//; s/```/``\\`/g'
}

emit_file_excerpt() {
  local title="$1"
  local path="$2"
  local mode="$3"  # tail|cat

  if [[ ! -f "${path}" ]]; then
    return 0
  fi

  if [[ ! -s "${path}" ]]; then
    return 0
  fi

  echo "### ${title}"
  echo "- Source: \`${path}\`"
  echo "\n\`\`\`text"

  if [[ "${mode}" == "tail" ]]; then
    tail -n "${max_lines}" "${path}" | sanitize_markdown_codeblock
  else
    cat "${path}" | sanitize_markdown_codeblock
  fi

  echo "\n\`\`\`"
  echo ""
}

# Prefer the compact structured reason file when present.
emit_file_excerpt "Error reason" "${evidence_dir%/}/reports/plan/summary.txt" "cat"

# Always include some preflight context; it's usually the most actionable.
emit_file_excerpt "Preflight (tail)" "${evidence_dir%/}/preflight.txt" "tail"
