locals {
  all_mounts_jellyfin     = lookup(var.service_mountpoints, "jellyfin", {})
  storage_mounts_jellyfin = { for k, v in local.all_mounts_jellyfin : k => v if !startswith(v.volume, "/") }
}

module "jellyfin_lxc" {
  source = "../../modules/lxc_service"

  name         = "jellyfin-lxc"
  hostname     = "${var.hostname_prefix}jellyfin"
  node         = var.proxmox_node
  ostemplate   = var.lxc_template
  storage_pool = var.storage_pool

  cores   = 2
  memory  = 2048
  disk_gb = 32

  bridge          = var.services_bridge
  ip              = var.service_ips["jellyfin"]
  gateway         = var.network_gateway
  nameserver      = var.nameserver
  searchdomain    = var.searchdomain
  ssh_public_keys = join("\n", var.ssh_public_keys)

  # Required for in-guest NFS mounts inside an unprivileged LXC.
  features_mount = "nfs"

  mountpoints = values(local.storage_mounts_jellyfin)
}
