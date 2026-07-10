module "eurooffice_lxc" {
  source = "../../modules/lxc_service"

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
