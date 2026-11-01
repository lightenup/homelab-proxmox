"""FR-021 gate verdict for a prod-render run (spec 097, research R-017).

Usage: python3 gate.py prod-render   (run.sh calls it after score.py)

Evaluates SC-001 to SC-005 from the run's own evidence and writes results/<cand>/gate.json with
the configuration fingerprint and the images the harness actually ran. Exits non-zero unless
every criterion passes. python/tests/guardrails/test_memory_harness_gate.py accepts a run only
if its gate.json says pass and carries the current fingerprint, so a matching fingerprint on a
failed run is not evidence (PR #318 review).

- SC-001: at least 14 of 16 probes, every volume probe, strictly above the best no-memory
  baseline (results/none*/score.txt). Amended 2026-11-01: a preference probe (one with
  `recall_expect`) counts as remembered when its preference is in the top 3 recall results
  (results/<cand>/recall.jsonl, hermes/recall_check.py), whatever the model then does with it.
  Whether the answer honoured it stays on record as `preference_answers`; p16 failed that in 4
  of 5 judged runs while recall returned the preference.
- SC-002: every update probe current, the negative probe "don't know".
- SC-003: the memory server's key made embed and rerank calls only, and at least one.
- SC-004: no egress attempt beyond the proxy in the compose log.
- SC-005: llmproxy/portability.py clients (run.sh) passed: 6/6 cross-client recalls across
  hermes, open-webui and claude-code, the server-stamped client tag, a read-only retain, a
  webhook and a bank-config change refused (results/<cand>/portability.json; missing fails).
- Images: every image in runs/<cand>/build/images.env (rendered from the PROD pins) is among
  the images compose ran (results/<cand>/images.txt).
A keyword miss that nobody judged by hand fails the gate.
"""
import collections, glob, hashlib, json, os, re, sys

from score import score

EGRESS = re.compile(r"huggingface|openai\.com|openrouter|anthropic\.com|Name or service not known|"
                    r"getaddrinfo|Temporary failure in name resolution", re.I)


def _env(path):
    return dict(line.strip().split("=", 1) for line in open(path) if "=" in line and not line.startswith("#"))


def recalled(probes, recall_lines):
    """The SC-001 outcome per probe: the scored answer, or for a preference probe a top-3 recall.
    Returns (probes with the effective verdict, {preference probe id: answer verdict})."""
    top3 = {}
    for line in recall_lines:
        try:
            r = json.loads(line)
        except ValueError:
            continue
        top3[r.get("probe")] = r.get("top3") is True
    effective, answers = [], {}
    for p, ok, answer, review in probes:
        if p.get("recall_expect"):
            answers[p["id"]] = ok
            ok, review = top3.get(p["id"], False), False
        effective.append((p, ok, answer, review))
    return effective, answers


def verdict(cand):
    out = f"results/{cand}"
    recall_path = f"{out}/recall.jsonl"
    probes, preference_answers = recalled(
        score(cand), open(recall_path) if os.path.exists(recall_path) else [])
    hits = sum(ok for _, ok, _, _ in probes)
    volume = [ok for p, ok, _, _ in probes if p["kind"].startswith("volume")]
    baselines = []
    for path in glob.glob("results/none*/score.txt"):
        m = re.search(r"^recall: (\d+)/", open(path).read(), re.M)
        if m:
            baselines.append(int(m.group(1)))
    unjudged = [p["id"] for p, _, _, review in probes if review]
    sc001 = {
        "score": f"{hits}/{len(probes)}",
        "volume": f"{sum(volume)}/{len(volume)}",
        "baseline_max": max(baselines) if baselines else None,
        "unjudged": unjudged,
        "preference_answers": preference_answers,
    }
    sc001["pass"] = (hits >= 14 and all(volume) and bool(baselines) and hits > max(baselines)
                     and not unjudged)

    updates = {p["id"]: ok for p, ok, _, _ in probes if p["kind"].startswith("update")}
    negative = {p["id"]: ok for p, ok, _, _ in probes if p["kind"] == "negative"}
    sc002 = {"update": updates, "negative": negative,
             "pass": bool(updates) and all(updates.values()) and bool(negative) and all(negative.values())}

    key = _env(f"runs/{cand}/secret.env")["llm_router_client_memory_key"]
    memory_caller = hashlib.sha256(key.encode()).hexdigest()[:8]
    memory_calls = collections.Counter()
    for r in map(json.loads, open("logs/calls.jsonl")):
        if r["run"].split("/")[0] == cand and r.get("caller") == memory_caller:
            kind = "embed" if "embed" in r["path"] else ("rerank" if "rerank" in r["path"] else "chat")
            memory_calls[kind] += 1
    sc003 = {"memory_key_calls": dict(memory_calls),
             "pass": memory_calls["chat"] == 0 and memory_calls["embed"] > 0}

    egress = [line.strip()[:200] for line in open(f"{out}/compose.log") if EGRESS.search(line)]
    sc004 = {"egress_lines": len(egress), "examples": egress[:3], "pass": not egress}

    expected = sorted(_env(f"runs/{cand}/build/images.env").values())
    ran = sorted({line.strip() for line in open(f"{out}/images.txt") if line.strip()})
    images = {"expected": expected, "ran": ran, "pass": set(expected) <= set(ran)}

    porta = f"{out}/portability.json"
    sc005 = json.load(open(porta)) if os.path.exists(porta) else {"missing": porta}
    sc005["pass"] = sc005.get("pass") is True

    fingerprint = open(f"runs/{cand}/fingerprint.txt").readline().strip()
    result = {"fingerprint": fingerprint, "images": images,
              "SC-001": sc001, "SC-002": sc002, "SC-003": sc003, "SC-004": sc004, "SC-005": sc005}
    result["pass"] = all(v["pass"] for k, v in result.items() if isinstance(v, dict))
    return result


if __name__ == "__main__":
    cand = sys.argv[1]
    result = verdict(cand)
    with open(f"results/{cand}/gate.json", "w") as f:
        json.dump(result, f, indent=1, ensure_ascii=False)
        f.write("\n")
    for k, v in result.items():
        if isinstance(v, dict):
            print(f"gate {k}: {'PASS' if v['pass'] else 'FAIL'}")
    print(f"gate: {'PASS' if result['pass'] else 'FAIL'} ({result['fingerprint'][:12]})")
    sys.exit(0 if result["pass"] else 1)
