module "ntfy_lxc" {
  source = "../../modules/lxc_service"

  name         = "ntfy-lxc"
  hostname     = "${var.hostname_prefix}ntfy"
  node         = var.proxmox_node
  ostemplate   = var.lxc_template
  storage_pool = var.storage_pool

  # ntfy is a lightweight Go binary serving SQLite-backed state; the financial-scenario
  # allocation is the ceiling, and this is deliberately smaller (research R-008).
  cores   = 1
  memory  = 512
  disk_gb = 8

  bridge          = var.services_bridge
  ip              = var.service_ips["ntfy"]
  gateway         = var.network_gateway
  nameserver      = var.nameserver
  searchdomain    = var.searchdomain
  ssh_public_keys = join("\n", var.ssh_public_keys)
  # No features_mount: all state (SQLite message cache, auth DB) lives on local disk,
  # never NFS, and is disposable — rebuilt from config on every deploy (R-008, FR-014).
}
