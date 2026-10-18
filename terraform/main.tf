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

module "financial_scenario_lxc" {
  source = "./modules/lxc_service"

  name         = "financial-scenario-lxc"
  hostname     = "financial-scenario"
  node         = var.proxmox_node
  ostemplate   = var.lxc_template
  storage_pool = var.storage_pool

  cores   = 2
  memory  = 2048
  disk_gb = 16

  bridge          = var.services_bridge
  ip              = var.service_ips["financial-scenario"]
  gateway         = var.network_gateway
  nameserver      = var.nameserver
  searchdomain    = var.searchdomain
  ssh_public_keys = join("\n", var.ssh_public_keys)

  # Backup destination is a host-NFS-mount + bind-mount (see service_mountpoints
  # in the environment tfvars) — the proven fleet pattern. In-guest NFS is NOT
  # used here: an unprivileged LXC cannot issue the NFS mount syscall (EPERM),
  # so features_mount = "nfs" would be dead config.
}

module "eurooffice_lxc" {
  source = "./modules/lxc_service"

  name         = "eurooffice-lxc"
  hostname     = "eurooffice"
  node         = var.proxmox_node
  ostemplate   = var.lxc_template
  storage_pool = var.storage_pool

  cores   = 4
  memory  = 4096
  disk_gb = 15

  bridge          = var.services_bridge
  ip              = var.service_ips["eurooffice"]
  gateway         = var.network_gateway
  nameserver      = var.nameserver
  searchdomain    = var.searchdomain
  ssh_public_keys = join("\n", var.ssh_public_keys)
  # nesting=true is already enabled for all LXCs in the lxc_service module.
  # No features_mount: eurooffice has no in-guest NFS mount (documents live in Nextcloud).
}

module "market_model_lxc" {
  source = "./modules/lxc_service"

  name         = "market-model-lxc"
  hostname     = "market-model"
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

module "llm_router_lxc" {
  source = "./modules/lxc_service"

  name         = "llm-router-lxc"
  hostname     = "llm-router"
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
