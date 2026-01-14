# LXC Deploy CI/CD (Gated)

This repository provides a gated GitHub Actions workflow for deploying a single Proxmox LXC “service” (baseline example: `jellyfin`) with least privilege.

## Goals

- Plan/preflight produces deterministic artifacts and does not change Proxmox.
- LAB can auto-apply.
- PROD is blocked by default and requires GitHub Environment approval + an explicit confirmation input.
- Every run produces an offline-verifiable evidence bundle stored on PVE.

## Workflow

- Workflow file (LAB): `.github/workflows/lxc-deploy-lab.yml`
- Orchestrator (runs on PVE): `scripts/lab/pve-service-deploy`
- Optional internal toggle: set repository variable `USE_PY_RUNNER=true` to invoke the Python runner on PVE (workflow_dispatch inputs remain unchanged)
- Evidence storage (on PVE): `/var/lib/homelab-proxmox/artifacts/service-deploy-runs/<run_id>`

## Required Secrets

- `ANSIBLE_VAULT_PASSWORD`
- Terraform Proxmox provider credentials (repo-specific; must be injected via GitHub Secrets/Environments and never committed)

## Vault Files on PVE (Required)

This repo intentionally gitignores `**/vault.yml`, so the workflow does not sync vault files to PVE.

On the Proxmox host (PVE), place your encrypted vault files under:

- `/var/lib/homelab-proxmox/vault/group_vars/all/vault.yml`
- `/var/lib/homelab-proxmox/vault/group_vars/services/secrets.yml`

The orchestrator will symlink this into the synced repo during a run.

### Migration checklist (recommended: per-environment vault)

Use this when migrating from any repo-tracked vault files to the PVE-sourced vault model.

1. Stop tracking the repo copy (one-time):

	- `git rm --cached ansible/group_vars/services/secrets.yml`
	- Ensure `.gitignore` covers `*secret*.yml` (it should).
	- Keep your local working copy file if you need it temporarily for copying; just don’t commit it.

2. Create per-environment vault directories on PVE:

	- `ssh ci@pve 'sudo mkdir -p /var/lib/homelab-proxmox/vault/{lab,prod}/group_vars/{all,services} && sudo chown -R ci:ci /var/lib/homelab-proxmox/vault'`

3. Create (or copy) the encrypted vault files for LAB and PROD:

	- LAB targets:
	  - `/var/lib/homelab-proxmox/vault/lab/group_vars/all/vault.yml`
	  - `/var/lib/homelab-proxmox/vault/lab/group_vars/services/secrets.yml`

	- PROD targets:
	  - `/var/lib/homelab-proxmox/vault/prod/group_vars/all/vault.yml`
	  - `/var/lib/homelab-proxmox/vault/prod/group_vars/services/secrets.yml`

	If you already have local encrypted files, you can copy them with `scp`.

4. Quick sanity check on PVE (files exist and are readable by `ci`):

	- `ssh ci@pve 'ls -l /var/lib/homelab-proxmox/vault/lab/group_vars/all/vault.yml /var/lib/homelab-proxmox/vault/lab/group_vars/services/secrets.yml'`
	- `ssh ci@pve 'ls -l /var/lib/homelab-proxmox/vault/prod/group_vars/all/vault.yml /var/lib/homelab-proxmox/vault/prod/group_vars/services/secrets.yml'`

5. Validate LAB uses LAB vault (safe, non-destructive):

	- Run the workflow `plan` with `environment=lab`.
	- Confirm the run succeeds and evidence verification passes.

6. Validate PROD gating still blocks by default:

	- Trigger `workflow_dispatch` with `environment=prod` and *omit* `confirm` (or set a wrong confirm).
	- Expected: PROD apply job must not run.

7. Validate PROD uses PROD vault (only when you’re ready):

	- Trigger with `environment=prod` and `confirm=deploy-prod` (and approve the GitHub `prod` Environment).
	- Expected: PROD apply proceeds and evidence verification passes.

### How to create the vault files

**Model**: one shared vault password stored as the GitHub Secret `ANSIBLE_VAULT_PASSWORD` (and used locally via `act --secret-file`).

1. Create encrypted files locally (example using a temporary password file):

	 - Create a password file (protect permissions):
		 - `umask 077; printf '%s' "$ANSIBLE_VAULT_PASSWORD" > /tmp/.ansible_vault_pass`

	 - Create the files:
		 - `ANSIBLE_VAULT_PASSWORD_FILE=/tmp/.ansible_vault_pass ansible-vault create ansible/group_vars/all/vault.yml`
		 - `ANSIBLE_VAULT_PASSWORD_FILE=/tmp/.ansible_vault_pass ansible-vault create ansible/group_vars/services/secrets.yml`

	 Notes:
	 - Keep the contents as normal YAML (usually a mapping). Even an empty mapping is fine (e.g. `{}`), as long as the file is vault-encrypted.
	 - These files should not be committed to git. The repo is set up so CI sources them from PVE.

2. Copy them to PVE (owned by `ci` so the runner can read them):

	 - `ssh ci@pve 'sudo mkdir -p /var/lib/homelab-proxmox/vault/group_vars/{all,services} && sudo chown -R ci:ci /var/lib/homelab-proxmox/vault'`
	 - `scp ansible/group_vars/all/vault.yml ci@pve:/var/lib/homelab-proxmox/vault/group_vars/all/vault.yml`
	 - `scp ansible/group_vars/services/secrets.yml ci@pve:/var/lib/homelab-proxmox/vault/group_vars/services/secrets.yml`

### What should each file contain?

- `group_vars/all/vault.yml`: global/shared secrets used by multiple playbooks/roles (credentials, API keys, passwords that apply across the homelab).
- `group_vars/services/secrets.yml`: service-related secrets that aren’t host-specific (for example service API keys/tokens shared across multiple service hosts).

If you’re unsure where a given secret belongs, default to `group_vars/all/vault.yml` for shared credentials and use `services/secrets.yml` only when it’s clearly service-scoped.

### Vault IDs (recommended: per environment) with one password

To reduce confusion and mishaps, prefer **per-environment vault ids**:

- LAB vault id: `lab`
- PROD vault id: `prod`

You can still keep **one shared password** (the GitHub Secret `ANSIBLE_VAULT_PASSWORD`). The deploy orchestrator will automatically set `ANSIBLE_VAULT_IDENTITY_LIST` to `${VAULT_ID}@${ANSIBLE_VAULT_PASSWORD_FILE}`.

**Recommended layout (PVE):** keep separate vault trees per environment:

- `/var/lib/homelab-proxmox/vault/lab/group_vars/all/vault.yml`
- `/var/lib/homelab-proxmox/vault/lab/group_vars/services/secrets.yml`
- `/var/lib/homelab-proxmox/vault/prod/group_vars/all/vault.yml`
- `/var/lib/homelab-proxmox/vault/prod/group_vars/services/secrets.yml`

The orchestrator will automatically prefer `/var/lib/homelab-proxmox/vault/<environment>/...` if it exists.

**Creating files with vault ids:**

- LAB:
	- `ansible-vault create --vault-id lab@prompt ansible/group_vars/all/vault.yml`
	- `ansible-vault create --vault-id lab@prompt ansible/group_vars/services/secrets.yml`

- PROD:
	- `ansible-vault create --vault-id prod@prompt ansible/group_vars/all/vault.yml`
	- `ansible-vault create --vault-id prod@prompt ansible/group_vars/services/secrets.yml`

Notes:
- The workflow sets `VAULT_ID=lab` for LAB and `VAULT_ID=prod` for PROD when invoking the orchestrator.
- If you don’t want env-separated vault directories, you can keep a single vault tree under `/var/lib/homelab-proxmox/vault/...` and just use vault ids; but separate directories are safer.

## Inputs

The workflow supports these `workflow_dispatch` inputs:

- `service`: service slug (e.g. `jellyfin`)
- `apply`: `true` to run plan+apply, `false` for plan-only
- `confirm_destructive`: required only when the plan contains replace/destroy

## PROD Gating

PROD apply is protected by two independent gates:

1. GitHub Actions Environment approval via the `prod` Environment (configure required reviewers in GitHub).
2. An explicit confirmation string: set `confirm=deploy-prod` when triggering the workflow.

If the reviewed plan includes any **replace** or **destroy** actions, ensure you review the plan evidence carefully before confirming the PROD apply.

## Operating Model

- CI connects to Proxmox as `ci@pve` (no root SSH).
- Any required elevation must be non-interactive (`sudo -n`) and restricted to specific commands.

## Shared media mounts (in-guest)

Spec 023 policy is **no host-path bind mounts in Terraform**. Shared media must be mounted **inside the container**.

- Role: `ansible/roles/shared_nfs_mount`
- Mount: `192.168.1.109:/volume1/video` → `/media/video`
- Options: read-only with automount (`ro,nofail,_netdev,x-systemd.automount`)

Evidence produced during apply includes:
- `reports/workload/shared-nfs-mount.txt`
- `reports/assertions.workload.json` (includes `SD-003` result)
- `reports/healthcheck/<service>.txt` (includes a mount check for Jellyfin)

Note: this means you do **not** need to mount the Jellyfin media export on PVE for the deploy workflow.

## Terraform state

Terraform state is per-service on PVE:

- `/var/lib/homelab-proxmox/state/services/<service>/terraform.tfstate`

After a successful apply, the orchestrator backs up that state file to Synology and captures proof in evidence:

- `reports/apply/state-backup.txt`

## Evidence Verification

The workflow fetches the evidence bundle from PVE and runs offline verification using:

- `scripts/lab/ci-verify.sh`

## Real LAB validation (recommended)

When changing the deploy orchestration or evidence semantics, validate against LAB with a real GitHub Actions run:

1. Trigger `.github/workflows/lxc-deploy-lab.yml` with:
	- `apply=false` (plan-only)
	- `service=<service>`
2. Download the evidence artifact and run offline verification:
	- `./scripts/lab/ci-verify.sh evidence/<run_id>`
3. Render the bounded operator summary from the evidence pack:
	- `PYTHONPATH=python/src python3 -m homelab_proxmox_orchestrator.cli summary --evidence-pack evidence/<run_id>`
4. Spot-check that logs/summaries do not contain secrets (vault password must never appear).

## Local runs (act)

This repo supports local workflow simulation using `act`. See `docs/operations/proxmox-ci.md` for runner prerequisites and secret handling.

### Quick start (LAB)

1. Create a local secrets file (gitignored):

```bash
cp .act.secrets.example .act.secrets
${EDITOR:-nano} .act.secrets
```

2. Create a `workflow_dispatch` event payload with inputs:

```bash
cat > /tmp/act-lxc-deploy-lab.json <<'JSON'
{
	"inputs": {
		"service": "jellyfin",
		"apply": "false",
		"confirm_destructive": "false"
	}
}
JSON
```

3. Run plan only (safe):

```bash
act workflow_dispatch \
	-W .github/workflows/lxc-deploy-lab.yml \
	-j plan \
	-e /tmp/act-lxc-deploy-lab.json \
	--secret-file .act.secrets \
	--container-options "-v $(pwd)/.act-ssh:/root/.ssh:ro"
```

4. Run the full LAB flow (plan + apply). Warning: this does real SSH to PVE and will run `apply`:

```bash
act workflow_dispatch \
	-W .github/workflows/lxc-deploy-lab.yml \
	-e /tmp/act-lxc-deploy-lab.json \
	--secret-file .act.secrets \
	--container-options "-v $(pwd)/.act-ssh:/root/.ssh:ro"
```

Notes:
- The workflow defaults `PROXMOX_HOST` to `pve`. If your SSH config uses a different host alias, run with `-s PROXMOX_HOST=<alias>` or set `PROXMOX_HOST` in your environment.
- Your `.act-ssh/` should contain a working key + config for `ci@pve` (mounted read-only into the container).
