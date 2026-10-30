"""Drive dataset.json through the Hermes gateway's API server, the way Open WebUI does.

POST /v1/chat/completions with the session's full history and no session header, one request
per turn. Probes are single-message conversations, so only long-term memory can answer them.
Runs inside the llmproxy container (on the internal network); prints one JSON line per turn.
"""
import json
import sys
import time
import urllib.request

API = "http://hermes:8642/v1/chat/completions"
cand = sys.argv[1]
d = json.load(open("/data/dataset.json"))


def phase(p):
    with open("/logs/RUN.phase", "w") as f:
        f.write(p)


def ask(messages):
    body = json.dumps({"model": "hermes-agent", "messages": messages, "stream": False}).encode()
    req = urllib.request.Request(API, data=body, method="POST", headers={
        "Content-Type": "application/json", "Authorization": "Bearer spike-api-key-not-secret-0001"})
    try:
        r = json.load(urllib.request.urlopen(req, timeout=1800))
        return r["choices"][0]["message"]["content"] or ""
    except Exception as e:  # keep going; a failed turn is a finding
        return f"ERROR {e}"


def emit(kind, id_, q, a, secs):
    print(json.dumps({"kind": kind, "id": id_, "q": q, "a": a, "secs": secs}, ensure_ascii=False), flush=True)
    print(f"[{kind} {id_}] {secs}s", file=sys.stderr, flush=True)


# wait for the API server (gateway start takes a while)
for _ in range(60):
    try:
        urllib.request.urlopen("http://hermes:8642/health", timeout=3); break
    except Exception:
        time.sleep(5)
phase("sessions")
for s in d["sessions"]:
    history = []
    for t in s["turns"]:
        history.append({"role": "user", "content": t})
        start = time.time()
        a = ask(history)
        history.append({"role": "assistant", "content": a})
        emit("turn", f"{cand}-{s['id']}", t, a, int(time.time() - start))
    time.sleep(5)  # gap between conversations, as between real chats
phase("settle")
time.sleep(60)  # session-end hooks and async writes
phase("probes")
for p in d["probes"]:
    start = time.time()
    emit("probe", p["id"], p["q"], ask([{"role": "user", "content": p["q"]}]), int(time.time() - start))
