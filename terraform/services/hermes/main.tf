module "hermes_lxc" {
  source = "../../modules/lxc_service"

  name         = "hermes-lxc"
  hostname     = "hermes"
  node         = var.proxmox_node
  ostemplate   = var.lxc_template
  storage_pool = var.storage_pool

  # Provisional (research R-007) — start from the financial-scenario allocation, adjusted
  # upward because this LXC also runs the SearXNG sidecar and in-container Whisper STT /
  # transformers TTS models, neither of which financial-scenario carries. T082 measures
  # actual use and right-sizes this against it rather than this initial guess.
  cores   = 4
  memory  = 6144
  disk_gb = 32

  bridge          = var.services_bridge
  ip              = var.service_ips["hermes"]
  gateway         = var.network_gateway
  nameserver      = var.nameserver
  searchdomain    = var.searchdomain
  ssh_public_keys = join("\n", var.ssh_public_keys)
  # No features_mount: hermes_data_dir lives on local disk, never NFS (FR-019). The backup
  # destination is a host-NFS-mount + bind-mount applied by pve-service-deploy via
  # service_mountpoints in the environment tfvars, not by this Terraform root — see
  # ansible/roles/hermes_backup/tasks/main.yml, mirroring financial-scenario.
}
