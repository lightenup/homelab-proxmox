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

  bridge  = var.services_bridge
  ip      = "192.168.20.13/24"
  gateway = "192.168.20.1"
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

  bridge  = var.services_bridge
  ip      = "192.168.20.10/24"
  gateway = "192.168.20.1"
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

  bridge  = var.services_bridge
  ip      = "192.168.20.12/24"
  gateway = "192.168.20.1"
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

  bridge  = var.services_bridge
  ip      = "192.168.20.11/24"
  gateway = "192.168.20.1"
}
