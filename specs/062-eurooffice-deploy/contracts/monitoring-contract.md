# Contract: Monitoring / Health (`host_vars/eurooffice.yml`)

Mirrors `ansible/host_vars/market-model.yml`; consumed by the healthcheck role and the
monitoring-contract aggregation.

```yaml
healthcheck_url:
  scheme: http
  port: 80          # eurooffice_port pinned to 80 (F1)
  path: /healthcheck
healthcheck_profile: lan
healthcheck_expect_status: 200

monitoring_contract:
  enabled: true
  scrape_targets: []
  liveness_targets:
    - job_name: "eurooffice"
      url: "http://192.168.1.219:80/healthcheck"
      module: http_2xx
  alert_rules:
    - alert: EuroOfficeDown
      expr: |
        probe_success{job="eurooffice"} == 0
      for: "5m"
      severity: critical
      summary: !unsafe "eurooffice is down on {{ $labels.instance }}"
      description: !unsafe "The Euro-Office document server has been unreachable for more than 5 minutes (instance: {{ $labels.instance }})."
```

## Contract assertions
- Post-apply healthcheck (`uri` GET `/healthcheck` → 200) passes in the pipeline (FR-008, SC-003).
- Blackbox liveness probe appears green in the monitoring contract (SC-007).
- `url` uses the concrete central IP:port (the aggregator resolves literal URLs).
