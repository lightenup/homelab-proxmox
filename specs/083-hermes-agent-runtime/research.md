# Research: Hermes Agent behind Hermes (083)

Facts marked **[doc]** come from upstream documentation read 2026-10-17 and are not yet observed in
this estate. Each one has a LAB or PROD check in [quickstart.md](./quickstart.md). Facts marked
**[repo]** were read from this repository.

## R-001 — Image and pin

- **Decision**: `nousresearch/hermes-agent:v0.21.6` (Docker Hub, released 2026-10-08), pinned as
  `hermes_agent_version` in the `group_vars/services/vars.yml` versions block next to
  `hermes_version`. The preflight rejects an empty pin or `latest`, as it already does for Open WebUI.
- **Rationale**: owner's choice (2026-10-17). It is the first release on upstream's new semver scheme
  and has 9 days of soak time. `v0.22.x` shipped three releases in two days.
- **Alternatives**: `v0.22.2`, the newest, has no soak. `v2026.9.24`, the last dated tag, may predate
  the ntfy plugin and `approvals.unattended_mode` as documented, and any upgrade from it crosses the
  scheme change.
- **Tag scheme [doc/registry]**: dated `vYYYY.M.D` until 2026-09-24, then `v0.21.6`, `v0.22.0`… The
  same repository also carries `-desktop`, `rc.N-` and per-arch variants. Pin only plain `vX.Y.Z`.
- **Upgrade procedure**: the same as Open WebUI (065). Bump the pin, deploy through LAB, run the
  quickstart LAB checks Q-L1…Q-L10, promote, then deploy PROD. Read the upstream changelog for
  `approvals`, `cron` and `ntfy` changes before bumping, because those three carry this feature's
  security and delivery guarantees. Job definitions survive upgrades **[doc]**.

## R-002 — How the runtime runs

- **Decision**: one compose service `hermes-agent` (container `hermes_agent`), `command: gateway run`,
  data bind-mounted at `/opt/data` from `{{ hermes_data_dir }}/agent`. No `ports:`. Not privileged,
  no Docker socket, no other host mounts except the heartbeat file (R-007) and the read-only config
  (R-004).
- **Facts [doc]**:
  - The entrypoint is s6-overlay `/init`. It starts as root to fix volume ownership, then drops to user
    `hermes` (UID 10000).
  - `gateway run` hosts the cron scheduler (a tick every 60 s) and, with `API_SERVER_ENABLED=true`,
    the API server on `:8642`.
  - The dashboard runs only if `HERMES_DASHBOARD=1`. It is left unset, which satisfies FR-005 by not
    running it at all.
  - The image ships system `git` and Python 3.14 (`/opt/hermes/.venv`), which satisfies the scout's
    Python ≥ 3.11. `/opt/hermes` (the code) is root-owned and read-only to the agent.
  - Two gateways must never share one data directory. This matters for the restore drill (R-009).
- **API server**: `API_SERVER_ENABLED=true`, `API_SERVER_HOST=0.0.0.0` (inside the container's own
  network namespace only, with nothing published), `API_SERVER_KEY` from vault (≥ 8 chars). The
  advertised model is `hermes-agent` for the default profile **[doc]**, which is the name the spec
  uses.
- **Memory**: upstream asks for 1 GB minimum and recommends 2–4 GB. The LXC has 6 GB, shared with Open
  WebUI's in-container Whisper and TTS. Set `mem_limit: 3g` on the agent so a runaway turn cannot
  starve Open WebUI, measure peak use during a real agent turn on LAB (SC-011), and raise LXC memory in
  the environment tfvars (Terraform, Constitution III) only if peak LXC use is above 80 %.

## R-003 — Model backend

- **Decision**: provider `custom`, base URL `{{ hermes_gateway_base_url }}`, key
  `llm_router_client_hermes_agent_key`, default model `hermes-balanced`. Agent jobs may set `--model`.
  The preflight asserts that the default alias exists in `llm_router_aliases`, the same check the
  role already makes for Open WebUI's aliases.
- **Config schema [observed v0.21.6]**: `config.yaml` takes top-level `model: <name>`,
  `provider: custom` and `base_url: <url>` (`cli-config.yaml.example` lines 90–135). For a bare
  `provider: custom`, the API key is read from the env var named by `model.key_env`
  (`hermes_cli/auth.py` `_model_level_key_env` → `model_cfg.get("key_env") or model_cfg.get("api_key_env")`,
  resolved through `get_secret`, i.e. `$HERMES_HOME/.env` / process env — `agent/secret_scope.py`).
  There is **no fixed default env var name** for the custom provider; the variable name is declared in
  config. We declare `key_env: LLM_ROUTER_CLIENT_HERMES_AGENT_KEY` and render the same name into the
  agent `.env`. (Named `providers:` entries use the same `key_env` field, `hermes_cli/config.py`
  `_VALID_CUSTOM_PROVIDER_FIELDS`.)
- **New gateway client** `hermes_agent` in `llm_router_clients`: `rpm_limit: 20`, `max_budget: 5.00`,
  `budget_duration: "30d"`, `key_env: LLM_ROUTER_CLIENT_HERMES_AGENT_KEY`. Sizing rule:
  `max = 60 ≤ gateway 65 < sum = 60 + 10 + 20 = 90`, so it holds with no gateway change. The
  llm_router role mints the virtual key (`virtual_keys.yml`). This is an llm-router deploy as well as
  a hermes deploy.
- **To verify on LAB**: tool calls work through each alias the agent may use, and the agent fails with a
  readable error within seconds when the inference host is away (US-2 #3).

## R-004 — Configuration ownership and approvals

- **Decision**: Ansible renders `config.yaml` as `{{ hermes_install_dir }}/agent-config.yaml`
  (root-owned) and mounts it **read-only** over `/opt/data/config.yaml`. The agent can then not switch
  its own approvals off from the terminal. Contents:
  - `approvals: {mode: manual, unattended_mode: deny, cron_mode: deny, timeout: 300}`
  - model / provider (R-003), `terminal.backend: local`
  - `web.search_backend: searxng`
  - `mcp_servers` rendered from `hermes_mcp_servers` (R-005)
  - `cron.failure_nudge_threshold: 3` (upstream default, stated explicitly)
- **Fallback** if `/init` profile reconciliation or a CLI write needs `config.yaml` writable (LAB
  check Q-L2): render it into the data directory and treat it like `hermes_managed_config`. It is
  owned by the deploy and re-asserted on every run, so an agent edit lasts only until the next deploy.
  The accepted risk then names this explicitly.
- **Facts [observed v0.21.6]** (`hermes_cli/config_defaults.py`, `tools/approval.py`):
  - `approvals` schema: `mode` (`manual` | `smart` | `off`), `timeout` (seconds, default 300),
    `cron_mode` (`deny` | `approve`), `single_query_mode`, `unattended_mode`, plus `smart_policy`,
    `denial_breaker_threshold`, `deny` (glob list), `mcp_reload_confirm`,
    `destructive_slash_confirm`.
  - `unattended_mode` covers "unattended programmatic platforms (webhook/msgraph_webhook/api_server)"
    (`tools/approval.py:764`) — i.e. every request from Open WebUI. `cron_mode` covers cron jobs.
    Both default to `deny`; `mode` defaults to `smart`, so we set `manual` explicitly.
  - Approvals apply to the `local` terminal backend. Isolated backends such as Docker skip them
    (`terminal.backend: local` is therefore required for the control to hold).
  - `terminal.env_passthrough` (default `[]`) is the list of env-var **names** forwarded into
    sandboxed terminal/execute_code children (`tools/env_passthrough.py`); values are resolved at
    runtime through the secret scope, so the config carries names only.
  - `web.search_backend: searxng` selects the bundled SearXNG web-search provider
    (`plugins/web/searxng/provider.py`, `NAME = "searxng"`; the endpoint comes from `SEARXNG_URL`).
  - `cron.failure_nudge_threshold` (default 3, 0 disables) appends a "worth a review" nudge after N
    consecutive failures of a recurring job (`cron/scheduler.py:136`).
  - Persistent memory is `memory.memory_enabled` (default `True`); we state it explicitly (FR-018).
  - `mcp_servers` schema: stdio servers use `command`/`args`/`env`; HTTP servers use `url` +
    `headers`. Header values may reference env vars as `${VAR}`; they are interpolated at connect
    time from `$HERMES_HOME/.env` (`hermes_cli/mcp_config.py` `_resolve_mcp_server_config` →
    `_interpolate_env_vars`; the CLI's own bearer templates are
    `Authorization: Bearer ${MCP_<NAME>_API_KEY}`). So a bearer entry in our rendered config is
    `headers: {Authorization: "Bearer ${<credential_env>}"}` with the token in the agent `.env`.
- **`hermes cron` CLI [observed v0.21.6]** (`hermes_cli/subcommands/cron.py`):
  - `hermes cron create SCHEDULE [PROMPT] --name NAME --deliver TARGET --script PATH --no-agent`
    — all four flags used by this feature exist. `--script` is a path under `~/.hermes/scripts/`
    (with `HERMES_HOME=/opt/data`, that is `/opt/data/scripts/`); `.sh` files run via bash.
    `--no-agent` skips the LLM and delivers the script's stdout verbatim (empty stdout = silent).
  - `--deliver` grammar: `origin, local, telegram, discord, signal, platform:chat_id, …` — `ntfy`
    is a platform name and works here. `--failure-deliver` overrides the failure-notice target only
    (`'local'` suppresses; omitted = failures follow `--deliver`).
  - `hermes cron list [--all]`, `hermes cron run JOB_ID`, `hermes cron runs [JOB_ID]`,
    `hermes cron tick`, `hermes cron status`, `hermes cron doctor`.
- **`.env`** (vault-rendered, 0600, owned by UID 10000) holds:
  - `API_SERVER_*`
  - the gateway key, under the variable name the custom provider reads
  - `SEARXNG_URL=http://searxng:8080`
  - `NTFY_*` (R-006)
  - MCP bearer tokens, when any exist

  Cron scripts do not inherit provider credentials **[doc]**. A job secret is exposed by name through
  `terminal.env_passthrough`, which is the one case where a new job needs a deploy change (spec Edge
  Cases).

## Observed in the pinned image (2026-10-17, local run of `nousresearch/hermes-agent:v0.21.6` with the rendered config mounted read-only)

- **Q-L1**: `hermes --version` = `v0.21.6 (2026.9.24)`; `python3` = 3.14.7 (`/opt/hermes/.venv`); `git` 2.47.3;
  `curl` present (the compose healthcheck uses it). The container user is `hermes`.
- **Q-L2**: a read-only `config.yaml` works. `gateway run` starts and `/health` answers. The entrypoint
  tries to migrate an *unversioned* config on every start and logs `[config-migrate] ERROR: Read-only
  file system`, so the template stamps `_config_version: 50` (the pinned image's schema); re-check it on
  every pin bump. `load_config()` returns exactly the rendered `approvals` (`manual`/`deny`/`deny`/300),
  `terminal.backend: local`, `web.search_backend: searxng`, `memory_enabled: true` and `mcp_servers`.
  `model.context_length` is rendered from the alias definition, otherwise the agent assumes 256k.
- **FR-005**: s6 logs `service dashboard: starting`, but the only listener in the container is `:8642`.
  The dashboard is not running.
- **Q-L10 memory (SC-011), 2026-10-17, LXC 110 (6144 MB, 4 cores)**, sampled every 2 s for 3 minutes
  while three loads ran at once: a multi-tool agent turn through the real gateway (terminal `df`, SearXNG
  web search, MCP tool listing; it succeeded), Whisper `base` transcribing 20 s of audio, and SpeechT5
  TTS loading and synthesising (the worst case for Open WebUI's in-process `transformers` TTS):

  | | idle | peak |
  |---|---|---|
  | LXC used memory (`free`, excludes cache) | 1093 MB | **2130 MB (34.7 %)** |
  | LXC available | 5050 MB | min 4013 MB |
  | `hermes_open_webui` | 657 MB | 1712 MB |
  | `hermes_agent` (limit 3 g) | 266 MB | 489 MB |
  | `hermes_searxng` | 91 MB | 127 MB |

  Well under the 80 % threshold, so **no Terraform memory change**. Caveats: the agent turn was short
  and did not use the browser tool (Chromium is bundled in the image), so a heavy browsing turn would use
  more, bounded by the agent's `mem_limit`; the STT input was noise and the TTS speaker embedding was
  zeros, which does not change model memory. The cgroup figure (about 6.0 GB) is page cache and is not
  a pressure signal. Side finding: SpeechT5 is not cached in Open WebUI, so the first spoken reply
  downloads it, and the cold load took about 99 s.
- **Scheduler timezone**: the container has no `TZ` and the config `timezone` defaults to empty, i.e. UTC,
  so a cron expression is evaluated in UTC (a job created at 16:01 UTC reported `Next run …T07:30:00+00:00`).
  `timezone` (or `HERMES_TIMEZONE`) takes an IANA name; verified in the pinned image that
  `timezone: "Europe/Oslo"` makes `hermes_time.now()` Oslo-local. The rendered config sets it from
  `{{ timezone | default('Europe/Oslo') }}`, the estate's existing convention. Existing jobs keep their
  stored `next_run_at` until re-saved.
- **API contract**: `/v1/models` without a key or with a wrong key → 401; with the key → `["hermes-agent"]`.
- **Script-only jobs** (`--no-agent --deliver local`): output is delivered; empty output is recorded as
  `silent (empty output)`; a non-zero exit is recorded as `script failed` ("Script exited with code 3").
  The flags `--no-agent --script --deliver --name` all exist.
- **`hermes cron runs` stays empty after a manual `hermes cron run`** (CLI prints `Ran now: succeeded`/
  `failed`; the outcome is written under `$HERMES_HOME/cron/output/<job>/`). The restore drill must not
  rely on `cron runs`; see tasks T043.

## R-005 — Tool services and web search

- **Decision**: one list, `hermes_mcp_servers`, rendered twice. It goes into Open WebUI's
  `TOOL_SERVER_CONNECTIONS` and reconcile task as today, and into the agent's `mcp_servers` in
  `config.yaml`. A bearer entry's token goes into the agent's `.env` and is referenced from
  `config.yaml` by variable, never inlined.
- **Web search**: the existing SearXNG sidecar. The agent joins the network SearXNG is on. No paid
  extract provider is configured.

## R-006 — Delivery and the ntfy adapter

- **Finding [observed v0.21.6] that changes FR-012**: the ntfy platform plugin **requires `NTFY_TOPIC`
  and subscribes to it** for inbound messages (`plugins/platforms/ntfy/adapter.py`: HTTP-streaming
  subscription on `/json`, `poll=false`). Upstream's "send-only" recipe still subscribes. It only
  leaves `NTFY_ALLOWED_USERS` unset, so the agent never answers ("an empty allowlist rejects
  everything"). A "never subscribes" setting does not exist.
- **Env vars [observed v0.21.6]** (adapter docstring, read at construct time; `platforms.ntfy.extra`
  wins over env): `NTFY_TOPIC`, `NTFY_SERVER_URL`, `NTFY_TOKEN` (Bearer, or `user:pass` Basic),
  `NTFY_PUBLISH_TOPIC` (defaults to topic), `NTFY_MARKDOWN` (`"true"`/`"1"`/`"yes"`),
  `NTFY_ALLOWED_USERS` (topic names), `NTFY_ALLOW_ALL_USERS` (dev only), `NTFY_HOME_CHANNEL`,
  `NTFY_HOME_CHANNEL_NAME`. A 401 on subscribe is a fatal stream error
  (`ntfy_unauthorized`, adapter line 189); the reconnect backoff is `[2, 5, 10, 30, 60]` s — bounded,
  not a tight loop.
- **Decision**: rely on two independent controls rather than one.
  1. **The server refuses the subscription.** 082's `hermes` token is write-only (082 SC-002, 20/20),
     so the subscribe is refused with 401/403 and nothing can arrive.
  2. **The agent ignores anything that does arrive.** `NTFY_ALLOWED_USERS` is unset and
     `NTFY_ALLOW_ALL_USERS` is not set.

  Spec FR-012 is amended to say this. On PROD:

  ```
  NTFY_SERVER_URL=https://ntfy.hus-sky.no
  NTFY_TOKEN={{ ntfy_hermes_token }}
  NTFY_TOPIC=hermes
  NTFY_PUBLISH_TOPIC=hermes
  NTFY_HOME_CHANNEL=hermes
  NTFY_MARKDOWN=true
  ```

- **Observed on LAB with no token [Q-L7, 2026-10-17, LXC 110, agent up 624 s]**: the subscription is
  refused with **403** (not 401). Retries follow `[2, 5, 10, 30, 60]` s and settle at one warning per
  minute: 14 lines in 10 minutes, no tight loop. A script job with `--deliver ntfy` runs its script
  and then records `ran, but the result was not delivered (delivery error: ntfy HTTP 403 …)`; the
  server refused the publish, so nothing can have reached the phone. A delivery failure is therefore
  visible on the job, not silent. Not yet observed: the same path on PROD with the write-only token
  (Q-P2), where the subscription is refused but publishing must succeed.
- **Unknown (now answered above for LAB)**: how the adapter behaves when its subscription is refused. The observed backoff is
  bounded (`[2, 5, 10, 30, 60]` s, `RECONNECT_BACKOFF`), so a refused subscription should settle into
  the 60 s retry cadence rather than a tight loop — to be confirmed by Q-L7. Cron delivery uses a
  standalone sender that opens its own HTTP connection **[doc]**, so delivery should not depend on
  the subscription, but this is not stated outright.
- **LAB (owner's choice, 2026-10-17)**: the adapter is configured with **no token**. Subscribe and
  publish are then both refused by ntfy's deny-all default (082). That exercises the refused path
  before PROD and still cannot reach the phone (FR-014).
  - Precondition: LAB can resolve and reach `ntfy.hus-sky.no`. If it cannot, the LAB check reports
    "not exercised" and the check moves to the first PROD deploy (Q-P2). It is not silently skipped.
- **Restart notices [observed v0.21.6, LAB 2026-10-17]**: independent of the adapter's own behaviour,
  the gateway posts a "♻️ Gateway online/restarted" notice to a platform's home channel on every start
  and stop (`PlatformConfig.gateway_restart_notification`, default `True`). The LAB log showed the
  stop-time send being refused (403) right after SIGTERM. On PROD it would be a phone push at every
  deploy and container restart. **Decision**: set `ntfy: {gateway_restart_notification: false}` in the
  rendered config (verified in the pinned image that the key is honoured). A stopped scheduler is
  caught by the heartbeat alert instead. Other home-channel notices (cron store unwritable/recovered,
  session DB failure) stay on: they only fire on faults.
- **PROD with the write-only token [Q-P2, 2026-10-17]**: the subscription is refused with 403 exactly as
  on LAB, on the same bounded backoff, and the publish succeeds (`hermes send --to ntfy …` →
  `success: true`, ntfy message id returned). The refused subscription does not stop delivery. The CLI
  form is `hermes send --to <platform> "<text>"` (an earlier draft had `hermes send ntfy "<text>"`,
  which the CLI rejects).
- **Size**: the adapter truncates at 4096 characters and logs a warning **[doc]**. That is below
  ntfy's 32 KB limit, so 082's 413 cannot happen through this adapter. The spec's size edge case is
  satisfied by truncation.
- **Failure delivery**: script-only jobs deliver an error alert to the job's `deliver` target on a
  non-zero exit or a timeout **[doc]**. For agent jobs, verify on LAB whether failures go to
  `deliver` or need a separate failure target (Q-L5). Either way, the job validation rule in
  [data-model.md](./data-model.md) requires a phone-reaching target for failures.

- **Agent-job failures [observed v0.21.6, Q-L5, 2026-10-18]**: the throwaway job `--model
  no-such-alias --deliver local` failed at the gateway with `HTTP 401: key not allowed to access
  model`. `hermes cron run` printed `Ran now: failed`, the last run was recorded as
  `error: RuntimeError: …`, and `cron/output/<job-id>/` held a `# Cron Job: ql5-badmodel (FAILED)`
  report. Failures follow `deliver`, so no separate failure target is needed (FR-013). Phone receipt
  is confirmed on PROD (T035).

## R-007 — Scheduler heartbeat (FR-016)

- **Decision** (owner, 2026-10-17): Ansible owns the heartbeat job **on PROD only**.
  - The role installs `heartbeat.sh` into `$HERMES_HOME/scripts/`.
  - It creates the job `heartbeat` (`every 15m`, `--no-agent`, `--deliver ntfy`) **only if no job of
    that name exists**. That makes it idempotent and safe after a restore, which brings the job back
    with it.
  - Every other job remains owner content (SC-001).
- **Mechanism**:
  - The script writes `hermes_agent_heartbeat_timestamp_seconds <now>` to
    `/var/lib/hermes-agent-heartbeat/hermes_agent.prom`. That host directory is bind-mounted into the
    container, owned by UID 10000, and holds nothing else.
  - The script writes a temp file and renames it, which is atomic within the mounted directory.
  - The script prints nothing, so a tick is silent. A failure exits non-zero and reaches the phone.
  - node_exporter reads the file through a symlink in its textfile directory. The agent never gets
    write access to the shared textfile directory, so it cannot forge the backup or canary metrics.
  - Fallback if node_exporter's textfile collector does not follow the symlink (Q-L6): pass a second
    `--collector.textfile.directory`, which node_exporter 1.8+ supports.
- **node_exporter [repo]**: `ansible/roles/node_exporter/defaults/main.yml` pins
  `node_exporter_version: "1.10.2"` (≥ 1.8, so multiple `--collector.textfile.directory` flags are
  supported) and `node_exporter_textfile_directory:
  "/var/lib/node_exporter/textfile_collector"`, passed as a single flag in the unit. **Chosen
  mechanism: symlink** `{{ node_exporter_textfile_directory }}/hermes_agent.prom` →
  `{{ hermes_agent_heartbeat_dir }}/hermes_agent.prom` (the agent never gets write access to the
  shared directory). The second-directory flag is the fallback; final confirmation on LAB (Q-L8).
- **Alert** (`host_vars/hermes.yml`, `monitoring_contract.alert_rules`):
  `HermesAgentCronStale`, firing on
  `time() - hermes_agent_heartbeat_timestamp_seconds > 3600 or absent(hermes_agent_heartbeat_timestamp_seconds)`,
  with `for: 5m` and severity warning.
  - A stopped container stops the ticks, so the value ages and the alert fires. It is independent of
    ntfy, because it goes through Alertmanager to Pushover and the alerts topic.
  - `absent()` covers a first deploy whose job was never created. Since Ansible creates the job, that
    should only happen if creation failed.
- **Why not a host systemd timer**: it would prove that systemd runs, not that the agent's scheduler
  does.
- **LAB and the alert [repo]**: the estate has one Prometheus (PROD), and LAB `monitoring` deploys
  are blocked (backlog 072). LAB hermes is never scraped, so `absent()` cannot fire for LAB, and
  the rule needs no environment guard.

## R-008 — Egress allowlist (FR-008)

- **Decision**: the agent gets a fixed address on its own compose network `agent`, and netfilter rules
  in the LXC's own network namespace filter by that source address. This is the chain Docker reserves
  for operators (`DOCKER-USER`), plus `INPUT` for traffic addressed to the LXC itself. Rules, in
  order, for packets from the agent's address:

  | # | Match | Action | Why |
  |---|---|---|---|
  | 1 | established/related | accept | replies |
  | 2 | dst = `agent` network subnet | accept | SearXNG, and replies to Open WebUI (bridge traffic traverses FORWARD with br_netfilter) |
  | 3 | dst `adguard_ip` udp/tcp 53 | accept | DNS, if the embedded resolver forwards from the container's namespace |
  | 4 | dst `llm_router_ip:llm_router_port` tcp | accept | gateway |
  | 5 | dst each `hermes_mcp_servers` host:port tcp | accept | tool services (rendered from the same list) |
  | 6 | dst `reverse_proxy_ip:443` tcp | accept | ntfy via Caddy. **Owner's choice**: this opens every Caddy vhost at L4, and each keeps its own auth. Recorded in the accepted risk. |
  | 7 | dst 10/8, 172.16/12, 192.168/16, 100.64/10, 169.254/16 | reject | rest of LAN, tailnet, link-local (hypervisor, NAS, router…) |
  | 8 | else | accept | internet (GitHub, Hugging Face, web) |
  | INPUT | src agent, new | reject | the LXC itself: sshd, node_exporter… |

  IPv6 stays off on the `agent` network.
- **Ownership and persistence**:
  - A root-owned script `hermes-agent-egress.sh` (Ansible template) flushes and refills its own chain
    `HERMES-AGENT` and ensures the jump from `DOCKER-USER` and `INPUT`.
  - A systemd oneshot runs it with `After=docker.service`, `PartOf=docker.service` and
    `WantedBy=docker.service`, so a Docker restart re-applies the rules. The deploy also runs it.
  - The container has no `NET_ADMIN` (Docker default) and the rules live in the LXC's namespace, so
    the agent cannot change them (FR-008).
- **Verification**: a deploy assertion runs `docker exec hermes_agent` probes. Each allowlisted
  destination must connect and each sample blocked destination must fail: the Proxmox host on 8006,
  the NAS, the router on 80, and the LXC's own 9100. This is SC-009.
- **Multi-homing note**: Open WebUI also joins the `agent` network to reach `hermes-agent:8642`. The
  rules match the agent's /32, never the subnet as a source, so Open WebUI's reach is unchanged (spec
  Out of Scope).
- **Alternatives rejected**:
  - The Proxmox firewall on the LXC would restrict Open WebUI too, and it is PVE-host configuration.
  - An HTTP egress proxy can be bypassed by a terminal that ignores `HTTP_PROXY`.
  - Allowing only the ntfy LXC directly was the owner's rejected option. It departs from 082's
    contract.

## R-009 — Backup, restore and drill (FR-018)

- **Backup**: `backup_hermes.sh` gains the agent's directory.
  - Every SQLite file under `{{ hermes_data_dir }}/agent` is snapshotted with
    `sqlite3.Connection.backup()`, and the rest is tar-piped.
    - **Implemented (T041)**: the snapshot runs with the host's `python3` (which Ansible already
      requires), not inside `hermes_agent`. A backup must still work while the agent is down.
      `audio_cache/`, `image_cache/` and `*.lock` are excluded as well.
  - Excluded: `.env` (re-rendered from vault), `config.yaml` (rendered by Ansible), `logs/`, `cache/`,
    and `-wal`/`-shm` files.
  - The scout's clone and state under `$HERMES_HOME` are included, because SC-007 needs the scout
    state.
  - The archive carries `agent-manifest.sha256`, the sha256 of every non-SQLite file it contains.
    This proves scripts, memory and scout state intact without the drill knowing where any owner
    content lives.
- **Restore** (`restore_hermes.sh`): stop the agent, then restore the directory with ownership set to
  UID 10000. The deploy re-renders `.env` and `config.yaml`.
- **Drill**: the playbook gains an agent leg on the extracted copy.
  - It first runs `sha256sum -c agent-manifest.sha256` and fails on any mismatch or missing file.
    This is how SC-007's scout state is verified. A live scout run would prove nothing, because the
    drill never touches the live data.
  - It runs `hermes cron list` in a throwaway `docker run --rm` container. That container has the
    restored data and no `gateway run`, so no scheduler is live and two gateways never share a
    directory.
  - It has **no ntfy env and no `.env`**, so a drill can never message the phone.
  - It asserts that jobs `heartbeat` and `model-scout` exist, and runs one job (`heartbeat`, via
    `hermes cron run` or `hermes cron tick`, settled by the upstream CLI read in tasks T002) with a success recorded in `hermes cron runs`.

## R-010 — Open WebUI: second connection and retiring Automations

- **Facts [observed v0.11.3]** (`backend/open_webui/config.py`):
  - Env vars: `OPENAI_API_BASE_URLS` and `OPENAI_API_KEYS` (lines 333–345), `;`-separated, falling
    back to the singular `OPENAI_API_KEY`/`OPENAI_API_BASE_URL`.
  - Persisted keys (in `DEFAULT_CONFIG`): `openai.api_keys` (line 2841) and
    `openai.api_base_urls` (line 2842) — PersistentConfig, so they survive restarts and must be
    reconciled, not only set via env.
  - `ENABLE_AUTOMATIONS` (line 2048, default `'True'`) → persisted key `automations.enable`
    (line 3113); `AUTOMATION_MIN_INTERVAL` (line 2060) → `automations.min_interval` (line 3122).
  - Automations live in the `automation` table (class `Automation`,
    `__tablename__ = 'automation'`, `backend/open_webui/models/automations.py` line 20–21); columns
    include `name`, `data` (JSON: prompt/model_id/rrule), `is_active`, `next_run_at`. FR-015's
    "list existing automations" is a `SELECT name, data FROM automation` against `webui.db` inside
    the `hermes` container.
- **Connection**:
  - `OPENAI_API_BASE_URLS="{{ hermes_gateway_base_url }};http://hermes-agent:8642/v1"` and
    `OPENAI_API_KEYS` in the same order replace the single-URL variables. The gateway stays at
    index 0, the default.
  - The persisted keys (`openai.api_base_urls`, `openai.api_keys`) are PersistentConfig, so they are
    reconciled the way `hermes_managed_config` is.
  - Unlike the existing managed keys, this set contains secrets, so it is reconciled in a separate
    `no_log` task fed on stdin. 065's rule "secrets deliberately absent from managed config" is
    amended for this one case, because without it the connection never appears on an existing deploy.
- **Observed on PROD (2026-10-17)**: the pre-disable check found one active automation, "Daglig
  nyhetsdigest (ukedager 07:30)" (`hermes-deep`, weekdays 07:30, never run). Owner decision: delete it
  without a replacement. The row was deleted by hand before the US3 deploy, and `automation` is now empty.
- **MCP single source (T030, FR-011)** [repo]: the agent config, the egress script and Open WebUI's
  `hermes_tool_server_connections` all iterate `hermes_mcp_servers`. The agent and the egress chain
  take `selectattr('enabled')`. Open WebUI registers every entry with `config.enable: item.enabled`,
  so a disabled server is off in both places. The Open WebUI fact is not reused for the agent: it
  has Open WebUI's shape and carries bearer tokens (`no_log`).
- **Automations**:
  - First list existing automations from the `automation` table (expected none, FR-015).
  - Then set `ENABLE_AUTOMATIONS=false`, drop `AUTOMATION_MIN_INTERVAL` and the
    `hermes_automation_min_interval` default, and add the persisted key `automations.enable` with
    value `false` to `hermes_managed_config`.
  - If automations exist, the deploy stops and reports them rather than disabling them.

- **Egress probe blocked list [repo, deviation from task wording]**: T018 asks for "LAB values
  (10.99.x network)". Backlog 067 established that the LAB pipeline renders tfvars byte-identical to
  prod (same `192.168.1.x` IPs, same PVE node) — "lab" is a gating stage, not a separate network; the
  `10.99.0.0/24` rig only exists in `scripts/lab/pve-lab`. The blocked destinations are the same real
  IPs in both environments, so `hermes_agent_egress_probe_blocked` is a single central list in
  `group_vars/services/vars.yml`, keyed by nothing (no environment split).

## R-011 — LAB vs PROD (FR-014)

- The deploy already passes `-e deploy_environment=<lab|prod>` **[repo]**: `pve-service-deploy`, used
  by `immich.yml` and `nextcloud.yml`. The hermes role derives
  `hermes_agent_operational: "{{ not (lab_inventory | default(false) | bool) and (deploy_environment | default('prod')) == 'prod' }}"`.
- **Correction (first LAB run, 2026-10-17)**: an earlier draft required `lab_inventory` and
  `deploy_environment` to agree, and failed the pipeline's own LAB stage. That stage deploys with
  the **prod inventory** and only `-e deploy_environment=lab` (backlog 067: "lab" is a gating
  stage at the production address, not a separate environment), so `lab_inventory` is false there.
  `deploy_environment` is therefore the signal. `lab_inventory` (the 10.99.x rig) can only make
  the flag false, and the preflight rejects that inventory paired with a prod deploy.
- **Residual gap**: the vault is shared, so `ntfy_hermes_token` is always defined. A laptop LAB
  run against the prod inventory that forgets `-e deploy_environment=lab` is indistinguishable
  from a PROD run. The pipeline always passes the flag, and quickstart documents it for laptops.
- **Consequence of 067**: a LAB deploy of `hermes` changes the production LXC (real egress rules,
  real containers). Q-L checks therefore run on the production machine, without the ntfy token.
- When it is false:
  - No `ntfy_hermes_token` is rendered.
  - The heartbeat job is not created.
  - The preflight asserts that the LAB `.env` holds no `NTFY_TOKEN`.
- The default is `prod`, which keeps a laptop run against the prod inventory correct (Constitution V).
  A laptop LAB run must pass `-e deploy_environment=lab`, which is documented in quickstart. If it
  is forgotten, the run is treated as PROD (see the residual gap above).

## R-012 — Exposure precondition (FR-017)

- **Decision**: a preflight task in the hermes role.
  - It installs `dnsutils` if missing.
  - For every `hus-sky.no` name the reverse proxy serves (`caddy_services[].host` in
    `group_vars/services/vars.yml`), plus the apex and one random label (catching a wildcard), it
    queries public resolvers `1.1.1.1` and `8.8.8.8` with `dig +short`. Querying two resolvers rules
    out a single-resolver artefact.
  - It **fails the deploy** if any answer is an address outside RFC 1918, 100.64/10 or ULA.
  - NXDOMAIN or empty answers pass.
- It runs on the Hermes LXC before the egress rules matter, because the LXC's own namespace is not
  filtered.
- **Manual router check**: done once and recorded in `quickstart.md` § Q-P6 with date, router model
  and the port-forward table (no forwards to `reverse_proxy_ip`).
- **Revisit trigger**: unchanged from the spec. Any public A or AAAA record turns this into a
  front-door-auth prerequisite.
