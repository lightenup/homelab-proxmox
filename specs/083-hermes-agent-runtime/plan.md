# Implementation Plan: Hermes Agent behind Hermes — a stock agent runtime and scheduler

**Branch**: `083-hermes-agent-runtime` | **Date**: 2026-10-17 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/083-hermes-agent-runtime/spec.md`

## Summary

Add the upstream Hermes Agent (`nousresearch/hermes-agent:v0.21.6`) as a third service in the existing
Hermes compose stack, running `gateway run` (scheduler + OpenAI-compatible API server). Open WebUI
gets a second connection to it as model `hermes-agent`. The agent:
- reaches models only through its own `064` gateway client;
- searches through the existing SearXNG;
- calls the same MCP servers as Open WebUI;
- delivers scheduled-job output to the phone through `082`'s ntfy `hermes` topic.

Safety controls:
- **Approvals** fail closed, and `config.yaml` is mounted read-only.
- **Egress** is cut to an allowlist by netfilter rules in the LXC's namespace.
- **The scheduler** proves it is alive through a node_exporter heartbeat that Ansible reconciles on
  PROD.
- **LAB** runs the runtime as a deploy gate only, with no ntfy token and no operational jobs.
- **The agent's data** joins the Hermes backup and the restore drill.
- **Open WebUI Automations** are retired.
- **Exposure**: a public-DNS exposure assertion guards the accepted terminal risk.

## Technical Context

**Language/Version**: YAML (Ansible 2.x), Jinja2, Bash; HCL only if LXC memory must grow. No
application code (FR-020). Job scripts are content.

**Primary Dependencies**:
- `nousresearch/hermes-agent:v0.21.6` (upstream image, unmodified)
- existing `openwebui/open-webui:0.11.3` and SearXNG
- `community.docker.docker_compose_v2`, `geerlingguy.docker`
- iptables (the same backend Docker uses in the LXC)
- `dnsutils`

**Storage**: agent data on the LXC's local disk under `{{ hermes_data_dir }}/agent`. It holds SQLite
state, jobs, scripts, memory and sessions, and is backed up to Synology through the existing
`hermes_backup` NFS bind-mount.

**Testing**: preflight assertions; deploy-time egress probes and DNS exposure assertion; LAB checks
Q-L1…Q-L10 and PROD checks Q-P1…Q-P10 ([quickstart.md](./quickstart.md)); restore drill.

**Target Platform**: the existing Hermes LXC (Debian, unprivileged, Docker), LAB and PROD.

**Project Type**: infrastructure configuration (Ansible role extension).

**Performance Goals**:
- A flagged command is refused in < 5 s (SC-008).
- Plain chat latency is unchanged (SC-005).
- Heartbeat every 15 min; stale alert at > 1 h.

**Constraints**:
- No published agent port.
- No Docker socket.
- Agent egress is allowlisted.
- LAB never reaches the phone.
- 6 GB LXC shared with Open WebUI (agent `mem_limit: 3g`, measured).

**Scale/Scope**: one owner, a handful of jobs, and agent chats at ≤ 20 rpm through the gateway.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|---|---|
| I. Spec-driven | Spec, plan and research in `specs/083-*`. 065's spec is amended in the same change (FR-022). ✅ |
| II. Secrets | Two new vault entries (`llm_router_client_hermes_agent_key`, `hermes_agent_api_server_key`). `.env` is rendered with `no_log` and excluded from backup; the Open WebUI key reconcile runs with `no_log` and takes its input on stdin. ✅ |
| III. Separation | Ansible configures inside the LXC (compose, netfilter, timers). Terraform is touched only if Q-L10 says memory must grow, as a sizing change. ✅ |
| IV. Code economy | No new role: the `hermes` and `hermes_backup` roles, compose file, preflight, drill and `host_vars/hermes.yml` are extended. One new template each for agent config, `.env`, the egress script and the heartbeat script. The MCP list is rendered from the existing single source. No per-job Ansible (SC-001). ✅ |
| V. Dual provisioning | Same service slug `hermes`, already in the workflow dropdowns. `deploy_environment` defaults to `prod`, and a laptop LAB run passes it explicitly (quickstart). ✅ |
| Networking | Allowlist IPs come from existing central vars (`llm_router_ip`, `reverse_proxy_ip`, `adguard_ip`, `hermes_mcp_servers`). One new central var: `hermes_agent_ip`. ✅ |
| Access control | Proxmox UI is not exposed; the agent is explicitly blocked from reaching it (egress rule 7). ✅ |

**Post-design re-check**: still passes. One accepted deviation, recorded in research R-010: Open WebUI
connection keys (secrets) are reconciled into its database. This is 065's own reconcile pattern,
narrowed to one `no_log` task, and is needed because PersistentConfig would otherwise make FR-006
inert on the existing deploy.

## Project Structure

### Documentation (this feature)

```text
specs/083-hermes-agent-runtime/
├── plan.md
├── research.md            # R-001 … R-012
├── data-model.md
├── quickstart.md          # LAB Q-L1…Q-L10, PROD Q-P1…Q-P10
├── contracts/
│   ├── agent-runtime.md   # chat interface, job-script contract, delivery, heartbeat
│   └── egress-allowlist.md
├── checklists/requirements.md
└── tasks.md               # /speckit-tasks
```

### Source Code (repository root)

```text
ansible/
├── group_vars/services/
│   ├── vars.yml                       # hermes_agent_version pin; hermes_agent_ip; llm_router_clients += hermes_agent;
│   │                                  #   drop hermes_automation_min_interval; hermes_managed_config += automations key
│   └── vault.yml                      # + llm_router_client_hermes_agent_key, hermes_agent_api_server_key (not in git)
├── host_vars/hermes.yml               # monitoring_contract.alert_rules += HermesAgentCronStale
├── playbooks/hermes-restore-drill.yml # + agent leg (no gateway, no ntfy env)
└── roles/
    ├── hermes/
    │   ├── defaults/main.yml          # hermes_agent_image, hermes_agent_operational, agent paths
    │   ├── tasks/preflight.yml        # pin, aliases, secrets, DNS exposure, LAB-no-token, MCP URL parse
    │   ├── tasks/main.yml             # agent dirs, config/.env, egress unit, heartbeat (PROD), probes,
    │   │                              #   Open WebUI connection reconcile, automations check
    │   ├── handlers/main.yml
    │   └── templates/
    │       ├── docker-compose.yml.j2      # + hermes-agent service, `agent` network, OPENAI_API_BASE_URLS
    │       ├── agent-config.yaml.j2       # new
    │       ├── agent.env.j2               # new
    │       ├── hermes-agent-egress.sh.j2  # new (+ systemd unit inline in tasks)
    │       └── agent-heartbeat.sh.j2      # new
    └── hermes_backup/templates/
        ├── backup_hermes.sh.j2        # + agent dir with SQLite snapshots
        └── restore_hermes.sh.j2       # + agent dir, UID 10000 ownership
specs/065-hermes-ai-workspace/spec.md  # amendments (FR-022)
docs/backlog/083-hermes-agent-runtime.md # status → specified
```

**Structure Decision**: extend the existing `hermes` and `hermes_backup` roles. The agent is part of
the Hermes service (same LXC, same deploy target, same backup), so no new role, playbook or workflow
entry is created.

## Complexity Tracking

| Item | Why needed | Simpler alternative rejected because |
|---|---|---|
| Netfilter egress chain + systemd re-apply unit | FR-008, the owner's decision to allowlist egress | A Proxmox LXC firewall would also restrict Open WebUI; an HTTP proxy is bypassable from a terminal |
| Read-only `config.yaml` mount | Approvals are a security control the agent itself must not switch off | Rendering it writable lets one terminal command undo FR-007 until the next deploy (kept as fallback) |
| Ansible-reconciled `heartbeat` job | Monitoring must not depend on owner action (owner's decision) | Owner-created job: the alert fires from day one until done, and again if deleted |
