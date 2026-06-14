# Contract: `/api/status` health endpoint

**Served by**: Caddy apex site block `hus-sky.no` on the reverse-proxy LXC (192.168.1.211)
**Upstream**: Prometheus `{{ monitoring_ip }}:9090` (192.168.1.214:9090)
**Purpose**: Give the browser the per-service health vector without exposing the Prometheus query API.

> **Port form**: `monitoring_ip` is a shared var (in `group_vars/services/vars.yml`, in scope for the
> reverse_proxy role). The Prometheus port `9090` is written **inline** — `prometheus_port` lives in
> `group_vars/monitoring/` and is out of scope for the reverse_proxy role, and it is referenced exactly
> once here (constitution IV — prefer inline over a single-use re-declared var).

## Request

```
GET https://hus-sky.no/api/status
```

- Same-origin with the landing page (no CORS).
- Any client query string is **ignored** — the handler rewrites the upstream URI to a fixed query.

## Behaviour (Caddy handler)

```caddyfile
handle /api/status {
    rewrite * /api/v1/query?query=probe_success
    reverse_proxy {{ monitoring_ip }}:9090
}
```

- The upstream request is **always** `GET /api/v1/query?query=probe_success`, regardless of client input.
- Client-supplied parameters (e.g. `?query=node_load1`) never reach Prometheus. *(FR-009, SC-007)*

## Response (passthrough from Prometheus instant-query API)

```json
{
  "status": "success",
  "data": {
    "resultType": "vector",
    "result": [
      { "metric": { "instance": "https://immich.hus-sky.no", "job": "blackbox-https" }, "value": [1718275200, "1"] },
      { "metric": { "instance": "https://jellyfin.hus-sky.no", "job": "blackbox-https" }, "value": [1718275200, "0"] }
    ]
  }
}
```

## Client (landing JS) interpretation

| Condition | Card state |
|-----------|-----------|
| `result[].value[1] == "1"` for the card's `data-probe` instance | `up` |
| `== "0"` | `down` |
| instance absent from `result`, OR fetch non-2xx, OR network/JSON error | `unknown` |

## Invariants (acceptance-testable)

1. Requesting `/api/status?query=<anything-else>` returns the **pinned** `probe_success` result, not
   the alternate query. *(SC-007)*
2. With Prometheus stopped/unreachable, `/api/status` fails or returns non-2xx; the page MUST still
   render all cards/links with `unknown` health (handled client-side). *(FR-010, SC-006)*
3. The handler exposes no other Prometheus path (`/api/v1/query_range`, `/api/v1/admin/*`, `/graph`,
   etc.) on the apex origin.

## Security note (deferred, per spec Out of Scope + D-004)

The endpoint is unauthenticated, consistent with the LAN + Tailscale access posture. If the apex is
ever exposed beyond LAN/Tailscale, gate `/api/status` (and the apex) behind auth. Not in scope now.
