#!/bin/bash
# Verify FR-016's residency requirement on the Mac: every model backing a homelab-facing
# role alias is PINNED, so it cannot be evicted and cold-load a request into the gateway's
# timeout.
#
# WHY THIS EXISTS, AND WHY IT IS NOT THE OBVIOUS CHECK. The plan called for asserting this
# against oMLX's `/admin/api/models`, which reports per-model `loaded` and `pinned`. That
# endpoint answers `401 Admin authentication required` to every credential present on this
# machine — the 4-char `auth.api_key`, the 64-char `auth.secret_key`, and no auth at all.
# The oMLX GUI does not use it over HTTP: it talks to the server through a unix socket at
# ~/Library/Application Support/oMLX/control.sock. So the admin API is not scriptable here,
# and the residency claim sat unverified from 2026-09-14 to 2026-09-19 for that reason.
#
# It did not need to. Pinning is CONFIGURED in ~/.omlx/model_settings.json (`is_pinned`),
# which is the same lever the amendment used to set it, and that file is readable. This
# asserts the configuration rather than the live engine state — a deliberate, stated limit:
# `/health` exposes only an aggregate `loaded_count`, never per-model residency, so no
# unprivileged caller can observe which models are resident right now. What this does prove
# is that nothing has silently un-pinned an aliased model, which is the regression FR-016
# is actually worried about.
#
# Run it after any oMLX restart — pinning survives in the settings file, but a model added
# or swapped behind a role alias will not be pinned unless someone remembers to.

set -uo pipefail

CONFIG="${LITELLM_CONFIG:-$HOME/Development/private/local-llm/proxy/litellm-config.yaml}"
SETTINGS="${OMLX_SETTINGS:-$HOME/.omlx/model_settings.json}"
HEALTH="${OMLX_HEALTH:-http://127.0.0.1:8000/health}"
# The role aliases the homelab gateway addresses. Anything the Mac's own
# context_window_fallbacks escalate to is added automatically — hermes-deep reaches
# Qwen3.8-27B-8bit:qwen-long that way, and an unpinned fallback target is the same hazard
# as an unpinned primary. Override to check a different set.
ALIASES="${OMLX_CHECK_ALIASES:-fast coder reasoner}"

python3 - "$CONFIG" "$SETTINGS" "$HEALTH" $ALIASES <<'PY'
import json, re, sys, urllib.request

config, settings, health, *aliases = sys.argv[1:]

cfg = open(config).read()
# model_name: <alias>  ...  model: openai/<Model>:<profile>
pairs = dict(re.findall(r'^\s*-\s*model_name:\s*(\S+)\s*\n(?:.*\n)??\s*model:\s*(\S+)',
                        cfg, re.M))

# Pull in every context_window_fallback target. Derived rather than listed, so a change to
# the Mac's escalation path is picked up here instead of silently going unchecked.
block = re.search(r'^\s*context_window_fallbacks:\s*\n((?:\s*-\s*\S+:.*\n)+)', cfg, re.M)
if block:
    for targets in re.findall(r'^\s*-\s*\S+:\s*\[([^\]]*)\]', block.group(1), re.M):
        for t in re.findall(r'[\w.:\-]+', targets):
            if t not in aliases:
                aliases.append(t)
pins = json.load(open(settings)).get('models', {})

rc, rows = 0, []
for alias in aliases:
    raw = pairs.get(alias)
    if raw is None:
        rows.append((alias, '(not served)', '-', 'FAIL')); rc = 1; continue
    model = raw.split('/', 1)[-1].split(':', 1)[0]       # openai/Foo:profile -> Foo
    pinned = pins.get(model, {}).get('is_pinned')
    ok = pinned is True
    rows.append((alias, model, str(pinned), 'ok' if ok else 'FAIL'))
    if not ok:
        rc = 1

w = max(len(r[1]) for r in rows)
print("FR-016 residency — models backing the homelab role aliases")
for alias, model, pinned, verdict in rows:
    print(f"  {alias:12s} -> {model:{w}s}  is_pinned={pinned:5s}  [{verdict}]")

try:
    with urllib.request.urlopen(health, timeout=10) as r:
        pool = json.loads(r.read()).get('engine_pool', {})
    print(f"\n  oMLX engine pool: {pool.get('loaded_count')} of {pool.get('model_count')} models loaded "
          f"({pool.get('current_model_memory', 0) / 1e9:.1f} GB of "
          f"{pool.get('final_ceiling', 0) / 1e9:.1f} GB)")
    print("  (aggregate only — /health never reports which models are resident, and the")
    print("   per-model admin endpoint refuses every credential on this machine)")
except Exception as e:
    print(f"\n  oMLX /health unreachable ({type(e).__name__}) — is the app running?")
    rc = 1

print("\n" + ("PASS — every aliased model is pinned" if rc == 0
              else "FAIL — an aliased model is not pinned, or oMLX is down"))
sys.exit(rc)
PY
