#!/usr/bin/env python3
"""TLS terminator for the Mac's LiteLLM, so the homelab gateway can hold a long request.

WHY THIS EXISTS. Plaintext HTTP inbound to this Mac is closed after ~300s with no
application-layer response data, and unpredictably thereafter (observed 658s and 1443s)
even with SSE keepalives flowing. TCP keepalive does not help, so the closer counts
application data rather than packets — an HTTP-aware middlebox, which on an MDM-managed
Mac means the app firewall's stealth mode or the Zscaler network filter. Neither is ours to
change.

The same request over TLS survived 1500s and 1800s of COMPLETE silence. Encrypting the
payload removes the closer's ability to act on it. Measured 2026-09-20; full account in
docs/backlog/069-*.md.

So: terminate TLS on the LAN, relay plaintext to LiteLLM over loopback — a path proven to
hold 1500s+ of silence. LiteLLM itself returns to 127.0.0.1, which means this process is
the ONLY thing listening on the LAN (FR-016), and the leg carrying the gateway's API key is
now encrypted rather than plaintext.

WHY NOT stunnel. It would be the conventional choice and is better-tested than this file.
It was rejected on dependency grounds: this Mac is MDM-managed with a documented policy
prompt on unapproved software, Python 3 is system-provided, and the mDNS announcer already
establishes the "small Python script + LaunchAgent" pattern next door. The trade is
acknowledged rather than hidden — this is a hand-rolled relay carrying real traffic, so it
does as little as possible and does not parse, buffer or interpret the stream at all.
"""

from __future__ import annotations

import os
import socket
import ssl
import sys
import threading
import time

LISTEN_HOST = os.environ.get("HERMES_TLS_LISTEN_HOST", "0.0.0.0")
LISTEN_PORT = int(os.environ.get("HERMES_TLS_LISTEN_PORT", "4443"))
UPSTREAM_HOST = os.environ.get("HERMES_TLS_UPSTREAM_HOST", "127.0.0.1")
UPSTREAM_PORT = int(os.environ.get("HERMES_TLS_UPSTREAM_PORT", "4000"))
TLS_DIR = os.environ.get("HERMES_TLS_DIR", os.path.expanduser("~/.config/hermes-tls"))

# A stalled TLS handshake must not hold a thread forever. The RELAY, by contrast, gets no
# timeout at all: a 20-minute silent prefill is the whole point of this process existing,
# so anything that tears down a quiet connection would reintroduce the bug it fixes.
HANDSHAKE_TIMEOUT = 15.0
UPSTREAM_CONNECT_TIMEOUT = 15.0
MAX_CONNECTIONS = int(os.environ.get("HERMES_TLS_MAX_CONNECTIONS", "64"))

_active = threading.BoundedSemaphore(MAX_CONNECTIONS)


def log(msg: str) -> None:
    print(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}", flush=True)


def _build_context() -> ssl.SSLContext:
    cert, key = os.path.join(TLS_DIR, "cert.pem"), os.path.join(TLS_DIR, "key.pem")
    for path in (cert, key):
        if not os.path.exists(path):
            sys.exit(f"missing {path} — run make-cert.sh first")
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(cert, key)
    return ctx


def _pipe(src: socket.socket, dst: socket.socket) -> None:
    """Relay bytes one way, then half-close so the peer sees EOF rather than a hang."""
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except (OSError, ssl.SSLError):
        pass
    finally:
        try:
            dst.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def _handle(raw: socket.socket, peer: str, ctx: ssl.SSLContext) -> None:
    tls = upstream = None
    try:
        raw.settimeout(HANDSHAKE_TIMEOUT)
        tls = ctx.wrap_socket(raw, server_side=True)
        upstream = socket.create_connection((UPSTREAM_HOST, UPSTREAM_PORT),
                                            timeout=UPSTREAM_CONNECT_TIMEOUT)
        tls.settimeout(None)        # no relay timeout: long silent prefills must survive
        upstream.settimeout(None)
        up = threading.Thread(target=_pipe, args=(tls, upstream), daemon=True)
        down = threading.Thread(target=_pipe, args=(upstream, tls), daemon=True)
        up.start(); down.start()
        up.join(); down.join()
    except ssl.SSLError as exc:
        log(f"{peer} tls handshake failed: {exc.__class__.__name__}")
    except OSError as exc:
        log(f"{peer} upstream {UPSTREAM_HOST}:{UPSTREAM_PORT} unreachable: {exc.__class__.__name__}")
    finally:
        for sock in (tls, upstream, raw):
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
        _active.release()


def main() -> None:
    ctx = _build_context()
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((LISTEN_HOST, LISTEN_PORT))
    srv.listen(64)
    log(f"listening {LISTEN_HOST}:{LISTEN_PORT} -> {UPSTREAM_HOST}:{UPSTREAM_PORT} "
        f"(tls>=1.2, max {MAX_CONNECTIONS} connections)")
    while True:
        try:
            raw, addr = srv.accept()
        except OSError as exc:
            log(f"accept failed: {exc.__class__.__name__}")
            continue
        if not _active.acquire(blocking=False):
            log(f"{addr[0]} refused: {MAX_CONNECTIONS} connections already active")
            try:
                raw.close()
            except OSError:
                pass
            continue
        threading.Thread(target=_handle, args=(raw, addr[0], ctx), daemon=True).start()


if __name__ == "__main__":
    main()
