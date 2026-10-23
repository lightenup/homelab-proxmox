# Research: Monitoring Stack Version Currency

**Feature**: `090-monitoring-version-currency` | **Date**: 2026-10-22

Upstream facts were checked on 2026-10-22: endoflife.date API, GitHub releases (via `gh api`), and
upstream changelogs. Repo facts come from the files cited. Docker Hub could not be reached from the
dev Mac (Zscaler). Image tags are confirmed from `pve` at implementation time (quickstart §1).

## R-01 Target versions

| Component | Pinned | Target | Source / support |
|---|---|---|---|
| Grafana | `12.3.1` | `13.2.4` | 13.2 supported until 2027-05-18 (endoflife.date). Tags without a `v` prefix on Docker Hub (`grafana/grafana:13.2.4`); GitHub tag `v13.2.4`. |
| Prometheus | `v3.8.1` | `v3.13.5` | 3.13 is the LTS line, supported until 2027-07-31 (endoflife.date `lts: true`). 3.13.5 was released 2026-10-21. |
| Alertmanager | `v0.30.0` | `v0.34.1` | No support policy (not on endoflife.date), so the latest release is used. |
| blackbox_exporter | `v0.28.0` | `v0.29.1` | Latest release (2026-10-21). |
| Telegraf | `1.37.0` | `1.40.2` | **1.37 left support on 2026-06-08** (endoflife.date). The backlog table described it only as "three minors behind". 1.40 has no end date yet. |
| node_exporter | `1.10.2` | `1.12.1` | Latest release. Binary from GitHub releases (`roles/node_exporter/tasks/main.yml`). |

**Decision**: use the targets above. If a newer patch is out at implementation time, take the
newest patch of the same line. Do not move to a new line during implementation.

**Rationale**: these satisfy SC-001 on the day of writing. Taking patches within a line is
low-risk and keeps the comparison valid.

## R-02 Grafana 13.2: is the fallback to 12.4 needed?

Checked against the 13.0 breaking-change list ("What's new in v13.0") and 12.4's:

| Breaking change | Affects this estate? | Evidence |
|---|---|---|
| Angular panels / `datagrid` removed; `Graph` components removed from `@grafana/ui` | No | All 8 provisioned dashboards use only core panels: `timeseries` 127, `stat` 30, `row` 33, `bargauge` 7, `gauge` 7, `table` 2, `state-timeline` 1 |
| Unified storage migration for dashboards and folders (13.0), playlists and small instances (12.4) | **Yes. Data is unaffected, but the migration is one-way.** | Grafana uses SQLite in the `grafana_data` volume. Dashboards are file-provisioned and come back from disk. The migration still runs once and records itself in `unifiedstorage_migration_log`. |
| Git Sync migration bug (13.0.0 only) | No | Git Sync feature flags are not enabled; target is 13.2.4 |
| Image renderer removed | No | No renderer configured |
| Plugin env vars not inherited (12.4) | No | No plugins installed (no `GF_INSTALL_PLUGINS`) |
| Deprecated id-based data source APIs disabled | No | `scripts/monitoring/smoke-test.sh` calls `GET /api/datasources` (list, not id-based) |
| `/api` path deprecated (not removed) | No, for now | `/api/health` is used by healthchecks and `verify.yml`; it still works in 13.x |
| `grafana-cli` / `grafana-server` removed | No | Not called anywhere |
| Legacy Alertmanager config APIs, RBAC tightening | No | Grafana alerting is not used; alerting goes through Prometheus and Alertmanager |
| Grafana DB metrics renamed / caching metrics removed | No | Not scraped or used in rules or dashboards |

All dashboard data source references use `${DS_PROMETHEUS}` or the built-in Grafana source.
No dashboard hard-codes a data source UID.

**Decision**: target 13.2.4. The 12.4 fallback (spec FR-001) is not triggered by any known
breaking change. It stays available only if the side-by-side rehearsal (R-06) shows a failure that
cannot be fixed.

**Consequence for rollback**: both lines migrate storage one way, so **changing the Grafana pin
back is not a rollback**. Rollback is a snapshot restore (FR-011, quickstart §6). This confirms
the spec's edge case.

## R-03 Prometheus 3.8 → 3.13, Alertmanager 0.30 → 0.34, blackbox, Telegraf, node_exporter

Changelog `[CHANGE]` entries in the range, checked against the repo:

| Item | Affects us? | Evidence |
|---|---|---|
| Prometheus 3.13: credentials no longer forwarded on cross-host redirects | Unlikely | Scrape auth is only on contract targets with `bearer_token` (`prometheus.yml.j2:72`). None is expected to redirect off-host. The after-snapshot target health check would catch it. |
| Prometheus 3.9: `native-histogram` flag is a no-op | No | No `--enable-feature` in compose |
| Prometheus 3.10: `alertmanager` label added to `prometheus_notifications_*` | No | Not used in rules or dashboards (grep) |
| Prometheus 3.15 `--log.level` deprecation | N/A | Not on the 3.13 line; not used |
| TSDB format | Compatible | 3.x reads earlier 3.x blocks. Downgrade within 3.x is also supported, but the snapshot is the rollback regardless |
| Alertmanager 0.33: `auto-gomaxprocs` flag removed; `alertmanager_marked_alerts` removed | No | Neither used (grep) |
| Alertmanager 0.34: `reason` label on `alertmanager_notifications_failed_total` split (`authError`, `rateLimited`) | No | No rule or dashboard matches `reason="clientError"` |
| blackbox 0.29: fails on invalid `prober` value | No | Modules use `http` and `dns` (`blackbox.yml.j2`) |
| Telegraf 1.38: strict env-var handling is the default | No | `telegraf.conf.j2` has no `${…}` references |
| Telegraf 1.40: plugin and option removals | No | Only `inputs.snmp` and `outputs.prometheus_client` are used |
| node_exporter 1.11–1.12 | No | Only addition is a distroless image; binary install unaffected |

**Decision**: no config changes needed for these components. Rely on validators (R-05) and the
before/after comparison (FR-006, FR-007) to catch what the changelogs do not mention.

## R-04 Single source for pins

Today:

- `ansible/group_vars/monitoring/vars.yml:7-10,97` and
  `ansible/roles/monitoring_stack/defaults/main.yml:8-11,58` both set the five monitoring
  versions. The playbook loads the group_vars file explicitly with `include_vars`
  (`playbooks/monitoring.yml:28`), because `monitoring` is a host, not a group. That has higher
  precedence, so the role-default copies are dead values.
- `node_exporter_version` is set once, in `roles/node_exporter/defaults/main.yml:6`.
- `docs/operations/monitoring/runbook-upgrades.md` tells the operator to "edit role defaults". That
  edit is silently ignored. This is a live hazard, not just duplication.

**Decision**: follow the `consolidate-service-versions` (spec 047) precedent. Delete the five
version lines from `roles/monitoring_stack/defaults/main.yml`, with no placeholder. Move
`node_exporter_version` into `group_vars/all/vars.yml`, because node_exporter runs on every LXC via
`lxc_base`. Rewrite the runbook's pin step to point at group_vars.

**Alternatives considered**: keeping a default that group_vars overrides (FR-005 allows it). It was
rejected because a default equal to the pin is the duplicate, and a different default is a trap.
Leaving node_exporter in role defaults was also rejected: it is already single, but the precedent's
acceptance rule is that "no role defaults file needs touching for a routine upgrade".

**Out of scope**: the role defaults duplicate many non-version values too, and they have already
drifted (`monitoring_install_dir` vs `monitoring_base_path`, `grafana_domain`). That is noted for
`improvement-candidates.md` and not fixed here (spec FR-005 is about versions).

## R-05 Validators run before the stack restarts

Today `compose_stack.yml` renders the configs, then runs `docker compose up -d`. Only after that
does `validate_alerts.yml` run `promtool check rules`. `amtool check-config` is never run, and
`promtool check config` (the main `prometheus.yml`) is never run either.

**Decision**: move validation between rendering and `up -d`. Use the **target** images to run
`promtool check config`, `promtool check rules` and `amtool check-config`. Extend the existing
`validate_alerts.yml` rather than adding a file. A failure stops the play while the old containers
are still running.

**Alternative**: Ansible `template: validate:`. It was rejected because the configs reference each
other (rule files, mounted paths), so they must be validated as a set after all are rendered.

## R-06 Rehearsal: the lab path is not isolated

The 072 incident and the 067 issue show that lab and prod share one address space. A lab-path
`monitoring` deploy either stops at the 072 guard or reconfigures the production host
`192.168.1.214`. A lab rehearsal is therefore not possible.

**Decision (owner, 2026-10-22)**: run a side-by-side rehearsal on the monitoring LXC before the prod
deploy:

1. Run the target `promtool` and `amtool` images against the **live** rendered config.
2. Copy the `grafana_data` volume to a scratch volume, and start a temporary `grafana/grafana:13.2.4`
   container on a spare port against that copy and the live provisioning. Let it finish the
   storage migration, then check through its API that all dashboards are listed and every panel's
   data source resolves.
3. Remove the temporary container and the scratch volume.

This tests the two risky parts, the one-way Grafana migration and the validators, without touching
the running stack. The other components have no stored state that migrates, apart from the
Prometheus TSDB (R-03, compatible).

**Alternatives considered**: cloning the LXC from the snapshot. It was rejected: it needs a new IP
outside Terraform, and the clone would scrape the estate in parallel. A third option, no rehearsal
(snapshot only), was rejected by the owner.

## R-07 Rollback point

`local-lvm` (LVM-thin, `terraform.tfvars.example`) supports `pct snapshot`. The snapshot covers the
LXC root disk, including the Docker volumes `prometheus_data`, `grafana_data` and
`alertmanager_data`.

**Decision**: the operator takes `pct snapshot <vmid> pre-090` as root on `pve` before the prod
deploy. The VMID is looked up with `pct list`. The snapshot is deleted after verification
(FR-012). This is a one-off operator step, not provisioning automation, so constitution
principle V does not require a CI path. The quickstart records it like the 089 operator steps.

## R-08 Where the currency check runs

**Decision (owner, 2026-10-22)**: a Python module in the existing package
(`python/src/homelab_proxmox_orchestrator/version_currency.py`). A new scheduled workflow
`.github/workflows/version-currency.yml` runs it on the self-hosted runner. That runner is
`pi-ci` (Raspberry Pi, LAN), per `docs/operations/proxmox-ci.md`. Note: the runner is not `pve`
itself. Deploy workflows SSH from the runner to `pve`.

- **Repo access**: the runner checks out the branch it runs on. A scheduled run uses `main`. For
  SC-003, a manual (`workflow_dispatch`) run on a test branch reports the lowered pin.
- **Network**: the runner has internet access (GitHub API, endoflife.date) and LAN access to
  `ntfy.hus-sky.no` (LAN or tailnet only).
- **Local parity (principle V)**: `python -m homelab_proxmox_orchestrator.version_currency --dry-run`
  prints the report and does not publish. With `NTFY_TOKEN` set, it publishes the same way the
  workflow does.

**Alternatives considered**: a systemd timer on the monitoring LXC. It checks deployed pins rather
than the repo, and SC-003 would need a deploy. A Hermes cron job, like the model scout, was also
considered. It would couple the check to Hermes and need a repo copy there. Renovate was rejected
in the spec clarifications.

## R-09 Cadence and repeats

**Decision (owner)**: run weekly, Mondays 06:00 UTC, with no state between runs. Every finding is
reported each week until the pin is raised. A run with no findings posts nothing (FR-015).

**Rationale**: being stateless means nothing to store and nothing to lose. A weekly nag is the
reminder.

## R-10 What "behind" means per policy

| Policy | Applies to | Reported when |
|---|---|---|
| `lts` | Prometheus | A newer patch exists on the pinned LTS line; **or** a newer LTS line exists; **or** the pinned line's support ends within 30 days or has ended. Newer non-LTS minors are not reported. |
| `latest` | Grafana, Telegraf, Alertmanager, blackbox, node_exporter, and service images with a release source | A newer stable release exists (any line); **or**, where endoflife.date has the product, the pinned line's support ends within 30 days or has ended. |
| `support-only` | Floating-major or distro-style pins whose product is on endoflife.date (`nextcloud_version: "34"`, `llm_router_postgres_version` → PostgreSQL 17) | The pinned line's support ends within 30 days or has ended. |
| `unchecked` | Digest-pinned images (Immich postgres and valkey); date-tagged images with no release source (`hermes_searxng_version`); the owner's own images (`financial_scenario_version`, `market_model_version`), whose repos publish no GitHub releases (checked 2026-10-22: 404 or empty) and which are versioned by their own pipelines | Never "behind". Each is listed by name in a "not checked" line with its reason, so nothing is skipped silently (owner decision). The list goes out only with a report that is posted anyway; a run with no findings stays silent. |

**Pins outside the version blocks (out of scope, named here so they are not skipped
silently)**: four version pins live in role defaults, outside the blocks that FR-014 and the
guard test cover:

- `jellyfin_exporter_version` (`roles/jellyfin/defaults/main.yml`, `1.4.0`)
- `fail2ban_exporter_version` (`roles/fail2ban/defaults/main.yml`, `0.10.3`)
- `go_version` (`roles/reverse_proxy/defaults/main.yml`, Caddy build toolchain, `1.22.0`)
- `docker_compose_version` (vendored `geerlingguy.docker` role default)

They are not checked by 090, and they do not appear in its report. Moving the two exporter pins
into the services versions block, where the check would cover them automatically, is recorded as
an improvement candidate (tasks T035). `docker_compose_version` belongs to a vendored role and is
not overridden.

Releases marked pre-release on GitHub, or whose tag contains `-rc`, `-beta` or `-alpha`, are
ignored (Euro-Office publishes `v9.3.6-rc.1`). Tags are compared on their numeric core
(`MAJOR.MINOR.PATCH`) after removing a leading `v`. Any remaining suffix is ignored: `-stable` on
the `llm_router` pin (its GitHub tags have no suffix), and `-hotfix.N` on Euro-Office tags. This
covers the spec's edge cases about a missing `v` prefix and pulled releases.

Tag formats were checked on 2026-10-22: `BerriAI/litellm` `v1.106.2`, `immich-app/immich` `v3.3.5`,
`open-webui/open-webui` `v0.12.3`, `binwiederhier/ntfy` `v2.32.0`,
`xperimental/nextcloud-exporter` `v0.9.2`, `NousResearch/hermes-agent` `v0.22.4` and
`euro-office/documentserver` `v9.3.5`. Most service pins are behind today. The first scheduled run
will therefore report them. That is expected, and their upgrades stay manual (spec FR-014).

The 30-day warning window is a default. It gives at least four weekly reports before end of
support.

## R-11 Source of the version data

- **GitHub releases API** (`/repos/{owner}/{repo}/releases`, first page): stable tags.
  Authenticated with the workflow's `GITHUB_TOKEN` (1,000 requests/hour) or `gh auth token`
  locally. Unauthenticated requests (60/hour) are enough for about 20 pins. Note that GitHub's
  "latest" flag is not monotonic: Prometheus marked `v3.15.1` and `v3.13.5` on the same day. So the
  module sorts the tags itself and does not trust `releases/latest`.
- **endoflife.date API** (`/api/{product}.json`): line, latest patch, `eol` and `lts`. Products
  used: `grafana`, `prometheus`, `telegraf`, `nextcloud`, `postgresql`. Alertmanager,
  node_exporter and blackbox are not listed there (404). They get `latest` with no support check.
- No registry (Docker Hub or GHCR) queries. Every checked image has a GitHub release source, so a
  registry client would add a dependency and authentication for no extra coverage.

The `pin → source` mapping lives in one data file, `ansible/version-sources.yml`, next to the
group_vars it describes. A guard test (FR-017) fails if a pin in a versions block has no entry,
so a new pin cannot be skipped silently. See [data-model.md](./data-model.md).

## R-12 Publishing and failure visibility

- **ntfy**: a new publisher under the `082` contract (`contracts/publisher-interface.md`). The
  account is `version_check`, the topic is `versions` (new), and the ACL is write-only. Vault holds
  `ntfy_version_check_token` and `ntfy_version_check_password_hash`, in
  `group_vars/services/vault.yml` next to the other publishers. The owner's `*` read grant covers
  the new topic.
- **Token in the workflow**: the workflow decrypts only that key from the services vault with the
  existing `ANSIBLE_VAULT_PASSWORD` secret, and masks it (`::add-mask::`). This keeps the vault the
  single source, as constitution principle V asks for CI, rather than duplicating the token into a
  GitHub secret.
- **Bounded**: each HTTP call has a 20 s timeout, and the job has `timeout-minutes: 10`.
- **Failure is visible (FR-013a)**: if a source cannot be reached, the report gets a "check errors"
  section and the process exits non-zero. If the ntfy publish fails, the process exits non-zero.
  Either way, the workflow run fails, and GitHub's failed-workflow e-mail is the out-of-band
  signal. The process never exits 0 after an error.

## R-13 Tests

- **Unit tests** for the module: `python/tests/version_currency/`, using fake HTTP responses
  without network access. They cover tag parsing and suffixes, pre-release filtering, the
  three policies and the 30-day window, no report when everything is current, error → non-zero
  exit, and the report format.
- **Guard test (FR-017)**: `python/tests/guardrails/test_version_pins.py`. Each monitoring
  version variable and `node_exporter_version` is assigned exactly once under `ansible/`. Every
  pin in the versions blocks has an entry in `ansible/version-sources.yml`. The workflow schedule
  exists.
- Both run in PR CI through the existing `scripts/ci/python-tests.sh`.
- **Workflow**: `act -l` and `act -n -W .github/workflows/version-currency.yml workflow_dispatch`,
  as the constitution's local workflow testing section asks.
