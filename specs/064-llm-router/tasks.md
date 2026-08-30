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
- [X] T002 [P] Add `llm-router` to the `service_ips` map in `terraform/environments/lab.tfvars` (`192.168.20.219/24`, next after financial-scenario — this file's own subnet) and `lab.tfvars.template` (`192.168.1.220/24`, matching the CI template's prod-mirrored range). *(Corrected during implementation — the original task text guessed `10.99.0.x`, which matches neither file; the two lab files use genuinely different subnets.)*
- [X] T003 Add `module "llm_router_lxc"` to `terraform/main.tf` using `./modules/lxc_service` with `cores = 2`, `memory = 4096`, `disk_gb = 16`, `ip = var.service_ips["llm-router"]`, and **no `features_mount`** (FR-012 — no NFS). Mirror the `market_model_lxc` block; comment that the mount is absent by requirement
- [X] T004 [P] Add `"llm-router": ["module.llm_router_lxc"]` to `scripts/lab/service-scope-allowlist.json` (protected path — the PR needs the `allow-protected-path-changes` label)
- [X] T005 [P] Add `llm-router` to the `service` choice list in `.github/workflows/lxc-deploy-lab.yml`
- [X] T006 [P] Add `llm-router` to the `service` choice list in `.github/workflows/lxc-promote-lab.yml`
- [X] T007 [P] Add `llm-router` to the `service` choice list in `.github/workflows/lxc-promote-prod.yml`
- [X] T008 [P] Add the `llm-router` host (`ansible_host: 192.168.1.220`, `ansible_user: root`) to the `services` group in `ansible/inventories/prod/hosts.yml` — **without this the monitoring contract in Phase 6 silently no-ops** (research D-107)
- [ ] T009 Add vault variables to `ansible/group_vars/services/vault.yml` via `ansible-vault edit`: `openrouter_api_key`, `anthropic_api_key`, `litellm_master_key`, `litellm_db_password`, `tailscale_authkey` (ephemeral + tagged), and one key per client consumer. No literal secret enters git (Constitution II)
- [X] T010 Validate the three workflow edits parse with `act -l` from the repo root; if Docker or `act` is unavailable, record the reason in the PR notes (Constitution § Local Workflow Testing)

**Checkpoint**: The service is registered everywhere the pipeline looks for it.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The role, its data, and its templates. **No user story can be exercised until this phase completes.**

- [X] T011 Add to `ansible/group_vars/services/vars.yml`: `llm_router_version` (pinned LiteLLM tag, never `latest`), `llm_router_postgres_version`, `llm_router_tailscale_version`, `llm_router_ip: "192.168.1.220"`, `llm_router_port: 4000`, alongside the existing `*_version` pins (FR-001). **No Redis pin** — FR-014 requires it only above one worker
- [X] T012 Add the `llm_router_aliases` mapping to `ansible/group_vars/services/vars.yml` for `hermes-fast`, `hermes-balanced`, `hermes-deep`, following the aggregate shape in [data-model.md](./data-model.md#entity-alias-mapping-the-aggregate). Local deployments use the Mac's MagicDNS name (`*.ts.net`), never an IP (FR-013); `hermes-deep` maps to `anthropic/claude-sonnet-5` (research D-106)
- [X] T013 Add `llm_router_clients` (per-consumer alias, `key_env`, `max_budget`, `budget_duration`, optional `rpm_limit`) and `llm_router_gateway_budget` to `ansible/group_vars/services/vars.yml`. Set caps against Sonnet 5 **list** pricing ($3/$15 per 1M), not the introductory rate that expires 2026-08-31 (research D-106)
- [X] T014 [P] Create `ansible/roles/llm_router/defaults/main.yml` with `llm_router_install_dir: /opt/llm-router`, `llm_router_data_dir: /opt/llm-router-data`, and the LiteLLM/Postgres/Tailscale image repositories (tags come from `group_vars`, per the `market_model` split)
- [X] T015 [P] Create `ansible/roles/llm_router/handlers/main.yml` with a `Restart llm-router` handler
- [X] T016 Create `ansible/roles/llm_router/tasks/preflight.yml` asserting: `llm_router_version` pinned and not `latest`; all vault variables present and non-empty; Docker daemon running; **alias fallback graph acyclic and terminating**; every referenced alias defined; every `tier: local` deployment has a `*.ts.net` `api_base` and not an IP literal (FR-013); every non-local deployment names a non-empty `api_key_env`; and `llm_router_gateway_budget.max_budget > sum(llm_router_clients.max_budget)` — fail, do not warn, because a cap below the client sum is a silent homelab-wide outage ([data-model.md](./data-model.md#entity-gateway-budget))
- [X] T017 Create `ansible/roles/llm_router/templates/config.yaml.j2` rendering `model_list`, `router_settings` and `general_settings` per [contracts/alias-mapping.md](./contracts/alias-mapping.md). Credentials by `os.environ/<NAME>` indirection only. Set `background_health_checks: true`, `health_check_interval: 60` (LiteLLM defaults to 300), `background_health_check_model_groups` scoped to aliases with a health-checked deployment, `allowed_fails: 2`, `cooldown_time: 60`, `enable_pre_call_checks: true`. **No alias name may appear literally in the template** — the template iterates, it never branches (FR-003, FR-004, FR-005, research D-101)
- [X] T018 Create `ansible/roles/llm_router/templates/docker-compose.yml.j2` with **three** services — `litellm`, `postgres`, and the `tailscale` userspace sidecar (`TS_USERSPACE=true`, `--outbound-http-proxy-listen`, vault-sourced `TS_AUTHKEY`) satisfying FR-017. **No Redis** (FR-014, research D-104). Set `HTTP_PROXY`/`HTTPS_PROXY` on the litellm service pointing at the sidecar and `NO_PROXY=localhost,127.0.0.1,postgres` so database and loopback traffic bypass it (research D-102). Pin every image; add a container healthcheck per service
- [X] T019 Create `ansible/roles/llm_router/tasks/main.yml`: include preflight; create install and data directories; template `config.yaml` and `docker-compose.yml`; `community.docker.docker_compose_v2` with `state: present`, `pull: always`; wait for port 4000; assert `/health/readiness` returns 200. Follow `ansible/roles/market_model/tasks/main.yml` for structure
- [X] T020 [P] Create `ansible/playbooks/llm-router.yml` applying `lxc_base`, then `geerlingguy.docker` and `llm_router`, matching `ansible/playbooks/market-model.yml`. The filename must match the service name — `pve-service-deploy` resolves the playbook as `ansible/playbooks/${SERVICE}.yml`
- [X] T021 [P] Create `scripts/healthcheck/llm-router.sh` delegating to `healthcheck.py --host llm-router`, copying the argument handling in `scripts/healthcheck/market-model.sh`. Make it executable
- [X] T022 [P] Create `ansible/host_vars/llm-router.yml` with `healthcheck_url` pointing at port 4000 `/health/readiness`, `healthcheck_profile: lan`, and the `monitoring_contract` skeleton per [contracts/monitoring.md](./contracts/monitoring.md). Alert rules are filled in Phase 6
- [ ] T023 Run `scripts/lab/pve-service-deploy plan --service llm-router --env lab` and confirm the plan is scope-clean against the allowlist and creates only `module.llm_router_lxc` (non-destructive validation, Constitution § Test-Driven Changes)

**Checkpoint**: Foundation ready. The service can now be deployed and stories exercised.

---

## Phase 3: User Story 2 - Deploy comes up healthy through the gated pipeline (P1) 🎯 MVP

> **Ordering note**: US1, US2 and US3 are all P1. US2 runs first because it is the enabling story —
> there is no gateway to route through, retier, or observe until it is deployed. This is a dependency
> ordering within equal priority, not a re-prioritisation.

**Goal**: A repeatable, idempotent, healthy deploy through the gated LAB→PROD pipeline.

**Independent Test**: Run the pipeline against the pinned tag; containers reach `Up (healthy)`;
`/health/readiness` returns 200; a re-run changes nothing and the pin holds.

- [ ] T024 [US2] Deploy to LAB: `scripts/lab/pve-service-deploy apply --service llm-router --env lab`. Confirm the LXC is created and all three containers report `Up (healthy)`
- [ ] T025 [US2] Verify readiness on the LAB host: `curl -s http://<lab-ip>:4000/health/readiness` returns 200 with `{"status":"healthy","db":"connected"}` — this single probe covers both gateway liveness and database reachability (FR-009a, research D-103)
- [ ] T026 [US2] **Verify the tailnet path (FR-017; research D-102 — unproven assumption)**: from inside the litellm container, confirm the Mac's MagicDNS name resolves and answers through the outbound HTTP proxy. If httpx does not honour `HTTP_PROXY` on the `ollama_chat` provider path, switch to `ALL_PROXY` with the SOCKS5 listener and record the outcome in `specs/064-llm-router/research.md` under D-102
- [ ] T027 [US2] **Verify the free metric surface (research D-105)**: `curl -s -H "Authorization: Bearer $LITELLM_MASTER_KEY" http://<lab-ip>:4000/metrics | grep -E 'litellm_spend_metric|litellm_deployment_state'`. Empty output means the metrics are enterprise-gated — record the result in research.md D-105, because it decides whether Phase 6 needs the `LiteLLM_SpendLogs` fallback. Do this before any dashboard work
- [ ] T028 [US2] Re-run the apply and confirm idempotency: no unintended container recreation, `llm_router_version` unchanged (SC-004)
- [ ] T029 [US2] Run `scripts/healthcheck/llm-router.sh --profile lan` and confirm it passes and writes evidence
- [ ] T030 [US2] Promote through `lxc-promote-lab` then `lxc-promote-prod` with `service: llm-router`; confirm the gate is green with healthcheck evidence at each step (FR-011, SC-004)

**Checkpoint**: A healthy, idempotent, pinned gateway is running in PROD. US1, US3, US4, US5 can now proceed.

---

## Phase 4: User Story 1 - A client gets an answer regardless of the Mac's state (P1)

**Goal**: The Mac's availability is invisible to callers — health-check-driven routing plus ordered fallbacks.

**Independent Test**: The downed-backend drills (T034/T035) — remove the Mac two different ways,
confirm each alias is still served with no client error and no full timeout, then confirm automatic recovery.

- [ ] T031 [US1] Confirm Ollama on the Mac runs headless with models kept resident (`OLLAMA_HOST=0.0.0.0`, `OLLAMA_KEEP_ALIVE=-1`) and the `hermes-fast`/`hermes-balanced` models are pulled (FR-016). Document the exact invocation in `specs/064-llm-router/quickstart.md` § Prerequisites
- [ ] T032 [US1] Happy path: request each of `hermes-fast`, `hermes-balanced`, `hermes-deep` against `http://192.168.1.220:4000/v1/chat/completions` with a client key; each returns a completion (FR-002)
- [ ] T033 [US1] Verify attribution: confirm from metrics that `hermes-fast` was served by the **local** deployment id at zero marginal cost (SC-002 is about attribution, not merely getting an answer)
- [ ] T034 [US1] **Downed-backend drill A — server stopped (SC-008)**: stop Ollama on the Mac, then request **all three aliases**. Assert each returns a valid completion from the standby; no client-visible error; and latency shows the dead deployment was **skipped, not attempted and timed out** (AS-1.3). This is the drill that exercises the reported LiteLLM routing-pool defect against the exact pinned version — it must pass before promotion is considered final
- [ ] T035 [US1] **Downed-backend drill B — Mac powered off (SC-001)**: power the Mac off (or drop it from the tailnet) and repeat all three aliases. This is a **different failure mode** from T034 — a stopped daemon refuses fast, while a vanished tailnet peer can hang to timeout, which is the false-fallback risk D-102 raises. Assert no alias exceeds the request timeout and every alias still answers
- [ ] T036 [US1] Recovery drill: restart Ollama, wait one health-check interval (≤60 s), repeat the request. Assert it is served locally again with **no operator action** (AS-1.4)
- [ ] T037 [US1] All-deployments-in-cooldown drill: force every deployment behind one alias into cooldown and confirm the gateway **fails fast with a clear error** rather than hanging or retrying indefinitely (AS-1.5)
- [ ] T038 [US1] Context-escalation check: send an input longer than `hermes-fast`'s context window and confirm a larger tier answers rather than a 400 context-length error (FR-006, SC-009)
- [ ] T039 [US1] Cold-load tuning: confirm the first request after Mac idle does not trip the request timeout into a false fallback. Watch for unexpected metered volume on `hermes-fast` as the tell-tale; adjust the timeout or the keep-resident policy in `ansible/group_vars/services/vars.yml` if it does

**Checkpoint**: The Mac can be powered off and every alias still answers. This is the feature's core promise.

---

## Phase 5: User Story 3 - Retiering is a config edit, not a code change (P1)

**Goal**: Prove the FR-003 indirection holds before the Mac's 32 GB → 128 GB upgrade arrives.

**Independent Test**: Change one `deployments` entry, deploy, confirm the new deployment serves the alias and nothing else changed.

- [ ] T040 [US3] Retier drill: change one `deployments` entry for `hermes-balanced` in `ansible/group_vars/services/vars.yml` and redeploy. Confirm subsequent `hermes-balanced` requests are served by the new deployment (SC-003)
- [ ] T041 [US3] Assert **no client changed** — inspect every consumer and confirm each still addresses the same alias with no configuration or code edit (AS-3.2)
- [ ] T042 [US3] Assert **no role logic changed** — confirm the retier required no edit to `ansible/roles/llm_router/templates/config.yaml.j2` or any task file. If it did, [contracts/alias-mapping.md](./contracts/alias-mapping.md) has been violated and the template must be fixed rather than the drill relaxed (AS-3.3)
- [ ] T043 [US3] Revert the drill change and redeploy, confirming the original mapping restores cleanly

**Checkpoint**: The 128 GB upgrade is now a one-line edit, rehearsed rather than hoped for.

---

## Phase 6: User Story 4 - Routing and spend are observable (P2)

**Goal**: Per-alias volume, per-deployment health and metered spend visible in Grafana; a downed Mac
raises its own distinct non-critical signal; a fully broken gateway cannot sit silently green.

**Independent Test**: With traffic across all three aliases, Grafana shows volume and per-deployment
outcomes; stopping Ollama raises `LlmRouterLocalTierDown` as **info**; breaking every backend with no
traffic flowing raises `LlmRouterCanaryFailing` as **critical**.

- [X] T044 [US4] Extend `ansible/roles/monitoring_stack/templates/prometheus.yml.j2` so `monitoring_contract.scrape_targets` entries support an optional `authorization` block. Built as planned (optional, default-off, existing contracts render byte-identically). **Not exercised for llm-router** — live testing against the pinned image (below) found `require_auth_for_metrics_endpoint: true` hangs indefinitely on the master key; `/metrics` is left at LiteLLM's own open default instead (research D-105). The auth block remains available for a future service.
- [X] T045 [US4] Fill in `monitoring_contract.scrape_targets` in `ansible/host_vars/llm-router.yml` for `192.168.1.220:4000/metrics` with the bearer token sourced from vault (FR-009b)
- [X] T046 [US4] Add the routing alert rules to `ansible/host_vars/llm-router.yml`: `LlmRouterDown` (**critical**, from the `/health/readiness` liveness probe) and `LlmRouterLocalTierDown` (**info**, from `litellm_deployment_state` for the Ollama deployment). The severity split is deliberate — alerting critically on an intermittent-by-design backend trains the operator to ignore the channel (FR-009, [contracts/monitoring.md](./contracts/monitoring.md))
- [X] T047 [US4] Add `LlmRouterAllBackendsFailing` (**critical**) to `ansible/host_vars/llm-router.yml`, firing when the failure ratio across all deployments exceeds 90% over 10m. Note in a comment that this signal is silent without client traffic — T048 is the half that covers the idle case (FR-018)
- [X] T048 [US4] Implement the synthetic canary (FR-018): `canary.sh.j2` + `llm-router-canary.service/.timer` (60 min) run one real request against `hermes-fast`, writing a gauge to node_exporter's textfile collector. **Design addition beyond the original task**: node_exporter's textfile collector was not enabled anywhere in the fleet — added `node_exporter_textfile_directory` (default, task, systemd flag) as a small, generic, backward-compatible extension to the shared `node_exporter` role rather than building a bespoke ingestion path. The canary itself is modelled as an ordinary entry in `llm_router_clients` (alias `canary`, $1/mo cap) so it rides the same virtual-key provisioning and budget-headroom validation as every other client, rather than being a special case
- [X] T049 [US4] Create a Grafana dashboard at `ansible/roles/llm_router/files/llm-router-dashboard.json` and reference it via `monitoring_contract.dashboard_file`: per-alias request volume, per-deployment success/failure by deployment id, metered spend per alias, and a local-tier availability timeline
- [ ] T050 [US4] If T027 showed the metrics are enterprise-gated, implement the fallback: add a `postgres_exporter` service with custom queries over LiteLLM's `LiteLLM_SpendLogs` table to `ansible/roles/llm_router/templates/docker-compose.yml.j2`, and repoint the spend panels at it. SC-005 is not dropped under either outcome
- [ ] T051 [US4] Deploy monitoring and verify all FR-009 signals in Grafana. Then **break every backend with no client traffic flowing** and confirm an alert fires within one canary interval — the gateway must not sit silently green (SC-005, SC-013, AS-4.4)

**Checkpoint**: The gateway is observable, and neither a downed Mac nor a totally broken gateway can hide.

---

## Phase 7: User Story 5 - A runaway client cannot bill unbounded (P2)

**Goal**: Per-client keys with their own budgets, plus a gateway-wide backstop cap that alerts distinctly.

**Independent Test**: Drive one client past its cap — it is refused while others keep working; then
exhaust the gateway cap and confirm a distinguishable error and its own alert.

- [X] T052 [US5] Create `ansible/roles/llm_router/tasks/virtual_keys.yml` provisioning one LiteLLM virtual key per entry in `llm_router_clients`, idempotently, with `max_budget`, `budget_duration` and optional `rpm_limit`. Include it from `tasks/main.yml` after the stack is healthy (FR-015). *(Built during Phase 2, not Phase 7 — `tasks/main.yml` (T019) already includes it, and leaving the reference dangling would have left the role broken between phases.)*
- [X] T053 [US5] Configure the gateway-wide cap from `llm_router_gateway_budget`, with real headroom above the sum of per-client budgets (FR-010). **Redesigned from the original plan**: a standalone `/budget/new` object (tried first, live) has no corresponding Prometheus metric, so `LlmRouterBudgetCapExhausted` (T046) couldn't observe it. Rebuilt on LiteLLM's native **team** primitive instead — one team ("llm-router-gateway-wide") holds the cap, each client's key is generated on that team with its own budget as LiteLLM's documented "team member budget". This is what `litellm_remaining_team_budget_metric` reports, so the alert became implementable, and it's LiteLLM's own two-level primitive rather than a bespoke one. See `tasks/virtual_keys.yml`.
- [ ] T054 [US5] Per-client breach drill: drive one client past its own cap. Assert that client is refused with a clear error **and that every other client continues to be served** (SC-010, AS-5.1)
- [ ] T055 [US5] Attribution check: confirm the breach is visible in monitoring and attributed to the specific client key (AS-5.2)
- [ ] T056 [US5] Gateway-cap drill: exhaust the gateway-wide cap and confirm the error is **distinguishable** from a per-client breach — an operator must be able to tell "one agent looped" from "the homelab is out of budget" without opening the database ([contracts/gateway-api.md](./contracts/gateway-api.md))
- [ ] T057 [US5] Add the `LlmRouterBudgetCapExhausted` alert rule (**critical** — it refuses every client at once, so it is an availability event) to `ansible/host_vars/llm-router.yml` and verify it fires (SC-012)

**Checkpoint**: A looping agent costs one client's budget, not the homelab's.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [X] T058 [P] Blast-radius check (SC-006): `git grep -nE 'sk-|OPENROUTER_API_KEY=|ANTHROPIC_API_KEY='` over the repo excluding `specs/` and `docs/` returns no hits; confirm the rendered `/opt/llm-router/config.yaml` on the LXC contains only `os.environ/...` indirection; confirm **no Anthropic subscription or OAuth credential** exists anywhere (FR-007)
- [X] T059 [P] Exposure check (SC-007, FR-008): confirm no Caddy route, no public DNS name and no landing-page entry exist, and that `192.168.1.220:4000` is unreachable from outside the LAN and tailnet. **LAN reachability is expected and accepted** — see research D-108; do not treat a successful LAN request as a failure
- [X] T060 [P] Confirm request logging is bounded and on local disk only, with prompt/response bodies not logged by default, in `ansible/roles/llm_router/templates/docker-compose.yml.j2` (FR-012)
- [X] T061 [P] Verify all image pins are recorded in `ansible/group_vars/services/vars.yml` alongside the other `*_version` pins, and that none is `latest` (FR-001)
- [ ] T062 [P] **Verify SC-011** after one week of operation: confirm background-health-check traffic accounts for under 1% of the period's metered spend. Query `LiteLLM_SpendLogs` (or the spend metric) filtered to health-check calls; expect ~zero, since D-101 scopes background checks to the local tier only. If it is not ~zero, the model-group scoping in `config.yaml.j2` has regressed
- [ ] T063 Run the full [quickstart.md](./quickstart.md) end to end against PROD as the acceptance pass
- [X] T064 [P] Update `docs/backlog/064-llm-router.md` to mark the item delivered, and record the resolutions of D-001/D-003/D-004 plus the Phase 0 and post-analyze corrections (D-102, D-103, D-104, D-108) so the backlog does not keep presenting them as open
- [X] T065 [P] **File a separate backlog item** for the pre-existing gap found in research D-107: `market-model` and `eurooffice` are missing from `ansible/inventories/prod/hosts.yml`, which means their monitoring contracts likely contribute nothing in prod. Out of scope for this feature — but it should not stay undocumented

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

`T003 → T011/T012 → T016–T019 → T024 → T026 (tailnet path) → T034/T035 (downed-backend drills)`

T026, T034 and T035 are the tasks most likely to force a design change: T026 tests an unproven
assumption about proxy handling, and T034/T035 test the pinned LiteLLM version against a known
routing-pool defect under two different failure modes. Schedule all three early rather than at the end.

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
- Commit after each task or logical group; the PR needs the `allow-protected-path-changes` label because of T004.
- Every drill (T034, T035, T037, T040, T051, T054, T056) is an acceptance criterion, not an optional extra — the spec is explicit that SC-008 is "exercised as part of acceptance, not assumed".
