resource "proxmox_lxc" "this" {
  target_node = var.node
  vmid        = var.vmid
  ostemplate  = var.ostemplate

  hostname = var.hostname

  cores  = var.cores
  memory = var.memory

  onboot       = var.onboot
  unprivileged = var.unprivileged
  start        = true

  ssh_public_keys = join("\n", var.ssh_public_keys)

  features {
    nesting = true
  }

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
}
