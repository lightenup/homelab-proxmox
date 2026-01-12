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

# Prefer compact structured reason files when present.
emit_file_excerpt "Error reason (plan)" "${evidence_dir%/}/reports/plan/summary.txt" "cat"
emit_file_excerpt "Error reason (apply)" "${evidence_dir%/}/reports/apply/summary.txt" "cat"

# Common apply-time diagnostics (bounded).
emit_file_excerpt "Terraform state pull stderr (tail)" "${evidence_dir%/}/reports/apply/terraform-state-pull.stderr.txt" "tail"
emit_file_excerpt "Ansible inventory-from-state stderr (tail)" "${evidence_dir%/}/reports/apply/ansible-inventory-from-state.stderr.txt" "tail"
emit_file_excerpt "Vault check stderr (tail)" "${evidence_dir%/}/reports/apply/vault-check.stderr.txt" "tail"

# Always include some preflight context; it's usually the most actionable.
emit_file_excerpt "Preflight (tail)" "${evidence_dir%/}/preflight.txt" "tail"

# Ansible output is often the key for rc=4 failures; keep it bounded.
for af in "${evidence_dir%/}"/reports/apply/ansible-*.txt; do
  if [[ -f "${af}" ]]; then
    emit_file_excerpt "Ansible output (tail)" "${af}" "tail"
  fi
done

emit_file_excerpt "Inventory generation (tail)" "${evidence_dir%/}/reports/apply/update-inventory.txt" "tail"

# Healthcheck output can be very actionable but should stay bounded.
for hc in "${evidence_dir%/}"/reports/healthcheck/*.txt; do
  if [[ -f "${hc}" ]]; then
    emit_file_excerpt "Healthcheck (tail)" "${hc}" "tail"
  fi
done
