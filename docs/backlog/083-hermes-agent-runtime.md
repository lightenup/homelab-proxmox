# Feature Specification: Hermes Agent behind Hermes — a stock agent runtime and scheduler

**Feature Branch**: `083-hermes-agent-runtime`
**Created**: 2026-10-16
**Status**: **Implemented** — live on PROD since 2026-10-18 ([`specs/083-hermes-agent-runtime/`](../../specs/083-hermes-agent-runtime/), [PR #247](https://github.com/lightenup/homelab-proxmox/pull/247)). No open follow-ups (the two-week review T050 was skipped by owner decision). Router check Q-P6 done: ISP Carrier-Grade NAT, so there is no inbound path. Depends on [`082`](./082-ntfy-push-service.md); amends [`065`](./065-hermes-service.md).
**Amended by [`095`](./095-ntfy-two-way.md) (2026-10-26, FR-013)**:
- *Delivery-only → interactive*: ntfy sessions from `hermes-in` are chat sessions with approval
  prompts on the phone. Cron, single-query and API-server (Open WebUI) surfaces still deny (FR-005
  unchanged). Slash commands over ntfy are limited to the 095 FR-014 set.
- *Silent restarts → silent gap notice*: every gateway start posts a priority-2 notice naming the
  window in which `hermes-in` messages were not received (gap-notice hook, read-only mount).
- *Approval timeout*: 300 s → 15 min.
- *FR-014 (LAB stage)*: the pipeline LAB stage still renders no ntfy. A separate LAB rig may hold the
  LAB-only `hermes_lab` scratch-pair credential.
- *Control comments*: `agent.env.j2` and `agent-config.yaml.j2` now describe inbound `hermes-in`,
  read-only for the agent's token, and that no `*_ALLOW_ALL_USERS` variable may ever be set.
- Two read-only overrides are mounted: the ntfy chunking shim (long replies split, not cut) and the
  gap-notice hook. Hermes's logs moved to `/var/log/hermes-agent` (collected for audit, FR-009).
**Input**: Add the upstream **Hermes Agent** (Nous Research) to the Hermes LXC as a second backend
behind the existing Open WebUI, so that (a) chats can use a full agent with terminal, tools and
memory, and (b) **any scheduled job is one script plus one `hermes cron create` line**, delivered
to the owner's phone through ntfy — instead of a new Ansible role and systemd timer per job.
Delivered as configuration of unmodified upstream software.

---

## Why this exists

"Hermes" today is Open WebUI 0.11.3 (`065`). It is a good chat surface, but it is not an agent:
no terminal, and its scheduled prompts (Open WebUI Automations, `065` FR-025) are LLM-only and
land as chats that the owner has to go and look at.

The first concrete need was a daily **model scout** (`local-llm` repo, `bench/model_scout.py`) that
tells the owner when a new MLX model worth benchmarking appears on Hugging Face. Done the estate's
current way it needs its own role, timer, vault entries, delivery code and monitoring contract —
and so would every similar job after it. That cost is the problem this feature removes.

What Hermes Agent brings, all upstream and documented:

- **No-agent cron jobs**: `hermes cron create "<schedule>" --no-agent --script <file> --deliver ntfy`.
  The script *is* the job: non-empty stdout is delivered, empty stdout is a silent tick, a non-zero
  exit or exception alerts. **No LLM call**, so it works while the inference host (the Mac) is away
  and costs nothing against the gateway.
- **Agent cron jobs**: scheduled prompts that run with the agent's tools, per-job model override,
  `failure_deliver` and a failure-streak review nudge.
- **Delivery targets** including `ntfy` (self-hosted server URL + token), `email`, `local`.
- **An OpenAI-compatible API server** (`:8642`, bearer `API_SERVER_KEY`) that Open WebUI connects to
  as a model — the integration upstream documents for Open WebUI.
- **MCP client** for the estate's Streamable-HTTP servers, **SearXNG** as a web-search backend,
  terminal, file tools, persistent memory and skills.

No agent framework was evaluated when `065` was specified (its R-001 compared Open WebUI,
LibreChat and AnythingLLM as chat surfaces). This feature keeps that decision — Open WebUI stays
the surface — and adds the runtime behind it.

## Decisions recorded (2026-10-16)

| decision | choice | consequence |
|---|---|---|
| Topology | **Same Hermes LXC**, a third service in the existing compose | One LXC, one backup, one monitoring contract. LXC sizing (`065` T082) must be re-measured. |
| Chat path | **Both connections** in Open WebUI | Gateway direct stays the default for plain chat and retrieval; the agent appears as a separate model (`hermes-agent`) for tool work. Plain chat does not become an agent run. |
| Terminal | **Full terminal** (stock `local` backend, inside the agent's own container) | Accepted risk, see below. |
| Front-door auth | **Not a prerequisite** | Accepted on the basis that every `hus-sky.no` name resolves to Caddy's LAN address (`reverse_proxy_ip`) and is reachable only on the LAN or over the tailnet. |
| Push channel | **ntfy, notify-only**, from `082` | The agent's ntfy adapter is used for *delivery* only; it never listens on a topic (FR-011). |
| Open WebUI Automations | **Retired** | One scheduler. Owner reports no automations in use (the "nyheter" chats are ad-hoc), so nothing to migrate; FR-013 still checks before disabling. |
| Default model | **`hermes-balanced`** for agent chats and agent cron jobs | Quality tier by default; a job may override per job (e.g. `hermes-fast`). No-agent jobs use no model. |
| MCP servers | **In both** Open WebUI and the agent | Plain chat keeps its tools; `078` (silently dropped MCP servers) now applies to two clients. |
| Agent memory | **On**, and **in the backup** | Memory is part of what the agent is; losing it on rebuild would be a regression. |
| Approvals | **Fail closed** | A flagged command with nobody to approve it is refused immediately (FR-007). |

### Accepted risk: a full terminal behind Open WebUI's own login

With the agent wired into Open WebUI, anyone who holds the Open WebUI admin session can make the
agent run shell commands on the Hermes LXC. `065` recorded the missing front-door auth (D-002) as
its principal risk for a chat app; with a terminal the impact grows from "read my chats" to
"shell on an estate host with a gateway key and MCP credentials".

Accepted because exposure is LAN + tailnet only (no port forward; verify, FR-016). Bounded by:
the agent API and dashboard never published (FR-004, FR-005); the terminal confined to the agent
container with no Docker socket and no host mounts beyond its data dir (FR-007); the agent's own
gateway key and allowance (FR-008); no inbound ntfy (FR-011). **Revisit if any `hus-sky.no` name
ever becomes internet-reachable** — at that point forward auth (D-002) becomes a prerequisite.

### Correction to `065`

`065` US-1 and its independent test describe Hermes as reachable "from a phone browser on mobile
data … no VPN step". The deployed estate does not do that: `hermes.hus-sky.no` resolves to
Caddy's LAN address (`reverse_proxy_ip`) and is reachable off-LAN only through the Tailscale subnet router. The "public"
wording in `reverse_proxy/templates/index.html.j2` means *routed by Caddy*, not internet-facing.
This feature's risk acceptance rests on that fact, so `065`'s wording should be corrected when
this is specified.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A new scheduled job is a script and one command (Priority: P1)

The owner (or the agent, asked in chat) drops a script into the agent's scripts directory and
schedules it. Its output reaches the phone; silence means nothing to report.

**Independent Test**: Install the model scout as a no-agent cron job delivering to ntfy topic
`hermes`; run it once with `hermes cron run`; the phone shows the report. Run again: no new
models → no message.

**Acceptance Scenarios**:
1. **Given** a script in the agent's scripts directory, **When** the owner runs
   `hermes cron create "<schedule>" --no-agent --script <file> --deliver ntfy`, **Then** it runs on
   schedule with no Ansible change, no new timer and no new vault entry.
2. **Given** a run whose script prints nothing, **When** it completes, **Then** nothing is sent.
3. **Given** a run whose script exits non-zero, **When** it completes, **Then** a failure message
   reaches the phone and names the job.
4. **Given** the Mac (inference host) is asleep, **When** a no-agent job fires, **Then** it runs
   and delivers normally.

### User Story 2 - Chat with an agent that can act, without changing plain chat (Priority: P1)

**Independent Test**: In Open WebUI, pick model `hermes-agent` and ask it to check disk usage on
its host and fetch something with web search; it uses the terminal and SearXNG. Pick
`hermes-balanced` (gateway direct) for a normal question; it answers exactly as before, with
retrieval unchanged.

**Acceptance Scenarios**:
1. **Given** the agent connection, **When** the owner selects `hermes-agent`, **Then** requests run
   through Hermes Agent with terminal, file, web-search and MCP tools available.
2. **Given** the gateway connection, **When** the owner selects a gateway alias, **Then** behaviour,
   tools and retrieval are unchanged from `065`.
3. **Given** the inference host is away, **When** the owner chats with `hermes-agent`, **Then** it
   fails clean with a readable error, as the gateway does (`065` gateway-usage contract), rather
   than hanging.

### User Story 3 - Scheduled prompts run in one place, with failures visible (Priority: P2)

**Independent Test**: Create an agent cron job (e.g. a weekly summary using web search) delivering
to ntfy; run it; it arrives. Make it fail (bad model alias); the failure reaches the phone. Open
WebUI Automations is disabled and its sidebar entry gone.

### User Story 4 - The scheduler itself is watched (Priority: P2)

**Independent Test**: Stop the agent container; within the alert window an alert reaches the
phone through Alertmanager. The owner can tell "scheduler down" from "job ran and found nothing".

### User Story 5 - The agent survives a rebuild (Priority: P2)

**Independent Test**: Run the Hermes restore drill; after restore, `hermes cron list` shows the
same jobs, scripts and memory, and the model scout's next run does not re-report models it had
already reported.

### Edge Cases

- **Gateway allowance exhausted by an agent loop** → the agent's own key hits its own `rpm`;
  Open WebUI's plain chat (separate key) is unaffected.
- **A job script needs a secret** → it lives in the agent's `.env` (vault-sourced, FR-009); cron
  scripts do not inherit provider credentials by default, which is the upstream behaviour and is kept.
- **Upstream releases are frequent** (dated tags) → pinned, upgraded deliberately, like Open WebUI.
- **Agent edits its own config or jobs** via the terminal → expected with a full terminal; the
  backup (FR-014) is the recovery path, and jobs created this way are visible in `hermes cron list`.

---

## Requirements *(mandatory)*

### Functional Requirements

**Runtime**

- **FR-001**: Hermes Agent MUST run as a service in the existing Hermes compose
  (`ansible/roles/hermes/templates/docker-compose.yml.j2`), unmodified upstream image
  `nousresearch/hermes-agent`, pinned in the `group_vars` versions block next to `hermes_version`.
- **FR-002**: Its data directory MUST be on the LXC's local disk under `{{ hermes_data_dir }}`
  (as `065` FR-019/020 require for Open WebUI), mounted at the image's data path.
- **FR-003**: Its model backend MUST be the `064` gateway, provider `custom`, base URL
  `{{ hermes_gateway_base_url }}`, addressed by alias only (`065` FR-007). Default model
  **`hermes-balanced`**; agent cron jobs may override per job (`model:`).
- **FR-004**: The API server MUST be enabled (`API_SERVER_ENABLED=true`) with a vault-sourced
  `API_SERVER_KEY`, bound so that it is reachable **only on the compose network**
  (`hermes-agent:8642`). It MUST NOT be published on the LAN and MUST NOT get a Caddy route.
- **FR-005**: The agent dashboard (which stores keys) MUST NOT be run, or if run, bound to
  127.0.0.1 inside the container only.

**Open WebUI**

- **FR-006**: Open WebUI MUST gain a second OpenAI-compatible connection to
  `http://hermes-agent:8642/v1` with `API_SERVER_KEY`, alongside the existing gateway connection,
  reconciled by the role like the other persisted settings (`roles/hermes/tasks/main.yml`
  reconcile tasks). The gateway connection stays the default. Retrieval (`RAG_*`) is unchanged.

**Terminal and tools**

- **FR-007**: Terminal backend `local`, i.e. commands run inside the agent container. No Docker
  socket, no `privileged`, no host mounts beyond FR-002's data directory. Approvals MUST fail
  closed wherever no human can answer:

  ```yaml
  approvals:
    mode: manual            # flagged commands always need a human
    unattended_mode: deny   # API-server sessions, i.e. every request from Open WebUI
    cron_mode: deny         # scheduled agent jobs
    timeout: 300            # an unanswered interactive prompt is denied (upstream default)
  ```

  Unflagged commands run (full terminal, accepted risk above). Verify on LAB that a flagged
  command from Open WebUI is refused at once with a readable message, not after the timeout.
- **FR-008**: The agent MUST have **its own gateway client** in `llm_router_clients`
  (`hermes_agent`, key in vault as `llm_router_client_hermes_agent_key`), with its own `rpm` and
  budget. Proposal: `rpm: 20`, `$5/30d`. Check against `064`'s sizing rule
  `max(client) ≤ gateway < sum(clients)`: 60 ≤ 65 < 90 holds, so the gateway-wide cap does not
  change. Limits are reviewed against measured use, never raised first (gateway-usage contract).
- **FR-009**: Secrets (gateway key, `API_SERVER_KEY`, ntfy token, MCP bearer tokens) MUST come
  from vault into the agent's `.env` at deploy, asserted by preflight with `no_log`, never in git.
- **FR-010**: The agent MUST be configured with the estate's MCP servers (`market-model` today;
  `financial-scenario` when its secret becomes configurable, `065` R-008) and with web search via
  the existing SearXNG sidecar (`web.search_backend: searxng`, `SEARXNG_URL=http://searxng:8080`).
  No paid extract provider (`065` FR-008: content stays in the estate). Open WebUI **keeps** its
  own MCP registrations (`hermes_tool_server_connections`); both are rendered from the same
  group_vars list so they cannot drift.

**Delivery**

- **FR-011**: The agent's ntfy platform MUST be configured for **delivery only**:
  `NTFY_SERVER_URL=https://ntfy.hus-sky.no`, `NTFY_TOKEN` = `082`'s write-only `hermes` token,
  `NTFY_HOME_CHANNEL=hermes`. It MUST NOT subscribe to any topic (no inbound commands), because a
  topic that can talk to the agent is a shell credential (upstream "identity model" note).
- **FR-012**: Every scheduled job MUST have a delivery target and a `failure_deliver` that reaches
  the phone. A job that silently fails is a defect.

**Scheduling**

- **FR-013**: Open WebUI Automations MUST be retired: list existing automations (expected: none),
  then set `ENABLE_AUTOMATIONS=false` and remove `AUTOMATION_MIN_INTERVAL`, reconciled so the
  persisted value follows. `065` FR-025 is then satisfied by Hermes Agent cron.
- **FR-014**: Persistent memory MUST be enabled. The agent's data directory (`/opt/data` in the
  image: `cron/`, `scripts/`, `memories/`, `sessions/`, `skills/`, `config.yaml`, `workspace/`,
  `state/`; `.env` excluded and re-rendered from vault) MUST be included in `hermes_backup`, and the
  restore drill
  (`ansible/playbooks/hermes-restore-drill.yml`) MUST verify `hermes cron list` and one job run
  after restore.

**Monitoring**

- **FR-015**: A no-agent **heartbeat** job (every 15 min) MUST write a timestamp to the node_exporter
  textfile collector (bind-mounted file, the canary/backup pattern), with a `HermesAgentCronStale`
  rule (> 1 h) in `host_vars/hermes.yml` `monitoring_contract`. This proves the *scheduler* runs,
  separately from any job's outcome. Container down is covered by the same rule.
- **FR-016**: The deploy MUST assert that no `hus-sky.no` service is reachable from outside the
  LAN/tailnet (no port forward on 443 to Caddy) — the precondition of the accepted risk.

**First job**

- **FR-017**: The `local-llm` model scout MUST be the acceptance job. Everything it needs is
  already in the public repo `github.com/lightenup/local-llm` (from commit `d7f6a4a`):
  `scout/hermes-cron.sh` is the no-agent script (clones/updates the repo under `$HERMES_HOME`,
  keeps its state there, runs `bench/model_scout.py scan --quiet`, which prints markdown only when
  there is news). Install and schedule it **as job content, not via Ansible** (SC-001):

  ```sh
  cp scout/hermes-cron.sh "$HERMES_HOME/scripts/model-scout.sh"
  hermes cron create "30 7 * * *" --no-agent --script model-scout.sh \
    --deliver ntfy --name model-scout
  hermes cron run <job_id>
  ```

  with `NTFY_MARKDOWN=true` in the agent's `.env`. Runbook: `local-llm/docs/SCOUT.md`. The image
  must provide `git` and `python3` ≥ 3.11 to the script (verify on LAB).

### Key Entities

- **Job**: a Hermes Agent cron entry — schedule, `no_agent` or prompt, script, `deliver`,
  `failure_deliver`, optional model override. Lives in the agent's data directory.
- **Script**: an executable in the agent's scripts directory; job content, not application code.
- **Agent client**: the `hermes_agent` gateway client and its allowance.

## Success Criteria *(mandatory)*

- **SC-001**: Adding a second scheduled job after the model scout requires **zero** Ansible,
  Terraform or vault changes (unless it needs a new secret).
- **SC-002**: The model scout delivers to the phone with the Mac asleep.
- **SC-003**: A deliberately failing job produces a phone notification naming it within one
  scheduled interval.
- **SC-004**: Stopping the agent container raises `HermesAgentCronStale` within 1 h + `for:`.
- **SC-005**: Plain chat on a gateway alias shows no change in latency or behaviour versus `065`
  (same prompts, same retrieval results).
- **SC-006**: The agent's gateway usage never pushes Open WebUI's own client into 429s (separate
  keys; checked in gateway metrics over the first two weeks).
- **SC-007**: Restore drill passes with jobs, scripts and scout state intact.

## Amendments to `065`

- **FR-025 (scheduled prompts)**: delivered by Hermes Agent cron instead of Open WebUI
  Automations; "failures visible" now means `failure_deliver` to ntfy (FR-012), and "output waiting
  for the owner" (SC-015) means delivered to the phone.
- **FR-026 (configuration only)**: clarify that **job scripts are content, not application code**,
  like prompts — the rule continues to forbid patching or building the platforms (Open WebUI,
  Hermes Agent, SearXNG), not writing jobs for them.
- **US-1 wording**: reachability is LAN + tailnet, not public (see Correction above).
- **R-001**: add the agent-runtime question it did not ask, and this answer.

## Assumptions

- The Hermes LXC (4 cores / 6 GB / 32 GB, provisional) can host a third container; to be
  measured, not assumed — raise RAM in Terraform if needed (`065` T082).
- Hermes Agent's custom-provider support works against LiteLLM aliases with tool calling, as
  upstream documents for LiteLLM. To be verified on the LAB deploy with each alias.
- Tailscale ACLs already restrict who on the tailnet can reach `reverse_proxy_ip`.

## Dependencies

- **`082`** — **done, live since 2026-10-17.** The interface to code against is
  [`specs/082-ntfy-push-service/contracts/publisher-interface.md`](../../specs/082-ntfy-push-service/contracts/publisher-interface.md).
  - **Credentials**: `POST https://ntfy.hus-sky.no/hermes` with `Authorization: Bearer
    {{ ntfy_hermes_token }}` (vault `group_vars/services/vault.yml`). The token is write-only on
    `hermes` and refused everywhere else (082 SC-002, 20/20).
  - **Phone**: the owner's phone is already subscribed to `hermes`.
  - **Limits**: 32 KB per message, cached for 72 h. Read the publisher contract for the
    responses a sender must handle.
  - **Still unproven**: 082 never published *from the Hermes LXC* (T026 accepted without
    running, because the dev box has no SSH there). 083's own tests must prove the path
    Hermes LXC → Caddy → ntfy.
- **`064`** — a new client entry (FR-008).
- **`local-llm`** — done: `scan --quiet` and `scout/hermes-cron.sh` are on `main` (`d7f6a4a`).
  Its webhook/Pushover `--notify` path stays as the non-Hermes alternative.

## Out of Scope

- Front-door auth (D-002) — not required while LAN/tailnet-only; becomes a prerequisite if that
  changes.
- Inbound messaging to the agent (ntfy, Telegram, Signal…).
- Removing MCP servers from Open WebUI (decided: both keep them).
- Paid web-extract providers.
- Splitting the agent onto its own LXC (rejected for now; revisit if T082 measurements say so).

## Open Questions

1. **Image tag**: upstream publishes dated releases (`v2026.x.y`); pick the pin at specify time and
   record the upgrade procedure next to Open WebUI's.

Resolved 2026-10-16: default model `hermes-balanced`; MCP in both; memory on and backed up;
approvals fail closed (FR-007).

## To verify on the LAB deploy

Facts taken from upstream documentation, not yet observed in this estate:

- [ ] Hermes Agent's `custom` provider drives tool calls correctly through each LiteLLM alias.
- [ ] `unattended_mode: deny` refuses a flagged command from an Open WebUI request immediately.
- [ ] The official image gives cron scripts `git` and `python3` ≥ 3.11; `HERMES_HOME=/opt/data`.
- [ ] `hermes cron` delivers to self-hosted ntfy out-of-process (no inbound subscription).
- [ ] Open WebUI lists the agent as model `hermes-agent` over the second connection.
- [ ] The LXC's 6 GB holds Open WebUI, SearXNG and the agent under a real agent turn.

## Handoff — continuing on another machine

Everything needed is in two public repos; nothing depends on the session that wrote this.

- **This repo**: this file. `082` is done (`specs/082-ntfy-push-service/`); start with
  `/speckit-specify` on `083`. Decisions above are the owner's, recorded
  2026-10-16; do not re-open them without the owner.
- **`github.com/lightenup/local-llm`** (public): `bench/model_scout.py`, `scout/scout.toml`
  (policy, each rule cites a FINDINGS section), `scout/setup.json` (the Mac's exported
  architectures and model sizes — refreshed on the Mac with `model_scout.py export`),
  `scout/hermes-cron.sh`, `docs/SCOUT.md`, tests in `tests/test_model_scout.py`
  (`python3 -m unittest discover -s tests`).
- **Vault entries**:
  - `082` (exist since 2026-10-17): `ntfy_owner_password_hash`, `ntfy_owner_token`,
    `ntfy_alertmanager_password_hash`, `ntfy_alertmanager_token`, `ntfy_hermes_password_hash`,
    `ntfy_hermes_token`. 083 reads only `ntfy_hermes_token`.
  - `083` (new): `llm_router_client_hermes_agent_key` (minted by `virtual_keys.yml` from this value),
    `hermes_agent_api_server_key`.
- **Owner-side phone setup**: done in `082` (app login as `owner`, subscriptions to `alerts` and
  `hermes`, WebSockets, battery exemption, Tailscale always-on;
  `docs/runbooks/ntfy-phone-setup.md`). Nothing new is needed for 083.
- **Deploy constraints learned in `082`**: the Linux dev box has no SSH to the LXCs, so every
  Ansible run goes through the pipeline (`lxc-deploy-lab` → `lxc-promote-*` → `lxc-apply-prod`).
  Monitoring changes need the prod path with `allow_override_failed_lab_gate=true` (backlog
  `072`).
- **Do not** enable the agent's inbound ntfy topic (FR-011), publish `:8642`, or run the dashboard
  on a LAN address (FR-004/005).
