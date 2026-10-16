#!/usr/bin/env bash
# ntfy ACL matrix check (spec 082, SC-002)
#
# Asserts every cell in data-model.md § "The access matrix the SC-002 check asserts":
#
#   Credential ↓ / action → | read alerts | read hermes | write alerts | write hermes | write other
#   ------------------------+-------------+-------------+--------------+--------------+-------------
#   none                    | ✗           | ✗           | ✗            | ✗            | ✗
#   owner token             | ✓           | ✓           | ✗            | ✗            | ✗
#   alertmanager token      | ✗           | ✗           | ✓            | ✗            | ✗
#   hermes token            | ✗           | ✗           | ✗            | ✓            | ✗
#
# ✓ = HTTP 200; ✗ = HTTP 401 or 403.
#
# Usage:
#   NTFY_URL=http://192.168.1.222 \
#   NTFY_OWNER_TOKEN=... NTFY_ALERTMANAGER_TOKEN=... NTFY_HERMES_TOKEN=... \
#     scripts/healthcheck/ntfy-acl-check.sh
#
# Exits non-zero on any FAIL. Never echoes tokens.
set -euo pipefail

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  cat <<'EOF'
ntfy-acl-check.sh — assert the ntfy access-control matrix (spec 082, SC-002)

Environment variables (all required):
  NTFY_URL                 Base URL, e.g. http://192.168.1.222 or https://ntfy.hus-sky.no
  NTFY_OWNER_TOKEN         Bearer token for the owner account
  NTFY_ALERTMANAGER_TOKEN  Bearer token for the alertmanager account
  NTFY_HERMES_TOKEN        Bearer token for the hermes account

Exit code: 0 if all 20 cells match, 1 otherwise.
EOF
  exit 0
fi

for var in NTFY_URL NTFY_OWNER_TOKEN NTFY_ALERTMANAGER_TOKEN NTFY_HERMES_TOKEN; do
  if [[ -z "${!var:-}" ]]; then
    echo "ERROR: ${var} is not set. See --help." >&2
    exit 2
  fi
done

NTFY_URL="${NTFY_URL%/}"
FAILURES=0
TOTAL=0

# do_request <token_or_empty> <method> <topic> <expected: allow|deny>
do_request() {
  local token="$1" method="$2" topic="$3" expected="$4"
  local url="${NTFY_URL}/${topic}"
  local code

  TOTAL=$((TOTAL + 1))

  if [[ -z "$token" ]]; then
    code=$(curl -s -o /dev/null -w '%{http_code}' -X "$method" "$url" \
      ${method:+-d "acl-check $(date -Is)"} \
      -H "Tags: acl-check" -H "Priority: min" 2>/dev/null || true)
  else
    code=$(curl -s -o /dev/null -w '%{http_code}' -X "$method" "$url" \
      -H "Authorization: Bearer ${token}" \
      ${method:+-d "acl-check $(date -Is)"} \
      -H "Tags: acl-check" -H "Priority: min" 2>/dev/null || true)
  fi

  local got_label
  case "$code" in
    200) got_label="allow" ;;
    401|403) got_label="deny" ;;
    *) got_label="unexpected(${code})" ;;
  esac

  local credential_label
  if [[ -z "$token" ]]; then
    credential_label="none"
  elif [[ "$token" == "$NTFY_OWNER_TOKEN" ]]; then
    credential_label="owner"
  elif [[ "$token" == "$NTFY_ALERTMANAGER_TOKEN" ]]; then
    credential_label="alertmanager"
  else
    credential_label="hermes"
  fi

  if [[ "$got_label" == "$expected" ]]; then
    echo "PASS ${credential_label} ${method} ${topic} got=${code}"
  else
    echo "FAIL ${credential_label} ${method} ${topic} got=${code} expected=${expected}"
    FAILURES=$((FAILURES + 1))
  fi
}

# --- Row: no credential ---
do_request "" GET  alerts  deny
do_request "" GET  hermes  deny
do_request "" POST alerts  deny
do_request "" POST hermes  deny
do_request "" POST other   deny

# --- Row: owner token (read *) ---
do_request "$NTFY_OWNER_TOKEN" GET  alerts  allow
do_request "$NTFY_OWNER_TOKEN" GET  hermes  allow
do_request "$NTFY_OWNER_TOKEN" POST alerts  deny
do_request "$NTFY_OWNER_TOKEN" POST hermes  deny
do_request "$NTFY_OWNER_TOKEN" POST other   deny

# --- Row: alertmanager token (write alerts only) ---
do_request "$NTFY_ALERTMANAGER_TOKEN" GET  alerts  deny
do_request "$NTFY_ALERTMANAGER_TOKEN" GET  hermes  deny
do_request "$NTFY_ALERTMANAGER_TOKEN" POST alerts  allow
do_request "$NTFY_ALERTMANAGER_TOKEN" POST hermes  deny
do_request "$NTFY_ALERTMANAGER_TOKEN" POST other   deny

# --- Row: hermes token (write hermes only) ---
do_request "$NTFY_HERMES_TOKEN" GET  alerts  deny
do_request "$NTFY_HERMES_TOKEN" GET  hermes  deny
do_request "$NTFY_HERMES_TOKEN" POST alerts  deny
do_request "$NTFY_HERMES_TOKEN" POST hermes  allow
do_request "$NTFY_HERMES_TOKEN" POST other   deny

echo ""
echo "=== ntfy ACL check: $((TOTAL - FAILURES))/${TOTAL} PASS, ${FAILURES} FAIL ==="

if [[ $FAILURES -gt 0 ]]; then
  exit 1
fi
