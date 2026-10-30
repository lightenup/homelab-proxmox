module "market_model_lxc" {
  source = "../../modules/lxc_service"

  name         = "market-model-lxc"
  hostname     = "${var.hostname_prefix}market-model"
  node         = var.proxmox_node
  ostemplate   = var.lxc_template
  storage_pool = var.storage_pool

  cores   = 2
  memory  = 2048
  disk_gb = 16

  bridge          = var.services_bridge
  ip              = var.service_ips["market-model"]
  gateway         = var.network_gateway
  nameserver      = var.nameserver
  searchdomain    = var.searchdomain
  ssh_public_keys = join("\n", var.ssh_public_keys)
  # No features_mount: market-model has no in-guest NFS mount (D-001).
}
