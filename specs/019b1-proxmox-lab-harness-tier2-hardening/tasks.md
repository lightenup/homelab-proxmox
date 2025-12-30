# Tasks: Tier 2 Hardening

**Feature**: `019b1-proxmox-lab-harness-tier2-hardening`

## Harness Script Updates (`scripts/lab/pve-lab`)

- [x] **T001**: Update `check_host_requirements` to check for `kvm_amd` module as well as `kvm_intel`. (FR-010)
- [x] **T002**: Add `check_network_requirements` function to validate FQDN resolution and internet connectivity (e.g., `curl -I https://deb.debian.org`). (FR-009)
- [x] **T003**: Implement `collect_artifacts` function to run after playbook execution (success or fail). (FR-011)
    - Capture `pveversion`, `pvesh version`, `apt-cache policy`, `systemctl status`.
    - Save to `artifacts/019-lab/<runid>/`.
- [x] **T004**: Implement `rotate_artifacts` to keep only the last 5 run directories in `artifacts/019-lab/`. (FR-012)

## Playbook Hardening (`ansible/playbooks/lab_tier2_pve.yml`)

- [x] **T005**: Implement `debconf` preseeding for Postfix (`postfix/main_mailer_type='Local only'`, `postfix/mailname=<hostname>`). (FR-005)
- [x] **T006**: Configure `needrestart` with `NEEDRESTART_MODE=a` to restart services automatically. (FR-006)
- [x] **T007**: Replace GPG file copy with `get_url` to `/usr/share/keyrings/` for Proxmox release key. (FR-001)
- [x] **T008**: Configure `apt_repository` for Proxmox VE no-subscription with `signed-by` reference. (FR-001a)
- [x] **T009**: Ensure `apt_repository` for Enterprise repo is `state: absent`. (FR-002)
- [x] **T010**: Add `apt-cache policy` check to validate repo availability before installing packages. (FR-003)
- [x] **T011**: Add `DEBIAN_FRONTEND=noninteractive` environment variable to all `apt` and `package` tasks. (FR-004)
- [x] **T012**: Add `retries: 3` and `delay: 10` to all `apt` tasks. (FR-007)

## Documentation (`docs/architecture/019-proxmox-lab-harness.md`)

- [x] **T013**: Update documentation with Tier 2 hardening details (repo setup, non-interactive measures, artifacts).
