module "llm_router_lxc" {
  source = "../../modules/lxc_service"

  name         = "llm-router-lxc"
  hostname     = "${var.hostname_prefix}llm-router"
  node         = var.proxmox_node
  ostemplate   = var.lxc_template
  storage_pool = var.storage_pool

  cores   = 2
  memory  = 4096
  disk_gb = 16

  bridge          = var.services_bridge
  ip              = var.service_ips["llm-router"]
  gateway         = var.network_gateway
  nameserver      = var.nameserver
  searchdomain    = var.searchdomain
  ssh_public_keys = join("\n", var.ssh_public_keys)
  # No features_mount: no user data is persisted, and no NFS mount is needed (FR-012, spec 064).
  # Sized 4GB (not the 2GB baseline other proxy-only services use) because this LXC also hosts the
  # LiteLLM Postgres backing service (FR-014, spec 064).
}
