# Implementation Plan: ntfy — self-hosted push notifications to the owner's phone

**Branch**: `082-ntfy-push-service` | **Date**: 2026-10-16 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/082-ntfy-push-service/spec.md`

## Summary

Run upstream ntfy (`binwiederhier/ntfy:v2.28.0`) on its own unprivileged LXC at `192.168.1.222`,
reachable as `ntfy.hus-sky.no` through Caddy on the LAN and tailnet only.

- **Access**: Access control is declarative (`deny-all`, plus users, ACLs and tokens in a vault-fed
  `server.yml`), so the service needs no backup and a rebuild is hands-off.
- **Alerts**: Alertmanager gains one ntfy webhook inside each of its three existing Pushover
  receivers, gated by `ntfy_enabled`.
- **Severity**: A custom ntfy template turns the alert payload into Pushover-style titles and
  computes the priority from severity and status. This closes the backlog's open question about
  combining `?priority=` with `?template=` (research R-003).
- **Monitoring and docs**: Liveness, metrics, the front-page card and the CI dropdowns follow the
  existing `eurooffice`/`hermes` patterns. The deliverable also includes a phone-setup runbook and a
  scripted ACL check.

## Technical Context

**Language/Version**: HCL (Terraform, `telmate/proxmox`), YAML (Ansible 2.x), Jinja2, Bash, Go
templates (one ntfy template file). No application code (FR-017).

**Primary Dependencies**: `modules/lxc_service`; `geerlingguy.docker` +
`community.docker.docker_compose_v2`; `binwiederhier/ntfy:v2.28.0`; the existing Alertmanager
`v0.30.0`, Prometheus, blackbox_exporter and Caddy.

**Storage**: SQLite message cache and auth DB under `/opt/ntfy-data` on the LXC's local disk. Both
are disposable. No NFS and no backup role (FR-014, R-008).

**Testing**: `terraform plan` scoped by the service allowlist, `ansible-playbook --check --diff`,
idempotence (a second run reports no changes), and a byte-identical Alertmanager render with the
gate off. Also the scripted ACL matrix (`scripts/healthcheck/ntfy-acl-check.sh`, SC-002), the
`amtool` synthetic alerts, and the failure-independence drill (quickstart § 5).

**Target Platform**: Debian 12 unprivileged LXC on the `pve` host. Android ntfy app (Play or
F-Droid) on the owner's phone over always-on Tailscale.

**Project Type**: Infrastructure configuration: a new service LXC plus a change to the monitoring
stack.

**Performance Goals**: Delivery to the phone within 60 s on mobile data (SC-001). Volume is a
handful of messages a day.

**Constraints**: LAN/tailnet only. No content leaves the estate (FR-004). Pushover is never
degraded by an ntfy failure (R-005). Templated input is capped at 32 KB, with at most 10 alerts per
group (R-004).

**Scale/Scope**: 1 subscriber, 2 publishers, 2 topics.

No NEEDS CLARIFICATION remains. Every unknown was resolved in [research.md](./research.md).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Status | How |
|---|---|---|
| I. Spec-driven | ✅ | Work flows from `specs/082-ntfy-push-service/`. `tasks.md` follows from `/speckit-tasks` |
| II. Secrets | ✅ | Six secrets go in the encrypted `group_vars/services/vault.yml` (R-012). `server.yml` is rendered at mode 0600 and not committed. The compose file has no secrets. No plaintext owner password anywhere |
| III. Separation of concerns | ✅ | Terraform: `terraform/services/ntfy/` creates and sizes the LXC only. Ansible: everything inside it, plus the Alertmanager change |
| IV. Code economy | ✅ | No backup role (R-008). No dashboard (R-006). One template file instead of three receivers (R-003). Webhooks are added to existing receivers, not new routes. One new flag (`ntfy_enabled`), justified by rollout ordering and the byte-identical-render check, which mirrors `pushover_enabled`. `ntfy_users` is a loop over 3 items (> 1, so justified) |
| V. Dual-provisioning parity | ✅ | `ntfy` is added to the `lxc-deploy-lab`, `lxc-promote-lab` and `lxc-promote-prod` dropdowns and to `service-scope-allowlist.json` in the same PR. Every step runs locally with the same `pve-service-deploy` and `ansible-playbook` arguments |
| Networking: central IPs | ✅ | `ntfy_ip` in `group_vars/services/vars.yml`, `service_ips.ntfy` in both tfvars templates (081 not started, R-010) |
| Access: no public exposure | ✅ | No port forward, and no DNS record created. The existing public wildcard `*.hus-sky.no` resolves only to Caddy's private address (`docs/network-layout.md`), so there is no route from the internet. Caddy `user_facing` follows the same LAN/tailnet model as every other service (FR-003) |
| Test-driven changes | ✅ | Plan-only and `--check` first. Scripted ACL check. Gate-off diff. Drills in quickstart |
| Token privilege tiers | ✅ | No new Proxmox credentials. The LXC goes through the Tier 1 Terraform path. No `features_mount` and no bind mount, so Tier 2 is not exercised |

**Post-design re-check (after Phase 1)**: ✅ No violations. Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/082-ntfy-push-service/
├── spec.md
├── plan.md                      # this file
├── research.md                  # R-001 … R-013
├── data-model.md                # accounts, topics, ACL matrix, alert→notification mapping
├── quickstart.md                # validation runbook (LAB → PROD)
├── contracts/
│   ├── server-config.md         # server.yml required, default and forbidden keys
│   ├── alertmanager-webhook.md  # receiver change, gate, template output
│   ├── publisher-interface.md   # how any sender publishes (consumed by 083)
│   └── monitoring-contract.md   # host_vars/ntfy.yml
├── checklists/requirements.md
└── tasks.md                     # /speckit-tasks (not created here)
```

### Source Code (repository root)

```text
terraform/
├── services/ntfy/main.tf                    # NEW  module "ntfy_lxc" (1 core, 512 MB, 8 GB)
├── services/ntfy/outputs.tf                 # NEW  ansible_inventory output
└── environments/{lab,prod}.tfvars.template  # EDIT service_ips.ntfy = 192.168.1.222/24

ansible/
├── inventories/prod/hosts.yml               # EDIT add ntfy under services (required for monitoring, R-010)
├── group_vars/services/vars.yml             # EDIT ntfy_version, ntfy_ip, ntfy_port, ntfy_metrics_port,
│                                            #      caddy_services entry (cache duration inlined in server.yml.j2)
├── group_vars/services/vault.yml            # EDIT (encrypted) six ntfy_* secrets
├── group_vars/monitoring/vars.yml           # EDIT ntfy_enabled
├── host_vars/ntfy.yml                       # NEW  healthcheck + monitoring_contract
├── playbooks/ntfy.yml                       # NEW  lxc_base → geerlingguy.docker → ntfy
└── roles/
    ├── ntfy/                                # NEW
    │   ├── defaults/main.yml                # dirs, image, ntfy_users (accounts/topics)
    │   ├── tasks/main.yml
    │   ├── tasks/preflight.yml              # vault vars present; token/hash format; FR-004 forbidden keys
    │   ├── handlers/main.yml
    │   ├── templates/docker-compose.yml.j2
    │   ├── templates/server.yml.j2
    │   └── files/homelab-alertmanager.yml   # Go template, copied verbatim
    └── monitoring_stack/templates/alertmanager.yml.j2   # EDIT webhook_configs ×3, gated

scripts/
├── healthcheck/ntfy.sh                      # NEW  per-service healthcheck wrapper (eurooffice pattern)
├── healthcheck/ntfy-acl-check.sh            # NEW  SC-002 access matrix
└── lab/service-scope-allowlist.json         # EDIT "ntfy": ["module.ntfy_lxc"]

.github/workflows/
├── lxc-deploy-lab.yml                       # EDIT dropdown
├── lxc-promote-lab.yml                      # EDIT dropdown
└── lxc-promote-prod.yml                     # EDIT dropdown

docs/
├── runbooks/ntfy-phone-setup.md             # NEW  FR-015
└── backlog/backlog.md, 082-…md              # EDIT status → specced
```

**Structure Decision**: Follow the latest single-service pattern (`hermes` for Terraform layout,
`eurooffice` for the Ansible role shape). The Alertmanager change goes into the existing template
rather than a new role. Nothing is added to `terraform/main.tf`.

## Delivery order

1. Vault secrets → Terraform (LAB) → `ntfy` role → ACL check (quickstart § 1–2).
2. `ntfy_enabled: true` → monitoring playbook → synthetic alerts (§ 3).
3. Promote to PROD → phone setup and delivery tests (§ 4) → failure drill (§ 5) → rebuild (§ 6).
4. Hand `ntfy_hermes_token` to `083`. Start the 4-week trial clock (SC-006).

## Risks

| Risk | Mitigation |
|---|---|
| A failing ntfy webhook delays Pushover, as the email receiver once reportedly did | Drill in quickstart § 5. Fallback: move the webhook to a separate `continue: true` route (R-005) |
| A large alert group exceeds ntfy's templated-body limit | `message-size-limit: 32k` and `max_alerts: 10`, verified with a 10-alert group (R-004) |
| Android kills the persistent connection | Battery exemption in the runbook. Overnight test (SC-005) |
| Host missing from the prod inventory silently disables monitoring | Inventory edit is part of the change. Prometheus targets check in quickstart (R-010, backlog 066) |

## Complexity Tracking

No violations to justify.

## Outcome (2026-10-17)

Delivered as planned, with these deviations and findings:

- **Code fixes found before or during deploy** (Phases 8–11 in `tasks.md`): the `server.yml` auth
  lists and the alert template's file format; the `NtfyDown` rule shape; the ACL script's read
  path; `loop:` indentation in preflight; the forbidden-key gate made check-mode safe and run
  before start; the Alertmanager comment made a Jinja comment so the gate-off render stays
  byte-identical.
- **No SSH from the dev box to any LXC.** Every Ansible run went through the pipeline: the ntfy
  role via `lxc-deploy-lab`/promote/apply, Caddy via `lxc-deploy-lab` with service
  `reverse_proxy`, and monitoring via `lxc-promote-prod` with the LAB-gate override.
  Verification ran over HTTP: Prometheus and Alertmanager APIs, and ntfy through Caddy. T026
  and T041 were accepted without running.
- **R-005 resolved in favour of the shared receiver**: Pushover latency was identical with ntfy
  down and up (31 s each).
- **WebSockets** in the Android app work through Caddy unchanged and are now in the runbook.
- **Trial (SC-006)** runs from 2026-10-17 to 2026-11-14. After that, decide whether to drop
  Pushover.
