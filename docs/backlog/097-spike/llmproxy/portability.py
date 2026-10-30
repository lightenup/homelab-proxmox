"""Hindsight portability tests, run inside llmproxy (internal network, stdlib only).

usage: portability.py write|mcp|export|import|recall <bank>
Client A = REST, client B = MCP over Streamable HTTP. HSK = Hindsight API key (env).
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

BASE = "http://hindsight:8888"
KEY = os.environ["HSK"]
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


def wait_op(bank, op):
    for _ in range(120):
        s, b, _ = http("GET", f"/v1/default/banks/{bank}/operations/{op}")
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


cmd, bank = sys.argv[1], sys.argv[2]
{"write": write, "mcp": mcp, "export": export, "import": import_, "recall": recall_all}[cmd](bank)
