# Data Model: Monitoring Stack Version Currency

**Feature**: `090-monitoring-version-currency` | **Date**: 2026-10-22

## 1. Version pin (Ansible variable)

One configured version, set in exactly one place (FR-005, SC-004).

| Field | Example | Rule |
|---|---|---|
| `variable` | `grafana_version` | Ansible variable name. It ends in `_version`. |
| `value` | `"13.2.4"` | String. It keeps the format the image or binary tag needs (`v` prefix for `prom/*` images, none for Grafana or Telegraf). |
| `file` | `ansible/group_vars/monitoring/vars.yml` | The only file under `ansible/` that assigns the variable. |

**Where each pin lives after this feature**

| Variables | File |
|---|---|
| `prometheus_version`, `grafana_version`, `telegraf_version`, `alertmanager_version`, `blackbox_exporter_version` | `ansible/group_vars/monitoring/vars.yml` (the version block at the top; `blackbox_exporter_version` moves into it from line 97) |
| `node_exporter_version` | `ansible/group_vars/all/vars.yml` (moved from `roles/node_exporter/defaults/main.yml`) |
| Service image pins (`nextcloud_version` … `ntfy_version`) | `ansible/group_vars/services/vars.yml`, `# Service versions` block (unchanged) |

**Validation (guard test)**: each variable in the first two rows is assigned exactly once under
`ansible/`. YAML comments and Jinja references do not count.

## 2. Version source entry: `ansible/version-sources.yml`

One entry per pin the check knows about. Each pin in the three version blocks above has exactly
one entry (guard test).

```yaml
# Schema illustration. The full list is written at implementation time.
pins:
  - variable: prometheus_version
    file: ansible/group_vars/monitoring/vars.yml
    policy: lts                         # lts | latest | support-only | unchecked
    github: prometheus/prometheus       # required for lts and latest
    endoflife: prometheus               # optional; required for lts and support-only
  - variable: alertmanager_version
    file: ansible/group_vars/monitoring/vars.yml
    policy: latest
    github: prometheus/alertmanager
  - variable: nextcloud_version
    file: ansible/group_vars/services/vars.yml
    policy: support-only
    endoflife: nextcloud
  - variable: immich_postgres_image
    file: ansible/group_vars/services/vars.yml
    policy: unchecked
    reason: digest-pinned; upgraded with Immich
```

| Field | Type | Rule |
|---|---|---|
| `variable` | string | Must be assigned in `file` |
| `file` | repo-relative path | Must exist |
| `policy` | enum | `lts`, `latest`, `support-only` or `unchecked` (research R-10) |
| `github` | `owner/repo` | Required for `lts` and `latest` |
| `endoflife` | product slug | Required for `lts` and `support-only`; optional for `latest` (adds the support-window check) |
| `reason` | string | Required for `unchecked`; shown in the report |

Policies by pin (implementation fills the rest in the same way):

| Pin | Policy | `github` | `endoflife` |
|---|---|---|---|
| `prometheus_version` | `lts` | `prometheus/prometheus` | `prometheus` |
| `grafana_version` | `latest` | `grafana/grafana` | `grafana` |
| `telegraf_version` | `latest` | `influxdata/telegraf` | `telegraf` |
| `alertmanager_version` | `latest` | `prometheus/alertmanager` | — |
| `blackbox_exporter_version` | `latest` | `prometheus/blackbox_exporter` | — |
| `node_exporter_version` | `latest` | `prometheus/node_exporter` | — |
| `nextcloud_version` | `support-only` | — | `nextcloud` |
| `nextcloud_exporter_version` | `latest` | `xperimental/nextcloud-exporter` | — |
| `immich_version` | `latest` | `immich-app/immich` | — |
| `immich_postgres_image`, `immich_redis_image` | `unchecked` | — | — |
| `financial_scenario_version`, `market_model_version` | `unchecked` | — | — |
| `eurooffice_version` | `latest` | `euro-office/documentserver` | — |
| `llm_router_version` | `latest` | `BerriAI/litellm` | — |
| `llm_router_postgres_version` | `support-only` | — | `postgresql` |
| `hermes_version` | `latest` | `open-webui/open-webui` | — |
| `hermes_searxng_version` | `unchecked` | — | — |
| `hermes_agent_version` | `latest` | `NousResearch/hermes-agent` | — |
| `ntfy_version` | `latest` | `binwiederhier/ntfy` | — |

## 3. Release (fetched, in memory)

| Field | Source |
|---|---|
| `tag` | GitHub `tag_name` |
| `core` | `(major, minor, patch)` parsed from `tag` after removing `v` and any suffix |
| `prerelease` | GitHub `prerelease`, or the tag contains `-rc`, `-beta` or `-alpha` → excluded |

## 4. Support line (fetched, in memory)

| Field | Source (endoflife.date) |
|---|---|
| `cycle` | `"13.2"`, `"3.13"`, `"34"` |
| `eol` | date, or `false` if no end date is set |
| `lts` | boolean |
| `latest` | latest patch in the line |

The pinned line is the entry whose `cycle` matches the pin's `major.minor`, or `major` for
products whose cycles are major-only (Nextcloud, PostgreSQL).

## 5. Finding

| Field | Example |
|---|---|
| `variable` | `prometheus_version` |
| `pinned` | `v3.13.5` |
| `kind` | `newer-patch` · `newer-release` · `newer-lts-line` · `support-ending` · `support-ended` |
| `available` | `v3.13.6` (for `newer-*`) |
| `eol` | `2027-07-31` (for `support-*`) |

## 6. Currency report

| Part | Content |
|---|---|
| `findings` | List of Findings, monitoring pins first, then service pins |
| `unchecked` | List of `(variable, reason)` |
| `errors` | List of `(variable or source, message)` for sources that could not be reached or parsed |

**State transitions per run**

```text
fetch sources ──► evaluate pins ──► findings empty AND errors empty ──► no publish, exit 0
                                 └► findings non-empty, errors empty ──► publish, exit 0 (exit 1 if publish fails)
                                 └► errors non-empty ─────────────────► publish if possible, exit 1
```

Message format: [contracts/currency-check.md](./contracts/currency-check.md).

## 7. Before/after snapshot (quickstart record)

The record is captured with the quickstart commands before and after the upgrade (FR-006,
FR-007, SC-002).

| Item | How it is identified | Comparison |
|---|---|---|
| Scrape targets | `(job, instance)` with `health` | Same set; every target that was `up` before is `up` after |
| Alert rules | Group name + rule name; total count | Identical set and count |
| Dashboards | Grafana `uid` + title | Identical set; each opens without panel errors |
| Alert delivery | Test alert | Reaches Pushover and ntfy |
| History | `count_over_time(up[1h] offset 2h)` | Non-zero after the upgrade (FR-010) |

## 8. Upgrade record (quickstart)

| Field | Content |
|---|---|
| Previous pins | The six values from research R-01 "Pinned" |
| New pins | The six target values |
| Snapshot | VMID, snapshot name `pre-090`, time taken, time deleted |
| node_exporter rollout | One row per LXC: host, deploy date, version reported by `node_exporter --version` |
