"""Score one candidate run: probe hits from the transcript, LLM traffic from the proxy log.

Overrides (overrides.json) record probes judged by hand. A bare true/false applies to every run
of a candidate; the spike's archived runs use that form. An object
{"pass": bool, "answer_sha256": "..."} applies only to the exact answer that was reviewed, so a
later run of the same candidate is scored on its own answer (spec 097, PR #318 review).
A keyword miss without a matching override prints a `review` line with the answer's digest.
"""
import collections, hashlib, json, re, sys


def _override(o, raw):
    """A bare bool, one digest-bound judgement, or a list of them (one per reviewed answer)."""
    if isinstance(o, bool):
        return o
    digest = hashlib.sha256(raw.encode()).hexdigest()
    for j in o if isinstance(o, list) else [o]:
        if isinstance(j, dict) and j.get("answer_sha256") == digest:
            return bool(j["pass"])
    return None


def score(cand):
    """[(probe, ok, answer, review_digest_or_None)] for every probe in dataset.json."""
    d = json.load(open("dataset.json"))
    tx = {r["id"]: r for r in map(json.loads, open(f"results/{cand}/transcript.jsonl")) if r["kind"] == "probe"}
    ov = json.load(open("overrides.json")).get(cand, {})
    out = []
    for p in d["probes"]:
        raw = tx.get(p["id"], {}).get("a", "")
        a = raw.lower()
        # "nut-free" / "uten nøtter" is compliance, not a violation
        neg = re.sub(r"(nut[- ]free|no nuts|without nuts|uten nøtter|nøt+e?fri\w*|lactose[- ]free|laktosefri\w*|uten melk)", "", a)
        ok = all(re.search(e, a) for e in p["expect"]) and not any(re.search(r"\b" + f, neg) for f in p["forbid"])
        review = None
        judged = _override(ov.get(p["id"]), raw) if p["id"] in ov else None
        if judged is not None:
            ok = judged
        elif not ok:
            review = hashlib.sha256(raw.encode()).hexdigest()
        out.append((p, ok, a, review))
    return out


def calls(cand):
    counts = collections.Counter()
    for r in map(json.loads, open("logs/calls.jsonl")):
        if r["run"].split("/")[0] != cand:
            continue
        kind = "embed" if "embed" in r["path"] else ("rerank" if "rerank" in r["path"] else "chat")
        if r["status"] == 404 and r["method"] == "GET":
            continue  # Hermes probing /props and /version at startup
        counts[(r["run"].split("/")[1], kind, r["status"])] += 1
    return counts


if __name__ == "__main__":
    cand = sys.argv[1]
    results = score(cand)
    for p, ok, a, review in results:
        print(f"{p['id']:3} {p['kind']:17} {'PASS' if ok else 'FAIL'}  {a[:110]!r}")
    print(f"recall: {sum(ok for _, ok, _, _ in results)}/{len(results)}")
    for p, _, _, review in results:
        if review:
            print(f"review {p['id']} sha256={review}  (keyword miss; judge by hand in overrides.json)")
    for k, v in sorted(calls(cand).items()):
        print("calls", *k, v)
