#!/usr/bin/env bash
# T054 / T055 — RATE-LIMIT breach drill, both levels of FR-010.
#
# T054 was reframed: the spend half of FR-010 is inert (local tiers carry no pricing, so
# spend is exactly 0.0 against any cap), which leaves rate limiting as the only
# runaway-client guard that can actually be exercised.
#
# RUN IT ON THE GATEWAY LXC — it reads the master key from the compose file and the canary
# key from canary.sh, both of which are root-only and local to that host:
#
#   ssh root@192.168.1.112 'pct push 109 /tmp/drill.sh /tmp/drill.sh --perms 0700 \
#     && pct exec 109 -- bash /tmp/drill.sh'
#
# WHAT IT MUTATES, and it cleans all of it up on exit including on failure (trap):
#   - one throwaway key on the real team  ("drill-bystander")
#   - one throwaway team                  ("drill-team")   + two keys on it
# The live clients' keys and the real gateway-wide team are never modified. The breaching
# client in phase 2 is `canary`, whose rpm_limit of 10 makes the breach cheap: 16 requests,
# ~3s, tiny prompts at max_tokens 1.
#
# The team-level phases use a throwaway team with a deliberately tiny limit rather than
# driving the real one. Breaching the real gateway cap would mean ~65 real inference
# requests; the mechanism is identical at rpm=4 and costs four.
#
# Recorded result: specs/064-llm-router/doctor-fault-injection.md § Row 11.
set -uo pipefail

BASE=http://127.0.0.1:4000
OUT=/tmp/drill-out; rm -rf "$OUT"; mkdir -p "$OUT"

MK=$(grep -oE 'LITELLM_MASTER_KEY: *"[^"]+"' /opt/llm-router/docker-compose.yml | sed -E 's/.*"(.*)"/\1/')
CANARY=$(grep -oE 'Bearer sk-[A-Za-z0-9_-]+' /opt/llm-router/canary.sh | head -1 | awk '{print $2}')
[ -n "$MK" ] && [ -n "$CANARY" ] || { echo "FATAL: could not read keys"; exit 1; }

say() { printf '\n== %s ==\n' "$*"; }
api() { curl -s -X "$1" "$BASE$2" -H "Authorization: Bearer $MK" -H 'Content-Type: application/json' ${3:+-d "$3"}; }

req() {  # req <token> <tag>
  curl -s -o "$OUT/body.$2" -w '%{http_code}' -m 90 -X POST "$BASE/v1/chat/completions" \
    -H "Authorization: Bearer $1" -H 'Content-Type: application/json' \
    -d '{"model":"hermes-fast","messages":[{"role":"user","content":"hi"}],"max_tokens":1}' \
    > "$OUT/code.$2" 2>/dev/null
}

say "Phase 0 — live state: are the declared limits actually ON the key and the team?"
api GET "/key/list?return_full_object=true&size=100" > "$OUT/keys.json"
api GET "/team/list" > "$OUT/teams.json"
python3 - <<'PY'
import json
for k in json.load(open('/tmp/drill-out/keys.json')).get('keys', []):
    if isinstance(k, dict):
        print(f"  key   alias={str(k.get('key_alias')):<16} rpm={k.get('rpm_limit')} "
              f"max_budget={k.get('max_budget')} spend={k.get('spend')}")
t = json.load(open('/tmp/drill-out/teams.json'))
for x in (t if isinstance(t, list) else t.get('teams', [])):
    if isinstance(x, dict):
        print(f"  team  alias={str(x.get('team_alias')):<16} rpm={x.get('rpm_limit')} "
              f"max_budget={x.get('max_budget')} spend={x.get('spend')}")
PY

TEAM=$(python3 -c "
import json
t=json.load(open('/tmp/drill-out/teams.json'))
ts=t if isinstance(t,list) else t.get('teams',[])
print(next((x['team_id'] for x in ts if isinstance(x,dict) and x.get('team_alias')=='llm-router-gateway-wide'),''))")

say "Phase 1 — FR-010 level 2 must be LIVE, not merely declared (backlog 071)"
GW_RPM=$(python3 -c "
import json
t=json.load(open('/tmp/drill-out/teams.json'))
ts=t if isinstance(t,list) else t.get('teams',[])
x=next((x for x in ts if isinstance(x,dict) and x.get('team_alias')=='llm-router-gateway-wide'),{})
print(x.get('rpm_limit'))")
if [ "$GW_RPM" = "None" ] || [ -z "$GW_RPM" ]; then
  echo "  FAIL  gateway-wide team carries rpm=None — the second level of FR-010 is absent"
else
  echo "  PASS  gateway-wide team carries rpm_limit=$GW_RPM"
fi

say "Phase 2 — provision a throwaway bystander key on the real team"
BY=$(api POST /key/generate "{\"key_alias\":\"drill-bystander\",\"team_id\":\"$TEAM\",\"models\":[\"hermes-fast\",\"hermes-balanced\",\"hermes-deep\"],\"max_budget\":1,\"budget_duration\":\"30d\",\"rpm_limit\":60}" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin).get("key",""))')
[ -n "$BY" ] || { echo "FATAL: bystander key not created"; exit 1; }
echo "  created drill-bystander (rpm_limit 60), token ${BY:0:6}…"

DTEAM=""; DA=""; DB=""
cleanup() {
  say "Cleanup"
  [ -n "$BY" ] && api POST /key/delete "{\"keys\":[\"$BY\"]}" >/dev/null
  for k in $DA $DB; do api POST /key/delete "{\"keys\":[\"$k\"]}" >/dev/null; done
  [ -n "$DTEAM" ] && api POST /team/delete "{\"team_ids\":[\"$DTEAM\"]}" >/dev/null
  api GET "/key/list?return_full_object=true&size=100" | python3 -c 'import json,sys
al=sorted(str(k.get("key_alias")) for k in json.load(sys.stdin).get("keys",[]) if isinstance(k,dict))
print("  keys remaining:", al)
print("  throwaways gone:", not any(a.startswith("drill-") for a in al))'
  api GET "/team/list" | python3 -c 'import json,sys
t=json.load(sys.stdin); ts=t if isinstance(t,list) else t.get("teams",[])
al=sorted(str(x.get("team_alias")) for x in ts if isinstance(x,dict))
print("  teams remaining:", al)'
}
trap cleanup EXIT

say "Phase 3 — LEVEL 1: drive the canary key (rpm_limit 10) past its own limit"
date -u +'  burst start %H:%M:%SZ'
for i in $(seq 1 16); do req "$CANARY" "c$i" & done
sleep 2
say "Phase 4 — AS-5.1: a DIFFERENT client, mid-breach, must keep serving"
req "$BY" "bystander"
echo "  bystander HTTP $(cat "$OUT/code.bystander")"
wait
date -u +'  burst end   %H:%M:%SZ'

python3 - <<'PY'
import collections, pathlib
c = collections.Counter(p.read_text().strip() for p in pathlib.Path('/tmp/drill-out').glob('code.c*'))
for k, n in sorted(c.items()): print(f"  HTTP {k}: {n}")
PY

say "Phase 5 — T055 / AS-5.2: is the per-key refusal attributable?"
for f in "$OUT"/code.c*; do
  [ "$(cat "$f")" = "429" ] && { head -c 500 "${f/code./body.}"; echo; break; }
done

say "Phase 6 — LEVEL 2: two INDIVIDUALLY COMPLIANT clients breaching a team cap"
echo "  throwaway team rpm_limit=4, two keys at rpm_limit=3 each; each key sends 3."
echo "  Neither key exceeds its own limit. Together they are 6 against a cap of 4."
DTEAM=$(api POST /team/new '{"team_alias":"drill-team","max_budget":1,"budget_duration":"30d","rpm_limit":4}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin).get("team_id",""))')
[ -n "$DTEAM" ] || { echo "  FATAL: throwaway team not created"; exit 1; }
DA=$(api POST /key/generate "{\"key_alias\":\"drill-a\",\"team_id\":\"$DTEAM\",\"models\":[\"hermes-fast\"],\"rpm_limit\":3}" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("key",""))')
DB=$(api POST /key/generate "{\"key_alias\":\"drill-b\",\"team_id\":\"$DTEAM\",\"models\":[\"hermes-fast\"],\"rpm_limit\":3}" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("key",""))')
[ -n "$DA" ] && [ -n "$DB" ] || { echo "  FATAL: throwaway keys not created"; exit 1; }

for i in 1 2 3; do req "$DA" "a$i" & req "$DB" "b$i" & done
wait
python3 - <<'PY'
import collections, pathlib
c = collections.Counter()
for p in pathlib.Path('/tmp/drill-out').glob('code.[ab][0-9]*'):
    c[p.read_text().strip()] += 1
for k, n in sorted(c.items()): print(f"  HTTP {k}: {n}")
PY

say "Phase 7 — FR-010: is a TEAM refusal distinguishable from a KEY refusal?"
for f in "$OUT"/code.[ab][0-9]*; do
  [ "$(cat "$f")" = "429" ] && { echo "  --- team-level 429 body ---"; head -c 500 "${f/code./body.}"; echo; break; }
done
echo "  --- compare with the key-level 429 above: the two must not read the same ---"

say "Phase 8 — the window rolls and the canary key recovers"
sleep 62
req "$CANARY" "recover"
echo "  canary HTTP $(cat "$OUT/code.recover") after a 62s wait"
