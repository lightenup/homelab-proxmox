"""Hindsight portability tests, run inside llmproxy (internal network, stdlib only).

usage: portability.py write|mcp|export|import|recall <bank>
       portability.py clients <bank> --clients hermes,open-webui,claude-code [--secrets PATH]
       portability.py durability <bank> [--secrets PATH]
Client A = REST, client B = MCP over Streamable HTTP. HSK = Hindsight API key (env).

`clients` is the FR-021 gate's SC-005 leg (spec 097 T045, research R-017): each client writes a
turn in the contracts/turn-format.md format with its own key from runs/prod-render/secret.env
(mounted at /run/harness/secret.env by compose.prod-render.yml), and every other client must
recall it (6/6 for three clients). It also checks the server-stamped client tag (a forged one
replaced), a read-only retain refused with 403 (the harness-only `claude-code-ro` client that
render-prod.sh adds), and a webhook creation and a bank-config change refused with 403. Writes
/logs/porta/clients.json, which run.sh archives and gate.py reads as SC-005.
`durability` is the T071 leg (research R-012): per client, in that client's retain shape, a turn
retired with invalidate_memory and a turn edited with update_memory must stay so after the
conversation gets another turn, and a Hermes full-session resend and a batch repeating a turn
must add nothing. Writes /logs/porta/durability.json, which gate.py reads as T071.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

BASE = "http://hindsight:8888"
KEY = os.environ.get("HSK", "")
OUT = "/logs/porta"
os.makedirs(OUT, exist_ok=True)


def http(method, path, body=None, key=KEY, headers=None, raw=False, timeout=300):
    h = {"Content-Type": "application/json"} if body is not None and not raw else {}
    if key:
        h["Authorization"] = f"Bearer {key}"
    h.update(headers or {})
    data = body if raw else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=h)
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        return r.status, r.read(), r.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers


def log(*a):
    print(*a, flush=True)


FACTS = [
    "My sister Ingrid lives in Tromsø and works as a marine biologist.",
    "Hunden min heter Tinde. Hun er en border collie.",
    "I'm allergic to nuts, so never suggest recipes with nuts.",
    "Vi bestemte at den nattlige backupen skal kjøre klokka 03:00 i stedet for midnatt.",
    "The winter tyres are stored at Dekkhotellet in Leangen.",
    "Jeg spiller bass i et coverband som heter Fjordfunk. Vi øver hver onsdag kl 19.",
]


def recall(bank, q, key=KEY):
    s, b, _ = http("POST", f"/v1/default/banks/{bank}/memories/recall",
                   {"query": q, "budget": "low", "max_tokens": 1024}, key=key)
    if s != 200:
        return s, []
    res = json.loads(b).get("results", [])
    return s, [(r.get("text") or "")[:120] for r in res[:3]]


def write(bank):
    s, b, _ = http("PUT", f"/v1/default/banks/{bank}", {})
    log("PUT bank", s)
    items = [{"content": f, "context": "owner chat", "tags": ["client:hermes-agent"],
              "metadata": {"source_client": "hermes-agent"}, "document_id": f"a-{i}"}
             for i, f in enumerate(FACTS)]
    t = time.time()
    s, b, _ = http("POST", f"/v1/default/banks/{bank}/memories", {"items": items, "async": False})
    log("REST retain (client A)", s, f"{time.time()-t:.1f}s", b[:200])
    s, b, _ = http("GET", f"/v1/default/banks/{bank}/memories/list?limit=20")
    units = json.loads(b).get("items", []) if s == 200 else []
    log("list", s, "units:", len(units))
    for u in units[:3]:
        log("  unit keys:", sorted(u.keys()))
        log("  unit:", {k: u.get(k) for k in ("fact_type", "tags", "document_id", "context", "metadata")})
    s, b, _ = http("GET", f"/v1/default/banks/{bank}/documents/a-0")
    d = json.loads(b) if s == 200 else {}
    log("document a-0", s, {k: d.get(k) for k in ("tags", "metadata", "document_metadata", "retain_params")})
    s, b, _ = http("GET", f"/v1/default/banks/{bank}/tags")
    log("tags", s, b[:200])
    s, _, _ = http("POST", f"/v1/default/banks/{bank}/memories/recall", {"query": "x"}, key=None)
    log("REST recall without key ->", s)
    s, _, _ = http("POST", f"/v1/default/banks/{bank}/memories/recall", {"query": "x"}, key="wrong-key")
    log("REST recall with wrong key ->", s)


class MCP:
    def __init__(self, bank, key=KEY):
        self.url = f"/mcp/{bank}/"
        self.key = key
        self.sid = None
        self.n = 0

    def call(self, method, params=None, notify=False):
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        if not notify:
            self.n += 1
            msg["id"] = self.n
        h = {"Accept": "application/json, text/event-stream"}
        if self.sid:
            h["Mcp-Session-Id"] = self.sid
        s, b, hd = http("POST", self.url, msg, key=self.key, headers=h)
        if hd and hd.get("Mcp-Session-Id"):
            self.sid = hd.get("Mcp-Session-Id")
        text = b.decode(errors="replace")
        if "text/event-stream" in (hd.get("Content-Type", "") if hd else ""):
            datas = [l[5:].strip() for l in text.splitlines() if l.startswith("data:")]
            text = datas[-1] if datas else ""
        try:
            return s, json.loads(text) if text else None
        except ValueError:
            return s, text[:300]


def mcp(bank):
    s, _ = MCP(bank, key=None).call("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                                   "clientInfo": {"name": "client-b", "version": "0"}})
    log("MCP initialize without key ->", s)
    m = MCP(bank)
    s, r = m.call("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                 "clientInfo": {"name": "client-b", "version": "0"}})
    log("MCP initialize ->", s, "server:", (r or {}).get("result", {}).get("serverInfo"), "session:", bool(m.sid))
    m.call("notifications/initialized", notify=True)
    s, r = m.call("tools/list", {})
    tools = (r or {}).get("result", {}).get("tools", [])
    log("MCP tools/list ->", s, len(tools), "tools:", [t["name"] for t in tools])
    json.dump(tools, open(f"{OUT}/mcp-tools.json", "w"), indent=1)
    rec = next((t for t in tools if t["name"] in ("recall", "hindsight_recall")), None)
    ret = next((t for t in tools if t["name"] in ("retain", "hindsight_retain")), None)
    log("recall schema:", json.dumps(rec.get("inputSchema", {}).get("properties", {}))[:300] if rec else None)
    log("retain schema:", json.dumps(ret.get("inputSchema", {}).get("properties", {}))[:400] if ret else None)
    for q in ["Hva jobber søsteren min med?",            # NO query, EN fact
              "What is my dog's name and breed?",         # EN query, NO fact
              "Which food allergy do I have?"]:
        s, r = m.call("tools/call", {"name": rec["name"], "arguments": {"query": q}})
        content = (r or {}).get("result", {}).get("content", [])
        txt = " ".join(c.get("text", "") for c in content)[:300]
        log(f"MCP recall {q!r} ->", s, txt.replace("\n", " "))
    if ret:
        args = {"content": "Client B (Claude Code) note: the owner's favourite ramen shop is Ramen Tori in Trondheim."}
        props = ret.get("inputSchema", {}).get("properties", {})
        if "tags" in props:
            args["tags"] = ["client:claude-code"]
        if "context" in props:
            args["context"] = "claude-code"
        s, r = m.call("tools/call", {"name": ret["name"], "arguments": args})
        log("MCP retain (client B) ->", s, json.dumps(r)[:300])
        time.sleep(5)
        log("REST recall (client A) of B's fact ->", *recall(bank, "Where is my favourite ramen shop?"))


def wait_op(bank, op, key=KEY):
    for _ in range(120):
        s, b, _ = http("GET", f"/v1/default/banks/{bank}/operations/{op}", key=key)
        d = json.loads(b)
        if d.get("status") in ("completed", "failed", "cancelled"):
            return d
        time.sleep(2)
    return d


def export(bank):
    t = time.time()
    s, b, _ = http("POST", f"/v1/default/banks/{bank}/document-transfer/export")
    op = json.loads(b).get("operation_id")
    d = wait_op(bank, op)
    md = d.get("result_metadata") or {}
    log("export ->", s, d.get("status"), {k: md.get(k) for k in ("byte_size", "filename", "storage_key")},
        f"{time.time()-t:.1f}s")
    s, z, _ = http("GET", f"/v1/default/files/download/{md['storage_key']}")
    open(f"{OUT}/export.zip", "wb").write(z)
    log("download ->", s, len(z), "bytes")


def import_(bank):
    http("PUT", f"/v1/default/banks/{bank}", {})
    z = open(f"{OUT}/export.zip", "rb").read()
    bd = uuid.uuid4().hex
    body = (f"--{bd}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"export.zip\"\r\n"
            f"Content-Type: application/zip\r\n\r\n").encode() + z + f"\r\n--{bd}--\r\n".encode()
    t = time.time()
    s, b, _ = http("POST", f"/v1/default/banks/{bank}/document-transfer", body, raw=True,
                   headers={"Content-Type": f"multipart/form-data; boundary={bd}"})
    log("import submit ->", s, b[:200])
    d = wait_op(bank, json.loads(b).get("operation_id"))
    log("import ->", d.get("status"), d.get("result_metadata"), f"{time.time()-t:.1f}s")


def recall_all(bank):
    for q in ["Where does my sister live?", "Hva heter hunden min?", "Når kjører backupen?",
              "Where are my winter tyres?", "Hva heter bandet mitt?", "Where is my favourite ramen shop?"]:
        log(f"recall {q!r} ->", *recall(bank, q))
    s, b, _ = http("GET", f"/v1/default/banks/{bank}/memories/list?limit=50")
    items = json.loads(b).get("items", []) if s == 200 else []
    log("units in bank:", len(items), "tags seen:", sorted({t for u in items for t in (u.get("tags") or [])}))


# --- clients: SC-005 across the three adapters (spec 097 T045) ---------------------------

# One turn per client, each about its own topic, in the shape that client's adapter stores:
# the plugin's session document for Hermes, owui-<chat_id> for Open WebUI (the filter),
# cc-<session_id> for Claude Code (the hook). The Open WebUI leg also sends a forged client tag.
TURNS = {
    "hermes": dict(doc="porta-hermes-session", context="conversation between Hermes Agent and the User",
                   say="My test parrot is called Kvitre-097.", reply="Noted, your test parrot is Kvitre-097.",
                   ask="What is my test parrot called?", expect="kvitre-097", tags=["client:hermes"]),
    "open-webui": dict(doc="owui-porta-chat", context="conversation between Open WebUI and the User",
                       say="My test sister lives in Probe-by.", reply="Got it, your test sister lives in Probe-by.",
                       ask="Where does my test sister live?", expect="probe-by", tags=["client:hermes"]),
    "claude-code": dict(doc="cc-porta-session", context="conversation between Claude Code and the User",
                        say="My test boat is called Probe-båt.", reply="Understood, your test boat is Probe-båt.",
                        ask="What is my test boat called?", expect="probe-båt", tags=[]),
}
READONLY = "claude-code-ro"   # harness-only client with scope readonly (render-prod.sh)


def key_var(client):
    return {"admin": "memory_admin_key", READONLY: "memory_client_claude_code_readonly_key"}.get(
        client, "memory_client_" + client.replace("-", "_") + "_key")


def turn(client, spec):
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    messages = [{"role": "user", "content": f"User: {spec['say']}", "timestamp": now},
                {"role": "assistant", "content": f"Assistant: {spec['reply']}", "timestamp": now}]
    return {"items": [{"content": json.dumps(messages, ensure_ascii=False), "document_id": spec["doc"],
                       "update_mode": "append", "context": spec["context"],
                       "tags": [f"session:{spec['doc']}"] + spec["tags"],
                       "metadata": {"retained_at": now, "turn_index": "1", "platform": client}}],
            "async": True}


def recall_texts(bank, query, key):
    s, b, _ = http("POST", f"/v1/default/banks/{bank}/memories/recall",
                   {"query": query, "types": ["world"], "budget": "mid", "max_tokens": 2000}, key=key)
    return s, [(r.get("text") or "") for r in (json.loads(b).get("results", []) if s == 200 else [])]


def clients(bank, names, secrets_path, deadline_s=180):
    keys = dict(line.strip().split("=", 1) for line in open(secrets_path) if "=" in line)
    key = {c: keys[key_var(c)] for c in [*names, READONLY, "control-plane", "admin"]}
    s, _, _ = http("PUT", f"/v1/default/banks/{bank}", {"name": bank}, key=key["admin"])
    log("create bank", bank, "->", s)
    retained = {}
    for c in names:
        retained[c], b, _ = http("POST", f"/v1/default/banks/{bank}/memories", turn(c, TURNS[c]), key=key[c])
        log(f"retain {c} ->", retained[c], b[:120])

    cross = {f"{w}->{r}": False for w in names for r in names if r != w}
    end = time.time() + deadline_s
    while not all(cross.values()) and time.time() < end:
        for pair in [p for p, ok in cross.items() if not ok]:
            writer, reader = pair.split("->")
            _, texts = recall_texts(bank, TURNS[writer]["ask"], key[reader])
            cross[pair] = any(TURNS[writer]["expect"] in t.casefold() for t in texts)
        if not all(cross.values()):
            time.sleep(5)
    for pair, ok in cross.items():
        log(f"recall {pair}:", "found" if ok else "MISSING")

    s, b, _ = http("GET", f"/v1/default/banks/{bank}/memories/list?limit=200", key=key["admin"])
    units = json.loads(b).get("items", []) if s == 200 else []
    # One document per turn (T071): a conversation's units sit in <doc>--<hash> documents.
    stamped = {c: sorted({t for u in units if (u.get("document_id") or "").startswith(TURNS[c]["doc"] + "--")
                          for t in (u.get("tags") or []) if t.startswith("client:")}) for c in names}
    log("client tags per writer:", stamped)
    tags_ok = all(stamped[c] == [f"client:{c}"] for c in names)

    readonly_retain, _, _ = http("POST", f"/v1/default/banks/{bank}/memories",
                                 turn(READONLY, TURNS["claude-code"]), key=key[READONLY])
    readonly_recall, _ = recall_texts(bank, TURNS["claude-code"]["ask"], key[READONLY])
    log("read-only retain ->", readonly_retain, "recall ->", readonly_recall)
    webhook = {c: http("POST", f"/v1/default/banks/{bank}/webhooks", {"url": "https://example.com/hook"},
                       key=k)[0] for c, k in key.items()}
    config = {c: http("PATCH", f"/v1/default/banks/{bank}/config",
                      {"updates": {"retain_extraction_mode": "chunks"}}, key=k)[0]
              for c, k in key.items() if c != "admin"}   # admin may change bank config
    log("webhook create ->", webhook)
    log("bank config change ->", config)

    found = sum(cross.values())
    result = {
        "clients": names, "bank": bank, "score": f"{found}/{len(cross)}", "cross_recall": cross,
        "retain_status": retained, "client_tags": stamped, "forged_tag_replaced": tags_ok,
        "readonly_retain_status": readonly_retain, "readonly_recall_status": readonly_recall,
        "webhook_status": webhook, "bank_config_status": config,
    }
    result["pass"] = (found == len(cross) and len(names) == 3 and all(v == 200 for v in retained.values())
                      and tags_ok and readonly_retain == 403 and readonly_recall == 200
                      and all(v == 403 for v in webhook.values()) and all(v == 403 for v in config.values()))
    with open(f"{OUT}/clients.json", "w") as f:
        json.dump(result, f, indent=1, ensure_ascii=False)
        f.write("\n")
    log(f"SC-005: {result['score']} cross-client recalls, {'PASS' if result['pass'] else 'FAIL'}")
    return result


# --- durability: one document per turn (spec 097 T071, research R-012) ------------------------


def conversation(session, pairs, update_mode="append", doc=None, start=0):
    """One retain item in the turn format: `pairs` of (user, assistant) text. Turn n of the
    conversation has a fixed timestamp, as a real client's message keeps its time when resent."""
    messages = []
    for i, (user, reply) in enumerate(pairs, start):
        ts = f"2026-11-01T12:{i:02d}:00+01:00"
        messages += [{"role": "user", "content": f"User: {user}", "timestamp": ts},
                     {"role": "assistant", "content": f"Assistant: {reply}", "timestamp": ts}]
    item = {"content": json.dumps(messages, ensure_ascii=False), "document_id": doc or session,
            "context": "durability check", "tags": [f"session:{session}"]}
    if update_mode:
        item["update_mode"] = update_mode
    return item


def live_units(bank, key, marker):
    s, b, _ = http("GET", f"/v1/default/banks/{bank}/memories/list?type=world&limit=200&q={marker}", key=key)
    return [u for u in (json.loads(b).get("items", []) if s == 200 else []) if marker in (u.get("text") or "")]


def settle(bank, key, ops):
    for op in ops:
        if op:
            wait_op(bank, op, key=key)
    time.sleep(3)


def retain_items(bank, key, items):
    s, b, _ = http("POST", f"/v1/default/banks/{bank}/memories", {"items": items, "async": True}, key=key)
    return s, (json.loads(b).get("operation_id") if s == 200 else None)


def durability_case(bank, client, key, keys_admin):
    run = uuid.uuid4().hex[:8]
    session = f"dur-{client}-{run}"
    t1, t2, t3 = (f"DUR{n}-{run}" for n in (1, 2, 3))
    pairs = [(f"Note {t1}: the shed key is under the blue pot.", "Noted."),
             (f"Note {t2}: the boat is moored at pier 4.", "Noted."),
             (f"Note {t3}: the bins go out on Tuesday.", "Noted.")]
    # The shape each adapter sends: the Hermes plugin one item with the delta turns, the Open
    # WebUI filter and the Claude Code hook one item per turn.
    if client == "hermes":
        first = [conversation(session, pairs[:2])]
    else:
        first = [conversation(session, [pairs[0]]), conversation(session, [pairs[1]], start=1)]
    statuses, ops = [], []
    for item in first:
        st, op = retain_items(bank, key, [item]); statuses.append(st); ops.append(op)
    settle(bank, key, ops)
    u1 = (live_units(bank, key, t1) or [None])[0]
    u2 = (live_units(bank, key, t2) or [None])[0]
    m = MCP(bank, key=key)
    m.call("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "dur", "version": "0"}})
    m.call("notifications/initialized", notify=True)
    if u1:
        m.call("tools/call", {"name": "invalidate_memory", "arguments": {"memory_id": u1["id"], "reason": "durability check"}})
    edited = f"Note {t2}-EDITED: the boat is moored at pier 9."
    if u2:
        m.call("tools/call", {"name": "update_memory", "arguments": {"memory_id": u2["id"], "text": edited}})
    st, op = retain_items(bank, key, [conversation(session, [pairs[2]], start=2)]); statuses.append(st)
    settle(bank, key, [op])
    result = {"client": client, "retain_status": statuses, "turn_units_found": [bool(u1), bool(u2)]}
    result["retired_stays_retired"] = bool(u1) and not live_units(bank, key, t1)
    after2 = live_units(bank, key, t2)
    result["edit_holds"] = bool(u2) and [u["id"] for u in after2] == [u2["id"]] and "EDITED" in after2[0]["text"]
    result["new_turn_stored"] = bool(live_units(bank, key, t3))
    s, b, _ = http("GET", f"/v1/default/banks/{bank}/documents?q={session}&limit=50", key=keys_admin)
    docs = [d for d in (json.loads(b).get("items", []) if s == 200 else []) if d["id"].startswith(session + "--")]
    result["documents"] = len(docs)
    result["client_tag"] = sorted({t for d in docs for t in d.get("tags", []) if t.startswith("client:")})
    checks = ["retired_stays_retired", "edit_holds", "new_turn_stored"]
    if client == "hermes":
        # The plugin's legacy path resends the whole session under a per-process document id with
        # no update_mode; with turn keys that is an identical replace, so nothing comes back.
        st, op = retain_items(bank, key, [conversation(session, pairs, update_mode=None, doc=f"{session}-1730000000")])
        settle(bank, key, [op])
        result["resend_status"] = st
        result["resend_adds_nothing"] = (st == 200 and not live_units(bank, key, t1)
                                         and len(live_units(bank, key, t2)) == 1 and len(live_units(bank, key, t3)) == 1)
        checks.append("resend_adds_nothing")
        # Hindsight refuses duplicate document ids in one batch; the shim drops repeats.
        st, op = retain_items(bank, key, [conversation(session, [pairs[2]], start=2),
                                          conversation(session, [pairs[2]], start=2)])
        settle(bank, key, [op])
        result["duplicate_batch_status"] = st
        result["duplicate_batch_ok"] = st == 200 and len(live_units(bank, key, t3)) == 1
        checks.append("duplicate_batch_ok")
    result["pass"] = (all(v == 200 for v in statuses) and all(result[c] for c in checks)
                      and result["documents"] == 3 and result["client_tag"] == [f"client:{client}"])
    log(f"durability {client}:", {k: v for k, v in result.items() if k != "client"})
    return result


def durability(bank, secrets_path):
    keys = dict(line.strip().split("=", 1) for line in open(secrets_path) if "=" in line)
    admin = keys[key_var("admin")]
    s, _, _ = http("PUT", f"/v1/default/banks/{bank}", {"name": bank}, key=admin)
    log("create bank", bank, "->", s)
    cases = [durability_case(bank, c, keys[key_var(c)], admin) for c in ("hermes", "open-webui", "claude-code")]
    result = {"bank": bank, "cases": cases, "pass": all(c["pass"] for c in cases)}
    with open(f"{OUT}/durability.json", "w") as f:
        json.dump(result, f, indent=1, ensure_ascii=False)
        f.write("\n")
    log(f"T071 durability: {sum(c['pass'] for c in cases)}/{len(cases)} clients, {'PASS' if result['pass'] else 'FAIL'}")
    return result


def option(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


cmd, bank = sys.argv[1], sys.argv[2]
if cmd == "clients":
    outcome = clients(bank, option("--clients", "hermes,open-webui,claude-code").split(","),
                      option("--secrets", "/run/harness/secret.env"))
    sys.exit(0 if outcome["pass"] else 1)
if cmd == "durability":
    sys.exit(0 if durability(bank, option("--secrets", "/run/harness/secret.env"))["pass"] else 1)
{"write": write, "mcp": mcp, "export": export, "import": import_, "recall": recall_all}[cmd](bank)
