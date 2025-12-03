resource "proxmox_lxc" "this" {
  target_node = var.node
  ostemplate  = var.ostemplate

  hostname = var.hostname

  cores  = var.cores
  memory = var.memory

  rootfs {
    storage = var.storage_pool
    size    = "${var.disk_gb}G"
  }

  network {
    name   = "eth0"
    bridge = var.bridge
    ip     = var.ip
    gw     = var.gateway
  }

  # Add more options as needed (features, unprivileged, etc.)
}
