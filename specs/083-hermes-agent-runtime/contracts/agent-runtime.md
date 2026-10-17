# Contract: the agent runtime's interfaces

## 1. Chat interface (Open WebUI → agent)

- **Endpoint**: `http://hermes-agent:8642/v1`, OpenAI-compatible. Reachable only on the compose
  `agent` network; never published and never routed by Caddy (FR-004).
- **Auth**: `Authorization: Bearer <hermes_agent_api_server_key>`. A request without it is refused.
- **Model**: `GET /v1/models` lists `hermes-agent`.
- **Sessions**: Chat Completions is stateless; Open WebUI resends history. Long-term memory is
  the agent's own.
- **Approvals**: every request is an unattended session. A flagged command is refused at once with a
  readable message (SC-008: < 5 s) and never waits for the 300 s timeout.
- **Health**: `GET /health` → `{"status":"ok"}`, inside the compose network only.
- **Failure**: with the inference host away, the agent returns a readable error within seconds
  (US-2 #3), the same as the gateway contract in `065/contracts/gateway-usage.md`.

## 2. Scheduling interface (owner or agent → scheduler)

Run inside the container as the agent user:

```sh
docker exec -it -u hermes hermes_agent hermes cron <list|create|run|runs|pause|resume|remove|edit> …
```

**Script-only job contract.** This is what a job author must know:

| Script does | Result |
|---|---|
| prints non-empty stdout, exit 0 | stdout delivered to `deliver` (truncated at 4096 chars) |
| prints nothing, exit 0 | silent tick, no delivery |
| last stdout line `{"wakeAgent": false}` | silent tick |
| exits non-zero or times out (`script_timeout_seconds`, 3600) | error alert naming the job, sent to the phone |

Further rules:
- Scripts live in `$HERMES_HOME/scripts/` (`/opt/data/scripts/`). `.sh`/`.bash` run under bash, and
  anything else under the image's Python (3.14).
- The environment is sanitised: no provider credentials. A secret is exposed by name through
  `terminal.env_passthrough` plus a vault entry, which is the one case that needs a deploy change.
- Scripts may write state under `$HERMES_HOME`. It is backed up.
- Outbound network access follows `egress-allowlist.md`.

## 3. Delivery (agent → ntfy)

As `082/contracts/publisher-interface.md`: topic `hermes`, bearer token, markdown on.

PROD only:
- The adapter's own subscription is refused by the server, because the token is write-only.
- `NTFY_ALLOWED_USERS` is unset, so nothing inbound is ever acted on (FR-012).
- The refused subscription MUST NOT stop delivery. This is checked on the first PROD deploy (Q-P2).

## 4. Heartbeat (scheduler → monitoring)

`hermes_agent_heartbeat_timestamp_seconds` and `HermesAgentCronStale`, see data-model. This is the
only signal that says the scheduler runs; job outcomes say nothing about it.
