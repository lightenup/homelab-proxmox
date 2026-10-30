"""Logging forwarder: the spike containers' only route out of the internal network.

Forwards every request to UPSTREAM (the Mac's LiteLLM) and appends one JSON line per
request to /logs/calls.jsonl: run tag, path, model, input size, status, latency.
Prompt and response bodies are not logged. Anything that is not the LLM (HF downloads,
OpenRouter, telemetry) cannot leave: the network is internal and this is the only bridge.
"""
import json
import os
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = os.environ.get("UPSTREAM", "http://host.docker.internal:4000")
KEY = os.environ["LITELLM_SPIKE_KEY"]
LOG = "/logs/calls.jsonl"


def _read(name):
    try:
        with open(f"/logs/{name}") as f:
            return f.read().strip()
    except OSError:
        return "unset"


def run_tag():
    return f"{_read('RUN')}/{_read('RUN.phase')}"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _forward(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        model = None
        if body:
            try:
                model = json.loads(body).get("model")
            except (ValueError, AttributeError):
                pass
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
                                "model": model, "in_bytes": len(body or b""), "status": status,
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


ThreadingHTTPServer(("0.0.0.0", 4000), Handler).serve_forever()
