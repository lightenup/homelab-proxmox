# Bootstrap notes – GitHub Actions runner on Raspberry Pi

- Install latest Raspberry Pi OS.
- Install git, curl, jq, ansible, terraform.
- Create a `runner` user.
- Register a self-hosted runner for this repo from GitHub:
  - Settings → Actions → Runners → New self-hosted runner.
- Give the runner labels like: `self-hosted`, `pi`.
- Ensure the runner has network access to:
  - Proxmox API
  - LXCs/VMs
  - Synology (for backups)
