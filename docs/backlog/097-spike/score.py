"""Score one candidate run: probe hits from the transcript, LLM traffic from the proxy log."""
import collections, json, re, sys
cand = sys.argv[1]
d = json.load(open("dataset.json"))
tx = {r["id"]: r for r in map(json.loads, open(f"results/{cand}/transcript.jsonl")) if r["kind"] == "probe"}
hits = 0
ov = json.load(open("overrides.json")).get(cand, {})
for p in d["probes"]:
    a = tx.get(p["id"], {}).get("a", "").lower()
    # "nut-free" / "uten nøtter" is compliance, not a violation
    neg = re.sub(r"(nut[- ]free|no nuts|without nuts|uten nøtter|nøt+e?fri\w*|lactose[- ]free|laktosefri\w*|uten melk)", "", a)
    ok = all(re.search(e, a) for e in p["expect"]) and not any(re.search(r"\b" + f, neg) for f in p["forbid"])
    if p["id"] in ov:
        ok = ov[p["id"]]
    hits += ok
    print(f"{p['id']:3} {p['kind']:17} {'PASS' if ok else 'FAIL'}  {a[:110]!r}")
print(f"recall: {hits}/{len(d['probes'])}")
calls = collections.Counter()
for r in map(json.loads, open("logs/calls.jsonl")):
    if r["run"].split("/")[0] != cand:
        continue
    kind = "embed" if "embed" in r["path"] else ("rerank" if "rerank" in r["path"] else "chat")
    if r["status"] == 404 and r["method"] == "GET":
        continue  # Hermes probing /props and /version at startup
    calls[(r["run"].split("/")[1], kind, r["status"])] += 1
for k, v in sorted(calls.items()):
    print("calls", *k, v)
