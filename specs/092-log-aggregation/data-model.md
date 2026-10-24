# Data Model: Log Aggregation and Log-Based Alerting

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Research**: [research.md](./research.md)

This feature has no database. Its "data" is Ansible variables, which are declarations in the
repo, and the shape of log streams and alerts at runtime. Each entity below says where it lives,
which fields it has, and what rule holds for it.

## 1. Log stream (runtime, in the store)

| Label | Values | Source |
|---|---|---|
| `env` | `prod` | static, set by the collector |
| `host` | inventory hostname (`reverse_proxy`, `ntfy`, …, `proxmox`) | collector, `inventory_hostname` |
| `service` | same as `host` on LXCs, `proxmox` on pve | collector |
| `source` | `journal` \| `docker` \| `file` | the source component |
| `ident` | journal `SYSLOG_IDENTIFIER` (e.g. `sshd`, `sshd-session`, `sudo`, `kernel`) | journal only |
| `unit` | journal `_SYSTEMD_UNIT`, only if it ends in `.service` | journal only |
| `container` | Docker container name without the leading `/` | docker only |
| `filename` | absolute path of a declared file | file only |

Structured metadata: `lxc`, only on pve kernel `oom-kill:` lines (R6).

Rules:

- No label may come from line content (R11).
- Every line passes through the redaction stages before `loki.write` (§5).
- Retention: 720 h for all streams.

## 2. Collector (one per expected host)

| Field | Where | Default | Notes |
|---|---|---|---|
| `alloy_version` | `group_vars/all/vars.yml` | `"1.21.2"` | pin (R1) |
| `alloy_docker_logs` | role default, overridden in `host_vars/{reverse_proxy,jellyfin,proxmox}.yml` | `true` | adds `docker` group and the Docker source |
| `alloy_file_logs` | `host_vars/jellyfin.yml`, `host_vars/nextcloud.yml` | `[]` | list of `{path_glob, tail_from_end}` |
| `alloy_relay` | `host_vars/monitoring/` | `false` | turns on the `:3101` push relay (R4) |
| `alloy_redaction_patterns` | role default | §5 | data, not code |
| `alloy_memory_high` / `alloy_memory_max` | role default | `128M` / `160M` | changed only after SC-007 |
| `alloy_journal_max_age` | role default | `"168h"` | equals the store's backfill limit (R9) |
| `alloy_rate_limit` / `alloy_rate_burst` | role default | `200` / `2000` lines/s | per-host throttle, `drop = false`, so nothing is lost (R9) |
| `alloy_relay_port` | role default | `3101` | relay listen port and the port in the push URL |
| `alloy_http_port` | `group_vars/all/vars.yml` | `12345` | two consumers: the collector's listen address and Prometheus' `alloy` job |

The push target is derived as `http://{{ monitoring_host_ip }}:{{ alloy_relay_port }}/loki/api/v1/push`.
`monitoring_host_ip` (`192.168.1.214`) is a new entry in the central address block of
`group_vars/all/vars.yml`, next to `proxmox_host_ip`. It is not read through `hostvars`, so a
per-service deploy does not depend on the monitoring host being in its inventory.
`monitoring_stack`'s `monitoring_ip` default becomes `"{{ monitoring_host_ip }}"`, so the
address is written once.
On the monitoring host it is `http://127.0.0.1:3100/loki/api/v1/push`.

**Expected host set** (the basis for MR-002): `groups['services'] + groups['proxmox_hosts']`.
The `alloy` scrape job lists these hosts on every path. The pipeline alert file that uses them
is rendered only when `deploy_environment != 'lab'` (R12), so a LAB-path render changes
neither.

State transitions per host: *absent* → *installed, retrying* (no relay yet) → *shipping*. A
store outage takes it to *blocked, buffering on disk*, then back to *shipping*. A stopped
service takes it to *down*, which raises `LogCollectorDown`.

## 3. Log rule declaration (per service)

Lives in `host_vars/<service>.yml` under `monitoring_contract.log_alert_rules`, next to
`alert_rules`.

| Field | Required | Type | Rule |
|---|---|---|---|
| `alert` | yes | string, CamelCase | unique across all log and metric rules |
| `expr` | yes | LogQL metric query ending in a comparison | must pass `lokitool rules check` |
| `for` | yes | duration | — |
| `severity` | yes | `critical` \| `warning` \| `info` | routes as today |
| `summary` | yes | string | Alertmanager → Pushover/ntfy message |
| `description` | yes | string | includes a Grafana Explore hint |
| `enabled` | yes | bool | `false` until the 7-day baseline passes (SC-004) |
| `disabled_reason` | when `enabled: false` | string | rendered as a comment in the rules file |
| `baseline` | when `enabled: true` | `{from, to, max_15m}` | the evidence that it passed |

The first delivery declares one rule each for `llm-router`, `hermes`, `nextcloud`, `immich` and
`ntfy`. Initial selectors are in research R8.

## 4. Allowed login list (estate-wide)

Lives in `group_vars/monitoring/vars.yml`, which is its only consumer.

```yaml
lan_cidr: "192.168.1.0/24"          # group_vars/all/vars.yml, central (topology)
tailnet_cidr: "100.64.0.0/10"       # group_vars/all/vars.yml; tailnet SSH to pve itself is not NATed
ssh_login_allowlist:
  lxc:                               # applies to every host in groups['services']
    - name: pipeline deploy key
      users: [root, ansible]
      keys: ["SHA256:NH5zp/61GeEPB81f+jkiTmMfTHaWrn4s4JU5MIQUwT4"]
      from: [proxmox]
    - name: owner
      users: [root]
      keys: ["SHA256:cqi3Ec4b…", "SHA256:3+LnahZM…"]
      from: [lan, proxmox]
  proxmox:                           # applies to groups['proxmox_hosts']
    - name: CI runner
      users: [ci]
      keys: ["SHA256:bclAaF1G…"]
      from: [lan]
    - name: owner
      users: [ci, root]
      keys: ["SHA256:ssfuJwQz…", "SHA256:cqi3Ec4b…", "SHA256:3+LnahZM…"]
      from: [lan, tailnet]
ssh_sudo_expected:
  lxc: ansible
  proxmox: ci
```

The full fingerprints are in research R3.

Rules:

- `from` values: `proxmox` resolves to `proxmox_host_ip`, `lan` to `lan_cidr`, and `tailnet` to
  `tailnet_cidr`. There are no literal addresses. Tailnet SSH to an LXC arrives NATed to the
  Proxmox host's address, so it matches `proxmox`. Tailnet SSH to pve itself keeps its
  `100.x` address, so it matches `tailnet`.
- A login alerts unless **some** entry matches all three of user ∈ `users`, fingerprint ∈ `keys`
  and source ∈ `from`.
- A password login has an empty fingerprint and never matches.
- Fingerprints are public. A guard test asserts that every key matches `^SHA256:[A-Za-z0-9+/]{43}$`.

## 5. Redaction pattern

Lives in `roles/alloy/defaults/main.yml` as `alloy_redaction_patterns`, a list of
`{name, expression}`. `expression` is RE2 with **exactly one capture group**, which is the part
replaced by `<redacted>`.

| name | covers (FR-005) |
|---|---|
| `authorization-header` | `Authorization:` values (Bearer, Basic, bare) |
| `pve-api-token` | `PVEAPIToken=…` anywhere |
| `ntfy-token` | `tk_` + 29 alphanumerics |
| `litellm-key` | `sk-…` |
| `tailscale-key` | `tskey-…` |
| `query-credential` | `?auth=`, `&token=`, `access_token=`, `api_key=` values |
| `url-password` | `scheme://user:<pass>@` |
| `env-assignment` | `*_TOKEN=`, `*_SECRET=`, `*_PASSWORD=`, `*_PASSWD=`, `*_KEY=` values |

Rules:

- Each pattern has a positive line in the test corpus. Adding a pattern means adding a line
  (FR-016).
- The control lines stay byte-identical.

## 6. Pipeline alert (Prometheus)

Rendered from `templates/log_pipeline_alerts.yml.j2`. Names, expressions and severities are in
research R14. Each carries `component: logging`. The `LogRulesNotLoaded` threshold is the number
of rules rendered into `log_alerts.yaml`: the enabled per-service rules plus the estate-wide
rules.

## 7. Delete request (FR-016, runtime)

`POST http://127.0.0.1:3100/loki/api/v1/delete?query=<selector + line filter>&start=<unix>&end=<unix>`,
run on the monitoring host. Its lifecycle is *received* → (10 min cancel period) → *processed*.
Matching lines are hidden from queries as soon as the request is *received* (R2). The procedure
is in [quickstart.md](./quickstart.md) §7.
