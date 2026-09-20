#!/usr/bin/env bash
# T054 / T055 — per-client RATE-LIMIT breach drill (FR-010, AS-5.1, AS-5.2, SC-010).
#
# T054 was reframed: the spend half of FR-010 is inert (local tiers carry no pricing, so
# spend is exactly 0.0 against any cap), which leaves rpm_limit as the only runaway-client
# guard that can actually be exercised.
#
# RUN IT ON THE GATEWAY LXC — it reads the master key from the compose file and the canary
# key from canary.sh, both of which are root-only and local to that host:
#
#   ssh root@192.168.1.112 'pct push 109 /tmp/drill.sh /tmp/drill.sh --perms 0700 \
#     && pct exec 109 -- bash /tmp/drill.sh'
#
# It provisions one throwaway key ("drill-bystander") to stand in as a second client and
# DELETES IT on exit, including on failure (trap). Nothing else is mutated. The live
# clients' own keys are never modified — the breaching client is `canary`, whose rpm_limit
# of 10 makes the breach cheap (16 requests, ~3s, tiny prompts at max_tokens 1).
#
# Recorded result: specs/064-llm-router/doctor-fault-injection.md § Row 11.
set -uo pipefail

BASE=http://127.0.0.1:4000
OUT=/tmp/drill-out; rm -rf "$OUT"; mkdir -p "$OUT"

MK=$(grep -oE 'LITELLM_MASTER_KEY: *"[^"]+"' /opt/llm-router/docker-compose.yml | sed -E 's/.*"(.*)"/\1/')
CANARY=$(grep -oE 'Bearer sk-[A-Za-z0-9_-]+' /opt/llm-router/canary.sh | head -1 | awk '{print $2}')
[ -n "$MK" ] && [ -n "$CANARY" ] || { echo "FATAL: could not read keys"; exit 1; }

say() { printf '\n== %s ==\n' "$*"; }

say "Phase 0 — live key state (does the declared rpm_limit actually exist on the key?)"
curl -s -H "Authorization: Bearer $MK" "$BASE/key/list?return_full_object=true&size=100" > "$OUT/keys.json"
curl -s -H "Authorization: Bearer $MK" "$BASE/team/list" > "$OUT/teams.json"
python3 - <<'PY'
import json
d=json.load(open('/tmp/drill-out/keys.json'))
ks=d.get('keys', d if isinstance(d,list) else [])
for k in ks:
    if not isinstance(k,dict): continue
    print(f"  key   alias={str(k.get('key_alias')):<16} rpm={k.get('rpm_limit')} tpm={k.get('tpm_limit')} "
          f"max_budget={k.get('max_budget')} spend={k.get('spend')} models={k.get('models')}")
t=json.load(open('/tmp/drill-out/teams.json'))
ts=t if isinstance(t,list) else t.get('teams',[])
for x in ts:
    if not isinstance(x,dict): continue
    print(f"  team  alias={str(x.get('team_alias')):<16} rpm={x.get('rpm_limit')} tpm={x.get('tpm_limit')} "
          f"max_budget={x.get('max_budget')} spend={x.get('spend')}")
    print(f"        team_id={x.get('team_id')}")
PY

TEAM=$(python3 -c "
import json
t=json.load(open('/tmp/drill-out/teams.json'))
ts=t if isinstance(t,list) else t.get('teams',[])
print(next((x['team_id'] for x in ts if isinstance(x,dict) and x.get('team_alias')=='llm-router-gateway-wide'),''))")
echo "  resolved team_id=$TEAM"

say "Phase 1 — provision a throwaway bystander key (deleted at the end)"
BY=$(curl -s -X POST "$BASE/key/generate" -H "Authorization: Bearer $MK" -H 'Content-Type: application/json' \
  -d "{\"key_alias\":\"drill-bystander\",\"team_id\":\"$TEAM\",\"models\":[\"hermes-fast\",\"hermes-balanced\",\"hermes-deep\"],\"max_budget\":1,\"budget_duration\":\"30d\",\"rpm_limit\":60}" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin).get("key",""))')
[ -n "$BY" ] || { echo "FATAL: bystander key not created"; exit 1; }
echo "  created drill-bystander (rpm_limit 60), token ${BY:0:6}…"

cleanup() {
  say "Cleanup — delete the throwaway key"
  curl -s -X POST "$BASE/key/delete" -H "Authorization: Bearer $MK" -H 'Content-Type: application/json' \
    -d "{\"keys\":[\"$BY\"]}" | head -c 300; echo
  curl -s -H "Authorization: Bearer $MK" "$BASE/key/list?return_full_object=true&size=100" \
    | python3 -c 'import json,sys
d=json.load(sys.stdin); ks=d.get("keys",[])
al=sorted(str(k.get("key_alias")) for k in ks if isinstance(k,dict))
print("  keys remaining:", al)
print("  drill-bystander gone:", "drill-bystander" not in al)'
}
trap cleanup EXIT

req() {  # req <token> <tag>
  curl -s -o "$OUT/body.$2" -w '%{http_code}' -m 90 -X POST "$BASE/v1/chat/completions" \
    -H "Authorization: Bearer $1" -H 'Content-Type: application/json' \
    -d '{"model":"hermes-fast","messages":[{"role":"user","content":"hi"}],"max_tokens":1}' \
    > "$OUT/code.$2" 2>/dev/null
}

say "Phase 2 — drive the canary key (rpm_limit 10) past its limit: 16 concurrent requests"
date -u +'  burst start %H:%M:%SZ'
for i in $(seq 1 16); do req "$CANARY" "c$i" & done

sleep 2
say "Phase 3 — AS-5.1: a DIFFERENT client, mid-breach, must keep serving"
req "$BY" "bystander"
echo "  bystander HTTP $(cat "$OUT/code.bystander")"
head -c 400 "$OUT/body.bystander"; echo

wait
date -u +'  burst end   %H:%M:%SZ'

say "Phase 4 — result of the burst"
python3 - <<'PY'
import collections, pathlib
codes = collections.Counter()
for p in sorted(pathlib.Path('/tmp/drill-out').glob('code.c*')):
    codes[p.read_text().strip()] += 1
for c, n in sorted(codes.items()):
    print(f"  HTTP {c}: {n}")
PY

say "Phase 5 — T055 / AS-5.2: is the refusal attributable to the breaching client?"
for f in "$OUT"/code.c*; do
  if [ "$(cat "$f")" = "429" ]; then
    echo "  --- one 429 body, verbatim ---"
    head -c 700 "${f/code./body.}"; echo
    break
  fi
done

say "Phase 6 — does the bystander's own limit remain intact after the breach?"
req "$BY" "bystander2"
echo "  bystander HTTP $(cat "$OUT/code.bystander2")"

say "Phase 7 — the canary key recovers when its window rolls"
sleep 62
req "$CANARY" "recover"
echo "  canary HTTP $(cat "$OUT/code.recover") after a 62s wait"
head -c 200 "$OUT/body.recover"; echo
