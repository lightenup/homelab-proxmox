locals {
  all_mounts_reverse_proxy     = lookup(var.service_mountpoints, "reverse_proxy", {})
  storage_mounts_reverse_proxy = { for k, v in local.all_mounts_reverse_proxy : k => v if !startswith(v.volume, "/") }
}

module "reverse_proxy_lxc" {
  source = "../../modules/lxc_service"

  name         = "proxy-lxc"
  hostname     = "proxy"
  node         = var.proxmox_node
  ostemplate   = var.lxc_template
  storage_pool = var.storage_pool

  cores   = 1
  memory  = 1024
  disk_gb = 16

  bridge          = var.services_bridge
  ip              = var.service_ips["reverse_proxy"]
  gateway         = var.network_gateway
  nameserver      = var.nameserver
  searchdomain    = var.searchdomain
  ssh_public_keys = join("\n", var.ssh_public_keys)

  mountpoints = values(local.storage_mounts_reverse_proxy)
}
