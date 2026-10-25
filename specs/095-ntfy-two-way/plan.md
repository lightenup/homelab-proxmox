# Implementation Plan: Two-way ntfy — talk to Hermes and act on notifications from the phone

**Branch**: `095-ntfy-two-way` | **Date**: 2026-10-25 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/095-ntfy-two-way/spec.md`

## Summary

Make ntfy two-way in two slices.

**Slice 1 (P1, configuration only)** covers US-1, US-2 and US-3. The Hermes agent subscribes to a
new inbound topic `hermes-in` that only the owner's phone can write. The agent can read it but
never write it. Replies keep going to `hermes`. Phone-originated sessions are interactive, so
flagged commands become typed `/approve`/`/deny` prompts on the phone. Bypass commands (`/yolo`,
`/update`) are gated off for ntfy. A read-only gateway startup hook reports offline gaps, and an
audit hook logs every inbound message and decision to Loki. It all runs on the stock upstream
image: changes are ntfy ACLs, `agent.env`, `agent-config.yaml` and two hooks.

**Slice 2 (P2)** covers US-4, US-5 and US-6:

- A small deterministic **action relay**, written in Python and run in the monitoring compose
  stack, becomes Alertmanager's ntfy-side receiver. It publishes alerts with `SEND_MESSAGE`
  broadcast buttons, so the phone publishes presses with its own account and no credential
  appears in any notification. It executes allowlisted actions from the `actions` topic, starting
  with a bounded Alertmanager silence.
- Native approval buttons and report-reply context follow, gated on on-device verification
  (R-006) and an upstream adapter PR.

Slice 3 (P3, US-7) admits further relay actions one at a time.

## Technical Context

**Language/Version**: Python 3.11 (relay, hooks); Jinja2/Ansible (configuration); YAML (ntfy
`server.yml`, agent config).

**Primary Dependencies**: ntfy `v2.28.0` (unchanged pin); `nousresearch/hermes-agent` `v0.21.6`
(stock, unchanged pin); Alertmanager `v0.34.1` API v2 (silences); relay uses the standard library
only (`urllib`, `http.server`, `json`), so it runs on a stock `python:3.11-slim` image with code
mounted read-only and needs no image build.

**Storage**: None durable. The relay keeps an in-memory dedupe LRU. Hooks write nothing but logs.
Optional P2 "recent reports" file under the agent's data dir (R-009).

**Testing**: `pytest` under `python/tests/` for the relay (parsing, allowlist, expiry, dedupe,
alert formatting parity with `homelab-alertmanager.yml`) and the hooks' pure functions; guard tests
in `python/tests/guardrails/` for rendered ACLs and agent config, covering SC-002 and the slash
gating; `scripts/healthcheck/ntfy-acl-check.sh` extended with the new matrix rows; LAB-first
manual checks per [quickstart.md](./quickstart.md).

**Target Platform**: Existing LXCs: `ntfy` (ACL), `hermes` (agent), `monitoring` (relay, P2).

**Project Type**: Infrastructure configuration plus one small service.

**Performance Goals**: Chat round-trip dominated by model latency. Relay confirms a press within
30 s (SC-005). Gap notice within 60 s of gateway start (SC-003).

**Constraints**:

- The agent never holds a credential that can write `hermes-in` or `actions` (R-005).
- No new network exposure.
- Pushover alert path untouched.
- LAB renders no inbound or actions grant (FR-011).

**Scale/Scope**: One owner, one phone. Messages are in the tens per day.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| I. Spec-driven | PASS | `specs/095-ntfy-two-way/` (spec, plan, research). Amendments to `082`/`083` docs are tasks (FR-013). |
| II. Secrets | PASS | Slice 1 reuses the `owner` and `hermes` users and tokens (only their ACLs change) and adds one LAB-only credential, `hermes_lab` (`ntfy_hermes_lab_password_hash`, `ntfy_hermes_lab_token`), in vault (spec FR-011). The relay's new ntfy user and token go in vault (`ntfy_action_relay_*`). Tokens exposed in session output are rotated as part of rollout. |
| III. Separation | PASS | No Terraform change. No new LXC (R-011). All service changes are Ansible. The LAB rig is the existing `pve-lab` VM (R-015); nothing under `scripts/lab/` changes. |
| IV. Code economy | PASS, with two watch items | Slice 1 adds no code beyond two small hooks. The relay replaces the Go template (one artifact out, one in) instead of adding a parallel path. The allowlist starts with **one** action; no plugin system is built for future actions. Watch item 2: the LAB-rig workflow (`lab-rig.yml`) and playbook (`lab_hermes_agent.yml`) have one consumer today (the T008 gate). They are justified because spec FR-011 needs the scratch pair on a machine that is not production, and no existing path deploys an application role to the 10.99.x rig (R-015). They reuse `pve-lab up`/`down` and the `hermes` role unchanged, and add no wrapper. |
| V. Dual provisioning | PASS, with one documented limitation | Existing `ntfy`, `hermes` and `monitoring` deploys, via CI or laptop. No new service in workflow dropdowns. The new `lab-rig.yml` (R-015) runs its commands on `pve` over SSH as `ci`. A laptop cannot route to 10.99.0.0/24, so the local path is the same commands run by hand from `ssh ci@pve` (documented in quickstart § 0, as principle V allows). |
| Networking / access | PASS | Nothing new is exposed. The relay talks to Alertmanager on the compose network and to ntfy via Caddy. |
| Test-driven | PASS | Relay logic in a testable Python module. Guard tests for rendered config. LAB-first verification of R-001/R-002 before PROD. |

**Post-design re-check**: still PASS. Watch item IV is the reason R-010 retires the Go template
instead of keeping both paths.

## Project Structure

### Documentation (this feature)

```text
specs/095-ntfy-two-way/
├── spec.md
├── plan.md              # this file
├── research.md          # R-001 … R-015
├── data-model.md        # topics, users, ACL matrix, action command, approval prompt
├── quickstart.md        # LAB/PROD validation, phone setup, revocation
├── contracts/
│   ├── acl-matrix.md        # who may read/write which topic (SC-002)
│   ├── inbound-chat.md      # hermes-in message, slash allowlist, audit line
│   └── action-command.md    # actions-topic command grammar, relay responses (P2)
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
ansible/roles/ntfy/
├── defaults/main.yml                  # ntfy_users gains per-user `access:` list; owner extra grants
└── templates/server.yml.j2            # render access from data, not hard-coded write-only
ansible/roles/hermes/
├── templates/agent.env.j2             # PROD: hermes-in; LAB rig: hermes-lab-in scratch pair; LAB stage: no NTFY_TOPIC
├── templates/agent-config.yaml.j2     # ntfy slash-command gating (R-002, spec FR-014); approvals.timeout 900
├── templates/docker-compose.yml.j2    # read-only bind mounts for hooks
├── files/hooks/gap-notice/{HOOK.yaml,handler.py}   # R-007 (static files, importable by pytest)
├── files/hooks/audit/{HOOK.yaml,handler.py}        # R-008
└── tasks/main.yml                     # LAB assert extended (FR-011)
ansible/roles/monitoring_stack/        # P2
├── templates/docker-compose.yml.j2    # + action-relay service (python:3.11-slim, code ro)
├── templates/alertmanager.yml.j2      # ntfy webhook → relay instead of ntfy
├── templates/prometheus.yml.j2        # + ntfy-action-relay scrape job (heartbeat, FR-008)
└── templates/service_alerts.yml.j2    # + NtfyActionRelayDown
ansible/host_vars/hermes.yml           # + HermesNtfyStreamDown, HermesPermanentApprovalGranted (Loki rules)
python/src/homelab_proxmox_orchestrator/ntfy_action_relay.py  # P2: relay (stdlib only; in the package so mutmut and coverage include it)
python/tests/ntfy_action_relay/        # P2: relay tests
python/tests/hermes_hooks/             # hook unit tests
python/tests/guardrails/               # ACL matrix + agent ntfy config guard tests
scripts/healthcheck/ntfy-acl-check.sh  # new matrix rows
docs/backlog/{082,083,093}-*.md        # amendments (FR-013)
# LAB rig for the T008 gate (R-015)
.github/workflows/lab-rig.yml          # workflow_dispatch: up | deploy | status | down (down needs confirm)
.github/workflows/proxmox-apply.yml    # + first step: refuse while a held LAB rig exists; shared concurrency group
ansible/playbooks/lab_hermes_agent.yml # docker + hermes roles on lab-pve-01; loads group_vars/services via vars_files
python/tests/workflows/test_lab_rig_workflow.py  # guard test for the two workflows and the playbook
```

**Structure Decision**: No new role and no new LXC. Slice 1 touches the `ntfy` and `hermes` roles.
Slice 2 adds the relay to `monitoring_stack`, with its code in the existing `python/` package so it
inherits the test, coverage and mutation tooling.

## Rollout order (slice 1)

1. **LAB gate** (R-015), every step a `workflow_dispatch`:
   1. Deploy `ntfy` through `Prod 1 - LXC Promote` → `Prod 2 - LXC Apply` from this branch (adds
      the `hermes_lab` scratch pair; production grants unchanged). Run the ACL check script.
   2. `lab-rig.yml` `action=up`: `pve-lab run --profile hypervisor-control-plane --keep` (tier-2
      clone, kept), then check that the rig reaches ntfy and the LLM router. If either is
      unreachable, stop and raise it.
   3. `lab-rig.yml` `action=deploy`: run `lab_hermes_agent.yml` on the rig.
   4. Run quickstart § 0 from the phone: verify R-001 (a text approval prompt appears and
      `/approve` runs the command) and R-002 (`/yolo` and `/update` are refused over ntfy). If
      either fails, stop: the design depends on both.
   5. `lab-rig.yml` `action=down`, `confirm=destroy-lab-rig`.
2. ntfy deploy: new ACLs. `hermes` gets read on `hermes-in`; `owner` gets read-write on
   `hermes-in`. Run the ACL check script.
3. hermes deploy: env, config and hooks. The agent subscribes to `hermes-in`. Confirm that the
   403 warning stops (SC-004 clock starts).
4. Phone: subscribe to `hermes-in`, mute it, and run the quickstart scenarios.
5. Rotate `ntfy_hermes_token` (exposed in an earlier session's output) and confirm again.
6. Docs: amend `082` and `083`, close `093` (FR-013).

## Complexity Tracking

No constitution violations. Three choices are recorded:

| Choice | Why needed | Simpler alternative rejected because |
|---|---|---|
| Relay replaces the ntfy Go template (P2) | Server-side templates cannot emit actions (`server/types.go:140-144`) | Static `?actions=` cannot name the alert; a second "companion" message per alert doubles notifications |
| Read-only bind mounts for hooks | The agent can write `/opt/data`; hooks are Python run by the gateway | Plain files in the data dir would let a prompt-injected agent rewrite gateway code |
| Tier-2 rig template for an app deploy (R-015) | `pve-lab up` raises a clone to 4 GB / 2 vCPU only for tier ≥ 2; the hermes stack needs more than the 2 GB tier-1 template (agent `mem_limit: 3g`) | Tier 1 needs a `scripts/lab/` edit (protected path) or a post-clone `qm set` outside the ci sudoers; the rig carries nested PVE it does not use |
