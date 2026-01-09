#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Usage:
  render_github_summary.sh <plan-ui-summary.json>

Prints bounded Markdown suitable for appending to $GITHUB_STEP_SUMMARY.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" || -z "${1:-}" ]]; then
    usage
    exit 0
fi

INPUT_PATH="$1"

python3 - <<'PY' "$INPUT_PATH"
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
obj = json.loads(path.read_text(encoding='utf-8'))

run_id = obj.get('run_id')
env = obj.get('environment')
service = obj.get('service')
destructive = obj.get('destructive')
counts = obj.get('counts') or {}
resources = obj.get('resources') or []
truncated = obj.get('truncated')
resources_total = obj.get('resources_total')
resources_shown = obj.get('resources_shown')
required_token = obj.get('confirmation_token_required')
evidence = obj.get('evidence') or {}

print('## Plan Summary')
print(f'- Run: `{run_id}`')
print(f'- Environment: `{env}`')
print(f'- Service: `{service}`')
print('')

print('### Counts')
print(f"- create: **{counts.get('create', 0)}**")
print(f"- update: **{counts.get('update', 0)}**")
print(f"- replace: **{counts.get('replace', 0)}**")
print(f"- destroy: **{counts.get('destroy', 0)}**")
print('')

print('### Safety')
print(f"- destructive: **{str(bool(destructive)).lower()}**")
if required_token:
    print(f"- confirmation token required: `{required_token}`")
else:
    print(f"- confirmation token required: (none)")
print('')

print('### Resources (bounded)')
if not resources:
    print('- (no changes)')
else:
    for r in resources:
        addr = r.get('address')
        cls = r.get('class')
        actions = r.get('actions')
        print(f"- `{addr}` ({cls}: {actions})")

if truncated:
    remaining = max(0, int(resources_total or 0) - int(resources_shown or 0))
    print(f"- …and **{remaining}** more")
print('')

print('### Evidence')
print(f"- PVE runs dir: `{evidence.get('pve_runs_dir')}`")
print(f"- PVE run dir: `{evidence.get('pve_run_id_dir')}`")

print('')
print('### Next steps')
if required_token:
    print(f"- If apply is blocked due to destructive changes, re-run with the required token: `{required_token}`")
else:
    print("- If a later stage fails, open the evidence pack referenced above for details")

print("- If you see missing tfvars / secrets errors, verify the tfvars material exists on PVE under `/var/lib/homelab-proxmox/tfvars` (do not print secrets in logs)")
print("- If PROD apply reports missing planfile, re-run the promotion so the PROD plan stage can regenerate the saved plan")
PY
