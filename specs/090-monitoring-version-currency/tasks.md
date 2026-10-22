---
description: "Task list for 090 monitoring stack version currency"
---

# Tasks: Monitoring Stack Version Currency

**Input**: Design documents from `/specs/090-monitoring-version-currency/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/currency-check.md](./contracts/currency-check.md),
[quickstart.md](./quickstart.md)

**Tests**: The spec requires one guard test (FR-017). The constitution's test-driven rule asks for
unit tests where feasible, and the currency module is pure logic over HTTP responses. So the guard
test is written first (Phase 2) and must fail first. The module's unit tests are written before the
module (Phase 7). Everything else is static checks plus the live checks in `quickstart.md`.

**Organization**: one phase per user story, in spec priority order. US1 is split into a code and
rehearsal phase (3) and a production rollout phase (5), because the rollout needs US2's snapshot
(phase 4). Taking the snapshot right before the deploy keeps the rollback point fresh.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1–US4, from spec.md
- Paths are repo-relative. Ansible commands run from `ansible/` unless stated.

## Path Conventions

- Ansible: `ansible/group_vars/`, `ansible/roles/`, `ansible/playbooks/`
- Python: `python/src/homelab_proxmox_orchestrator/`, `python/tests/`
- Workflows: `.github/workflows/`
- Operator docs: `docs/operations/monitoring/`
- Live results: the tables in `specs/090-monitoring-version-currency/quickstart.md`
- Where live commands run:
  - `ssh root@192.168.1.214` (monitoring LXC) and `pve` root commands run from an operator machine
    on the LAN.
  - The dev Mac cannot reach Docker Hub, the tailnet, or `git push` (Zscaler; see `AGENTS.md`).
  - Pipeline deploys are `gh workflow run`, which works from the Mac.
- **Secrets**: the agent never reads, prints or generates vault values. Tasks that need a secret
  value (T024) are operator steps, and the agent stops and asks.

---

## Phase 1: Setup

**Purpose**: a known baseline and current upstream facts.

- [x] T001 Create the branch `090-monitoring-version-currency` from `origin/main`:
  `git fetch origin main && git switch -c 090-monitoring-version-currency origin/main`. If it
  already exists, switch to it and confirm it contains `origin/main`.
  - Then, from `ansible/`, run `ansible-playbook playbooks/monitoring.yml --syntax-check`.
  - From the repo root, run `.venv/bin/python -m pytest -c python/pytest.ini --no-cov
    python/tests/guardrails`.
  - Record in `specs/090-monitoring-version-currency/quickstart.md` §0 that both pass before
    any change. If either fails, record the pre-existing failure there.
  - Make sure `.venv/bin/python -c 'import yaml'` works. If it does not, run
    `uv pip sync --python .venv/bin/python --require-hashes python/requirements-test.lock.txt`.
  - Do **not** stage `.specify/feature.json`. It is a protected path (`.specify/**`), and
    committing it would trip CI's protected-path guardrail (`AGENTS.md`).
- [x] T002 Re-check upstream versions, because the targets were fixed on 2026-10-22.
  - Run `gh api repos/<repo>/releases?per_page=10 --jq '.[]|"\(.tag_name) \(.prerelease)"' </dev/null`
    for `grafana/grafana`, `prometheus/prometheus`, `prometheus/alertmanager`,
    `prometheus/blackbox_exporter`, `influxdata/telegraf` and `prometheus/node_exporter`.
  - Run `curl -s https://endoflife.date/api/{grafana,prometheus,telegraf}.json`.
  - If there is a newer **patch on the same line** as a target in research R-01, use it: update
    the R-01 table in `specs/090-monitoring-version-currency/research.md`, and every literal
    version in `quickstart.md` §1, §3 and §9. Do not move to a new line (R-01).
  - If 3.13 is no longer the newest Prometheus LTS line, stop and ask the owner.

---

## Phase 2: Foundational (guard test first)

**Purpose**: the automated guard required by FR-017. It is written before the changes so it is
seen to fail.

- [x] T003 Create `python/tests/guardrails/test_version_pins.py`, modelled on
  `python/tests/guardrails/test_backup_log_rotation_config.py`. Use the same `_find_repo_root`
  helper, `from __future__ import annotations`, `pathlib` and `yaml.safe_load`. Write these
  functions, each with a docstring naming its requirement:
  1. `test_monitoring_pins_assigned_once` (FR-005, SC-004). For each of `prometheus_version`,
     `grafana_version`, `telegraf_version`, `alertmanager_version`,
     `blackbox_exporter_version` and `node_exporter_version`:
     - scan every `*.yml` and `*.yaml` under `ansible/` (skip `ansible/roles/geerlingguy.*`)
       for lines matching `^\s*<var>:\s` that are not comments;
     - assert exactly one match;
     - assert the five monitoring vars are in `ansible/group_vars/monitoring/vars.yml`, and
       `node_exporter_version` is in `ansible/group_vars/all/vars.yml`.
  2. `test_monitoring_role_defaults_have_no_versions` (FR-005, research R-04): load
     `ansible/roles/monitoring_stack/defaults/main.yml` and
     `ansible/roles/node_exporter/defaults/main.yml`, and assert neither defines any key ending in
     `_version`.
  3. `test_every_pin_has_a_source` (FR-014, FR-017, data-model §2).
     - Collect the pins:
       - every key ending in `_version` in `ansible/group_vars/monitoring/vars.yml`;
       - `node_exporter_version` from `ansible/group_vars/all/vars.yml`;
       - from `ansible/group_vars/services/vars.yml`, the keys in the text block from the line
         `# Service versions` to the next blank line, matched with `^([a-z0-9_]+):`. That is 14
         keys today, including `immich_postgres_image` and `immich_redis_image`.
     - Load `ansible/version-sources.yml` → `pins` list, and assert:
       - every collected pin has exactly one entry, and there are no entries for unknown
         variables;
       - each entry's `file` exists and assigns its `variable`;
       - `policy` is one of `lts`, `latest`, `support-only`, `unchecked`;
       - `github` is present for `lts` and `latest`;
       - `endoflife` is present for `lts` and `support-only`;
       - `reason` is a non-empty string for `unchecked`.
  4. `test_version_currency_workflow` (FR-013, FR-013a, contract §2): load
     `.github/workflows/version-currency.yml` with `yaml.safe_load`. Note: PyYAML parses the key
     `on` as `True`, so read `data.get("on", data.get(True))`. Assert:
     - `schedule[0].cron == "0 6 * * 1"`;
     - `workflow_dispatch.inputs.dry_run.type == "boolean"`;
     - the single job has `runs-on` containing `self-hosted` and `timeout-minutes == 10`;
     - `permissions == {"contents": "read"}` (top-level or job-level).
  5. `test_monitoring_validates_before_compose_up` (FR-008, research R-05): load
     `ansible/roles/monitoring_stack/tasks/compose_stack.yml`. Assert that a task including
     `validate_alerts.yml` comes before the task named `Start monitoring stack`. Read
     `ansible/roles/monitoring_stack/tasks/validate_alerts.yml` as text and assert it contains
     `promtool`, `check config`, `amtool` and `check-config`. Assert
     `ansible/roles/monitoring_stack/tasks/main.yml` no longer includes `validate_alerts.yml`
     directly, so it runs once.

  Run `.venv/bin/python -m pytest -c python/pytest.ini --no-cov
  python/tests/guardrails/test_version_pins.py`. Confirm all five **fail**, each for its expected
  reason. Do not mark this task done until you have seen them fail.

**Checkpoint**: the guard exists and is red. Test 5 turns green in US1, tests 1–2 in US3, and
tests 3–4 in US4.

---

## Phase 3: User Story 1 — Supported versions, nothing lost (Priority: P1) — code and rehearsal

**Goal**: the new pins and pre-restart validation exist on the branch, and the risky parts are
proven on the live host without touching the running stack (FR-001 to FR-004, FR-006, FR-008,
research R-05, R-06).

**Independent Test**: guard test 5 passes, and the syntax check and lint are clean. Quickstart §1–§3
are recorded with no missing tag, both validators passing, and Grafana 13.2 migrating and listing
all 8 dashboards.

### Implementation for User Story 1

- [x] T004 [US1] In `ansible/group_vars/monitoring/vars.yml`, raise the pins to the R-01 targets
  (as confirmed in T002):
  - `prometheus_version: "v3.13.5"`, `grafana_version: "13.2.4"`, `telegraf_version: "1.40.2"`,
    `alertmanager_version: "v0.34.1"`;
  - `blackbox_exporter_version: "v0.29.1"`, which stays where it is in the file for now (T019 moves
    it).

  Replace each trailing comment with `# Upgraded from <old> (2026-10-22, spec 090)`. Keep the
  format: `v` prefix for `prom/*` images, none for Grafana and Telegraf.
- [x] T005 [P] [US1] In `ansible/roles/node_exporter/defaults/main.yml`, set
  `node_exporter_version: "1.12.1"` (no `v`; the download URL adds it). T020 moves this line later.
- [x] T006 [US1] Extend `ansible/roles/monitoring_stack/tasks/validate_alerts.yml` (research R-05).
  Keep the existing `find` and the per-file `promtool check rules` loop, and add two tasks after
  them:
  - `Validate Prometheus configuration with promtool`:
    `docker run --rm --entrypoint promtool -v {{ prometheus_config_path }}:/etc/prometheus:ro prom/prometheus:{{ prometheus_version }} check config /etc/prometheus/prometheus.yml`.
  - `Validate Alertmanager configuration with amtool`:
    `docker run --rm --entrypoint amtool -v {{ alertmanager_config_path }}:/etc/alertmanager:ro prom/alertmanager:{{ alertmanager_version }} check-config /etc/alertmanager/alertmanager.yml`.

  Both tasks use `changed_when: false`, `register` and `failed_when: <result>.rc != 0`. The amtool
  task also sets `no_log: true` (the file contains SMTP, Pushover and ntfy credentials). Add a
  follow-up `ansible.builtin.fail` task, `when: <result>.rc != 0`, whose `msg` shows only `rc` and
  `stderr_lines` with lines containing `secret`, `password` or `token` filtered out. Update the
  header comment to say the validation runs before the stack restarts, and cite spec 090 FR-008.
- [x] T007 [US1] Move the validation before the restart (research R-05).
  - In `ansible/roles/monitoring_stack/tasks/compose_stack.yml`, insert immediately before the
    `Start monitoring stack` task:
    ```yaml
    - name: Validate rendered configuration before (re)starting the stack
      ansible.builtin.include_tasks: validate_alerts.yml
    ```
  - In `ansible/roles/monitoring_stack/tasks/main.yml`, delete the `Validate alert rule syntax`
    include, so it runs once.

  The `docker run` validators pull the target images, so a missing tag fails here, before
  `up -d`, while the old containers are still running.
- [x] T008 [US1] Static checks. From `ansible/`:
  - run `ansible-playbook playbooks/monitoring.yml --syntax-check`;
  - run `ansible-lint roles/monitoring_stack roles/node_exporter group_vars/monitoring/vars.yml`;
  - run guard test 5 (`-k validates_before_compose_up`) and confirm it now **passes**.

  Fix any new lint findings in the touched files only. Record the results in quickstart §0.
- [x] T009 [US1] Live, from the operator machine: run quickstart §1 (pull the five target tags on
  the monitoring LXC). Record "no MISSING" or the missing tag. If a tag is missing, stop and
  re-check T002.
- [x] T010 [US1] Live: run quickstart §2 (before snapshot) on the monitoring LXC. Pass the Grafana
  admin password as `GF_PW` through the environment, taken from
  `ansible/group_vars/monitoring/vault.yml` by the operator, and never echo it. Fill in the §2
  table: targets up/total, rule count, dashboard count (expect 8). Keep `/root/090/*.before.json`
  on the host.
- [x] T011 [US1] Live: run quickstart §3 (side-by-side rehearsal).
  - First confirm the real volume and network names with `docker volume ls` and
    `docker network ls`, and use them in place of `monitoring_grafana_data` and
    `monitoring_default`.
  - Fill in the §3 table: promtool, amtool, Grafana migration log, dashboards listed and opened
    without panel errors (x / 8).
  - Clean up the rehearsal container and volume.
  - If Grafana 13.2 fails and the cause cannot be fixed in this feature, record why in §3. Change
    `grafana_version` in `ansible/group_vars/monitoring/vars.yml` to the latest `12.4.x` (spec
    FR-001), and repeat this task with that image. If it is fixable, add a follow-up task here
    and do not mark this one done.

- [x] T012 [US1] Commit the work so far: T003–T008, plus T013 (runbook) and T018–T022 (US3) if
  already done, and the quickstart and research edits. Do not commit `.specify/feature.json`.
  - Push the branch through the GitHub Git-Data API as described in `AGENTS.md`. `git push` is
    blocked; run the first `gh api` call in the background because of the ~2-minute cold-TLS
    stall.
  - Verify that the local `HEAD^{tree}` equals the remote tree SHA.
  - Realign with `git fetch origin 090-monitoring-version-currency && git reset --hard origin/090-monitoring-version-currency`.
  - Open a draft PR to `main` with `gh api repos/OWNER/REPO/pulls --input pr.json`
    (`"draft": true`). No protected paths are touched, so no label is needed.
  - Confirm PR CI is green. Guard test 5 passes now. Guard tests 1–2 pass only if US3 is in this
    push; tests 3–4 stay red until US4. If red guard tests block CI, mark **only the tests that
    are red at push time** with `pytest.mark.xfail(strict=True, reason="090 US3/US4 pending")`.
    A strict xfail on a test that already passes fails the run. Remove the markers in T022 and
    T030.

**Checkpoint**: the branch carries the new pins and validation, and the rehearsal shows the upgrade
is safe. The production deploy waits for US2.

---

## Phase 4: User Story 2 — Failed upgrade can be undone (Priority: P1)

**Goal**: a fresh rollback point and written rollback steps exist before the production deploy
(FR-011, research R-02, R-07).

**Independent Test**: `pct listsnapshot <vmid>` shows `pre-090`. Quickstart §4 lists the VMID, the
snapshot time and the six previous pins. The runbook's rollback section says a Grafana pin revert
is not a rollback.

### Implementation for User Story 2

- [x] T013 [P] [US2] In `docs/operations/monitoring/runbook-upgrades.md`, rewrite three sections:
  - "1. Create Pre-Upgrade Backup": the rollback point is `pct snapshot <vmid> pre-<change>` as
    root on `pve`, with the VMID from `pct list`. The in-guest `backup-monitoring.sh` is not
    relied on, because the monitoring backup is broken until `091`.
  - "Rollback Procedure": "Option 1 Revert Version Pins" applies **only** to components without
    migrating state. State explicitly that Grafana 12.4 and later migrates dashboard storage one
    way on first start, so after a Grafana upgrade the rollback is `pct rollback <vmid> pre-<change>`
    plus reverting the pins on the branch (research R-02).
  - Add a closing step: `pct delsnapshot` once verified.

  Leave the "Update Version Pins" section for T021 (same file; do T013 first).
- [x] T014 [US2] Live, as root on `pve`, after T012's PR CI is green and immediately before T015:
  run quickstart §4 (take the `pre-090` snapshot). Nothing else should happen between this task
  and T015, because anything written after the snapshot is lost on rollback. Fill in the §4 row (VMID, snapshot, time taken in UTC) and confirm the
  previous-pins line matches the values T004 and T005 replaced.

**Checkpoint**: a fresh rollback point exists. Production deploy may proceed.

---

## Phase 5: User Story 1 — Supported versions, nothing lost (Priority: P1) — production rollout

**Goal**: production runs the new versions with an identical set of targets, rules and
dashboards, working alert delivery, and history kept (FR-004, FR-007, FR-009, FR-010, SC-001 to
SC-003, SC-007).

**Independent Test**: the quickstart §6 table is complete, with zero diffs, all 8 dashboards free
of panel errors, history queryable, and the test alert on both channels within 5 minutes. The
quickstart §7 table shows every LXC on the new node_exporter.

### Implementation for User Story 1 (rollout)

- [x] T015 [US1] Live: production deploy of `monitoring` from the branch (quickstart §5). Run
  `gh workflow run lxc-promote-prod.yml -f ref=090-monitoring-version-currency -f service=monitoring -f allow_override_failed_lab_gate=true`.
  After it passes and is approved, run `lxc-apply-prod.yml` with `-f promotion_run_id=<promote run id>
  -f allow_override_failed_lab_gate=true -f confirm_apply_prod=deploy-prod` (the apply takes the
  promote run's id, not a service or branch). Confirm in the
  run log that the three validators ran **before** `Start monitoring stack`, and that `verify.yml`
  passed. If a validator fails, the old stack is still running: fix it on the branch and
  re-run. Do not roll back.
- [x] T016 [US1] Live: run quickstart §6 (after snapshot and comparison).
  - Fill in the §6 table: running versions (SC-001); the three diffs (only `health` changes on
    targets that were already down before are allowed); 8 dashboards open at
    `https://grafana.hus-sky.no` without panel errors; the history query pinned to the deploy
    time recorded in §5 (`count(count_over_time(up[1h] @ <DEPLOY_EPOCH - 300>))`) returns a value
    above 0 (FR-010). This query is valid at any time after the deploy, unlike a relative offset;
    that holds for as long as the data stays within the 15-day retention; the `Test090` warning alert received on **both** Pushover and ntfy within
    5 minutes (SC-003; the owner confirms Pushover).
  - On any blocking difference, run the rollback in §6 (`pct rollback`, then revert the pins on
    the branch), record what happened, and stop.
- [ ] T017 [US1] Live: node_exporter rollout (quickstart §7, SC-007). For each LXC in the §7 table
  except `monitoring` (already done in T015), one at a time:
  - run the normal prod deploy from the branch (`lxc-promote-prod`, then `lxc-apply-prod`,
    `-f service=<host>`), which applies `lxc_base` → `node_exporter`;
  - confirm `/usr/local/bin/node_exporter --version` shows `1.12.1`;
  - fill in the row.

  This is done when `count by (version) (node_exporter_build_info)` returns only `1.12.1`. If a
  service is mid-change elsewhere, skip it and note the date it will be picked up. The task stays
  open until every row is filled in.

  **Guard for the `ntfy` host**: a deploy from the branch carries every commit on it. If T025
  (the `version_check` entry in `ntfy_users`) is on the branch, deploy `ntfy` only after T024
  (vault keys present). Otherwise the ntfy role renders undefined variables. Before deploying
  `ntfy`, check `git log origin/090-monitoring-version-currency -- ansible/roles/ntfy/defaults/main.yml`.
  If T025 is there and T024 is not done, skip `ntfy` here. It gets node_exporter 1.12.1 from
  T032's ntfy deploy instead; record that in its row.

**Checkpoint**: US1 is complete. SC-001 to SC-003 and SC-007 are met.

---

## Phase 6: User Story 3 — Each version is defined in one place (Priority: P2)

**Goal**: one assignment per monitoring pin, no dead role-default copies, and a runbook that points
at the real pins (FR-005, SC-004, research R-04).

**Independent Test**: guard tests 1–2 pass. The `rg` in quickstart §0 shows exactly six lines. The
monitoring playbook syntax-checks and renders the same images.

### Implementation for User Story 3

- [x] T018 [US3] In `ansible/roles/monitoring_stack/defaults/main.yml`, delete the
  `# Service versions …` comment block and the four `*_version` lines (current lines 5–11). Also
  delete `blackbox_exporter_version` (current line 58), keeping `blackbox_exporter_port` and
  `blackbox_config_path`. Leave no placeholder or comment. This follows the precedent in
  `docs/backlog/consolidate-service-versions.md`.
- [x] T019 [US3] In `ansible/group_vars/monitoring/vars.yml`, move `blackbox_exporter_version`
  (with its value from T004) out of the `# Blackbox exporter configuration` section into the
  `# Service versions` block at the top, after `alertmanager_version`. The block's five lines
  are the only monitoring pins.
- [x] T020 [US3] Move `node_exporter_version` out of `ansible/roles/node_exporter/defaults/main.yml`
  and delete the line there. Add it to `ansible/group_vars/all/vars.yml`, after the address block,
  as:
  ```yaml
  # node_exporter on every LXC (role node_exporter via lxc_base). Single pin (spec 090).
  node_exporter_version: "1.12.1"
  ```
  Confirm nothing else references the role default: `rg -n node_exporter_version ansible`
  should show the role's task file and this one assignment.
- [x] T021 [US3] In `docs/operations/monitoring/runbook-upgrades.md` (after T013), rewrite
  "2. Update Version Pins":
  - edit `ansible/group_vars/monitoring/vars.yml` (the block at the top) for the five monitoring
    components, and `ansible/group_vars/all/vars.yml` for node_exporter;
  - **never** edit role defaults, which no longer hold versions;
  - deploy through the prod path (`lxc-promote-prod`, then `lxc-apply-prod`, with
    `allow_override_failed_lab_gate=true`), not `ansible-playbook` against the host and not the
    lab path (`072`).

  Replace the stale SNMP Exporter references in the release-notes links and §5 verification with
  Telegraf and blackbox_exporter.
- [x] T022 [US3] Static checks: run `ansible-playbook playbooks/monitoring.yml --syntax-check`,
  then `ansible-lint` on the touched files. Run guard tests 1–2 and confirm they now pass; remove
  their `xfail` markers if T012 added them. Run
  `rg -n '^(prometheus|grafana|telegraf|alertmanager|blackbox_exporter|node_exporter)_version:' ansible/`
  and confirm exactly six lines. Record the results in quickstart §0. The rendered output is
  unchanged, because the values are identical and only their location moved, so no redeploy is
  needed.

**Checkpoint**: US3 is complete. SC-004 is met.

---

## Phase 7: User Story 4 — Pins that fall behind are reported (Priority: P2)

**Goal**: a weekly, stateless check posts to ntfy `versions` when a pin is behind or its support
is ending. It stays silent when everything is current, and fails visibly on errors (FR-013 to
FR-015, FR-013a, SC-005, SC-006, research R-08 to R-13).

**Independent Test**: the unit tests pass and guard tests 3–4 pass. A `--dry-run` lists no monitoring
pin. A manual run on a branch with `grafana_version` lowered posts a `grafana_version` line to
`versions`. An unreachable source fails the run.

### Tests for User Story 4 (write first, see them fail)

- [x] T023 [P] [US4] Create `python/tests/version_currency/test_version_currency.py`. Import from
  `homelab_proxmox_orchestrator.version_currency`. Fake every HTTP call by passing a fetch
  function or monkeypatching the module's single `_http_get_json(url, token)` and
  `_http_post(url, body, headers)` helpers: no network. Fix `today` by injection. Cases:
  1. `parse_tag` handles `v3.13.5`, `3.13.5`, `13.2.4`, `v1.83.3-stable`, `v9.3.4-hotfix.1`
     → numeric cores `(3,13,5)`, `(13,2,4)`, `(1,83,3)`, `(9,3,4)`. It returns `None` for
     `2026.9.19-c0014f015`.
  2. Pre-releases are excluded: GitHub `prerelease: true`, and tags containing `-rc`, `-beta`,
     `-alpha` (for example `v9.3.6-rc.1`, `v3.15.0-rc.0`).
  3. `lts` policy with pin `v3.13.5`. LTS line 3.13 has latest `3.13.5` and eol `2027-07-31`, and
     a non-LTS `3.15.1` exists → **no finding**. With `v3.13.6` released → `newer-patch`. With a
     new LTS line `3.17` → `newer-lts-line`. With `today` 20 days before eol → `support-ending`.
     After eol → `support-ended`.
  4. `latest` policy: Grafana `13.2.4`, with releases `v13.2.4`, `v13.1.8`, `v12.4.13` → no
     finding. `v13.3.0` added → `newer-release`. An unordered release list, like Prometheus's
     same-day `v3.15.1` and `v3.13.5`, is still sorted correctly.
  5. `support-only` policy: Nextcloud `"34"` with cycle `34` eol in the past → `support-ended`.
     With eol `false` → no finding.
  6. `unchecked` entries never produce findings and appear in `report.unchecked` with their
     reason.
  7. All current and no errors → `main(["--dry-run"])` prints nothing to publish and returns `0`.
     With `NTFY_TOKEN` set, it does **not** call `_http_post` (FR-015).
  8. Findings plus a successful publish → returns `0`. Assert the POST URL is
     `{NTFY_URL}/{NTFY_TOPIC}`, there is an `Authorization: Bearer <token>` header, and the
     `Title` is `Version pins: <F> behind`. Assert the body lines match contract §4: monitoring
     pins first, the `Not checked:` line, and that the token does not appear in the body.
  9. A source raising a timeout or URL error → that pin is under `Check errors` and not reported
     as current. The exit code is `1`, and `Title` includes `check errors`. The publish is still
     attempted.
  10. Publish returns 403, or raises a connection error → exit code `1`.
  11. Bad input → exit code `2`: unknown policy, a missing `file`, a `variable` not found in its
      file, or a missing `NTFY_TOKEN` without `--dry-run`.
  12. Priority header: `4` when any `support-ended` finding or error exists, else `3`.

  Run `.venv/bin/python -m pytest -c python/pytest.ini --no-cov python/tests/version_currency`
  and confirm they fail (the module does not exist yet).

### Implementation for User Story 4

- [x] T024 [US4] **Operator step.** Stop and ask the owner to create the ntfy publisher
  credentials (082 contract onboarding; generation commands as in 082 quickstart):
  - a token from `docker run --rm binwiederhier/ntfy:<ntfy_version> token generate`;
  - a password hash from `docker run --rm -it binwiederhier/ntfy:<ntfy_version> user hash`, with a
    random, discarded password.

  The owner adds them with `ansible-vault edit ansible/group_vars/services/vault.yml` as
  `ntfy_version_check_token` and `ntfy_version_check_password_hash`. The agent does not see the
  values. Afterwards, confirm only that both keys exist:
  `ansible-vault view … | grep -c '^ntfy_version_check_'` should print `2`, run by the owner.
- [x] T025 [P] [US4] In `ansible/roles/ntfy/defaults/main.yml`, append to `ntfy_users`:
  ```yaml
  - name: "version_check"
    topic: "versions"
    password_hash: "{{ ntfy_version_check_password_hash }}"
    token: "{{ ntfy_version_check_token }}"
  ```
  Check `roles/ntfy/tasks/preflight.yml` and the ACL template for any hard-coded list of publishers
  or topics, and extend them in the same way if needed. The ACL must be write-only on `versions`.
- [x] T026 [P] [US4] In `scripts/healthcheck/ntfy-acl-check.sh`, add the `version_check` account
  following the `pve_backup` pattern:
  - a `NTFY_VERSION_CHECK_TOKEN` env var, in the usage text and the required-vars loop;
  - a credential label;
  - a `read versions` and a `write versions` column in the header matrix comment;
  - `do_request` rows: anonymous GET/POST `versions` → deny; owner GET `versions` → allow;
    `version_check` POST `versions` → allow; `version_check` GET `versions` → deny;
    `version_check` POST to every other topic → deny; every other publisher POST `versions` →
    deny.

  Run `bash -n scripts/healthcheck/ntfy-acl-check.sh` and `shellcheck` if available.
- [x] T027 [US4] Create `ansible/version-sources.yml`, following data-model §2. Start with a
  header comment: purpose, spec 090, schema link `specs/090-monitoring-version-currency/data-model.md`,
  and "every pin in a versions block must have exactly one entry (guard test)". Then add the
  `pins:` list with one entry per row of the data-model §2 policy table, monitoring entries first,
  in this order: prometheus, grafana, telegraf, alertmanager, blackbox_exporter, node_exporter.
  Then the 14 service pins in file order. Each entry has:
  - `variable` and `file` (repo-relative);
  - `policy`;
  - `github`, `endoflife` and `reason` exactly as the table says.

  Reasons:
  - `immich_postgres_image` / `immich_redis_image`: "digest-pinned; upgraded with Immich";
  - `financial_scenario_version` / `market_model_version`: "own image; released by its own
    pipeline (no GitHub releases)";
  - `hermes_searxng_version`: "date-tagged image; no release source".
- [x] T028 [US4] Create `python/src/homelab_proxmox_orchestrator/version_currency.py`, following
  contract §1 and §4, data-model §3–§6, and research R-10 and R-11. Use only the stdlib plus
  `yaml`. Structure:
  - **HTTP helpers**: `_http_get_json(url, token=None)` and `_http_post(url, body, headers)`, each
    with `urllib.request` and `timeout=20`, no retries.
  - **Tags**: `parse_tag(tag) -> tuple[int, int, int] | None`. Drop a leading `v`, take the first
    `\d+\.\d+(\.\d+)?` as the core, and pad the patch with 0. Return `None` if the core does not
    start the string, as with date-tagged images.
  - `is_prerelease(release)`.
  - `fetch_releases(repo, token)`: `GET https://api.github.com/repos/{repo}/releases?per_page=100`,
    with `Authorization: Bearer` if a token is given.
  - `fetch_cycles(product)`: `GET https://endoflife.date/api/{product}.json`.
  - **Pins**: `load_pins(sources_path, repo_root)` validates the schema (exit 2 on violation), and
    reads each pin's current value with `yaml.safe_load` of its `file`.
  - **Evaluation**: `evaluate(pin, value, releases, cycles, today) -> list[Finding]`, implementing
    the three policies of research R-10 with a 30-day warning window. The pinned line is matched
    by `major.minor`, or by `major` for major-only cycles.
  - **Report**: `build_report(...)`, and `format_message(report, run_url) -> (title, priority, body)`
    exactly as contract §4. `run_url` comes from `GITHUB_SERVER_URL`/`GITHUB_REPOSITORY`/`GITHUB_RUN_ID`
    when set.
  - **CLI**: `main(argv=None) -> int`, with `argparse` options `--dry-run`, `--sources` (default
    `ansible/version-sources.yml`) and `--repo-root` (auto-detect, like the guard tests). Env:
    `NTFY_TOKEN`, `NTFY_URL` (default `https://ntfy.hus-sky.no`), `NTFY_TOPIC` (default
    `versions`), `GITHUB_TOKEN`.
  - **Exit codes**: 0 / 1 / 2 as in contract §1. Never print the token. In `--dry-run`, print
    title, priority and body to stdout.
  - `if __name__ == "__main__": sys.exit(main())`.

  Fetch each GitHub repo and each endoflife product once per run. Make T023 pass.
- [x] T029 [US4] In `python/pytest.ini`, add `--cov=homelab_proxmox_orchestrator.version_currency`
  to `addopts`. Run `bash scripts/ci/python-tests.sh` (the coverage gate is `--cov-fail-under=80`)
  and confirm the whole suite passes. If coverage of the new module pulls the total below 80%,
  add unit cases. Do not lower the threshold.
  **Mutation gate**: `python/mutmut.ini` mutates the whole package, so the new module enters
  the nightly mutation score, gated at `python/mutmut-threshold.txt` (41.0). Measure the new
  module's own score, on `pve` as the threshold script expects, or locally:
  `.venv/bin/mutmut run --paths-to-mutate python/src/homelab_proxmox_orchestrator/version_currency.py`
  then `.venv/bin/mutmut results`. Score = killed / (killed + survived).
  - If it is below 41%, add unit cases to `python/tests/version_currency/test_version_currency.py`
    until it reaches 41%, focusing on the policy branches and the exit codes. Do not lower the
    threshold.
  - Record the measured score in quickstart §0.
  - If mutmut cannot run locally (it is not in the test lock), run it through
    `nightly-deeper-verification.yml` with `run_mutmut=true` on the branch, and record that
    instead.
- [x] T030 [US4] Create `.github/workflows/version-currency.yml` (contract §2):
  - `name: Version currency`;
  - `on: schedule: [{cron: "0 6 * * 1"}]`, and `workflow_dispatch: inputs: dry_run: {type: boolean, default: false, description: "Print the report, do not publish"}`;
  - top-level `permissions: {contents: read}`;
  - one job `check`, with `runs-on: [self-hosted]` and `timeout-minutes: 10`.

  Steps:
  1. `actions/checkout@v4`.
  2. Validate system Python ≥ 3.11 (copy the step from `nightly-deeper-verification.yml`).
  3. `astral-sh/setup-uv@v3`, then `uv venv --python 3.11 --clear && uv pip sync --python
     .venv/bin/python --require-hashes python/requirements-nightly.lock.txt`. That lock has
     `ansible-core` and PyYAML.
  4. **Read token**, skipped when `inputs.dry_run` is true:
     - env `ANSIBLE_VAULT_PASSWORD: ${{ secrets.ANSIBLE_VAULT_PASSWORD }}`;
     - write the password to a `mktemp` file with `umask 077`, then run
       `.venv/bin/ansible-vault view --vault-password-file "$f" ansible/group_vars/services/vault.yml`
       piped to `.venv/bin/python -c` that prints only `ntfy_version_check_token`;
     - `echo "::add-mask::$tok"`, then append `NTFY_TOKEN=$tok` to `$GITHUB_ENV`;
     - `rm -f "$f"`, with `set -euo pipefail` and no `set -x`.
  5. **Run**: env `GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}` and `PYTHONPATH: python/src`;
     `.venv/bin/python -m homelab_proxmox_orchestrator.version_currency ${{ inputs.dry_run && '--dry-run' || '' }}`.

  Make guard test 4 pass, and remove its `xfail` marker if T012 added one. Run `act -l` and
  `act -n -W .github/workflows/version-currency.yml workflow_dispatch`. If `act` or Docker is not
  available on the Mac, record why in quickstart §0, as the constitution allows.
- [x] T031 [US4] Run the full guard file
  `.venv/bin/python -m pytest -c python/pytest.ini --no-cov python/tests/guardrails/test_version_pins.py`
  and confirm all 5 tests pass with no `xfail` markers left. Run the local dry run from the repo
  root: `GITHUB_TOKEN=$(gh auth token) PYTHONPATH=python/src .venv/bin/python -m homelab_proxmox_orchestrator.version_currency --dry-run`.
  Expect exit 0 (or exit 1 with only network-caused check errors from the Mac behind Zscaler;
  record which). The output must have **no** monitoring pin among the findings, and must list the
  service pins that are behind and the five `unchecked` pins. Record this in quickstart §9.
- [ ] T032 [US4] Commit T023–T031 (not `.specify/feature.json`). Push through the Git-Data API
  as in T012, and confirm PR CI is green.
  - **Live**: deploy `ntfy` from the branch through the prod path (`lxc-promote-prod`, then
    `lxc-apply-prod`, `-f service=ntfy`).
  - Then the owner runs `scripts/healthcheck/ntfy-acl-check.sh` with all tokens, including
    `NTFY_VERSION_CHECK_TOKEN`, and expects every cell to match.
  - The owner subscribes to `versions` in the ntfy app (quickstart §8). Record the result in §8.
- [ ] T033 [US4] Live: SC-005 and FR-013a (quickstart §9).
  1. Run `gh workflow run version-currency.yml --ref 090-monitoring-version-currency -f dry_run=true`
     and confirm it succeeds and prints the report.
  2. Create the throwaway branch `test/090-lowered-pin` from the 090 branch, with
     `grafana_version: "13.2.3"` (one patch below the deployed pin). Push it through the API, run
     the workflow on it with `dry_run=false`, and confirm a `versions` message containing
     `grafana_version 13.2.3 -> 13.2.4` arrives (owner confirms).
  3. Error case: on the same test branch, set `NTFY_URL` to an unreachable host by temporarily
     adding `NTFY_URL: https://ntfy.invalid` to the run step's env. Re-run and confirm the run
     fails red.
  4. Delete the test branch: `gh api -X DELETE repos/OWNER/REPO/git/refs/heads/test/090-lowered-pin`.

  Fill in the §9 table rows 1–3.

**Checkpoint**: US4 is complete. SC-005 is met; SC-006 is observed after merge (T036).

---

## Phase 8: Polish & Cross-Cutting Concerns

- [ ] T034 Live, as root on `pve`, after T016 and T017 pass: `pct delsnapshot <vmid> pre-090`
  (FR-012). Record the deletion time in quickstart §4. On the monitoring LXC, remove the
  `/root/090` evidence files once their counts are in the quickstart.
- [x] T035 [P] Append an entry to `docs/backlog/improvement-candidates.md`: the
  `roles/monitoring_stack/defaults/main.yml` copies of non-version values have drifted from
  `group_vars/monitoring/vars.yml`, for example `monitoring_install_dir` vs `monitoring_base_path`,
  and `grafana_domain` (research R-04, out of scope for 090). Give the date and cite spec 090.
  Add a second entry: "Move `jellyfin_exporter_version` and `fail2ban_exporter_version` from role
  defaults into the `# Service versions` block of `group_vars/services/vars.yml`, so the 090
  currency check covers them (spec 090 research R-10, out of scope there)".
- [ ] T036 Update `docs/backlog/090-monitoring-stack-version-currency.md`: set **Status** to
  `Delivered — specs/090-monitoring-version-currency/` with the date, as the
  `consolidate-service-versions.md` precedent does. Set `specs/090-monitoring-version-currency/spec.md`
  **Status** to `Implemented (<date>)`. Commit (not `.specify/feature.json`), push through the API,
  and mark the PR ready for review. After merge, record the first scheduled Monday run in
  quickstart §9 row 4. After 4 weeks, record the SC-006 outcome in row 5: zero reports for pins that
  are current.

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 1 (Setup)**: no dependencies.
- **Phase 2 (Guard test)**: after Phase 1. Blocks nothing, but must be seen red first.
- **Phase 3 (US1 code and rehearsal)**: after Phase 2. It ends with T012, the first push and PR.
- **Phase 4 (US2 rollback)**: T013 (runbook) can start any time after Phase 1. T014 (snapshot)
  comes after T012's CI is green and must be the last step before T015.
- **Phase 5 (US1 rollout)**: needs Phase 3 complete (including T012) and T014.
- **Phase 6 (US3 single source)**:
  - The code tasks T018–T022 touch no file used by the rollout except `group_vars/monitoring/vars.yml`
    (T019) and the runbook (T021, after T013). They may be done before T012 so they ship in the
    first push. The rendered output does not change.
  - If done after T015, no redeploy is needed.
  - T020 must come after T005.
- **Phase 7 (US4 currency check)**: the code (T023, T025–T031) is independent of Phases 3–6, with
  one exception. **T025 must not reach the branch before T024** while any `ntfy` deploy from the
  branch is still pending (T017's ntfy row): the ntfy role would render undefined vault
  variables. T027 needs the final pin locations (after T019 and T020) for its `file` fields. T033
  needs T032 (the ntfy account deployed) and T024.
- **Phase 8 (Polish)**: T034 after T016 and T017. T036 last.

### User story dependencies

- **US1** needs US2's snapshot (T014) before its production deploy (T015). Nothing else.
- **US2** is independent. It only has to be in place before US1's deploy.
- **US3** is independent of US1 at runtime. Its guard tests pass only once its own tasks are done.
- **US4** has no runtime dependency on US1–US3. Its sources map uses US3's final pin locations,
  and its SC-005 test lowers the pin US1 raised. T025 on the branch blocks branch deploys of
  `ntfy` until T024 is done (T017 guard).

### Within each story

- Tests first (T003 before any change; T023 before T028), and see them fail.
- Code → static checks → push → live checks.
- One host at a time for T017.

## Parallel Opportunities

- T005 (node_exporter default) ∥ T004/T006/T007: different files.
- T013 (runbook rollback) ∥ all of Phase 3.
- T023 (unit tests), T025 (ntfy defaults) and T026 (ACL script) ∥ each other, and ∥ all Phase 3–6
  code.
- T035 ∥ anything.
- Live tasks are strictly sequential: T009 → T010 → T011 → (T012 push) → T014 → T015 → T016 → T017 → T034.

### Parallel example: User Story 4

```text
In parallel:
  T023  python/tests/version_currency/test_version_currency.py
  T025  ansible/roles/ntfy/defaults/main.yml
  T026  scripts/healthcheck/ntfy-acl-check.sh
Then:   T027 → T028 → T029 → T030 → T031 → T032 → T033
```

### Parallel example: User Story 1 (code)

```text
In parallel:
  T004  ansible/group_vars/monitoring/vars.yml
  T005  ansible/roles/node_exporter/defaults/main.yml
  T013  docs/operations/monitoring/runbook-upgrades.md   (US2)
Then:   T006 → T007 → T008 → T009 → T010 → T011 → T012
```

## Implementation Strategy

### MVP (US1 + US2: supported versions, safely)

1. Phase 1 and Phase 2 (guard red).
2. Phase 3: pins, validation before restart, static checks, rehearsal.
3. Phase 4: rollback runbook and a fresh snapshot.
4. Phase 5: one prod deploy, before/after comparison, test alert, then node_exporter host by host.
5. **Stop and validate**: SC-001 to SC-003 and SC-007. The estate is back on supported versions,
   which was the urgent part.

### Incremental delivery

1. MVP as above, with the US3 code (T018–T022) folded into the first push, because it is small and
   output-neutral.
2. US4: the currency check, the ntfy account, and the workflow. Prove it with SC-005.
3. Polish: delete the snapshot, record the backlog candidate, mark the feature delivered, and
   observe SC-006 over 4 weeks.

## Notes

- [P] means different files with no incomplete dependency.
- Every live result is written into the quickstart tables; they are the rollout record.
- Never commit `.specify/feature.json`, vault values, `GF_PW` or tokens.
- Pushes go through the GitHub Git-Data API (`AGENTS.md`). Deploys can target the branch ref; no
  merge is needed to deploy.
