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
    # mount feature is applied host-side by orchestrator via `pct set` to avoid API token permission limits
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
      features,
      mountpoint,
      # The deploy script injects a ci@pve key at LXC creation time; ignore drift
      # so key changes never force a destructive LXC replacement.
      ssh_public_keys,
    ]
  }

  # Add more options as needed (features, unprivileged, etc.)
}
