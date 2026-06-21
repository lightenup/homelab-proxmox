# Contract: Compose Topology (0.2.2 single-engine)

The rendered `docker-compose.yml` is the deploy's primary interface contract with the running stack.
Diff vs. the `046`/`0.1.0` template:

## `api` service

```yaml
api:
  container_name: financial_scenario_api
  image: {{ financial_scenario_api_image }}:{{ financial_scenario_version }}   # 0.2.2
  volumes:
    - "{{ financial_scenario_data_dir }}/reference_data:/app/config/reference_data"
    - "{{ financial_scenario_data_dir }}/scenarios:/app/data"     # NEW — persisted SQLite store
    - "/etc/localtime:/etc/localtime:ro"
  environment:
    EXTRACTION_BASE_URL: ""
    # SCENARIOS_DB_PATH intentionally unset — app default /app/data/scenarios.db is correct
    # given the /app/data mount above. To relocate, set this env and change the mount target.
  # healthcheck unchanged (python urlopen /docs)
```

**Contract assertions** (verification §):
- `docker inspect financial_scenario_api` shows a bind-mount with destination `/app/data`.
- `scenarios.db` appears under `{{ financial_scenario_data_dir }}/scenarios` on the host after first
  save; `docker compose down && up` preserves it.

## `mcp` service

```yaml
mcp:
  container_name: financial_scenario_mcp
  image: {{ financial_scenario_api_image }}:{{ financial_scenario_version }}
  command: ["python", "-m", "src.mcp_server.server"]
  # reference_data bind-mount REMOVED — mcp is now a stateless HTTP client of api.
  volumes:
    - "/etc/localtime:/etc/localtime:ro"
  environment:
    MCP_TRANSPORT: "http"          # kept — server defaults to stdio otherwise
    MCP_PORT: "8001"               # kept — required to bind the port
    API_BASE_URL: "http://api:8000"  # NEW — forwards all engine traffic to api
    EXTRACTION_BASE_URL: ""
  depends_on:                      # NEW — never start before its authority
    api:
      condition: service_healthy
  # healthcheck unchanged (TCP connect :8001)
```

**Contract assertions**:
- `docker inspect financial_scenario_mcp` shows **no** `reference_data` mount and
  `API_BASE_URL=http://api:8000`.
- `mcp` reaches `healthy` only after `api` is `healthy`.

## `gui` service

Unchanged from `046`: only published port (`{{ financial_scenario_gui_port }}:80`); nginx fronts
`/api`, `/docs`, `/mcp`; `depends_on` both `api` and `mcp` healthy; image-baked MCP secret gate.

## Invariants preserved (FR-009)

- Only port `3000` published. No Caddy route, no landing-page card.
- `/mcp` still requires the image-baked shared secret.
- GHCR pull credential and blackbox liveness contract unchanged.
