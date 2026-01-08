module "monitoring_lxc" {
  source = "../../modules/lxc_service"

  name         = "monitoring-lxc"
  hostname     = "monitoring"
  node         = var.proxmox_node
  ostemplate   = var.lxc_template
  storage_pool = var.storage_pool

  cores   = 2
  memory  = 4096
  disk_gb = 32

  bridge          = var.services_bridge
  ip              = var.service_ips["monitoring"]
  gateway         = var.network_gateway
  nameserver      = var.nameserver
  searchdomain    = var.searchdomain
  ssh_public_keys = join("\n", var.ssh_public_keys)

  mountpoints = values(lookup(var.service_mountpoints, "monitoring", {}))
}
