# Contract: Document Server Compose (env + volumes)

`ansible/roles/eurooffice/templates/docker-compose.yml.j2` (rendered on the eurooffice LXC).

```yaml
services:
  documentserver:
    container_name: eurooffice
    image: {{ eurooffice_image }}:{{ eurooffice_version }}    # ghcr.io/euro-office/documentserver:9.3.1 — NEVER latest
    ports:
      - "{{ eurooffice_port }}:80"                            # eurooffice_port pinned to 80 (F1) → 80:80; LAN callback + Caddy upstream + probe all use port 80
    environment:
      JWT_ENABLED: "true"                                     # FR-003
      JWT_SECRET: "{{ eurooffice_jwt_secret }}"               # vault, >=32 chars (no_log)
      EXAMPLE_ENABLED: "false"                                # FR-004
    volumes:
      - "{{ eurooffice_data_dir }}/data:/var/lib/euro-office/documentserver"    # FR-005
      - "{{ eurooffice_data_dir }}/logs:/var/log/euro-office/documentserver"
      - "{{ eurooffice_data_dir }}/config:/etc/euro-office/documentserver"
      - "/etc/localtime:/etc/localtime:ro"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:80/healthcheck"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
```

**Contract assertions**
- Image reference MUST interpolate a pinned `eurooffice_version` (preflight rejects empty/`latest`).
- `JWT_ENABLED=true`, `EXAMPLE_ENABLED=false` are literal in the template (not overridable to unsafe).
- `JWT_SECRET` rendered from vault only; the task deploying/handling it uses `no_log: true`.
- Bundled Postgres/RabbitMQ/Redis run inside the image with defaults; no external DB service.

**To confirm at implement time** (D-003): exact env var names and volume paths from the Euro-Office
Docker doc; whether a swap/`ulimit`/`shm` setting is needed as in ONLYOFFICE.
