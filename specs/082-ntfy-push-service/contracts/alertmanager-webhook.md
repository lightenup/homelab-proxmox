# Contract: Alertmanager → ntfy

## Gate

`ntfy_enabled: true` in `ansible/group_vars/monitoring/vars.yml`. With `false`, or undefined, the
rendered `alertmanager.yml` MUST be byte-identical to today's. This is checked by rendering with
the flag off and diffing against the current output.

## Receiver change

Each of the three existing receivers (`pushover-critical`, `pushover-warning`, `pushover-info`)
gains the **same** `webhook_configs` entry next to its unchanged `pushover_configs`. Routes,
matchers, grouping and inhibit rules are untouched (FR-008):

```yaml
    webhook_configs:
      - url: 'https://ntfy.{{ caddy_base_domain }}/alerts?template=homelab-alertmanager'
        send_resolved: true
        max_alerts: 10
        http_config:
          authorization:
            type: Bearer
            credentials: '{{ ntfy_alertmanager_token }}'
```

The root fallback receiver is `pushover-warning`, which already carries the webhook, so alerts
without a severity label reach ntfy too.

## Template `homelab-alertmanager.yml`

Shipped as a static file (`roles/ntfy/files/`, copied, **not** templated, because it is Go template
syntax) to `/opt/ntfy/templates/homelab-alertmanager.yml`. Its input is the Alertmanager webhook
payload (version 4). Its output is fixed by data-model § Alert → notification mapping:

- `title`: `[<SEVERITY>] <groupLabels.alertname>`, or `[RESOLVED] <…>` when `status == "resolved"`.
  `(+N more)` is appended when `truncatedAlerts > 0`.
- `message`: one `annotations.summary` per alert, in payload order.
- `priority`: info → `1`; resolved → `3`; critical → `5`; otherwise `3`.

The severity comes from `commonLabels.severity`. That is reliable because the route groups by
`['alertname', 'severity']`.

## Acceptance

| Check | Expected |
|---|---|
| Synthetic critical firing payload POSTed with the alertmanager token | 200. Phone shows `[CRITICAL] …` at urgent priority |
| Same payload with `status=resolved` | `[RESOLVED] …` at default priority |
| Info firing and info resolved | Delivered silently (priority 1) |
| 10-alert group with long descriptions | 200, delivered (R-004) |
| ntfy stopped, critical test alert | Pushover delivery time unchanged against baseline (R-005 drill) |
