module "immich_lxc" {
  source = "./modules/lxc_service"

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
}

module "adguard_lxc" {
  source = "./modules/lxc_service"

  name         = "adguard-lxc"
  hostname     = "adguard"
  node         = var.proxmox_node
  ostemplate   = var.lxc_template
  storage_pool = var.storage_pool

  cores   = 2
  memory  = 2048
  disk_gb = 16

  bridge          = var.services_bridge
  ip              = var.service_ips["adguard"]
  gateway         = var.network_gateway
  nameserver      = var.nameserver
  searchdomain    = var.searchdomain
  ssh_public_keys = join("\n", var.ssh_public_keys)
}

module "homeassistant_lxc" {
  source = "./modules/lxc_service"

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
}

module "reverse_proxy_lxc" {
  source = "./modules/lxc_service"

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
}

module "monitoring_lxc" {
  source = "./modules/lxc_service"

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
}

locals {
  all_mounts_nextcloud_root     = lookup(var.service_mountpoints, "nextcloud", {})
  storage_mounts_nextcloud_root = { for k, v in local.all_mounts_nextcloud_root : k => v if !startswith(v.volume, "/") }
  all_mounts_jellyfin_root      = lookup(var.service_mountpoints, "jellyfin", {})
  storage_mounts_jellyfin_root  = { for k, v in local.all_mounts_jellyfin_root : k => v if !startswith(v.volume, "/") }
}

module "nextcloud_lxc" {
  source = "./modules/lxc_service"

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

  mountpoints = values(local.storage_mounts_nextcloud_root)
}

# Baseline example for specs/022-lxc-gated-deploy
module "jellyfin_lxc" {
  source = "./modules/lxc_service"

  name         = "jellyfin-lxc"
  hostname     = "jellyfin"
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

  mountpoints = values(local.storage_mounts_jellyfin_root)
}
