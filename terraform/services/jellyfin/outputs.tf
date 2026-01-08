output "ansible_inventory" {
  value = {
    services = {
      jellyfin = module.jellyfin_lxc.ipv4
    }
  }
}
