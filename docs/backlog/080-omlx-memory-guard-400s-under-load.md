# oMLX's prefill memory guard 400s real traffic under load — the alerting fix treats the symptom

**Status**: Backlog — found 2026-09-22 investigating a Pushover notification storm from `064`/`065`.
**Impact**: real Hermes requests fail with HTTP 400 while the gateway reports healthy, and every
alias carries `fallback_to: null`, so there is no recovery path — the caller just gets an error.
The alerting changes shipped the same day (the `pushover-info` route, the canary demotion, and
`llm_router_health_check_interval` 60 → 300) stop the *phone* from screaming about this. They do
not stop it happening.

## What was measured

The Mac's LiteLLM container log, over 24 hours:

```
$ docker logs litellm --since 24h 2>&1 | grep -oE '"POST /v1/[a-z/]+ HTTP/1.1" [0-9]{3}' \
    | sort | uniq -c | sort -rn
4052 "POST /v1/chat/completions HTTP/1.1" 200
 244 "POST /v1/chat/completions HTTP/1.1" 400
  88 "POST /v1/embeddings HTTP/1.1" 200
   7 "POST /v1/rerank HTTP/1.1" 200
   6 "POST /v1/chat/completions HTTP/1.1" 507
```

Every one of the 400s is the same rejection:

```
oMLX prefill memory guard rejected this prompt: Prefill would require ~115.99 GB peak
(current 85.25 GB + KV+SDPA 30.74 GB) but metal_cap ceiling is 102.14 GB.
Raise kernel iogpu.wired_limit_mb in Terminal (currently caps Metal at 107.52 GB),
or reduce context length.
```

They are not spread evenly across models — 488 of 503 rejections named one model group:

```
$ docker logs litellm --since 48h -t 2>&1 | grep -oE "Received Model Group=[a-z-]+" \
    | sort | uniq -c | sort -rn
 488 Received Model Group=fast
   8 Received Model Group=reasoner
   6 Received Model Group=coder
   1 Received Model Group=rerank
```

**The guard's projection is dominated by a transient, not by prompt size.** Note the
`KV+SDPA 30.74 GB` term above against a 14-token request. That is why the synthetic canary —
`{"messages":[{"role":"user","content":"canary"}],"max_tokens":1}` — is refused just as readily
as a real one. The same request succeeded in 0.57 s when run by hand a few minutes later:

```
$ curl -sk -m 60 -w '\nHTTP %{http_code} time=%{time_total}s\n' -X POST \
    https://127.0.0.1:4443/v1/chat/completions -H "Authorization: Bearer $KEY" \
    -d '{"model":"fast","messages":[{"role":"user","content":"canary"}],"max_tokens":1}'
... "total_time":0.52}
HTTP 200 time=0.567493s
```

Attribution by caller, from the gateway's own metrics over 6 hours — this is the part that makes
it more than a monitoring problem:

| Caller | Successes | 400s |
|---|---|---|
| `litellm-internal-health-check` | 1,010 | 28 (all on `fast`) |
| `hermes` (real use) | 39 | **1** |
| `canary` | 5 | 1 |

Headroom on the host:

```
$ sysctl iogpu.wired_limit_mb
iogpu.wired_limit_mb: 0          # default; oMLX reports this as capping Metal at 107.52 GB
$ sysctl -n hw.memsize | awk '{print $1/1024/1024/1024" GB"}'
128 GB
```

## Why it is still worth fixing

The 2026-09-22 changes removed the *noise*: `info` now routes to Pushover priority `-1`,
`LlmRouterCanaryFailing` is `warning` rather than a priority-2 emergency, and cutting the health
check from 60 s to 300 s removed ~3,400 generations/day of self-inflicted load. That last one
genuinely reduces how often the guard trips — health checks were **96% of all traffic reaching
the Mac** (1,044 of 1,090 requests over 6 h) — but it is a probabilistic improvement, not a fix.
Three 27B models stay resident either way, and the transient that busts the cap is per-request.

What remains unaddressed:

- **`hermes` requests still fail outright.** One in the measured 6-hour window. With
  `fallback_to: null` on every alias (deliberate — see `spec.md` FR-004's withdrawal) a 400 is
  terminal for that request.
- **The capacity lever is untouched and is not in this repo.** `iogpu.wired_limit_mb` is at the
  default. Raising it (e.g. `sudo sysctl iogpu.wired_limit_mb=114688`, made persistent) is the
  change the guard's own error message asks for. It belongs to `~/Development/private/local-llm`,
  not here, which is exactly why it is easy to leave undone.
- **Nothing alerts on the 400 rate itself.** `LlmRouterAllBackendsFailing` needs >90% failure
  across all deployments over 10 m; a steady 2–3% 400 rate concentrated on one alias is invisible
  to it, and now that the canary is `warning` there is no prompt to go and look.

A second, smaller hole found in the same investigation and also left open:
`llm_router_canary_last_run_timestamp_seconds` is written by `canary.sh` and **read by nothing** —
no alert, no dashboard panel. Because the canary metric is a level served indefinitely by
node_exporter's textfile collector, a stalled timer leaves the last value in place forever. A
stale `0` is merely annoying; a stale `1` hides a real outage silently. A `LlmRouterCanaryStale`
rule on `time() - llm_router_canary_last_run_timestamp_seconds > 7200` would close it.
