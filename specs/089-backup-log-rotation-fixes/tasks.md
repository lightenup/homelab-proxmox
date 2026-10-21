---
description: "Task list for 089 backup and log rotation quick fixes"
---

# Tasks: Backup and Log Rotation Quick Fixes

**Input**: Design documents from `/specs/089-backup-log-rotation-fixes/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/runtime-config.md](./contracts/runtime-config.md),
[quickstart.md](./quickstart.md)

**Tests**: One guard test file in the existing guardrail tests (FR-013, constitution test-driven
rule). It is written first (Phase 2) and must fail before the fixes and pass after them. Everything
else is static checks plus the live checks in `quickstart.md`.

**Organization**: One phase per user story. US1 (Proxmox host backup, P1), US2 (Immich database
backup, P1) and US3 (Docker log rotation, P2) touch disjoint files and can be done in any order
after Phase 2.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1, US2 or US3, from spec.md
- Paths are repo-relative. Ansible commands run from `ansible/` unless stated.

## Path Conventions

- Ansible: `ansible/roles/`, `ansible/playbooks/`, `ansible/group_vars/`
- Operator docs: `docs/operations/`, `docs/runbooks/`
- Tests: `python/tests/guardrails/`
- Live results: the tables at the end of `specs/089-backup-log-rotation-fixes/quickstart.md`
- Where live commands run (quickstart Prerequisites): **Fix 1** runs from an operator machine with
  root SSH to `pve` and `ansible/.vault-pass.txt`. **Fix 2 drill and Fix 3 recreate** run as
  `ci@pve` in `/home/ci/homelab-proxmox`, using `~/.ssh/id_lxc_deploy` and a temporary
  `ANSIBLE_VAULT_PASSWORD_FILE`.

---

## Phase 1: Setup

**Purpose**: Confirm the baseline before editing.

- [X] T001 Confirm the branch is `089-backup-log-rotation-fixes` and up to date with `origin/main` (`git fetch origin main && git log --oneline origin/main -1`). Then run `ansible-playbook -i inventories/prod/hosts.yml playbooks/backup_proxmox.yml --syntax-check` and `ansible-playbook -i inventories/prod/hosts.yml playbooks/immich.yml --syntax-check` from `ansible/`, and note that both pass before any change. If either fails now, record the pre-existing failure in `specs/089-backup-log-rotation-fixes/quickstart.md` (Results, "Static checks and guard test") so it is not blamed on this feature. Make sure the test environment has PyYAML: `.venv/bin/python -c 'import yaml'`; if it fails, `pip install -r python/requirements-test.lock.txt` into `.venv`.

---

## Phase 2: Foundational (guard test first)

**Purpose**: The automated guard required by FR-013. It is written before the fixes so it is seen
to fail first.

- [X] T002 Create `python/tests/guardrails/test_backup_log_rotation_config.py`, modelled on `python/tests/guardrails/test_no_deprecated_refs.py` (same `_find_repo_root` helper, `from __future__ import annotations`, `pathlib`; use `yaml.safe_load` for YAML). Write these test functions, one per assertion group. Each has a docstring naming the spec requirement.
  1. `test_pve_backup_unit_sandbox` (FR-001, FR-002, contract C1): read `ansible/roles/proxmox_backup/templates/proxmox-backup.service.j2` as text. Assert it contains the lines `ProtectHome=read-only`, `ProtectSystem=strict`, `PrivateTmp=true` and `NoNewPrivileges=true`, and does not contain `ProtectHome=true`. Find the single line starting with `ReadWritePaths=` and assert that, stripped, it equals exactly `ReadWritePaths={{ proxmox_backup_staging_base }} {{ proxmox_backup_nas_mount_point }} /run/lock`.
  2. `test_pve_backup_deploy_uses_prod_inventory` (FR-003): in `Taskfile.yml` and `scripts/backup/run_proxmox_backup.sh`, every line containing `backup_proxmox.yml` also contains `inventories/prod/hosts.yml` and does not contain `inventories/static`.
  3. `test_pve_backup_doc_states_ci_limitation` (FR-014): `docs/operations/backups-proxmox-config.md` contains the heading `## Deploy path and CI limitation`.
  4. `test_immich_playbook_applies_backup_role` (FR-004): load `ansible/playbooks/immich.yml`. Find the play whose `name` is `Configure Immich`, and assert its `roles` list contains `immich_backup` at an index greater than that of `immich`.
  5. `test_immich_backup_role_asserts_nas_mount` (spec edge case, research R5): load `ansible/roles/immich_backup/tasks/main.yml` and assert the first task uses `ansible.builtin.assert` and has a `when` mentioning `immich_require_nas_mount`.
  6. `test_standalone_immich_backup_playbook_removed` (FR-006): assert `ansible/playbooks/backup.yml` does not exist, and `docs/runbooks/immich-backup-restore.md` does not contain `playbooks/backup.yml`.
  7. `test_docker_log_rotation_defaults` (FR-008, FR-009, contract C3): load `ansible/group_vars/services/vars.yml` and assert `docker_daemon_options == {"log-driver": "json-file", "log-opts": {"max-size": "10m", "max-file": "3"}}` (values are strings). Also assert `ansible/group_vars/monitoring/vars.yml` does not define `docker_daemon_options`, so there is one definition only.

  Run `.venv/bin/python -m pytest -c python/pytest.ini --no-cov python/tests/guardrails/test_backup_log_rotation_config.py` and confirm all 7 tests **fail** for the expected reasons. Do not mark this task done until you have seen them fail.

**Checkpoint**: The guard exists and is red. The story phases turn it green one group at a time.

---

## Phase 3: User Story 1 - Proxmox host configuration is backed up again (Priority: P1) 🎯 MVP

**Goal**: `proxmox-backup.service` completes from its timer and leaves a fresh, decryptable archive on
the NAS (FR-001 to FR-003, FR-014, SC-001, SC-002).

**Independent Test**: Guard tests 1–3 pass. Then, from the operator machine, deploy with
`task ansible:backup`, start the service once, and confirm `Result=success` and a NAS archive under
24 h old that decrypts with the age key (quickstart Fix 1).

### Implementation for User Story 1

- [X] T003 [US1] In `ansible/roles/proxmox_backup/templates/proxmox-backup.service.j2`, change `ProtectHome=true` to `ProtectHome=read-only`. Change `ReadWritePaths={{ proxmox_backup_staging_base }} {{ proxmox_backup_nas_mount_point }}` to `ReadWritePaths={{ proxmox_backup_staging_base }} {{ proxmox_backup_nas_mount_point }} /run/lock`. Change nothing else in the unit: `PrivateTmp=true`, `NoNewPrivileges=true` and `ProtectSystem=strict` stay. Do NOT change the lock path in `proxmox-config-backup.sh.j2` (research R1: the lock stays `/run/lock/proxmox-backup.lock` so manual runs and timer runs still exclude each other). The rendered result must match contract C1 in `specs/089-backup-log-rotation-fixes/contracts/runtime-config.md`.
- [X] T004 [P] [US1] In `Taskfile.yml` line 247 (task `ansible:backup`), replace `-i inventories/static/hosts.yml` with `-i inventories/prod/hosts.yml`. Leave lines 223 and 235 (`host_proxmox.yml`) unchanged; they are a recorded follow-up (plan.md, Follow-ups).
- [X] T005 [P] [US1] In `scripts/backup/run_proxmox_backup.sh` line 32, replace `ansible/inventories/static/hosts.yml` with `ansible/inventories/prod/hosts.yml`.
- [X] T006 [P] [US1] In `docs/operations/backups-proxmox-config-restore.md`, lines 564 and 615, replace `inventories/static/hosts.yml` with `inventories/prod/hosts.yml` in both `ansible-playbook ... playbooks/backup_proxmox.yml` commands.
- [X] T007 [P] [US1] In `docs/operations/backups-proxmox-config.md`: (a) at lines 472 and 475 (troubleshooting "Check inventory exists" / "Verify proxmox_hosts group defined"), replace `ansible/inventories/static/hosts.yml` with `ansible/inventories/prod/hosts.yml`; (b) add a new section with exactly the heading `## Deploy path and CI limitation` (FR-014, constitution principle V exception). It must say: (1) the backup system is deployed only from an operator machine with root SSH to the Proxmox host (`192.168.1.112`) and `ansible/.vault-pass.txt`, using `task ansible:backup` (or `ansible-playbook -i inventories/prod/hosts.yml playbooks/backup_proxmox.yml` from `ansible/`); (2) why CI cannot run it: the `ci` account on `pve` has no root SSH to the host, and its passwordless sudo is limited to `qm`/`pct`/`systemctl` and similar, by design of the constitution's privilege tiers; (3) a CI path would need a privilege-model change and is tracked as a follow-up in `specs/089-backup-log-rotation-fixes/plan.md`. Put the section near the existing deployment instructions. Keep it to about 10 lines.
- [X] T008 [US1] Static checks (FR-013), from `ansible/`: `ansible-playbook -i inventories/prod/hosts.yml playbooks/backup_proxmox.yml --syntax-check` passes; `ansible-lint roles/proxmox_backup` reports no new findings compared with `main`; `rg -n "inventories/static" ../Taskfile.yml ../scripts/backup ../docs/operations/backups-proxmox-config*.md` matches only `Taskfile.yml` lines 223 and 235. From the repo root, guard tests 1–3 (`-k "pve_backup"`) pass. Record the result in quickstart.md (Results, "Static checks and guard test").

### Live verification for User Story 1 (operator machine with root SSH to `pve`)

- [ ] T009 [US1] Live deploy and first run, following `specs/089-backup-log-rotation-fixes/quickstart.md` "Fix 1" steps 1–6. As root on `pve`, confirm `/root/.age/proxmox-backup.key` is non-empty. If it is missing, stop and ask the owner to restore it from the password manager; do not generate a new key. Then run `task ansible:backup` from the operator machine's checkout of this branch. It cannot run from `ci@pve` (no root SSH; see T007). Confirm `systemctl show proxmox-backup.service -p ProtectHome -p ReadWritePaths` matches contract C1. Run `systemctl start proxmox-backup.service` and expect `Result=success`. Confirm the newest `/mnt/nas-backup/proxmox-backup-*.tar.zst.age` is under 24 h old and that `age -d -i /root/.age/proxmox-backup.key <archive> | zstd -d | tar -t` lists entries. If the run fails, capture `journalctl -u proxmox-backup.service -n 100 --no-pager`; fixing a further defect is in scope (spec Assumptions), so add a follow-up task here and do not mark this one done. Record each result row in quickstart.md (Results, "Fix 1 and Fix 2").
- [ ] T010 [US1] SC-002: over the next 3 nights, check `journalctl -u proxmox-backup.service --since -1d --no-pager` and `systemctl show proxmox-backup.service -p Result` after each timer firing (around 02:00–02:05). Record the 3 dates and their results in quickstart.md (Results, "PVE timer run 1 / 2 / 3"). Each must be `success`.

**Checkpoint**: The Proxmox host's configuration backup works. US1 is done when T010 has three successes.

---

## Phase 4: User Story 2 - Immich database is backed up on a schedule (Priority: P1)

**Goal**: The normal Immich pipeline deploy installs `immich-backup.timer`, a run succeeds, and the
existing restore drill passes (FR-004 to FR-007, SC-003, SC-004).

**Independent Test**: Guard tests 4–6 pass. Then run `Prod 1 → Prod 2` for `immich`, check the
timer is enabled and active, run one backup, and run `playbooks/restore-drill.yml` (quickstart
Fix 2).

### Implementation for User Story 2

- [X] T011 [US2] In `ansible/playbooks/immich.yml`, second play ("Configure Immich"), change `roles:` from `[geerlingguy.docker, immich]` to `[geerlingguy.docker, immich, immich_backup]`. Order matters: `immich_backup` goes after `immich`, matching `playbooks/nextcloud.yml`. Keep the existing `vars: immich_require_nas_mount: "{{ (deploy_environment | default('prod')) != 'lab' }}"` unchanged.
- [X] T012 [P] [US2] In `ansible/roles/immich_backup/tasks/main.yml`, insert a new FIRST task, before "Ensure backup directory exists". Name it "Assert Immich backup location is on the NAS mount". Make it `ansible.builtin.assert` with `that: (immich_backup_path | dirname) in (ansible_mounts | map(attribute='mount') | list)`, `when: immich_require_nas_mount | default(true) | bool`, and a `fail_msg` saying the NAS bind mount for `{{ immich_backup_path | dirname }}` is missing, so the backup would write to the container's local disk. Do not add a role `defaults/` file. `immich_backup_path` is `/mnt/immich/backups` in `ansible/group_vars/services/vars.yml:431`, so the check targets `/mnt/immich` (research R5).
- [X] T013 [P] [US2] Delete `ansible/playbooks/backup.yml` (`git rm`). Do not touch historical references in `specs/006-backups-and-restore-drill/` or `docs/backlog/` (FR-006).
- [X] T014 [P] [US2] In `docs/runbooks/immich-backup-restore.md`, section "Manual Backup" (around lines 26–37), replace "You can trigger a backup manually via Ansible:" and the `ansible-playbook ansible/playbooks/backup.yml ...` code block with "Trigger a backup now (on the Immich host):" and a code block `sudo systemctl start immich-backup.service`. Keep the existing "Or directly on the host: `sudo /usr/local/bin/backup_immich.sh`" alternative.
- [X] T015 [US2] Static checks (FR-013), from `ansible/`: `ansible-playbook -i inventories/prod/hosts.yml playbooks/immich.yml --syntax-check` passes; `ansible-lint playbooks/immich.yml roles/immich_backup` reports no new findings compared with `main`; `test ! -e playbooks/backup.yml`; and `rg -n "playbooks/backup\.yml" ../docs/runbooks ../ansible ../.github ../scripts ../Taskfile.yml` returns nothing. From the repo root, guard tests 4–6 (`-k "immich"`) pass. Record the result in quickstart.md (Results, "Static checks and guard test").

### Delivery and live verification for User Story 2

- [ ] T016 [US2] Commit the code for all three stories in one commit (T002–T015 and T019–T020) with a conventional message (e.g. `fix(089): PVE backup sandbox, install immich backup, docker log rotation`). Do not run this task until T008, T015 and T020 have all passed. The guard file from T002 covers all three fixes, so pushing with any story's code missing would leave the PR's CI red. Before committing, run the full guard file; all 7 tests must pass. Push branch `089-backup-log-rotation-fixes` through the GitHub Git-Data API, following `AGENTS.md`, "How to push a branch/commit": `git push` is blocked by Zscaler. Run the push script in the background, because the first `gh api` call stalls for about 2 minutes. Verify that the local `git rev-parse HEAD^{tree}` equals the remote tree SHA, then `git fetch origin 089-backup-log-rotation-fixes && git reset --hard origin/089-backup-log-rotation-fixes`. Open a PR with `gh api repos/OWNER/REPO/pulls --input pr.json`, base `main`, linking `specs/089-backup-log-rotation-fixes/spec.md`. No `allow-protected-path-changes` label is needed: no file under `.specify/**`, `adapter/**`, `scripts/lab/**` or `mkdir/**` changes, and `.specify/feature.json` is gitignored. Confirm the PR's CI run executes the new guard test (it lives under `python/tests/`, which `scripts/ci/python-tests.sh` runs).
- [ ] T017 [US2] Lab check (edge case: the backup must not break the lab deploy), after T016: `gh workflow run lxc-deploy-lab.yml --ref 089-backup-log-rotation-fixes -f service=immich -f apply=true`. The deploy must succeed with the NAS assert skipped (`immich_require_nas_mount` is false in the lab) and `immich-backup.timer` active on the lab host. Record the run id in quickstart.md (Results, "Immich lab deploy"). If the lab Immich host is not provisioned, write "lab not available" there and continue; the prod promote also runs the lab gate.
- [ ] T018 [US2] Prod deploy and verify, following quickstart.md "Fix 2" steps 1–4: `gh workflow run lxc-promote-prod.yml --ref 089-backup-log-rotation-fixes -f ref=089-backup-log-rotation-fixes -f service=immich`, then `gh workflow run lxc-apply-prod.yml --ref 089-backup-log-rotation-fixes -f promotion_run_id=<promote run id> -f confirm_apply_prod=deploy-prod`. On `immich` (from `ci@pve`: `ssh -i ~/.ssh/id_lxc_deploy root@192.168.1.213`), check that `systemctl is-enabled immich-backup.timer` is `enabled`, `systemctl is-active immich-backup.timer` is `active` and `findmnt /mnt/immich` shows a mount (SC-003). Run `systemctl start immich-backup.service` and expect `Result=success` with a new `/mnt/immich/backups/immich-backup-*.tar.gz`. Then, as `ci@pve` with a temporary `ANSIBLE_VAULT_PASSWORD_FILE` (quickstart Prerequisites): `cd /home/ci/homelab-proxmox/ansible && ansible-playbook -i inventories/prod/hosts.yml playbooks/restore-drill.yml --private-key ~/.ssh/id_lxc_deploy` must end with recap `failed=0` (SC-004); afterwards remove the password file. This deploy also writes `daemon.json` (T019 is in the same commit) and restarts Docker on `immich`, so do T021 (the immich recreate) immediately after. Record results in quickstart.md (Results, "Fix 1 and Fix 2").

**Checkpoint**: The Immich database is backed up nightly at 04:30, and the backup is proven restorable.

---

## Phase 5: User Story 3 - Container logs stay bounded on every container host (Priority: P2)

**Goal**: Every container host defaults to `json-file`, `max-size=10m`, `max-file=3`. All 9 hosts are
redeployed and recreated one at a time, and none has a per-container log total over 30 MB
(FR-008 to FR-011, SC-005 to SC-007).

**Independent Test**: Guard test 7 passes. Then deploy one host, run the recreate, and confirm that
every container reports `{"max-file":"3","max-size":"10m"}` (quickstart Fix 3).

### Implementation for User Story 3

- [X] T019 [US3] In `ansible/group_vars/services/vars.yml`, directly below the existing `# Docker configuration (geerlingguy.docker)` block (after `docker_compose_package_state: present`, around line 13), add:
  ```yaml
  # Container log rotation for every Docker host, monitoring included (089, FR-008/FR-009).
  # Applies only to containers created after the change; see specs/089-*/quickstart.md.
  docker_daemon_options:
    log-driver: json-file
    log-opts:
      max-size: "10m"
      max-file: "3"
  ```
  Values must be quoted strings (daemon.json requirement). Do not set `live-restore` (spec Clarifications). Do not add `logging:` to any compose template, and do not add the variable to `group_vars/monitoring/vars.yml` (research R7: monitoring is in the `services` group).
- [X] T020 [US3] Static checks (FR-013), from `ansible/`: `ansible-playbook -i inventories/prod/hosts.yml playbooks/monitoring.yml --syntax-check` and the same for `playbooks/nextcloud.yml` pass. Check that every Docker host resolves the variable. `--playbook-dir` is required: `ansible/group_vars/` sits next to `playbooks/` through the `playbooks/group_vars` symlink, not next to the inventory, so `ansible-inventory` skips it without the flag. Run `ansible-inventory -i inventories/prod/hosts.yml --playbook-dir playbooks --host <h> | python3 -c 'import json,sys; print(json.load(sys.stdin)["docker_daemon_options"])'` for `monitoring`, `nextcloud` and `immich`; each prints the dict. This needs the vault password: `ansible/.vault-pass.txt` locally, or `ANSIBLE_VAULT_PASSWORD_FILE` on `ci@pve`. From the repo root, guard test 7 (`-k "docker_log_rotation"`) passes. Record the result in quickstart.md (Results, "Static checks and guard test").

### Rollout for User Story 3 (sequential, one host at a time, FR-010, SC-007)

Each task below follows quickstart.md "Fix 3" steps 1–6 for its host. Deploy with
`gh workflow run lxc-promote-prod.yml --ref 089-backup-log-rotation-fixes -f ref=089-backup-log-rotation-fixes -f service=<host>`,
then `lxc-apply-prod.yml` with that promotion run id and `-f confirm_apply_prod=deploy-prod`. From
`ci@pve`, `ssh -i ~/.ssh/id_lxc_deploy root@<host-ip>` (IPs in `ansible/inventories/prod/hosts.yml`).
Check that `/etc/docker/daemon.json` matches contract C3, then run the one-off recreate loop from
quickstart step 3, which uses `docker compose ls` and `docker compose -p <name> up -d --force-recreate`
from each project's directory. Check with
`docker ps -q | xargs docker inspect -f '{{.Name}} {{json .HostConfig.LogConfig.Config}}'` that
**every** line shows `{"max-file":"3","max-size":"10m"}`, and confirm the service is healthy. Then
fill that host's row in the quickstart "Rollout record": deploy run id, recreate date, "All
containers limited" = yes. "Verified ≤ 30 MB" is filled by T030. Do not start the next host until
the current row's first three cells are complete.

- [ ] T021 [US3] Rollout host `immich`: T018 already deployed the commit containing T019, so skip the deploy and do only the daemon.json check, the recreate and the inspect. Record row 8.
- [ ] T022 [US3] Rollout host `ntfy`. Record row 1.
- [ ] T023 [US3] Rollout host `market-model`. Record row 2.
- [ ] T024 [US3] Rollout host `financial-scenario`. Record row 3. (The transient `financial-scenario-seed` container is created only on first deploy and removed at once; ignore it if `docker ps -a` shows it.)
- [ ] T025 [US3] Rollout host `eurooffice`. Record row 4.
- [ ] T026 [US3] Rollout host `llm-router`. Record row 5.
- [ ] T027 [US3] Rollout host `hermes`. Record row 6.
- [ ] T028 [US3] Rollout host `monitoring`. Record row 7. Its compose project is started by `roles/monitoring_stack/tasks/compose_stack.yml` (`docker compose up -d`); the recreate loop covers it. Expect a scrape gap of a few minutes.
- [ ] T029 [US3] Rollout host `nextcloud`, last (largest logs: 245 MB). Record row 9. After the recreate, confirm the old oversized `*-json.log` files are gone (`du -sh /var/lib/docker/containers`).
- [ ] T030 [US3] Final sweep (SC-005, SC-006). On each of the 9 hosts, run the sweep from quickstart.md ("Final sweep"). The largest per-container total must be at most 31457280 bytes. Fill each host's "Verified ≤ 30 MB" cell with yes, write the largest value seen in quickstart.md ("Final sweep, largest per-container total across all hosts"), and confirm all 9 rows are `verified` (both yes/no columns yes).

**Checkpoint**: Logs on every container host are bounded. `092` can rely on contract C3.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T031 [P] Update `docs/backlog/089-backup-and-log-rotation-quick-fixes.md`: change the `**Status**` line to point at `specs/089-backup-log-rotation-fixes/`. Answer the two "Open questions" with the decisions (10m × 3; the daemon restarts at deploy and containers need an explicit recreate, see the quickstart).
- [ ] T032 [P] Mark `specs/089-backup-log-rotation-fixes/spec.md` `**Status**` as `Implemented` once T010, T018 and T030 are done, and tick the completed tasks in this file.
- [ ] T033 Push the final docs commit (Git-Data API, as in T016). Ask the owner to merge the PR; do not merge it yourself.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: none.
- **Foundational (Phase 2)**: T002 after T001. It blocks the static-check tasks of every story (T008, T015, T020), which run its tests.
- **US1 (Phase 3)**: code tasks T003–T007 can start after T001; T008 needs T002. T009 deploys from an operator machine and needs no push. T010 spans 3 nights.
- **US2 (Phase 4)**: T011–T014 after T001; T015 needs T002. T016 (the single push) needs T008, T015 and T020, so it also waits for US1's and US3's code. T017 and T018 need T016.
- **US3 (Phase 5)**: T019 after T001; T020 needs T002. Rollout T021–T030 needs T016 (pushed with T019).
- **Polish (Phase 6)**: after the stories it reports on.

### Within each story

- US1: T003 → T008 → T009 → T010. T004–T007 can run in parallel with T003.
- US2: T011–T014 touch different files and can be edited together (T012's assert only runs once T011 wires the role in) → T015 → T016 → T017 and T018.
- US3: T019 → T020 → (T016) → T021 → T022 → … → T029 → T030, strictly sequential (one host at a time, SC-007).

### Cross-story interactions

- All three stories add to the one guard file from T002, but they only make its tests pass; none edits the file.
- T018's Immich deploy also restarts Docker on `immich`, because T019 is in the same commit. Do T021's recreate straight after T018.
- T016 is the single shared push and needs all three stories' code and static checks (T008, T015, T020), so the PR's CI is green from its first run. US1's live work (T009) needs no push and can run before T016.

---

## Parallel Example

```text
# US1 doc and entry-point fixes together, alongside T003:
T004 Taskfile.yml:247
T005 scripts/backup/run_proxmox_backup.sh:32
T006 docs/operations/backups-proxmox-config-restore.md:564,615
T007 docs/operations/backups-proxmox-config.md:472,475 + "Deploy path and CI limitation" section

# US2 file edits together:
T011 playbooks/immich.yml
T012 roles/immich_backup/tasks/main.yml (assert)
T013 git rm playbooks/backup.yml
T014 docs/runbooks/immich-backup-restore.md

# Across stories (different files): T003, T011 and T019 can be edited in the same session.
```

The rollout (T021–T029) must never run in parallel.

---

## Implementation Strategy

### MVP first (US1)

1. T001 → T002 (guard, red) → T003–T007 → T008 (guard tests 1–3 green) → T009. The Proxmox host backup produces a verified archive the same day.
2. T010 confirms over 3 nights. Meanwhile, continue with US2.

### Recommended single pass

1. T001, then T002 (all 7 guard tests red).
2. Edit all code: T003–T007, T011–T014, T019.
3. Run all static checks and the guard: T008, T015, T020 (all 7 green).
4. One push and PR: T016.
5. Live: T009 (PVE, operator machine), T017 (lab), T018 + T021 (Immich deploy, backup, restore drill, recreate), then T022–T029 host by host, then T030.
6. T010 runs in the background over 3 nights. Polish: T031–T033.

---

## Notes

- Total: 33 tasks. Setup: 1. Foundational: 1. US1: 8 (T003–T010). US2: 8 (T011–T018). US3: 12 (T019–T030). Polish: 3.
- The live steps change prod (a Docker restart and a container recreate per host). They run through the gated pipeline or by the operator, one host at a time.
- Never print or commit the age private key or vault contents (constitution II). The temporary vault password file is created with `umask 077` and removed after use.
