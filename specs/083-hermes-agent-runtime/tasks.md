---

description: "Task list for 083 — Hermes Agent behind Hermes"
---

# Tasks: Hermes Agent behind Hermes — a stock agent runtime and scheduler

**Input**: Design documents from `/specs/083-hermes-agent-runtime/`

**Prerequisites**: plan.md, spec.md, research.md (R-001…R-012), data-model.md, contracts/agent-runtime.md,
contracts/egress-allowlist.md, quickstart.md (Q-L1…Q-L10, Q-P1…Q-P10)

**Tests**: No unit-test suite is requested. Validation follows the constitution's "non-destructive
validation" rule: preflight assertions and deploy-time probes are implementation tasks, and the
quickstart LAB/PROD checks are explicit verification tasks inside each story.

**Organization**: Tasks are grouped by user story. Paths are relative to the repository root. All
Ansible runs go through the pipeline (`lxc-deploy-lab` → `lxc-promote-*` → `lxc-apply-prod`); commands
"on the Hermes LXC" run from the PVE host via `pct exec <vmid> -- …` (quickstart preamble).

**Code economy (Constitution IV)**: no new role, playbook or workflow entry. Extend `roles/hermes`,
`roles/hermes_backup`, `playbooks/hermes-restore-drill.yml`, `host_vars/hermes.yml` and
`group_vars/services/vars.yml`. New files are limited to the four templates named in plan.md.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1…US5 from spec.md

---

## Phase 1: Setup (verify upstream facts the implementation depends on)

**Purpose**: Resolve the "[doc]" and "verify at 0.11.3" items that would otherwise force rework. Record
each answer in `specs/083-hermes-agent-runtime/research.md` under the relevant R-section.

- [X] T001 [P] Read `backend/open_webui/config.py` at Open WebUI tag `v0.11.3` and record in research.md R-010 the exact persisted key names for the OpenAI connection list (expected `openai.api_base_urls`, `openai.api_keys`), the env var names (`OPENAI_API_BASE_URLS`, `OPENAI_API_KEYS`, `;`-separated) and the persisted key backing `ENABLE_AUTOMATIONS`; also record how to list existing automations (DB table name) for FR-015
- [X] T002 [P] Read the upstream `nousresearch/hermes-agent` docs/source at tag `v0.21.6` and record in research.md R-003/R-004/R-006: the env var the `custom` provider reads its API key from, the `config.yaml` schema for `model`/`provider`/`base_url`, `approvals`, `terminal.backend`, `terminal.env_passthrough`, `web.search_backend`, `mcp_servers` (including how a bearer header references an env var), `cron.failure_nudge_threshold`, and the exact `hermes cron create` flags (`--no-agent`, `--script`, `--deliver`, `--name`)
- [X] T003 [P] Check the node_exporter version deployed by `ansible/roles/node_exporter/defaults/main.yml` and whether its textfile collector follows a symlink placed in `node_exporter_textfile_directory` (`/var/lib/node_exporter/textfile_collector`); record the chosen mechanism (symlink, or second `--collector.textfile.directory`, node_exporter ≥ 1.8) in research.md R-007

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: The agent service exists, is pinned, has its own gateway identity, is confined (approvals,
read-only config, egress allowlist, no ports) and the exposure precondition is asserted. No story may
start before this — the accepted risk depends on these controls being in place before the agent first
runs.

**⚠️ CRITICAL**: The agent container must never start on any environment without T012–T015 in place.

### Variables, vault, gateway client

- [X] T004 Add `hermes_agent_version: "v0.21.6"` to the versions block in `ansible/group_vars/services/vars.yml` next to `hermes_version` and `hermes_searxng_version`, with a comment: plain `vX.Y.Z` only, never `latest`/`-desktop`/`rc.`; upgrade procedure in research R-001 (read upstream changelog for `approvals`, `cron`, `ntfy` before bumping)
- [X] T005 Add `hermes_agent_ip` (a fixed IPv4 inside a new `/29`-or-larger `agent` compose subnet, e.g. `hermes_agent_subnet: "172.30.83.0/24"`, `hermes_agent_ip: "172.30.83.10"`) to the Hermes block of `ansible/group_vars/services/vars.yml`; subnet must not collide with any existing Docker network on the Hermes LXC
- [X] T006 Add the `hermes_agent` client to `llm_router_clients` in `ansible/group_vars/services/vars.yml`: `alias: hermes_agent`, `key_env: LLM_ROUTER_CLIENT_HERMES_AGENT_KEY`, `max_budget: 5.00`, `budget_duration: "30d"`, `rpm_limit: 20`; update the sizing-rule comment block under `llm_router_gateway_budget` to `60 <= 65 < 90` and name the three clients (the `llm_router` preflight already enforces the band)
- [X] T007 Generate `llm_router_client_hermes_agent_key` (`sk-` + 32+ random chars, matching the existing client keys' format) and `hermes_agent_api_server_key` (≥ 8 chars, use 32 random chars) and add both to the encrypted, git-tracked `ansible/group_vars/services/vault.yml` with `ansible-vault edit` (the same procedure as 082 T002). LAB and PROD share this one vault. Never commit plaintext; after editing, confirm the file still starts with `$ANSIBLE_VAULT;1.1;AES256`. The `llm_router` compose already resolves `key_env | lower` to the first variable
- [X] T008 Add to `ansible/roles/hermes/defaults/main.yml`: `hermes_agent_image: "nousresearch/hermes-agent:{{ hermes_agent_version }}"`, `hermes_agent_data_dir: "{{ hermes_data_dir }}/agent"`, `hermes_agent_config_path: "{{ hermes_install_dir }}/agent-config.yaml"`, `hermes_agent_env_path: "{{ hermes_install_dir }}/agent.env"`, `hermes_agent_uid: 10000`, `hermes_agent_default_model: "hermes-balanced"`, `hermes_agent_heartbeat_dir: "/var/lib/hermes-agent-heartbeat"`, `hermes_agent_env_passthrough: []` (names of job secrets exposed to scripts; each name's value is read from the vault variable `name | lower`, the `llm_router_clients` `key_env` convention — empty today), and `hermes_agent_operational: "{{ not (lab_inventory | default(false) | bool) and (deploy_environment | default('prod')) == 'prod' }}"` (R-011: `deploy_environment` is the signal, because the pipeline's LAB stage uses the prod inventory (backlog 067); `lab_inventory` can only make it false). `mem_limit` is inlined in the compose file (single use, Constitution IV)

### Preflight

- [X] T009 Extend `ansible/roles/hermes/tasks/preflight.yml` with: (a) pin check — `hermes_agent_version` defined, non-empty, not `latest`, matches `^v\d+\.\d+\.\d+$`; (b) `hermes_agent_default_model` is in `llm_router_aliases | map(attribute='name')`; (c) `llm_router_client_hermes_agent_key` and `hermes_agent_api_server_key` defined, non-empty, the latter `length >= 8`, all with `no_log: true`; (d) every `hermes_mcp_servers[].url` with `enabled: true` parses to host and port (`urlsplit`), failing with the entry name otherwise; (e) when `hermes_agent_operational`, `ntfy_hermes_token` is defined and non-empty (`no_log`); (f) fail if `lab_inventory | default(false)` is true while `deploy_environment | default('prod') == 'prod'` (the pipeline's LAB stage legitimately pairs the prod inventory with `deploy_environment=lab`, so only this direction is an error); (g) every name in `hermes_agent_env_passthrough` has a defined, non-empty vault variable `name | lower` (`no_log`)
- [X] T010 Add the DNS exposure assertion (FR-017, R-012) to `ansible/roles/hermes/tasks/preflight.yml`: ensure `dnsutils` is installed; build the name list from every `caddy_services[].host` + `.hus-sky.no`, the apex `hus-sky.no`, and one random label (`{{ 99999999 | random }}-exposure-check.hus-sky.no`); for each name query `dig +short A` and `AAAA` against `@1.1.1.1` and `@8.8.8.8`; fail the deploy listing name+address if any answer is an IP outside `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `100.64.0.0/10`, `fc00::/7` (use `ansible.utils.ipaddr` or a shell check); NXDOMAIN/empty passes; CNAME lines are ignored

### Agent service and rendered configuration

- [X] T011 [P] Create `ansible/roles/hermes/templates/agent-config.yaml.j2` (R-004): `model`/`provider: custom` with `base_url: {{ hermes_gateway_base_url }}` and default model `{{ hermes_agent_default_model }}` (key read from env per T002, never inlined); `approvals: {mode: manual, unattended_mode: deny, cron_mode: deny, timeout: 300}`; `terminal.backend: local`; `terminal.env_passthrough` rendered from `hermes_agent_env_passthrough` (names only, schema per T002; empty list today — the spec's "job needs a secret" edge case); `web.search_backend: searxng`; `cron.failure_nudge_threshold: 3`; persistent memory enabled (FR-018); `mcp_servers` rendered by looping over `hermes_mcp_servers | selectattr('enabled')` with bearer entries referencing `credential_env` by variable name only (FR-011); a header comment stating the file is deploy-owned and mounted read-only
- [X] T012 [P] Create `ansible/roles/hermes/templates/agent.env.j2` (R-004, data-model § Agent secrets): `API_SERVER_ENABLED=true`, `API_SERVER_HOST=0.0.0.0`, `API_SERVER_KEY={{ hermes_agent_api_server_key }}`, the gateway key under the variable name from T002 = `{{ llm_router_client_hermes_agent_key }}`, `SEARXNG_URL=http://searxng:8080`, each bearer `credential_env` from `hermes_mcp_servers`, and each `hermes_agent_env_passthrough` name as `NAME={{ lookup('vars', name | lower) }}`; `HERMES_DASHBOARD` MUST NOT appear (FR-005); the `NTFY_*` block is added in US1 (T024)
- [X] T013 Render the agent config and env in `ansible/roles/hermes/tasks/main.yml` after "Ensure data directory exists": create `{{ hermes_agent_data_dir }}` (owner `{{ hermes_agent_uid }}`, mode 0750) and `{{ hermes_agent_data_dir }}/scripts`; template `agent-config.yaml.j2` → `{{ hermes_agent_config_path }}` (owner root, mode 0644); template `agent.env.j2` → `{{ hermes_agent_env_path }}` (owner `{{ hermes_agent_uid }}`, mode 0600, `no_log: true`); both notify the compose restart handler in `ansible/roles/hermes/handlers/main.yml` (extend it to cover the agent service)
- [X] T014 Add the `hermes-agent` service to `ansible/roles/hermes/templates/docker-compose.yml.j2` (R-002, data-model § Agent service): `image: {{ hermes_agent_image }}`, `container_name: hermes_agent`, `command: gateway run`, `env_file: {{ hermes_agent_env_path }}`, volumes `{{ hermes_agent_data_dir }}:/opt/data` and `{{ hermes_agent_config_path }}:/opt/data/config.yaml:ro`, `mem_limit: 3g` (inline, R-002), `restart: unless-stopped`, networks `agent` with `ipv4_address: {{ hermes_agent_ip }}` (the agent is **only** on `agent`, never on `default`), healthcheck on `http://localhost:8642/health`; **no `ports:`, no `privileged`, no `cap_add`, no Docker socket**. Add a top-level `networks:` block declaring `default: {}` and `agent` with `ipam` subnet `{{ hermes_agent_subnet }}` and `enable_ipv6: false`. Attach `searxng` to `agent` **in addition to** `default` by listing both explicitly (`networks: [default, agent]`) — a service that lists only `agent` silently leaves `default`, which would change the existing Open WebUI ↔ SearXNG topology (spec Out of Scope)
- [X] T015 Add a post-render assertion in `ansible/roles/hermes/tasks/preflight.yml` (or right after the compose template task in `main.yml`) that parses the rendered compose (`from_yaml`) and fails if `services['hermes-agent']` has `ports`, `privileged`, `cap_add`, or any volume containing `docker.sock` (FR-004, FR-007)

### Egress allowlist (FR-008) — must be live before the agent starts

- [X] T016 Create `ansible/roles/hermes/templates/hermes-agent-egress.sh.j2` (R-008, contracts/egress-allowlist.md): `set -euo pipefail`; create-or-flush chain `HERMES-AGENT`; rules for source `{{ hermes_agent_ip }}/32` in order — ESTABLISHED,RELATED accept; dst `{{ hermes_agent_subnet }}` accept; dst `{{ adguard_ip }}` udp+tcp 53 accept; dst `{{ llm_router_ip }}` tcp `{{ llm_router_port }}` accept; one accept per enabled `hermes_mcp_servers` host:port (derived with `urlsplit`, never hand-listed); dst `{{ reverse_proxy_ip }}` tcp 443 accept; reject `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `100.64.0.0/10`, `169.254.0.0/16`; final `RETURN` (internet allowed). Ensure exactly one jump `-s {{ hermes_agent_ip }} -j HERMES-AGENT` at the top of `DOCKER-USER`, and one `INPUT` rule rejecting NEW from `{{ hermes_agent_ip }}`; idempotent on re-run
- [X] T017 In `ansible/roles/hermes/tasks/main.yml`, before "Ensure hermes stack is running": template the script to `/usr/local/sbin/hermes-agent-egress.sh` (root, 0750); install systemd unit `hermes-agent-egress.service` inline via `copy: content:` (`Type=oneshot`, `RemainAfterExit=yes`, `After=docker.service`, `PartOf=docker.service`, `WantedBy=docker.service`, `ExecStart=/usr/local/sbin/hermes-agent-egress.sh`); enable it; run the script on every deploy (`command`, `changed_when: false`). On the first deploy the `DOCKER-USER` chain may not exist until Docker starts — the script must create it if missing
- [X] T018 Add the egress probe assertion in `ansible/roles/hermes/tasks/main.yml` after "Verify the workspace is healthy" (SC-009): wait for `hermes_agent` healthy; then `docker exec hermes_agent` a Python/bash TCP connect probe (3 s timeout) to each allowlisted destination — `searxng:8080`, `{{ llm_router_ip }}:{{ llm_router_port }}`, each MCP host:port, `{{ reverse_proxy_ip }}:443` — which MUST connect, and to the blocked destinations in `hermes_agent_egress_probe_blocked` plus `{{ hermes_ip }}:9100` — which MUST fail; fail the deploy naming each mismatch. Define `hermes_agent_egress_probe_blocked` (list of `{name, host, port}`: Proxmox host `:8006`, NAS `:5000`, router `:80`) centrally: PROD values in `ansible/group_vars/services/vars.yml`, LAB values (10.99.x network) where the LAB environment overrides service IPs today (locate it via `scripts/lab/pve-service-deploy`; if no override layer exists, key the list by environment). Reuse `synology_nas_ip` by moving it from `ansible/group_vars/monitoring/vars.yml` and `ansible/roles/monitoring_stack/defaults/main.yml` to `ansible/group_vars/all/` rather than copying it; add new central vars for the router and PVE host IPs (Constitution: IPs defined centrally)

**Checkpoint**: LAB deploy of `llm-router` then `hermes` passes; agent container is healthy, has no ports, egress probes and DNS assertion pass. Run quickstart Q-L1, Q-L2 and Q-L10 (record results in quickstart.md); if Q-L2 shows the read-only `config.yaml` blocks startup, switch to the R-004 fallback (render into `{{ hermes_agent_data_dir }}/config.yaml`, re-asserted every deploy) and note it in spec.md § Accepted risk.

- [X] T019 Deploy `llm-router` to LAB (mints the `hermes_agent` virtual key), then `hermes` to LAB via `lxc-deploy-lab`; run quickstart Q-L1 (`hermes --version` = pin, `python3 --version` ≥ 3.11, `git --version`) and Q-L2 (read-only mount, `hermes config show` shows approvals `manual/deny/deny/300`); record results with dates in `specs/083-hermes-agent-runtime/quickstart.md`
- [X] T020 Run quickstart Q-L10 on LAB (gate for the first PROD deploy, T024): `docker stats` while a multi-tool agent turn runs from the CLI (`docker exec -u hermes hermes_agent hermes chat …` — the Open WebUI connection arrives in US2) concurrently with an Open WebUI voice request on a gateway model; if LXC peak ≥ 80 %, raise Hermes LXC memory in the environment tfvars (Terraform, Constitution III) before the first PROD deploy and record the measurement in research.md R-002 (SC-011)

---

## Phase 3: User Story 1 — A new scheduled job is a script and one command (P1) 🎯 MVP

**Goal**: Script-only jobs deliver non-empty output and failures to the phone via 082's `hermes` topic on
PROD; LAB never reaches the phone.

**Independent Test**: On PROD, install the model scout as owner content, `hermes cron run model-scout`
→ report on phone; run again → nothing (quickstart Q-P3).

- [X] T021 [US1] Add the PROD-only ntfy block to `ansible/roles/hermes/templates/agent.env.j2`, guarded by `{% if hermes_agent_operational %}`: `NTFY_SERVER_URL=https://ntfy.hus-sky.no`, `NTFY_TOKEN={{ ntfy_hermes_token }}`, `NTFY_TOPIC=hermes`, `NTFY_PUBLISH_TOPIC=hermes`, `NTFY_HOME_CHANNEL=hermes`, `NTFY_MARKDOWN=true`; `NTFY_ALLOWED_USERS` and `NTFY_ALLOW_ALL_USERS` MUST NOT be set (FR-012). On LAB render the same block without `NTFY_TOKEN` (R-006 owner's choice: refused path exercised)
- [X] T022 [US1] Add a LAB guard in `ansible/roles/hermes/tasks/main.yml` after the env render: when `not hermes_agent_operational`, `slurp` the rendered `{{ hermes_agent_env_path }}` (`no_log: true`) and assert it contains no `NTFY_TOKEN=` line (FR-014, data-model validation 5)
- [X] T023 [US1] Run quickstart Q-L7 on LAB: after 10 min inspect `docker logs hermes_agent` for the refused subscription without a tight retry loop; create a throwaway script job printing `lab` with `--deliver ntfy`, run it, confirm publish refused (401/403) and **nothing on the phone**; then remove the job. If LAB cannot resolve/reach `ntfy.hus-sky.no`, record "not exercised" — do not skip silently. Record outcome and adapter behaviour in research.md R-006 and quickstart.md
- [X] T024 [US1] Promote and deploy `llm-router` then `hermes` to PROD; run quickstart Q-P1 (deploy green incl. DNS exposure assertion and egress probes) and Q-P2 (`hermes send --to ntfy "083 path test"` arrives on the phone; subscription refused without a loop); record in quickstart.md
- [X] T025 [US1] Install the model scout on PROD as owner content per quickstart § "Installing the model scout" (`local-llm` ≥ `d7f6a4a`, `scout/hermes-cron.sh` → `$HERMES_HOME/scripts/model-scout.sh`, `hermes cron create "30 7 * * *" --no-agent --script model-scout.sh --deliver ntfy --name model-scout`) — **no repository change** (FR-019, SC-001)
- [x] T026 [US1] Run quickstart Q-P3 (first run reports on phone, second run silent), Q-P4 (inference host asleep — scout still runs/delivers, SC-002) and Q-P5 (temporary `fail.sh` with `exit 3`, `every 15m`, failure naming `fail` reaches the phone within one interval, then remove the job, SC-003); record results in quickstart.md

**Checkpoint**: US1 delivered — any further job is a script plus one command.

---

## Phase 4: User Story 2 — Chat with an agent that can act, without changing plain chat (P1)

**Goal**: Open WebUI shows `hermes-agent` as a second connection; gateway connection stays default and
unchanged; flagged commands are refused at once; blocked destinations fail.

**Independent Test**: In Open WebUI pick `hermes-agent` → terminal + web search + MCP work; pick
`hermes-balanced` → unchanged (Q-L3); flagged command refused < 5 s (Q-L4).

- [x] T027 [US2] In `ansible/roles/hermes/templates/docker-compose.yml.j2`, replace `OPENAI_API_BASE_URL`/`OPENAI_API_KEY` on the Open WebUI service with `OPENAI_API_BASE_URLS: "{{ hermes_gateway_base_url }};http://hermes-agent:8642/v1"` and `OPENAI_API_KEYS: "{{ llm_router_client_hermes_key }};{{ hermes_agent_api_server_key }}"` (gateway at index 0, names per T001); leave `RAG_OPENAI_API_*` untouched; attach the Open WebUI service to `agent` **in addition to** `default` by listing both explicitly (`networks: [default, agent]`; listing only `agent` would drop it from `default`), and add `depends_on: hermes-agent`
- [x] T028 [US2] Add a `no_log: true` task "Reconcile the Open WebUI model connections" in `ansible/roles/hermes/tasks/main.yml` after "Reconcile the persisted Open WebUI configuration we own", following that task's pattern but feeding the JSON (`openai.api_base_urls` = `[gateway, http://hermes-agent:8642/v1]`, `openai.api_keys` in the same order; key names per T001) on **stdin** so no secret appears in argv or logs (R-010); idempotent (`changed_when` from the script's output)
- [x] T029 [US2] Update the `hermes_managed_config` comment in `ansible/group_vars/services/vars.yml` ("Secrets are deliberately ABSENT…") to record the one exception: the connection keys are reconciled in a separate `no_log` task (083 R-010), because PersistentConfig would otherwise make FR-006 inert
- [x] T030 [US2] Verify the MCP single-source rule (FR-011): confirm the existing "Build the MCP tool-server connection list" task in `ansible/roles/hermes/tasks/main.yml` and `agent-config.yaml.j2` (T011) both iterate `hermes_mcp_servers` with the same `enabled` filter; if the build task computes a derived fact, reuse it in the agent template rather than re-deriving
- [x] T031 [US2] Deploy to LAB and run quickstart Q-L3 (`hermes-agent` uses terminal, SearXNG, MCP; `hermes-balanced` unchanged — SC-005), Q-L4 (flagged command e.g. `rm -rf /opt/data/workspace/x` refused with readable message in < 5 s, 3 attempts — SC-008), Q-L6 (egress probes by hand match the deploy probe — SC-009) and Q-L9 (inference host away → readable error within seconds, US-2 #3); record in quickstart.md, and record per-alias tool-call behaviour in research.md R-003

**Checkpoint**: US1 and US2 both work; plain chat is unchanged.

---

## Phase 5: User Story 3 — Scheduled prompts run in one place, with failures visible (P2)

**Goal**: Open WebUI Automations retired (listed first, deploy stops if any exist); agent jobs deliver
output and failures to the phone.

**Independent Test**: Create an agent job delivering to the phone; it arrives; a failing one (bad model)
produces a failure message; Automations is not offered (Q-P9).

- [x] T032 [US3] Add a pre-disable check in `ansible/roles/hermes/tasks/main.yml` (before the compose deploy): query Open WebUI's DB in the `hermes` container for existing automations (table per T001); if any exist, fail the deploy and print their names/schedules rather than disabling them (FR-015); skip cleanly if the table does not exist (first deploy)
- [x] T033 [US3] In `ansible/roles/hermes/templates/docker-compose.yml.j2` set `ENABLE_AUTOMATIONS: "false"` and remove `AUTOMATION_MIN_INTERVAL`; remove `hermes_automation_min_interval` from `ansible/roles/hermes/defaults/main.yml` (it lives there, not in vars.yml); add the persisted automations key (name per T001) with value `false` to `hermes_managed_config` in `ansible/group_vars/services/vars.yml`
- [x] T034 [US3] Run quickstart Q-L5 on LAB: throwaway agent job with an unknown model alias, `--deliver local`, `hermes cron run`, inspect the CLI's `Ran now: …` line and `$HERMES_HOME/cron/output/<job-id>/` (not `hermes cron runs`, which stays empty for manual runs); record in research.md R-006 whether agent-job failures go to `deliver` or need a separate failure target, and update data-model.md § Job "failure target" and contracts/agent-runtime.md § 2 accordingly (FR-013)
- [x] T035 [US3] On PROD run quickstart Q-P9 (Automations not offered; gateway still default connection) and create/run one agent job (e.g. weekly web-search summary on `hermes-balanced`, `--deliver ntfy`) confirming output reaches the phone, then a variant with a bad model alias confirming the failure message reaches the phone; remove or keep the job per owner preference; record in quickstart.md

**Checkpoint**: one scheduler; failures visible for both job kinds.

---

## Phase 6: User Story 4 — The scheduler itself is watched (P2)

**Goal**: PROD heartbeat job writes a timestamp node_exporter exposes; `HermesAgentCronStale` alerts when
it ages past 1 h.

**Independent Test**: `docker stop hermes_agent` on PROD → alert within 1 h + 5 m via Alertmanager (Q-P7).

- [x] T036 [P] [US4] Create `ansible/roles/hermes/templates/agent-heartbeat.sh.j2` (R-007): `#!/usr/bin/env bash`, `set -euo pipefail`; write `hermes_agent_heartbeat_timestamp_seconds $(date +%s)` (with `# HELP`/`# TYPE gauge` lines) to `/heartbeat/hermes_agent.prom.tmp` then `mv` to `/heartbeat/hermes_agent.prom`; print nothing on success (silent tick); any error exits non-zero (reaches the phone)
- [x] T037 [US4] In `ansible/roles/hermes/tasks/main.yml`, when `hermes_agent_operational`: create `{{ hermes_agent_heartbeat_dir }}` (owner `{{ hermes_agent_uid }}`, mode 0755, holds nothing else); install `agent-heartbeat.sh.j2` to `{{ hermes_agent_data_dir }}/scripts/heartbeat.sh` (owner `{{ hermes_agent_uid }}`, 0755); link `{{ node_exporter_textfile_directory }}/hermes_agent.prom` → `{{ hermes_agent_heartbeat_dir }}/hermes_agent.prom` (or the second-directory mechanism chosen in T003). In `docker-compose.yml.j2` add the bind mount `{{ hermes_agent_heartbeat_dir }}:/heartbeat` to `hermes-agent`, guarded by `{% if hermes_agent_operational %}`
- [x] T038 [US4] Add the idempotent heartbeat-job reconcile in `ansible/roles/hermes/tasks/main.yml` after the agent is healthy, when `hermes_agent_operational`: `docker exec -u hermes hermes_agent hermes cron list` (parse output/JSON per T002); if no job named `heartbeat` exists, `hermes cron create "every 15m" --no-agent --script heartbeat.sh --deliver ntfy --name heartbeat`; `changed_when` only on creation. When not operational, assert no `heartbeat` job exists (FR-014)
- [x] T039 [US4] Add `HermesAgentCronStale` to `monitoring_contract.alert_rules` in `ansible/host_vars/hermes.yml`: `expr: time() - hermes_agent_heartbeat_timestamp_seconds > 3600 or absent(hermes_agent_heartbeat_timestamp_seconds)`, `for: 5m`, `labels.severity: warning`, annotations naming "Hermes agent scheduler" and distinguishing "scheduler down" from "job found nothing"; follow the shape of the existing `HermesDown` rule. No LAB guard is needed: the estate has one Prometheus (PROD, `192.168.1.214`), LAB `monitoring` deploys are blocked (backlog 072), and LAB hermes is never scraped, so `absent()` cannot fire for LAB. Record this in research.md R-007
- [x] T040 [US4] On LAB run quickstart Q-L8 (no `heartbeat` job; manual write through the symlink mechanism appears on `:9100/metrics`, then remove it). On PROD: deploy `hermes`, deploy `monitoring` (`allow_override_failed_lab_gate=true`, backlog 072), confirm the metric is fresh, then run Q-P7 (`docker stop hermes_agent` → `HermesAgentCronStale` within 1 h + 5 m; restart and confirm it clears); record in quickstart.md

**Checkpoint**: a silent scheduler is distinguishable from "nothing to report".

---

## Phase 7: User Story 5 — The agent survives a rebuild (P2)

**Goal**: Agent data (jobs, scripts, memory, scout state) is in the Hermes backup; restore re-renders
secrets; the drill verifies jobs and one run without messaging the phone.

**Independent Test**: Backup, then `hermes-restore-drill.yml` → `heartbeat` and `model-scout` listed,
one run succeeds, no phone message (Q-P8).

- [x] T041 [P] [US5] Extend `ansible/roles/hermes_backup/templates/backup_hermes.sh.j2` (R-009): for every `*.db`/`*.sqlite` under `{{ hermes_data_dir }}/agent`, snapshot with `sqlite3.Connection.backup()` executed inside `hermes_agent` (same method as `webui.db`); tar the rest of the agent directory excluding `.env`, `config.yaml`, `logs/`, `cache/`, `*-wal`, `*-shm`; include `scripts/` and scout clone/state under `$HERMES_HOME`; write `agent-manifest.sha256` into the archive (sha256 of every non-SQLite file included, relative paths) so the drill can prove scripts, memory files and scout state are byte-identical without knowing their paths; add the agent archive to the existing retention set and the textfile success metric
- [x] T042 [P] [US5] Extend `ansible/roles/hermes_backup/templates/restore_hermes.sh.j2`: stop `hermes_agent` before restoring; restore the agent directory with ownership `10000:10000`; do not restore `.env`/`config.yaml` (the following deploy re-renders them from vault, FR-010); print a reminder to run the hermes deploy afterwards
- [x] T043 [US5] Add the agent leg to `ansible/playbooks/hermes-restore-drill.yml` (and `ansible/roles/hermes_backup/templates/docker-compose.restore.yml.j2` if the drill uses it): on the extracted copy, first verify `agent-manifest.sha256` with `sha256sum -c` (fails the drill on any mismatch or missing file — this is SC-007's "scripts, memory and scout state intact"), then run `docker run --rm` of `{{ hermes_agent_image }}` with **only** the restored data mounted at `/opt/data`, no `.env`, no `NTFY_*`, no `gateway run`; assert `hermes cron list` contains `heartbeat` and `model-scout`; run `heartbeat` once (`hermes cron run` or `hermes cron tick`, per Q-L7/T002) with a writable throwaway `/heartbeat` mount and assert the CLI prints `Ran now: succeeded` and a new file appears under `$HERMES_HOME/cron/output/<job-id>/` (`hermes cron runs` stays empty after a manual run — research "Observed in the pinned image"); never point at the live data directory (two gateways must not share one)
- [x] T044 [US5] On PROD trigger a backup, then run `hermes-restore-drill.yml` (quickstart Q-P8): manifest verifies, jobs listed, one run succeeds, no phone message (SC-007). Scout state is proven by the manifest check, not by a live scout run (the live system is untouched by the drill, so its next run proves nothing about restored state); record in quickstart.md

**Checkpoint**: all five stories delivered.

---

## Phase 8: Polish & cross-cutting

- [x] T045 [P] Amend `specs/065-hermes-ai-workspace/spec.md` (FR-022): FR-025 → scheduled prompts are delivered by the 083 agent scheduler to the phone, failures delivered; FR-026 → job scripts are content, not application code; US-1 wording → reachable on LAN + tailnet only, "public" means routed by the reverse proxy; and add to `specs/065-hermes-ai-workspace/research.md` the agent-runtime question 065 did not ask, with 083 as the answer
- [ ] T046 [P] Update `docs/backlog/083-hermes-agent-runtime.md` status (specified → in progress → done) with links to the spec and PR
- [ ] T047 Perform the one-time manual router check (Q-P6): no port forward to `reverse_proxy_ip` (or any) on 80/443; record date, router model and screenshot reference in `specs/083-hermes-agent-runtime/quickstart.md` § Q-P6 (FR-017)
- [x] T048 [P] Run `ansible-playbook --syntax-check` for `ansible/playbooks/hermes.yml`, `ansible/playbooks/hermes-restore-drill.yml` and the llm-router playbook, plus `ansible-lint` on `ansible/roles/hermes` and `ansible/roles/hermes_backup`, and `bash -n`/`shellcheck` on the rendered `hermes-agent-egress.sh`, `heartbeat.sh`, `backup_hermes.sh`, `restore_hermes.sh`
- [ ] T049 Bring `specs/083-hermes-agent-runtime/spec.md` (Status), `plan.md`, `research.md` (every [doc] fact now observed or corrected), `data-model.md` and `contracts/*.md` up to date with what was delivered
- [ ] T050 After two weeks on PROD, run quickstart Q-P10: gateway metrics show no 429s for client `hermes` caused by `hermes_agent` (SC-006); zero LAB-origin or duplicate scout messages (SC-010); review `hermes_agent` rpm/budget against measured use (FR-009 — never raise first); record in quickstart.md

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (T001–T003)**: no dependencies; all [P]. Answers feed T011, T012, T027, T028, T032, T033, T037, T038.
- **Foundational (T004–T020)**: blocks every story. T004–T008 first; T009–T010 after T004–T008; T011/T012 [P] after T002; T013 after T011/T012; T014 after T005/T008; T015 after T014; T016–T018 after T014; T019 (LAB deploy) then T020 (memory gate; may trigger a Terraform resize before any PROD deploy).
- **US1 (T021–T026)**: after Foundational. T024 (first PROD deploy) is the first PROD touch for the whole feature.
- **US2 (T027–T031)**: after Foundational; independent of US1 code (different template blocks), shares the LAB deploy cadence.
- **US3 (T032–T035)**: after Foundational; T032 must land in the same deploy as or before T033. T034 informs US1's failure handling for agent jobs only.
- **US4 (T036–T040)**: after Foundational; PROD part needs US1's ntfy env (failures deliver) and a `monitoring` deploy.
- **US5 (T041–T044)**: after Foundational; T044 needs `model-scout` (T025) and `heartbeat` (T038) present on PROD.
- **Polish**: T045, T046, T048 any time; T047 before declaring FR-017 done; T050 two weeks after T024.

### Deploy order (quickstart)

1. `llm-router` LAB → PROD (client key minted by T006/T007)
2. `hermes` LAB → Q-L1…Q-L10
3. `hermes` PROD → Q-P1…Q-P9
4. `monitoring` PROD only (T039)

### Within each story

Templates/vars → tasks wiring → LAB deploy + checks → PROD deploy + checks.

## Parallel Opportunities

- T001, T002, T003 (research reads, separate sources).
- T011 and T012 (separate new templates).
- T036 (heartbeat template) alongside any US2/US3 task.
- T041 and T042 (backup vs restore templates).
- T045, T046, T048 (docs and lint).

### Parallel example: User Story 5

```bash
Task: "Extend backup_hermes.sh.j2 with agent SQLite snapshots and tar (T041)"
Task: "Extend restore_hermes.sh.j2 with agent dir, UID 10000 ownership (T042)"
```

### Parallel example: Foundational

```bash
Task: "Create agent-config.yaml.j2 (T011)"
Task: "Create agent.env.j2 (T012)"
```

## Implementation Strategy

### MVP (US1 on top of Foundational)

1. Phase 1 → Phase 2 (agent confined, egress and exposure asserted) → LAB gate T019 + memory gate T020.
2. Phase 3 (US1): ntfy env on PROD, LAB guard, first PROD deploy, scout installed as content.
3. **Stop and validate**: Q-P3/Q-P4/Q-P5 — the scout reaches the phone, silence is silent, failures alert.

### Incremental delivery

- US2 (chat connection) can ship in the same LAB/PROD cycle as US1 since both touch the same deploy.
- US3 and US4 next (one scheduler; scheduler watched) — US4 should land soon after the first PROD
  deploy, because until it does a stopped scheduler is indistinguishable from "nothing to report".
- US5 last (backup/drill), then Polish and the two-week review (T050).

## Notes

- Never commit secrets; vault values live on the PVE host (Constitution II). Every task that renders or
  passes a secret uses `no_log: true`.
- No workflow file changes: `hermes` and `llm-router` are already in the dropdowns (Constitution V), so no
  `act` run is needed.
- Jobs other than `heartbeat` are owner content and are never added to the repository (SC-001).
