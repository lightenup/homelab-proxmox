module "immich_lxc" {
  source = "../../modules/lxc_service"

  name         = "immich-lxc"
  hostname     = "immich"
  node         = var.proxmox_node
  ostemplate   = var.lxc_template
  storage_pool = var.storage_pool

  cores   = 4
  memory  = 4096
  disk_gb = 64

  bridge          = var.services_bridge
  ip              = var.service_ips["immich"]
  gateway         = var.network_gateway
  nameserver      = var.nameserver
  searchdomain    = var.searchdomain
  ssh_public_keys = join("\n", var.ssh_public_keys)

  mountpoints = values(lookup(var.service_mountpoints, "immich", {}))
}
