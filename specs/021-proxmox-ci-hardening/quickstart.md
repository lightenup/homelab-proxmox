# Quickstart: Proxmox CI Hardening

## Rerun proxmox-apply on pi-ci

1. Trigger **Proxmox Apply + Verify** in GitHub Actions (pi-ci self-hosted runner).
2. Observe steps: offline fixtures → ensure-artifacts → rsync (excludes artifacts) → `pve-lab rebuild --apply --verify --apply-sudoers` → sudo smoke → fetch/verify evidence.
3. Find `RUN_ID` in workflow logs (exported by rebuild step) and download the `evidence-<RUN_ID>` artifact.

## Manual rerun from pi-ci shell

```bash
ssh ci@pi-ci-host  # or use runner console
cd /home/ci/homelab-proxmox
./scripts/lab/guardrails.sh ensure-artifacts
rsync -az --delete --exclude '.git' --exclude 'scripts/lab/artifacts/' --exclude 'artifacts/' ./ ci@pve:/home/ci/homelab-proxmox/
ssh ci@pve "cd /home/ci/homelab-proxmox/scripts/lab && ARTIFACT_ROOT=/var/lib/homelab-proxmox/artifacts ./pve-lab rebuild --apply --verify --apply-sudoers"
ssh ci@pve 'ls -1t /var/lib/homelab-proxmox/artifacts | head -1'  # capture RUN_ID
```

## Review an evidence bundle

```bash
# Assuming evidence-${RUN_ID}.tgz downloaded from workflow artifacts
mkdir -p /tmp/evidence && tar xzf evidence-${RUN_ID}.tgz -C /tmp/evidence
ls /tmp/evidence/${RUN_ID}/
# Verify structure and checks
./scripts/lab/ci-verify.sh /tmp/evidence/${RUN_ID}
# Key files: summary.json, checks.json, provenance.json, reports/host/, reports/templates/, logs/
```

## Troubleshooting shortcuts

- Re-apply sudoers: `ssh ci@pve 'cd /home/ci/homelab-proxmox/scripts/lab && ./pve-lab --apply-sudoers'`
- Fix artifacts ownership: `ssh ci@pve 'sudo chown -R ci:ci /var/lib/homelab-proxmox/artifacts'`
- Provisioning timeout evidence lives under `/var/lib/homelab-proxmox/artifacts/<RUN_ID>/`.
