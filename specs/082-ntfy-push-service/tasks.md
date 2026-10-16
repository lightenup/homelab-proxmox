---
description: "Task list for 082-ntfy-push-service implementation"
---

# Tasks: ntfy — self-hosted push notifications to the owner's phone

**Input**: Design documents from `/specs/082-ntfy-push-service/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: No unit-test suite is generated. The spec does not ask for one, and the feature ships no
application code (FR-017). Per Constitution § *Test-Driven Changes*, validation consists of:

- non-destructive checks: `pve-service-deploy plan`, `ansible-playbook --check --diff`, preflight
  assertions, an idempotence re-run, and a gate-off render diff;
- one scripted check (`ntfy-acl-check.sh`, SC-002);
- the drills in [quickstart.md](./quickstart.md).

All of these appear below as tasks.

**Environments**: LAB proves the LXC, the role and the ACL matrix against the service's direct
address. Caddy, monitoring and the phone are proven on PROD. Monitoring changes deploy through the
prod promote path, with the LAB monitoring gate expected to refuse (precedent: `065` tasks.md
progress note, backlog `072`).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: The user story this task belongs to (US1–US4 from spec.md)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Branch, secrets, and the central variables every later task reads.

- [X] T001 Create branch `082-ntfy-push-service` from `main` (the spec, plan and `CLAUDE.md` changes are already in the working tree; commit them as the first commit on the branch)
- [ ] T002 Generate the six secrets and add them to the encrypted `ansible/group_vars/services/vault.yml` with `ansible-vault edit` (research R-012). Use `docker run --rm -it binwiederhier/ntfy:v2.28.0 user hash` for `ntfy_owner_password_hash` (enter the real owner password and store it only in the password manager). Use the same command with a random password that you then discard for `ntfy_alertmanager_password_hash` and `ntfy_hermes_password_hash`. Use `docker run --rm binwiederhier/ntfy:v2.28.0 token generate` three times for `ntfy_owner_token`, `ntfy_alertmanager_token` and `ntfy_hermes_token`. Constraints: hashes are bcrypt with "cost ≥ 10". Tokens are "`tk_` + 29 chars" (32 total). Never commit plaintext
- [X] T003 [P] Add `ntfy_version: "v2.28.0"` to the `# Service versions` block, and a `# ntfy Configuration (spec 082)` block with `ntfy_ip: "192.168.1.222"`, `ntfy_port: 80`, and `ntfy_metrics_port: 9090` (consumed by the compose file and `host_vars/ntfy.yml`) after the Hermes block. The cache duration is inlined in `server.yml.j2` (T012); it has one consumer, so it gets no variable (constitution IV), in `ansible/group_vars/services/vars.yml`
- [X] T004 [P] Add `ntfy = "192.168.1.222/24"` to `service_ips` (aligned with the other entries, after `hermes`) in `terraform/environments/lab.tfvars.template` and `terraform/environments/prod.tfvars.template`
- [X] T005 [P] Add `ntfy` (`ansible_host: 192.168.1.222`, `ansible_user: root`) under `services.hosts` after `hermes` in `ansible/inventories/prod/hosts.yml`. This is required for any monitoring to be generated (research R-010, backlog `066`)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: A running, access-controlled ntfy reachable at `https://ntfy.hus-sky.no`. Every user
story publishes to or reads from it.

**⚠️ CRITICAL**: No user-story work can start until this phase is complete.

### Machine and pipeline parity (FR-001, FR-016)

- [X] T006 [P] Create `terraform/services/ntfy/main.tf` with `module "ntfy_lxc"` copied from `terraform/services/hermes/main.tf`: `name = "ntfy-lxc"`, `hostname = "ntfy"`, `cores = 1`, `memory = 512`, `disk_gb = 8`, `ip = var.service_ips["ntfy"]`, and no `features_mount` (comment: local-disk state only, no NFS, no backup — R-008). Do not touch `terraform/main.tf`
- [X] T007 [P] Create `terraform/services/ntfy/outputs.tf` with `output "ansible_inventory"` returning `{ services = { "ntfy" = module.ntfy_lxc.ipv4 } }` (copy of `terraform/services/eurooffice/outputs.tf`)
- [X] T008 [P] Add `"ntfy": ["module.ntfy_lxc"]` in alphabetical position in `scripts/lab/service-scope-allowlist.json`
- [X] T009 [P] Add `ntfy` to the service `options:` dropdown in `.github/workflows/lxc-deploy-lab.yml`, `.github/workflows/lxc-promote-lab.yml` and `.github/workflows/lxc-promote-prod.yml`, then run `act -l` (constitution § Local Workflow Testing; record the reason if `act` is unavailable) — `act` is not installed in this environment; dropdowns verified by inspection
- [ ] T010 Run `scripts/lab/pve-service-deploy plan --environment lab --service ntfy` and confirm the plan creates exactly `module.ntfy_lxc` and nothing else (depends on T004, T006–T008)

### ntfy role (contracts/server-config.md)

- [X] T011 [P] Create `ansible/roles/ntfy/defaults/main.yml` with `ntfy_install_dir: /opt/ntfy`, `ntfy_data_dir: /opt/ntfy-data` and `ntfy_image: binwiederhier/ntfy`. Add `ntfy_users`, a list of `{name, topic, password_hash, token}` for `alertmanager` (topic `alerts`) and `hermes` (topic `hermes`), each referencing its vault vars. Keep `owner` separate as `ntfy_owner_password_hash`/`ntfy_owner_token` (read `*`, no topic). Rules from data-model.md: "A topic has exactly one publisher", "No account has role `admin`"
- [X] T012 [P] Create `ansible/roles/ntfy/templates/server.yml.j2` with exactly the required keys in contracts/server-config.md: `base-url`, `listen-http: ":80"`, `behind-proxy: true`, `metrics-listen-http: ":9090"`, `cache-file`, `cache-duration: "72h"` (inline, FR-013), `auth-file`, `auth-default-access: deny-all`, `auth-users` (`name:hash:user` for owner and each `ntfy_users` item), `auth-access` (`owner:*:read-only`, then `<name>:<topic>:write-only` per publisher), `auth-tokens` (`name:token:<label>`), `template-dir: /etc/ntfy/templates` and `message-size-limit: "32k"`. Header comment: Generated by Ansible, plus a pointer to the contract. None of the Forbidden keys may appear
- [X] T013 [P] Create `ansible/roles/ntfy/templates/docker-compose.yml.j2` following contracts/server-config.md § Compose shape: service `ntfy`, `container_name: ntfy`, image `{{ ntfy_image }}:{{ ntfy_version }}`, `command: serve`, ports `"{{ ntfy_port }}:80"` and `"{{ ntfy_metrics_port }}:9090"`. Mounts: `{{ ntfy_install_dir }}/server.yml:/etc/ntfy/server.yml:ro`, `{{ ntfy_install_dir }}/templates:/etc/ntfy/templates:ro` and `{{ ntfy_data_dir }}:/var/lib/ntfy`. Also `restart: unless-stopped` and a healthcheck `wget -q --spider http://localhost/v1/health`. No secrets and no `environment:` with credentials (R-011)
- [X] T014 [P] Create `ansible/roles/ntfy/tasks/preflight.yml` modelled on `ansible/roles/eurooffice/tasks/preflight.yml`. Assert that `ntfy_version` is pinned (not empty, not `latest`). Assert that every token matches `^tk_[A-Za-z0-9]{29}$`. Assert that every hash matches `^\$2[aby]\$(1[0-9]|[2-3][0-9])\$` (bcrypt, cost ≥ 10). Assert that the six vault vars are defined and non-empty, with a fail message naming `ansible-vault edit group_vars/services/vault.yml`. Assert that topic names in `ntfy_users` are unique
- [X] T015 [P] Create `ansible/roles/ntfy/handlers/main.yml` with `Restart ntfy` (`community.docker.docker_compose_v2`, `state: restarted`), copying the eurooffice handler
- [X] T016 Create `ansible/roles/ntfy/tasks/main.yml`: include preflight; create `ntfy_install_dir`, `ntfy_install_dir/templates` and `ntfy_data_dir`; template `server.yml` (mode `0600`, owner root, `notify: Restart ntfy`); template the compose file (`notify: Restart ntfy`); bring the stack up with `docker_compose_v2` (`state: present`, `remove_orphans: true`, `pull: always`); wait for `/v1/health` on `127.0.0.1:{{ ntfy_port }}` to return 200 with retries. Then add a post-render FR-004 assertion: `slurp` the rendered `server.yml` and fail if it contains `upstream-base-url`, `upstream-access-token`, `firebase-key-file`, `web-push-`, `smtp-sender-` or `twilio-` (research R-009) (depends on T011–T015)
- [X] T017 [P] Create `ansible/playbooks/ntfy.yml` as a copy of `ansible/playbooks/eurooffice.yml` with `hosts: ntfy` and roles `lxc_base`, then `geerlingguy.docker` and `ntfy`
- [X] T018 [P] Create `ansible/host_vars/ntfy.yml` with the `healthcheck_url` block only (`scheme: http`, `port: 80`, `path: /v1/health`), `healthcheck_profile: lan` and `healthcheck_expect_status: 200`. `monitoring_contract` is added in T038
- [X] T019 [P] Create `scripts/healthcheck/ntfy.sh` as a copy of `scripts/healthcheck/eurooffice.sh` with `--host ntfy` and the usage text updated, then `chmod +x`

### Route (FR-003)

- [X] T020 Add a `caddy_services` entry after `hermes` in `ansible/group_vars/services/vars.yml`: `host: ntfy`, `ip: "{{ ntfy_ip }}"`, `port: "{{ ntfy_port }}"`, `title: "ntfy"`, `desc: "Push notifications to the phone"`, `enabled: true`, `user_facing: true`. Add a comment that the same flag drives the route, the card and the HTTPS probe (R-007), and that `web-root` must stay `/` so the probe gets a 200. This also creates the US4 card, which US4 verifies

### Deploy and prove the base

- [ ] T021 Deploy to LAB (pipeline `lxc-deploy-lab`, service `ntfy`, or the same `pve-service-deploy apply --environment lab --service ntfy` locally), then run `ansible-playbook ansible/playbooks/ntfy.yml --check --diff`, then the real run. Expected: `curl -s http://<lab ntfy ip>/v1/health` returns `{"healthy":true}` (quickstart § 1)
- [ ] T022 Re-run the playbook on LAB and confirm it reports **0 changed**, which proves the hashes and rendered config are stable (research R-012). If anything changes, fix it before continuing
- [ ] T023 Promote to PROD (`lxc-promote-lab` → `lxc-promote-prod`), run `ansible-playbook ansible/playbooks/reverse_proxy.yml` so Caddy serves `ntfy.hus-sky.no`, and confirm `https://ntfy.hus-sky.no/v1/health` returns healthy from the LAN

**Checkpoint**: ntfy is running at `ntfy.hus-sky.no` with `deny-all`. Stories can start.

---

## Phase 3: User Story 2 — A script or scheduled job notifies the phone (Priority: P1) 🎯 MVP

Ordered first among the P1s: it is the capability that does not exist today, `083` depends on it,
and its scripted check gates every other story's security.

**Goal**: Every publisher writes only to its own topic. Nobody without a credential reads or writes
anything.

**Independent Test**: Publishing to `hermes` with the hermes token from the Hermes LXC succeeds.
Publishing without a token, or with the alertmanager token, is refused (spec US-2). The full matrix
is scripted.

- [X] T024 [US2] Create `scripts/healthcheck/ntfy-acl-check.sh` (bash, `set -euo pipefail`). It reads `NTFY_URL`, `NTFY_OWNER_TOKEN`, `NTFY_ALERTMANAGER_TOKEN` and `NTFY_HERMES_TOKEN` from the environment and asserts every one of the 20 cells in data-model.md § "The access matrix the SC-002 check asserts". Writes use `curl -X POST -d "acl-check $(date -Is)"` (tagged `Tags: acl-check`, priority `min`). Reads use `GET <topic>/json?poll=1&since=1m`. ✓ means HTTP 200; ✗ means HTTP 401 or 403. Print one line per cell (`PASS`/`FAIL credential action topic got=<code>`), print a summary, and exit non-zero on any FAIL. Support `--help`. Never echo tokens
- [ ] T025 [US2] Run `scripts/healthcheck/ntfy-acl-check.sh` against LAB (`NTFY_URL=http://<lab ntfy ip>`) and PROD (`NTFY_URL=https://ntfy.hus-sky.no`), with tokens exported from vault. Expected: 20/20 PASS on both (SC-002, quickstart § 2)
- [ ] T026 [US2] From the Hermes LXC (`ssh root@192.168.1.221`), publish to `https://ntfy.hus-sky.no/hermes` with `Authorization: Bearer <ntfy_hermes_token>`. Confirm HTTP 200 and that the message appears in the owner's read (`GET /hermes/json?poll=1`, owner token). This proves the path `083` will use
- [X] T027 [P] [US2] Write `docs/runbooks/ntfy-add-publisher.md` from contracts/publisher-interface.md § Onboarding: add a `ntfy_users` item, add two vault vars, deploy, subscribe in the app, and extend the matrix in `ntfy-acl-check.sh`

**Checkpoint**: US2 is complete. `083` can consume `ntfy_hermes_token`.

---

## Phase 4: User Story 1 — An alert reaches the phone through the new channel (Priority: P1)

**Goal**: Every alert goes to Pushover (unchanged) **and** ntfy, rendered with Pushover-style titles
and severity-mapped priority.

**Independent Test**: Fire a test alert. It appears in the ntfy app, formatted, within a minute,
and Pushover still receives it (spec US-1).

- [X] T028 [P] [US1] Create `ansible/roles/ntfy/files/homelab-alertmanager.yml` (Go template, not Jinja) with `title`, `message` and `priority` keys, implementing data-model.md § "Alert → notification mapping" exactly. Title: `[CRITICAL]`/`[WARNING]`/`[INFO] <groupLabels.alertname>`, or `[RESOLVED] <groupLabels.alertname>` when `status == "resolved"`, with `(+N more)` appended when `truncatedAlerts > 0`. Message: one `annotations.summary` line per alert. Priority: severity `info` → `1` (firing or resolved); `status == "resolved"` → `3`; `critical` firing → `5`; otherwise `3`. Severity is read from `commonLabels.severity`, and a missing label must not error (use `default`)
- [X] T029 [US1] In `ansible/roles/ntfy/tasks/main.yml`, add a `copy` task that installs `files/homelab-alertmanager.yml` to `{{ ntfy_install_dir }}/templates/homelab-alertmanager.yml` (mode `0644`, `notify: Restart ntfy`), placed before the compose-up task (depends on T028)
- [X] T030 [US1] Add `ntfy_enabled: true`, with a comment pointing at spec 082 and contracts/alertmanager-webhook.md, next to `pushover_enabled` in `ansible/group_vars/monitoring/vars.yml`. **Set it to `false` until T033 has passed** — set to `false` as instructed
- [X] T031 [US1] In `ansible/roles/monitoring_stack/templates/alertmanager.yml.j2`, add the `webhook_configs` block from contracts/alertmanager-webhook.md (URL `https://ntfy.{{ caddy_base_domain }}/alerts?template=homelab-alertmanager`, `send_resolved: true`, `max_alerts: 10`, `http_config.authorization` Bearer `{{ ntfy_alertmanager_token }}`). Put it inside `pushover-critical`, `pushover-warning` and `pushover-info`, each wrapped in `{% if ntfy_enabled | default(false) | bool %}`. Do not change routes, matchers or inhibit rules. Add a comment block explaining the shared-receiver choice and the R-005 fallback
- [ ] T032 [US1] Gate check: render `alertmanager.yml.j2` with `ntfy_enabled: false` by running `ansible-playbook ansible/playbooks/monitoring.yml --check --diff --limit monitoring -e ntfy_enabled=false` (the `monitoring_stack` role has no task tags, so run without `--tags`). Confirm the diff shows **no change** to `{{ alertmanager_config_path }}/alertmanager.yml`, which `ansible/roles/monitoring_stack/tasks/compose_stack.yml` writes and where `alertmanager_config_path` is `{{ monitoring_base_path }}/alertmanager` in `group_vars/monitoring/vars.yml`. Then repeat with `-e ntfy_enabled=true`, copy the rendered file from the diff to the monitoring LXC, and confirm it passes `docker exec alertmanager amtool check-config <file>`
- [ ] T033 [US1] Deploy T028/T029 to PROD ntfy, then POST synthetic Alertmanager v4 payloads directly to `https://ntfy.hus-sky.no/alerts?template=homelab-alertmanager` with the alertmanager token. Send one payload per row of the data-model mapping table (5 rows), plus a 10-alert group with long descriptions and a payload whose `truncatedAlerts` is 3. Expected: titles and priorities exactly as tabled, `(+3 more)` shown, and no 413 in `docker logs ntfy` (research R-003, R-004). Keep the payloads in `specs/082-ntfy-push-service/drills/payloads/` for reuse
- [ ] T034 [US1] Set `ntfy_enabled: true` (T030) and deploy monitoring through the prod promote path (expect the LAB monitoring gate to refuse; see the Environments note). Confirm `/api/v2/status` on Alertmanager shows the config loaded
- [ ] T035 [US1] On the monitoring LXC, use `amtool alert add` to fire `TestNtfyCritical` (critical), `TestNtfyWarning` (warning) and `TestNtfyInfo` (info), then expire them. Expected: each arrives on **both** Pushover and ntfy, and the resolutions arrive on both, with ntfy priorities as tabled (spec US-1 scenarios 1–4, quickstart § 3)

**Checkpoint**: US1 is complete. Alerts are dual-delivered.

---

## Phase 5: User Story 3 — The phone keeps receiving away from home (Priority: P1)

**Goal**: Messages reach the phone on mobile data without opening the app, including after an idle
night and after a tailnet gap shorter than 72 h.

**Independent Test**: With Wi-Fi off and Tailscale on, send a test message and it arrives. With
Tailscale off, send another; it arrives after reconnect. Repeat after a night idle (spec US-3).

- [X] T036 [P] [US3] Write `docs/runbooks/ntfy-phone-setup.md` (FR-015). Cover: install the ntfy Android app (Play or F-Droid); Settings → default server `https://ntfy.hus-sky.no`; Settings → Manage users → add `owner` and the password from the password manager; subscribe to `alerts` and `hermes`; per topic, check "instant delivery" is on; set the `alerts` notification channel for urgent priority to override Do Not Disturb if wanted; Android battery optimisation → ntfy → Unrestricted; Tailscale → Always-on VPN. Also describe what a 72 h gap means (FR-013) and how to check reach (`/v1/health` in the phone browser)
- [ ] T037 [US3] Follow the runbook on the owner's phone, then run quickstart § 4 steps 1–5: reach check, app-closed delivery, a Tailscale-off gap followed by reconnect, an overnight idle test (SC-005), and per-severity delivery on mobile data within 60 s (SC-001). Record times in `specs/082-ntfy-push-service/drills/phone-delivery.md`

**Checkpoint**: US3 is complete.

---

## Phase 6: User Story 4 — The service is on the front page and its state is honest (Priority: P2)

**Goal**: An ntfy card with a truthful liveness indicator, and an outage alert that never depends
on ntfy itself.

**Independent Test**: The front page shows the ntfy card. Stopping the container turns it red
(spec US-4).

- [X] T038 [US4] Add `monitoring_contract` to `ansible/host_vars/ntfy.yml`, exactly as in contracts/monitoring-contract.md: scrape job `ntfy` on port `"{{ ntfy_metrics_port }}"`, path `/metrics`; liveness job `ntfy-health` on `https://ntfy.{{ caddy_base_domain }}/v1/health` with `http_2xx`; rule `NtfyDown` (`probe_success{job="ntfy-health"} == 0`, `for: "5m"`, `severity: critical`, `!unsafe` summary and description). The description states that it is routed to Pushover and that the ntfy copy is expected to fail
- [ ] T039 [US4] Deploy reverse proxy and monitoring through the prod path. Confirm that `https://hus-sky.no` shows the ntfy card as `up` and that Prometheus `/targets` lists `ntfy` and `ntfy-health` as UP, with no pre-existing job missing (compare the active target and rule-group counts before and after, as in `065`)
- [ ] T040 [US4] Failure drill (quickstart § 5, SC-003, R-005). Fire a critical test alert with ntfy up and record the Pushover delivery time. Run `docker stop ntfy` on the ntfy LXC and fire another critical test alert; Pushover time must match the baseline. Wait more than 5 min: the card shows `down` and `NtfyDown` arrives on Pushover. Run `docker start ntfy`: the resolution arrives on Pushover, the card shows `up`, and the delayed ntfy copies arrive. Record the results in `specs/082-ntfy-push-service/drills/failure-independence.md`. **If Pushover was delayed**, apply the R-005 fallback: move the webhook to a separate `ntfy` receiver on a `continue: true` sibling route in `alertmanager.yml.j2`, then repeat this task

**Checkpoint**: All four user stories are complete.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T041 Rebuild drill (SC-004, FR-014, quickstart § 6): destroy and recreate the ntfy LXC through the normal lifecycle path, then run `ansible/playbooks/ntfy.yml` with no manual step. Then T025 must pass and a test publish must reach the already-subscribed phone. Record the result in `specs/082-ntfy-push-service/drills/rebuild.md`
- [X] T042 [P] Update `docs/backlog/082-ntfy-push-service.md` status to "Specced → `specs/082-ntfy-push-service/`", and update its row in `docs/backlog/backlog.md`. Answer the backlog's two open questions in place (priority: custom template, R-003; cache: 72 h, FR-013)
- [X] T043 [P] Add an `ntfy-lxc` entry to the authoritative service list in `specs/002-core-services-lxc/spec.md` (constitution § Services Model), in the same style as the existing `hermes-lxc` entry. It should say: ntfy, the estate's push channel to the owner's phone, at `192.168.1.222`, LAN/tailnet only, with state on local disk and no backup by design (FR-014), spec `082`
- [X] T044 Record the 4-week trial start date (the date T035 passed) at the top of `specs/082-ntfy-push-service/trial-report.md`. Add a skeleton table (alert, fired at, Pushover at, ntfy at, missed/late/duplicate) for SC-006. The write-up itself is due at the end of the window and is not a blocker for merging — skeleton created; start date to be filled in after T035 passes
- [ ] T045 Final review: compare `git diff main --stat` with the plan.md Source Code tree (no unplanned files, nothing secret in the diff, `vault.yml` still encrypted), and open the PR with `gh pr create`, ending the body with the attribution line

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)**: none. T002 (vault) blocks T016 at deploy time, not at authoring time.
- **Foundational (Phase 2)**: depends on Setup. T010 depends on T004, T006–T008. T016 depends on
  T011–T015. T021 depends on everything before it. T023 depends on T020 and T021.
- **US2 (Phase 3)**: depends on T023 (PROD) for the PROD half of T025 and T026. The LAB half of
  T025 only needs T021.
- **US1 (Phase 4)**: depends on Foundational. It is independent of US2 in code; T024 is useful
  but not required. T029 depends on T028. T033 depends on T029. T034 depends on T031–T033.
- **US3 (Phase 5)**: depends on Foundational. T037 is most informative after US1 and US2, since
  both topics then have traffic.
- **US4 (Phase 6)**: depends on Foundational (T020 already created the card). T040 needs US1's
  T034 (dual delivery live) to test independence.
- **Polish (Phase 7)**: T041 after all stories. T042, T043 and T044 at any time after T035.

### Story independence

| Story | Can ship without | Needs |
|---|---|---|
| US2 | US1, US3, US4 | Foundational |
| US1 | US2, US3 | Foundational |
| US3 | US1, US4 | Foundational (any topic with a message) |
| US4 | US2, US3 | Foundational. T040 additionally needs US1 |

---

## Parallel Execution Examples

**Phase 1**: T003, T004 and T005 touch different files and can run together after T001.

**Phase 2 authoring** (all different files, no inter-dependencies):

```text
T006 terraform/services/ntfy/main.tf
T007 terraform/services/ntfy/outputs.tf
T008 scripts/lab/service-scope-allowlist.json
T009 .github/workflows/*.yml
T011 roles/ntfy/defaults/main.yml
T012 roles/ntfy/templates/server.yml.j2
T013 roles/ntfy/templates/docker-compose.yml.j2
T014 roles/ntfy/tasks/preflight.yml
T015 roles/ntfy/handlers/main.yml
T017 playbooks/ntfy.yml
T018 host_vars/ntfy.yml
T019 scripts/healthcheck/ntfy.sh
```

Then T016 and T020 run in sequence, followed by the deploy tasks T021–T023.

**Across stories** once Foundational is done: T024 (US2 script), T028 (US1 template) and T036 (US3
runbook) are separate files and can be written in parallel. T027 and T036 are pure documentation.

---

## Implementation Strategy

### MVP (US2 + Foundational)

Phases 1–3 deliver a locked-down ntfy that any estate job can publish to. That alone unblocks
`083`, and SC-002 is proven by script. Stop and validate at the Phase 3 checkpoint.

### Incremental delivery

1. **+US1**: dual-delivered alerts (stage it with `ntfy_enabled` false → true).
2. **+US3**: phone setup and away-from-home proof.
3. **+US4**: monitoring contract, then the failure-independence drill. This is the last gate before
   ntfy can be trusted next to Pushover.
4. **Polish**: rebuild drill, docs, then start the trial clock.

### Notes

- The six vault secrets are the only manual input. Everything else is re-applied from config on
  every deploy.
- Do not enable `ntfy_enabled` on PROD before T033 has shown that the template renders correctly.
  A broken template would put malformed alerts on the phone for the whole trial window.
- If backlog `081` (externalise topology) lands before this merges, move T003, T004 and T005 to
  wherever it puts addresses (spec Dependencies).

---

## Phase 8: Convergence

- [X] T046 Rewrite `ansible/roles/ntfy/files/homelab-alertmanager.yml` as a valid YAML file whose `title`, `message` and `priority` keys are each a block-scalar Go template (ntfy parses the file as YAML first and executes each key separately, so variables cannot be shared between keys and the leading `{{/* */}}` comment must go or become a `#` comment). Use the raw Alertmanager JSON keys (`.status`, `.commonLabels.severity`, `.groupLabels.alertname`, `.truncatedAlerts`, `.alerts`, `.annotations.summary`), not Go-struct casing (`.Status`, `.CommonLabels`). Compare `.truncatedAlerts` against `0.0` because JSON numbers are float64. Keep the data-model.md § "Alert → notification mapping" table exact, and recheck it with T033 per US1/AC1–AC4, T028 (contradicts)
- [X] T047 Render `auth-users`, `auth-access` and `auth-tokens` in `ansible/roles/ntfy/templates/server.yml.j2` as YAML **lists** of quoted strings (`- "owner:<hash>:user"`), as in the ntfy config docs, instead of `|` block scalars. A block scalar is one string, so no publisher is provisioned and every authenticated request fails. Verify by rendering the template and loading it with a YAML parser per FR-005, FR-006, FR-007, US2/AC1 (contradicts)
- [X] T048 Change the `NtfyDown` rule in `ansible/host_vars/ntfy.yml` to the flat shape that `ansible/roles/monitoring_stack/templates/service_alerts.yml.j2` reads (`severity:`, `summary: !unsafe …`, `description: !unsafe …` at the rule's top level, as in `ansible/host_vars/hermes.yml`). Drop `labels:` and `annotations:`. As written, `rule.severity` is undefined and the monitoring render fails for every service. Confirm with `ansible-playbook ansible/playbooks/monitoring.yml --check --diff --limit monitoring` per FR-011, US4/AC2, T038 (contradicts)
- [X] T049 Fix `scripts/healthcheck/ntfy-acl-check.sh` per SC-002 and T024 (contradicts). Reads must use `GET ${NTFY_URL}/<topic>/json?poll=1&since=1m`, because `GET /<topic>` serves the web app with a 200 to anyone and would fail the `none`/publisher read cells. Send the `-d` body, `Tags` and `Priority` only for POST, built in a bash array rather than through the unquoted `${method:+-d "…"}`, which is always set and splits the date into an extra URL argument. Check with `bash -n` and `shellcheck`
- [X] T050 In `ansible/roles/ntfy/tasks/main.yml`, replace `content | b64decode | search(item) is not matched` with the Jinja test form `(… | b64decode) is not search(item)`; `search` is a test, not a filter, so the current task errors on every run. Move the forbidden-key check before "Ensure ntfy stack is running", so that a forbidden key fails the deploy before ntfy starts with it, per FR-004 and contracts/server-config.md § Forbidden (contradicts)
- [X] T051 In `ansible/roles/ntfy/tasks/preflight.yml`, make the "six vault secrets" assert actually catch undefined vars. `default(omit)` turns an undefined var into a non-empty placeholder, so the assert passes and the next task fails with a raw undefined-variable error. Assert `vars[item] is defined and vars[item] | length > 0` over the variable *names* instead, per T014 (partial)
- [X] T052 Bind the published ports in `ansible/roles/ntfy/templates/docker-compose.yml.j2` to `{{ ntfy_ip }}` (`"{{ ntfy_ip }}:{{ ntfy_port }}:80"`, same for metrics), or reword contracts/server-config.md § Compose shape so it matches what is implemented. Choose the binding only if the health wait on `127.0.0.1` in `tasks/main.yml` is moved to `{{ ntfy_ip }}` at the same time, per contracts/server-config.md (partial)
