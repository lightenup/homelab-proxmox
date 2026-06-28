# Contract: Compose Topology (`docker-compose.yml.j2`)

Two services from the **one** image `{{ market_model_image }}:{{ market_model_version }}`. No GUI,
no nginx, no auth gate. Both ports published directly on the LAN/tailnet.

## `api`

- **Image/command**: default `CMD` (`uvicorn market_model.api.app:app --host 0.0.0.0 --port 8000`).
- **Ports**: `{{ market_model_api_port }}:8000` (published).
- **Volumes**:
  - `{{ market_model_data_dir }}/data:/app/data` — the single writable store. **No**
    `MARKET_MODEL_DB_PATH` override (app default resolves here; D-007).
  - `/etc/localtime:/etc/localtime:ro`.
- **restart**: `unless-stopped`.
- **healthcheck**: `GET http://localhost:8000/healthz` → 200 (interval 30s / timeout 10s / retries 3
  / start_period ~20s).

## `mcp`

- **Image**: same image; `command: ["python", "-m", "market_model.mcp.server"]`.
- **Env**: `MCP_TRANSPORT=http`, `MCP_PORT=8001`, `API_BASE_URL=http://api:8000`.
- **Ports**: `{{ market_model_mcp_port }}:8001` (published).
- **Volumes**: `/etc/localtime:/etc/localtime:ro` only — **no** data mount (api is sole writer).
- **depends_on**: `api` with `condition: service_healthy`.
- **restart**: `unless-stopped`.
- **healthcheck**: TCP connect to `localhost:8001` (FastMCP serves `/mcp`, not a health route —
  same pattern as PFS).

## Invariants (verifiable post-deploy)

1. Exactly two published ports: `8000` (api) and `8001` (mcp). No GUI container, no Caddy route.
2. `docker inspect market_model_mcp` shows `API_BASE_URL=http://api:8000`, `MCP_TRANSPORT=http`, no
   data mount, `depends_on` api healthy.
3. `market_model_api` has the `/app/data` bind-mount (plus localtime) and no others.
4. Host `{{ market_model_data_dir }}/data` is owned by `100:65534`; the api (uid 100) successfully
   writes `path-sets.sqlite` (a `root:root` dir would fail — D-006).
