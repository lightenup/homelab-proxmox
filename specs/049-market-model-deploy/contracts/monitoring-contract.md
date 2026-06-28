# Contract: Monitoring & Health Verification

## Ansible health verification (FR-006/FR-007)

After `docker_compose_v2` up, the `market_model` role MUST:
1. `wait_for` the api port (`127.0.0.1:{{ market_model_api_port }}`, delay ~5s, timeout ~120s).
2. `uri` GET `http://127.0.0.1:{{ market_model_api_port }}/healthz` expecting `status_code: 200`,
   with retries (mirror financial_scenario's wait/verify).

## Blackbox monitoring contract (`host_vars/market-model.yml`, FR-008)

```yaml
healthcheck_url:
  scheme: http
  port: 8000
  path: /healthz
healthcheck_profile: lan
healthcheck_expect_status: 200

monitoring_contract:
  enabled: true
  scrape_targets: []          # blackbox liveness only — no app metrics
  liveness_targets:
    - job_name: "market-model-api"
      url: "http://<market-model-ip>:8000/healthz"
      module: http_2xx
  alert_rules:
    - alert: MarketModelDown
      expr: probe_success{job="market-model-api"} == 0
      for: "5m"
      severity: critical
```

## Healthcheck wrapper (`scripts/healthcheck/market-model.sh`)

Mirror `scripts/healthcheck/financial-scenario.sh`: accept `--profile lan|tailscale` and
`--output-json`, and invoke `healthcheck.py --host market-model`.

## Invariants

1. Probe `market-model-api` reports `probe_success == 1` when the stack is healthy.
2. `MarketModelDown` fires when the service is taken down (probe 0 for 5m).
3. No scrape (app-metrics) targets are defined — parity with financial-scenario.
