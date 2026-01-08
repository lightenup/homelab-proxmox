# Spec 023: Hardening Gated LXC Deploy (Child of 022)

**Parent**: 022-lxc-gated-deploy

## Problem Statement
- In 022 we hit Proxmox privilege limits for host-path bind mounts (requires root@pam), masking drift with targeted plans, and lacked blast-radius gating.
- Shared media storage must be consumable across services without host-path binds.
- Evidence and gating must be strengthened for destructive operations and mount policy.

## Goals
- Full-plan, least-privilege gated pipeline for a single LXC service (e.g., Jellyfin) with durable evidence.
- Avoid Proxmox host-path binds; mount shared NFS inside containers (`/media/video`, read-only) for reuse across services.
- Enforce gates: no `-target`, service scope allowlist, bind-mount policy guard, blast-radius confirmations before apply (LAB/PROD), destructive confirmations.
- Evidence verified offline; healthchecks include mount validation.

## Non-Goals
- No change to Terraform backend location (state stays local on PVE).
- No root@pam tokens in normal path; no host-path bind mounts in Terraform.
- No multi-service apply per run.

## State Backup (Constitution Gate)
- After any successful `apply` (LAB and PROD), the Terraform state used for that run MUST be backed up to Synology.
- This MUST work with the standardized per-service state path:
	`/var/lib/homelab-proxmox/state/services/<service>/terraform.tfstate`.

## Architecture / Flow (text)
1) GH Actions workflow `lxc-deploy.yml` (plan, apply_lab, apply_prod) orchestrates via `scripts/lab/pve-service-deploy` on PVE.
2) Terraform runs on PVE with local state at `/var/lib/homelab-proxmox/state/services/<service>/terraform.tfstate`.
3) Orchestrator gates: refuse `-target`, enforce service scope allowlist, fail on host-path mp binds, emit blast-radius summary.
4) Evidence per RUN_ID under `/var/lib/homelab-proxmox/artifacts/service-deploy-runs/<RUN_ID>/`; verified offline with `scripts/lab/ci-verify.sh`.
5) Ansible mounts NFS inside the container to `/media/video` via shared role; Jellyfin depends on it; healthcheck validates mount and service.

## Workflow Logic
- Inputs: `environment` (lab|prod), `service`, `confirm` (prod), `confirm_destructive` (when plan has replace/destroy).
- plan (PR/dispatch): full plan only; scope/bind guards; evidence + offline verify.
- apply_lab: requires destructive confirm if needed; runs apply + idempotency re-apply; evidence verified.
- apply_prod: GitHub Environment approval + confirm strings; runs plan+apply; evidence verified.
- Any targeted plan detected => fail with clear message.

## Evidence Pack (required)

### Plan evidence (required for plan + apply)
- provenance.json (git SHA, dirty flag, runner, env, service, RUN_ID)
- reports/plan/plan.txt (full plan text; no `-target`)
- reports/plan/plan.json (full plan JSON; no `-target`)
- blast-radius.json (create/update/replace/destroy counts, list, destructive flag)
- preflight.txt (mount readiness, scope, bind policy results)
- reports/verify.json (output from offline verification)

### Apply evidence (required for apply_lab + apply_prod)
- reports/assertions.*.json (NFS mount checks emitted as Ansible assertions + referenced by checks)
- healthcheck.txt (container up, `/media/video` present & ro, service port)

## Orchestrator Changes (`scripts/lab/pve-service-deploy`)
- Commands: `plan`, `apply`; structured RUN_ID (format defined in tasks; deterministic components + UTC timestamp for uniqueness).
- RUN_ID MUST include: environment, service, git SHA prefix, and UTC timestamp.
- RUN_ID MUST be unique per run (no collisions allowed).
- Enforce no `-target`, scope allowlist, host-path bind rejection.
- Generate blast-radius summary and destructive signal for workflow gating.
- Ensure state path exists; emit evidence (plan, preflight, blast, provenance).

## Bind-Mount Policy (Terraform)
- Terraform MUST NOT set any LXC `mpX` mountpoint to a host filesystem path.
- Treat any `mpX` source beginning with `/` as a policy violation (examples: `/mnt/...`, `/srv/...`).
- Storage-backed mount specifications (e.g., `local-lvm:...`) are allowed.

## Service Scope Allowlist
- Service scoping MUST be defined in a single canonical mapping (checked into the repo) and loaded by the orchestrator.
- Mapping schema MUST be a JSON object: `{ "<service>": ["<allowed_prefix>", ...] }` (example: `{ "jellyfin": ["module.jellyfin_lxc"] }`).
- Scope guard rule: every planned resource change address MUST start with one of the allowed prefixes for that service.
- Match semantics: prefix match against the full Terraform address; case-sensitive; at least one prefix required per service.

## Least-Privilege Control
- “No root@pam tokens” is enforced by workflow guardrails (non-root SSH user; deny sudo shell escalation) in addition to the Terraform/plan policy guards.

## Shared NFS Mount Role (`ansible/roles/shared_nfs_mount`)
- Install `nfs-common`.
- Mount `192.168.1.109:/volume1/video` to `/media/video` with `ro,nofail,_netdev,x-systemd.automount`.
- Collect mount/findmnt evidence into run directory.

## Jellyfin Example
- Jellyfin playbook/role includes `shared_nfs_mount` and uses `/media/video` (RO).
- Healthcheck asserts container up, mount RO, service port responsive; output saved to evidence.

## Implementation Plan
- Update `.github/workflows/lxc-deploy.yml` (inputs, gating, artifact fetch/verify, destructive confirmations, no-target guard).
- Enhance `scripts/lab/pve-service-deploy` (state path, guards, blast summary, evidence emission).
- Add `ansible/roles/shared_nfs_mount`; wire Jellyfin to it.
- Update Jellyfin healthcheck script to cover mount RO + service port.
- Update docs `docs/operations/lxc-deploy-ci.md` (split, shared mount pattern, destructive gates, act usage, state/evidence locations).

## Tests / Validation
- `act` plan run (lab) with secrets; evidence verification must pass.
- CI plan must fail if `-target`, host-path bind, or scope violation occurs.
- apply_lab: create Jellyfin LXC, second apply no-op, healthcheck passes and mount is RO.
- apply_prod (simulated): destructive plans require `confirm_destructive`.

## Rollback / Safety
- Surface blast radius pre-apply; advise snapshots when replaces/destroys present.
- Evidence retains plan/blast/preflight for manual rollback; state stays on PVE.
- If a host bind is attempted, fail early rather than proceed with privileged tokens.
