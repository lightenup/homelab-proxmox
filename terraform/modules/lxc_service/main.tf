resource "proxmox_lxc" "this" {
  target_node = var.node
  ostemplate  = var.ostemplate

  unprivileged = true
  onboot       = true
  start        = true

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

  nameserver   = var.nameserver
  searchdomain = var.searchdomain

  ssh_public_keys = var.ssh_public_keys

  features {
    nesting = true
    mount   = var.features_mount
  }

  dynamic "mountpoint" {
    for_each = var.mountpoints
    content {
      mp      = mountpoint.value.mp
      size    = mountpoint.value.size != null ? mountpoint.value.size : "0G"
      slot    = mountpoint.value.slot != null ? mountpoint.value.slot : 0
      key     = mountpoint.value.key != null ? mountpoint.value.key : ""
      storage = mountpoint.value.storage != null ? mountpoint.value.storage : var.storage_pool
      volume  = mountpoint.value.volume
    }
  }

  lifecycle {
    ignore_changes = [
      mountpoint,
      # Ignore changes to these as they are reset to defaults by provider if not specified
      # but we want to keep them if they were set manually or by other means
      # Actually, we set them explicitly now, so maybe we don't need to ignore them?
      # But mountpoint is definitely needed to be ignored if we manage it via Ansible.
    ]
  }

  # Add more options as needed (features, unprivileged, etc.)
}
