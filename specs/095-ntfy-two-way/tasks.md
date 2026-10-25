---

description: "Task list for 095 two-way ntfy"
---

# Tasks: Two-way ntfy — talk to Hermes and act on notifications from the phone

**Input**: Design documents from `/specs/095-ntfy-two-way/`

**Prerequisites**: plan.md, spec.md (incl. Clarifications 2026-10-25), research.md, data-model.md,
contracts/, quickstart.md

**Tests**: Included. The plan (§ Testing) and the constitution (Test-Driven Changes) require
pytest tests for the relay and hooks, and guard tests for rendered config. Write each test task
before its implementation task and see it fail first.

**Organization**: Grouped by user story. Slice 1 = US1–US3 (P1). Slice 2 = US4–US6 (P2).
Slice 3 = US7 (P3).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1…US7 from spec.md
- Manual/on-device tasks say **(manual)**; they produce evidence, not code

## Deviations from plan.md (decided while generating tasks)

- **Relay module path**: `python/src/homelab_proxmox_orchestrator/ntfy_action_relay.py` (one
  module), not `python/src/ntfy_action_relay/`. Reason: `setup.cfg` mutmut `source_paths` is
  `src/homelab_proxmox_orchestrator` only, and coverage is per-module in `python/pytest.ini`;
  the plan's goal "inherits the coverage and mutation gates" needs this location.
- **Hook code as static files**: `ansible/roles/hermes/files/hooks/<name>/{HOOK.yaml,handler.py}`
  (copied, not Jinja-templated), so the handlers are importable by pytest. Configuration comes
  from the agent's environment at runtime.
- **Spec clarifications after the plan**: FR-004 (session approval is pattern-scoped, scope
  stated, one pending prompt, permanent approvals alerted), FR-006 (always report on restart;
  drops > 10 min), FR-008 (relay heartbeat). T001 reconciles the design docs. Research R-014
  (upstream source check) settles most of the LAB gate in advance.

---

## Phase 1: Setup (design-doc reconciliation)

**Purpose**: Bring the plan artifacts in line with the 2026-10-25 clarifications before code.

- [x] T001 Reconcile design docs with spec Clarifications 2026-10-25 and research R-014: in `specs/095-ntfy-two-way/data-model.md` § Approval prompt replace "`session` and `always` choices are not in the slash allowlist's intent … use `/approve` only" with: `/approve` = once; `/approve session` = the approved pattern for the rest of the conversation, ended by `/new`/`/reset` (FR-004); `/approve always` = permanent until agent restart, cannot be disabled upstream, raises `HermesPermanentApprovalGranted` (FR-004, R-014); bare words (`yes`, `ok`, `session`, `always`, 👍/👎) map to the same choices only while a prompt is pending; at most one prompt pending. In `contracts/inbound-chat.md` add rows for `/approve session`, `/approve always`, bare-word replies, and "second flagged command while a prompt is pending → withheld until resolved". In `research.md` R-011 add "Relay exposes `/metrics` with `ntfy_action_relay_heartbeat_timestamp_seconds`; Prometheus scrapes it; `NtfyActionRelayDown` alerts via the normal route (FR-008)". In `plan.md` § Project Structure change the relay path to `python/src/homelab_proxmox_orchestrator/ntfy_action_relay.py` and hooks to `ansible/roles/hermes/files/hooks/`. In `data-model.md` add a note: server `message-size-limit` stays `32k` (spec Edge Case "Oversized inbound message"). (Done 2026-10-25 during analysis remediation.)
- [x] T002 [P] Extend `specs/095-ntfy-two-way/quickstart.md` § 0 (LAB gate) with steps that confirm research R-014: (4) the text prompt lists once, session (pattern), always (permanent), deny and the deadline; (5) `/approve session` on a scratch `rm`, a second `rm` runs without a prompt, a different flagged command (e.g. `chmod 777` on a scratch file) still prompts, then `/new`, then `rm` prompts again; (6) with a prompt pending, a second flagged command is withheld until the first is answered; (7) `/yolo` and `/update` are refused with the gating keys in the root-level `ntfy:` block; (8) `/approve always` on a scratch `rm`: `docker logs hermes_agent` shows `via /approve (always)`, and after `docker restart hermes_agent` the same `rm` prompts again. Extend § 3 with step 4: on PROD, `/approve always` on a scratch command, then `HermesPermanentApprovalGranted` arrives within 5 min, then restart `hermes_agent` (SC-001). Extend § 7 with step 5: stop the relay, and within 10 min `NtfyActionRelayDown` arrives on Pushover. (Done 2026-10-25 during analysis remediation.)

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: Data-driven ntfy ACLs (behaviour-preserving), the LAB scratch pair, and the LAB gate
that slice 1 depends on.

**⚠️ CRITICAL**: No user-story work starts until T008 passes.

- [x] T003 [P] Write guard test `python/tests/guardrails/test_ntfy_acl.py`: render `ansible/roles/ntfy/templates/server.yml.j2` with `jinja2` using `ntfy_users` from `ansible/roles/ntfy/defaults/main.yml` (stub secret vars with placeholders, `caddy_base_domain: example.invalid`), parse `auth-access` into `(user, topic, perm)` tuples, and assert today's matrix exactly: `owner:*:read-only` plus one `write-only` grant per publisher. Add helpers `writers(topic)` and `readers(topic)` for later tasks. Reuse the repo-root finder pattern from `python/tests/guardrails/test_log_pipeline.py`.
- [x] T004 Refactor `ansible/roles/ntfy/defaults/main.yml`: give each `ntfy_users` entry an `access:` list of `"<topic>:<perm>"` strings (e.g. `alertmanager` → `["alerts:write-only"]`) and drop the `topic:` key; add `ntfy_owner_access: ["*:read-only"]`. Behaviour must not change (T003 stays green).
- [x] T005 Update `ansible/roles/ntfy/templates/server.yml.j2` lines 21–25 to render `auth-access` from `ntfy_owner_access` and each user's `access` list (`"{{ user.name }}:{{ grant }}"`). Keep `message-size-limit: "32k"` unchanged (spec Edge Case "Oversized inbound message").
- [x] T006 Replace the "topic names are unique" assert in `ansible/roles/ntfy/tasks/preflight.yml` (line ~71) with two asserts: (a) every topic with a `write-only`/`read-write` grant has exactly one non-owner writer (082 rule); (b) no non-owner user has `write-only` or `read-write` on `hermes-in`, `actions` or `hermes-lab-in` (FR-002, data-model § Validation). Add the same two checks to `test_ntfy_acl.py`.
- [x] T007 Add the LAB scratch pair (spec FR-011, data-model § LAB scratch pair): in `ansible/roles/ntfy/defaults/main.yml` add user `hermes_lab` (`access: ["hermes-lab-in:read-only", "hermes-lab:write-only"]`, `password_hash: "{{ ntfy_hermes_lab_password_hash }}"`, `token: "{{ ntfy_hermes_lab_token }}"`) and `"hermes-lab-in:read-write"` to `ntfy_owner_access`; add both secrets to the asserts in `ansible/roles/ntfy/tasks/preflight.yml` and to the vault with `ansible-vault edit ansible/group_vars/services/vault.yml`. In `test_ntfy_acl.py` assert `hermes_lab` has no grant on any production topic (`hermes`, `hermes-in`, `actions`, `alerts`, `relay`, …). Render the LAB-rig branch of `agent.env.j2` now (T014 adds the PROD branch) and its rendered-file guard in `ansible/roles/hermes/tasks/main.yml`. Extend `scripts/healthcheck/ntfy-acl-check.sh` with the scratch-pair section of `contracts/acl-matrix.md` (new env var `NTFY_HERMES_LAB_TOKEN`). Configuration only; deploying it is T066–T068 (R-015).
- [x] T062 [P] Write guard test `python/tests/workflows/test_lab_rig_workflow.py` (red first; research R-015): `.github/workflows/lab-rig.yml` is `workflow_dispatch` only, with a choice input `action` = `up|deploy|status|down` and a string input `confirm`; concurrency group `pve-lab`, `cancel-in-progress: false`; the `down` path fails unless `confirm == destroy-lab-rig`, and that check comes before any `pve-lab down`; `up` runs `pve-lab run --profile hypervisor-control-plane --keep` (tier 2, never `pve-lab up`); every rig command sets `PROVISION_SSH_KEY=/home/ci/.ssh/lab_rig_ed25519`; vault comes from `/var/lib/homelab-proxmox/vault/.ansible_vault_pass` and no step references `secrets.ANSIBLE_VAULT_PASSWORD`; `deploy` runs `ansible/playbooks/hermes_lab_rig.yml` with `-i ansible/inventories/lab/hosts.yml` and `deploy_environment=lab`; `up` probes ntfy and the LLM router from the rig and fails if either is unreachable. `.github/workflows/proxmox-apply.yml` uses concurrency group `pve-lab` and has a step, before the harness step, that fails when `pve-lab status` reports a lab VM. `hermes_lab_rig.yml` targets `lab`, runs `geerlingguy.docker` and `hermes` only (no `lxc_base`, no `service_backup`), and loads `group_vars/services/vars.yml` and `vault.yml` via `vars_files`. Extract and `bash -n` every `run:` block (pattern of `test_workflow_heredocs.py`).
- [x] T063 Create `ansible/playbooks/hermes_lab_rig.yml` per T062 and R-015. Add a first-play assert: `lab_inventory | bool` and `deploy_environment == 'lab'`.
- [x] T064 Create `.github/workflows/lab-rig.yml` per T062 and R-015 (runs on `[self-hosted]`, syncs the repo to `ci@pve:/home/ci/homelab-proxmox/` like `proxmox-apply.yml`, then runs on `pve`): `up` creates `lab_rig_ed25519` if missing, runs the kept harness, then from the rig `curl` `https://ntfy.<domain>/v1/health` and the router's `/health/liveliness`; `deploy` runs the playbook; `status` runs `pve-lab status`; `down` checks `confirm` then runs `pve-lab down`.
- [x] T065 In `.github/workflows/proxmox-apply.yml` set concurrency group `pve-lab` and add, after the repo sync and before the harness, a step that fails while `pve-lab status` reports a lab VM ("a kept LAB rig exists; run lab-rig.yml action=down first").
- [x] T066 Run `bash scripts/ci/python-tests.sh`, `act -l` and `act -n -W` for `lab-rig.yml` and `proxmox-apply.yml` (`DOCKER_HOST` per AGENTS.md); record the result in the PR.
- [x] T070 [P] Write guard test `python/tests/guardrails/test_hermes_env_modes.py` (research R-016, condition 2). Render `ansible/roles/hermes/templates/agent.env.j2` offline with `jinja2` + `StrictUndefined` (repo-root finder and stub pattern of `test_ntfy_acl.py`; every secret stubbed with a distinct placeholder such as `STUB-<varname>`) in the three modes: **PROD** (`hermes_agent_operational: true`), **LAB rig** (`false`, `lab_inventory: true`), **pipeline LAB stage** (`false`, no `lab_inventory`). Assert: (a) PROD renders `NTFY_TOPIC=hermes-in`, `NTFY_ALLOWED_USERS=hermes-in` and the `ntfy_hermes_token` stub; the rig renders `NTFY_TOPIC=hermes-lab-in`, `NTFY_PUBLISH_TOPIC=hermes-lab`, the `ntfy_hermes_lab_token` stub and **neither** `hermes-in` nor the `ntfy_hermes_token` stub; the pipeline LAB stage renders no `NTFY_TOPIC`, `NTFY_TOKEN` or `NTFY_ALLOWED_USERS` (FR-011, 083 FR-014); (b) no mode renders `NTFY_ALLOW_ALL_USERS` or `GATEWAY_ALLOW_ALL_USERS` (FR-003); (c) `NTFY_ALLOWED_USERS` has no wildcard or comma; (d) **credential freeze**: the set of stub placeholders appearing in each mode's render equals a pinned set in the test (rig today: `hermes_agent_api_server_key`, `llm_router_client_hermes_agent_key`, `llm_router_client_scout_probe_key`, `ntfy_hermes_lab_token`), and the set of vault variables referenced by `docker-compose.yml.j2` equals a pinned set (`hermes_webui_secret_key`, `hermes_admin_password_bootstrap`, `llm_router_client_hermes_key`, `hermes_agent_api_server_key`, `hermes_searxng_secret`). The pinned sets carry a comment: "changing this set is a credential-policy decision; record it in research R-016". Also fix the stale header of `agent.env.j2` (lines 10–11 still describe two modes). Test-only plus a comment; must be green before T068.
- [x] T071 Close the confidence-suite hole (research R-016, condition 3). In `.github/workflows/lxc-promote-prod.yml`, job "Confidence suite (best-effort)", add a step after the repo sync and before "Run confidence suite on PVE" that fails while `pve-lab status` reports a lab VM, with the same command and message as the `proxmox-apply.yml` guard (T065). Extend `python/tests/workflows/test_lab_rig_workflow.py`: the step exists, contains `pve-lab status` and `exit 1`, and sits between the sync and the suite step. A failure here records the LAB gate as failed, so Prod 1 stops unless overridden, which is the intended outcome while a rig is held. Re-run `act -n -W .github/workflows/lxc-promote-prod.yml workflow_dispatch` and `bash scripts/ci/python-tests.sh`. Must land before T068.
- [ ] T067 **(manual)** Deploy `ntfy` from this branch through `Prod 1 - LXC Promote` → `Prod 2 - LXC Apply` (adds the `hermes_lab` scratch pair; production grants unchanged). Run `scripts/healthcheck/ntfy-acl-check.sh` with `NTFY_HERMES_LAB_TOKEN` set: every cell passes.
- [ ] T068 **(manual)** `gh workflow run lab-rig.yml -f action=up`. If the ntfy or router probe fails, **stop and raise it** (R-015: the fix is pve routing or the router allowlist, not in this branch). Then `-f action=deploy`; the role's LAB-rig guard must pass (scratch pair only).
- [ ] T008 **(manual) LAB gate** — run `quickstart.md` § 0 steps 1–9 on the LAB rig (deployed by T068) using the scratch pair from T007. Research R-014 has already predicted every result from the v0.21.6 source; the LAB run confirms it on the deployed image. Record pass/fail per step under research.md R-014 ("Verified on LAB <date>"), including the long-reply behaviour (step 7, spec US1 AS-4), whether hooks get a message id (step 8, FR-009) and the stream-error interval (step 9, FR-006). **If any step fails, stop and raise it.** If behaviour differs from R-014, update R-014 and the spec before PROD.
- [ ] T069 **(manual)** After T008: `gh workflow run lab-rig.yml -f action=down -f confirm=destroy-lab-rig`, then `-f action=status` shows no lab VM. **Rig lifetime (R-016)**: run this the same day as T068, also when T008 fails or stalls; bring the rig up again later rather than keep it. The rig holds production router keys (R-016, condition 1).

**Checkpoint**: ACLs are data-driven, the guard tests are green (including the credential freeze
of T070 and the confidence-suite guard of T071), the LAB rig talks on the scratch pair, the LAB
gate has passed, and the rig is torn down.

---

## Phase 3: User Story 1 — Chat with the agent from the phone (P1) 🎯 MVP

**Goal**: The owner types on `hermes-in`; the agent replies on `hermes` and keeps context.

**Independent Test**: quickstart § 3.1 and § 3.3; ACL rows for `hermes-in` in § 1 (SC-002).

### Tests for User Story 1

- [ ] T009 [P] [US1] Extend `python/tests/guardrails/test_ntfy_acl.py` with the `hermes-in` columns of `contracts/acl-matrix.md`: `writers("hermes-in") == {"owner"}`, `readers("hermes-in") == {"owner", "hermes"}`, `hermes` has no write on `hermes-in` (bold cells).
- [ ] T010 [P] [US1] Write guard test `python/tests/guardrails/test_hermes_ntfy_config.py` on `ansible/roles/hermes/templates/agent-config.yaml.j2`. (Parts (a)–(c) below moved forward to T070, which renders `agent.env.j2` in all three modes; do not duplicate them here.) ~~(a) `NTFY_TOPIC=hermes-in`, `NTFY_ALLOWED_USERS=hermes-in` and `ntfy_hermes_token` appear only in the PROD branch, and `hermes-lab-in`/`ntfy_hermes_lab_token` only in the LAB-rig branch; the pipeline LAB-stage branch renders no `NTFY_TOPIC` and no `NTFY_TOKEN` (spec FR-011); (b) `NTFY_ALLOW_ALL_USERS` and `GATEWAY_ALLOW_ALL_USERS` never appear as settings; (c) `NTFY_ALLOWED_USERS` has no wildcard or comma (FR-003);~~ (d) the ntfy slash-gating `user_allowed_commands` is exactly `approve, deny, new, reset, stop, status, compress, retry, undo, usage, title, model` (spec FR-014) and contains neither `yolo` nor `update`.
- [ ] T011 [P] [US1] Write `python/tests/hermes_hooks/test_audit_hook.py`: load `ansible/roles/hermes/files/hooks/audit/handler.py` with `importlib.util.spec_from_file_location`; assert `format_audit_line(event, topic, msg_id, text)` returns exactly `ntfy_audit event=<event> topic=<topic> msg_id=<id> text="<first 80 chars>"` (data-model § Audit line); event must be one of `inbound|approve|deny|slash_refused`; a missing message id renders `msg_id=-` and the line still carries the ISO timestamp (FR-009 fallback); text is cut at 80 chars, newlines become spaces, and `"` is escaped; `approve` events carry `scope=<once|session|always>` before `text=`. Because these tests read files under `ansible/`, add `ansible/roles/hermes/files/hooks` to `also_copy` in `setup.cfg` (mutmut copies only listed paths) and run `task mutmut:run` once to confirm the tests pass inside mutmut's tree.

### Implementation for User Story 1

- [ ] T012 [US1] In `ansible/roles/ntfy/defaults/main.yml` add `"hermes-in:read-only"` to `hermes`'s `access` and `"hermes-in:read-write"` to `ntfy_owner_access` (R-004: must be `read-write`, not `write-only`, because the specific entry replaces the wildcard read).
- [ ] T013 [P] [US1] Extend `scripts/healthcheck/ntfy-acl-check.sh` with the `hermes-in` read/write cells for every credential and `none`, per `contracts/acl-matrix.md`; update the header matrix comment. Never echo tokens.
- [ ] T014 [US1] **Status 2026-10-25: the three branches below already landed with T007 (commit `cc5e845`); only the comment rewrite remains, and T070 covers the branches.** Consequence until T015 lands: **do not deploy `hermes` to PROD from this branch** (Prod 1/Prod 2 with service `hermes`), because the PROD branch would subscribe to `hermes-in` without the slash-command gating. Harmless today (no credential can write `hermes-in` before T012), but out of order. T067 deploys `ntfy` only. Edit `ansible/roles/hermes/templates/agent.env.j2` lines 37–50 into three branches. **PROD** (`hermes_agent_operational`): `NTFY_TOPIC=hermes-in`, `NTFY_ALLOWED_USERS=hermes-in` (= topic name, R-003), `NTFY_PUBLISH_TOPIC=hermes`, `NTFY_HOME_CHANNEL=hermes`, `NTFY_TOKEN={{ ntfy_hermes_token }}`. **LAB rig** (`lab_inventory`): `NTFY_TOPIC=hermes-lab-in`, `NTFY_ALLOWED_USERS=hermes-lab-in`, `NTFY_PUBLISH_TOPIC=hermes-lab`, `NTFY_HOME_CHANNEL=hermes-lab`, `NTFY_TOKEN={{ ntfy_hermes_lab_token }}`. **Pipeline LAB stage** (anything else): no `NTFY_TOPIC` and no `NTFY_TOKEN`, which disables the ntfy platform (`required_env=["NTFY_TOPIC"]`, `adapter.py:362`) and ends the anonymous 403s. All branches keep `NTFY_SERVER_URL` and `NTFY_MARKDOWN=true`. Rewrite the comment block: inbound is `hermes-in` (scratch `hermes-lab-in` on the LAB rig), read-only for the agent's token, only the owner can write it, and neither `*_ALLOW_ALL_USERS` variable may ever be set (FR-013 control comment).
- [ ] T015 [US1] In `ansible/roles/hermes/templates/agent-config.yaml.j2`: (1) in the root-level `ntfy:` block (line ~84, beside `gateway_restart_notification`; path confirmed in research R-014) add `allow_admin_from: ["no-admin"]` (non-empty so gating is on; must **not** be `hermes-in` or `hermes-lab-in`, which are the sender ids, R-003) and `user_allowed_commands: [approve, deny, new, reset, stop, status, compress, retry, undo, usage, title, model]` (spec FR-014). The comment must say: `/yolo` and `/update` are excluded because they bypass approvals or change the agent; the others are conversation-scoped and recover from upstream's own error advice ("use /compress", "/retry", "/model"); `/help` lists exactly this set; and `/approve always` cannot be blocked here because gating matches command names, not arguments (R-014). (2) Change `approvals.timeout` from `300` to `900` (spec FR-004) and update its comment (no longer the upstream default; the authorization-gate lock follows it, `agent/tool_executor.py:153-160`). Leave the other `approvals:` keys unchanged (FR-005). Add to T010's test: `allow_admin_from` is non-empty and contains neither sender id.
- [ ] T016 [US1] Extend the LAB guards in `ansible/roles/hermes/tasks/main.yml` (lines ~99–116), checking the rendered env (`no_log: true`): on the pipeline LAB stage (`not hermes_agent_operational and not lab_inventory`) assert no `NTFY_TOKEN`, no `NTFY_TOPIC` and no `NTFY_ALLOWED_USERS` line (keep the existing 083 FR-014 assert); on the LAB rig assert `NTFY_TOPIC=hermes-lab-in`, `NTFY_PUBLISH_TOPIC=hermes-lab`, no `hermes-in` value and that the value of `ntfy_hermes_token` does not appear (spec FR-011). Add an unconditional assert that the rendered env never contains `NTFY_ALLOW_ALL_USERS` or `GATEWAY_ALLOW_ALL_USERS` (FR-003).
- [ ] T017 [US1] Create `ansible/roles/hermes/files/hooks/audit/HOOK.yaml` (events `agent:start` and `command:*`, per R-008) and `handler.py`, standard library only: `format_audit_line(...)` as tested in T011, plus the handler entry point, which prints one line per inbound ntfy message and per `/approve` (with scope), `/deny` or refused slash command to stdout. Confirm the hook API (handler signature, event payload fields) against `gateway/hooks.py` in the pinned image (v0.21.6). If the payload has no ntfy message id, use the `msg_id=-` fallback (FR-009); T008 step 8 records which applies.
- [ ] T018 [US1] In `ansible/roles/hermes/defaults/main.yml` add `hermes_agent_hooks_dir: "/opt/hermes-agent-hooks"`. In `ansible/roles/hermes/tasks/main.yml` copy `files/hooks/` to that directory (root-owned, `0644` files, `0755` dirs), so it is not writable by the agent UID.
- [ ] T019 [US1] In `ansible/roles/hermes/templates/docker-compose.yml.j2` (agent volumes, lines ~180–189) add read-only bind mounts `{{ hermes_agent_hooks_dir }}/audit:/opt/data/hooks/audit:ro` and `{{ hermes_agent_hooks_dir }}/gap-notice:/opt/data/hooks/gap-notice:ro`, with a comment explaining why they are read-only (plan § Complexity Tracking). Extend the confinement assert in `tasks/main.yml` (line ~213) to require `:ro` on every `/opt/data/hooks/` mount.
- [ ] T020 [US1] **(manual)** Roll out in order (plan § Rollout 2–4): deploy `ntfy`; run `scripts/healthcheck/ntfy-acl-check.sh` (all cells pass); deploy `hermes`; confirm the subscription-refused 403 warning has stopped (SC-004 clock starts); set up the phone per `docs/runbooks/ntfy-phone-setup.md` (subscribe to and mute `hermes-in`). Run quickstart § 3.1 and § 3.3, then send a prompt that forces a long reply and check it arrives split or visibly cut, as T008 step 7 recorded (US1 AS-4). Send `/help`, `/usage` and `/yolo`: the list matches FR-014, `/usage` answers, `/yolo` is refused (SC-007). Confirm audit lines in Loki: `{container="hermes_agent"} |= "ntfy_audit"` (FR-009).

**Checkpoint**: Phone chat works on PROD; only the owner can write `hermes-in`.

---

## Phase 4: User Story 2 — Answer an approval prompt on the phone (P1)

**Goal**: Flagged commands in phone sessions prompt on the phone; approve, deny, timeout and
pattern-scoped session approvals all behave as in FR-004; permanent approvals raise an alert.

**Independent Test**: quickstart § 3.2 plus the FR-004 checks in T026.

### Tests for User Story 2

- [ ] T021 [P] [US2] Add to `python/tests/guardrails/test_hermes_ntfy_config.py`: the `approvals:` block in `agent-config.yaml.j2` has `mode: manual`, `timeout: 900` (spec FR-004), and `deny` for `cron_mode`, `single_query_mode` and `unattended_mode` (FR-005, US2 AS-3).
- [ ] T022 [P] [US2] Create `python/tests/guardrails/test_hermes_log_rules.py` (shared with T028): `ansible/host_vars/hermes.yml` `log_alert_rules` contains an enabled rule `HermesPermanentApprovalGranted` whose selector matches `container="hermes_agent"` and `via /approve (always)`, with `for: "0m"` and `severity: warning` (FR-004, R-014). If `test_log_pipeline.py` asserts a rendered-rule count, update it there.

### Implementation for User Story 2

- [ ] T023 [US2] In `ansible/host_vars/hermes.yml` `log_alert_rules`, add `HermesPermanentApprovalGranted`: expr `sum(count_over_time({env="prod", host="hermes", container="hermes_agent"} |= "via /approve (always)" [5m])) > 0`, `for: "0m"`, `severity: warning`, `enabled: true`. Summary: "A permanent command approval was granted on Hermes". Description: "Scheduled jobs now skip their refusal for that pattern until the agent restarts (spec FR-004/FR-005, research R-014). If unintended, run `docker restart hermes_agent` on the hermes LXC." The upstream log line comes from `gateway/slash_commands.py:1206` and covers typed and bare-word approvals.

- [ ] T024 [US2] Add an "Approving from the phone" section to `docs/runbooks/ntfy-phone-setup.md`: `/approve` (or "yes"/"ok"/👍) runs one command; `/approve session` approves that kind of command until `/new` or `/reset`, and other flagged commands still prompt (FR-004); **do not use `/approve always` or reply "always"/"remember"**: it is permanent until the agent restarts and lets scheduled jobs run that pattern too. If it happens, `HermesPermanentApprovalGranted` fires; revoke it with `docker restart hermes_agent` (R-014). `/deny`, or no answer within 15 minutes, means it does not run; only one prompt is pending at a time; never approve without reading the command (R-006 residual risk). Also add a "Commands you can type" table: the FR-014 set with one line each (`/new` fresh conversation, `/compress` shorten a long one, `/retry` re-run the last message, `/undo` drop the last exchange, `/model` show or switch model alias, `/usage` token use, `/title` name the conversation, `/status`, `/stop`), and note that `/help` in the app shows the same list.
- [ ] T025 [US2] **(external)** Open an upstream PR to `nousresearch/hermes-agent` adding a config switch (e.g. `approvals.allow_permanent: false`) that removes the permanent tier from the text prompt, button actions, `/approve always` and bare-word `always`/`remember` (honoured in `tools/approval.py` `_persist_choice` and the `allow_permanent` flags at `:841`). Link it in research.md R-014. When a release ships it, bump `hermes_agent_version`, set the switch in `ansible/roles/hermes/templates/agent-config.yaml.j2`, add a guard-test assertion, and keep `HermesPermanentApprovalGranted` as a backstop.
- [ ] T026 [US2] **(manual)** On PROD from the phone (mobile data), run quickstart § 3.2 (approve, deny, timeout after 15 min), then: the prompt lists once, session, always and deny with the deadline; `/approve session` on a scratch `rm`, then a second `rm` runs with no prompt, a different flagged command still prompts, then `/new`, then `rm` prompts again (US2 AS-5, SC-001); with a prompt pending, a second flagged command is withheld until the first is answered (US2 AS-6); quickstart § 3.4 (permanent approval → `HermesPermanentApprovalGranted` within 5 min → restart → prompts again; US2 AS-7). The ACL check shows the agent's token is refused on `hermes-in` write (US2 AS-4). Record results in the PR.

**Checkpoint**: US1 and US2 work together; non-interactive surfaces still deny.

---

## Phase 5: User Story 3 — Know when messages were missed (P1)

**Goal**: A gap notice after every restart; an alert only for sustained mid-run stream drops.

**Independent Test**: quickstart § 4 (SC-003).

### Tests for User Story 3

- [ ] T027 [P] [US3] Write `python/tests/hermes_hooks/test_gap_notice_hook.py` (import as in T011): `parse_last_heartbeat(prom_text)` returns the value of `hermes_agent_heartbeat_timestamp_seconds`, or `None` if the file is missing or malformed; `build_gap_notice(started_at, last_heartbeat_at)` returns "Back online at <T>. Last heartbeat <H>. Anything sent to hermes-in between <H> and <T> was not received." in Europe/Oslo local time, with "Last heartbeat unknown" when `None`; `publish_headers(token)` includes `Priority: 2` (silent, spec FR-006) and the bearer token; `should_publish(env)` is False when `NTFY_TOKEN` is absent and True otherwise; there is **no threshold**: a gap of 1 s still produces a notice (FR-006).
- [ ] T028 [P] [US3] Add to `python/tests/guardrails/test_hermes_log_rules.py` (from T022): `ansible/host_vars/hermes.yml` `log_alert_rules` contains an enabled rule `HermesNtfyStreamDown` whose selector matches `container="hermes_agent"` and `Stream error`, with `for: "10m"` and a range window at least as long as the error interval T008 step 9 recorded.

### Implementation for User Story 3

- [ ] T029 [US3] Create `ansible/roles/hermes/files/hooks/gap-notice/HOOK.yaml` (event `gateway:startup`, R-007) and `handler.py`, standard library only: read `/heartbeat/hermes_agent.prom` (mounted on PROD only), build the notice, and POST it to `${NTFY_SERVER_URL}/${NTFY_PUBLISH_TOPIC}` with `Authorization: Bearer ${NTFY_TOKEN}` and `Priority: 2` using `urllib.request` (10 s timeout). It always posts on startup (no threshold, silent priority, FR-006) and skips when `NTFY_TOKEN` is absent (pipeline LAB stage). On failure it logs one line and never raises into the gateway. Keep `ntfy.gateway_restart_notification: false` in `agent-config.yaml.j2`; this notice replaces it.
- [ ] T030 [US3] In `ansible/host_vars/hermes.yml` `log_alert_rules`, add `HermesNtfyStreamDown`: expr `sum(count_over_time({env="prod", host="hermes", container="hermes_agent"} |= "Stream error" [5m])) > 0` (widen `[5m]` to the interval T008 step 9 recorded if it is longer), `for: "10m"`, `severity: warning`, `enabled: true`, with summary and description that point to US3 (spec FR-006: the estate alerts; the agent does not report this itself). Rewrite the comment at lines 47–49 (the 403 lines are gone with 093; a sustained stream error is now a real signal, R-007.2).
- [ ] T031 [US3] **(manual)** Deploy `hermes` and `monitoring`. Run quickstart § 4: stop and start `hermes_agent` for under a minute; the silent notice arrives within 60 s and the message sent during the gap is never answered (SC-003). Check that `lokitool rules check` passes in the monitoring deploy (validate_alerts).

**Checkpoint**: Slice 1 (US1–US3) is complete; MVP shippable.

---

## Phase 6: User Story 4 — Reply to scheduled-job output (P2)

**Goal**: A reply on `hermes-in` gets the latest (or named) job report as context.

**Independent Test**: Trigger the model-scout report, reply "benchmark it", and check the answer names the reported model.

- [ ] T032 [US4] **(spike)** Resolve R-009 against the v0.21.6 image: can an `agent:start` hook inject context into an ntfy session, or must a skill read a "recent reports" file? Can no-agent cron delivery (`standalone_sender_fn`) be made to also append to `/opt/data/reports/recent.jsonl` without a code change? Record the decision in `research.md` R-009. If it needs an upstream change, mark US4 as blocked and stop here.
- [ ] T033 [P] [US4] Write `python/tests/hermes_hooks/test_report_context_hook.py` for the chosen design: `select_report(reports, reply_text)` returns the most recent report unless the reply names a job by name (US4 AS-1); the file is bounded to the last 20 reports; the job is never re-run (AS-2).
- [ ] T034 [US4] Implement the T032 decision in `ansible/roles/hermes/files/hooks/report-context/{HOOK.yaml,handler.py}` (or a skill under the same `files/` tree), add the read-only mount to `ansible/roles/hermes/templates/docker-compose.yml.j2`, and deploy.
- [ ] T035 [US4] **(manual)** Run the independent test on PROD; record the result.

---

## Phase 7: User Story 5 — Act on an alert from the notification (P2)

**Goal**: The relay renders alerts with buttons, executes allowlisted silences, confirms every
press, and is itself monitored by a heartbeat.

**Independent Test**: quickstart § 7 steps 1–6 (SC-005).

- [ ] T036 [US5] **(manual, on device)** Verify R-006 (a) and (b): publish a notification on a scratch topic with a `broadcast` action `intent=io.heckel.ntfy.SEND_MESSAGE, extras.base_url=https://ntfy.hus-sky.no, extras.topic=<scratch-in>, extras.message=ping`; press it; confirm the publish arrives on `<scratch-in>`, authenticated as `owner` (refused if the owner grant is removed). Record in research.md R-006. **If it fails, stop US5 and US6**: no credential-free button design exists (FR-012).

### Tests for User Story 5

- [ ] T037 [P] [US5] Write `python/tests/ntfy_action_relay/test_command.py` for `parse_command(body, now)`: grammar `<verb> <target> [<param>=<value> ...] exp=<unix> v=1`; verb allowlist is `silence` only; `target` must be 16 hex characters; `dur` must be one of `1h`, `24h`, `morning` ("Anything else is refused"); `silence_end(dur, now)` for `morning` is the next 07:00 Europe/Oslo, at most 24 h ahead, correct across DST changes; `exp` in the past is refused as `expired`; unknown param, missing `v=1` or trailing text is refused as `refused: bad params`; title and tags are ignored.
- [ ] T038 [P] [US5] Write `python/tests/ntfy_action_relay/test_render.py`: `render_alert(webhook_alert, now)` gives title, priority and message identical to today's `ansible/roles/ntfy/files/homelab-alertmanager.yml` output for firing and resolved fixtures (golden strings stored in the test; parity test); the `Click` header is the alert's Grafana URL; firing alerts get exactly 3 actions: `Silence 1h`, `Silence until 07:00` (`dur=morning`), `Silence 24h` (broadcast `SEND_MESSAGE` to topic `actions`, message `silence <fp> dur=<d> exp=<now+24h> v=1`, `clear=true`), where `exp` is the **render time** + 24 h, so a repeat notification of an alert that started days ago has live buttons; resolved alerts get no buttons; **no rendered field contains a token or `Authorization`** (FR-012).
- [ ] T039 [P] [US5] Write `python/tests/ntfy_action_relay/test_execute.py` with a fake Alertmanager client: the state machine `received → refused(unknown verb|bad params|expired|duplicate|target unknown) | executed → confirmed` (data-model § Action command); a duplicate message id is silent and only logged; the relay's seen-map (fingerprint → labels, last seen, filled from the webhook) accepts a fingerprint seen within 24 h **even if it has resolved since** (flapping case, spec US5 AS-2) and builds the silence matchers from its stored labels; a fingerprint not seen within 24 h, or unseen since a relay restart, gives `target unknown`; an existing matching active silence gives `already silenced` and creates nothing (R-012); the seen-map and the dedupe LRU are bounded; each outcome's response text matches `contracts/action-command.md` § Relay responses exactly; each outcome logs one stdout line (FR-009).
- [ ] T040 [P] [US5] Write `python/tests/ntfy_action_relay/test_heartbeat.py`: `/metrics` exposes `ntfy_action_relay_heartbeat_timestamp_seconds`; the value is refreshed by the subscription loop on every keepalive or message and **not** by the HTTP server alone, so a dead subscriber shows as stale (FR-008 heartbeat).

### Implementation for User Story 5

- [ ] T041 [US5] Implement `python/src/homelab_proxmox_orchestrator/ntfy_action_relay.py` (stdlib only: `http.server`, `urllib.request`, `json`, `threading`; runnable with `python ntfy_action_relay.py`, no package-relative imports) so that T037–T040 pass. Parts: `POST /alertmanager` webhook receiver → update the seen-map → `render_alert` → publish to `alerts`; subscriber on `${NTFY_URL}/actions/json` with no `since` (R-012), reconnecting with backoff; executor using the Alertmanager v2 API (`GET/POST /api/v2/silences`, matchers from the seen-map labels) at `ALERTMANAGER_URL`; responses published to `relay`; `GET /metrics`. Config from env only: `NTFY_URL`, `NTFY_TOKEN`, `ALERTMANAGER_URL`, `GRAFANA_URL`, `LISTEN_PORT`.
- [ ] T042 [US5] Add `--cov=homelab_proxmox_orchestrator.ntfy_action_relay` to `addopts` in `python/pytest.ini`, and run `bash scripts/ci/python-tests.sh` (≥80 % overall must still hold).
- [ ] T043 [US5] In `ansible/roles/ntfy/defaults/main.yml` add user `action_relay` (`access: ["alerts:write-only", "relay:write-only", "actions:read-only"]`, `password_hash: "{{ ntfy_action_relay_password_hash }}"`, `token: "{{ ntfy_action_relay_token }}"`) and `"actions:read-write"` to `ntfy_owner_access`. Remove `"alerts:write-only"` from `alertmanager` (one publisher per topic). Add both new secrets to the secret, token-format and bcrypt asserts in `ansible/roles/ntfy/tasks/preflight.yml`. Add the values with `ansible-vault edit ansible/group_vars/services/vault.yml` (never in plain text, constitution II).
- [ ] T044 [P] [US5] Extend `python/tests/guardrails/test_ntfy_acl.py` with the `actions`, `alerts` and `relay` columns of `contracts/acl-matrix.md` (`writers("actions") == {"owner"}`, `writers("alerts") == {"action_relay"}`, `writers("relay") == {"action_relay"}`, and `hermes` has no access to `actions`).
- [ ] T045 [P] [US5] Extend `scripts/healthcheck/ntfy-acl-check.sh`: require `NTFY_ACTION_RELAY_TOKEN`; add `actions`, `relay` and `alerts` rows for every credential; `alertmanager` now writes nothing (it is removed in T050).
- [ ] T046 [US5] Add the relay to `ansible/roles/monitoring_stack`: in `templates/docker-compose.yml.j2` add service `action-relay` (`image: python:{{ ntfy_action_relay_python_version }}-slim`, `command: ["python", "/app/ntfy_action_relay.py"]`, module mounted `:ro`, `env_file` 0600, `restart: unless-stopped`, **no `ports:`**, `depends_on: [alertmanager]`, and the same `extra_hosts` block as `blackbox-exporter` (from `blackbox_static_hosts`) so `ntfy.<domain>` resolves to the reverse proxy on the LAN). In `tasks/compose_stack.yml` copy `python/src/homelab_proxmox_orchestrator/ntfy_action_relay.py` to `{{ monitoring_install_dir }}/action-relay/` and render `action-relay.env` (`NTFY_URL=https://ntfy.{{ caddy_base_domain }}`, `NTFY_TOKEN={{ ntfy_action_relay_token }}`, `ALERTMANAGER_URL=http://alertmanager:9093`, `GRAFANA_URL`, `LISTEN_PORT=8080`) with `no_log: true`. Pin `ntfy_action_relay_python_version` (e.g. `"3.11.10"`) in `ansible/group_vars/monitoring/vars.yml`, and register the pin if `python/tests/guardrails/test_version_pins.py` enumerates image pins.
- [ ] T047 [US5] In `ansible/roles/monitoring_stack/templates/alertmanager.yml.j2`, replace the three ntfy `webhook_configs` (lines ~88–97, ~111–120, ~141–150) with `url: 'http://action-relay:8080/alertmanager'`, with no credentials and `send_resolved: true` kept. Leave `pushover_configs` unchanged. Update the comment block at lines ~64–72 (the relay is now the ntfy side; R-010).
- [ ] T048 [US5] Relay heartbeat (FR-008, SC-005): in `ansible/roles/monitoring_stack/templates/prometheus.yml.j2` add a static job `ntfy-action-relay` with target `action-relay:8080` beside the `loki` job (line ~59), guarded by `ntfy_enabled`. Add alert `NtfyActionRelayDown` (`up{job="ntfy-action-relay"} == 0 or time() - ntfy_action_relay_heartbeat_timestamp_seconds > 300 or absent(ntfy_action_relay_heartbeat_timestamp_seconds)`, `for: 5m`, `severity: warning`, description: "Alert buttons are dead; Pushover is unaffected") as a static group in `templates/service_alerts.yml.j2`, also guarded by `ntfy_enabled`. Confirm `tasks/validate_alerts.yml` (promtool) passes.
- [ ] T049 [US5] **(manual)** Deploy `ntfy`, then `monitoring`. Run `ntfy-acl-check.sh`, then quickstart § 7 steps 1–6: three buttons render and tapping opens the dashboard; Silence 1h gives exactly one silence and a confirmation on `relay` within 30 s; a past-`exp` replay gives "Button expired" and no new silence; with the relay stopped, presses get no confirmation, Pushover still delivers, and `NtfyActionRelayDown` arrives via Pushover; a press on a just-resolved alert still silences it (SC-005, US5 AS-2/AS-4/AS-5).
- [ ] T050 [US5] After T049 passes, retire the old path (plan § Constitution IV watch item): remove the `alertmanager` user from `ansible/roles/ntfy/defaults/main.yml` and its secrets from `tasks/preflight.yml` and `ntfy-acl-check.sh`; delete `ansible/roles/ntfy/files/homelab-alertmanager.yml`, its copy task (`ansible/roles/ntfy/tasks/main.yml` lines ~37–41) and `template-dir:` in `server.yml.j2`; update the `ntfy_alertmanager_token` comment in `ansible/group_vars/monitoring/vars.yml`. Remove the vault entries with `ansible-vault edit`. Redeploy `ntfy` and re-run the ACL check.

**Checkpoint**: Alert buttons work end to end; the relay is monitored; the old Go template is gone.

---

## Phase 8: User Story 6 — Native approval buttons (P2)

**Goal**: Approval prompts carry Approve once / Approve session / Deny buttons that the agent cannot forge.

**Independent Test**: An approval prompt shows buttons; Approve runs the command; a press forged from anything the agent can read has no effect.

- [ ] T051 [US6] **(external)** Open an upstream PR to `nousresearch/hermes-agent`: the ntfy adapter overrides `_send_exec_approval_prompt` to attach `broadcast`/`SEND_MESSAGE` actions to `hermes-in` (`/approve`, `/approve session`, `/deny`; plus `/approve always` only until the T025 switch ships), with labels that state each scope (FR-004), plus a `view` "Reply" action on normal messages (R-013). No credential in any action (FR-012). Gate: T036 passed. Link the PR in research.md R-006.
- [ ] T052 [US6] When the PR is released, bump `hermes_agent_version` in `ansible/group_vars/services/vars.yml` (line 41), recheck `_config_version` in `ansible/roles/hermes/templates/agent-config.yaml.j2` (line 16, R-001 note), deploy to LAB, then PROD.
- [ ] T053 [US6] **(manual)** On PROD: buttons appear; Approve once, Approve session (then `/new` resets) and Deny match US2; a notification the agent publishes on `hermes` with an `/approve` button is a press by the owner, so record the R-006 residual risk in `docs/runbooks/ntfy-phone-setup.md` ("read the command before pressing").

---

## Phase 9: User Story 7 — Act on other estate notifications (P3)

**Goal**: Each further action is admitted only after its own threat review.

- [ ] T054 [US7] Add "Admitting a new relay action" to `specs/095-ntfy-two-way/contracts/action-command.md`: per action, record the verb, bounded parameters, target-state validation, executor and network reach (revisit R-011 if it needs `pve`), threat review (forgery, replay, blast radius) and tests in `python/tests/ntfy_action_relay/`. State that no generic "run a command" verb is ever admitted (US7 AS-1, Out of Scope). No action is admitted in this feature.

---

## Phase 10: Polish & cross-cutting

- [ ] T055 [P] FR-013: amend `docs/backlog/082-ntfy-push-service.md` (publish-only → two-way via `hermes-in` and `actions`, owner-only write) and `docs/backlog/083-hermes-agent-runtime.md` (delivery-only → interactive ntfy sessions with phone approvals, FR-005 surfaces unchanged; silent restarts → silent gap notice at priority 2; approval timeout 300 s → 15 min; FR-014 LAB stage → LAB rig may hold the scratch-pair credential); close `docs/backlog/093-hermes-agent-ntfy-403.md` as superseded by 095; set the status in `docs/backlog/095-ntfy-two-way.md`.
- [ ] T056 [P] FR-010: in `docs/runbooks/ntfy-phone-setup.md` add subscribing to `hermes-in` (muted) and `relay`, and a "Phone lost / revoke" procedure: the app signs in with the owner **password**, so rotate both `ntfy_owner_password_hash` and `ntfy_owner_token` with `ansible-vault edit`, deploy `ntfy` once, verify the old password and old token are refused (quickstart § 6), and sign the new phone in with the new password (SC-006).
- [ ] T057 [P] Update the ntfy data-flow description in `docs/architecture.md` (inbound `hermes-in` → agent; `actions` → relay → Alertmanager).
- [ ] T058 **(manual)** Rotate `ntfy_hermes_token` (it appeared in an earlier session's output; plan § Rollout 5): vault edit, deploy `ntfy` and `hermes`, re-run the ACL check.
- [ ] T059 **(manual)** SC-006 drill: run quickstart § 6 and expect 403 for both the old owner password and the old owner token after one deploy.
- [ ] T060 Run `bash scripts/ci/python-tests.sh` and `task mutmut:run -- "homelab_proxmox_orchestrator.ntfy_action_relay*"`. The score must stay at or above the floor in `python/mutmut-threshold.txt` minus 1. Workflow files changed in T064/T065; `act` ran in T066.
- [ ] T061 **(manual)** SC-004: 7 days after T020, run `{container="hermes_agent"} |= "Stream error"` in Loki and expect zero subscription-refused lines. Then close 093 for real.

---

## Dependencies & execution order

### Phase dependencies

- **Setup (T001–T002)**: done 2026-10-25 (analysis remediation).
- **Foundational (T003–T008, T062–T071)**: T003 → T004 → T005 → T006 → T007 (same files).
  T062 (test) → T063, T064, T065 → T066 → push. T070 and T071 (R-016) are independent of each
  other and of T067. T067 needs T007 and the push; T068 needs T064, T067, T070 and T071. T008
  (LAB gate) needs T068 and blocks US1–US3. T069 after T008, the same day as T068. IDs T062–T071
  were added on 2026-10-25 (R-015, R-016) and sit in Phase 2 out of numeric order.
- **US1 (T009–T020)**: after T008. Tests T009–T011 first. T012 → T020; T014 → T016; T017 → T018 → T019.
- **US2 (T021–T026)**: config lands with US1 (T015). T022 → T023; the T023 rule is rendered by the
  `monitoring` role (`log_alerts.yaml.j2` reads every host's contract), so deploy `monitoring` before
  T026. T026 needs T020 and T023. T025 is external and blocks nothing in slice 1.
- **US3 (T027–T031)**: T029 needs T018/T019 (the hooks dir and mount, shared with US1); T030 is independent.
- **US4 (T032–T035)**: after US1. T032 gates the rest.
- **US5 (T036–T050)**: T036 gates. Independent of the agent (US1–US4). T037–T040 → T041 → T042;
  T043 → T044/T045; T046 needs T041 and T043; T047 and T048 need T046; T049 → T050.
- **US6 (T051–T053)**: needs T036 and US2. T051 is external and can be slow.
- **US7 (T054)**: after US5.
- **Polish**: T055–T057 any time after US1; T058 after T020; T061 seven days after T020.

### User story dependencies

- US1: foundation only. US2 and US3: share US1's config and hooks mount and ship together (slice 1).
- US4: needs US1. US5: independent of the agent. US6: needs US2 and US5's T036.

## Parallel examples

```text
# Foundational/US1 tests (different files):
T003 test_ntfy_acl.py   |  T010 test_hermes_ntfy_config.py  |  T011 test_audit_hook.py

# Before the rig goes up (R-016):
T070 test_hermes_env_modes.py  |  T071 confidence-suite guard (lxc-promote-prod.yml)

# US3 alongside US1 implementation:
T027 test_gap_notice_hook.py  |  T028 hermes stream-rule test  |  T030 host_vars/hermes.yml rule

# US5 tests together:
T037 test_command.py | T038 test_render.py | T039 test_execute.py | T040 test_heartbeat.py

# Polish docs:
T055 backlog amendments | T056 phone runbook | T057 architecture.md
```

## Implementation strategy

### MVP = slice 1 (US1 + US2 + US3)

The spec makes all three P1 and the first deliverable (Clarifications: "Agent chat, approvals
and the offline notice"). Shipping chat without US3 would make dropped messages look ignored.

1. T003–T007 → T062–T066 → T070, T071 (credential freeze, confidence-suite guard; R-016) →
   T067 (ntfy deploy) → T068 (rig up/deploy) → **T008 LAB gate** (stop if it fails) → T069 (rig
   down, same day)
2. US1 → US2 → US3 → validate (T020, T026, T031) → T055, T056, T058
3. Start the SC-004 seven-day clock

### Incremental after MVP

4. US5 (relay + heartbeat), gated by T036. It is independent of the agent and highest-value.
5. US4 (after the T032 spike) and US6 (after the upstream PR).
6. US7 as a process only.

## Notes

- Secrets: never in plain text. New vault keys are `ntfy_action_relay_password_hash` and
  `ntfy_action_relay_token`; removed keys are `ntfy_alertmanager_*` (after T050).
- Every service deploy goes through the `Prod 1 / Prod 2` pipeline or a laptop run (constitution
  V); no new service, so the workflow dropdowns are unchanged. The LAB rig goes through
  `lab-rig.yml`; its laptop path is the same commands from `ssh ci@pve` (R-015).
- Commit after each task or logical group. Push via the gh Git-Data API (AGENTS.md).
- **LAB rig credentials (R-016)**: the rig runs with production router and Hermes identities for
  the T008 gate only; ntfy is the one LAB-specific credential. Do not add keys to the rig in 095;
  T070's pinned sets make any addition fail CI. Out of 095, for a follow-up backlog item: a rig
  credential allowlist with rig-specific router keys, a rig-correct `hermes-own-node-exporter`
  egress probe, and an expiry or alert for a forgotten rig.
