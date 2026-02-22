locals {
  all_mounts_nextcloud     = lookup(var.service_mountpoints, "nextcloud", {})
  storage_mounts_nextcloud = { for k, v in local.all_mounts_nextcloud : k => v if !startswith(v.volume, "/") }
}

module "nextcloud_lxc" {
  source = "../../modules/lxc_service"

  name         = "nextcloud-lxc"
  hostname     = "nextcloud"
  node         = var.proxmox_node
  ostemplate   = var.lxc_template
  storage_pool = var.storage_pool

  cores   = 4
  memory  = 4096
  disk_gb = 32

  bridge          = var.services_bridge
  ip              = var.service_ips["nextcloud"]
  gateway         = var.network_gateway
  nameserver      = var.nameserver
  searchdomain    = var.searchdomain
  ssh_public_keys = join("\n", var.ssh_public_keys)

  # Required for in-guest NFS mounts inside an unprivileged LXC.
  features_mount = "nfs"

  mountpoints = values(local.storage_mounts_nextcloud)
}
