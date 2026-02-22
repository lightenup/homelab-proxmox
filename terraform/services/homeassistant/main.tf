locals {
  all_mounts_homeassistant     = lookup(var.service_mountpoints, "homeassistant", {})
  storage_mounts_homeassistant = { for k, v in local.all_mounts_homeassistant : k => v if !startswith(v.volume, "/") }
}

module "homeassistant_lxc" {
  source = "../../modules/lxc_service"

  name         = "ha-lxc"
  hostname     = "homeassistant"
  node         = var.proxmox_node
  ostemplate   = var.lxc_template
  storage_pool = var.storage_pool

  cores   = 2
  memory  = 2048
  disk_gb = 32

  bridge          = var.services_bridge
  ip              = var.service_ips["homeassistant"]
  gateway         = var.network_gateway
  nameserver      = var.nameserver
  searchdomain    = var.searchdomain
  ssh_public_keys = join("\n", var.ssh_public_keys)

  mountpoints = values(local.storage_mounts_homeassistant)
}
