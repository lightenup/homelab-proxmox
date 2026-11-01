"""SC-001's retrieval leg for preference probes (spec 097, amended 2026-11-01; PR #340 review).

Usage: python3 recall_from_injected.py <cand>   (run.sh, after the probes) > results/<cand>/recall.jsonl

For each probe with `recall_expect`, takes the recall block the agent injected into that probe's
first chat request (logs/injected.jsonl, written by llmproxy/logproxy.py) and reports the rank of
the first recalled item matching the pattern. It measures what the model was given before it
answered, so the probes' own answers, stored afterwards, cannot count. A block Hermes cut short
(hook-output spill) is reported as truncated, and only its visible items are ranked.
"""
import json
import re
import sys


def items(context):
    """The recalled items of an injected block, in rank order (lines starting "- ")."""
    body = context.split("\n\n- ", 1)
    if len(body) < 2:
        return []
    return body[1].split("\n- ")


def rank(context, pattern):
    for i, text in enumerate(items(context)):
        if re.search(pattern, text, re.I):
            return i + 1
    return None


def main(cand, dataset="dataset.json", log="logs/injected.jsonl"):
    probes = [p for p in json.load(open(dataset))["probes"] if p.get("recall_expect")]
    first = {}
    try:
        for line in open(log):
            r = json.loads(line)
            if r.get("run") == f"{cand}/probes":
                first.setdefault(r["q"], r["context"])
    except OSError:
        pass
    for p in probes:
        context = first.get(p["q"])
        if context is None:
            print(json.dumps({"probe": p["id"], "error": "no injected recall"}))
            continue
        r = rank(context, p["recall_expect"])
        print(json.dumps({"probe": p["id"], "rank": r, "top3": r is not None and r <= 3,
                          "truncated": "output truncated" in context, "source": "injected"}))


if __name__ == "__main__":
    main(sys.argv[1])
