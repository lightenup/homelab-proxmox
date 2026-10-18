# Data Model: Hermes Agent behind Hermes (083)

Configuration entities and owner content only. This feature adds no application data model.

## Entity: Agent service

| Field | Value / source | Rule |
|---|---|---|
| image | `nousresearch/hermes-agent:{{ hermes_agent_version }}` | plain `vX.Y.Z`; not empty, not `latest`, no `-desktop`/`rc.` (preflight) |
| command | `gateway run` | scheduler + API server in one process (R-002) |
| data | `{{ hermes_data_dir }}/agent` → `/opt/data` | local disk; the preflight's existing NFS assertion covers it (FR-002) |
| config | `{{ hermes_install_dir }}/agent-config.yaml` → `/opt/data/config.yaml:ro` | root-owned; fallback in R-004 |
| network | compose network `agent`, fixed IPv4 `hermes_agent_ip` | the egress rules match this /32 (R-008) |
| ports | none | FR-004. Preflight: the rendered compose has no `ports:` under `hermes-agent` |
| mem_limit | `3g` | R-002, measured on LAB (SC-011) |
| dashboard | not enabled (`HERMES_DASHBOARD` unset) | FR-005 |

## Entity: Agent client (gateway)

`llm_router_clients` entry: `alias: hermes_agent`, `key_env: LLM_ROUTER_CLIENT_HERMES_AGENT_KEY`,
`rpm_limit: 20`, `max_budget: 5.00`, `budget_duration: "30d"`.

Rule: the llm_router preflight sizing band `max ≤ gateway < sum` holds (60 ≤ 65 < 90).

## Entity: Agent secrets (vault → `.env`)

| Vault variable | `.env` | PROD | LAB |
|---|---|---|---|
| `llm_router_client_hermes_agent_key` (new) | gateway key for the custom provider | ✓ | ✓ (shared vault) |
| `hermes_agent_api_server_key` (new, ≥ 8 chars) | `API_SERVER_KEY` | ✓ | ✓ |
| `ntfy_hermes_token` (082, existing) | `NTFY_TOKEN` | ✓ | **absent** (FR-014) |
| MCP bearer tokens (`credential_env`) | by name | when any exist | when any exist |
| job secrets (`hermes_agent_env_passthrough`, vault var `name \| lower`) | by name, and listed in `terminal.env_passthrough` | when any exist | when any exist |

Rules:
- All values live in the one encrypted, git-tracked `group_vars/services/vault.yml`, which LAB and
  PROD share. LAB differs only in what is rendered.
- The preflight asserts each value is present, with `no_log`.
- On LAB, the preflight asserts that the rendered `.env` contains no `NTFY_TOKEN`.
- `.env` is never backed up.

## Entity: Job (owner content, in `/opt/data/cron/`)

| Field | Notes |
|---|---|
| name | unique; `heartbeat` is reserved for the platform |
| schedule | cron expression or `every Nm` |
| kind | `no_agent` (script) or agent prompt |
| script | file in `$HERMES_HOME/scripts/`. Paths escaping that directory are rejected upstream |
| deliver | MUST include a target that reaches the phone (`ntfy`) on PROD (FR-013) |
| failure target | `deliver`: no separate target. A failed agent run produces a `(FAILED)` report that goes to the same target (Q-L5). MUST reach the phone |
| model | agent jobs only; a gateway alias. Default `hermes-balanced` |

State: `active ⇄ paused`, then `removed`. `failure_streak` counts consecutive failed runs and
resets on success; at 3 the failure message carries a review nudge (upstream).

Jobs present at acceptance:

| Job | Owner | Schedule | Kind | Deliver |
|---|---|---|---|---|
| `heartbeat` | Ansible, PROD only (R-007) | `every 15m` | no_agent | ntfy (failures only; ticks are silent) |
| `model-scout` | owner (FR-019) | `30 7 * * *` | no_agent | ntfy |

## Entity: Heartbeat metric

`hermes_agent_heartbeat_timestamp_seconds` (gauge, unix seconds), written by `heartbeat.sh` to
`/var/lib/hermes-agent-heartbeat/hermes_agent.prom` and read by node_exporter through a symlink.
Alert `HermesAgentCronStale` fires on age > 3600 s or absence, `for: 5m` (R-007).

## Entity: Egress allowlist

Derived, never hand-listed:
- `llm_router_ip:llm_router_port`
- each `hermes_mcp_servers[].url` host:port
- `reverse_proxy_ip:443`
- DNS through the LXC's public resolver (1.1.1.1), with no rule needed. No AdGuard in this estate (Q-L6)
- the `agent` subnet

Everything else private or tailnet is rejected; the internet is allowed. Rule: adding an MCP server to
`hermes_mcp_servers` extends the allowlist with no other edit (R-008).

## Entity: Open WebUI connections

`openai.api_base_urls` = `[gateway, http://hermes-agent:8642/v1]`, with `openai.api_keys` in the same
order. Index 0 (the gateway) stays the default. Reconciled by `no_log` (R-010).

## Validation summary (preflight)

1. The agent pin is valid (above).
2. `hermes-balanced` and any configured agent default exist in `llm_router_aliases`.
3. The new vault variables are present (`no_log`).
4. Exposure: no `hus-sky.no` name resolves to a public address (R-012), otherwise the deploy fails.
5. LAB (`deploy_environment=lab`): no `NTFY_TOKEN` is rendered; a `lab_inventory` is never paired with a prod deploy. Only on the LAB rig (`lab_inventory`) the deploy also asserts that no `heartbeat` job exists. The pipeline's LAB stage runs on the production machine, where the job legitimately exists (LAB deploy 39092898788).
6. Every `hermes_mcp_servers` URL parses to host:port, which the egress rules need.
