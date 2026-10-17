# Contract: ntfy monitoring (`ansible/host_vars/ntfy.yml`)

```yaml
healthcheck_url:
  scheme: http
  port: 80
  path: /v1/health
healthcheck_profile: lan
healthcheck_expect_status: 200

monitoring_contract:
  enabled: true
  scrape_targets:
    - job_name: "ntfy"
      port: "{{ ntfy_metrics_port }}"   # metrics-listen-http, never proxied (R-006)
      path: /metrics
  liveness_targets:
    - job_name: "ntfy-health"
      url: "https://ntfy.{{ caddy_base_domain }}/v1/health"
      module: http_2xx
  alert_rules:
    - alert: NtfyDown
      expr: probe_success{job="ntfy-health"} == 0
      for: "5m"
      severity: critical
      # Routed like every critical, so it reaches Pushover. The ntfy copy fails, which is harmless (R-005).
```

## Preconditions

- `ntfy` is listed in `ansible/inventories/prod/hosts.yml` under `services`. Without it Prometheus
  builds none of the above (backlog `066`, R-010).
- The `caddy_services` entry (`host: ntfy`, `user_facing: true`) also produces the
  `blackbox-https` probe of `https://ntfy.hus-sky.no`. The front-page card reads that probe
  (FR-012), and the generic `EndpointDown` rule covers it.

## Acceptance

| Check | Expected |
|---|---|
| Prometheus targets page | `ntfy` (scrape) and `ntfy-health` (probe) both `UP` |
| `docker stop ntfy` on the LXC | Card turns `down` within ~1 min. `NtfyDown` reaches Pushover after 5 min (SC-003) |
| `docker start ntfy` | Card `up`. `NtfyDown` resolution reaches Pushover |
