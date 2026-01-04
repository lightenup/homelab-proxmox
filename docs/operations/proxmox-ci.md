# Proxmox CI Runbook (pi-ci ➜ PVE)

Audience: operators running `proxmox-apply` on pi-ci. Goal: keep all automation on PVE under the `ci` account with constrained sudo, durable artifacts at `/var/lib/homelab-proxmox/artifacts`, and predictable evidence when provisioning stalls.

## Workflow at a Glance

1. **Runner:** pi-ci self-hosted runner executes `.github/workflows/proxmox-apply.yml`.
2. **Artifact root:** Runtime outputs live on PVE at `/var/lib/homelab-proxmox/artifacts` (owned by `ci`, excluded from rsync).
3. **Guardrails:** `scripts/lab/guardrails.sh ensure-artifacts` prepares the artifact root; pve-lab uses sudo helper and provisioning timeouts with evidence hooks.
4. **Main action:** Workflow syncs repo to `/home/ci/homelab-proxmox/` and runs `scripts/lab/pve-lab rebuild --apply --verify --apply-sudoers` as `ci`.
5. **Smoke checks:** Sudo smoke verifies `sudo -n true`, `sudo -n qm --version`, `sudo -n pveversion` succeed and `sudo -n bash` is denied.
6. **Evidence:** Latest run ID is captured, evidence pack tarred from `/var/lib/homelab-proxmox/artifacts/lab-runs/<runid>` and verified offline via `scripts/lab/ci-verify.sh`.

Related:

- LXC gated service deploy workflow: [docs/operations/lxc-deploy-ci.md](docs/operations/lxc-deploy-ci.md)

## Sudoers Policy (ci)

- Deployed to `/etc/sudoers.d/ci-homelab` from `scripts/lab/profiles.d/ci-sudoers.conf` via `pve-lab --apply-sudoers`.
- Allows non-interactive (`sudo -n`) calls to `qm`, `pct`, `pvesh`, `pveversion`, selected `systemctl` actions, and guardrail helpers; denies shells/escalation.
- Defaults include `Defaults:ci !requiretty`. Policy is validated with `visudo -c` before apply.

## Artifact Handling

- All logs, locks, evidence live under `/var/lib/homelab-proxmox/artifacts`; workflows must **never** rsync or delete this path.
- `guardrails.sh ensure-artifacts` creates/owns the directory for `ci` and is invoked early in the workflow.

## Runbook: Rerun proxmox-apply

1. Trigger `Proxmox Apply + Verify` in GitHub Actions (pi-ci runner).
2. Monitor steps: offline fixtures → ensure-artifacts → rsync → rebuild/apply/verify → sudo smoke → fetch/verify evidence.
3. On success, evidence is published as `evidence-<RUN_ID>` artifact. Keep packs for audit/drift checks.

## Runbook: Inspect Evidence Bundle

```bash
# After workflow finishes and evidence is downloaded
ls evidence/<RUN_ID>/
# Key contents
#  summary.json, checks.json, provenance.json
#  reports/host/, reports/templates/, logs/
# Provisioning timeouts include qm status/config, cloud-init files, and network probes
```

## IaC Posture Requirements

- **Ansible:** Default remote user must be `ci` with non-interactive sudo. `ansible/ansible.cfg` sets `remote_user = ci` and `become_flags = -n`; playbooks should avoid `remote_user: root` except for initial bootstrap.
- **Terraform:** Use a non-root API token (e.g., `ci-terraform@pve!token`). Secrets are provided via `TF_VAR_proxmox_api_token_id` and `TF_VAR_proxmox_api_token_secret`; do not embed tokens in files.
- **Validation:** Run `./scripts/lab/ci-validate-iac.sh` locally or let the workflow step fail fast if posture drifts.

## Secrets & Roles

- **SSH:** pi-ci uses the `ci` SSH key (alias `pve`) with `StrictHostKeyChecking=no`, `CheckHostIP=no`, and ephemeral known_hosts.
- **Ansible Vault:** Playbooks require `ANSIBLE_VAULT_PASSWORD` (provided as a GitHub Secret on pi-ci; when running locally via `act`, use `--secret-file`).
- **Sudo:** `ci` must belong to the sudoers policy deployed by `pve-lab --apply-sudoers`.
- **Terraform token:** Provision via Proxmox UI/API for user `ci` or another non-root account scoped to required resources; store in GitHub Secrets/environment (never committed).

## Local Validation with act (macOS)

1. Create a local secrets file (gitignored):

```bash
cp .act.secrets.example .act.secrets
${EDITOR:-nano} .act.secrets
```

2. Run the workflow locally (requires your `.act-ssh/` to contain a working `ci@pve` key/config):

```bash
act workflow_dispatch -W .github/workflows/proxmox-apply.yml -j apply \
	--secret-file .act.secrets \
	--container-options "-v $(pwd)/.act-ssh:/root/.ssh:ro"
```

## Troubleshooting

- **SSH host key errors:** Confirm `CheckHostIP=no` is present; rerun workflow to refresh the keyless session.
- **Artifacts permission issues:** Re-run `guardrails.sh ensure-artifacts` or `sudo chown -R ci:ci /var/lib/homelab-proxmox/artifacts`.
- **Sudo smoke failure:** Re-apply sudoers with `pve-lab --apply-sudoers` and verify `visudo -c` output.
- **Provisioning timeout:** Inspect evidence pack (qm status/config, cloud-init, network probe logs) under the captured `RUN_ID`.
