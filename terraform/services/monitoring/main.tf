locals {
  all_mounts_monitoring     = lookup(var.service_mountpoints, "monitoring", {})
  storage_mounts_monitoring = { for k, v in local.all_mounts_monitoring : k => v if !startswith(v.volume, "/") }
}

module "monitoring_lxc" {
  source = "../../modules/lxc_service"

  name         = "monitoring-lxc"
  hostname     = "${var.hostname_prefix}monitoring"
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

  mountpoints = values(local.storage_mounts_monitoring)
}
