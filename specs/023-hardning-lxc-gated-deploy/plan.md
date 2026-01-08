# Plan: 023 Hardening Gated LXC Deploy

Parent: 022-lxc-gated-deploy

## Outcome
Deliver a “v2” gated LXC deploy pipeline that:
- Runs **full Terraform plans only** (no `-target`).
- Enforces **service scope** (plan may only touch the selected service).
- Enforces **no host-path bind mounts** (no `mp0=/mnt/...` / raw host binds in Terraform).
- Adds a **blast-radius gate** (confirm strings required when replace/destroy present).
- Mounts shared media NFS **inside the container** at `/media/video` (read-only), reusable across services.
- Produces durable evidence packs on PVE and verifies them offline on the runner.
- Backs up Terraform state to Synology after successful apply (LAB and PROD).

## Phases

### Phase 0 — Baseline inventory (no behavior change)
1. Identify the current workflow/orchestrator responsibilities and where plan/apply arguments are assembled.
2. Identify the current evidence pack structure and verification expectations (`scripts/lab/ci-verify.sh`).
3. Identify how service scoping is currently implemented (allowlist definition and parsing).

Deliverables:
- Notes captured in this spec folder (optional) or directly applied in Phase 1.

### Phase 1 — Orchestrator hardening (policy + evidence)
Implement in `scripts/lab/pve-service-deploy`:
1. **Full-plan enforcement**
   - Detect `-target` usage (inputs/env/args) and fail with actionable message.
   - Write failure reason into evidence preflight output.
2. **Service scope guard**
   - Parse terraform plan (json) and ensure only resources in the selected service allowlist are touched.
   - Define the allowlist via a single canonical mapping file committed to the repo.
   - Fail fast and record offending resources in evidence.
3. **Bind-mount policy guard**
   - Parse plan json for `mp0/mp1/...` changes and fail if the source is a host filesystem path (treat any source starting with `/` as disallowed).
   - Policy target: *Terraform must not model host-path binds.*
4. **Blast radius summary**
   - From plan json compute create/update/replace/destroy counts + resource list.
   - Emit `blast-radius.json` and a simple “destructive” signal for the workflow to enforce.
5. **State path standardization**
   - Ensure state is stored at `/var/lib/homelab-proxmox/state/services/<service>/terraform.tfstate`.
6. **Deterministic RUN_ID**
    - Define and implement a structured RUN_ID format with deterministic components plus a UTC timestamp for uniqueness (e.g., `${ENV}-${SERVICE}-${GIT_SHA:0:8}-${UTC_TS}`).
7. **State backup after apply (Synology)**
   - After successful `apply`, back up the per-service state file to Synology and record proof in evidence.
8. **Evidence completeness**
    - Ensure evidence includes: provenance, plan txt+json, preflight, blast-radius summary, and offline verification output (`reports/verify.json`).
    - Apply runs additionally include healthcheck output and assertion report(s) under `reports/assertions.*.json`.

Deliverables:
- Updated orchestrator with guards and evidence outputs.

### Phase 2 — Workflow gating updates (GH Actions)
Update `.github/workflows/lxc-deploy.yml`:
1. Inputs
   - `environment` (lab|prod)
   - `service`
   - `confirm` (prod)
   - `confirm_destructive` (conditional)
2. Job structure
   - `plan` job safe on PR/dispatch (no mutation).
   - `apply_lab` on `workflow_dispatch` with `environment=lab`.
   - `apply_prod` on `workflow_dispatch` with `environment=prod` + GitHub Environment approval.
3. Destructive gating
   - If plan indicates replace/destroy, require:
     - LAB: `confirm_destructive=apply-lab-destructive`
     - PROD: `confirm=deploy-prod` and `confirm_destructive=deploy-prod-destructive`
4. Evidence handling
   - Fetch evidence pack from PVE and run offline verification (`scripts/lab/ci-verify.sh`) before marking success.
5. Guardrails
   - Ensure workflow never passes `-target` to orchestrator.

Deliverables:
- Updated workflow aligning with policy gates and evidence requirements.

### Phase 3 — Shared NFS mount inside container (Ansible)
Create `ansible/roles/shared_nfs_mount`:
1. Install `nfs-common`.
2. Configure `/etc/fstab` (or systemd mount unit) to mount:
   - `192.168.1.109:/volume1/video` → `/media/video`
   - Default options: `ro,nofail,_netdev,x-systemd.automount`
3. Evidence capture
   - Collect `findmnt` and `mount` output into the run evidence directory.

Deliverables:
- New role that is generic and reusable by other services.

### Phase 4 — Jellyfin wiring + healthcheck evidence
1. Ensure the Jellyfin Ansible role/play includes `shared_nfs_mount`.
2. Update Jellyfin healthcheck to validate:
   - container up
   - `/media/video` exists and is mounted read-only
   - Jellyfin responds on expected port
3. Write healthcheck output into evidence pack.

Deliverables:
- Jellyfin uses in-container shared NFS mount.
- Healthcheck evidence includes mount validation.

### Phase 5 — Documentation update
Update `docs/operations/lxc-deploy-ci.md`:
- Platform vs workload responsibility split.
- Shared media mount pattern (in-container NFS, no host binds in Terraform).
- Destructive blast-radius gate and required confirm strings.
- Local `act` usage (`--secret-file .act.secrets`, `.act-ssh` mounts).
- Where state and evidence live on PVE.

Deliverables:
- Updated runbook consistent with v2 behavior.

## Validation Plan
- `plan` job:
  - Succeeds and produces verified evidence.
  - Fails with clear message if `-target` is attempted.
  - Fails if plan touches outside service allowlist.
  - Fails if plan includes host-path bind mount(s).
- `apply_lab` job:
  - Applies successfully.
  - Second apply is no-op (idempotency assertion).
  - Evidence verified offline.
- Shared mount:
  - `/media/video` mounted read-only inside container.
  - Evidence includes `findmnt`/`mount` proof.

## File Checklist
- `.github/workflows/lxc-deploy.yml`
- `scripts/lab/pve-service-deploy`
- `ansible/roles/shared_nfs_mount/**`
- Jellyfin role/play + healthcheck script(s)
- `docs/operations/lxc-deploy-ci.md`

## Rollback / Safety Notes
- Blast-radius summary must be reviewed for replace/destroy.
- Destructive actions require explicit confirmations (LAB/PROD).
- Policy is to fail early on host binds (avoid root token dependency).
