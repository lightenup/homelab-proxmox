"""Logging forwarder: the spike containers' only route out of the internal network.

Forwards every request to UPSTREAM (the Mac's LiteLLM) and appends one JSON line per
request to /logs/calls.jsonl: run tag, path, model, input size, status, latency.
Prompt and response bodies are not logged, with one exception: during the probes phase, the
recall block the agent injected into a chat request is appended to /logs/injected.jsonl, so the
gate measures what the model was given (SC-001's preference leg, spec 097; PR #340 review). The
dataset is synthetic. Anything that is not the LLM (HF downloads,
OpenRouter, telemetry) cannot leave: the network is internal and this is the only bridge.
"""
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = os.environ.get("UPSTREAM", "http://host.docker.internal:4000")
KEY = os.environ["LITELLM_SPIKE_KEY"]
LOG = "/logs/calls.jsonl"
INJECTED = "/logs/injected.jsonl"
# Optional gateway alias mapping, "alias=upstream,..." (prod-render, spec 097): the rendered
# production config names the gateway's aliases, the Mac's LiteLLM knows the targets.
MODEL_MAP = dict(p.split("=", 1) for p in os.environ.get("MODEL_MAP", "").split(",") if "=" in p)


def _read(name):
    try:
        with open(f"/logs/{name}") as f:
            return f.read().strip()
    except OSError:
        return "unset"


def run_tag():
    return f"{_read('RUN')}/{_read('RUN.phase')}"


def record_injected(payload):
    """The probe question and the <memory-context> block the agent sent with it (probes phase)."""
    tag = run_tag()
    if not tag.endswith("/probes") or not isinstance(payload, dict):
        return
    users = [m for m in payload.get("messages") or [] if isinstance(m, dict) and m.get("role") == "user"]
    content = users[-1].get("content") if users else None
    if not isinstance(content, str) or "<memory-context>" not in content:
        return
    question, _, rest = content.partition("<memory-context>")
    with open(INJECTED, "a") as f:
        f.write(json.dumps({"run": tag, "q": question.strip(), "context": rest.partition("</memory-context>")[0]},
                           ensure_ascii=False) + "\n")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _forward(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        model = None
        if body:
            try:
                payload = json.loads(body)
                model = payload.get("model")
                record_injected(payload)
                if model in MODEL_MAP:
                    payload["model"] = MODEL_MAP[model]
                    body = json.dumps(payload).encode()
            except (ValueError, AttributeError):
                pass
        # Which client key called (SC-003: embed and rerank only, under the memory key): a
        # short hash, never the key itself.
        auth = self.headers.get("Authorization") or ""
        caller = hashlib.sha256(auth.removeprefix("Bearer ").encode()).hexdigest()[:8] if auth else None
        headers = {k: v for k, v in self.headers.items()
                   if k.lower() not in ("host", "authorization", "content-length", "connection")}
        # Every client uses the one spike key, whatever it was configured with.
        headers["Authorization"] = f"Bearer {KEY}"
        req = urllib.request.Request(UPSTREAM + self.path, data=body, headers=headers, method=self.command)
        start = time.time()
        try:
            resp = urllib.request.urlopen(req, timeout=1800)
            status, data, rheaders = resp.status, resp.read(), resp.headers
        except urllib.error.HTTPError as e:
            status, data, rheaders = e.code, e.read(), e.headers
        except Exception as e:  # upstream unreachable
            status, data, rheaders = 502, str(e).encode(), {}
        with open(LOG, "a") as f:
            f.write(json.dumps({"ts": start, "run": run_tag(), "method": self.command, "path": self.path,
                                "model": model, "caller": caller, "in_bytes": len(body or b""), "status": status,
                                "secs": round(time.time() - start, 2)}) + "\n")
        self.send_response(status)
        ctype = rheaders.get("Content-Type", "application/json") if rheaders else "text/plain"
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_GET = do_POST = do_PUT = do_DELETE = _forward

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 4000), Handler).serve_forever()
