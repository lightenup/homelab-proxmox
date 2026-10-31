# Implementation Plan: Long-term memory for Hermes, shared with the owner's other AI clients

**Branch**: `097-hermes-long-term-memory` | **Date**: 2026-10-31 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/097-hermes-long-term-memory/spec.md`

## Summary

A new `memory` LXC (`192.168.1.223`, lab `10.99.0.223`) runs the stock Hindsight server
(`1.1.0-slim`) and pgvector Postgres in Docker, in verbatim-chunks mode with every LLM feature
off (research R-004). It is one store with one bank (`owner`), reached by every client through
Caddy at `https://memory-api.hus-sky.no`: REST for the adapters, MCP for browsing and editing.

Per-client identity is a small extension in this repo (R-001, R-002). A tenant extension maps
each client's key (stored hashed) to a client id and scope. An operation validator stamps the
`client:<id>` tag on every retained item. It allows each scope only the operations listed for it
(read-only, read-write, curator, admin) and refuses webhooks, reflect and consolidation for every
key, so no client can send memories off the estate or start an inference pass. The policy is a pure Python
module in the orchestrator package, so it gets unit tests and mutation testing. A thin shim
subclasses Hindsight's classes and is mounted read-only into the stock image.

Three thin adapters inject recall before a turn and retain the turn after it, all with the same
turn format (contract [turn-format.md](./contracts/turn-format.md)):

- **Hermes**: upstream's Hindsight plugin `1.2.3` in context-only mode, on the stock agent image.
  Plugin source and four pinned wheels are fetched at deploy with checksums and mounted read-only
  (R-003).
- **Open WebUI**: a filter function, provisioned by the role's existing reconcile pattern. Open
  WebUI's own memories are imported once, then switched off (R-007, R-008).
- **Claude Code**: `UserPromptSubmit` and `Stop` hooks in the owner's dotfiles. They are enabled
  per private repository, and only after the accepted risk is confirmed (R-010).

Hindsight's own web UI runs as a third container in the memory stack (stock
`hindsight-control-plane` image). It is published at `https://memory.hus-sky.no` with a portal
tile, behind its own mandatory login key, and acts as a fourth client, `control-plane`, with the
`curator` scope: read-write plus hard delete and retry (R-020).

Memory's embedding and rerank traffic uses its own gateway key. The key is scoped to the two
aliases, so the gateway itself refuses chat-model calls from memory (R-011). Backups take a
nightly `pg_dump` plus the portable export to the NAS (R-013). A restore drill (R-014),
monitoring (R-015) and the lab fit of `067` (R-016) complete the service. The spike harness gates
every PROD promotion that changes memory (R-017).

## Technical Context

**Language/Version**: HCL (Terraform, `telmate/proxmox`), YAML (Ansible 2.x), Jinja2, Bash,
Python 3.11 (extension policy, filter, harness render). No new language.

**Primary Dependencies**:

- Existing: `modules/lxc_service`; `geerlingguy.docker` and `community.docker.docker_compose_v2`.
- New pins:
  - `ghcr.io/vectorize-io/hindsight:1.1.0-slim`, `ghcr.io/vectorize-io/hindsight-control-plane:1.1.0`
    and `pgvector/pgvector:0.8.1-pg17` (stock images).
  - Hindsight Hermes plugin `integrations/hermes/v1.2.3`.
  - `hindsight-client`, `hindsight-embed` (`0.10.x`, exact pins with hashes) and
    `aiohttp-retry 2.9.1`.
- Unchanged: Open WebUI `0.11.3`, `nousresearch/hermes-agent:v0.21.6`.

**Storage**: Postgres 17 + pgvector on the memory LXC's local disk (`/opt/memory-data/postgres`).
No NFS for state (spec FR-007). The NAS share `homelab_memory` holds backups only.

**Testing**:

- `pytest` under `python/tests/`:
  - `memory_access/` for the policy module (key mapping, scopes, tag rewrite, internal worker
    calls).
  - `guardrails/` for the rendered server env, plugin config, Caddy entry, lab overrides,
    lab-switch classification, credential freeze and version pins.
  - `open_webui_memory_filter/` for the filter's pure functions.
- Mutation testing through the existing gate covers the policy module.
- The spike harness on the dev Mac is the quality gate (FR-021), run against the
  production-rendered configuration (R-017).
- The LAB rehearsal checks deploy, health and isolation.
- [quickstart.md](./quickstart.md) covers PROD verification.

**Target Platform**:

- New: the `memory` LXC (Debian, Docker).
- Changed: `hermes` (agent and Open WebUI), `llm-router` (one client), `reverse_proxy` (two
  vhosts, one portal tile), `monitoring` (scrape, probe and rules), `pve` (NFS mount).
- Off-repo: the dev Mac (Claude Code hooks, dotfiles).

**Project Type**: Infrastructure service plus three small adapters.

**Performance Goals**:

- Recall adds at most 3 s to a turn (Open WebUI, Claude Code) and at most 10 s worst case to a
  Hermes turn (plugin timeout).
- Retain never blocks a turn.
- Zero memory-side chat-model calls (SC-003).

**Constraints**:

- Local only (FR-003).
- No runtime installs (FR-002).
- The agent cannot change memory configuration (FR-008).
- No more than 10 memory tools offered to any model (FR-009).
- Every client keeps working when memory is down.
- A lab copy holds no credential that reaches the internet (`067`).

**Scale/Scope**:

- One owner, three clients, tens of turns a day.
- The store grows by about 1–3 KB per turn: low hundreds of MB after years, which is negligible.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| I. Spec-driven | PASS | `specs/097-hermes-long-term-memory/` (spec, plan, research, data model, contracts, quickstart). Two spec fixes are made in this change: FR-020's `lan` label becomes `internal` (R-011), and a new edge case covers Open WebUI chats with the agent model (R-007). Amendments to `083`, `065` and `002` are tasks (FR-022). |
| II. Secrets | PASS | Seven new vault entries: `memory_db_password`, `memory_client_hermes_key`, `memory_client_open_webui_key`, `memory_client_control_plane_key`, `memory_ui_access_key`, `memory_admin_key` and `llm_router_client_memory_key`. The UI's API key exists only in the UI container's environment; the browser never holds it. Claude Code's key lives in the vault and the Mac's keychain, never in a repo. The LXC holds only sha256 hashes of client keys (R-001). Placeholders in docs. |
| III. Separation | PASS | Terraform: `terraform/services/memory/` (existence and sizing) plus the IP and mountpoint in `prod.tfvars.template`. Ansible: everything inside the LXC, the Hermes, Open WebUI and gateway changes, Caddy, monitoring and the NFS mount. |
| IV. Code economy | PASS, with six recorded choices | See Complexity Tracking. No new image builds: both images stay stock, and code is mounted read-only. The policy module and shim are about 150 lines. The other three are one optional field each on an existing list (`hermes_mcp_servers` twice, `llm_router_clients` once). No wrapper roles: `memory` follows `ntfy`'s layout. |
| V. Dual provisioning | PASS | `memory` joins the `lxc-promote-prod.yml` dropdown and `service-scope-allowlist.json` in the same PR. All deploys go through `pve-service-deploy`. The spike harness runs on the dev Mac by design (FR-021); it is a gate, not a provisioning path. The Claude Code hooks are owner-workstation config in dotfiles, outside both paths, as the spec says (FR-019). |
| Networking / access | PASS | Static IP defined once (`service_ips`, `memory_ip`). The API and the UI are published only through Caddy (public DNS points at the private `.211`; LAN and tailnet only, as for every vhost). The UI refuses to deploy without its login key (upstream would serve it open). |
| Token tiers | PASS | No new Proxmox credential. The NFS bind mount uses the orchestrator's existing tier-2 path. |
| Test-driven | PASS | Policy in a testable module with mutation coverage. Guard tests on every rendered file. The harness quality gate runs before PROD. LAB proves deploy and isolation. |

**Post-design re-check**: PASS. The design adds no Hermes egress rule (R-005) and no image
build, and keeps one store and one bank. The three optional list fields are each used by exactly
one entry today, and each is justified by a requirement (FR-004, FR-010, FR-011; see Complexity
Tracking).

## Project Structure

### Documentation (this feature)

```text
specs/097-hermes-long-term-memory/
├── spec.md
├── plan.md              # this file
├── research.md          # R-001 … R-020
├── data-model.md        # memory item, client, key scopes, bank, export
├── quickstart.md        # harness gate, LAB, PROD checks, restore, revocation
├── contracts/
│   ├── memory-access.md     # endpoints, scopes, who may do what (SC-009 matrix)
│   └── turn-format.md       # retain item and recall injection shared by the three adapters
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
terraform/services/memory/{main,outputs,providers,variables}.tf   # copy of services/ntfy; 2 cores, 2048 MB, 16 GB
terraform/environments/prod.tfvars.template          # service_ips.memory, service_mountpoints.memory (backups)
scripts/lab/service-scope-allowlist.json             # + "memory": ["module.memory_lxc"]   (protected path)
scripts/lab/validate-existing-state.sh               # SERVICES += memory                  (protected path)
scripts/healthcheck/memory.sh                        # modelled on ntfy.sh
.github/workflows/lxc-promote-prod.yml               # dropdown += memory
ansible/playbooks/memory.yml                         # lxc_base → geerlingguy.docker → memory → service_backup (lab-gated)
ansible/playbooks/memory-restore-drill.yml           # R-014, Immich pattern
ansible/roles/memory/
├── defaults/main.yml                                # dirs, images, bank id, MCP tool allowlist
├── tasks/{main,preflight,bank}.yml                  # compose up, health wait, bank settings, deploy probe (R-019)
├── templates/docker-compose.yml.j2                  # memory_api + memory_postgres + memory_ui; ports bound to memory_ip
├── templates/server.env.j2                          # R-004 (0600, no_log)
├── templates/clients.json.j2                        # key hashes + scopes (0400)
├── templates/ui.env.j2                              # UI login key + its API key only (0600, no_log; R-020)
├── files/hindsight_ext/shim.py                      # subclasses Hindsight's TenantExtension/OperationValidatorExtension
└── handlers/main.yml
python/src/homelab_proxmox_orchestrator/memory_access.py   # pure policy (R-001, R-002); copied to the LXC, mounted ro
python/tests/memory_access/                          # policy unit tests (mutmut target)
ansible/roles/hermes/
├── defaults/main.yml                                # plugin pin, wheel pins+hashes, plugin dirs
├── tasks/memory_plugin.yml                          # fetch plugin tarball + wheels (checksums), install to ro dir (R-003)
├── tasks/main.yml                                   # include memory_plugin; Open WebUI filter reconcile; memories import + off (R-007, R-008)
├── templates/agent-config.yaml.j2                   # memory.provider: hindsight
├── templates/hindsight-config.json.j2               # plugin config (R-003), ro mount
├── templates/docker-compose.yml.j2                  # ro mounts for plugin + deps; PYTHONPATH; ENABLE_MEMORIES=false
└── files/open_webui/memory_filter.py                # Open WebUI filter (R-007)
ansible/roles/hermes/templates/hermes-agent-egress.sh.j2   # skip own rule for via_proxy MCP entries (R-005)
ansible/roles/llm_router/tasks/virtual_keys.yml      # per-client `models` override (R-011)
ansible/roles/service_backup/templates/snapshot/memory.sh.j2          # pg_dump -Fc + export ZIP (R-013)
ansible/roles/service_backup/templates/restore/memory-compose.yml.j2  # restore drill stack (R-014)
ansible/roles/proxmox_mounts/tasks/main.yml          # + /mnt/nas/homelab_memory
ansible/roles/alloy/defaults/main.yml                # + redaction pattern for memory keys
ansible/group_vars/services/vars.yml                 # pins, memory_ip/ports, caddy_services (memory = UI tile, memory-api), hermes_mcp_servers, llm_router_clients
ansible/group_vars/all/vars.yml                      # service_backups.memory (05:30)
ansible/version-sources.yml                          # hindsight, pgvector, plugin
ansible/inventories/{prod,lab}/hosts.yml             # memory host
ansible/inventories/lab/lab-overrides.yml            # memory_ip: "10.99.0.223"
ansible/host_vars/memory.yml                         # monitoring_contract, healthcheck profile, log rules
ansible/host_vars/hermes.yml                         # + plugin failure log rule
python/tests/guardrails/                             # new and updated guards (see research R-018)
docs/backlog/097-spike/                              # harness: render production config, 3-client test (R-017)
docs/backlog/{083,065}-*.md, specs/002-core-services-lxc/spec.md, docs/architecture.md   # amendments (FR-022)
# off-repo, owner's dotfiles: Claude Code hooks (R-010)
```

**Structure Decision**: One new role (`memory`), modelled on `ntfy`. Everything else extends
existing roles and lists. The extension policy lives in the existing Python package to inherit
its test, coverage and mutation tooling. The shim is the only file that imports Hindsight.

## Rollout order

Each PROD step goes through `Prod 1 - LXC Promote` → `Prod 2 - LXC Apply`, which includes the
LAB rehearsal.

1. **Preconditions**:
   - The Synology share `homelab_memory` exists.
   - `ssh pve sudo pct list` shows no untracked container at `.223`.
   - The vault entries are created.
2. **Harness gate** (FR-021, quickstart § 1): run on the dev Mac against the pinned images, the
   rendered `server.env`, the plugin config, the extension and the client list. Meet SC-001 to
   SC-005 and record the results under `docs/backlog/097-spike/results/<date>-prod-render/`.
3. **Create the LXC**: `lxc-lifecycle.yml` with `add`, `prod`, `memory`.
4. **llm-router**: add the `memory` client (embed and rerank only).
5. **memory**: deploy, with the web UI. LAB proves liveness without embeddings and that the UI
   serves its login page (SC-008). PROD runs the deploy probe (R-019), adds the backup timer and
   the portal tile; check quickstart § 11.
6. **reverse_proxy**: the `memory-api` route (and the `memory` portal tile once the UI ships).
   DNS is a wildcard to `.211`, so the route is all that is missing. Before step 7, an
   authenticated `GET https://memory-api.hus-sky.no/v1/default/banks/owner/stats` with the
   Hermes key returns 200 (quickstart § 3). Without it, Hermes runs every turn without memory.
7. **hermes**: plugin, config and MCP entry. LAB proves the agent stays healthy with memory
   unreachable. In PROD, a fresh conversation shows recall (quickstart § 4).
8. **monitoring**: scrape, probe and rules (log rules start disabled, awaiting a 7-day baseline).
9. **Open WebUI** (part of the `hermes` deploy, separate PR): filter, memories import, memories
   off.
10. **Claude Code**: only after the accepted risk is confirmed against the Claude Enterprise
   Guidance & Guidelines. Mint the key, then enable the hooks in one private repo.
11. **US-4 and US-5**: restore drill, the forget/correct check and the revocation drill.
12. **Docs**: amend `083`, `065` and `002`, and update the architecture table (FR-022).

## Complexity Tracking

No constitution violations. Six choices are recorded:

| Choice | Why needed | Simpler alternative rejected because |
|---|---|---|
| Custom Hindsight extension (policy module + shim), re-checked on every Hindsight bump | FR-011, FR-012: per-client identity, revocation and read-only. Upstream has one shared key (R-001) | Caddy bearer per client cannot filter MCP (JSON-RPC on one URL) and leaves tags self-declared; one shared key means revoking Claude Code rotates every client |
| Split policy module / shim | Tests and mutmut must run without installing Hindsight's server package in the gate venv | One file importing `hindsight_api` would need the server and its dependencies in CI for a ~100-line policy |
| `webui_vault_var` on a `hermes_mcp_servers` entry | The list feeds both the agent and Open WebUI with one key, but FR-011 needs each client to write under its own identity (R-009) | A second list duplicates URL and enable logic, which the list exists to prevent (`065` FR-011) |
| Per-client `models` on `llm_router_clients` | FR-004, SC-003: memory must make zero chat-model calls; scoping its key to two aliases enforces it at the gateway (R-011) | Trusting the server config alone leaves one env var between memory and the chat queue that starved chat in the spike |
| Web UI as its own container and client, with a `curator` scope | FR-023: owner choice (2026-10-31) of a read-write UI that may also hard-delete and retry, with changes attributed to it | Enabling the UI inside the API container shares the gateway key, database password, memory and restarts; giving the UI the admin key lets one login export or wipe the store |
| `via_proxy` on a `hermes_mcp_servers` entry | The memory MCP endpoint is reached through Caddy (TLS, FR-010). The egress script derives an iptables rule from each URL's host, which must be an IP | Direct `http://memory_ip:8888` for the agent breaks FR-010's TLS for one client and adds an egress rule FR-017 does not need |
