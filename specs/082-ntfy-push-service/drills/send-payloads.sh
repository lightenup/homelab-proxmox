#!/usr/bin/env bash
# T033 drill: POST synthetic Alertmanager v4 payloads through the homelab-alertmanager
# template and assert title, priority and message line count against expected.json
# (data-model.md § "Alert → notification mapping", research R-003/R-004).
#
# Usage:
#   NTFY_URL=https://ntfy.hus-sky.no \
#   NTFY_ALERTMANAGER_TOKEN=... NTFY_OWNER_TOKEN=... \
#     specs/082-ntfy-push-service/drills/send-payloads.sh
#
# Publishes to the `alerts` topic, so every message also reaches the subscribed phone.
# Reads each message back with the owner token. Exits non-zero on any mismatch.
# Needs curl and python3. Never echoes tokens.
set -euo pipefail

for var in NTFY_URL NTFY_ALERTMANAGER_TOKEN NTFY_OWNER_TOKEN; do
  if [[ -z "${!var:-}" ]]; then
    echo "ERROR: ${var} is not set." >&2
    exit 2
  fi
done

NTFY_URL="${NTFY_URL%/}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/payloads" && pwd)"
FAILURES=0

for payload in "$DIR"/[0-9]*.json; do
  name="$(basename "$payload" .json)"
  body="$(mktemp)"
  code=$(curl -s -o "$body" -w '%{http_code}' -X POST \
    -H "Authorization: Bearer ${NTFY_ALERTMANAGER_TOKEN}" \
    --data-binary @"$payload" \
    "${NTFY_URL}/alerts?template=homelab-alertmanager")
  if [[ "$code" != "200" ]]; then
    echo "FAIL ${name} publish got=${code} $(head -c 200 "$body")"
    FAILURES=$((FAILURES + 1))
    rm -f "$body"
    continue
  fi
  if python3 -I - "$body" "$DIR/expected.json" "$name" <<'EOF'
import json, sys
msg = json.load(open(sys.argv[1]))
exp = json.load(open(sys.argv[2]))[sys.argv[3]]
title = msg.get("title", "").strip()
prio = msg.get("priority", 3)
lines = [l for l in msg.get("message", "").splitlines() if l.strip()]
problems = []
if title != exp["title"]:
    problems.append(f"title={title!r} want {exp['title']!r}")
if prio != exp["priority"]:
    problems.append(f"priority={prio} want {exp['priority']}")
if len(lines) != exp["lines"]:
    problems.append(f"lines={len(lines)} want {exp['lines']}")
print(("FAIL " if problems else "PASS ") + sys.argv[3] + (" " + "; ".join(problems) if problems else f" {title!r} p{prio} {len(lines)} lines"))
sys.exit(1 if problems else 0)
EOF
  then :; else FAILURES=$((FAILURES + 1)); fi
  rm -f "$body"
done

# The owner can read what was just published (the phone's view).
code=$(curl -s -o /dev/null -w '%{http_code}' \
  -H "Authorization: Bearer ${NTFY_OWNER_TOKEN}" "${NTFY_URL}/alerts/json?poll=1&since=5m")
[[ "$code" == "200" ]] && echo "PASS owner read-back" || { echo "FAIL owner read-back got=${code}"; FAILURES=$((FAILURES + 1)); }

echo ""
echo "=== template drill: ${FAILURES} failure(s) ==="
[[ $FAILURES -eq 0 ]]
