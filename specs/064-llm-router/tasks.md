---
description: "Task list for 064-llm-router implementation"
---

# Tasks: LLM Router (gateway LXC)

**Input**: Design documents from `/specs/064-llm-router/`
**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/)

**Tests**: No TDD unit-test suite is generated — the spec does not request one, and this feature ships
no application code. Per Constitution § Test-Driven Changes, validation is **non-destructive checks**
(`pve-service-deploy plan`, `act -l`, preflight assertions) plus the drills in
[quickstart.md](./quickstart.md), which are first-class tasks below rather than an afterthought.

**Revised after `/speckit.analyze`**: Redis dropped (FR-014 amended), exposure scope settled to
LAN + tailnet (FR-008 amended), and three coverage gaps closed — all-backends-down detection
(FR-018/SC-013), a genuine Mac power-off drill (SC-001), and SC-011 verification. Task IDs were
renumbered in the same pass; they are sequential in execution order.

## Status — reconciled 2026-09-19

**The gateway is deployed and serving at `192.168.1.220`.** doctor 13/13, pipeline apply green,
fault injection executed. Merged as #202.

This list was written before any of that and had drifted badly: it described Ollama over the
tailnet, a tailscaled sidecar, metered OpenRouter/Anthropic tiers and a LAB on `192.168.20.0/24`,
none of which survive. Every task below has been reconciled against what actually happened rather
than marked done wholesale — several **failed** when finally run, and those are recorded as failures
with the fix, because that is the useful part.

Marker meanings: `[X]` done · `[ ]` genuinely still open · `[~]` withdrawn, not applicable, or not
verifiable — with the reason inline.

Two whole-plan corrections that invalidate wording throughout:

- **SC-001 is withdrawn.** There is no standby. With the Mac away every alias **fails clean**; it
  does not still answer. Any "the Mac can be powered off and every alias still answers" phrasing
  below is void — see `amendment-drop-metered-tiers.md`.
- **LAB is not a separate environment.** The two tfvars templates are byte-identical for this
  service, so "deploy to LAB" and "promote to PROD" build the same LXC at the same address. The
  *inventories* differ completely, which is a separate trap — see T051.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Parallelizable — different file, no dependency on an incomplete task
- **[Story]**: US1–US5, mapping to spec.md user stories

## Path Conventions

Homelab IaC layout (not `src/`+`tests/`): `terraform/`, `ansible/`, `scripts/`, `.github/workflows/`.
All paths are repo-relative.

---

## Phase 1: Setup (Registration & Provisioning Inputs)

**Purpose**: Everything that must land in the same PR as the service (Constitution V, FR-011), plus
the Terraform inputs. All edits to existing central files — no new abstractions.

- [X] T001 [P] Add `llm-router = "192.168.1.220/24"` to the `service_ips` map in `terraform/environments/prod.tfvars.template` (next free address after eurooffice `.219`)
- [X] T002 [P] Add `llm-router` to the `service_ips` map in `terraform/environments/lab.tfvars` (`192.168.20.219/24`, next after financial-scenario — this file's own subnet) and `lab.tfvars.template` (`192.168.1.220/24`, matching the CI template's prod-mirrored range). *(Corrected during implementation — the original task text guessed `10.99.0.x`, which matches neither file; the two lab files use genuinely different subnets.)* **Superseded 2026-09-19**: `lab.tfvars`'s `192.168.20.219` is dead weight — `pve-service-deploy` resolves tfvars from `TFVARS_DIR`, rendered from `lab.tfvars.template`, so the pipeline never reads this file. The address that matters is the template's `192.168.1.220`.
- [X] T003 Add `module "llm_router_lxc"` to `terraform/main.tf` using `./modules/lxc_service` with `cores = 2`, `memory = 4096`, `disk_gb = 16`, `ip = var.service_ips["llm-router"]`, and **no `features_mount`** (FR-012 — no NFS). Mirror the `market_model_lxc` block; comment that the mount is absent by requirement
- [X] T004 [P] Add `"llm-router": ["module.llm_router_lxc"]` to `scripts/lab/service-scope-allowlist.json` (protected path — the PR needs the `allow-protected-path-changes` label)
- [X] T005 [P] Add `llm-router` to the `service` choice list in `.github/workflows/lxc-deploy-lab.yml`
- [X] T006 [P] Add `llm-router` to the `service` choice list in `.github/workflows/lxc-promote-lab.yml`
- [X] T007 [P] Add `llm-router` to the `service` choice list in `.github/workflows/lxc-promote-prod.yml`
- [X] T008 [P] Add the `llm-router` host (`ansible_host: 192.168.1.220`, `ansible_user: root`) to the `services` group in `ansible/inventories/prod/hosts.yml` — **without this the monitoring contract in Phase 6 silently no-ops** (research D-107)
- [X] T009 Add vault variables to `ansible/group_vars/services/vault.yml` via `ansible-vault edit`. **Done 2026-09-19 with a different key set than written here**: `litellm_master_key`, `litellm_db_password`, `llm_router_client_hermes_key`, `llm_router_canary_key`, `mac_litellm_key`. ~~`openrouter_api_key`~~, ~~`anthropic_api_key`~~, ~~`tailscale_authkey`~~ are withdrawn — no deployment consumes them. `litellm_db_password` must be URL-safe (see T069)
- [X] T010 Validate the three workflow edits parse with `act -l` from the repo root; if Docker or `act` is unavailable, record the reason in the PR notes (Constitution § Local Workflow Testing)

**Checkpoint**: The service is registered everywhere the pipeline looks for it.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The role, its data, and its templates. **No user story can be exercised until this phase completes.**

- [X] T011 Add to `ansible/group_vars/services/vars.yml`: `llm_router_version` (pinned LiteLLM tag, never `latest`), `llm_router_postgres_version`, `llm_router_tailscale_version`, `llm_router_ip: "192.168.1.220"`, `llm_router_port: 4000`, alongside the existing `*_version` pins (FR-001). **No Redis pin** — FR-014 requires it only above one worker **Superseded in part**: `llm_router_tailscale_version` was removed with the sidecar. The pins that remain are the LiteLLM and Postgres tags, plus `llm_router_request_timeout`/`llm_router_num_retries` added by T073.
- [X] T012 Add the `llm_router_aliases` mapping to `ansible/group_vars/services/vars.yml` for `hermes-fast`, `hermes-balanced`, `hermes-deep`, following the aggregate shape in [data-model.md](./data-model.md#entity-alias-mapping-the-aggregate). Local deployments use the Mac's MagicDNS name (`*.ts.net`), never an IP (FR-013); `hermes-deep` maps to `anthropic/claude-sonnet-5` (research D-106) **Superseded 2026-09-15/19**: local deployments no longer use a MagicDNS `*.ts.net` name — they use the Mac's mDNS `.local` name over the LAN — and `hermes-deep` is `openai/reasoner` on the Mac, not `anthropic/claude-sonnet-5`. The metered deployments are gone entirely.
- [X] T013 Add `llm_router_clients` (per-consumer alias, `key_env`, `max_budget`, `budget_duration`, optional `rpm_limit`) and `llm_router_gateway_budget` to `ansible/group_vars/services/vars.yml`. Set caps against Sonnet 5 **list** pricing ($3/$15 per 1M), not the introductory rate that expires 2026-08-31 (research D-106)
- [X] T014 [P] Create `ansible/roles/llm_router/defaults/main.yml` with `llm_router_install_dir: /opt/llm-router`, `llm_router_data_dir: /opt/llm-router-data`, and the LiteLLM/Postgres/Tailscale image repositories (tags come from `group_vars`, per the `market_model` split)
- [X] T015 [P] Create `ansible/roles/llm_router/handlers/main.yml` with a `Restart llm-router` handler
- [X] T016 Create `ansible/roles/llm_router/tasks/preflight.yml` asserting: `llm_router_version` pinned and not `latest`; all vault variables present and non-empty; Docker daemon running; **alias fallback graph acyclic and terminating**; every referenced alias defined; every `tier: local` deployment has a `*.ts.net` `api_base` and not an IP literal (FR-013); every non-local deployment names a non-empty `api_key_env`; and `llm_router_gateway_budget.max_budget > sum(llm_router_clients.max_budget)` — fail, do not warn, because a cap below the client sum is a silent homelab-wide outage ([data-model.md](./data-model.md#entity-gateway-budget)) **Superseded in part**: the FR-013 assertion now requires a `.local` mDNS name, not `*.ts.net`; the hand-written credential assertion was narrowed to the gateway's own keys (T068); and a URL-safety assertion was added (T069).
- [X] T017 Create `ansible/roles/llm_router/templates/config.yaml.j2` rendering `model_list`, `router_settings` and `general_settings` per [contracts/alias-mapping.md](./contracts/alias-mapping.md). Credentials by `os.environ/<NAME>` indirection only. Set `background_health_checks: true`, `health_check_interval: 60` (LiteLLM defaults to 300), `background_health_check_model_groups` scoped to aliases with a health-checked deployment, `allowed_fails: 2`, `cooldown_time: 60`, `enable_pre_call_checks: true`. **No alias name may appear literally in the template** — the template iterates, it never branches (FR-003, FR-004, FR-005, research D-101)
- [X] T018 Create `ansible/roles/llm_router/templates/docker-compose.yml.j2` with **three** services — `litellm`, `postgres`, and the `tailscale` userspace sidecar (`TS_USERSPACE=true`, `--outbound-http-proxy-listen`, vault-sourced `TS_AUTHKEY`) satisfying FR-017. **No Redis** (FR-014, research D-104). Set `HTTP_PROXY`/`HTTPS_PROXY` on the litellm service pointing at the sidecar and `NO_PROXY=localhost,127.0.0.1,postgres` so database and loopback traffic bypass it (research D-102). Pin every image; add a container healthcheck per service **Superseded 2026-09-15/19**: **two** services, not three — the tailscaled sidecar is gone with FR-017, and with it `HTTP_PROXY`/`NO_PROXY`. `extra_hosts` was added by T070.
- [X] T019 Create `ansible/roles/llm_router/tasks/main.yml`: include preflight; create install and data directories; template `config.yaml` and `docker-compose.yml`; `community.docker.docker_compose_v2` with `state: present`, `pull: always`; wait for port 4000; assert `/health/readiness` returns 200. Follow `ansible/roles/market_model/tasks/main.yml` for structure
- [X] T020 [P] Create `ansible/playbooks/llm-router.yml` applying `lxc_base`, then `geerlingguy.docker` and `llm_router`, matching `ansible/playbooks/market-model.yml`. The filename must match the service name — `pve-service-deploy` resolves the playbook as `ansible/playbooks/${SERVICE}.yml`
- [X] T021 [P] Create `scripts/healthcheck/llm-router.sh` delegating to `healthcheck.py --host llm-router`, copying the argument handling in `scripts/healthcheck/market-model.sh`. Make it executable
- [X] T022 [P] Create `ansible/host_vars/llm-router.yml` with `healthcheck_url` pointing at port 4000 `/health/readiness`, `healthcheck_profile: lan`, and the `monitoring_contract` skeleton per [contracts/monitoring.md](./contracts/monitoring.md). Alert rules are filled in Phase 6
- [X] T023 Run the plan and confirm it is scope-clean. **Done** — `1 to add, 0 to change, 0 to destroy`, only `module.llm_router_lxc`, blast radius non-destructive, evidence pack verified. Required T066 first: the pipeline refuses to plan a service with no per-service Terraform root

**Checkpoint**: Foundation ready. The service can now be deployed and stories exercised.

---

## Phase 3: User Story 2 - Deploy comes up healthy through the gated pipeline (P1) 🎯 MVP

> **Ordering note**: US1, US2 and US3 are all P1. US2 runs first because it is the enabling story —
> there is no gateway to route through, retier, or observe until it is deployed. This is a dependency
> ordering within equal priority, not a re-prioritisation.

**Goal**: A repeatable, idempotent, healthy deploy through the gated LAB→PROD pipeline.

**Independent Test**: Run the pipeline against the pinned tag; containers reach `Up (healthy)`;
`/health/readiness` returns 200; a re-run changes nothing and the pin holds.

- [X] T024 [US2] Deploy to LAB. **Done** — LXC created at `192.168.1.220`, ansible `ok=63 changed=3 failed=0`. **Two** containers, not three: the tailscaled sidecar was removed with FR-017
- [X] T025 [US2] Verify readiness. **Done** — `{"status":"healthy","db":"connected"}`, HTTP 200
- [~] T026 [US2] ~~Verify the tailnet path (FR-017, research D-102): MagicDNS through the outbound HTTP proxy, `ALL_PROXY`/SOCKS5 fallback if httpx ignores `HTTP_PROXY` on `ollama_chat`.~~ **WITHDRAWN** — FR-017 is withdrawn, the sidecar is gone, no leg crosses the tailnet and there is no `ollama_chat` path. The name-resolution problem it was guarding did turn out to be real, in a different place: see T067 and T070
- [X] T027 [US2] Verify the free metric surface. **Done** — `/metrics` IS populated on the pinned image with `litellm_settings.callbacks: [prometheus]`. Real names confirmed (`litellm_deployment_state`, `litellm_spend_metric_total`, `litellm_remaining_team_budget_metric`, …). So T050's fallback is not needed. Also found: `require_auth_for_metrics_endpoint: true` hangs indefinitely against this version, so the endpoint stays at LiteLLM's open default (research D-105)
- [X] T028 [US2] Re-run the apply and confirm idempotency (SC-004). **Done, and it failed the first time** — the second apply died on duplicate key aliases because the idempotency lookup could never work. Fixed in T071; repeated applies are now clean
- [X] T029 [US2] Run `scripts/healthcheck/llm-router.sh --profile lan`. **Done via the pipeline's post-apply gate** — PASS against `http://192.168.1.220:4000/health/readiness`. It cannot be run ad hoc off-box: it resolves hosts from `inventories/generated/hosts.yml`, which only exists on `pve`
- [ ] T030 [US2] Promote through `lxc-promote-lab` then `lxc-promote-prod`. **Still open, and it no longer means what it says.** `lab.tfvars.template` and `prod.tfvars.template` are byte-identical for this service, so both stages build the same LXC at the same address — the gateway is already running at its final address. Promotion is a gating formality here, not a second deployment

**Checkpoint**: A healthy, idempotent, pinned gateway is running in PROD. US1, US3, US4, US5 can now proceed.

---

## Phase 4: User Story 1 - A client gets an answer regardless of the Mac's state (P1)

**Goal**: ~~The Mac's availability is invisible to callers.~~ **Rewritten 2026-09-19.** With the metered tiers gone the Mac is a hard dependency and its absence is *visible by design*: every alias must **fail clean** — a prompt error naming the unreachable backend, never a hang — and rejoin without operator action when it returns.

**Independent Test**: The downed-backend drills (T034/T035) — remove the Mac, confirm every alias
errors promptly and legibly rather than hanging, then confirm automatic recovery. *(The two drills
turned out to be one: stealth mode on the Mac blackholes a stopped server exactly as it does a
vanished host. See T035.)*

- [~] T031 [US1] ~~Confirm Ollama runs headless with `OLLAMA_HOST=0.0.0.0` and `OLLAMA_KEEP_ALIVE=-1`.~~ **WITHDRAWN** — Ollama is not the local runtime and that Mac was returned. Replaced by the Mac-side work: LiteLLM bound to `0.0.0.0:4000` in front of oMLX on `127.0.0.1:8000` (done 2026-09-16), and T067's mDNS announcer. The residency half survives as T077 and is **still unverified**
- [X] T032 [US1] Happy path against all three aliases with a client key. **Done** — `hermes-fast` 2.0s, `hermes-balanced` 1.3s, `hermes-deep` 2.6s, each a real completion
- [ ] T033 [US1] Verify attribution from metrics that `hermes-fast` was served by the **local deployment id** (SC-002 is about attribution, not merely getting an answer). **Still open** — the request path is proven, the metrics assertion is not. Now checkable: the `llm-router` scrape job went live 2026-09-19
- [X] T034 [US1] **Downed-backend drill A — server stopped (SC-008). Done, and it FAILED.** The written expectation ("a valid completion from the standby") is void: SC-001 is withdrawn and there is no standby. Against the rephrased clause it failed anyway — every alias **hung past 300s and returned nothing**. Root cause and fixes in T073/T074. Now: a bounded HTTP 500 naming the model group
- [X] T035 [US1] **Downed-backend drill B — vanished host. Done by substitution, and the drill's own premise was wrong.** The Mac could not be powered off (the agent ran on it), so the blackhole was reproduced with a `DOCKER-USER` DROP rule — a faithful stand-in, because stealth mode makes a *stopped* server behave identically: LXC→Mac:4000 with nothing listening hung the full 25s window, while the same probe against `pve` refused in 0.001s. **T034 and T035 are the same failure mode on this Mac**, so the distinction the task rests on does not exist here
- [X] T036 [US1] Recovery drill, ≤60s, no operator action (AS-1.4). **Done — recovered in 51s**, no intervention
- [X] T037 [US1] All-deployments-in-cooldown drill: fail fast with a clear error. **Done** — `HTTP 429` in 0.03s, "No deployments available for selected model, Try again in 60 seconds. Passed model=hermes-fast". Only true after T074; before it, every request paid the full timeout
- [X] T038 [US1] Context-escalation check (FR-006, SC-009). **Done 2026-09-20 — the escalation works, and it had never been exercised before today.** A 170,305-token prompt was served in 901.8s through the gateway, well above `reasoner`'s 131,072 window, so the Mac's `context_window_fallbacks: reasoner → Qwen3.8-27B-8bit:qwen-long` fired. This also validates the 20-minute envelope against a real workload rather than a synthetic one. **Caveat, measured: a narrow band just above the boundary is broken** — a 132,658-token prompt was REJECTED in 0.56s with "Prompt too long ... exceeds max context window of 131072" instead of escalating, because LiteLLM's pre-call token estimate undercounts against oMLX's tokenizer and so still considered `reasoner` viable. Both deployments declare `max_input_tokens` correctly and `enable_pre_call_checks` is on; the estimate is the weak link. Tracked as backlog 070
- [ ] T039 [US1] Cold-load tuning. **Still open, and its tell-tale is gone** — there is no metered tier, so unexpected metered volume can no longer signal a false fallback. The hazard is unchanged (a cold load tripping the request timeout) and is now bounded by `llm_router_request_timeout`; the lever is oMLX pinning, which is T077 and unverified

**Checkpoint**: ~~The Mac can be powered off and every alias still answers.~~ **Void — SC-001 is withdrawn.** The replacement promise, and what was actually verified: the Mac's absence produces a clear error within a bounded time and never a hang, and recovery is automatic (51s measured).

---

## Phase 5: User Story 3 - Retiering is a config edit, not a code change (P1)

**Goal**: Prove the FR-003 indirection holds before the Mac's 32 GB → 128 GB upgrade arrives.

**Independent Test**: Change one `deployments` entry, deploy, confirm the new deployment serves the alias and nothing else changed.

- [X] T040 [US3] Retier drill. **Done 2026-09-20** — `hermes-balanced` retiered `openai/coder` → `openai/fast` (8-bit swapped for the 4-bit sibling, so the change is observable rather than cosmetic), deployed, and the rendered `/opt/llm-router/config.yaml` on the LXC showed `model: openai/fast` under `model_name: hermes-balanced`. Served in 1.02s
- [X] T041 [US3] Assert **no client changed**. **Done** — the same client key called the same alias name (`hermes-balanced`) before and after, with no edit to any consumer. `git diff` across the retier touched exactly one file, `ansible/group_vars/services/vars.yml`
- [X] T042 [US3] Assert **no role logic changed**. **Done** — nothing under `roles/`, `templates/` or `tasks/` was touched by the retier, so the alias-mapping contract holds: the template iterates, it never branches on an alias name
- [X] T043 [US3] Revert the drill and redeploy. **Done** — redeployed from the unmodified branch, and the LXC's rendered config returned to `model: openai/coder`. Temporary branch deleted

**Checkpoint**: The 128 GB upgrade is now a one-line edit, rehearsed rather than hoped for.

---

## Phase 6: User Story 4 - Routing and spend are observable (P2)

**Goal**: Per-alias volume, per-deployment health and metered spend visible in Grafana; a downed Mac
raises its own distinct non-critical signal; a fully broken gateway cannot sit silently green.

**Independent Test**: With traffic across all three aliases, Grafana shows volume and per-deployment
outcomes; stopping **the Mac's LiteLLM** raises `LlmRouterLocalTierDown` as **info**; breaking every backend with no
traffic flowing raises `LlmRouterCanaryFailing` as **critical**.

- [X] T044 [US4] Extend `ansible/roles/monitoring_stack/templates/prometheus.yml.j2` so `monitoring_contract.scrape_targets` entries support an optional `authorization` block. Built as planned (optional, default-off, existing contracts render byte-identically). **Not exercised for llm-router** — live testing against the pinned image (below) found `require_auth_for_metrics_endpoint: true` hangs indefinitely on the master key; `/metrics` is left at LiteLLM's own open default instead (research D-105). The auth block remains available for a future service.
- [X] T045 [US4] Fill in `monitoring_contract.scrape_targets` in `ansible/host_vars/llm-router.yml` for `192.168.1.220:4000/metrics` with the bearer token sourced from vault (FR-009b)
- [X] T046 [US4] Add the routing alert rules to `ansible/host_vars/llm-router.yml`: `LlmRouterDown` (**critical**, from the `/health/readiness` liveness probe) and `LlmRouterLocalTierDown` (**info**, from `litellm_deployment_state` for the Ollama deployment). The severity split is deliberate — alerting critically on an intermittent-by-design backend trains the operator to ignore the channel (FR-009, [contracts/monitoring.md](./contracts/monitoring.md)) **Superseded in wording**: the local-tier signal is the Mac's **LiteLLM** deployment, not an Ollama one.
- [X] T047 [US4] Add `LlmRouterAllBackendsFailing` (**critical**) to `ansible/host_vars/llm-router.yml`, firing when the failure ratio across all deployments exceeds 90% over 10m. Note in a comment that this signal is silent without client traffic — T048 is the half that covers the idle case (FR-018)
- [X] T048 [US4] Implement the synthetic canary (FR-018): `canary.sh.j2` + `llm-router-canary.service/.timer` (60 min) run one real request against `hermes-fast`, writing a gauge to node_exporter's textfile collector. **Design addition beyond the original task**: node_exporter's textfile collector was not enabled anywhere in the fleet — added `node_exporter_textfile_directory` (default, task, systemd flag) as a small, generic, backward-compatible extension to the shared `node_exporter` role rather than building a bespoke ingestion path. The canary itself is modelled as an ordinary entry in `llm_router_clients` (alias `canary`, $1/mo cap) so it rides the same virtual-key provisioning and budget-headroom validation as every other client, rather than being a special case
- [X] T049 [US4] Create a Grafana dashboard at `ansible/roles/llm_router/files/llm-router-dashboard.json` and reference it via `monitoring_contract.dashboard_file`: per-alias request volume, per-deployment success/failure by deployment id, metered spend per alias, and a local-tier availability timeline
- [~] T050 [US4] ~~If T027 showed the metrics are enterprise-gated, add a `postgres_exporter` over `LiteLLM_SpendLogs`.~~ **NOT NEEDED** — T027 showed `/metrics` is populated on the pinned image. The condition this task was contingent on did not occur
- [X] T051 [US4] Deploy monitoring and verify the FR-009 signals, then break every backend with **no client traffic** and confirm an alert fires within one canary interval (SC-013, AS-4.4). **Both halves done.** The deploy half landed 2026-09-19 (scrape job, blackbox probe, five alert rules, dashboard) and required the **prod** path — `pve-service-deploy` layers `inventories/${ENVIRONMENT}/hosts.yml` for monitoring, and the lab inventory holds one host and no services. The SC-013 half ran 2026-09-20: blackholed the backend, triggered the canary as the timer does (`OnUnitActiveSec=60min`, verified), watched `llm_router_canary_success` flip to 0, Prometheus scrape it, and `LlmRouterCanaryFailing` go **firing with zero client traffic**. Restored: metric back to 1, alert `inactive`, no operator action. Note the canary's own failure cools the deployment down, so recovery needs one run after the cooldown lapses

**Checkpoint**: The gateway is observable, and neither a downed Mac nor a totally broken gateway can hide.

---

## Phase 7: User Story 5 - A runaway client cannot bill unbounded (P2)

**Goal**: Per-client keys with their own budgets, plus a gateway-wide backstop cap that alerts distinctly.

**Independent Test**: Drive one client past its cap — it is refused while others keep working; then
exhaust the gateway cap and confirm a distinguishable error and its own alert.

- [X] T052 [US5] Create `ansible/roles/llm_router/tasks/virtual_keys.yml` provisioning one LiteLLM virtual key per entry in `llm_router_clients`, idempotently, with `max_budget`, `budget_duration` and optional `rpm_limit`. Include it from `tasks/main.yml` after the stack is healthy (FR-015). *(Built during Phase 2, not Phase 7 — `tasks/main.yml` (T019) already includes it, and leaving the reference dangling would have left the role broken between phases.)*
- [X] T053 [US5] Configure the gateway-wide cap from `llm_router_gateway_budget`, with real headroom above the sum of per-client budgets (FR-010). **Redesigned from the original plan**: a standalone `/budget/new` object (tried first, live) has no corresponding Prometheus metric, so `LlmRouterBudgetCapExhausted` (T046) couldn't observe it. Rebuilt on LiteLLM's native **team** primitive instead — one team ("llm-router-gateway-wide") holds the cap, each client's key is generated on that team with its own budget as LiteLLM's documented "team member budget". This is what `litellm_remaining_team_budget_metric` reports, so the alert became implementable, and it's LiteLLM's own two-level primitive rather than a bespoke one. See `tasks/virtual_keys.yml`.
- [ ] T054 [US5] ~~Per-client budget breach drill.~~ **Not verifiable as written** — local deployments carry no per-token pricing, so spend accrues at exactly 0.0 and no cap can be reached (FR-010's spend half is inert). The runaway-loop guard is now **rate limiting**, so the drill that still has meaning is driving one client past its `rpm_limit` and confirming others keep serving. Not done
- [ ] T055 [US5] Attribution check on the breach (AS-5.2). **Not done**, and follows T054's reframing — attribute a *rate-limit* refusal to the specific client key, since a spend breach cannot occur
- [~] T056 [US5] ~~Gateway-cap drill: exhaust the gateway-wide cap and confirm a distinguishable error.~~ **NOT VERIFIABLE** — same root cause as T054. Spend is exactly zero, so the cap cannot be reached. SC-012 is marked not-verifiable in `spec.md`; the mechanism stays configured and untested until a priced tier returns
- [ ] T057 [US5] Add `LlmRouterBudgetCapExhausted` (**critical**) and verify it fires. **Rule added and deployed** 2026-09-19, visible on the monitoring host. **Firing cannot be verified** for the reason in T056, so this stays open rather than being claimed

**Checkpoint**: A looping agent costs one client's budget, not the homelab's.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [X] T058 [P] Blast-radius check (SC-006): `git grep -nE 'sk-|OPENROUTER_API_KEY=|ANTHROPIC_API_KEY='` over the repo excluding `specs/` and `docs/` returns no hits; confirm the rendered `/opt/llm-router/config.yaml` on the LXC contains only `os.environ/...` indirection; confirm **no Anthropic subscription or OAuth credential** exists anywhere (FR-007)
- [X] T059 [P] Exposure check (SC-007, FR-008): confirm no Caddy route, no public DNS name and no landing-page entry exist, and that `192.168.1.220:4000` is unreachable from outside the LAN and tailnet. **LAN reachability is expected and accepted** — see research D-108; do not treat a successful LAN request as a failure
- [X] T060 [P] Confirm request logging is bounded and on local disk only, with prompt/response bodies not logged by default, in `ansible/roles/llm_router/templates/docker-compose.yml.j2` (FR-012)
- [X] T061 [P] Verify all image pins are recorded in `ansible/group_vars/services/vars.yml` alongside the other `*_version` pins, and that none is `latest` (FR-001)
- [~] T062 [P] ~~Verify SC-011 after one week: background health checks under 1% of metered spend.~~ **MOOT** — with no metered tier there is no denominator. Spend is zero by construction, not by scoping. Re-arm this if a priced tier returns
- [ ] T063 Run the full [quickstart.md](./quickstart.md) end to end as the acceptance pass. **Still open** — and `quickstart.md` needs the same reconciliation this file just had before it is worth running
- [X] T064 [P] Update `docs/backlog/064-llm-router.md` to mark the item delivered, and record the resolutions of D-001/D-003/D-004 plus the Phase 0 and post-analyze corrections (D-102, D-103, D-104, D-108) so the backlog does not keep presenting them as open
- [X] T065 [P] **File a separate backlog item** for the pre-existing gap found in research D-107: `market-model` and `eurooffice` are missing from `ansible/inventories/prod/hosts.yml`, which means their monitoring contracts likely contribute nothing in prod. Out of scope for this feature — but it should not stay undocumented

---

## Phase 9: Delivered 2026-09-19 — not in the original plan

Found by actually deploying the thing. Each of these either failed the deploy outright or shipped a
silent hole, and none was anticipated above.

- [X] T066 Create the per-service Terraform root at `terraform/services/llm-router/`. The pipeline refuses to plan without one (`Missing per-service Terraform root ... create it to avoid cross-service plans`). Phase 1's registration covered the dropdowns, the allowlist and the tfvars, but not this
- [X] T067 Make the Mac's `.local` name resolve at all. It resolved from **nowhere** in the homelab: the Mac *announces* mDNS records but never *answers* a query, because stealth mode is MDM-enforced. Fixed with a LaunchAgent re-announcing every 45s — no firewall or MDM change. `mac-mdns-announcer/`
- [X] T068 Stop preflight demanding `openrouter_api_key`/`anthropic_api_key`, deleted with the metered tiers. Would have failed every deploy
- [X] T069 Assert `litellm_db_password` is URL-safe. A `/` from `openssl rand -base64` made `DATABASE_URL` parse the password tail as the port (`Prisma P1013: invalid port number`). Asserted rather than escaped: Jinja's `urlencode` uses `safe="/"`, so the obvious fix is a silent no-op
- [X] T070 Resolve the Mac's name on the LXC and pass it to the container as `extra_hosts`. `network_mode: host` — the candidate `deploy-plan.md` recorded — does **not** work: it shares the network namespace, not the filesystem, so the container keeps its own `nsswitch.conf` with no `libnss-mdns`. Reverted, along with the loopback-published Postgres that only existed to serve it
- [X] T071 Make virtual-key provisioning idempotent (SC-004). `/key/info` looks up by `key` only, so `?key_alias=` 404s for a key that exists; the lookup always said "not provisioned" and the second apply died on duplicate aliases. Rebuilt on `/key/list?return_full_object=true`
- [X] T072 Fix the canary template referencing `node_exporter_textfile_directory`, which `include_role` never exports across plays. Could not have worked on any host
- [X] T073 Bound the failure case with an explicit `timeout` and `num_retries: 0`. Without them a dead backend hung the caller past 300s with no status at all
- [X] T074 Set `allowed_fails: 0` so the dead deployment is actually ejected. The failure **counter** is cached with a TTL of `cooldown_time`, so a threshold above 0 is unreachable whenever a failure takes longer than that — at 135s per failure against 60s of TTL, `allowed_fails: 2` could never be reached and every request paid the full timeout
- [X] T075 Scope client keys to the declared aliases (FR-002). `openai/fast` — the declared `provider_model` — was addressable by a client key and returned a real completion, bypassing the alias and the `context_window`/fallback behaviour it declares. The doctor check meant to catch this probed `claude-sonnet-5`, deleted with the frontier tier, so it passed while testing nothing
- [X] T076 Stop publishing an internal probe URL on the public apex. `/api/status` proxies Prometheus unauthenticated, so llm-router's liveness target put `http://192.168.1.220:4000/health/readiness` on `hus-sky.no`. Added an optional `instance_label` to liveness targets; the scrape path already had one
- [X] T077 Show the gateway on `hus-sky.no` without routing to it. `caddy_services` couples route and tile, and `user_facing: false` suppresses only the tile — the wrong half. `caddy_landing_links` renders a tile with no vhost; the card links to the Grafana dashboard, gated by Grafana's auth. FR-008 amended to permit exactly this
- [X] T079 **Per-deployment request timeouts.** The single `llm_router_request_timeout` from T073 made `hermes-deep`'s own declared 262144 window unusable — a request well inside it returned `408 Timeout` at 180.3s, because a cold 108k-token prefill takes ~397s. Now per-deployment: fast 180s, balanced 300s, deep 1200s. Affordable only because T074's cooldown means exactly one request pays the long timeout before the deployment is ejected.
- [X] T080 **Move the local-tier leg to verified TLS, lifting the ~300s ceiling.** Plaintext inbound to the Mac is closed after ~300s with no application-layer response data and unpredictably thereafter (658s, 1443s) even with SSE keepalives; TCP keepalive does not help, so the closer parses HTTP. TLS held 1500s and 1800s of complete silence, twice. Terminator on the Mac relays to LiteLLM over loopback, so LiteLLM and oMLX are both back on 127.0.0.1 and the terminator is the only LAN-exposed process; `mac_litellm_key` stops crossing the LAN in plaintext. Certificate is verified, not trusted blindly. Timeouts raised to 1200s on all three aliases. Six alternatives measured and rejected — see backlog 069.
- [X] T078 **Verify oMLX residency/pinning (FR-016). Done 2026-09-19 — all four aliased models pinned.** The admin API was a dead end: `/admin/api/models` refuses every credential on the machine, because the GUI reaches the server over a unix socket rather than HTTP. Verified instead from `~/.omlx/model_settings.json`'s `is_pinned` — the same lever that sets it — by `mac-checks/verify-omlx-residency.sh`, which derives fallback targets from the Mac's own `context_window_fallbacks` and is fault-injected both ways. Asserts configuration, not live engine state; `/health` exposes only an aggregate `loaded_count`

**Checkpoint**: Everything the plan did not foresee is landed except T078.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies.
- **Phase 2 (Foundational)**: Depends on Phase 1. **Blocks every user story.**
- **Phase 3 (US2)**: Depends on Phase 2. **Blocks US1, US3, US4, US5** — nothing can be exercised against a gateway that is not deployed.
- **Phases 4–7 (US1, US3, US4, US5)**: All depend on Phase 3. Independent of one another thereafter.
- **Phase 8 (Polish)**: Depends on all desired stories. T062 additionally needs one week of elapsed operation.

### User Story Dependencies

- **US2 (P1)**: The enabling story — must complete first despite equal priority.
- **US1 (P1)**: After US2. Needs T031 (Mac serving) as an external prerequisite.
- **US3 (P1)**: After US2. Independent of US1.
- **US4 (P2)**: After US2. T027's result (taken during US2) decides whether T050's fallback is needed.
- **US5 (P2)**: After US2. Independent of US1/US3/US4.

### Critical Path

~~`T003 → T011/T012 → T016–T019 → T024 → T026 (tailnet path) → T034/T035`~~

**What the critical path turned out to be** (2026-09-19). The instinct was right — the
name-resolution task and the downed-backend drills were the ones that forced design changes — but
they were not the tasks written down:

`T066 (terraform root) → T009 (vault) → T067 (mDNS announcer) → T070 (extra_hosts) → T024 → T034/T035 → T073/T074`

T026 was withdrawn before it could be run. Its *concern* — can the container reach the Mac by name —
was the single biggest source of failed deploys, just over the LAN rather than the tailnet, and in
the container's resolver rather than a proxy. T034/T035 did force a design change, twice: first the
missing request timeout, then the unreachable cooldown threshold.

### Parallel Opportunities

- **Phase 1**: T001, T002, T004–T008 are different files — fully parallel. T003 and T009 are separate; T010 follows T005–T007.
- **Phase 2**: T014, T015, T020, T021, T022 are independent files. T016–T019 touch the role's task/template set and should be sequential.
- **Phases 4–7**: Once Phase 3 completes, the four remaining stories can be worked in parallel.
- **Phase 8**: T058, T059, T060, T061, T064, T065 are all independent.

---

## Parallel Example: Phase 1

```bash
# All registration edits touch different files — run together:
Task: "Add llm-router to service_ips in terraform/environments/prod.tfvars.template"
Task: "Add llm-router allowlist entry in scripts/lab/service-scope-allowlist.json"
Task: "Add llm-router to service dropdown in .github/workflows/lxc-deploy-lab.yml"
Task: "Add llm-router to service dropdown in .github/workflows/lxc-promote-lab.yml"
Task: "Add llm-router to service dropdown in .github/workflows/lxc-promote-prod.yml"
Task: "Add llm-router host entry in ansible/inventories/prod/hosts.yml"
```

---

## Implementation Strategy

### MVP (Phases 1–3)

Setup → Foundational → US2. Delivers a healthy, idempotent, pinned gateway in PROD. **Stop and
validate**: containers healthy, readiness 200, healthcheck evidence written, and — critically — T026
and T027 answered, because both can change the design.

### Incremental Delivery

1. Phases 1–3 → gateway deployed (MVP)
2. + Phase 4 (US1) → the Mac can be powered off and every alias still answers ← **the feature's actual promise**
3. + Phase 5 (US3) → retiering rehearsed before the 128 GB upgrade lands
4. + Phase 6 (US4) → observable, including the silent-total-failure case
5. + Phase 7 (US5) → runaway clients bounded

Stopping after step 2 leaves a genuinely useful system: routing works and fallbacks hold, but spend is
unobservable and unbounded. Do not leave it there for long — FR-010 exists because the first consumer
is an agent.

### Notes

- `[P]` = different files, no dependency on incomplete work.
- Commit after each task or logical group. The `allow-protected-path-changes` label was needed for T004 in the original PR (#201); the follow-up PR (#202) touches no protected path and needed no label — verify per PR rather than assuming.
- Every drill (T034, T035, T037, T040, T051, T054, T056) is an acceptance criterion, not an optional extra — the spec is explicit that SC-008 is "exercised as part of acceptance, not assumed".
