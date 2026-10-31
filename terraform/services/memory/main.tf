module "memory_lxc" {
  source = "../../modules/lxc_service"

  name         = "memory-lxc"
  hostname     = "${var.hostname_prefix}memory"
  node         = var.proxmox_node
  ostemplate   = var.lxc_template
  storage_pool = var.storage_pool

  # Spec 097 research R-005: the spike measured Hindsight at about 310 MiB and Postgres at
  # about 50-70 MiB idle; the web UI adds 100-200 MB. 2048 MB keeps SC-007's 30 % headroom
  # after the Open WebUI import. T074 re-measures after a week.
  cores   = 2
  memory  = 2048
  disk_gb = 16

  bridge          = var.services_bridge
  ip              = var.service_ips["memory"]
  gateway         = var.network_gateway
  nameserver      = var.nameserver
  searchdomain    = var.searchdomain
  ssh_public_keys = join("\n", var.ssh_public_keys)
  # No features_mount: the Postgres store lives on local disk, never NFS (FR-007). The backup
  # destination is a host NFS mount plus bind mount applied by pve-service-deploy from
  # service_mountpoints in the environment tfvars, as for hermes.
}
