---
description: "Task list for 092 log aggregation and log-based alerting"
---

# Tasks: Log Aggregation and Log-Based Alerting

**Input**: Design documents from `/specs/092-log-aggregation/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/log-pipeline.md](./contracts/log-pipeline.md),
[quickstart.md](./quickstart.md)

**Tests**: The plan requires guard tests.

- A new file, `python/tests/guardrails/test_log_pipeline.py`, covers every contract clause
  marked **[test]**, together with a redaction corpus fixture (research R7). It is written in
  Phase 2 and must be seen to fail before the code.
- `test_version_pins.py` is extended for `alloy_version`.
- LogQL syntax is checked with `lokitool rules check` locally (quickstart §1) and at deploy.
  Everything else is the live drills in `quickstart.md`.

**Organization**: the code phases follow the spec's user stories, and all code merges in one PR.

- The live rollout (Phase 9) deploys in the order **services → pve → monitoring last**
  (plan "Rollout"). Collectors retry without limit until the relay exists.
- Per-service error rules ship **disabled**. They are enabled after a 7-day baseline (Phase 10).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (a different file, with no dependency on an incomplete task)
- **[Story]**: US1–US5, from spec.md
- Paths are repo-relative. Ansible commands run from `ansible/` unless stated.

## Path Conventions

- Ansible: `ansible/roles/`, `ansible/playbooks/`, `ansible/group_vars/`, `ansible/host_vars/`
  (`monitoring` is a directory: `ansible/host_vars/monitoring/vars.yml`).
- Tests: `python/tests/guardrails/`.
- Docs: `docs/architecture.md`, `docs/operations/monitoring/`, `docs/backlog/`.
- Live results go into the Record table in `specs/092-log-aggregation/quickstart.md` §13.
- Where live commands run:
  - **pve** (`host_proxmox.yml`): only from an operator machine with root SSH to `pve`
    (192.168.1.112) and `ansible/.vault-pass.txt` (principle V exception).
  - **Services and monitoring**: through the pipeline (`Prod 1 - LXC Promote` →
    `Prod 2 - LXC Apply`) on branch `092-log-aggregation`.
  - Read-only checks: `ssh ci@pve` then `sudo pct exec <vmid> -- …`. The VMIDs are 100 jellyfin,
    101 immich, 102 eurooffice, 103 monitoring, 105 nextcloud, 106 financial-scenario,
    107 market-model, 108 proxy, 109 llm-router, 110 hermes and 111 ntfy.
- Never run `lokitool rules lint` without `--dry-run`: it rewrites the file into a form the ruler
  rejects (research R10).

---

## Phase 1: Setup

**Purpose**: a baseline before any edit, and the live facts the allow-list depends on.

- [X] T001 Confirm the branch is `092-log-aggregation` and rebased on `origin/main` (`git fetch origin main && git log --oneline origin/main -1`). From `ansible/`, run `ansible-playbook -i inventories/prod/hosts.yml --syntax-check` on `playbooks/{reverse_proxy,immich,monitoring,jellyfin,nextcloud,financial-scenario,market-model,eurooffice,llm-router,hermes,ntfy,host_proxmox}.yml`, and run `bash scripts/ci/python-tests.sh` from the repo root. Record any failure that already exists in `specs/092-log-aggregation/quickstart.md` §13 so it is not blamed on this feature.
- [X] T002 Run the quickstart §0.1 login census again (research R3 table). Every (user, key) pair seen in the last 30 days must be one of the fingerprints in research R3. Ask the owner to confirm that `SHA256:3+LnahZMxEHmkN3uF/R5qPgFxPev6aSf1Sk6H1jyhQM` (192.168.1.106) is the owner's key before T034 commits it. Record the result in quickstart §13 row "§0.1".
- [X] T003 [P] Record the quickstart §0.2 memory baseline from Prometheus (`http://192.168.1.214:9090`): minimum `node_memory_MemAvailable_bytes` over 7 days for `192.168.1.214:9100` and `192.168.1.222:9100`, and `process_resident_memory_bytes{job="prometheus"}`. Write the values into quickstart §13 notes.
- [X] T004 [P] On the dev Mac, download `lokitool-darwin-arm64.zip` from Loki release `v3.7.9` (`gh release download v3.7.9 -R grafana/loki -p 'lokitool-darwin-arm64.zip'`), unzip it to `~/.local/bin/lokitool`, and check that `lokitool rules check --help` runs. Pull `grafana/alloy:v1.21.2` and `grafana/loki:3.7.9` into Docker Desktop (`DOCKER_HOST=unix://$HOME/.docker/run/docker.sock`). These are needed for quickstart §1.

---

## Phase 2: Foundational (guard test, pins, shared variables, rule plumbing)

**Purpose**: the pieces every story uses:

- the guard test, seen red first;
- the version pins;
- the topology variables;
- the store's paths;
- the two rule files' render and validation path.

**⚠️ CRITICAL**: no user story work can begin until this phase is complete.

- [X] T005 Create `python/tests/guardrails/fixtures/redaction_corpus.txt`. Write one entry per line, pipe-separated: `<pattern name>|<raw line>|<secret substring>`. Lines starting with `#` are comments. Include at least one positive line for each of the 8 `alloy_redaction_patterns` names (data-model §5): `authorization-header`, `pve-api-token`, `ntfy-token`, `litellm-key`, `tailscale-key`, `query-credential`, `url-password`, `env-assignment`. Use the synthetic values from research R7 (`drill-1` … `drill-9`, for example `drill-8 DATABASE_URL=postgresql://litellm:S3cr3tPassw0rd@llm_router_postgres:5432/litellm|S3cr3tPassw0rd`). Add at least 3 `control|<line>|` entries that must stay unchanged, for example `drill-10 plain line with no secret, user=andreas path=/var/lib/x` and an `sshd` "Accepted publickey for root from 192.168.1.112 port 1 ssh2: ED25519 SHA256:NH5zp/61GeEPB81f+jkiTmMfTHaWrn4s4JU5MIQUwT4" line. The control lines prove that key fingerprints are not redacted, because the login rules need them.
- [X] T006 Create `python/tests/guardrails/test_log_pipeline.py`. Model it on `python/tests/guardrails/test_service_backup.py`: the same `_find_repo_root`, `from __future__ import annotations`, `pathlib`, `yaml.safe_load` and text assertions on `.j2` files. Write one function per contract clause, each with a docstring naming the requirement:
  1. `test_redaction_corpus`: load `alloy_redaction_patterns` from `ansible/roles/alloy/defaults/main.yml`. Apply every pattern in list order to each corpus line, replacing only the span of `group(1)` with `<redacted>` (Python `re`). For positive lines, the secret substring must be absent and `<redacted>` present. Control lines must be byte-identical. Every pattern must have exactly one capture group (`re.compile(e).groups == 1`) and at least one positive corpus line (FR-005, SC-002, R7).
  2. `test_store_contract`: in `ansible/roles/monitoring_stack/templates/docker-compose.yml.j2`, the `loki` service uses `grafana/loki:{{ loki_version }}`, its only port mapping starts with `127.0.0.1:`, it has `mem_limit`, it is not inside any `{% if` on `deploy_environment`, and the volume `loki_data` is declared. `templates/loki.yaml.j2` contains every key listed in contracts C1 (`retention_enabled: true`, `delete_request_store: filesystem`, `delete_request_cancel_period: 10m`, `retention_period`, `reject_old_samples_max_age: 168h`, `max_line_size_truncate: true`, `replay_memory_ceiling`, `schema: v13`, `store: tsdb`, `alertmanager_url: http://alertmanager:9093`, `reporting_enabled: false`). `files/grafana/provisioning/datasources/loki.yml` has `type: loki`, `uid: loki` and `url: http://loki:3100`, and `tasks/grafana_provision.yml` copies it (C1, FR-004, FR-006, FR-013).
  3. `test_store_validation_before_start`: in `ansible/roles/monitoring_stack/tasks/validate_alerts.yml`, the text contains `-verify-config` and `lokitool rules check`. No file under `ansible/` contains `rules lint` without `--dry-run`. In `tasks/compose_stack.yml`, the `include_tasks: validate_alerts.yml` comes before the `docker compose up -d` task (C1, C4, R10).
  4. `test_collector_contract`: in `ansible/roles/alloy/tasks/main.yml`, the URL contains `github.com/grafana/alloy/releases/download/v{{ alloy_version }}`, a `checksum:` uses `SHA256SUMS`, and the groups include `adm` and `systemd-journal`. In `templates/config.alloy.j2`, `max_backoff_retries = 0` appears in every `loki.write` block, there is no `wal {` or `stability.level`, and `stage.replace` sits inside a `for` loop over `alloy_redaction_patterns`. `templates/alloy-override.conf.j2` contains `MemoryMax=` and `MemoryHigh=`. `config.alloy.j2` contains `stage.limit` with `drop = false` before the first `stage.replace`, and listens on `alloy_relay_port`, not a literal `3101`. `tasks/main.yml` contains a `docker inspect` check on `max-size` that fails the play (C3, FR-003, FR-010, FR-011).
  5. `test_collector_production_only`: `ansible/roles/lxc_base/tasks/main.yml` includes role `alloy` with a `when` containing `deploy_environment` and `!= 'lab'`. `ansible/playbooks/host_proxmox.yml` lists role `alloy` with the same `when` (C3, FR-017).
  6. `test_log_rules_declarations`: for every `ansible/host_vars/*.yml` that has `monitoring_contract.log_alert_rules`, each entry has `alert`, `expr`, `for`, `severity` ∈ {`critical`, `warning`, `info`}, `summary`, `description` and `enabled` (bool). If `enabled` is false, it has `disabled_reason`. If true, it has `baseline` with `from`, `to` and `max_15m`. `llm-router`, `hermes`, `nextcloud`, `immich` and `ntfy` each declare exactly one (data-model §3, FR-008).
  7. `test_login_allowlist`: `ansible/group_vars/monitoring/vars.yml` defines `ssh_login_allowlist` with keys `lxc` and `proxmox`. Every entry has `name`, `users` (a non-empty list), `keys` (each matching `^SHA256:[A-Za-z0-9+/]{43}$`) and `from` (a subset of {`proxmox`, `lan`, `tailnet`}). `ssh_sudo_expected` is `{lxc: ansible, proxmox: ci}`. `ansible/group_vars/all/vars.yml` defines `lan_cidr`, `tailnet_cidr`, `monitoring_host_ip` and `alloy_http_port`. No file under `ansible/roles/alloy/` contains `hostvars['monitoring']` (data-model §2 and §4, FR-009).
  8. `test_rules_file_rendering`: `ansible/roles/monitoring_stack/tasks/compose_stack.yml` renders `log_alerts.yaml.j2` to a path ending `/fake/log_alerts.yaml` with a `when` containing `!= 'lab'`. `templates/log_alerts.yaml.j2` contains `KernelOomKill`, `SshLoginNotAllowed`, `SudoByUnexpectedUser`, `log_estate`, `log_services` and `log_alert_rules`, and filters on `enabled`. The SSH regex contains `port \\d+ ssh2(?:` (never `port \\d+ \\S+(?:`), and every `sudo_user` comparison is preceded by `sudo_user != ""`. The same two checks apply to `files/grafana/dashboards/security-overview.json`. Every `log_alert_rules` `summary` contains `{host=` (C4, FR-017, R3, spec US3 scenario 1).
  9. `test_pipeline_alerts`: `ansible/roles/monitoring_stack/templates/log_pipeline_alerts.yml.j2` defines `LogCollectorDown`, `LogHostSilent`, `LogRulesNotLoaded`, `LogRuleEvaluationFailing`, `LogRuleNotificationsFailing`, `LogLinesDiscarded`, `LogLinesDiscardedSustained`, `LogCollectorDropping`, `LogRetentionStalled` and `HostOomKill`, each with `component: logging`. `templates/prometheus.yml.j2` has `job_name: 'loki'` and `job_name: 'alloy'`, and the `alloy` job carries `no_down_alert` and has no `deploy_environment` condition. `tasks/compose_stack.yml` renders `log_pipeline_alerts.yml.j2` with a `when` containing `!= 'lab'` (C5, R12, R14, FR-017).
  10. `test_sshd_lxc_only`: `ansible/roles/lxc_base/tasks/main.yml` writes `/etc/ssh/sshd_config.d/10-homelab-auth.conf` containing `PasswordAuthentication no` and `KbdInteractiveAuthentication no`, followed by a task running `sshd -t`. That task has no `deploy_environment` condition. No file in `ansible/roles/{proxmox_host,tailscale_host,node_exporter,alloy}` or `ansible/playbooks/host_proxmox.yml` contains `PasswordAuthentication` (C7, FR-015).
  11. `test_file_logs_declared`: `ansible/host_vars/nextcloud.yml` `alloy_file_logs` contains `/mnt/nextcloud/data/nextcloud.log` with `tail_from_end: true`. `ansible/host_vars/jellyfin.yml` contains `/var/log/jellyfin/*.log`. `alloy_docker_logs: false` is set in `host_vars/{reverse_proxy,jellyfin,proxmox}.yml`. `ansible/host_vars/monitoring/vars.yml` sets `alloy_relay: true` (C6, R5, R8).

  Run `bash scripts/ci/python-tests.sh` and confirm that every new test fails, for the expected reason (file or key missing).
- [X] T007 In `python/tests/guardrails/test_version_pins.py`, add `"alloy_version"` to `ALL_VARS`, and in `test_every_pin_has_a_source` collect `alloy_version` from `ansible/group_vars/all/vars.yml` beside `node_exporter_version`. Run the file and confirm that it fails until T008.
- [X] T008 [P] Add the pins and the central topology variables:
  - In `ansible/group_vars/monitoring/vars.yml`, in the version block next to `prometheus_version`, add `loki_version: "3.7.9"` with a comment naming spec 092 and noting that it also pins `lokitool`.
  - In `ansible/group_vars/all/vars.yml`, after `node_exporter_version`, add `alloy_version: "1.21.2"` (comment: "Alloy on every host incl. pve, spec 092").
  - In the "Estate infrastructure addresses" block, add `lan_cidr: "192.168.1.0/24"` and `tailnet_cidr: "100.64.0.0/10"`, with a comment that LAN addresses are DHCP, so rules use the range. Add `monitoring_host_ip: "192.168.1.214"` next to `proxmox_host_ip`.
  - After `alloy_version`, add `alloy_http_port: 12345`, with a comment: "collector HTTP/metrics port; read by the alloy role and Prometheus' alloy job".
  - In `ansible/version-sources.yml`, add `{variable: loki_version, file: ansible/group_vars/monitoring/vars.yml, policy: latest, github: grafana/loki}` under Monitoring and `{variable: alloy_version, file: ansible/group_vars/all/vars.yml, policy: latest, github: grafana/alloy}` under Shared.
  - Run `python -m pytest -c python/pytest.ini python/tests/guardrails/test_version_pins.py` and confirm it passes.
- [X] T009 [P] Add the store's settings to `ansible/roles/monitoring_stack/defaults/main.yml` under a `# Loki (spec 092)` heading:
  - `loki_port: 3100`;
  - `loki_config_path: "{{ monitoring_install_dir }}/loki"`;
  - `loki_rules_path: "{{ monitoring_install_dir }}/loki/rules"`;
  - `loki_retention_period: "720h"`;
  - `loki_mem_limit: "1g"`;
  - `lokitool_path: /usr/local/bin/lokitool`.

  Change the existing `monitoring_ip: "192.168.1.214"` to `monitoring_ip: "{{ monitoring_host_ip }}"`, so the address is written once. Do not add any `*_version` key here (`test_monitoring_role_defaults_have_no_versions`). In `ansible/roles/monitoring_stack/tasks/create_directories.yml`, add tasks for `{{ loki_config_path }}` (0755) and `{{ loki_rules_path }}/fake` (0755). Loki runs as uid 10001 and reads them through a read-only bind mount.
- [X] T010 Create `ansible/roles/monitoring_stack/templates/log_alerts.yaml.j2` as a skeleton:
  - a header comment ("Loki ruler rules, spec 092. Generated by Ansible — DO NOT EDIT. Validated with `lokitool rules check`; never `lint`.");
  - `groups:` with two groups, `log_estate` and `log_services`, both with `interval: 1m`.

  `log_estate` gets `rules:` filled by T027 (OOM) and T035–T036 (login and `sudo`). `log_services` loops over every host in `groups['all']` whose `hostvars[host].monitoring_contract.log_alert_rules` has entries with `enabled` true, rendering `alert`, `expr` (indented, as in `service_alerts.yml.j2`), `for`, `labels.severity`, `labels.service: <host>`, and `annotations.summary` and `annotations.description`.

  Before `groups:`, render one comment line per disabled rule: `# disabled: <host> <alert> — <disabled_reason>`. Set a Jinja variable `log_rules_rendered_count` and write it in a comment `# rendered rules: N`, so T040 can use the same count. Wrap PromQL-style `{{ $labels.x }}` text in `{% raw %}`. If a group would otherwise be empty, render `rules: []`.
- [X] T011 Create `ansible/roles/monitoring_stack/templates/log_pipeline_alerts.yml.j2` as a skeleton: a header comment (spec 092, research R14), and `groups:` with one group `log_pipeline_alerts` (`interval: 30s`) whose rules T029 and T039–T040 fill. At the top, set `{% set log_expected_hosts = groups['services'] | default([]) + groups['proxmox_hosts'] | default([]) %}`. This file is not rendered on the LAB path (T012), so no lab condition is needed inside it.
- [X] T012 In `ansible/roles/monitoring_stack/tasks/compose_stack.yml`, after "Deploy backup staleness alert rule", add these tasks:
  - "Deploy log pipeline alert rules": template `log_pipeline_alerts.yml.j2` to `{{ prometheus_config_path }}/alerts/log_pipeline_alerts.yml`, mode 0644, notify `Reload prometheus`, with `when: (deploy_environment | default('prod')) != 'lab'`. A LAB-path run leaves the production file untouched (FR-017, R12).
  - "Deploy Loki ruler rules": template `log_alerts.yaml.j2` to `{{ loki_rules_path }}/fake/log_alerts.yaml`, mode 0644, with `when: (deploy_environment | default('prod')) != 'lab'` and **no handler**, because the ruler polls every minute (R15).
- [X] T013 In `ansible/roles/monitoring_stack/tasks/validate_alerts.yml`, add tasks at the top, before the promtool tasks:
  1. "Check installed lokitool version": `command: {{ lokitool_path }} --version`, with `failed_when: false` and `changed_when: false`.
  2. When it is missing, or its output lacks `loki_version`: `get_url` `https://github.com/grafana/loki/releases/download/v{{ loki_version }}/lokitool-linux-amd64.zip` to `/tmp/` with `checksum: "sha256:https://github.com/grafana/loki/releases/download/v{{ loki_version }}/SHA256SUMS"`, then `unarchive` with `remote_src` and `copy` it to `{{ lokitool_path }}` (0755). Skip it in check mode, as `node_exporter` does.
  3. "Validate Loki ruler rules with lokitool": `command: {{ lokitool_path }} rules check {{ loki_rules_path }}/fake/log_alerts.yaml`, with `changed_when: false`, `when: prod` and a `fail_msg` that names the file and says not to use `lint`.

  The promtool loop already picks up `log_pipeline_alerts.yml`.
- [X] T014 Render-check the plumbing locally: `ansible monitoring -i inventories/prod/hosts.yml -c local -m ansible.builtin.template -a "src=roles/monitoring_stack/templates/log_alerts.yaml.j2 dest=/tmp/092/log_alerts.yaml"`, then `lokitool rules check /tmp/092/log_alerts.yaml`. Do the same with `log_pipeline_alerts.yml.j2` and `docker run --rm --entrypoint promtool -v /tmp/092:/r prom/prometheus:v3.13.5 check rules /r/log_pipeline_alerts.yml`. Both validators must exit 0, even though the files have empty groups.

**Checkpoint**: `test_version_pins.py` is green. `test_log_pipeline.py` is red except for parts of groups 3, 8 and 9. The plumbing renders and validates empty.

---

## Phase 3: User Story 1 - Search every host's logs in one place (Priority: P1) 🎯 MVP

**Goal**: every LXC ships its journal, its Docker output and its declared files, redacted on the
host, to a store on the monitoring host. That store can be searched only through Grafana.

**Independent Test**: quickstart §4. A canary line on every in-scope host's journal, and one on a
container on each Docker host, is found in Grafana by host and service within 60 s. The quickstart
§5 redaction drill shows `<redacted>` for every format.

- [X] T015 [P] [US1] Create `ansible/roles/monitoring_stack/templates/loki.yaml.j2` with exactly the keys in contracts C1, using `{{ loki_retention_period }}`:
  - `auth_enabled: false`;
  - `server.http_listen_port: 3100`, `log_level: warn`;
  - `common.path_prefix: /loki`, `replication_factor: 1`, ring `kvstore.store: inmemory`, `storage.filesystem.chunks_directory: /loki/chunks` and `rules_directory: /loki/rules-unused`;
  - `schema_config` from `"2026-10-01"`, `store: tsdb`, `object_store: filesystem`, `schema: v13`, index `prefix: index_`, `period: 24h`;
  - `ingester.wal.replay_memory_ceiling: 256MB`;
  - `limits_config`: `retention_period`, `ingestion_rate_mb: 4`, `ingestion_burst_size_mb: 8`, `per_stream_rate_limit: 1MB`, `per_stream_rate_limit_burst: 4MB`, `max_global_streams_per_user: 5000`, `reject_old_samples: true`, `reject_old_samples_max_age: 168h`, `max_line_size: 256KB`, `max_line_size_truncate: true`, `max_query_series: 1000`, `max_query_parallelism: 2`, `deletion_mode: filter-and-delete`, `allow_structured_metadata: true`;
  - `compactor`: `working_directory: /loki/compactor`, `retention_enabled: true`, `delete_request_store: filesystem`, `delete_request_cancel_period: 10m`;
  - `chunk_store_config.chunk_cache_config.embedded_cache.enabled: false`;
  - `query_range.results_cache.cache.embedded_cache` with `enabled: true` and `max_size_mb: 32`;
  - `ruler`: `storage.type: local`, `local.directory: /etc/loki/rules`, `rule_path: /loki/rules-temp`, `alertmanager_url: http://alertmanager:9093`, ring `kvstore.store: inmemory`, `enable_api: true`, `evaluation_interval: 1m`;
  - `pattern_ingester.enabled: false`;
  - `analytics.reporting_enabled: false`.

  This config was verified with `-verify-config` in research R2.
- [X] T016 [US1] In `ansible/roles/monitoring_stack/templates/docker-compose.yml.j2`, add the service `loki`:
  - `container_name: loki` and `image: grafana/loki:{{ loki_version }}`;
  - `command: ['-config.file=/etc/loki/loki.yaml']`;
  - `ports: ["127.0.0.1:{{ loki_port }}:3100"]`;
  - volumes `{{ loki_config_path }}/loki.yaml:/etc/loki/loki.yaml:ro`, `{{ loki_rules_path }}:/etc/loki/rules:ro` and `loki_data:/loki`;
  - `environment: [TZ={{ timezone }}]`, `restart: unless-stopped`, `mem_limit: {{ loki_mem_limit }}`.

  Add a comment that there is no healthcheck because the image has no shell (R2), and that liveness is `up{job="loki"}` with `ServiceDown`. Add `loki_data: {driver: local}` under `volumes:`. Do not put it under any `deploy_environment` condition (R12), and do not add `depends_on` from grafana.
- [X] T017 [US1] In `ansible/roles/monitoring_stack/tasks/compose_stack.yml`, add the task "Deploy Loki configuration": template `loki.yaml.j2` to `{{ loki_config_path }}/loki.yaml`, mode 0644, notify `Restart monitoring stack`. It runs on every path. In `tasks/validate_alerts.yml`, add the task "Validate Loki configuration": `command: docker run --rm -v {{ loki_config_path }}:/etc/loki:ro grafana/loki:{{ loki_version }} -config.file=/etc/loki/loki.yaml -verify-config`, with `changed_when: false`, placed before the lokitool rules check.
- [X] T018 [P] [US1] Create `ansible/roles/monitoring_stack/files/grafana/provisioning/datasources/loki.yml` (`apiVersion: 1`, one data source: `name: Loki`, `uid: loki`, `type: loki`, `access: proxy`, `url: http://loki:3100`, `editable: false`, `jsonData.maxLines: 1000`). In `tasks/grafana_provision.yml`, after the Prometheus data source task, add "Deploy Loki datasource provisioning", which copies it to `{{ grafana_provisioning_path }}/datasources/loki.yml` with mode 0644.
- [X] T019 [US1] In `ansible/roles/monitoring_stack/tasks/verify.yml`, add `loki` to the container loop. Add a `uri` task to `http://127.0.0.1:{{ loki_port }}/ready` with `status_code: 200`, `retries: 30` and `delay: 5`, because Loki waits 15 s after it is ready (R2). Do not add 3100 to the LAN port wait.
- [X] T020 [P] [US1] Create `ansible/roles/alloy/defaults/main.yml`:
  - `alloy_docker_logs: true`;
  - `alloy_file_logs: []`;
  - `alloy_relay: false`;
  - `alloy_memory_high: "128M"`, `alloy_memory_max: "160M"`;
  - `alloy_journal_max_age: "168h"`;
  - `alloy_relay_port: 3101`;
  - `alloy_rate_limit: 200`, `alloy_rate_burst: 2000` (lines per second per host; R9);
  - `alloy_push_url: "http://{{ monitoring_host_ip }}:{{ alloy_relay_port }}/loki/api/v1/push"`. Use the central address, not `hostvars['monitoring']`, so a per-service inventory without the monitoring host still works;
  - `alloy_local_loki_url: "http://127.0.0.1:3100/loki/api/v1/push"`.

  Also add `alloy_redaction_patterns`, a list of `{name, expression}` in this order. Each expression has exactly one capture group. YAML single-quote them:
  1. `authorization-header`: `(?i)authorization:\s*(?:bearer|basic|pveapitoken=)?\s*([^\s"',]+)`
  2. `pve-api-token`: `PVEAPIToken=(\S+)`
  3. `ntfy-token`: `(tk_[A-Za-z0-9]{29})`
  4. `litellm-key`: `\b(sk-[A-Za-z0-9_-]{8,})`
  5. `tailscale-key`: `(tskey-[A-Za-z0-9_-]+)`
  6. `query-credential`: `[?&](?:auth|token|access_token|api_key)=([^&\s"']+)`
  7. `url-password`: `[a-zA-Z][a-zA-Z0-9+.-]*://[^:/@\s]+:([^@/\s]+)@`
  8. `env-assignment`: `(?i)\b[A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|PASSWD|_KEY)\s*[=:]\s*"?([^\s"',]+)`

  These are verified in research R7. Do not put any `*_version` key, or `alloy_http_port` (it lives in `group_vars/all`, T008), here. Run `test_redaction_corpus` and confirm that it passes.
- [X] T021 [P] [US1] Create `ansible/roles/alloy/templates/alloy.default.j2`, which renders `/etc/default/alloy`:
  - `CONFIG_FILE="/etc/alloy/config.alloy"`;
  - `CUSTOM_ARGS="--server.http.listen-addr={{ ansible_host }}:{{ alloy_http_port }} --disable-reporting"`;
  - `RESTART_ON_UPGRADE=true`.

  Also create `ansible/roles/alloy/templates/alloy-override.conf.j2` with `[Service]`, `MemoryHigh={{ alloy_memory_high }}`, `MemoryMax={{ alloy_memory_max }}` and `Restart=always`.
- [X] T022 [US1] Create `ansible/roles/alloy/templates/config.alloy.j2`, following plan "Collector role" and contracts C3.
  1. `loki.write "default"`: `endpoint { url = "{{ alloy_relay | ternary(alloy_local_loki_url, alloy_push_url) }}"  max_backoff_retries = 0 }`.
  2. `loki.process "redact"`, forwarding to `loki.write.default.receiver`. It has `stage.static_labels { values = { env = "prod", host = "{{ inventory_hostname }}", service = "{{ 'proxmox' if inventory_hostname in groups['proxmox_hosts'] else inventory_hostname }}" } }`, then `stage.limit { rate = {{ alloy_rate_limit }}  burst = {{ alloy_rate_burst }}  drop = false }` (per-host throttle with no loss, R9), then a Jinja `for p in alloy_redaction_patterns` loop that renders `stage.replace { expression = {{ p.expression | to_json }}  replace = "<redacted>" }` with a `// {{ p.name }}` comment.
  3. `loki.relabel "journal"` (`forward_to = []`) with these rules:
     - `__journal__systemd_unit` → `unit`, only if it matches `.+\.service`;
     - `__journal_syslog_identifier` → `ident`;
     - a static `source = "journal"`.
  4. `loki.source.journal "journal"` with `max_age = "{{ alloy_journal_max_age }}"`, `relabel_rules = loki.relabel.journal.rules` and `forward_to = [loki.process.redact.receiver]` on every host. On `proxmox_hosts`, T028 changes it to `loki.process.oom.receiver`.
  5. `{% if alloy_docker_logs %}`: `discovery.docker "local" { host = "unix:///var/run/docker.sock" }`, then `discovery.relabel "docker"`, which maps `__meta_docker_container_name` with the leading `/` stripped (regex `/(.*)`) to `container` and sets `source = "docker"`. Then `loki.source.docker "docker"`, with the same host, `targets = discovery.relabel.docker.output` and `forward_to = [loki.process.redact.receiver]`.
  6. `{% for f in alloy_file_logs %}`: a `local.file_match "file_{{ loop.index }}"` with `path_targets = [{"__path__" = {{ f.path_glob | to_json }}, "source" = "file"}]`, and a `loki.source.file "file_{{ loop.index }}"` with `tail_from_end = {{ f.tail_from_end | default(false) | lower }}`, forwarding to redact.
  7. `{% if alloy_relay %}`: `loki.source.api "relay" { http { listen_address = "0.0.0.0"  listen_port = {{ alloy_relay_port }} }  use_incoming_timestamp = true  forward_to = [loki.write.default.receiver] }`. The relay does **not** go through redact, because senders already redacted.

  Render it for `ntfy`, `jellyfin` and `monitoring` with the quickstart §1 command, and run `alloy validate` (via `grafana/alloy:v1.21.2`) on each. All must return 0.
- [X] T023 [P] [US1] Create `ansible/roles/alloy/handlers/main.yml` with three handlers, in this order:
  - "Validate alloy config": `command: alloy validate /etc/alloy/config.alloy`, `changed_when: false`;
  - "Reload systemd for alloy": `systemd: daemon_reload: true`;
  - "Restart alloy": `systemd: name=alloy state=restarted`.

  Tasks notify all three through `listen: alloy config changed`.
- [X] T024 [US1] Create `ansible/roles/alloy/tasks/main.yml` with these tasks:
  1. Assert `(deploy_environment | default('prod')) != 'lab'`, with the message "alloy is production-only (FR-017)".
  2. Check the installed version with `dpkg-query -W -f='${Version}' alloy` (`failed_when: false`, `changed_when: false`).
  3. If it does not start with `alloy_version`, `get_url` `https://github.com/grafana/alloy/releases/download/v{{ alloy_version }}/alloy-{{ alloy_version }}-1.amd64.deb` to `/tmp/` with `checksum: "sha256:https://github.com/grafana/alloy/releases/download/v{{ alloy_version }}/SHA256SUMS"`, then `apt: deb=/tmp/alloy-….deb`, then remove the file. Skip the install in check mode.
  4. When `alloy_docker_logs`, `group: name=docker system=true state=present`. Then the FR-003 check:
     - `command: which docker`, `register`, `failed_when: false`, `changed_when: false`;
     - when docker exists: `shell: docker ps -q | xargs -r docker inspect -f '{{ "{{" }}.Name{{ "}}" }} {{ "{{" }}index .HostConfig.LogConfig.Config "max-size"{{ "}}" }}'`, with `changed_when: false`;
     - `assert` that no output line has an empty second field, with a `fail_msg` naming the containers and pointing at spec 089 (recreate the container so it picks up rotation).
  5. `user: name=alloy groups="adm,systemd-journal{{ ',docker' if alloy_docker_logs else '' }}" append=true`, notifying `alloy config changed`.
  6. Ensure `/etc/systemd/system/alloy.service.d/` exists, then template `alloy-override.conf.j2` to `override.conf` in it.
  7. Template `alloy.default.j2` to `/etc/default/alloy`.
  8. Template `config.alloy.j2` to `/etc/alloy/config.alloy` (0640, `root:alloy`). Steps 6–8 all notify `alloy config changed`.
  9. For each `alloy_file_logs` entry with a non-glob `path_glob`: `command: runuser -u alloy -- test -r {{ item.path_glob }}`, with `changed_when: false` and a `fail_msg` pointing at quickstart §2 step 2 (the `nogroup` fallback).
  10. `systemd: name=alloy enabled=true state=started`.
  11. `meta: flush_handlers`.
- [X] T025 [US1] Wire the collector in:
  - In `ansible/roles/lxc_base/tasks/main.yml`, after the node_exporter include, add "Deploy Alloy log collector (spec 092)": `include_role: name=alloy` with `when: (deploy_environment | default('prod')) != 'lab' and (alloy_enabled | default(true))`.
  - Set `alloy_docker_logs: false` in `ansible/host_vars/reverse_proxy.yml` and `ansible/host_vars/jellyfin.yml`.
  - Add `alloy_file_logs: [{path_glob: "/var/log/jellyfin/*.log", tail_from_end: false}]` to `ansible/host_vars/jellyfin.yml`.
  - Add `alloy_file_logs: [{path_glob: "/mnt/nextcloud/data/nextcloud.log", tail_from_end: true}]` to `ansible/host_vars/nextcloud.yml`, with a comment that fail2ban reads the same file, so `log_type` stays `file` (R8).
  - Add `alloy_relay: true` to `ansible/host_vars/monitoring/vars.yml`, with a comment: "push-only relay on :3101 → host-local Loki (FR-013, R4)".

  Run `bash scripts/ci/python-tests.sh`. Groups 1, 2 and 4 of `test_log_pipeline.py` must now pass. Groups 5 and 11 pass after T026.

- [X] T026 [US1] Wire the collector into pve, so US1 covers every in-scope host (spec US1 scenario 1). In `ansible/playbooks/host_proxmox.yml`, add `- role: alloy` with `when: (deploy_environment | default('prod')) != 'lab'` after `node_exporter`. Add `alloy_docker_logs: false` to `ansible/host_vars/proxmox.yml`. Render `config.alloy.j2` for `proxmox` and run `alloy validate`. Run `bash scripts/ci/python-tests.sh`: groups 5 and 11 must now pass.

**Checkpoint**: US1's code is complete. Quickstart §1 static checks pass for the collector and
store templates.

---

## Phase 4: User Story 2 - An OOM kill on any LXC reaches the phone, naming the LXC (Priority: P1)

**Goal**: pve's kernel `oom-kill:` lines reach the store with the LXC's name. A Loki rule alerts
within 5 minutes, and a Prometheus rule backs it up when the log path is down.

**Independent Test**: quickstart §8. A container OOM on `market-model` raises one `KernelOomKill`
naming `market-model` and `python`, on Pushover and ntfy. With Loki stopped, it raises
`HostOomKill` instead.

- [X] T027 [US2] In `ansible/roles/monitoring_stack/templates/log_alerts.yaml.j2`, group `log_estate`, add `KernelOomKill`:
  - `expr: sum by (lxc, task) (count_over_time({env="prod", host="proxmox", ident="kernel"} |= "oom-kill:constraint=" | regexp "task=(?P<task>[^,]+)," [5m])) > 0`. `lxc` is structured metadata set by T028.
  - `for: 0m`, `labels.severity: warning`.
  - `summary: "OOM kill in LXC {{ $labels.lxc }}: {{ $labels.task }}"`.
  - `description`: the kernel killed `task` in `lxc`; check `journalctl -k -g oom-kill` on pve and the container's memory limit.

  Render it and run `lokitool rules check` (T014 command).
- [X] T028 [US2] In the `alloy` role, for pve:
  - In `ansible/roles/alloy/tasks/main.yml`, before the config template, add "Read VMID to name map (pve only)": `command: pct list`, `changed_when: false`, `when: inventory_hostname in groups['proxmox_hosts']`. Then `set_fact alloy_vmid_names` as a dict of VMID to name, parsed from the stdout lines after the header (first and last columns).
  - In `ansible/roles/alloy/templates/config.alloy.j2`, `{% if inventory_hostname in groups['proxmox_hosts'] %}`, add `loki.process "oom"`, forwarding to `loki.process.redact.receiver`, with `stage.match { selector = "{ident=\"kernel\"} |= \"oom-kill:\""` containing:
    - `stage.regex { expression = "task_memcg=/lxc/(?P<vmid>[0-9]+)/" }`;
    - `stage.template { source = "lxc"  template = <Go template> }`, rendered from `alloy_vmid_names` as `{{ "{{" }} if eq .vmid "100" {{ "}}" }}jellyfin{{ "{{" }} else if … {{ "}}" }}…{{ "{{" }} else if .vmid {{ "}}" }}{{ "{{" }} .vmid {{ "}}" }}{{ "{{" }} else {{ "}}" }}host{{ "{{" }} end {{ "}}" }}`, with care for Jinja vs Go braces;
    - `stage.structured_metadata { values = { lxc = "" } }` `}`.

    The journal source on pve forwards to `loki.process.oom.receiver`.
  - Render it for `proxmox` and run `alloy validate`.
- [X] T029 [US2] In `ansible/roles/monitoring_stack/templates/log_pipeline_alerts.yml.j2`, add `HostOomKill` (`warning`, `component: logging`):
  - `expr: increase(node_vmstat_oom_kill{instance="{{ proxmox_host_ip }}:{{ node_exporter_port | default(9100) }}"}[10m]) > 0`;
  - `for: 0m`;
  - summary "OOM kill on the Proxmox host (host-wide counter; LXC not known)";
  - a description pointing to `KernelOomKill` and pve's `journalctl -k`.

  Render it only when `groups['proxmox_hosts'] | default([]) | length > 0`. The whole file is already skipped in lab (T012). Run promtool (T014).

**Checkpoint**: US2's code is complete. The quickstart §8 drill is in Phase 9.

---

## Phase 5: User Story 3 - A failing application is noticed even when its port still answers (Priority: P1)

**Goal**: per-service error-rate rules for `llm-router`, `hermes`, `nextcloud`, `immich` and
`ntfy`, declared in each monitoring contract. They ship disabled and are enabled after a 7-day
baseline.

**Independent Test**: quickstart §6. After a rule is enabled, an injected error burst on one
service fires only that service's alert.

Every rule's `summary` ends with ` — Explore: <the rule's selector and filter>`. Pushover and ntfy
show only the summary, so this is how the alert carries the query for the matching lines (spec
US3 scenario 1). The `test_rules_file_rendering` group checks it.

- [X] T030 [P] [US3] In `ansible/host_vars/llm-router.yml`, add `log_alert_rules` under `monitoring_contract` (next to `alert_rules`) with one entry:
  - `alert: LlmRouterErrorLogs`;
  - `expr: sum(count_over_time({env="prod", host="llm-router", container="llm_router_litellm"} | json | level="ERROR" [15m])) > 5`;
  - `for: 0m`, `severity: warning`;
  - `summary: "llm-router is logging errors — Explore: {host=\"llm-router\", container=\"llm_router_litellm\"} | json | level=\"ERROR\""`. The query sits in the summary because Pushover and ntfy show only the summary (spec US3 scenario 1);
  - `description`: the count over 15 min, and "Grafana → Explore → Loki: {host=\"llm-router\"} | json | level=\"ERROR\"";
  - `enabled: false`, `disabled_reason: "awaiting 7-day baseline (SC-004)"`.

  The data-model §3 fields are required.
- [X] T031 [P] [US3] In `ansible/host_vars/hermes.yml`, add `log_alert_rules` with `HermesErrorLogs`:
  - `expr: sum(count_over_time({env="prod", host="hermes", container=~"hermes_open_webui|hermes_agent"} |~ "[| ](ERROR|CRITICAL)[ |]" [15m])) > 5`;
  - `severity: warning`, `enabled: false`;
  - the `disabled_reason` as in T030.

  Add a comment that hermes_agent's `WARNING [Ntfy] Stream error … 403` lines (R8) are deliberately not matched, and that they are tracked as their own backlog item (`docs/backlog/093-hermes-agent-ntfy-403.md`, T044).
- [X] T032 [P] [US3] In `ansible/host_vars/nextcloud.yml`, add `log_alert_rules` with `NextcloudErrorLogs`:
  - `expr: sum(count_over_time({env="prod", host="nextcloud", source="file"} | json | level >= 3 [15m])) > 5`;
  - `severity: warning`, `enabled: false`, with the same `disabled_reason`.

  Add a comment that Nextcloud level 3 means error and 4 means fatal, that the R8 sample showed 3,227 level-4 lines, and that the baseline decides the threshold.
- [X] T033 [P] [US3] Add the remaining two rules, each with `severity: warning`, `enabled: false` and the same `disabled_reason`:
  - In `ansible/host_vars/immich.yml`, `ImmichErrorLogs` with `expr: sum(count_over_time({env="prod", host="immich", container="immich_server"} |~ "ERROR" !~ "VipsJpeg|ffprobe|unsupported image format" [15m])) > 5`.
  - In `ansible/host_vars/ntfy.yml`, `NtfyErrorLogs` with `expr: sum(count_over_time({env="prod", host="ntfy", container="ntfy"} |~ "level=(ERROR|FATAL)|\\bERROR\\b" [15m])) > 5`.

  Then run `bash scripts/ci/python-tests.sh` (group 6 green). Temporarily render `log_alerts.yaml.j2` with all five set to `enabled: true` (`-e` override is not possible for nested keys, so copy the host_vars into a temporary inventory directory) and run `lokitool rules check`. All five expressions must parse. Revert the temporary copy.

**Checkpoint**: the five rules are declared and parse. None is rendered until Phase 10.

---

## Phase 6: User Story 4 - An unexpected login is noticed (Priority: P1)

**Goal**: SSH logins outside the (users, key, source-class) allow-list alert, password logins on
pve included. Unexpected `sudo` alerts. Password authentication is off on every LXC.

**Independent Test**: quickstart §9. A drill key login on `market-model` alerts, and so does a
password login on pve. A pipeline deploy and the owner's normal logins do not. A password-only
attempt on every LXC is refused.

- [X] T034 [US4] In `ansible/group_vars/monitoring/vars.yml`, add `ssh_login_allowlist` and `ssh_sudo_expected` exactly as data-model §4, with the **full** fingerprints from research R3:
  - `NH5zp/61GeEPB81f+jkiTmMfTHaWrn4s4JU5MIQUwT4` (pipeline deploy key; `lxc`; users root, ansible; from proxmox);
  - `cqi3Ec4bCtvvNDN4iPe1er0NH8BTToa2PfQV7WHHwVU` and `3+LnahZMxEHmkN3uF/R5qPgFxPev6aSf1Sk6H1jyhQM` (owner; `lxc` users root, from lan and proxmox);
  - `bclAaF1GOPV0jxfGNMjdUaKQG4Mj85fv66zJ9VO9vrY` (CI runner; `proxmox` user ci, from lan);
  - `ssfuJwQz9oDVn41sWkAwZHPvux2vT5x08vnWqiIYit0`, `cqi3…` and `3+Lnah…` (owner; `proxmox` users ci and root, from lan and tailnet).

  Each key is prefixed `SHA256:`. Add a header comment: "Public key fingerprints, not secrets. Census 2026-10-24 (spec 092 R3). A password login has no key and never matches, so every password login on pve alerts (owner decision)." Only commit `3+Lnah…` if T002 confirmed it. Run `test_login_allowlist`.
- [X] T035 [US4] In `ansible/roles/monitoring_stack/templates/log_alerts.yaml.j2`, group `log_estate`, add the Jinja macro `ssh_rule(class, selector)`. It renders `SshLoginNotAllowed` for one class:
  - `expr`:

    ```text
    sum by (host, user, src, method, fp) (count_over_time({env="prod", <selector>, ident=~"sshd|sshd-session"} |= "Accepted " | regexp "Accepted (?P<method>\\S+) for (?P<user>\\S+) from (?P<src>\\S+) port \\d+ ssh2(?:: \\S+ (?P<fp>SHA256:\\S+))?" <clauses> [5m])) > 0
    ```

  - `<clauses>` is one `| (user !~ "<users joined by |>" or fp !~ "<keys regex-escaped, joined by |>" or (<source-not-in-from>))` per entry. `<source-not-in-from>` joins with ` and `: `src != "{{ proxmox_host_ip }}"` for `proxmox`, `src != ip("{{ lan_cidr }}")` for `lan`, and `src != ip("{{ tailnet_cidr }}")` for `tailnet`.
  - The keys need regex-escaping, because `+` and `/` appear in fingerprints. Use `regex_escape`, and wrap with `^…$` anchors through `fp !~ "^(…)$"`.
  - `labels.severity: warning`.
  - `summary: "Unexpected SSH login on {{ $labels.host }}: {{ $labels.user }} from {{ $labels.src }} ({{ $labels.method }} {{ $labels.fp }})"`, inside raw blocks.

  Call it twice: `ssh_rule('lxc', 'host!="proxmox"')` and `ssh_rule('proxmox', 'host="proxmox"')`. The two alert names are the same, and the selector separates them. Render it and run `lokitool rules check`. Then hand-test the clause logic in local Loki with the research R2 config (`docker run` of `grafana/loki:3.7.9`): push 4 synthetic `Accepted` lines (deploy key from .112, owner key from 192.168.1.50, drill key from .50, `password` on host proxmox) and confirm that only the last two return series. Use the real census line format (`Accepted publickey for root from 192.168.1.112 port 41488 ssh2: ED25519 SHA256:…`), and also confirm that `fp` is non-empty for the key lines (`sum by (fp)`). The literal `ssh2` is required: with `\\S+` there, `fp` is always empty (research R3).
- [X] T036 [US4] In the same file, add `SudoByUnexpectedUser`, twice, one for each class:
  - `expr: sum by (host, sudo_user) (count_over_time({env="prod", <selector>, ident="sudo"} | regexp "^\\s*(?P<sudo_user>\\S+) : " | sudo_user != "" | sudo_user != "{{ ssh_sudo_expected[class] }}" [5m])) > 0`. The `sudo_user != ""` filter drops PAM session lines (`pam_unix(sudo:session): …`), which share the `sudo` identifier and do not match the regex (research R3);
  - `severity: warning`;
  - summary "Unexpected sudo on {{ $labels.host }} by {{ $labels.sudo_user }}".

  Render it and run `lokitool rules check`. Hand-test in the same local Loki as T035: push `  ansible : PWD=/home/ansible ; USER=root ; COMMAND=/bin/true`, `pam_unix(sudo:session): session opened for user root(uid=0) by ansible(uid=1000)` and `  andreas : PWD=/ ; USER=root ; COMMAND=/bin/true` with `ident="sudo"`. Only the last returns a series.
- [X] T037 [US4] In `ansible/roles/lxc_base/tasks/main.yml`, before the Alloy include and with **no** `deploy_environment` condition, add the task "Disable SSH password and keyboard-interactive auth (spec 092 FR-015)":
  - `copy` to `/etc/ssh/sshd_config.d/10-homelab-auth.conf` (0644, root);
  - content: a header comment ("Managed by Ansible, spec 092. LXCs only; pve keeps password auth by owner decision."), then `PasswordAuthentication no` and `KbdInteractiveAuthentication no`;
  - no `validate:` on the copy, because a drop-in cannot be checked on its own. Instead, a following task checks the whole config: `command: /usr/sbin/sshd -t`, with `changed_when: false`. A failure stops the play before the handler reloads sshd;
  - notify `Reload ssh`.

  In `ansible/roles/lxc_base/handlers/main.yml`, add `- name: Reload ssh` with `ansible.builtin.service: name=ssh state=reloaded`. Run `test_sshd_lxc_only`.
- [X] T038 [US4] In `ansible/roles/monitoring_stack/files/grafana/dashboards/security-overview.json`, append three panels after panel 12 (keep existing ids):
  - a `row` panel id 13, "SSH logins and sudo (logs)", `gridPos {h:1, w:24, x:0, y:27}`;
  - a `table` panel id 14, "Accepted SSH logins (24h)", `gridPos {h:9, w:16, x:0, y:28}`, `datasource {type: "loki", uid: "loki"}`, a `range` target with `expr: {env="prod", ident=~"sshd|sshd-session"} |= "Accepted " | regexp "Accepted (?P<method>\\S+) for (?P<user>\\S+) from (?P<src>\\S+) port \\d+ ssh2(?:: \\S+ (?P<fp>SHA256:\\S+))?"`, and a `labelsToFields` transformation;
  - a `timeseries` panel id 15, "sudo calls by user", `gridPos {h:9, w:8, x:16, y:28}`, Loki data source, `expr: sum by (host, sudo_user) (count_over_time({env="prod", ident="sudo"} | regexp "^\\s*(?P<sudo_user>\\S+) : " | sudo_user != "" [1h]))`.

  Validate with `python3 -c 'import json; json.load(open(...))'`.

**Checkpoint**: US4's code is complete. `test_login_allowlist` and `test_sshd_lxc_only` are green.

---

## Phase 7: User Story 5 - The log pipeline's own failures are visible (Priority: P2)

**Goal**: Prometheus scrapes the store and every collector, and raises the R14 alerts without
depending on the store.

**Independent Test**: quickstart §10. Stopping one collector raises `LogCollectorDown` for that
host only. Stopping Loki raises `ServiceDown{job="loki"}` (critical) on Pushover.

- [X] T039 [US5] In `ansible/roles/monitoring_stack/templates/prometheus.yml.j2`, after the `node-exporter` job, add two jobs:
  - `job_name: 'loki'` with `static_configs: [{targets: ['loki:3100'], labels: {instance: 'loki'}}]`;
  - `job_name: 'alloy'`, with one target per host in `groups['services'] + groups['proxmox_hosts']`, with **no** lab condition, so a LAB-path render leaves the production targets as they are (R12): `'{{ hostvars[host].ansible_host }}:{{ alloy_http_port }}'`, `labels: {instance: '{{ host }}', no_down_alert: 'true'}`. Render each host as its own `static_configs` item so the per-host `instance` label is kept.

  Render it locally and run `promtool check config` (after copying the alerts directory, as T014 does).
- [X] T040 [US5] In `ansible/roles/monitoring_stack/templates/log_pipeline_alerts.yml.j2`, add these rules, all with `component: logging` and expressions as in research R14:
  - `LogCollectorDown`: `up{job="alloy"} == 0`, `for: 10m`, warning;
  - `LogHostSilent`: `(sum by (instance) (increase(loki_write_sent_entries_total{job="alloy"}[2h])) == 0) or (sum by (instance) (increase(loki_source_journal_target_lines_total{job="alloy"}[2h])) == 0)`, `for: 15m`, warning;
  - `LogRulesNotLoaded`: `absent(loki_prometheus_rule_group_rules{job="loki"}) or sum(loki_prometheus_rule_group_rules{job="loki"}) < N`, where `N` is computed in this template exactly as `log_alerts.yaml.j2` counts it (the estate rules: 1 OOM + 2 SSH + 2 sudo = 5, plus the enabled `log_alert_rules`). Use `for: 10m`, warning;
  - `LogRuleEvaluationFailing`: failures or iterations missed, increase over 10m > 0, warning;
  - `LogRuleNotificationsFailing`: `loki_prometheus_notifications_errors_total` or `_dropped_total`, increase over 10m > 0, warning;
  - `LogLinesDiscarded`: `sum by (reason) (increase(loki_discarded_samples_total[10m])) > 0`, info;
  - `LogLinesDiscardedSustained`: the same expression with `for: 1h`, warning;
  - `LogCollectorDropping`: `sum by (instance) (increase(loki_write_dropped_entries_total{job="alloy"}[15m])) > 0`, warning;
  - `LogRetentionStalled`: `time() - loki_compactor_apply_retention_last_successful_run_timestamp_seconds > 7200`, `for: 30m`, warning.

  Summaries must name `{{ $labels.instance }}` where it exists, inside `{% raw %}`. Render it and run promtool. Then run `bash scripts/ci/python-tests.sh`: every group of `test_log_pipeline.py` must be green.

**Checkpoint**: all code is complete and the tests are green. Commit, push through the GitHub API (`AGENTS.md`), and open the PR. No protected path is touched, so no label is needed.

---

## Phase 8: Documentation

**Purpose**: the runbook FR-016 asks for, and the record of what the estate now does.

- [X] T041 [P] Create `docs/operations/monitoring/logging.md`, the logging runbook, with these sections:
  1. Data flow: collectors → `:3101` relay → host-local Loki → Grafana and ruler → Alertmanager.
  2. Where things are: config paths, ports, labels (data-model §1).
  3. Leaked-credential procedure: quickstart §7 verbatim, with the steps rotate → delete (curl on the monitoring host) → extend patterns and corpus.
  4. Store or relay outage: what buffers where, and the 7-day backfill limit (R9).
  5. Tuning an error rule and enabling it after a baseline (quickstart §6).
  6. "Never `lokitool rules lint`" (R10).
  7. Accepted risks: Docker socket access, unauthenticated push on `:3101`, and password SSH on pve.

  Link it from `docs/operations/monitoring/quickstart.md`, and from `docs/operations/README.md` if that file indexes runbooks.
- [X] T042 [P] In `docs/architecture.md`, under "Backup & Monitoring", add a "Logging" bullet group: Loki in the monitoring stack (host-local, 30 days, not backed up), Alloy on every production host (journal, Docker, declared files, redaction on the host), the push relay, the log rules (OOM, SSH and `sudo`, per-service errors) and the pipeline alerts. Link `docs/operations/monitoring/logging.md`. In the Backup table row for `monitoring`, add "Loki keeps 30 days of logs".
- [X] T043 [P] Update the backlog files:
  - In `docs/backlog/improvement-candidates.md`, mark "Application-level error/log alerting" (line ~52) and "Login anomaly alerting" (line ~87) as delivered by `specs/092-log-aggregation/`, and note that time-of-day rules were dropped.
  - In `specs/042-*/spec.md`, add a note under its out-of-scope "Log aggregation" entry (line ~255): "Delivered separately by spec 092."
- [X] T044 [P] Create `docs/backlog/093-hermes-agent-ntfy-403.md`. It records the hermes_agent ntfy stream subscription getting `403 Forbidden` about every 3 minutes: 1,359 times in 72 h, measured 2026-10-24 (research R8), with a sample line, the likely cause (the agent's ntfy token or ACL for its topic, spec 083) and how to verify it. Add a row to `docs/backlog/backlog.md`.
- [X] T045 [P] Create `docs/backlog/094-nextcloud-log-unrotated.md`. It records that `/mnt/nextcloud/data/nextcloud.log` is 479 MB with no rotation, that fail2ban reads it, and the proposal to set `log_rotate_size` through `occ` in the nextcloud role (R8). Add a row to `docs/backlog/backlog.md`.
- [X] T046 Set the status of `docs/backlog/092-log-aggregation.md` and its row in `docs/backlog/backlog.md` to "In progress — implementation" once the PR is open.

---

## Phase 9: Rollout and live verification (quickstart order)

**Purpose**: deploy services, then pve, then monitoring, and prove every success criterion that
does not need 7 days. Record each step in quickstart §13.

- [X] T047 Run quickstart §1 static checks on the PR head: python tests, local renders, `lokitool rules check`, `alloy validate` for `ntfy`, `jellyfin`, `monitoring` and `proxmox`, promtool, and a deliberate broken `expr` that makes `lokitool` exit 1. Record the result.
- [X] T048 Deploy `market-model` through the pipeline. Run the quickstart §2 step 1 checks (`alloy` active, groups, `MemoryMax`, `sshd -T` showing both settings `no`, `connection refused` in the alloy journal because the relay does not exist yet). From the Mac, `ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no root@192.168.1.218` must give `Permission denied (publickey)`. Then confirm that a normal key login still works.
- [X] T049 Deploy the remaining LXCs through the pipeline, one at a time, running the §2 step 1 checks after each: `ntfy`, `reverse_proxy`, `jellyfin`, `eurooffice`, `financial-scenario`, `immich`, `llm-router`, `hermes`, `nextcloud`. On `nextcloud`, run §2 step 2 (`runuser -u alloy -- head -c1 /mnt/nextcloud/data/nextcloud.log`). If that is denied, add `nogroup` to the alloy user's groups for that host only, through a host_vars `alloy_extra_groups`, and record it. Do not deploy `monitoring` yet.
- [X] T050 From an operator machine, run `ansible-playbook -i inventories/prod/hosts.yml playbooks/host_proxmox.yml`. On pve, check that `alloy` is active, that `/etc/alloy/config.alloy` contains the VMID map for all 12 containers, and that `sshd -T | grep passwordauthentication` still prints `yes`.
- [X] T051 Deploy `monitoring` through the pipeline, then run quickstart §2 step 4: `loki` is Up, `/ready` answers, and Prometheus has 13 `loki` and `alloy` targets up. Then run §3 (`:3100` refused from the LAN, `:3101` query path 404, Grafana data source test OK). Within 10 minutes, every collector's `loki_write_sent_entries_total` increases. Lines logged while the relay was missing arrive with their original timestamps, which is a first FR-011 check.
- [X] T052 Run quickstart §4 (the SC-001 canary). That means 12 journal lines and 9 Docker lines, found within 60 s. Record the result per host. Record `MemoryCurrent` for `alloy` on `ntfy` and `hermes`. If `ntfy` is above 70% of `MemoryHigh`, raise `alloy_memory_high` and `alloy_memory_max` in `host_vars/ntfy.yml` and redeploy before going on.
- [X] T053 Run quickstart §5, the SC-002 redaction drill on `market-model` (journal and container). Every corpus secret must be `<redacted>` and the control lines unchanged.
- [ ] T054 Run quickstart §8, the SC-003 OOM drill on `market-model`: `KernelOomKill` with `lxc=market-model` and `task=python` on Pushover and ntfy within 5 minutes. Then run it again with Loki stopped and expect `HostOomKill`. Start Loki again.
- [ ] T055 Run quickstart §9, the SC-005 login drills:
  - the drill key on `market-model` alerts;
  - an owner password login on pve alerts with `method=password`;
  - a pipeline deploy, an owner login on the LAN, and owner tailnet logins to an LXC and to pve produce no alert;
  - a password-only attempt against all 11 LXC addresses is refused.

  Record each result.
- [ ] T056 Run quickstart §7, the SC-008 leaked-credential drill. Record the timings, and commit the new redaction pattern and corpus line through T020's files in the same PR, or in a follow-up commit.
- [ ] T057 Run quickstart §10, the SC-006 outage drills: one collector stopped, which gives `LogCollectorDown` for that host only; then Loki stopped for 30 minutes, which gives `ServiceDown{job="loki"}` on Pushover with no service restart, and all the canary lines from the outage present afterwards.
- [ ] T058 Run quickstart §11, the SC-009 LAB-path check (`lxc-deploy-lab.yml` for `market-model`). Afterwards these must be unchanged: the alloy config, the Loki container's creation time, `log_alerts.yaml`, `/opt/monitoring/prometheus/alerts/log_pipeline_alerts.yml`, and the `alloy` targets in Prometheus (`sha256sum` before and after).

---

## Phase 10: After the baseline (≥ 7 days and 14 days), and close

- [ ] T059 After at least 7 days of collection, run quickstart §6 for each of the five services. Set the threshold to `max(5, 3 × max_15m)` and update `expr`. Set `enabled: true` with `baseline: {from, to, max_15m}`, remove `disabled_reason`, redeploy monitoring, and check that `LogRulesNotLoaded` stays quiet (its count rises with the rules). Inject an error burst for each service and confirm that only that service's alert fires. A service that does not pass stays `enabled: false` with its `disabled_reason` updated to the actual finding (FR-008).
- [ ] T060 After 14 days, run quickstart §12 (SC-007): ingestion per host, the `loki_data` size, peak memory of Loki and of the collectors on `ntfy` and `hermes`, and the monitoring host's minimum `MemAvailable`. Confirm or change FR-004's limits and the collector limits, and record the result.
- [ ] T061 Close out:
  - Set `specs/092-log-aggregation/spec.md` Status to `Implemented (<date>)`.
  - Set `docs/backlog/092-log-aggregation.md` and its `docs/backlog/backlog.md` row to "Delivered", with a link to the spec, and mark `docs/backlog/079-sshd-password-auth-enabled-estate-wide.md` closed for the LXCs.
  - Confirm that quickstart §13 has every row filled.
  - Run `bash scripts/ci/python-tests.sh` and `pre-commit run --all-files` on `main` after merge.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies. T002 gates T034's third owner key.
- **Foundational (Phase 2)**: after Setup. T005 and T006 must be red before any story task. T008–T013 block every story.
- **US1 (Phase 3)**: after Phase 2. It is the MVP and the base for every other story's live test, because the rules need stored logs.
- **US2 (Phase 4)**: its code needs T022–T024 (the collector role, which T028 extends) and T010–T012 (the rules file).
- **US3 (Phase 5)**: its code needs only T010 (the `log_services` loop). T030–T033 can be written in parallel with US1 and US2.
- **US4 (Phase 6)**: T035 and T036 need T010. T034 needs T002. T037 is independent of everything except Phase 2.
- **US5 (Phase 7)**: T040's `N` needs T027, T035 and T036 to exist.
- **Docs (Phase 8)**: any time after the code exists. T044 and T045 are independent.
- **Rollout (Phase 9)**: after the PR is reviewed. Strict order: T047 → T048 → T049 → T050 → T051, then T052–T058 in any order, with T054 and T057 not overlapping (both stop Loki).
- **Phase 10**: T059 waits 7 days after T051, and T060 waits 14 days.

### Within Each Story

- `log_alerts.yaml.j2` is edited by T010, T027, T035 and T036, in that order (same file, no [P]).
- `log_pipeline_alerts.yml.j2` is edited by T011, T029 and T040, in that order.
- `config.alloy.j2` is written by T022, then T028.
- `alloy/tasks/main.yml` is written by T024, then T028.

### Parallel Opportunities

- Phase 1: T003 and T004.
- Phase 2: T008 and T009 together, after T005–T007.
- US1: T015, T018, T020, T021 and T023 together. Then T016 → T017 → T019, and T022 → T024 → T025 → T026.
- US3: T030–T033 all together.
- Docs: T041–T045 all together.

## Parallel Example: User Story 1

```bash
# After Phase 2:
Task: "T015 loki.yaml.j2 per contracts C1"
Task: "T018 Grafana Loki datasource + copy task"
Task: "T020 alloy role defaults + redaction patterns"
Task: "T021 alloy /etc/default and systemd override templates"
Task: "T023 alloy handlers"
```

## Parallel Example: User Story 3

```bash
Task: "T030 llm-router log_alert_rules"
Task: "T031 hermes log_alert_rules"
Task: "T032 nextcloud log_alert_rules"
Task: "T033 immich + ntfy log_alert_rules"
```

## Implementation Strategy

### MVP (User Story 1)

Phases 1–3 alone give searchable, redacted logs from every in-scope host, pve included. The rollout steps
T047–T053 prove them. If time is short, US1 can be merged and rolled out on its own. The rules
file then renders empty groups, which validate cleanly (T014).

### Incremental Delivery

All five stories are planned for one PR (spec: "all four capabilities in one delivery", plus
US5). The rollout is incremental by host: each LXC is checked before the next, `market-model`
first. A broken collector is fixed forward, or disabled for one host with `alloy_enabled: false`
in its host_vars, without touching the others. Error rules turn on one service at a time after
their baseline.

## Notes

- [P] = a different file, with no dependency on an incomplete task.
- Do not add a compose healthcheck for Loki (no shell, R2), a sidecar (R4), or an Alloy WAL (R9).
- Do not put `alloy_version` or `loki_version` anywhere except the two group_vars files.
- Commit after each phase. Push through the GitHub API (Zscaler, `AGENTS.md`).
