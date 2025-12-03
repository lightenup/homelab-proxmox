output "ipv4" {
  value = proxmox_lxc.this.network[0].ip
}
