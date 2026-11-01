"""SC-001 retrieval leg for preference probes (spec 097, amended 2026-11-01): run inside the hermes
container after the probes. For each probe with `recall_expect`, recall the probe question the way
the plugin does (its own config: URL, key, bank, types, budget) and report whether a top-3 result
matches the pattern. A preference probe tests memory, not whether the model obeys what it is
given; gate.py counts it as remembered when the preference is in the top 3."""
import json, re, sys, urllib.request

d = json.load(open(sys.argv[1]))
c = json.load(open("/opt/data/hindsight/config.json"))
for p in d["probes"]:
    if not p.get("recall_expect"):
        continue
    body = {"query": p["q"], "types": c.get("recall_types", ["world"]), "budget": c.get("recall_budget", "mid"),
            "max_tokens": 2000}
    req = urllib.request.Request(f"{c['api_url']}/v1/default/banks/{c['bank_id']}/memories/recall",
                                 json.dumps(body).encode(),
                                 {"Authorization": f"Bearer {c['api_key']}", "Content-Type": "application/json"})
    try:
        texts = [r.get("text") or "" for r in json.load(urllib.request.urlopen(req, timeout=60)).get("results", [])]
    except Exception as e:  # recorded, and gate.py treats a missing hit as a miss
        print(json.dumps({"probe": p["id"], "error": type(e).__name__}))
        continue
    ranks = [i + 1 for i, t in enumerate(texts) if re.search(p["recall_expect"], t, re.I)]
    print(json.dumps({"probe": p["id"], "rank": ranks[0] if ranks else None, "top3": bool(ranks) and ranks[0] <= 3}))
