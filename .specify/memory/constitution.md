# Homelab Proxmox Constitution

## Core Principles

### I. Spec-Driven Workflow
All feature work must be driven from `specs/NNN-*/` directories and must reference that spec’s `tasks.md`. The `.specify/memory/constitution.md` and `spec.md` are the sources of truth. Do not implement changes that are not represented in an approved `tasks.md`. If a change alters behaviour/architecture, update the relevant spec/docs in the same change.

### II. Secrets Policy (NON-NEGOTIABLE)
Never commit secrets: Proxmox tokens, passwords, private keys, Synology creds, Tailscale auth keys. Use local `*.tfvars` (gitignored) and/or environment variables for secrets. Copilot must not output real secrets; use placeholders and describe where they come from.

### III. Separation of Concerns
- **Terraform** owns *existence and sizing* of machines (LXCs/VMs) and base provisioning.
- **Ansible** owns *configuration inside* those machines and on the Proxmox host.
**Do not generate code that mixes these responsibilities.**

### IV. Code Economy (YAGNI)
Every line of code, every file, every abstraction layer must justify its existence against a current requirement — not a hypothetical future one. Specifically:

- **Prefer modifying an existing file over creating a new one.** A new file is justified only when separation of concerns demands it or the existing file would become incoherent.
- **Do not add indirection layers** (wrapper functions, abstract base classes, plugin systems, factory patterns) unless at least two concrete consumers exist today. "We might need this later" is not justification.
- **Do not generate scaffolding, boilerplate, or stub files** for functionality that is not in the current task list. Empty `__init__.py` files, placeholder roles, and skeleton modules are bloat.
- **Prefer inline configuration over parameterization.** Extract a value into a variable only when it is referenced in more than one place or must differ between environments. A single-use variable with a default that is never overridden is noise.
- **Templating and abstraction earn their keep.** A Jinja2 loop over a list is justified when the list has >1 item today. A loop over a list with exactly 1 item is premature abstraction.
- **Consolidate before adding.** Before creating a new alert rule, dashboard, role, or module, check whether an existing one can be extended. The cost of a new artifact is not just its lines — it is ongoing maintenance, cognitive load, and drift risk.

Violation of this principle produces codebases that are harder to understand, slower to change, and more fragile than the problem warrants. When in doubt, ship less.

### V. Dual-Provisioning Parity
Every provisioning and deployment operation MUST be executable through **both** CI/CD (GitHub Actions) **and** from a developer laptop. Neither path may have capabilities the other lacks.

- New services must be added to the GitHub Actions workflow dropdowns and service scope allowlist **in the same PR** that introduces the service.
- Scripts invoked by CI (e.g., `pve-service-deploy`) must also run locally with the same arguments. Hardcoded CI-only paths or runner-only assumptions are prohibited.
- Secrets must be accessible in both contexts: vault files on PVE for CI, local `vault.yml` (gitignored) or environment variables for laptop runs.
- If a step only works in one context (e.g., requires a self-hosted runner network), document the limitation and provide an equivalent local alternative.

## Architecture & Boundaries

### Provider Strategy
- Use the `telmate/proxmox` provider (`proxmox_lxc`).
- Do not rewrite Terraform to `bpg/proxmox` resources unless a spec explicitly requests a migration.

### Networking
- Core service LXCs (Immich, Home Assistant, reverse proxy, and the rest) must have **static IPs** + gateway.
- Avoid scattering IP strings across files: define them centrally (variables/locals) and pass into modules.
- Target network is eventually segmented (Management, Services, LAN, IoT, VPN egress).

### Access Control
- Terraform must inject SSH public keys into LXCs (`ssh_public_keys`) so Ansible can connect without passwords.
- Ansible initially uses `root` for bootstrapping (homelab tradeoff).
- Do not expose Proxmox UI publicly on the internet. Prefer Tailscale for remote admin.

### Token Privilege Tiers

All automated operations use a three-tier privilege model. No tier may be substituted for another.

| Tier | Credential / Grant | Scope | Used By |
|------|--------------------|-------|---------|
| **1** | `terraform@pve` API token | Create/update/destroy LXC resources via Proxmox API | Terraform (`pve-service-deploy plan/apply`) |
| **2** | Orchestrator `sudo pct` (sudoers rule, no password) | Post-create LXC configuration: bind mounts, feature flags | `pve-service-deploy` orchestrator post-create steps |
| **3** | `root@pam!rebuild` API token | Break-glass disaster recovery only | Manual rebuild operations |

**Invariant rules**:
1. Tier 1 is the only credential passed to Terraform. No `root@pam` token in Terraform configurations.
2. Tier 2 is exercised only by the orchestrator post-create step (`pct set` via `sudo`). Never used for Terraform.
3. Tier 3 is never referenced in automated flows (CI/CD). Manual use only for disaster recovery.

**Enforcement**: Enforced by `scripts/lab/ci-validate-iac.sh` (Tier 1 boundary — rejects `root@pam` in any `.tf` file) and orchestrator bind-mount allowlist (Tier 2 boundary — for `prod`, rejects host paths outside `/mnt/nas/`; for `lab` (067), allows only `/var/lib/homelab-proxmox/lab-scratch/` and rejects `/mnt/nas/`, so an isolated lab copy can never mount production data).

## Baseline Decisions

### State Management
- Terraform state is **local** on the Proxmox (PVE) host.
- State must be backed up to Synology after successful apply (via script/workflow). Do not introduce remote state unless explicitly requested.

### Storage
- Immich user data lives on Synology NAS.
- Initial approach: NFS mounts on Proxmox host, bind-mounted into unprivileged LXCs (Ansible + Terraform managed).
- No Ceph and no unnecessary storage complexity for v1.

### Services Model
- General model: one LXC per service (Debian stable).
- The authoritative list of services and their responsibilities lives in `specs/002-core-services-lxc/spec.md`.
- Do not assume a service exists unless it is defined in the current spec/tasks.

## Workflow & Process

### Test-Driven Changes (NEW FUNCTIONALITY)
- New functionality SHALL include non-destructive validation steps (e.g., plan-only or dry-run checks) executed during development.
- When feasible, add automated tests (unit or integration). If not feasible, document the reason in the spec/tasks or work notes.
- Prefer implementations that support unit testing (e.g., Python modules with mock/fake support) over opaque shell-only logic.

### CI/CD Expectations
- Pipeline should: Validate/plan Terraform -> (Optional) lint Ansible -> Apply Terraform -> Run Ansible.
- Avoid adding destructive automation without clear barriers (e.g. approvals, prevent_destroy).

### Local Workflow Testing
- `act` is an approved tool for running GitHub Actions workflows locally during development.
- When modifying `.github/workflows/*.yml`, you SHOULD validate the workflow with `act` before closing an implementation cycle (when `act` + Docker are available).
	- Minimum check: `act -l` (ensures workflows parse and events like `workflow_dispatch` are recognized).
	- If you changed a specific workflow: `act -n -W .github/workflows/<file>.yml workflow_dispatch` (or the relevant event).
	- If it’s not feasible (e.g. no Docker daemon, `act` not installed), document the reason in the PR/work notes.
- Keep any `act` runner artifacts local-only (gitignored).

### Repo Layout
- `docs/` – architecture and network docs.
- `terraform/` – providers, root module, `modules/lxc_service`.
- `ansible/` – inventories, group vars, roles, playbooks.
- `.github/workflows/` – CI and deploy pipelines.
- `scripts/` – helper scripts.

## System Roles & Interoperability

### Spec Kit — Workflow System
Spec Kit owns the workflow definition: stages, artifact formats, templates,
shell scripts, and directory conventions. The `.specify/` directory and
`.github/agents/` files are Spec Kit's domain.

**Rules:**
- Feature directories follow `specs/NNN-feature-name/` naming.
- Git branches should follow `NNN-feature-name` convention for feature work.
- Shell scripts in `.specify/scripts/bash/` are authoritative for scaffolding
	(branch creation, template copying, prerequisite checks). Use them — do not
	replicate their logic.
- Templates in `.specify/templates/` define artifact structure. Follow them.

### Droid — Execution Engine
Droid executes work defined by Spec Kit artifacts. It reads prompts, produces
code and documents, runs commands, and marks tasks complete.

**Rules:**
- Droid runs non-interactively via `droid exec -f <prompt> --auto <level>`.
- When instructions say "ask the user" or "wait for response," make an informed
	decision from available context and document the choice.
- Droid MUST NOT create alternative directory structures, artifact formats,
	or workflow conventions that conflict with Spec Kit's expectations.
- Droid uses `--auto medium` by default. Production operations (push, deploy)
	require `--auto high`.

### Adapter — Interface Translation
The adapter (`adapter/speckit-droid-adapter`) translates Spec Kit's interactive
agent interface into droid's non-interactive execution model. It is stateless
and mechanical.

**Rules:**
- The adapter MUST NOT add workflow stages, templates, or artifact formats.
- The adapter MUST NOT make decisions about what to run or in what order.
- The adapter's only job: prepend a non-interactive preamble, load the
	appropriate persona, substitute `$ARGUMENTS`, and invoke `droid exec`.

## Personas

Each pipeline stage is executed under a specific persona that constrains the
agent's perspective, vocabulary, and decision-making frame. Persona files live
in `adapter/personas/` and are prepended to the prompt by the adapter.

| Persona | Stages | Focus |
|---------|--------|-------|
| **Analyst** | specify, clarify | Requirements, user stories, acceptance criteria |
| **Architect** | plan, tasks, checklist, analyze | Design, structure, decomposition |
| **Developer** | implement | Code, tests, build, run |
| **Reviewer** | review | Spec compliance, quality, feedback loops |

The reviewer persona enables an implement → review → re-implement loop (max 3
iterations) to converge on quality before declaring a feature complete.

## Precedence
- On **workflow concerns** (stages, artifacts, directory layout): Spec Kit wins.
- On **execution concerns** (how commands run, autonomy levels): Droid wins.
- On **process concerns** (transparency, scope discipline, verification):
	this constitution wins.
- On **technology-specific concerns**: the project addendum wins (if present,
	placed at `.specify/memory/addendum.md`).

## Governance
This constitution supersedes all other practices. Amendments require documentation and approval. All PRs and reviews must verify compliance with these principles.

**Version**: 1.5.0 | **Ratified**: 2026-02-22 | **Last Amended**: 2026-10-30
