---
description: "Task list for 065-hermes-ai-workspace implementation"
---

# Tasks: Hermes — a self-hosted AI workspace on local models

**Input**: Design documents from `/specs/065-hermes-ai-workspace/`
**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/)

**Tests**: No unit-test suite is generated. The spec does not request one and this feature ships no
application code (FR-026). Per Constitution § *Test-Driven Changes*, validation is **non-destructive
checks** (`pve-service-deploy plan`, Ansible preflight assertions, `act -l`) plus the drills in
[quickstart.md](./quickstart.md) — which appear below as first-class tasks, not as an afterthought.

**Organization**: Grouped by user story so each can be implemented, tested and delivered
independently.

**Progress (2026-09-21)**: **deployed and serving.** The LXC exists at `192.168.1.221`, both
containers are up, and `https://hermes.hus-sky.no` answers behind a valid certificate with every
surface gated. SC-002 is verified behaviourally — chat, model list, knowledge, files, users and
the programmatic endpoint all return 401 unauthenticated, and a real registration attempt was
refused with 403 (no account created).

**Monitoring deployed 2026-09-21 through the prod path.** Verified against a before/after
baseline: 28 -> 31 active targets, 8 -> 9 rule groups, 0 unhealthy, and **every pre-existing job
and alert group intact** — the `072` failure mode did not recur. The LAB half of the promote
chain failed exactly as designed (`Refusing to deploy monitoring: the layered inventory exposes
1 host(s)`), which is the guard working, and `allow_override_failed_lab_gate=true` carried the
chain to the prod apply. `hermes_alerts` holds HermesDown (critical) and HermesBackupStale
(warning); `probe_success{job="hermes"}` is 1 and the landing-page card's `data-probe` matches
its instance label, so the indicator tracks rather than reading "unknown".

**Still outstanding**: Retrieval (US6) is blocked on the oMLX
embedding/reranker work on the inference host. The phone drills (SC-001, FR-005, SC-012), the
long-generation drill (SC-009), the fail-fast drills (Phase 7), the restore drill (SC-006) and
the measurement tasks (T078/T082) all need a human. See
[quickstart.md § Status](./quickstart.md).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel — different files, no dependency on incomplete work
- **[Story]**: US1–US6, mapping to the user stories in [spec.md](./spec.md)

## Path Conventions

This is an infrastructure feature; there is no application source tree. Paths are the estate's real
ones: `terraform/`, `ansible/`, `.github/workflows/`, `scripts/lab/`.

---

## Phase 1: Setup — service registration and scaffolding

**Purpose**: Bring the service into existence in every place the estate expects it.

> **Constitution V (Dual-Provisioning Parity) is a hard gate here.** A new service must be
> registered in **eight** places *in the same PR*. Partial registration means CI and laptop paths
> diverge — that is a parity violation, not a follow-up. T001–T008 are those eight.
>
> **Correction, 2026-09-21 — it is ten, not eight.** The first real deploy failed twice on
> registration points the list does not mention, both of which fail *after* a green Terraform
> apply rather than at validation time:
>
> 9. **`ansible/inventories/prod/hosts.yml`** — without it the service is invisible to
>    `playbooks/monitoring.yml`, so its `monitoring_contract` never renders: no probe, no alerts,
>    and a front-page card with nothing behind it. This is exactly backlog `066`, which records
>    `market-model` and `eurooffice` as already missing.
> 10. **`scripts/healthcheck/<service>.sh`** — `pve-service-deploy` hard-fails the apply with
>     `missing healthcheck script for service=<name>` *after* Ansible has completed successfully.
>     The file is an 11th copy of a template differing by one word.
>
> Neither is caught by `act -l`, by preflight, or by a plan. Worth folding into the constitution's
> own list rather than rediscovering per service.

- [X] T001 [P] Add `hermes = "192.168.1.221/24"` to the service address map in `terraform/environments/prod.tfvars.template`
- [X] T002 [P] Add the same entry to `terraform/environments/lab.tfvars.template`
- [X] T003 Create the per-service Terraform root at `terraform/services/hermes/` (`main.tf`, `variables.tf`, `outputs.tf`, `providers.tf`), mirroring `terraform/services/llm-router/`
- [X] T004 [P] Add `hermes` to the service dropdown in `.github/workflows/lxc-deploy-lab.yml`
- [X] T005 [P] Add `hermes` to the service dropdown in `.github/workflows/lxc-promote-lab.yml`
- [X] T006 [P] Add `hermes` to the service dropdown in `.github/workflows/lxc-promote-prod.yml`
- [X] T007 [P] Add the `hermes` scope prefixes to `scripts/lab/service-scope-allowlist.json`
- [X] T008 [P] Create the service playbook at `ansible/playbooks/hermes.yml`, following `ansible/playbooks/llm-router.yml`
- [X] T009 Verify all eight registration points are present and consistent — grep for `hermes` across the paths in T001–T008 and confirm none is missing
- [X] T010 Run `act -l` to confirm the edited workflows still parse (Constitution § *Local Workflow Testing*); if `act` or Docker is unavailable, record why in the PR
- [X] T086 Verify Constitution V parity from a laptop, not only from CI: run `scripts/lab/pve-service-deploy plan --environment lab --service hermes` locally with the same arguments CI uses, and confirm the vault variables from T012 resolve from a local `ansible/group_vars/services/vault.yml` rather than only from the PVE vault store. Parity is currently *inherited* from the orchestrator rather than proven for this service — if either half fails, document the limitation and the local equivalent

---

## Phase 2: Foundational — the machine and the stack

**Purpose**: A running, reachable service that every user story builds on.

**⚠️ CRITICAL**: No user story work can begin until this phase completes.

- [X] T011 Define `hermes_*` settings in `ansible/group_vars/services/vars.yml` per [data-model.md](./data-model.md) § *Service configuration* — pinned non-`latest` image tags for both containers, `hermes_data_dir` on local disk, gateway base URL, capability aliases
- [X] T012 Add the vault variables (gateway client key, admin bootstrap credential) to `ansible/group_vars/services/vault.yml` via `ansible-vault edit`. **Never commit a value** (Constitution II)
- [X] T013 Create `ansible/roles/hermes/defaults/main.yml` with the role's own defaults
- [X] T014 Create `ansible/roles/hermes/tasks/preflight.yml` implementing every validation in [data-model.md](./data-model.md) — image tags pinned, `hermes_data_dir` not on NFS, aliases exist and are within the client key's scope, credentials resolve, `ENABLE_SIGNUP` false, **and both `RAG_OPENAI_*` variables explicitly set** (see T015)
- [X] T015 [P] In `ansible/roles/hermes/tasks/preflight.yml`, assert `RAG_OPENAI_API_BASE_URL` and `RAG_OPENAI_API_KEY` are set explicitly. They do **not** reliably inherit from `OPENAI_API_*` (upstream open-webui#22084); unset, retrieval silently reaches `api.openai.com` — broken *and* an FR-008 breach. This assertion is the only thing standing between the two
- [X] T016 Create `ansible/roles/hermes/templates/docker-compose.yml.j2` with the application and the SearXNG sidecar (research R-005), SearXNG **not published** to the LAN
- [X] T017 Create `ansible/roles/hermes/tasks/main.yml` — preflight, directories, render compose, bring the stack up, wait for readiness
- [X] T018 Deploy through the pipeline (plan, then apply) and confirm the stack is up and answering on the LXC's published port

**Checkpoint**: The service runs and is reachable on the LAN. User stories can now proceed.

---

## Phase 3: User Story 1 — The owner talks to a local model from wherever they are (P1) 🎯 MVP

**Goal**: A private assistant, authenticated, reachable from a phone anywhere.

**Independent Test**: Sign in from a phone on mobile data, send a prompt, get an answer from a local
model, add the site to the home screen.

- [X] T019 [US1] Configure the gateway backend in `ansible/roles/hermes/templates/docker-compose.yml.j2` — `OPENAI_API_BASE_URL` at the `064` gateway, `OPENAI_API_KEY` from the vault (FR-007)
- [X] T020 [US1] Set `ENABLE_SIGNUP=False` and the admin bootstrap in `ansible/roles/hermes/templates/docker-compose.yml.j2` so exactly one account exists (FR-003, FR-004)
- [X] T021 [US1] Add the `caddy_services` entry for `hermes` in `ansible/group_vars/services/vars.yml` with **`user_facing: false`** — this creates the public route without the landing-page card, which User Story 2 adds separately
- [X] T022 [US1] Set `proxy_timeout` on that `ansible/group_vars/services/vars.yml` entry long enough to clear FR-021's twenty-minute ceiling. The default truncates a long generation and the symptom looks like a model fault, not a proxy one
- [X] T023 [US1] Point `TASK_MODEL_EXTERNAL` at the cheapest capability alias and set `ENABLE_TITLE_GENERATION` deliberately, in `ansible/roles/hermes/templates/docker-compose.yml.j2` (FR-011, research R-004)
- [X] T024 [US1] Redeploy and confirm the public hostname resolves, serves a valid certificate, and presents a login before any other surface
- [X] T025 [US1] **Drill (SC-002)**: request every surface unauthenticated — chat, model list, documents — and confirm each is refused. Attempt to register and confirm it is refused
- [ ] T026 [US1] **Drill (SC-001)**: from a phone on mobile data, sign in and receive an answer; record the elapsed time against the 60-second criterion
- [ ] T027 [US1] **Drill (FR-005)**: add the site to a phone home screen and confirm it launches standalone; check every primary action is reachable at phone width without horizontal scrolling
- [ ] T028 [US1] **Drill (SC-009)**: send a prompt whose response takes ~15 minutes and confirm it is delivered complete

**Checkpoint**: MVP. A private, authenticated assistant on local models, usable from a phone.

---

## Phase 4: User Story 2 — It appears on the front page and tells the truth there (P1)

**Goal**: Discoverable from the estate's landing page, with an indicator that is not a lie.

**Independent Test**: Load the front page, see the card and its state, stop Hermes, reload and see
the state change, restart, click through.

- [X] T029 [US2] Flip the `caddy_services` entry to `user_facing: true` in `ansible/group_vars/services/vars.yml` so the landing-page card appears alongside the route from T021
- [X] T030 [US2] Create `ansible/host_vars/hermes.yml` with the `monitoring_contract` from [contracts/monitoring.md](./contracts/monitoring.md) — a blackbox liveness probe on the public hostname
- [X] T087 [US2] Determine whether the application exposes a metrics endpoint, and if it does add it as a scrape target in `ansible/host_vars/hermes.yml`. FR-018 asks for one "if the application exposes one" — nobody has checked, so the clause is currently neither satisfied nor consciously waived. Record the answer either way
- [X] T031 [US2] Add the `LlmRouter`-style unreachable alert (**critical**) to `ansible/host_vars/hermes.yml`
- [X] T032 [US2] Deploy the monitoring change **through the prod path only**. A lab-path monitoring deploy renders an empty configuration over the live one — this removed 16 scrape jobs and 5 alert groups from production on 2026-09-20 (backlog `072`). Two guards now refuse it; do not test them by accident
- [X] T033 [US2] Confirm the card renders on `hus-sky.no`, its indicator tracks the real probe, and clicking it opens Hermes itself
- [X] T034 [US2] **Drill**: stop the service, reload the front page, confirm the card reports it down rather than showing a stale success; restart and confirm recovery
  - **Run 2026-09-21, measured.** Stopped `hermes_open_webui` at 07:06:07Z. The card's probe
    (`blackbox-https`, instance `https://hermes.hus-sky.no`) went to 0 in **10s**; the contract's
    own probe (`job="hermes"`) followed at **30s**. `/api/status` on the apex returned 0 for both
    — **down, not a stale success**, which is the thing this drill exists to catch.
  - Restarted: card probe back to 1 within **20s**, container `Up (healthy)`, public URL 200.
  - `HermesDown` went `pending` and returned to `inactive` **without firing** — the `for: 5m`
    damping correctly absorbed a 30-second blip, so the card tells the truth in seconds while the
    pager stays quiet. That split is the design working, not a gap.

**Checkpoint**: Hermes is discoverable and its state on the front page is honest.

---

## Phase 5: User Story 3 — Hermes uses the homelab's own tools (P1)

**Goal**: Answers grounded in the estate's own data, not guesses.

**Independent Test**: Ask a question only answerable through a homelab tool service and confirm the
tool was called and used.

> **Scope, decided 2026-09-20**: `market-model` only. `financial-scenario` gates on a secret baked
> into a third-party image this repo does not hold (research R-008). The credentialed branch is
> still built — that is what makes adding the second server a list entry later.

- [X] T035 [US3] Add `hermes_mcp_servers` to `ansible/group_vars/services/vars.yml` per [data-model.md](./data-model.md), populated with `market-model` (`auth: none`)
- [X] T036 [US3] Implement the `auth: bearer` branch and its `credential_env` validation in `ansible/roles/hermes/tasks/preflight.yml`, **even though nothing populates it yet** — the schema is what makes FR-013 true, and validating an unused branch is deliberate, not dead configuration
- [X] T037 [US3] Render the MCP server registrations into the stack configuration in `ansible/roles/hermes/templates/docker-compose.yml.j2`
- [ ] T038 [US3] **Drill (SC-003)**: ask a question answerable only through `market-model`; confirm the tool was called and the answer derives from what it returned
- [ ] T039 [US3] **Drill (US-3 AS-3)**: make the tool service unreachable and confirm the conversation shows a readable error naming it — never an indefinite wait, never a fabricated answer presented as tool output
- [ ] T040 [US3] **Drill (SC-004)**: change a capability alias in `group_vars`, redeploy, and confirm via `git diff --stat` that only configuration changed — no template, no code. The diff is the assertion
- [ ] T088 [US3] **Drill (SC-004, second half)**: add a tool-service entry to `hermes_mcp_servers` in `ansible/group_vars/services/vars.yml` — a disabled placeholder is sufficient — redeploy, and confirm via `git diff --stat` that only configuration changed. T040 proves the *capability alias* half; this proves the *tool service* half, which is the one FR-013 is actually about
- [ ] T090 [US3] **Drill (edge case)**: exercise a tool call returning far more data than fits in a conversation, and one returning malformed output. Confirm both surface readably and neither is presented to the owner as a successful result (FR-014)

**Checkpoint**: Hermes answers from the estate's own data.

---

## Phase 6: User Story 4 — The owner can get into the box, and nothing is lost on a rebuild (P1)

**Goal**: Administrable, and survivable.

**Independent Test**: SSH in by key; destroy the LXC; rebuild from code; restore; confirm state.

- [X] T041 [US4] Ensure `terraform/services/hermes/` injects `ssh_public_keys` into the LXC (FR-006, Constitution § *Access Control*)
- [ ] T042 [US4] Confirm SSH works by key from the LAN, that password authentication is refused, and that no public route to SSH exists
  - **Two of three verified 2026-09-21.** Key-based SSH works (`BatchMode=yes`, so no password
    fallback was possible). No public SSH route: `caddy_services` has no port-22 entry.
  - **The third does not hold, and it is estate-wide, not ours.** `sshd -T` on hermes reports
    `passwordauthentication yes`. So do `llm-router` (`.220`) and `financial-scenario` (`.217`) —
    identical. In practice nothing can log in by password, because `permitrootlogin
    without-password` and root is the only account; but the literal claim "password
    authentication is refused" is false at the sshd level on every service LXC.
  - Left unchecked deliberately rather than quietly redefined. Hardening `sshd` fleet-wide is a
    change to every other service's access posture and belongs in its own feature — the same
    argument plan.md makes for `forward_auth`.
- [X] T043 [P] [US4] Create `ansible/roles/hermes_backup/tasks/main.yml`, following `ansible/roles/financial_scenario_backup/`
- [X] T044 [P] [US4] Create `ansible/roles/hermes_backup/templates/backup_hermes.sh.j2` covering everything under `hermes_data_dir` — SQLite, uploaded documents and the vector index ([data-model.md](./data-model.md) § *Workspace state*)
- [X] T045 [US4] Add the backup schedule and retention settings to `ansible/group_vars/services/vars.yml`, and wire the role into `ansible/playbooks/hermes.yml`
- [X] T046 [US4] Add the backup-age alert (**warning**) to `ansible/host_vars/hermes.yml` per [contracts/monitoring.md](./contracts/monitoring.md)
- [ ] T047 [US4] Confirm a backup artifact reaches the Synology and its age is visible to monitoring
- [ ] T048 [US4] **Drill (SC-006)**: accumulate state, destroy the LXC, rebuild from code, run the restore, and confirm conversations, accounts, settings and knowledge all return. **A backup that has never been restored is a belief, not a backup**

**Checkpoint**: Hermes is administrable and survives a rebuild.

---

## Phase 7: User Story 5 — Hermes degrades honestly when models are unavailable (P2)

**Goal**: The normal case — the inference host asleep — behaves like a feature, not a fault.

**Independent Test**: Make the inference host unavailable, use Hermes, time the failure.

- [ ] T049 [US5] Confirm request timeouts in the stack configuration surface a backend failure in seconds rather than waiting on the twenty-minute ceiling meant for *successful* long generations (FR-009 vs FR-021 — these pull in opposite directions and the split must be deliberate)
  - **FAILS, 2026-09-21.** The split was never actually made: there is one knob. LiteLLM's
    per-deployment `timeout` is a *total request* timeout, so the 1200s needed for FR-021
    governs connect too. Backlog `075`.
- [ ] T050 [US5] **Drill (SC-005)**: log the inference host out; send a prompt; time the error against the 10-second criterion; confirm it names the unavailable backend
  - **FAILS, measured 2026-09-21.** Baseline 0.91s. Host away: first request **no response at
    90.01s**, second **no response at 30.00s**. Later requests are correct and fast — 429 in
    0.03s naming `cooldown_list=['fast-local']` — but the cooldown cannot engage until the
    first failure completes, and on this Mac the SYN is dropped rather than refused, so it
    never does. Raised as backlog `075` per T054. **Left unchecked deliberately: a hang is the
    one outcome that fails this story.**
- [X] T051 [US5] **Drill (US-5 AS-2)**: with the host still away, confirm the interface loads and previous conversations remain readable
- [X] T052 [US5] **Drill (US-5 AS-3)**: bring the host back and confirm the next prompt is served with no administrative action
- [ ] T089 [US5] **Drill (edge case)**: start a long generation, then make the inference host unavailable *mid-stream*, and confirm the conversation surfaces a readable error rather than spinning or leaving a half-delivered response that looks complete. T050–T052 cover a host that is already away; this covers one that leaves during the request, which is a different failure and the more likely one in practice
  - **FAILS, measured 2026-09-21 — and worse than T050.** Host pulled away 9s into a
    streaming answer. The stream ended **0.1s later, cleanly**: `finish_reason: "stop"`,
    `data: [DONE]`, curl exit 0, **zero error chunks**. Delivered **322 words of ~1200 (27%)**,
    cut mid-sentence at "…attributed to the 13th century. While".
  - This is the exact outcome the task was written to catch — "a half-delivered response that
    looks complete" — and it is the one failure US-5's title rules out. Open WebUI receives a
    well-formed successful stream, so it has nothing to detect: the truncated answer is
    rendered and **persisted to the conversation store** as a normal turn.
  - Raised as backlog `076`. Left unchecked deliberately. Note it wants the OPPOSITE of
    `075`'s fix: `075` is about how long the stream takes to end, this is about what the
    stream *says* when it ends.
- [X] T053 [US5] Record the measured failure times in [quickstart.md](./quickstart.md) — replacing the claims it currently makes with observations
- [X] T054 [US5] Record the Phase 7 results in `specs/065-hermes-ai-workspace/quickstart.md` § 3, and raise any drill that **hung rather than errored** as a defect before closing the phase. `064` has no fallback tier, so failure is unavoidable — the only question is whether it is legible and fast, and a hang is the one outcome that fails the story

**Checkpoint**: Absence of the inference host is handled honestly.

---

## Phase 8: User Story 6 — The owner asks questions of their own documents (P3)

**Goal**: Document Q&A with citations, entirely on the owner's hardware.

**Independent Test**: Upload a document, ask something answerable only from it, confirm the citation.

> **This phase depends on work outside the new machine.** T055–T058 are prerequisites and are not
> deployments of this LXC.

- [ ] T055 [US6] On the inference host, load an embedding model into oMLX and expose it in the Mac's `~/Development/private/local-llm/proxy/litellm-config.yaml` (research R-002)
- [ ] T056 [US6] On the inference host, load a reranker model and expose it the same way in `~/Development/private/local-llm/proxy/litellm-config.yaml`
- [X] T057 [US6] Amend `064`: add the embedding and reranking capability aliases to `ansible/group_vars/services/vars.yml`, extend the Hermes client key's permitted `models` scope to include them, and update `064`'s preflight and doctor ([contracts/gateway-usage.md](./contracts/gateway-usage.md))
- [X] T058 [US6] Record the amendment in `specs/064-llm-router/` — it is a change to a closed feature and belongs in its records, not only in this one (Constitution I)
- [X] T059 [US6] Configure retrieval in `ansible/roles/hermes/templates/docker-compose.yml.j2` — `RAG_EMBEDDING_ENGINE=openai`, `RAG_EMBEDDING_MODEL`, and **both** `RAG_OPENAI_API_BASE_URL` and `RAG_OPENAI_API_KEY` explicitly (T015 asserts this)
- [X] T060 [US6] Configure the external reranker in `ansible/roles/hermes/templates/docker-compose.yml.j2` — `RAG_RERANKING_ENGINE=external`, `RAG_RERANKING_MODEL`, `RAG_EXTERNAL_RERANKER_URL`, `RAG_EXTERNAL_RERANKER_API_KEY`
- [ ] T061 [US6] **Drill (SC-007)**: upload a document, ask a question answerable only from it, confirm the answer identifies the source passage
- [ ] T062 [US6] **Drill (FR-008/FR-016)**: confirm no document content leaves the estate at any stage — in particular that retrieval never reaches `api.openai.com`
- [ ] T063 [US6] **Drill (US-6 AS-3)**: with the inference host away, ask a document question and confirm it fails readably rather than quietly answering without the document
- [ ] T064 [US6] Measure the cost of indexing a representative document set against the gateway request allowance; bulk indexing is not an interactive operation and must not be treated as one
- [ ] T065 [US6] Record in [quickstart.md](./quickstart.md) that retrieval is unavailable while the inference host sleeps — the accepted cost of research R-002's decision

**Checkpoint**: Document Q&A works, entirely locally, and fails honestly.

---

## Phase 9: Additional capabilities

**Purpose**: FR-022 to FR-025. These carry success criteria but no dedicated user story, and each is
independently deliverable after the MVP.

### Web search (FR-022, SC-013)

- [X] T066 [P] Configure `SEARXNG_QUERY_URL` against the sidecar in `ansible/roles/hermes/templates/docker-compose.yml.j2`
- [X] T067 [P] Configure the SearXNG instance itself in `ansible/roles/hermes/templates/searxng-settings.yml.j2` — enabled engines, JSON output format, no external API keys
- [ ] T068 **Drill (SC-013)**: ask something requiring current information; confirm citations to sources fetched at the time of asking, and that no query reached a commercial search provider

### Voice (FR-023, SC-012)

- [X] T069 [P] Configure local speech-to-text in `ansible/roles/hermes/templates/docker-compose.yml.j2` so audio never leaves the estate
- [X] T070 [P] Configure text-to-speech in `ansible/roles/hermes/templates/docker-compose.yml.j2`
- [ ] T071 **Drill (SC-012)**: on a phone, speak a question and hear the answer; confirm no audio left the estate

### Programmatic interface (FR-024, SC-014)

- [X] T072 Enable the application's own OpenAI-compatible endpoint in `ansible/roles/hermes/templates/docker-compose.yml.j2` and confirm it is subject to the same authentication as every other surface (FR-002, FR-004)
- [ ] T073 **Drill (SC-014)**: call it from another homelab service and confirm the answer reflects the configured tools and knowledge — demonstrably more than the bare gateway would return for the same prompt
- [X] T074 Confirm this endpoint was covered by T025's unauthenticated sweep; if it was added afterwards, re-run that drill against it

### Scheduled prompts (FR-025, SC-010, SC-015)

- [X] T075 [P] Enable automations in `ansible/roles/hermes/templates/docker-compose.yml.j2` via `ENABLE_AUTOMATIONS`, and set `AUTOMATION_MIN_INTERVAL` so a misconfigured schedule cannot exhaust the gateway allowance
- [ ] T076 **Drill (SC-015)**: schedule a prompt that **requires a tool call**, let it run unattended, and confirm both that its output is waiting afterwards and that the tool was actually used. FR-025 requires scheduled runs to have "the same tools and knowledge available as in an interactive conversation" — a prompt that needs no tool would pass without testing that clause
- [ ] T077 **Drill (SC-010)**: let a scheduled run fire while the inference host is away; confirm it is visibly recorded as failed and that "ran and failed" is distinguishable from "never ran"

---

## Phase 10: Polish & Cross-Cutting Concerns

- [ ] T078 **Drill (SC-008)**: define what "one hour of representative use" means *before* running it — number of conversations, whether documents are indexed — then measure the request rate from gateway metrics and record both the definition and the result
- [ ] T079 Review the Hermes client key's `rpm_limit` in `ansible/group_vars/services/vars.yml` (`llm_router_clients`) against T078's measurement. **Measure before raising** — raising first hides the problem rather than solving it (FR-011)
- [X] T080 **Drill (SC-011)**: inspect the full diff and confirm it contains no bespoke application source code (FR-026)
- [ ] T081 Rewrite [quickstart.md](./quickstart.md) against what actually happened. It was written before implementation and every command in it is a claim; a step that needed changing is information worth keeping
- [ ] T082 Record the LXC's measured resource use and right-size `terraform/services/hermes/` against it rather than against the initial guess (research R-007)
- [X] T083 Update `docs/architecture/` and the landing-page documentation to include Hermes
- [X] T084 Raise a backlog item in `docs/backlog/` (and index it in `docs/backlog/backlog.md`) for consolidating the five near-identical backup roles into one parameterised role — with five consumers it now passes Constitution IV's own ">1 concrete consumer" test, and it was deferred from this feature only because it means rewriting four other services' working code
- [X] T085 Confirm the principal risk is still recorded accurately: Hermes is internet-facing with only its own login in front of the gateway and the homelab's tools. If an estate-wide `forward_auth` layer has become viable, raise it as its own feature

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 1 (Setup)** → no dependencies. T001–T008 are largely parallel; T009 gates on all of them
- **Phase 2 (Foundational)** → depends on Phase 1. **Blocks every user story**
- **Phase 3 (US1)** → depends on Phase 2. **This is the MVP**
- **Phase 4 (US2)** → depends on US1's T021 (the `caddy_services` entry it flips)
- **Phase 5 (US3)** → depends on Phase 2 only. Independent of US1/US2
- **Phase 6 (US4)** → T041–T042 depend on Phase 1; the backup work depends on Phase 2
- **Phase 7 (US5)** → depends on US1 (something must exist to fail)
- **Phase 8 (US6)** → depends on Phase 2 **and** on external work (T055–T058)
- **Phase 9** → each group depends only on Phase 2; the four are independent of each other
- **Phase 10** → depends on everything it measures

### User story independence

US3, US4 and US6 touch different files from US1 and can proceed alongside it once Phase 2 lands.
US2 and US5 are the two with a real ordering constraint: US2 flips a value US1 introduces, and US5
needs a working path in order to break it.

### Parallel opportunities

- **Phase 1**: T001, T002, T004, T005, T006, T007, T008 — seven files, no interdependencies
- **Phase 6**: T043 and T044 — different files in a new role
- **Phase 9**: the four capability groups are independent; within them T066/T067, T069/T070 and T075 are parallel
- **Across phases**: once Phase 2 is done, US3 and US4 can run alongside US1

## Parallel Example: Phase 1

```text
T001  prod.tfvars.template          ┐
T002  lab.tfvars.template           │
T004  lxc-deploy-lab.yml            │  all seven in parallel —
T005  lxc-promote-lab.yml           │  different files, no shared state
T006  lxc-promote-prod.yml          │
T007  service-scope-allowlist.json  │
T008  playbooks/hermes.yml          ┘
          ↓
T009  verify all eight registration points  (gates on the above)
T010  act -l
```

## Implementation Strategy

### MVP first

**Phases 1 → 2 → 3.** That delivers a private, authenticated AI workspace on local models, usable
from a phone. Everything after it is additive. Stop and use it before building more — it will tell
you which of the Phase 9 capabilities you actually want.

### Incremental delivery

1. **MVP** — Phases 1–3
2. **Discoverable and observable** — Phase 4
3. **Grounded in the estate's data** — Phase 5
4. **Survivable** — Phase 6
5. **Honest under failure** — Phase 7 *(cheap, and it validates a design claim rather than adding surface)*
6. **Documents** — Phase 8, once the inference host has the models
7. **Capabilities** — Phase 9, à la carte
8. **Polish** — Phase 10

### Sequencing note

Phase 7 is P2 but costs almost nothing and tests the design's central claim — that absence of the
inference host is a feature rather than a fault. Consider running it immediately after the MVP
rather than in priority order. If it fails there, later phases are building on a false premise.

## Notes

- **No unit tests by design.** No application code ships (FR-026). Validation is preflight
  assertions plus the drills, which are tasks here rather than an afterthought.
- **The drills are the acceptance criteria**, not optional extras. Every `**Drill**` task names the
  success criterion it proves.
- **Constitution V is a hard gate.** All eight registration points in the same PR.
- **Monitoring deploys go through the prod path only** (T032, backlog `072`).
- **36 tasks name no file path, and that is deliberate.** The checklist format asks for a path on
  every task. These are 24 **drills** plus 12 deploy/verify actions — they act on a running
  system, not on a file, so each names the success criterion it proves or the thing it checks
  instead. Every task that *edits* something names the file it edits.
- **IDs T086–T090 were added after `/speckit.analyze` and sit out of numeric order.** They are
  placed in the phase where they execute, so **phase position gives execution order, not the
  number**. Renumbering would have churned 85 tasks and broken the cross-references in these
  notes and in the dependency section — a worse trade than a numbering gap. What they close:
  T086 the only constitution finding (Constitution V laptop parity, which was inherited rather
  than proven), T087 FR-018's unexamined scrape-target clause, T088 the half of SC-004 that
  T040 does not reach, T089 and T090 the two edge cases with no coverage.
- **`git diff --stat` is a real assertion** in T040 and T080 — SC-003 and SC-011 are claims about
  *where* a change lands, not just about behaviour.
