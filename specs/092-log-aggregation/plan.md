# Implementation Plan: Log Aggregation and Log-Based Alerting

**Branch**: `092-log-aggregation` | **Date**: 2026-10-24 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/092-log-aggregation/spec.md`

## Summary

Ship every production host's logs into one store next to Prometheus, make them searchable in
Grafana, and alert on them through the existing Alertmanager:

1. **Store**: Loki 3.7.9 as a sixth container in `monitoring_stack`. It is bound to
   `127.0.0.1:3100`, keeps logs for 30 days, has explicit memory limits, and runs a local-file
   ruler that posts to `alertmanager:9093`. A provisioned Grafana data source points at it.
2. **Collector**: a new `alloy` role (Alloy 1.21.2 from the pinned GitHub `.deb`), included from
   `lxc_base` on all 11 LXCs and from `host_proxmox.yml` on pve, in production only. It reads the
   journal, Docker over the socket, and declared files (Jellyfin's logs and Nextcloud's
   application log). It redacts 8 credential pattern families **on the host** and retries
   without limit.
3. **Push path**: the monitoring host's own Alloy relays pushes on `:3101` to the host-local
   Loki. The LAN can push, and only Grafana can read (FR-013, R4).
4. **Log rules**, in one ruler file:
   - kernel OOM kills from pve's journal, named by LXC through a VMID map rendered on pve;
   - SSH logins outside a (users, key, source-class) allow-list, password logins included;
   - `sudo` by an unexpected user;
   - one error-rate rule per service for `llm-router`, `hermes`, `nextcloud`, `immich` and
     `ntfy`, declared in each `monitoring_contract`, each disabled until its 7-day baseline.
5. **Self-monitoring in Prometheus**: scrape jobs `loki` and `alloy`, and one template of
   pipeline alerts (R14). Store liveness reuses `ServiceDown`. `HostOomKill` is the metric
   backstop.
6. **SSH**: an `sshd_config.d` drop-in in `lxc_base` turns password and keyboard-interactive
   authentication off on the LXCs. pve keeps password authentication (owner decision), and
   every password login there alerts.

Research ([research.md](./research.md)) changed the design in five places:

- The login census found DHCP addresses and password logins on pve. The spec's FR-009 and FR-015
  were amended after asking the owner.
- Loki has no shell and no `-health`, so there is no compose healthcheck.
- `lokitool rules lint` corrupts rule files for the local ruler, so only `check` is used.
- Nextcloud's errors exist only in its file log, which fail2ban also reads.
- A LAB render must keep the store, so FR-017 was amended.

## Technical Context

**Language/Version**: YAML (Ansible 2.x), Jinja2, Alloy config syntax, LogQL, PromQL; tests in Python 3.11 (pytest + PyYAML). No new language.

**Primary Dependencies**: Grafana Loki 3.7.9 + `lokitool`, Grafana Alloy 1.21.2 (GitHub `.deb`), existing `monitoring_stack`, `lxc_base`, `node_exporter`

- Grafana Loki 3.7.9 (image `grafana/loki`) and `lokitool` 3.7.9 (release zip, used at deploy).
- Grafana Alloy 1.21.2 (`.deb` from GitHub releases).
- Existing: `monitoring_stack` (Prometheus v3.13.5, Grafana 13.2.4, Alertmanager v0.34.1),
  `lxc_base`, `node_exporter`, `geerlingguy.docker`, `fail2ban`, and the gated pipeline with
  `scripts/lab/pve-service-deploy`.

**Storage**: `loki_data` Docker volume on the monitoring LXC rootfs (about 200 MB at 30 days); not backed up (FR-014)

The monitoring LXC rootfs has 25.9 GB free. Collector positions files sit under each host's Alloy storage path.

**Testing**:

- New guard tests in `python/tests/guardrails/test_log_pipeline.py` (text and YAML assertions on
  contract clauses marked **[test]**) and the redaction corpus test with
  `fixtures/redaction_corpus.txt`.
- `test_version_pins.py` is extended for `alloy_version`.
- At deploy: `loki -verify-config`, `lokitool rules check`, `alloy validate`, and the existing
  promtool loop for the new Prometheus rules.
- The live drills are in [quickstart.md](./quickstart.md).

**Target Platform**: Proxmox VE 9.2.3 host `pve` (Debian 13, kernel 7.0) and 11 Debian 12
unprivileged LXCs: `reverse_proxy`, `immich`, `monitoring`, `jellyfin`, `nextcloud`,
`financial-scenario`, `market-model`, `eurooffice`, `llm-router`, `hermes` and `ntfy`.

**Project Type**: Infrastructure configuration (Ansible-managed homelab).

**Performance Goals**:

- A canary line is searchable within 60 s (SC-001).
- An OOM alert arrives within 5 min (SC-003).
- Ingestion is about 7 MB/day estate-wide, against a 4 MB/s rate limit.

**Constraints**:

- `ntfy` has 512 MiB (415 MiB available): the collector runs with `MemoryMax=160M`.
- The monitoring LXC has 4 GiB (3.4 GiB available): Loki runs with `mem_limit: 1g`.
- Loki rejects samples older than 7 days.
- pve changes run only from an operator machine (principle V exception, as `091` recorded).
- `scripts/lab/**` is protected and is not changed.
- The Mac cannot `git push` (Zscaler): push through the GitHub API (`AGENTS.md`).

**Scale/Scope**:

- 12 hosts and about 25 containers.
- 1 new role (`alloy`), 6 new templates (`loki.yaml.j2`, `log_alerts.yaml.j2`,
  `log_pipeline_alerts.yml.j2`, `config.alloy.j2`, `alloy.default.j2`, `alloy-override.conf.j2`), 1 new data source
  file and 2 new test files.
- About 20 files edited.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Spec-driven workflow | PASS | Work comes from `specs/092-*`. The spec was amended where the census changed facts, after the owner's answers. Docs (runbook in quickstart §7, `architecture.md` logging section, backlog closures) ship in the same change. |
| II. Secrets policy | PASS | No new secret. Push is unauthenticated, on purpose (R4: LAN push only, reads stay local). Credentials are redacted on the host before shipping (FR-005), proven by the corpus test and the drill. Key fingerprints in the allow-list are public values. The redaction corpus holds synthetic values only. |
| III. Separation of concerns | PASS | Ansible only. No Terraform change: VMIDs are read from Proxmox at deploy, not pinned (R6). |
| IV. Code economy | PASS | One collector role with 12 consumers. **No sidecar**: the relay is the collector that the monitoring host runs anyway (R4). Store liveness **reuses** `ServiceDown` (R2). Per-service log rules **extend** `monitoring_contract`. Login panels **extend** `security-overview.json`. One rules file, one pipeline-alert template. `HostOomKill` sits in that template, not in a new file. No dashboard is added. |
| V. Dual-provisioning parity | PASS through the documented-exception clause | Services and monitoring go through the pipeline and through `pve-service-deploy` locally, unchanged. pve (`host_proxmox.yml`) is operator-only, the existing exception recorded by `089` and `091` (CI has no root on pve). No new service, so no change to dropdowns or the scope allow-list. |
| CI/CD: no destructive automation without barriers | PASS | Nothing is deleted. The sshd drop-in is validated with `sshd -t` before reload, and `pct enter` stays the recovery path. The delete API is used only by hand (runbook). |
| Test-driven changes | PASS | Guard tests for every contract clause marked [test], a redaction corpus test, deploy-time validators that fail before any restart, and live drills for every SC. The LogQL syntax check is not in CI (PyYAML-only test environment). It runs locally before merge (quickstart §1) and at deploy. A CI step is a follow-up. |

**Post-design re-check (after Phase 1)**: all PASS.

- The relay decision avoided a new container.
- The OOM name mapping avoided a Terraform change.
- The 2-hour silent-host window is driven by data (the census), not guessed.
- The one new template that could have been static (`log_pipeline_alerts.yml.j2`) has to be a
  template, because it needs the rule count, the lab switch and `proxmox_host_ip`.

## Project Structure

### Documentation (this feature)

```text
specs/092-log-aggregation/
├── plan.md                    # This file
├── research.md                # Phase 0: R1–R15
├── data-model.md              # Streams, collector, rule declaration, allow-list, redaction, delete
├── quickstart.md              # Static checks, rollout order, drills for SC-001…SC-009, runbook
├── contracts/
│   └── log-pipeline.md        # C1–C7
├── checklists/
│   └── requirements.md
└── tasks.md                   # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
ansible/
├── version-sources.yml                              # + loki_version, alloy_version
├── group_vars/all/vars.yml                          # + alloy_version, alloy_http_port, lan_cidr, tailnet_cidr, monitoring_host_ip
├── group_vars/monitoring/vars.yml                   # + loki_version, ssh_login_allowlist, ssh_sudo_expected
├── host_vars/
│   ├── {llm-router,hermes,nextcloud,immich,ntfy}.yml   # + monitoring_contract.log_alert_rules (enabled: false)
│   ├── nextcloud.yml                                # + alloy_file_logs (nextcloud.log)
│   ├── jellyfin.yml                                 # + alloy_file_logs, alloy_docker_logs: false
│   ├── reverse_proxy.yml                            # + alloy_docker_logs: false
│   ├── proxmox.yml                                  # + alloy_docker_logs: false
│   └── monitoring/vars.yml                          # + alloy_relay: true
├── roles/alloy/                                     # NEW
│   ├── defaults/main.yml                            #   memory limits, journal max_age, redaction patterns
│   ├── handlers/main.yml                            #   validate + restart alloy
│   ├── tasks/main.yml                               #   .deb + checksum, groups, files, pve VMID map, service
│   └── templates/
│       ├── config.alloy.j2                          #   sources → redaction → write (+ relay, + pve OOM map)
│       ├── alloy.default.j2                         #   /etc/default/alloy CUSTOM_ARGS
│       └── alloy-override.conf.j2                   #   MemoryHigh / MemoryMax
├── roles/lxc_base/
│   ├── tasks/main.yml                               # + sshd drop-in, + include alloy (prod only)
│   └── handlers/main.yml                            # + Reload ssh
├── roles/monitoring_stack/
│   ├── defaults/main.yml                            # + loki paths/limits; monitoring_ip → "{{ monitoring_host_ip }}"
│   ├── templates/docker-compose.yml.j2              # + loki service, loki_data volume
│   ├── templates/loki.yaml.j2                       # NEW (C1)
│   ├── templates/log_alerts.yaml.j2                 # NEW (C4)
│   ├── templates/log_pipeline_alerts.yml.j2         # NEW (C5, R14)
│   ├── templates/prometheus.yml.j2                  # + loki and alloy jobs
│   ├── tasks/create_directories.yml                 # + loki config/rules dirs
│   ├── tasks/compose_stack.yml                      # + render loki config, rules (prod), pipeline alerts
│   ├── tasks/validate_alerts.yml                    # + lokitool install, -verify-config, rules check
│   ├── tasks/grafana_provision.yml                  # + loki datasource copy task
│   ├── tasks/verify.yml                             # + 127.0.0.1:3100/ready
│   ├── files/grafana/provisioning/datasources/loki.yml   # NEW
│   └── files/grafana/dashboards/security-overview.json   # + SSH login / sudo log panels
└── playbooks/host_proxmox.yml                       # + alloy role (prod only)
python/tests/guardrails/
├── test_log_pipeline.py                             # NEW (contract [test] clauses, redaction corpus)
├── fixtures/redaction_corpus.txt                    # NEW
└── test_version_pins.py                             # ALL_VARS + alloy_version
docs/
├── architecture.md                                  # + logging section (data flow, ports, what is not collected)
├── operations/monitoring/logging.md                 # NEW runbook: leaked-credential purge (quickstart §7), outage, rule tuning
└── backlog/{improvement-candidates,092-*,079-*,042 ref}.md   # mark delivered/closed
```

**Structure Decision**: one new role, `alloy`, because 12 hosts consume it. Everything on the
monitoring side edits the role that already owns the behaviour. Per-service knowledge goes into
`host_vars` next to each existing `monitoring_contract`. The only new doc is the runbook
FR-016 asks for.

## Implementation Notes

### Collector role (R5, R6, R7, R9)

- `tasks/main.yml`, in order:
  1. Assert `deploy_environment != 'lab'`. The caller also gates, so this guards against misuse.
  2. Ensure the `docker` system group exists when `alloy_docker_logs`. If `docker` is
     installed, fail when any running container lacks the `max-size` log option (FR-003, R9).
  3. `get_url` the `.deb` with `checksum: sha256:<SHA256SUMS URL>`, then install it with
     `apt deb=`. Check the installed version first, like the version check in `node_exporter`.
  4. Add `alloy` to its groups.
  5. Template `/etc/default/alloy`, the systemd override and `/etc/alloy/config.alloy`.
  6. On `proxmox_hosts` only, before step 5: `command: pct list`, parsed into
     `alloy_vmid_names`.
  7. Notify the handler, which runs `alloy validate /etc/alloy/config.alloy`, then
     daemon-reload and restart.
  8. On `nextcloud`: `runuser -u alloy -- test -r` for each declared file, failing with a message
     that points at quickstart §2.2.
- `config.alloy.j2` structure:

  ```text
  journal → loki.relabel (env/host/service/source/ident/unit; drop *.scope) → loki.process "redact"
  docker (if) → discovery.docker → loki.source.docker (container label) → loki.process "redact"
  files (if) → local.file_match → loki.source.file → loki.process "redact"
  pve only: loki.process "oom" stage.match {ident="kernel"} |= "oom-kill:" → regex vmid → template map → structured_metadata lxc
  loki.process "redact" = stage.limit (per-host throttle, drop=false) → one stage.replace per alloy_redaction_patterns → loki.write (max_backoff_retries = 0)
  relay (monitoring only): loki.source.api :{{ alloy_relay_port }} (use_incoming_timestamp) → loki.write 127.0.0.1:3100
  ```

- `lxc_base`: the sshd drop-in task and its `Reload ssh` handler come first, on every path.
  Then `include_role: alloy` with `when: (deploy_environment | default('prod')) != 'lab' and
  (alloy_enabled | default(true))`.

### Monitoring stack (R2, R4, R10, R12, R14, R15)

- Compose: add the `loki` service (C1). Grafana gets no `depends_on` on it, because a store
  outage must not block Grafana.
- `compose_stack.yml`:
  - render `loki.yaml.j2` (every path);
  - render `log_alerts.yaml.j2` to `{{ loki_rules_path }}/fake/log_alerts.yaml`, with
    `when: prod`;
  - render `log_pipeline_alerts.yml.j2` into Prometheus `alerts/`, with `when: prod`. A
    LAB-path run leaves the production file untouched (FR-017, R12). The `alloy` scrape job in
    `prometheus.yml.j2` lists the same hosts on every path.
- `validate_alerts.yml`, run before `docker compose up -d`:
  1. ensure `lokitool` (`get_url` of the zip with checksum, `unarchive`, compare the version);
  2. `docker run --rm -v …:/etc/loki:ro grafana/loki:{{ loki_version }} -config.file=/etc/loki/loki.yaml -verify-config`;
  3. `lokitool rules check {{ loki_rules_path }}/fake/log_alerts.yaml` (prod only);
  4. the existing promtool loop picks up `log_pipeline_alerts.yml`.
- Rule changes reach the ruler through its 1-minute poll. Config changes restart the stack
  through the existing handler.
- `security-overview.json`: add two log panels from the Loki data source: accepted SSH logins
  (table of host, user, source, method, key) and `sudo` callers. They sit next to the fail2ban
  panels.

### Login rules (R3, C4)

- `log_alerts.yaml.j2` loops `ssh_login_allowlist.lxc` and `.proxmox`. Each entry becomes one
  negated clause:

  ```text
  (user !~ "<users>" or fp !~ "<keys>" or <source not in from>)
  ```

  where `<source not in from>` is built from:
  - `src != "{{ proxmox_host_ip }}"`
  - `src != ip("{{ lan_cidr }}")`
  - `src != ip("{{ tailnet_cidr }}")`

  joined with `and`.
- Key fingerprints are regex-escaped (`+`, `/`) in the template with a filter, not by hand.
- `SudoByUnexpectedUser`:
  `{ident="sudo"} | regexp "^\\s*(?P<sudo_user>\\S+) : " | sudo_user != "" | sudo_user != "<expected>"`,
  with `count_over_time [5m] > 0`, per host class. The `!= ""` filter drops the PAM session
  lines that share the `sudo` identifier (R3).
- The SSH regex ends `port \\d+ ssh2(?:: \\S+ (?P<fp>SHA256:\\S+))?`. The literal `ssh2` is
  required, or the fingerprint is never captured (R3).

### Rollout

Order: services → pve → monitoring (quickstart §2). Collectors installed earlier retry until the
relay exists, which exercises FR-011 before anyone relies on it. The `alloy` scrape targets
appear only with the monitoring deploy, after every collector exists, so `LogCollectorDown`
does not fire during rollout. Error rules ship disabled. They are enabled one service at a time
after 7 days (quickstart §6). SC-007 is recorded at 14 days.

## Risks

| Risk | Mitigation |
|------|------------|
| One bad rule file stops every log rule (R10) | `lokitool rules check` at deploy before anything changes. `LogRulesNotLoaded` compares the loaded count with the rendered count. `lint` is never used (guard test). |
| A collector without its groups ships nothing and stays green | SC-001 canary per host and `LogHostSilent` on journal lines (2 h window; the census shows hourly cron lines). |
| Alloy (about 52 MiB idle, more with three sources) squeezes `ntfy` | `MemoryHigh=128M` and `MemoryMax=160M`, measured at quickstart §4 before going further. If `MemoryMax` is hit, the collector is killed, not the service. |
| The sshd drop-in locks the pipeline out of an LXC | The drop-in only removes password methods, and every observed login is by key (census). `sshd -t` before reload. `pct enter` is the recovery path. Rolled out on `market-model` first. |
| The pve VMID map goes stale after a new LXC | The alert falls back to the VMID. The map is refreshed on every pve deploy. |
| The Nextcloud log is unreadable for `alloy` on NFS, or has multi-MB lines | Checked at deploy (fails loudly). The `nogroup` fallback. Loki truncates lines over 256 KB. |
| Unauthenticated push on `:3101` lets a LAN device inject fake log alerts | Accepted (R4): it cannot read or delete. Ingestion limits plus MR-004. Recorded in `architecture.md`. |
| Docker socket access makes the collector root-equivalent on 8 Docker LXCs and on monitoring | Accepted (FR-010), recorded in `architecture.md`. The collector has no inbound control surface beyond the read-mostly UI on `:12345`, and the config holds no secrets. |
| A first start ships 7 days of journal history in a burst | Bounded by the 4/8 MB/s limits. 429s are retried. Old lines have old timestamps, so they do not trip the `[5m]` rules. |
| A LAB-path monitoring render changes production log monitoring | It cannot. The store renders on every path. The Loki rules file and `log_pipeline_alerts.yml` are not rendered on the LAB path. The `alloy` scrape targets are path-independent (R12). Checked by SC-009 and T058. |
| A flooding host is throttled by the per-host `stage.limit` | `drop = false`: nothing is lost, the excess waits on that host's disk. The rate (200 lines/s) is well over 100× the busiest host's average (R9). |

## Follow-ups (not in this feature)

- **New backlog candidate**: hermes-agent's ntfy subscription gets `403 Forbidden` about every
  3 minutes (1,359 times in 72 h, R8).
- **New backlog candidate**: Nextcloud's `nextcloud.log` on the NAS is 479 MB with no rotation
  (R8). Set `log_rotate_size`. fail2ban keeps working.
- pve keeps `PermitRootLogin yes` and password authentication (owner decision). Revisit if a
  password login alert ever turns out to be unexpected.
- A LogQL check in CI (download `lokitool` in `ci.yml`).
- Joining multi-line stack traces (`stage.multiline`), per service, once the error rules show
  which traces matter (spec edge case, deferred).
- Caddy access logs, the Synology NAS and Logs Drilldown (pattern ingester), each after SC-007's
  measurements.

## Complexity Tracking

No constitution violations to justify.
