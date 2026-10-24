# Research: Log Aggregation and Log-Based Alerting

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Date**: 2026-10-24

Sources:

- The repo on branch `092-log-aggregation`.
- Read-only checks on the live estate on 2026-10-24, from `ci@pve` with `pct exec`.
- Upstream release feeds and documentation, fetched the same day.
- A local trial on the dev Mac (Docker Desktop) of the exact store and collector versions
  chosen. The trial validated the store configuration, a rule file, the delete API, the
  redaction stages and memory at idle. Its configs were throwaway and are not committed. The
  committed templates follow [contracts/log-pipeline.md](./contracts/log-pipeline.md).

## R1 — Versions and pins (FR-001)

- **Finding**: the latest releases are Loki **v3.7.9** (2026-10-20) and Alloy **v1.21.2**
  (2026-10-22). Loki's release assets include `lokitool-linux-amd64.zip`. Alloy ships
  `alloy-1.21.2-1.amd64.deb` with a `SHA256SUMS` file. Promtail is end-of-life (backlog item).
- **Finding**: `test_version_pins.py` collects every `*_version` key in
  `group_vars/monitoring/vars.yml` automatically. In `group_vars/all/vars.yml` it collects only
  `node_exporter_version`, which is hard-coded in `ALL_VARS` and in `test_every_pin_has_a_source`.
- **Decision**:
  - `loki_version: "3.7.9"` goes in `group_vars/monitoring/vars.yml`. It pins the image and the
    `lokitool` binary used at deploy (R10).
  - `alloy_version: "1.21.2"` goes in `group_vars/all/vars.yml` beside `node_exporter_version`,
    because Alloy runs on every host, the Proxmox host included.
  - Both get entries in `ansible/version-sources.yml` (`policy: latest`, `github: grafana/loki`
    and `grafana/alloy`). The guard test's `ALL_VARS` and its `all/vars.yml` collection gain
    `alloy_version`.
- **Alternatives considered**: putting Alloy's pin in `monitoring/vars.yml`. Rejected: hosts
  outside the `monitoring` group could not see it.

## R2 — Store configuration (FR-004, FR-016)

Trialled locally with `grafana/loki:3.7.9`: `-verify-config` returned 0, a pushed line was found,
a rule loaded and was evaluated, and a delete request was accepted.

- **Finding**: the image has **no shell** (`exec: "sh": executable file not found`) and **no
  `-health` flag**. The backlog's `loki -health` does not exist in 3.7.9. A compose healthcheck
  is therefore not possible.
- **Finding**: retention needs `compactor.retention_enabled: true` and `delete_request_store`.
  Without them, Loki keeps logs forever. The delete API is registered only when retention is on.
  `deletion_mode` defaults to `filter-and-delete`. **A deleted line disappears from query
  results as soon as the request is accepted**, which was observed in the trial. Physical removal
  happens after `delete_request_cancel_period`, 24 h by default.
- **Finding**: idle memory in the trial was 91–95 MiB.
- **Decision** (the full key list is in [contracts/log-pipeline.md](./contracts/log-pipeline.md) C1):
  - Monolithic mode, `auth_enabled: false`, filesystem storage, TSDB, `schema: v13`, 24 h index
    period.
  - `retention_period: 720h`.
  - `delete_request_cancel_period: 10m`, so FR-016's purge finishes within the drill.
  - `ingester.wal.replay_memory_ceiling: 256MB`. The default would size the ceiling to the whole
    LXC.
  - Chunk cache off. Results cache embedded, at 32 MB.
  - `ingestion_rate_mb: 4` and `ingestion_burst_size_mb: 8`, against an estate-wide average of
    about 0.1 KB/s.
  - `per_stream_rate_limit: 1MB`, `max_global_streams_per_user: 5000`,
    `reject_old_samples_max_age: 168h`.
  - `max_line_size: 256KB` with `max_line_size_truncate: true`, because Nextcloud lines reach MBs
    (R8).
  - Pattern ingester off. Analytics reporting off.
  - Container `mem_limit: 1g`. The monitoring LXC had 3.4 GiB available on 2026-10-24.
  - Store liveness comes from Prometheus scraping `loki:3100/metrics` (job `loki`). The existing
    `ServiceDown` rule is already `critical` for any `up == 0`, so it **is** MR-001. No new rule
    is needed (constitution IV).
- **Alternatives considered**: a `wget` healthcheck, which is impossible without a shell. A
  sidecar health prober, which duplicates `ServiceDown`.

## R3 — Login census, tailnet source NAT, and the allowed list (FR-009, FR-015)

Census: 30 days of `Accepted …` lines from `sshd`/`sshd-session`, and `sudo` callers, on all 11
LXCs and the Proxmox host (2026-10-24).

| Host(s) | User | From | Key (SHA256) | What it is |
|---|---|---|---|---|
| all 11 LXCs | `root`, `ansible` | 192.168.1.112 (pve) | `NH5zp/61GeEPB81f+jkiTmMfTHaWrn4s4JU5MIQUwT4` | Pipeline deploy key, used from `pve` |
| 9 LXCs | `root` | 192.168.1.177 | `cqi3Ec4bCtvvNDN4iPe1er0NH8BTToa2PfQV7WHHwVU` | Owner (`jacobsen.andreas@gmail.com`, the Terraform-injected key) from the dev Mac |
| hermes | `root` | 192.168.1.106 | `3+LnahZMxEHmkN3uF/R5qPgFxPev6aSf1Sk6H1jyhQM` | Owner device (owner, 2026-10-24) |
| pve | `ci` | 192.168.1.116 and .117 | `bclAaF1GOPV0jxfGNMjdUaKQG4Mj85fv66zJ9VO9vrY` | CI runner (`pi-runner`), DHCP |
| pve | `ci` | 192.168.1.177 | `ssfuJwQz9oDVn41sWkAwZHPvux2vT5x08vnWqiIYit0` | Owner's `ci` key on the dev Mac |
| pve | `ci` | 192.168.1.106 | `3+Lnah…` (as above) | Owner device |
| pve | `root` | 192.168.1.177 | `cqi3…` (as above) | Owner |
| pve | `root` (2×), `ci` (1×) | .177, .106 | **password** | Owner. pve keeps password authentication (clarification) |

- `sudo`: only `ansible` on LXCs (149–3,479 calls per host) and only `ci` on pve (2,928). The
  `monitoring` LXC has no `ansible` logins and no `sudo` at all.
- **Tailnet source NAT**: `tailscale debug prefs` on pve shows `"NoSNAT": false`. Tailnet SSH to
  an LXC therefore arrives from 192.168.1.112, the same address the pipeline uses. The key tells
  them apart.
- **sshd state**: `passwordauthentication yes` on every LXC and on pve. `/etc/ssh/sshd_config.d/`
  is empty everywhere. pve also has `PermitRootLogin yes`.
- **Decision**:
  - The allowed list is keyed on **(users, key fingerprints, source class)**. The source classes
    are `proxmox`, meaning the Proxmox host's address (`proxmox_host_ip`); `lan`, meaning any
    address in `lan_cidr`, a new central variable set to `192.168.1.0/24`; and `tailnet`
    (`tailnet_cidr`, `100.64.0.0/10`), for tailnet SSH to pve itself, which is not NATed. No rule
    names a LAN address.
  - The owner's three keys are allowed from `lan` and `proxmox` on the LXCs, and from `lan` and
    `tailnet` on pve. The deploy key is allowed from `proxmox` only. The runner key is allowed
    for `ci`, from `lan`.
  - Line formats were checked with Go's `regexp`, the engine Loki uses, against real census
    lines:
    - SSH: `Accepted (?P<method>\S+) for (?P<user>\S+) from (?P<src>\S+) port \d+ ssh2(?:: \S+ (?P<fp>SHA256:\S+))?`
      gives the full fingerprint for key logins, and `fp=""` with `method="password"` for
      password logins. A first draft used `\S+` in place of `ssh2`; that swallowed the colon
      and left `fp` empty for every login.
    - `sudo`: the journal's `sudo` identifier also carries PAM lines
      (`pam_unix(sudo:session): session opened …`). These do not match
      `^\s*(?P<sudo_user>\S+) : `, so `sudo_user` is empty. Every `sudo` rule and panel therefore
      filters `sudo_user != ""` before comparing.
  - Verified end to end in a local Loki 3.7.9 (`/speckit-analyze` follow-up, 2026-10-24) with
    the rendered clause shape (contracts C4).
    - LXC rule, these alert: a drill key from the LAN, and the deploy key used from the LAN.
      These do not: the deploy key from pve, and the owner key from the LAN.
    - pve rule: a root password login alerts. The owner's `ci` key over the tailnet (`100.x`)
      does not.
    - `sudo` rule: only `andreas` alerts, not the `ansible` line and not the PAM line.
    - Fingerprints need `+` escaped in the `fp !~` regex (`regex_escape`).
  - A password login has no fingerprint, so it never matches and always alerts. On pve that
    makes every password login visible (owner decision). On the LXCs password authentication is
    off (FR-015).
  - The list lives in `group_vars/monitoring/vars.yml`, its only consumer, as
    `ssh_login_allowlist`. Shape: data-model §4.
- **Alternatives considered**: per-address entries. Rejected because DHCP changes them (owner).
  Keying on key fingerprint alone. Rejected: the deploy key used from a LAN machine would then
  pass, and the spec asks for a source.

## R4 — How collectors reach the store without exposing it (FR-013)

- **Finding**: Loki has one HTTP port, which serves push, query, rules and **delete**, with no
  authentication. Publishing it on the LAN would make the LAN a second, unauthenticated
  interface to every log line, and would let anyone on the LAN delete logs. Today Prometheus,
  Alertmanager and Grafana's port are published on the LAN, but they hold metrics, not log text.
- **Decision**: Loki is published on **`127.0.0.1:3100` only**. Grafana and Prometheus reach it
  as `loki:3100` on the compose network, and deploy validation and the FR-016 runbook use
  localhost. The monitoring host's own Alloy, installed there anyway as its collector, also runs
  a **`loki.source.api` relay on `:3101`**. That relay accepts only the push API and forwards to
  `127.0.0.1:3100`. Every other collector pushes to `http://<monitoring>:3101/loki/api/v1/push`.
  Nothing else is added: the relay is the collector that already has to run on that host.
- **Consequence**: an outage of the relay looks the same as an outage of the store (R9). Both run
  on the same LXC, so this adds no new failure domain. The relay keeps the incoming labels and
  timestamps (`use_incoming_timestamp = true`).
- **Accepted risk**: anyone on the LAN can push lines to `:3101`. That could fake a log alert
  or use up ingestion limits. Limits and MR-004 bound it. It cannot read or delete logs.
- **Alternatives considered**:
  - An nginx sidecar with a path allow-list: a new container and a new pin for what the relay
    does already.
  - A host firewall allow-list: no firewall pattern exists in the repo, Docker-published ports
    bypass `INPUT`, and it would still leave queries open from every collector host.
  - Routing through Caddy: ruled out by FR-013.

## R5 — Collector install and placement (FR-002, FR-010, FR-017)

- **Finding**: every service playbook runs `lxc_base` first, and `lxc_base` includes
  `node_exporter` with `include_role`. `host_proxmox.yml` applies `proxmox_host`, `node_exporter`
  and `tailscale_host`. The Docker role runs **after** `lxc_base` on all 8 Docker hosts. The
  monitoring playbook installs Docker inside `monitoring_stack`. `proxy` and `jellyfin` have no
  Docker. The PVE host is Debian 13 (trixie), and the LXCs are Debian 12.
- **Finding**: Alloy's journal source starts cleanly and collects nothing without the `adm` and
  `systemd-journal` groups (upstream). Alloy listens on `127.0.0.1:12345` by default.
- **Decision**:
  - New role **`alloy`**, installed from the pinned GitHub `.deb` with the checksum from the
    release's `SHA256SUMS`. This is the same pattern as `node_exporter`: no third-party apt
    repository on the hypervisor, an exact pin, and `090`'s currency check reads GitHub.
  - Included from `lxc_base`, after `node_exporter`, when
    `(deploy_environment | default('prod')) != 'lab'`. On pve it is added to `host_proxmox.yml`
    with the same `when`.
  - The `alloy` user gets `adm` and `systemd-journal`. On hosts with `alloy_docker_logs: true`
    (the default) it also gets `docker`. The role creates `docker` as a system group if it does
    not exist yet, so the membership is in place before the Docker role runs on a fresh build,
    and discovery connects once the socket appears. `host_vars/reverse_proxy.yml`,
    `host_vars/jellyfin.yml` and `host_vars/proxmox.yml` set `alloy_docker_logs: false`.
  - Docker logs are read with `discovery.docker` and `loki.source.docker` over the socket. Both
    options need the socket, so the collector is root-equivalent on Docker hosts. This is
    **recorded as an accepted risk** (FR-010). The API source labels containers by name without
    path parsing.
  - systemd drop-in: `MemoryHigh=128M`, `MemoryMax=160M`. The trial collector used 52 MiB with
    one source. Measured on `ntfy` in quickstart §4 and revisited at SC-007.
  - `/etc/default/alloy`: `CUSTOM_ARGS="--server.http.listen-addr=<host ip>:12345
    --disable-reporting"`, so Prometheus can scrape it. The UI on that port shows the config,
    which holds no secrets.
  - Config is checked with `alloy validate` before restart.
- **Alternatives considered**:
  - Grafana's apt repository: adds a third-party repository to the hypervisor, and unattended
    upgrades could move the version.
  - Running Alloy as a container: it needs the host journal and the Docker socket either way,
    and `proxy` and `jellyfin` have no Docker.
  - Placing the role at the end of each playbook: 11 edits instead of 1.
  - Tailing json-files with `loki.source.file`: still needs the socket for container names.

## R6 — OOM kills (FR-007, US-2)

- **Finding**: the kernel writes `oom-kill:constraint=…,oom_memcg=…,task_memcg=/lxc/<vmid>/…,task=<comm>,pid=…,uid=…`
  for every OOM kill, whatever caused it (backlog Research notes, `mm/oom_kill.c`).
  `/sys/fs/cgroup/lxc/<vmid>` exists on pve for all 12 containers, so the path layout holds.
  pve's journal has **no** `oom-kill:` line ever. VMIDs are **not** pinned in Terraform; Proxmox
  assigns them (`pct list`: 100 jellyfin … 111 ntfy).
- **Finding** (trial): this LogQL extracted `lxc="111"` and `task="stress"` from a synthetic line:
  `sum by (lxc, task) (count_over_time({…} |= "oom-kill:constraint=" | regexp `task_memcg=/lxc/(?P<lxc>[0-9]+)/.*,task=(?P<task>[^,]+),` [5m])) > 0`.
- **Decision**:
  - The name mapping happens **on pve, at collection**. The `alloy` role on pve reads `pct list`
    at deploy and renders a VMID→name map into the pipeline for kernel `oom-kill:` lines. The
    pipeline sets structured metadata `lxc=<name>`. It falls back to the VMID for an unknown VMID
    and to `host` for a non-LXC cgroup.
  - The rule groups by `lxc` and `task`. A container created after the last pve deploy is named
    by VMID until the next pve deploy, and still alerts.
  - Backstop: a Prometheus rule `HostOomKill` (`warning`) on
    `increase(node_vmstat_oom_kill{instance="<proxmox_host_ip>:9100"}[10m]) > 0`. It uses the
    pve instance only, because the counter is host-wide in every LXC too and would fire 12
    times.
- **Alternatives considered**: `label_replace` chains in the rule. The monitoring deploy cannot
  see VMIDs. Pinning VMIDs in Terraform: out of scope, and it changes existence (constitution
  III).

## R7 — Redaction (FR-005, SC-002)

- **Finding** (trial, Alloy v1.21.2): `stage.replace` replaces **only the capture group**. All
  nine FR-005 formats in a 10-line corpus were redacted, and the control line was unchanged:

  ```text
  drill-1 GET /api Authorization: Bearer <redacted> ok
  drill-2 pvesh call with Authorization: PVEAPIToken=<redacted>
  drill-3 ntfy publish token <redacted> done
  drill-4 litellm key <redacted> used
  drill-5 tailscale up --authkey=<redacted>
  drill-6 GET /alerts?auth=<redacted>&x=1 200
  drill-7 GET /v1/x?token=<redacted> 200
  drill-8 DATABASE_URL=postgresql://litellm:<redacted>@llm_router_postgres:5432/litellm
  drill-9 DOMENESHOP_TOKEN=<redacted> DOMENESHOP_SECRET=<redacted> JELLYFIN_PASSWORD=<redacted> API_KEY=<redacted>
  drill-10 plain line with no secret, user=andreas path=/var/lib/x
  ```

- **Decision**:
  - The patterns are data: `alloy_redaction_patterns` in `roles/alloy/defaults/main.yml`, a list
    of `{name, expression}`. The role is their only consumer. The config template renders one
    `stage.replace` per entry, in every pipeline (journal, Docker, files) before `loki.write`.
  - A guard test applies every pattern with Python `re` to a committed corpus
    (`python/tests/guardrails/fixtures/redaction_corpus.txt`). Each positive line must lose its
    secret and keep the rest, and the control lines must be unchanged. The patterns use only
    syntax that RE2 and Python share.
  - `loki.secretfilter` is not used (backlog: documented false positives and negatives).
- **Alternatives considered**: redacting in Loki, which is too late because the secret has
  already left the host. Redacting in the ruler: does not exist.

## R8 — Per-service error sources and baseline (FR-008, SC-004)

72-hour sample on 2026-10-24 of container output and of Nextcloud's log file. Lines were
matched case-insensitively on error, exception, traceback, fatal, panic and critical:

| Service | Source | Lines (72 h) | Matches | Dominant pattern |
|---|---|---|---|---|
| llm-router | `llm_router_litellm` stdout | 25,829 | 7 | JSON `"level":"ERROR"`, Postgres connection error |
| hermes | `hermes_open_webui` | 17,227 | 4 | `\| ERROR \|` connection error to hermes-agent |
| hermes | `hermes_agent` | 2,848 | 1,386 | **1,359 × `WARNING … [Ntfy] Stream error: Client error '403 Forbidden'`** |
| nextcloud | container stdout | 22,261 | 0 | Apache access only |
| nextcloud | `/mnt/nextcloud/data/nextcloud.log` | 6,447 lines, **479 MB** | levels 0:1964, 1:1065, 2:42, 3:149, 4:3227 | JSON per line, some lines several MB |
| immich | `immich_server` | 1,293 | 76 | media decode errors (`VipsJpeg`, `ffprobe`) |
| ntfy | `ntfy` | 4,293 | 0 | — |

- **Finding**: Nextcloud's application errors go **only** to its log file, on the NAS
  (`640 nobody:nogroup`). fail2ban's nextcloud jail reads that file
  (`host_vars/nextcloud.yml:18`), so switching Nextcloud to `errorlog` would break fail2ban.
- **Finding**: hermes-agent's ntfy subscription has been refused with 403 about every 3 minutes.
  This is a live defect, outside this feature. It is reported to the owner as a new backlog
  candidate. The hermes rule matches `ERROR` and above, so this `WARNING` does not trip it.
- **Decision**:
  - Nextcloud's file is collected with `loki.source.file` from `/mnt/nextcloud/data/nextcloud.log`,
    starting at the end (`tail_from_end = true`), declared in `host_vars/nextcloud.yml`
    `alloy_file_logs`. Jellyfin's `/var/log/jellyfin/*.log` uses the same mechanism.
  - Read access is checked at deploy with `runuser -u alloy -- test -r`. If the NFS squash
    setting denies it, the fallback is the `nogroup` supplementary group, decided at quickstart
    §0.2. Loki truncates lines over 256 KB (R2).
  - Initial selectors, to be tuned against the baseline:
    - llm-router: `| json | level="ERROR"`.
    - hermes: `{container="hermes_open_webui"} |~ "\\| (ERROR|CRITICAL) "` plus
      `{container="hermes_agent"} |~ " (ERROR|CRITICAL) "`.
    - nextcloud: `| json | level >= 3`.
    - immich: `{container="immich_server"} |~ "ERROR" !~ "VipsJpeg|ffprobe|unsupported image format"`.
    - ntfy: `|~ "level=(ERROR|FATAL)|\\bERROR\\b"`.
  - Thresholds are set from the 7-day baseline: the highest 15-minute count observed, times 3,
    with a minimum of 5. All five are declared `enabled: false` until their baseline passes
    (quickstart §6).
- **Alternatives considered**: `log_type = errorlog` for Nextcloud. Rejected because it breaks
  fail2ban's nextcloud jail.

## R9 — Back-pressure and how much an outage can lose (FR-011, backlog Open Question 1)

- **Finding** (upstream): `loki.write` defaults to 10 retries and then drops (counted in
  `loki_write_dropped_entries_total`). `max_backoff_retries = 0` retries forever. The queue is in
  memory (10 MiB per shard), and its overflow behaviour defaults to **blocking**, which applies
  back-pressure to the sources. The sources keep positions: the journal cursor, the file offset
  and the Docker since-time. The Alloy WAL is experimental and is not used.
- **Finding** (census): every container on all 9 Docker hosts was created on or after
  2026-10-21 with `json-file`, `max-size 10m`, `max-file 3`. The precondition of FR-003 is met
  everywhere, and no container needs recreating. Journals hold 16–130 MB per LXC and 394 MB on
  pve.
- **Buffer depth**: monitoring's 5 containers produce about 2.8 MB/day together. The busiest
  single container is under 1.5 MB/day, so its 30 MB on disk covers more than 2 weeks. Journals
  cover weeks to months. The binding limit is Loki's `reject_old_samples_max_age` of 7 days
  (spec edge case).
- **Decision**: `max_backoff_retries = 0` on every `loki.write`. The journal source gets
  `max_age = "168h"`, equal to the store's backfill limit. Only the first start reads that far
  back, because later restarts resume from the cursor. Docker output is written by `dockerd` to
  json-file whatever Alloy does, so a stalled collector cannot block a container (FR-011).
- **Decision (per-host limit, spec edge case "one service floods")**: one `stage.limit` per
  collector, at the top of the shared `redact` pipeline: `rate = 200`, `burst = 2000` lines per
  second, `drop = false`. Upstream: with `drop` false, excess entries "are queued until more
  tokens are available". That means back-pressure onto the source, which keeps reading position
  on disk. A flooding host is slowed, and nothing is lost unless the flood outlasts its own
  on-disk buffer (R9 depth). The estate's busiest host averages well under 1 line per second, so
  the limit only ever acts on a real flood. The store keeps its per-stream and global limits
  (R2).
- **Decision (FR-003 enforcement)**: on Docker hosts the collector role runs
  `docker ps -q | xargs -r docker inspect -f '{{.Name}} {{index .HostConfig.LogConfig.Config "max-size"}}'`
  before it enables the Docker source. It fails, naming the container, if any value is empty. On
  a fresh build, Docker is not installed yet when `lxc_base` runs, so the check is skipped when
  the `docker` command is absent. Containers created later inherit `089`'s daemon defaults.

## R10 — Validating rules and configs (FR-008)

- **Finding** (trial): `lokitool rules check <file>` parses LogQL offline and returns 1 on a
  syntax error. `lokitool rules lint` **rewrites the file in place** (without `--dry-run`) and
  adds a top-level `namespace:` key. The local ruler then rejects that key
  (`field namespace not found in type rulefmt.RuleGroups`).
- **Finding** (trial): one unparseable file makes the ruler fail to list **all** rule groups for
  the tenant, so every log rule stops. The only trace is an error log line, plus the absence of
  `loki_prometheus_rule_group_rules`.
- **Finding**: `alloy validate <file>` exists in 1.21 and returned 0 on the trial config.
  `loki -verify-config` exists and returned 0.
- **Decision**:
  - At deploy on the monitoring host, before (re)starting anything:
    `docker run --rm grafana/loki:<v> -verify-config`, then `lokitool rules check` on the rendered
    rules file. `lokitool` is downloaded to `/usr/local/bin/lokitool`, pinned to `loki_version`
    with its checksum. This sits next to the existing promtool and amtool steps.
  - Collectors run `alloy validate` before their handler restarts the service.
  - `lokitool rules lint` is never used.
  - The loaded-rule count is watched by Prometheus (R14).
  - In CI, the guard tests cover structure (R7, R13, R15). They cannot parse LogQL, because the
    test environment has PyYAML only. The local `lokitool rules check` in quickstart §1 is the
    pre-merge LogQL check. Adding the binary to CI is a follow-up (plan).

## R11 — Labels and cardinality (FR-002)

- **Decision**: the stream labels are `env` (`prod`), `host` (inventory hostname),
  `service` (the host's service, the inventory hostname, or `proxmox` on pve) and `source`
  (`journal`, `docker` or `file`). Depending on the source, the stream also carries `ident` (the
  journal `SYSLOG_IDENTIFIER`, for example `sshd`, `sshd-session`, `sudo`, `kernel`, `cron`) and
  `unit` (the journal `_SYSTEMD_UNIT`, kept only for `*.service`), or `container` (the Docker
  container name), or `filename` (the file).
- Session and scope units (`session-123.scope`) are dropped because they are unbounded. That
  gives about 30–60 streams per host and under 1,000 in total, against a limit of 5,000.
- Line content that varies per entry (users, addresses, keys, request IDs) stays in the line and
  is extracted at query time. The OOM `lxc` field is structured metadata, not a label.

## R12 — LAB path (FR-017)

- **Finding**: LAB-path runs reach production hosts (`067`). Docker Compose `up -d` does not
  remove orphans (`compose_stack.yml`). Both `prometheus.yml.j2` and `backup_alerts.yml.j2`
  already render a lab view keyed on `deploy_environment`.
- **Decision**:
  - The Loki service, its config and the Grafana data source are rendered on **every** path. They
    are part of the monitoring stack's definition, so a LAB-path render cannot orphan or drop
    the production store.
  - These are skipped in lab:
    - the `alloy` role (`lxc_base` and `host_proxmox.yml`);
    - rendering of the Loki rules file. The task is skipped, so the production file stays as it
      is;
    - rendering of the Prometheus pipeline alert file (`log_pipeline_alerts.yml`). The task is
      skipped, so the production file stays as it is. That file is where the expected-host set
      lives (R14). This is **stricter than 091's `BackupStale`**, which renders an empty
      expected set on the LAB path. FR-017 forbids changing a production rule set.
  - The `alloy` scrape job in `prometheus.yml.j2` lists the same hosts on every path, with no lab
    condition. A LAB-path render therefore leaves the production scrape targets as they are. In a
    genuine lab there is no pipeline alert file, so those targets alert on nothing.
  - This matches the spec as amended (FR-017, SC-009).

## R13 — SSH password authentication on the LXCs (FR-015)

- **Finding**: Debian 12's `sshd_config` starts with `Include /etc/ssh/sshd_config.d/*.conf`.
  For sshd the first value wins, so a drop-in overrides the main file. The directory is empty on
  every LXC.
- **Decision**:
  - `lxc_base` installs `/etc/ssh/sshd_config.d/10-homelab-auth.conf` with
    `PasswordAuthentication no` and `KbdInteractiveAuthentication no`. It validates with
    `sshd -t` and reloads `ssh` from a handler.
  - The drop-in is **not** lab-gated, because it is a security baseline, not part of the log
    pipeline.
  - A guard test asserts that the drop-in task exists in `lxc_base`, and that no role or
    playbook targeting `proxmox_hosts` sets `PasswordAuthentication`, which keeps the owner's
    pve decision explicit.
  - `pct enter` does not use sshd and stays the recovery path.

## R14 — Pipeline self-monitoring in Prometheus (FR-012, MR-001 to MR-005)

Metric names confirmed against the running trial (`/metrics`), or against upstream docs where
marked:

| MR | Rule | Expression (sketch) | Severity |
|---|---|---|---|
| MR-001 | existing `ServiceDown` | `up{job="loki"} == 0` for 2m | critical |
| MR-002 | `LogCollectorDown` | `up{job="alloy"} == 0` for 10m (targets carry `no_down_alert="true"` so `ServiceDown` stays quiet) | warning |
| MR-002 | `LogHostSilent` | `sum by (instance) (increase(loki_write_sent_entries_total{job="alloy"}[2h])) == 0`, or `increase(loki_source_journal_target_lines_total[2h]) == 0` | warning |
| MR-003 | `LogRulesNotLoaded` | `absent(loki_prometheus_rule_group_rules) or sum(loki_prometheus_rule_group_rules) < <rendered count>` for 10m | warning |
| MR-003 | `LogRuleEvaluationFailing` | `increase(loki_prometheus_rule_evaluation_failures_total[10m]) > 0` or `increase(loki_prometheus_rule_group_iterations_missed_total[10m]) > 0` | warning |
| MR-003 | `LogRuleNotificationsFailing` | `increase(loki_prometheus_notifications_errors_total[10m]) > 0` or `increase(loki_prometheus_notifications_dropped_total[10m]) > 0` | warning |
| MR-004 | `LogLinesDiscarded` | `sum by (reason) (increase(loki_discarded_samples_total[10m])) > 0` (upstream name) | info |
| MR-004 | `LogLinesDiscardedSustained` | same, held `for: 1h` | warning |
| MR-005 | `LogCollectorDropping` | `increase(loki_write_dropped_entries_total[15m]) > 0` | warning |
| FR-012 | `LogRetentionStalled` | `time() - loki_compactor_apply_retention_last_successful_run_timestamp_seconds > 7200` | warning |
| FR-007 | `HostOomKill` | R6 backstop | warning |

- **Decision**: one new template, `log_pipeline_alerts.yml.j2`, rendered into Prometheus' `alerts/`
  directory and validated by the existing promtool loop. It is a template because it needs the
  rendered rule count, `proxmox_host_ip` and the lab switch. It does not go into
  `infrastructure_alerts.yml`, which is static.
- `LogHostSilent` uses 2 h because the quietest LXC journal still logs an hourly cron session
  (census).

## R15 — Where log rules are declared and rendered (FR-007, FR-008, FR-009)

- **Decision**:
  - Per-service rules: `monitoring_contract.log_alert_rules`, a list next to `alert_rules` in
    each service's `host_vars`, with the same fields plus `enabled` (data-model §3).
  - Estate-wide rules (OOM, SSH login, `sudo`) are rendered from `ssh_login_allowlist` and fixed
    text.
  - Both render into **one** file, `/opt/monitoring/loki/rules/fake/log_alerts.yaml`, from
    `templates/log_alerts.yaml.j2`.
  - Disabled rules are not rendered, but are counted and listed in a comment at the top of the
    file, which records their reason (FR-008).
  - The ruler polls the local directory (1 min), so a deploy needs no restart.
  - A guard test asserts that every `log_alert_rules` entry has the required keys and a
    `severity` from {critical, warning, info}, and that `enabled: false` entries carry a
    `disabled_reason`.
- **Alternatives considered**: separate files per service. A single bad file stops every rule
  (R10) either way, and one file keeps validation to one command.
