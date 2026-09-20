# Implementation Plan: Hermes — a self-hosted AI workspace on local models

**Branch**: `065-hermes-ai-workspace` | **Date**: 2026-09-20 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/065-hermes-ai-workspace/spec.md`

## Summary

Deploy an established open-source AI workspace (**Open WebUI**) onto a new unprivileged LXC at
`192.168.1.221`, configured to reach models only through the `064` gateway, to call the homelab's
MCP servers, and to serve a public, self-authenticating web app at `hermes.hus-sky.no` that is
usable and installable on a phone.

**The feature is configuration, not code** (FR-026). Every requirement is met by settings on
unmodified upstream software plus the estate's existing Terraform module, Ansible patterns, reverse
proxy, monitoring contract and backup mechanism. The only genuinely new artifacts are one Ansible
role, one backup role, and the registration entries a new service needs.

Two pieces of work fall **outside** the new machine: adding embedding and reranking models to the
inference host, and amending `064` to expose them as capability aliases the Hermes key may use.

## Technical Context

**Language/Version**: No application code (FR-026) — configuration only: HCL, YAML (Ansible 2.x), Jinja2
**Primary Dependencies**: `modules/lxc_service` (Terraform); `geerlingguy.docker` + `community.docker.docker_compose_v2` (Ansible); Open WebUI and SearXNG images pinned non-`latest`; the `064` gateway; oMLX embedding + reranker models on the inference host
**Storage**: SQLite + vector store on the LXC's local disk, bind-mounted for backup to Synology; no NFS for state (FR-019)
**Testing**: Non-destructive validation — `pve-service-deploy plan`, Ansible preflight assertions, `act -l` — plus the drills in quickstart.md
**Target Platform**: Debian LXC on Proxmox, unprivileged, containers via Docker
**Project Type**: Infrastructure service — one LXC per service; no application source tree
**Performance Goals**: A single response may take 20 minutes without truncation (FR-021, SC-009); failure surfaces in under 10s when models are absent (SC-005)
**Constraints**: No prompt, document or audio content leaves the estate (FR-008, FR-016, SC-012); no bespoke application code (FR-026, SC-011); stay inside the gateway request allowance (FR-011, SC-008)
**Scale/Scope**: One user; one LXC, two containers, two new capability aliases on the gateway

## Constitution Check

*GATE: evaluated before Phase 0 and re-evaluated after Phase 1.*

| Principle | Assessment |
|---|---|
| **I — Spec-Driven Workflow** | PASS. Driven from `specs/065-hermes-ai-workspace/`. The `064` amendments this needs are recorded here and will appear in `tasks.md`, not made ad hoc. |
| **II — Secrets Policy** | PASS, with one caveat. The gateway client key, any MCP credential and the admin bootstrap credential come from the vault. **Caveat**: the `financial-scenario` MCP secret is baked into a third-party image and is *not* ours to hold — see Complexity Tracking. No secret is committed. |
| **III — Separation of Concerns** | PASS. Terraform owns the LXC's existence, sizing, static IP and SSH keys. Ansible owns everything inside it. No mixing. |
| **IV — Code Economy (YAGNI)** | PASS with two declared tensions — see Complexity Tracking. SearXNG is a sidecar rather than a service precisely to honour this. |
| **V — Dual-Provisioning Parity** | PASS, and it is a hard gate: a new service must be registered in **eight** places in the same PR (listed under Project Structure). Partial registration is a parity violation, not a follow-up. |
| **Networking** | PASS. Static `192.168.1.221`, defined centrally in the environment tfvars, never scattered. |
| **Access Control** | PASS. Terraform injects `ssh_public_keys`; no public SSH route (FR-006). |
| **Token Privilege Tiers** | PASS. Tier 1 for Terraform, Tier 2 for the orchestrator's post-create step. Tier 3 is not referenced. |
| **CI/CD Expectations** | PASS. Plan → apply → Ansible through the existing pipeline. |
| **Local Workflow Testing** | GATE. This feature edits `.github/workflows/*.yml` (service dropdowns), so `act -l` must run before the cycle closes, or the reason it could not must be documented. |

**Post-Phase-1 re-evaluation**: unchanged. The design added no new abstraction, no new indirection
layer and no new service beyond the one the feature is. Both Code Economy tensions were already
declared before design and neither grew.

**Post-decision re-evaluation (2026-09-20)**: the MCP scope decision narrows the feature and adds
nothing, so no gate moves. Principle I is worth re-checking specifically, since shipping a
requirement only partly exercised risks drifting from the spec: FR-012 is **not** being reduced —
the credential path is still built and asserted in preflight — only its demonstration is deferred,
and that is recorded against the acceptance scenario rather than left implicit.

## Project Structure

### Documentation (this feature)

```text
specs/065-hermes-ai-workspace/
├── plan.md              # This file
├── research.md          # Phase 0 — decisions, with one unresolved item escalated
├── data-model.md        # Phase 1 — configuration entities and their rules
├── quickstart.md        # Phase 1 — deploy, verify, and the drills that prove the spec
├── contracts/
│   ├── monitoring.md    # signals, severities, alert rules
│   └── gateway-usage.md # how this feature consumes and amends 064
├── checklists/
│   └── requirements.md  # spec quality checklist (from /speckit.specify)
└── tasks.md             # Phase 2 — NOT created by /speckit.plan
```

### Repository changes (real paths)

```text
terraform/
├── environments/{lab,prod}.tfvars.template     # + hermes = "192.168.1.221/24"
└── services/hermes/                            # per-service root, mirroring llm-router

ansible/
├── group_vars/services/vars.yml                # + hermes_* settings, caddy_services entry
├── group_vars/services/vault.yml               # + hermes admin + gateway client credentials
├── host_vars/hermes.yml                        # + monitoring contract and alert rules
├── playbooks/hermes.yml                        # new service playbook
└── roles/
    ├── hermes/                                 # compose stack, config, preflight
    │   ├── defaults/main.yml
    │   ├── tasks/{main,preflight}.yml
    │   └── templates/docker-compose.yml.j2
    └── hermes_backup/                          # follows financial_scenario_backup
        ├── tasks/main.yml
        └── templates/backup_hermes.sh.j2

.github/workflows/                              # + hermes in the service dropdowns
└── {lxc-deploy-lab,lxc-promote-lab,lxc-promote-prod}.yml

scripts/lab/service-scope-allowlist.json        # + hermes scope prefixes
```

**Structure Decision**: This is an infrastructure feature, so none of the template's application
layouts apply. The structure follows the estate's one-LXC-per-service model exactly as
`llm-router`, `financial-scenario` and `market-model` do: a per-service Terraform root for
existence and sizing, an Ansible role for configuration, a sibling backup role, a monitoring
contract in `host_vars`, and registration in the eight places Constitution V requires.

### The eight registration points (Constitution V)

`terraform/environments/lab.tfvars.template` · `prod.tfvars.template` ·
`.github/workflows/lxc-deploy-lab.yml` · `lxc-promote-lab.yml` · `lxc-promote-prod.yml` ·
`scripts/lab/service-scope-allowlist.json` · `ansible/playbooks/hermes.yml` ·
`terraform/services/hermes/`.

## Work outside the new machine

Two dependencies are not deployments of this LXC and must be sequenced before the retrieval
acceptance criteria can pass:

1. **Inference host** — load an embedding model and a reranker into oMLX and expose them through the
   Mac's own gateway. New Mac-side configuration.
2. **`064` amendment** — add the two capability aliases, extend the Hermes client key's permitted
   model scope to include them, and update `064`'s preflight and doctor accordingly. This is a
   change to a closed feature and must be recorded there, not only here.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| **A fifth near-identical backup role** (`hermes_backup`, joining four others of ~55 lines each with the same shape) | The feature needs backup, and the established pattern is one role per service | A single parameterised backup role is now clearly the right refactor — there would be five consumers, which passes Constitution IV's own ">1 concrete consumer" test. **Rejected for this feature only** because consolidating four working roles is a refactor of other services' code, outside this scope and a worse change to review. **Recommended as its own backlog item.** |
| **An internet-facing service whose only access control is its own login** | The owner chose public reachability for mobile use, and the estate's proxy provides no authentication | An estate-wide `forward_auth` layer is the correct answer and would benefit every public service. Rejected here because it is a separate feature touching the proxy the whole estate depends on. Recorded as the spec's principal risk, not hidden. |
| **Shipping with one MCP server instead of two** (research R-008) — **DECIDED 2026-09-20: ship with `market-model` only** | `financial-scenario`'s gate uses a secret baked into a third-party image that this repo does not hold, and making it configurable needs an upstream change | Extracting the baked secret works today but depends on an unmanaged image internal and breaks silently on the next bump. **Consequence accepted**: FR-012's credentialed path is built and configured but **unexercised at launch**, so spec US-3 AS-2 is not-verifiable — recorded as such, not dropped. Adding the second server later is one list entry plus a vault variable, which is itself the test of FR-013. |
