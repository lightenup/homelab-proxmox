# Backlog: the monitoring stack runs unsupported versions, and nothing keeps pins current

**Status**: Backlog — raised 2026-10-21 while preparing [`089`](./089-log-aggregation.md). Spec
only.
**Order**: After [`090`](./090-backup-coverage-and-staleness.md) (or with a one-off snapshot of the
`monitoring` LXC, because its own backup does not work), **before `089`**. `089` adds Loki to the
same compose file and role, and should start from supported versions.

## Why this exists

The image pins in `group_vars/monitoring/vars.yml` (duplicated in
`roles/monitoring_stack/defaults/main.yml`) have not moved since they were set. Two components
are past their vendors' support windows. Dependabot covers only `python/`, and it cannot read
version variables in Ansible YAML, so nothing raises a pin that falls behind.

## Current state (checked 2026-10-21)

| Component | Pinned (live) | Latest | Support status |
|---|---|---|---|
| Grafana | 12.3.1 | 13.2.x | **12.3 security support ended 2026-08-19.** Supported: 13.2 (until 2027-05-18), 13.1 (2027-03-20), 12.4 (2027-05-24) |
| Prometheus | v3.8.1 | v3.15.0 | **3.8 unsupported since 2026-01-09.** LTS: 3.13 (until 2027-07-31) |
| Alertmanager | v0.30.0 | v0.34.1 | No published support policy; four minors behind |
| blackbox_exporter | v0.28.0 | v0.29.0 | One minor behind |
| Telegraf | 1.37.0 | 1.40.2 | Three minors behind |
| node_exporter (every LXC, via `lxc_base`) | 1.10.2 | 1.12.1 | Two minors behind |

Sources: endoflife.date (Grafana, Prometheus), GitHub releases. Re-check at plan time.

Not in scope here: the LXCs' Debian 12 base (regular security support ended 2026-07-11, LTS until
2028-06-30; listed in `improvement-candidates.md`), and the service images (each service owns
its own upgrade).

## Requirements

- **FR-001 — Supported versions.** Grafana moves to a supported line, and Prometheus to the
  current LTS (3.13). Alertmanager, blackbox_exporter, Telegraf and node_exporter move to their
  current releases. Which Grafana line, 12.4 (minor step) or 13.2 (major), is decided at plan
  time from the 13.0 breaking changes against the provisioned dashboards and data sources.
- **FR-002 — One pin per component.** Each version is defined once: the copies in
  `roles/monitoring_stack/defaults/main.yml` are removed, or reduced to a single default that
  `group_vars` overrides, following the `consolidate-service-versions` precedent.
- **FR-003 — Nothing is lost silently.** After the upgrade, the same set of scrape targets is up,
  the same alert rules are loaded (count and names compared before and after, which is the
  `072` lesson), every provisioned dashboard loads without panel errors, `promtool check rules`
  and `amtool check-config` pass, and a test alert reaches Pushover and ntfy.
- **FR-004 — Pins stay current.** A mechanism raises a pull request, or a notification, when a
  pinned monitoring image falls behind or leaves support. For example a Renovate regex manager
  over `group_vars/**/vars.yml`, or a scheduled check that posts to ntfy like the model scout.
  The mechanism is chosen at plan time. It must cover the services block in
  `group_vars/services/vars.yml` as well, even if those upgrades stay manual.
- **FR-005 — Rollback.** Before the upgrade, the `monitoring` LXC's state is captured (by `090`'s
  backup or a one-off snapshot), and the previous pins are recorded, so a failed upgrade can be
  reverted by a pin change and a restore.

## Success criteria

- **SC-001**: Every component in the table runs a version inside its vendor's support window, or
  the latest release where there is no policy.
- **SC-002**: The FR-003 before/after comparison is recorded, with no target, rule or dashboard
  missing.
- **SC-003**: Lowering one pin on a test branch makes FR-004's mechanism report it.

## Open questions

- Grafana 12.4 or 13.2? 13.x may be what Logs Drilldown needs for `089`. That is a reason to
  choose 13.2 if its breaking changes are harmless here.
- Prometheus: stay on LTS lines (yearly upgrades) or follow the six-weekly minors?
- Renovate (a new tool and GitHub App), or a scout-style scheduled check?

## Dependencies

- **After [`090`](./090-backup-coverage-and-staleness.md)**, or a one-off snapshot (FR-005).
- **Before [`089`](./089-log-aggregation.md)**: soft. `089` can proceed on the current versions,
  but would then add Loki to an unsupported base.
